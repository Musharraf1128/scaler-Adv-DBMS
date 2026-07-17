# MiniDB

A small but genuinely working relational database engine, built from the ground
up in Python. It runs SQL over a page-based storage engine with a B+ tree
index, a cost-based planner, Strict 2PL concurrency, and write-ahead-logging
crash recovery.

- **Language:** Python 3, no third-party libraries.
- **Status:** All core features implemented and tested end-to-end; 31 assertions pass.
- **Concurrency:** Strict 2PL with table-level locking and WAL for durability.

---

## 1. Project Overview

**Problem.** Modern databases hide an enormous amount of machinery — paging,
indexing, planning, concurrency, recovery — behind a single `SELECT`. The goal
of this project is to make that machinery concrete by building a relational
engine where every layer is small enough to read in full and explain.

**Goals.**
- Execute real SQL (`CREATE`, `INSERT`, `SELECT` with `WHERE`/`JOIN`/`ORDER BY`,
  `UPDATE`, `DELETE`, `BEGIN`/`COMMIT`/`ROLLBACK`, `EXPLAIN`) end to end.
- Store rows durably in paged heap files behind a buffer pool, indexed by a B+ tree.
- Let a cost-based planner choose between an index seek and a full scan.
- Run transactions under **Strict 2PL** and survive a process crash without
  losing committed data via WAL + ARIES recovery.

---

## 2. System Architecture

```
                         ┌──────────────────────────────┐
  SQL text ─────────────>│  parser.py                    │  regex tokenizer → command dict
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │  minidb.py  (engine/planner)  │  cost-based: index seek vs
                         │  _execute_select()            │  seq scan, EXPLAIN support
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │  executor.py                  │  Volcano pull operators:
                         │  SeqScan → Filter → Project  │  SeqScan, Filter, Project,
                         └──────────────┬───────────────┘  HashJoin, NestedLoopJoin
                                        ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                           engine core                                │
  │   Strict 2PL locking | WAL hooks | ARIES crash recovery             │
  └───┬───────────────┬───────────────┬───────────────┬────────────────┘
      ▼               ▼               ▼               ▼
  btree.py        storage.py      buffer_pool.py   transaction.py
  B+ tree         HeapFile +      LRU frame        WAL + lock
  (PK index)      SlottedPage     cache             manager
```

**Module map.**

| File | Responsibility |
|------|----------------|
| `storage.py` | Slotted page format (4 KiB), HeapFile, Record (de)serialization, RID |
| `buffer_pool.py` | LRU frame cache, pin counts, dirty flags, eviction |
| `btree.py` | In-memory B+ tree mapping primary key → RID, splits, range scan |
| `parser.py` | SQL tokenizer + parser (CREATE, INSERT, SELECT, UPDATE, DELETE, EXPLAIN) |
| `executor.py` | Volcano pull operators: SeqScan, Filter, Projection, NestedLoopJoin |
| `transaction.py` | WAL (write-ahead log), Strict 2PL lock manager, ARIES recovery |
| `minidb.py` | Core engine wiring all layers, cost-based planner, HashJoin |
| `main.py` | Interactive REPL / script runner |

---

## 3. Storage Layer

**Page format — slotted pages (4 KiB).** Each page has a header
(`num_records`, `free_space_ptr`), a slot directory that grows forward, and
record bodies that grow backward. A record's address is `RID = (page, slot)` and
never changes when neighbors are added. Deleting flips a slot to a tombstone.

**Heap files.** A table is a sequence of pages in a `.db` file. Inserts
append to the last page with room, or grow a new page. Free space management
scans pages for available slots.

**Buffer pool — LRU.** A fixed set of frames (default 10) caches pages.
When full, the least recently used unpinned frame is evicted. Dirty frames
are written back on eviction.

---

## 4. Indexing

**B+ tree.** The primary key index maps a column value to the RID of that row.
Fan-out = 4 (configurable). Internal nodes hold separator keys and child
pointers; leaf nodes hold `(key → RID)` pairs plus a `next` pointer chaining
leaves for range scans. Inserts split full nodes and push separators up.

---

## 5. Query Execution

**Parser.** A regex-based parser turns SQL into command dicts (equivalent to AST nodes).

**Plan generation.** The engine chooses an access path:
- **IndexSeek** if the WHERE clause is an equality on the primary key
- **SeqScan** otherwise

`EXPLAIN` shows the chosen plan without executing.

**Operators — Volcano pull model.** Every operator implements `open()`, `next()`, `close()`:
- `SeqScan` — reads all visible rows
- `Filter` — keeps rows satisfying WHERE predicates
- `Projection` — narrows to selected columns
- `HashJoin` — build-probe equi-join
- `NestedLoopJoin` — brute-force O(n×m) join

---

## 6. Transactions & Recovery

**ACID.** Atomicity via WAL undo, Consistency via constraint checks,
Isolation via Strict 2PL, Durability via WAL flush-before-commit.

**WAL.** Every mutation appends a log record (JSON Lines) with before/after
values before touching the heap. On commit, a COMMIT record is appended.

**ARIES recovery.** Three phases: Analysis (identify active transactions),
Redo (replay committed ops), Undo (rollback uncommitted ops).

---

## 7. Quick Start

```bash
cd miniDB
python3 main.py          # interactive REPL
python3 main.py < examples/demo.sql  # run demo script
python3 tests/run_tests.py           # run test suite (31 assertions)
```

### Interactive Usage

```sql
CREATE TABLE users (id, name, age)
INSERT INTO users VALUES (1, 'alice', 30)
INSERT INTO users VALUES (2, 'bob', 25)

SELECT * FROM users WHERE age > 28
EXPLAIN SELECT * FROM users WHERE id = 2
SELECT * FROM users ORDER BY age

BEGIN
UPDATE users SET age = 26 WHERE id = 2
COMMIT
```

### Special Commands

```
.demo           Guided walkthrough of all components
.tables         List all tables
.index <table>  Show B+ tree structure
.buffer <table> Show buffer pool stats
.wal            Show WAL contents
.help           Help
.quit           Exit
```

---

## 8. Project Structure

```
miniDB/
├── storage.py          # Storage engine: Page, Record, HeapFile
├── buffer_pool.py      # Buffer pool with LRU eviction
├── btree.py            # B+ tree index
├── parser.py           # SQL parser (lexer + parser)
├── executor.py         # Volcano model query operators
├── transaction.py      # WAL, 2PL lock manager, ARIES recovery
├── minidb.py           # Main engine (ties everything together)
├── main.py             # Interactive CLI shell
├── README.md           # This file
├── docs/
│   ├── architecture.md
│   ├── design_decisions.md
│   └── test_plan.md
├── examples/
│   └── demo.sql        # Runnable demo script
└── tests/
    └── run_tests.py    # 31-assertion test suite
```
