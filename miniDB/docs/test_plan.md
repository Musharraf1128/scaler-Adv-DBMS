# Test Plan

## Running Tests

```bash
cd miniDB
python3 tests/run_tests.py
```

## Test Categories

### 1. DDL + CRUD (Happy Path)
- CREATE TABLE with multiple columns
- INSERT records and verify RIDs
- SELECT * returns all rows
- SELECT with WHERE filter
- SELECT with ORDER BY
- UPDATE modifies correct rows
- DELETE removes correct rows

### 2. Index Operations
- B+ tree insert and search
- Index seek for primary key equality (O(log n))
- Sequential scan fallback for non-indexed columns

### 3. Query Execution Pipeline
- SeqScan operator returns all rows
- Filter operator applies WHERE correctly
- Projection operator selects columns
- Hash Join produces correct combined rows

### 4. EXPLAIN
- EXPLAIN SELECT shows IndexSeek for PK equality
- EXPLAIN SELECT shows SeqScan for non-PK filter

### 5. Transactions
- BEGIN / COMMIT flow
- WAL records are written for INSERT/UPDATE/DELETE
- ARIES recovery identifies committed vs active transactions

### 6. Error Handling
- SELECT from non-existent table
- INSERT with wrong number of values
- Invalid SQL syntax

## Test Output

Each test prints `PASS` or `FAIL` with a description.
A summary line at the end shows total pass/fail counts.
