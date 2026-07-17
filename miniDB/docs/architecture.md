# System Architecture

## Overview

miniDB is a minimal relational database engine built from scratch in Python.
It implements the full query processing pipeline from SQL parsing to disk I/O,
covering every major layer found in production databases like PostgreSQL and SQLite.

## Architecture Diagram

```
                         ┌──────────────────────────────┐
  SQL text ─────────────>│  parser.py                    │  regex-based tokenizer + parser
                         │  "SELECT * FROM t WHERE ..."  │  produces command dicts (AST)
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │  minidb.py  (planner/engine)  │  cost-based: index seek vs
                         │  _execute_select()            │  sequential scan decision
                         └──────────────┬───────────────┘  EXPLAIN support
                                        ▼
                         ┌──────────────────────────────┐
                         │  executor.py                  │  Volcano pull model
                         │  SeqScan → Filter → Project  │  HashJoin, NestedLoopJoin
                         └──────────────┬───────────────┘
                                        ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                         engine layer                                 │
  │   WAL logging | Strict 2PL locking | crash recovery (ARIES)         │
  └───┬───────────────┬───────────────┬───────────────┬────────────────┘
      ▼               ▼               ▼               ▼
  btree.py        storage.py      buffer_pool.py   transaction.py
  B+ tree index   HeapFile +      LRU frame        WAL manager +
  (PK lookup)     SlottedPage     cache             lock manager
```

## Module Map

| File | Responsibility |
|------|----------------|
| `storage.py` | Slotted page format (4 KiB), HeapFile (paged data store), Record serialization, RID addressing |
| `buffer_pool.py` | LRU frame cache with pin counts, dirty flags, eviction policy |
| `btree.py` | In-memory B+ tree mapping primary key → RID, with split/merge support |
| `parser.py` | SQL tokenizer + parser: CREATE, INSERT, SELECT (with WHERE/JOIN/ORDER BY), UPDATE, DELETE, EXPLAIN |
| `executor.py` | Volcano pull operators: SeqScan, Filter, Projection, NestedLoopJoin, HashJoin |
| `transaction.py` | WAL (write-ahead log), Strict 2PL lock manager, ARIES-style recovery |
| `minidb.py` | Core engine: wires all layers, owns cost-based access path selection, EXPLAIN |
| `main.py` | Interactive REPL shell + script runner |

## Data Flow

1. **SQL text** enters through `main.py` (REPL) or piped script
2. **Parser** (`parser.py`) tokenizes and parses into a command dict
3. **Engine** (`minidb.py`) makes cost-based decisions (index vs scan)
4. **Executor** (`executor.py`) builds a Volcano operator pipeline
5. **Operators** read data through the **B+ tree** (`btree.py`) or **HeapFile** (`storage.py`)
6. **Buffer Pool** (`buffer_pool.py`) caches hot pages in memory with LRU eviction
7. **Transaction Manager** (`transaction.py`) logs all mutations to WAL before applying
