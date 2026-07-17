# miniDB — A Minimal Database Engine from Scratch

A simple relational database engine built from scratch in Python, demonstrating core DBMS concepts.

## 📦 Components

| Module | File | Concepts Covered |
|--------|------|------------------|
| Storage Engine | `storage.py` | Pages, slotted-page layout, HeapFile, Record encoding, RIDs |
| Buffer Pool | `buffer_pool.py` | Page caching, LRU eviction, pin counts, dirty flags |
| B+ Tree Index | `btree.py` | B+ tree search, insert, split, range queries, leaf linking |
| SQL Parser | `parser.py` | Lexing, tokenization, AST/command generation |
| Query Executor | `executor.py` | Volcano/Iterator model, SeqScan, Filter, Projection, Nested Loop Join |
| Transactions | `transaction.py` | ACID, WAL (Write-Ahead Logging), Strict 2PL, ARIES recovery |
| Main Engine | `minidb.py` | Full query processing pipeline, index vs. sequential scan |
| CLI Shell | `main.py` | Interactive SQL shell with demo mode |

## 🚀 Quick Start

```bash
# No dependencies needed — pure Python 3
cd miniDB
python main.py
```

## 💻 Usage

```sql
-- Create a table
CREATE TABLE students (id, name, grade)

-- Insert records
INSERT INTO students VALUES (1, 'Alice', 92)
INSERT INTO students VALUES (2, 'Bob', 85)

-- Query with WHERE and ORDER BY
SELECT * FROM students WHERE grade > 80 ORDER BY name

-- Update and Delete
UPDATE students SET grade = 95 WHERE id = 1
DELETE FROM students WHERE id = 2

-- Transactions
BEGIN
INSERT INTO students VALUES (3, 'Charlie', 78)
COMMIT
```

### Special Commands
```
.demo           Run a guided walkthrough of all components
.tables         List all tables
.index <table>  Show B+ tree index structure
.buffer <table> Show buffer pool hit/miss statistics
.wal            Show write-ahead log contents
.help           Show help
.quit           Exit
```

## 🏗️ Architecture

```
SQL Query: "SELECT * FROM students WHERE grade > 80"
    │
    ▼
┌─────────────┐
│   Parser     │ → Tokenize SQL into structured command
└─────┬───────┘
      ▼
┌─────────────┐
│  Executor    │ → Build Volcano pipeline: SeqScan → Filter → Projection
└─────┬───────┘
      ▼
┌─────────────┐
│  B+ Tree    │ → O(log n) index lookup (if applicable)
└─────┬───────┘
      ▼
┌─────────────┐
│ Buffer Pool │ → Check page cache, LRU eviction if full
└─────┬───────┘
      ▼
┌─────────────┐
│  Storage    │ → Read/write 4KB pages from heap file on disk
└─────┬───────┘
      ▼
┌─────────────┐
│ WAL / TXN   │ → Log changes for crash recovery (ARIES)
└─────────────┘
```

## 📚 Course Topics Mapped

- **DBMS Architecture**: Full pipeline in `minidb.py`
- **Storage Engine**: `storage.py` — pages, slotted layout, heap file
- **Buffer Pool**: `buffer_pool.py` — LRU cache with pin counts
- **Index Structures**: `btree.py` — B+ tree with splits and range scans
- **Query Parsing**: `parser.py` — SQL lexing and parsing
- **Query Execution**: `executor.py` — Volcano model operators
- **Transactions**: `transaction.py` — ACID, 2PL, WAL, ARIES recovery
