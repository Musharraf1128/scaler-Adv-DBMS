"""
Transaction Manager with WAL (Write-Ahead Logging).

WHAT THIS DOES (for viva):
- Transactions ensure ACID properties:
  A = Atomicity: All or nothing. If a transaction fails, ALL its changes are rolled back.
  C = Consistency: DB stays in a valid state.
  I = Isolation: Concurrent transactions don't interfere with each other.
  D = Durability: Once committed, changes survive crashes.

- WAL (Write-Ahead Log): Before modifying data, write the change to a LOG file first.
  If the system crashes, we can replay the log to recover.

- 2PL (Two-Phase Locking): 
  Growing phase: acquire locks, never release.
  Shrinking phase: release locks, never acquire.
  This ensures serializability (transactions appear to run one at a time).

KEY CONCEPTS:
- WAL: Write the log BEFORE writing data. "Write-Ahead" = log first, data second.
- Log Record: (txn_id, operation, table, before_value, after_value)
- ARIES Recovery: Analysis → Redo → Undo (we implement a simplified version)
- Strict 2PL: Hold ALL locks until commit/abort. Prevents cascading rollbacks.

VIVA TIP: "WAL ensures durability — even if the system crashes mid-transaction,
we can recover by replaying the log. ARIES is the gold standard recovery 
algorithm used by most real databases."
"""

import json
import os
import time
from threading import Lock


class WALManager:
    """
    Write-Ahead Log manager.
    
    Every modification is logged BEFORE it's applied to data.
    Log format: JSON lines file — one log record per line.
    
    VIVA TIP: "The WAL is append-only and sequential, which is very fast 
    on disk. We flush the log before acknowledging a commit to ensure 
    durability."
    """

    def __init__(self, log_path: str):
        self.log_path = log_path
        self.lock = Lock()

    def write_log(self, txn_id: int, op_type: str, table: str,
                  before: dict = None, after: dict = None):
        """
        Write a log record.
        
        Log record format (simplified ARIES):
        - txn_id: Which transaction
        - op_type: BEGIN, INSERT, UPDATE, DELETE, COMMIT, ABORT
        - table: Which table
        - before: Old value (for UNDO)
        - after: New value (for REDO)
        """
        record = {
            "txn_id": txn_id,
            "op_type": op_type,
            "table": table,
            "before": before,
            "after": after,
            "timestamp": time.time(),
        }
        with self.lock:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record) + "\n")

    def read_log(self) -> list:
        """Read all log records (for recovery)."""
        records = []
        if os.path.exists(self.log_path):
            with open(self.log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        return records

    def clear_log(self):
        """Clear the log (after checkpoint)."""
        with open(self.log_path, "w") as f:
            pass


class LockManager:
    """
    Simple lock manager implementing Strict 2PL.
    
    - Each transaction acquires locks on tables it accesses.
    - Locks are held until COMMIT or ABORT (Strict 2PL).
    - Simple table-level locking (not row-level, for simplicity).
    
    VIVA TIP: "Strict 2PL holds all locks until the transaction ends.
    This prevents dirty reads and ensures serializability, but can 
    cause deadlocks. Real databases use deadlock detection (wait-for graphs)
    or timeouts."
    """

    def __init__(self):
        self.locks = {}  # table_name -> txn_id that holds the lock
        self.lock = Lock()

    def acquire(self, txn_id: int, table: str) -> bool:
        """Try to acquire a lock on a table for a transaction."""
        with self.lock:
            if table not in self.locks or self.locks[table] == txn_id:
                self.locks[table] = txn_id
                return True
            return False  # Lock held by another transaction

    def release_all(self, txn_id: int):
        """Release all locks held by a transaction (on commit/abort)."""
        with self.lock:
            tables_to_release = [t for t, tid in self.locks.items() if tid == txn_id]
            for t in tables_to_release:
                del self.locks[t]


class TransactionManager:
    """
    Manages transactions with ACID guarantees.
    
    Usage:
        txn_id = tm.begin()
        tm.log_insert(txn_id, "students", {"id": 1, "name": "Alice"})
        tm.commit(txn_id)
        # or tm.abort(txn_id) to rollback
    """

    def __init__(self, wal_path: str):
        self.wal = WALManager(wal_path)
        self.lock_manager = LockManager()
        self.next_txn_id = 1
        self.active_txns = set()  # currently running transactions

    def begin(self) -> int:
        """Start a new transaction. Returns transaction ID."""
        txn_id = self.next_txn_id
        self.next_txn_id += 1
        self.active_txns.add(txn_id)
        self.wal.write_log(txn_id, "BEGIN", "")
        return txn_id

    def log_insert(self, txn_id: int, table: str, record_data: dict):
        """Log an INSERT operation."""
        if not self.lock_manager.acquire(txn_id, table):
            raise Exception(f"Transaction {txn_id} could not acquire lock on {table}")
        self.wal.write_log(txn_id, "INSERT", table, after=record_data)

    def log_update(self, txn_id: int, table: str, before: dict, after: dict):
        """Log an UPDATE operation (stores both old and new values for undo/redo)."""
        if not self.lock_manager.acquire(txn_id, table):
            raise Exception(f"Transaction {txn_id} could not acquire lock on {table}")
        self.wal.write_log(txn_id, "UPDATE", table, before=before, after=after)

    def log_delete(self, txn_id: int, table: str, record_data: dict):
        """Log a DELETE operation."""
        if not self.lock_manager.acquire(txn_id, table):
            raise Exception(f"Transaction {txn_id} could not acquire lock on {table}")
        self.wal.write_log(txn_id, "DELETE", table, before=record_data)

    def commit(self, txn_id: int):
        """
        Commit a transaction.
        1. Write COMMIT record to WAL.
        2. Release all locks.
        
        VIVA TIP: "Once the COMMIT record is written to the WAL and flushed 
        to disk, the transaction is durable — even if the system crashes 
        right after, recovery will redo the committed changes."
        """
        self.wal.write_log(txn_id, "COMMIT", "")
        self.lock_manager.release_all(txn_id)
        self.active_txns.discard(txn_id)

    def abort(self, txn_id: int):
        """
        Abort/rollback a transaction.
        1. Write ABORT record to WAL.
        2. Release all locks.
        The actual undo would use the 'before' values from the log.
        """
        self.wal.write_log(txn_id, "ABORT", "")
        self.lock_manager.release_all(txn_id)
        self.active_txns.discard(txn_id)

    def recover(self) -> dict:
        """
        Simplified ARIES-style recovery.
        
        ARIES has 3 phases:
        1. ANALYSIS: Scan log to find active transactions at crash time.
        2. REDO: Replay ALL logged operations to restore state.
        3. UNDO: Rollback any transactions that didn't commit.
        
        Returns a summary of recovery actions.
        """
        log_records = self.wal.read_log()
        committed = set()
        aborted = set()
        active = set()

        # Phase 1: ANALYSIS — figure out which txns committed
        for record in log_records:
            txn_id = record["txn_id"]
            if record["op_type"] == "BEGIN":
                active.add(txn_id)
            elif record["op_type"] == "COMMIT":
                committed.add(txn_id)
                active.discard(txn_id)
            elif record["op_type"] == "ABORT":
                aborted.add(txn_id)
                active.discard(txn_id)

        # Phase 2: REDO — replay committed transactions (in a real DB, 
        # we'd reapply the changes to the actual data pages)
        redo_ops = [r for r in log_records 
                    if r["txn_id"] in committed and r["op_type"] in ("INSERT", "UPDATE", "DELETE")]

        # Phase 3: UNDO — rollback active (uncommitted) transactions
        undo_ops = [r for r in reversed(log_records) 
                    if r["txn_id"] in active and r["op_type"] in ("INSERT", "UPDATE", "DELETE")]

        return {
            "committed_txns": list(committed),
            "aborted_txns": list(aborted),
            "active_txns_to_undo": list(active),
            "redo_operations": len(redo_ops),
            "undo_operations": len(undo_ops),
        }
