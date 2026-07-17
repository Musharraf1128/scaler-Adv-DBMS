#!/usr/bin/env python3
"""
miniDB end-to-end test suite.
Run: python3 tests/run_tests.py (from the miniDB directory)
"""

import sys
import os
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minidb import MiniDB

PASS = 0
FAIL = 0
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")


def check(label, condition):
    global PASS, FAIL
    if condition:
        print(f"  ok:   {label}")
        PASS += 1
    else:
        print(f"  FAIL: {label}")
        FAIL += 1


def fresh_db():
    """Create a fresh database for each test group."""
    if os.path.exists(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    return MiniDB(DATA_DIR)


# ============================================================
print("=== DDL + CRUD ===")
db = fresh_db()
out = db.execute("CREATE TABLE u (id, name, age)")
check("CREATE TABLE", "created" in out.lower())

db.execute("INSERT INTO u VALUES (1, 'alice', 30)")
db.execute("INSERT INTO u VALUES (2, 'bob', 25)")
db.execute("INSERT INTO u VALUES (3, 'carol', 41)")

out = db.execute("SELECT * FROM u")
check("SELECT * returns 3 rows", "(3 rows)" in out)
check("row present: alice", "alice" in out)
check("row present: bob", "bob" in out)

# ============================================================
print("=== WHERE filter ===")
out = db.execute("SELECT * FROM u WHERE age > 28")
check("filter keeps alice (30)", "alice" in out)
check("filter keeps carol (41)", "carol" in out)
check("filter removes bob (25)", "bob" not in out)
check("filter returns 2 rows", "(2 rows)" in out)

# ============================================================
print("=== ORDER BY ===")
out = db.execute("SELECT name, age FROM u ORDER BY age")
lines = out.strip().split("\n")
data_lines = [l for l in lines if "|" in l and "name" not in l and "-" not in l]
check("ORDER BY: bob first (25)", "bob" in data_lines[0])
check("ORDER BY: carol last (41)", "carol" in data_lines[-1])

# ============================================================
print("=== Index seek (PK equality) ===")
out = db.execute("SELECT * FROM u WHERE id = 2")
check("index seek finds bob", "bob" in out)
check("index seek returns 1 row", "(1 row)" in out)

# ============================================================
print("=== EXPLAIN ===")
out = db.execute("EXPLAIN SELECT * FROM u WHERE id = 2")
check("EXPLAIN shows IndexSeek", "IndexSeek" in out or "Index" in out)

out = db.execute("EXPLAIN SELECT * FROM u WHERE age > 28")
check("EXPLAIN shows SeqScan", "SeqScan" in out or "Scan" in out)

# ============================================================
print("=== UPDATE ===")
out = db.execute("UPDATE u SET age = 26 WHERE id = 2")
check("UPDATE reports 1 row", "1 row" in out)

out = db.execute("SELECT * FROM u WHERE id = 2")
check("UPDATE applied: age=26", "26" in out)

# ============================================================
print("=== DELETE ===")
out = db.execute("DELETE FROM u WHERE id = 3")
check("DELETE reports 1 row", "1 row" in out)

out = db.execute("SELECT * FROM u")
check("DELETE removed carol", "carol" not in out)
check("after DELETE: 2 rows", "(2 rows)" in out)

# ============================================================
print("=== JOIN (Hash Join) ===")
db.execute("CREATE TABLE orders (oid, uid, item)")
db.execute("INSERT INTO orders VALUES (100, 1, 'keyboard')")
db.execute("INSERT INTO orders VALUES (101, 2, 'monitor')")

out = db.execute("SELECT * FROM u JOIN orders ON u.id = orders.uid")
check("JOIN produces results", "keyboard" in out)
check("JOIN matches uid", "alice" in out or "1" in out)

# ============================================================
print("=== Transactions ===")
out = db.begin_transaction()
check("BEGIN transaction", "started" in out.lower() or "Transaction" in out)

db.execute("INSERT INTO u VALUES (4, 'dave', 35)")

out = db.commit_transaction()
check("COMMIT transaction", "committed" in out.lower() or "Transaction" in out)

out = db.execute("SELECT * FROM u")
check("committed row present: dave", "dave" in out)

# ============================================================
print("=== WAL ===")
wal_out = db.show_wal()
check("WAL has BEGIN record", "BEGIN" in wal_out)
check("WAL has COMMIT record", "COMMIT" in wal_out)
check("WAL has INSERT record", "INSERT" in wal_out)

# ============================================================
print("=== Recovery ===")
recovery = db.txn_manager.recover()
check("recovery finds committed txns", len(recovery["committed_txns"]) > 0)

# ============================================================
print("=== Error handling ===")
out = db.execute("SELECT * FROM nonexistent")
check("error on missing table", "ERROR" in out)

out = db.execute("INSERT INTO u VALUES (1, 2)")
check("error on wrong column count", "ERROR" in out)

out = db.execute("BLAH BLAH")
check("error on invalid SQL", "ERROR" in out or "Unknown" in out)

# ============================================================
# Cleanup
shutil.rmtree(DATA_DIR, ignore_errors=True)

print(f"\n{'='*40}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL == 0:
    print("All tests passed! ✓")
else:
    print(f"{FAIL} test(s) FAILED")
    sys.exit(1)
