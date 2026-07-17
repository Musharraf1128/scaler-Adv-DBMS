"""
miniDB — A minimal database engine built from scratch.

This is the MAIN ENGINE that ties all components together:
  Storage Engine → Buffer Pool → B+ Tree Index → Parser → Executor → Transactions

Architecture (for viva):
┌─────────────────────────────────────────────────┐
│                   SQL Query                      │
│              "SELECT * FROM ..."                 │
├─────────────────────────────────────────────────┤
│  Parser          → Tokenize + parse SQL          │
├─────────────────────────────────────────────────┤
│  Executor        → Volcano model operators       │
├─────────────────────────────────────────────────┤
│  B+ Tree Index   → O(log n) key lookups          │
├─────────────────────────────────────────────────┤
│  Buffer Pool     → Cache pages in RAM (LRU)      │
├─────────────────────────────────────────────────┤
│  Storage Engine  → Pages, HeapFile, disk I/O     │
├─────────────────────────────────────────────────┤
│  Transaction/WAL → ACID, recovery, locking       │
└─────────────────────────────────────────────────┘
"""

import os
import sys

from storage import Record, HeapFile
from buffer_pool import BufferPool
from btree import BPlusTree
from parser import parse
from executor import (
    SeqScanOperator, FilterOperator, ProjectionOperator,
    NestedLoopJoinOperator, execute_pipeline
)
from transaction import TransactionManager


class MiniDB:
    """
    The main database engine.
    
    Manages multiple tables, each backed by:
    - A HeapFile (data on disk)
    - A BufferPool (caching layer)
    - A B+ Tree index (on the first column, typically the primary key)
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Table metadata: table_name -> {"columns": [...], "heap": HeapFile, 
        #                                 "buffer": BufferPool, "index": BPlusTree}
        self.tables = {}

        # Transaction manager (shared across all tables)
        self.txn_manager = TransactionManager(os.path.join(data_dir, "wal.log"))

        # Current transaction (None if autocommit)
        self.current_txn = None

        # Load existing tables
        self._load_tables()

    def _load_tables(self):
        """Load table metadata from disk on startup."""
        meta_path = os.path.join(self.data_dir, "tables.meta")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) == 2:
                        table_name = parts[0]
                        columns = parts[1].split(",")
                        self._init_table(table_name, columns, create_file=False)

    def _save_meta(self):
        """Save table metadata to disk."""
        meta_path = os.path.join(self.data_dir, "tables.meta")
        with open(meta_path, "w") as f:
            for name, info in self.tables.items():
                f.write(f"{name}:{','.join(info['columns'])}\n")

    def _init_table(self, table_name: str, columns: list, create_file=True):
        """Initialize a table's components."""
        filepath = os.path.join(self.data_dir, f"{table_name}.db")
        
        if create_file and os.path.exists(filepath):
            raise Exception(f"Table '{table_name}' already exists!")

        heap = HeapFile(filepath)
        buffer_pool = BufferPool(heap, capacity=10)
        index = BPlusTree(order=4)

        self.tables[table_name] = {
            "columns": columns,
            "heap": heap,
            "buffer": buffer_pool,
            "index": index,
        }

        # Rebuild index from existing data
        if not create_file:
            for rid, record in heap.scan_all():
                pk_col = columns[0]  # index on first column
                pk_val = record.data.get(pk_col)
                if pk_val is not None:
                    index.insert(pk_val, rid)

    def execute(self, sql: str) -> str:
        """
        Execute a SQL statement and return the result as a string.
        This is the main entry point — it goes through the full pipeline:
        SQL → Parser → Executor → Storage
        """
        cmd = parse(sql)

        if cmd["type"] == "ERROR":
            return f"ERROR: {cmd['message']}"
        elif cmd["type"] == "CREATE":
            return self._execute_create(cmd)
        elif cmd["type"] == "INSERT":
            return self._execute_insert(cmd)
        elif cmd["type"] == "SELECT":
            return self._execute_select(cmd)
        elif cmd["type"] == "DELETE":
            return self._execute_delete(cmd)
        elif cmd["type"] == "UPDATE":
            return self._execute_update(cmd)
        else:
            return f"ERROR: Unsupported command type: {cmd['type']}"

    def _execute_create(self, cmd: dict) -> str:
        """CREATE TABLE"""
        table_name = cmd["table"]
        columns = cmd["columns"]
        self._init_table(table_name, columns)
        self._save_meta()
        return f"Table '{table_name}' created with columns: {columns}"

    def _execute_insert(self, cmd: dict) -> str:
        """INSERT INTO table VALUES (...)"""
        table_name = cmd["table"]
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"

        table = self.tables[table_name]
        columns = table["columns"]
        values = cmd["values"]

        if len(values) != len(columns):
            return f"ERROR: Expected {len(columns)} values, got {len(values)}"

        # Create record from column names + values
        data = dict(zip(columns, values))
        record = Record(data)

        # Log in WAL if in a transaction
        if self.current_txn:
            self.txn_manager.log_insert(self.current_txn, table_name, data)

        # Insert into heap file
        rid = table["heap"].insert_record(record)

        # Update B+ tree index (indexed on first column)
        pk_val = values[0]
        table["index"].insert(pk_val, rid)

        return f"Inserted: {data} → RID {rid}"

    def _execute_select(self, cmd: dict) -> str:
        """SELECT with Volcano model pipeline."""
        table_name = cmd["table"]
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"

        table = self.tables[table_name]
        where = cmd.get("where")

        # Decide: use INDEX SCAN or SEQ SCAN?
        use_index = False
        if where and where["column"] == table["columns"][0] and where["op"] == "=":
            use_index = True

        if use_index:
            # INDEX SCAN — O(log n) using B+ tree
            rid = table["index"].search(where["value"])
            if rid is None:
                records = []
            else:
                page = table["heap"].read_page(rid[0])
                rec = page.get(rid[1])
                records = [(rid, rec)] if rec else []
        else:
            # SEQ SCAN — O(n) read all records
            records = table["heap"].scan_all()

        # Build Volcano pipeline
        pipeline = SeqScanOperator(records)

        # Add Filter if WHERE clause (and not already handled by index)
        if where and not use_index:
            pipeline = FilterOperator(pipeline, where["column"], where["op"], where["value"])

        # Add Projection
        pipeline = ProjectionOperator(pipeline, cmd["columns"])

        # Execute pipeline
        results = execute_pipeline(pipeline)

        # Sort if ORDER BY
        if cmd.get("order_by"):
            order_col = cmd["order_by"]
            results.sort(key=lambda x: x[1].data.get(order_col, ""))

        # Format output
        if not results:
            return "(0 rows)"

        output_lines = []
        # Header
        if results:
            cols = list(results[0][1].data.keys())
            output_lines.append(" | ".join(str(c) for c in cols))
            output_lines.append("-" * len(output_lines[0]))

        for rid, record in results:
            output_lines.append(" | ".join(str(v) for v in record.data.values()))

        output_lines.append(f"({len(results)} row{'s' if len(results) != 1 else ''})")
        return "\n".join(output_lines)

    def _execute_delete(self, cmd: dict) -> str:
        """DELETE FROM table WHERE ..."""
        table_name = cmd["table"]
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"

        table = self.tables[table_name]
        where = cmd.get("where")

        records = table["heap"].scan_all()
        deleted = 0

        for rid, record in records:
            if where:
                col_val = record.data.get(where["column"])
                if not self._compare(col_val, where["op"], where["value"]):
                    continue

            # Log in WAL
            if self.current_txn:
                self.txn_manager.log_delete(self.current_txn, table_name, record.data)

            # Delete from heap
            table["heap"].delete_record(rid[0], rid[1])
            # Delete from index
            pk_val = record.data.get(table["columns"][0])
            table["index"].delete(pk_val)
            deleted += 1

        return f"Deleted {deleted} row{'s' if deleted != 1 else ''}"

    def _execute_update(self, cmd: dict) -> str:
        """UPDATE table SET col=val WHERE ..."""
        table_name = cmd["table"]
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"

        table = self.tables[table_name]
        where = cmd.get("where")
        set_data = cmd.get("set", {})

        records = table["heap"].scan_all()
        updated = 0

        for rid, record in records:
            if where:
                col_val = record.data.get(where["column"])
                if not self._compare(col_val, where["op"], where["value"]):
                    continue

            old_data = dict(record.data)
            new_data = dict(record.data)
            new_data.update(set_data)

            # Log in WAL
            if self.current_txn:
                self.txn_manager.log_update(self.current_txn, table_name, old_data, new_data)

            # Delete old record and insert new one
            table["heap"].delete_record(rid[0], rid[1])
            pk_val = old_data.get(table["columns"][0])
            table["index"].delete(pk_val)

            new_record = Record(new_data)
            new_rid = table["heap"].insert_record(new_record)
            new_pk = new_data.get(table["columns"][0])
            table["index"].insert(new_pk, new_rid)

            updated += 1

        return f"Updated {updated} row{'s' if updated != 1 else ''}"

    def _compare(self, a, op, b):
        """Helper for WHERE comparisons."""
        if a is None:
            return False
        if op == "=":  return a == b
        if op == "!=": return a != b
        if op == ">":  return a > b
        if op == "<":  return a < b
        if op == ">=": return a >= b
        if op == "<=": return a <= b
        return False

    # --- Transaction commands ---
    def begin_transaction(self) -> str:
        self.current_txn = self.txn_manager.begin()
        return f"Transaction {self.current_txn} started"

    def commit_transaction(self) -> str:
        if self.current_txn is None:
            return "No active transaction"
        txn_id = self.current_txn
        self.txn_manager.commit(txn_id)
        self.current_txn = None
        return f"Transaction {txn_id} committed"

    def abort_transaction(self) -> str:
        if self.current_txn is None:
            return "No active transaction"
        txn_id = self.current_txn
        self.txn_manager.abort(txn_id)
        self.current_txn = None
        return f"Transaction {txn_id} aborted (rolled back)"

    def show_index(self, table_name: str) -> str:
        """Show the B+ tree index for a table."""
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            self.tables[table_name]["index"].print_tree()
        return f.getvalue()

    def show_buffer_stats(self, table_name: str) -> str:
        """Show buffer pool statistics."""
        if table_name not in self.tables:
            return f"ERROR: Table '{table_name}' does not exist"
        stats = self.tables[table_name]["buffer"].get_stats()
        lines = [f"  {k}: {v}" for k, v in stats.items()]
        return "Buffer Pool Stats:\n" + "\n".join(lines)

    def show_wal(self) -> str:
        """Show the WAL contents."""
        records = self.txn_manager.wal.read_log()
        if not records:
            return "WAL is empty"
        lines = []
        for r in records:
            lines.append(f"  TXN-{r['txn_id']} {r['op_type']:8s} {r['table']}"
                         f"{' before=' + str(r['before']) if r['before'] else ''}"
                         f"{' after=' + str(r['after']) if r['after'] else ''}")
        return "WAL Contents:\n" + "\n".join(lines)
