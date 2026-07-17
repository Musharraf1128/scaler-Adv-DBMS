#!/usr/bin/env python3
"""
miniDB — Interactive CLI Shell

Usage:
    python main.py

Type SQL commands or special commands:
    SQL:    CREATE TABLE, INSERT INTO, SELECT, UPDATE, DELETE
    BEGIN   — Start a transaction
    COMMIT  — Commit current transaction
    ROLLBACK — Abort current transaction
    .index <table>  — Show B+ tree index
    .buffer <table> — Show buffer pool stats
    .wal            — Show write-ahead log
    .tables         — List all tables
    .demo           — Run a demo with sample data
    .help           — Show this help
    .quit           — Exit
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minidb import MiniDB


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║              miniDB v1.0                     ║
║   A minimal database engine from scratch     ║
║──────────────────────────────────────────────║
║  Covers: Storage Engine, Buffer Pool,        ║
║  B+ Tree Index, SQL Parser, Volcano          ║
║  Executor, Transactions & WAL Recovery       ║
╚══════════════════════════════════════════════╝
Type .help for commands, .demo for a walkthrough
""")


def run_demo(db: MiniDB):
    """Run a guided demo that showcases all components."""
    print("\n" + "=" * 50)
    print("       📚 miniDB DEMO WALKTHROUGH")
    print("=" * 50)

    steps = [
        ("1️⃣  CREATE TABLE — Define schema",
         "CREATE TABLE students (id, name, grade)"),
        ("2️⃣  INSERT — Add records to heap file",
         "INSERT INTO students VALUES (1, 'Alice', 92)"),
        ("   More inserts...",
         "INSERT INTO students VALUES (2, 'Bob', 85)"),
        ("", "INSERT INTO students VALUES (3, 'Charlie', 78)"),
        ("", "INSERT INTO students VALUES (4, 'Diana', 95)"),
        ("", "INSERT INTO students VALUES (5, 'Eve', 88)"),
        ("", "INSERT INTO students VALUES (6, 'Frank', 72)"),
        ("", "INSERT INTO students VALUES (7, 'Grace', 91)"),
        ("", "INSERT INTO students VALUES (8, 'Hank', 67)"),
        ("3️⃣  SELECT * — Full table scan (SeqScan operator)",
         "SELECT * FROM students"),
        ("4️⃣  SELECT with WHERE — Filter operator in pipeline",
         "SELECT * FROM students WHERE grade > 85"),
        ("5️⃣  SELECT with ORDER BY — Sort operator",
         "SELECT name, grade FROM students ORDER BY grade"),
        ("6️⃣  INDEX LOOKUP — Uses B+ tree instead of SeqScan",
         "SELECT * FROM students WHERE id = 3"),
        ("7️⃣  UPDATE — Modify a record",
         "UPDATE students SET grade = 99 WHERE id = 1"),
        ("8️⃣  DELETE — Remove a record (tombstone in page)",
         "DELETE FROM students WHERE id = 8"),
        ("9️⃣  Verify changes",
         "SELECT * FROM students"),
    ]

    for label, sql in steps:
        if label:
            print(f"\n{'─' * 50}")
            print(f"  {label}")
        print(f"  miniDB> {sql}")
        result = db.execute(sql)
        print(f"  {result}")

    # Show internal structures
    print(f"\n{'─' * 50}")
    print("  🔟 B+ TREE INDEX (on 'id' column):")
    print(f"  {db.show_index('students')}")

    print(f"{'─' * 50}")
    print("  1️⃣1️⃣ BUFFER POOL STATS:")
    print(f"  {db.show_buffer_stats('students')}")

    # Demo transactions
    print(f"\n{'─' * 50}")
    print("  1️⃣2️⃣ TRANSACTION DEMO (ACID + WAL):")

    print(f"  miniDB> BEGIN")
    print(f"  {db.begin_transaction()}")

    sql = "INSERT INTO students VALUES (9, 'Ivy', 83)"
    print(f"  miniDB> {sql}")
    print(f"  {db.execute(sql)}")

    print(f"  miniDB> COMMIT")
    print(f"  {db.commit_transaction()}")

    print(f"\n{'─' * 50}")
    print("  1️⃣3️⃣ WAL (Write-Ahead Log) CONTENTS:")
    print(f"  {db.show_wal()}")

    print(f"\n{'─' * 50}")
    print("  1️⃣4️⃣ RECOVERY DEMO (ARIES-style):")
    recovery = db.txn_manager.recover()
    for k, v in recovery.items():
        print(f"    {k}: {v}")

    print(f"\n{'=' * 50}")
    print("  ✅ Demo complete! All components demonstrated.")
    print(f"{'=' * 50}\n")


def show_help():
    print("""
Commands:
  SQL Statements:
    CREATE TABLE <name> (<col1>, <col2>, ...)
    INSERT INTO <name> VALUES (<val1>, <val2>, ...)
    SELECT <cols> FROM <name> [WHERE <col> <op> <val>] [ORDER BY <col>]
    UPDATE <name> SET <col> = <val> WHERE <col> <op> <val>
    DELETE FROM <name> WHERE <col> <op> <val>

  Transactions:
    BEGIN      — Start a transaction
    COMMIT     — Commit current transaction
    ROLLBACK   — Abort / rollback current transaction

  Internal Inspection:
    .index <table>   — Show B+ tree index structure
    .buffer <table>  — Show buffer pool hit/miss stats
    .wal             — Show write-ahead log contents
    .tables          — List all tables
    .demo            — Run a full demo with sample data

  Other:
    .help    — Show this help
    .quit    — Exit miniDB
""")


def main():
    # Use a data directory inside miniDB folder
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    db = MiniDB(data_dir)

    print_banner()

    while True:
        try:
            # Show transaction indicator in prompt
            txn_indicator = f" [TXN-{db.current_txn}]" if db.current_txn else ""
            sql = input(f"miniDB{txn_indicator}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not sql:
            continue

        # Special commands
        if sql.lower() in (".quit", ".exit", "quit", "exit"):
            print("Bye!")
            break
        elif sql.lower() == ".help":
            show_help()
        elif sql.lower() == ".demo":
            run_demo(db)
        elif sql.lower() == ".tables":
            if db.tables:
                for name, info in db.tables.items():
                    print(f"  {name}: columns={info['columns']}")
            else:
                print("  No tables")
        elif sql.lower().startswith(".index"):
            parts = sql.split()
            if len(parts) >= 2:
                print(db.show_index(parts[1]))
            else:
                print("Usage: .index <table_name>")
        elif sql.lower().startswith(".buffer"):
            parts = sql.split()
            if len(parts) >= 2:
                print(db.show_buffer_stats(parts[1]))
            else:
                print("Usage: .buffer <table_name>")
        elif sql.lower() == ".wal":
            print(db.show_wal())
        elif sql.upper() == "BEGIN":
            print(db.begin_transaction())
        elif sql.upper() == "COMMIT":
            print(db.commit_transaction())
        elif sql.upper() in ("ROLLBACK", "ABORT"):
            print(db.abort_transaction())
        else:
            # Regular SQL
            result = db.execute(sql)
            print(result)


if __name__ == "__main__":
    main()
