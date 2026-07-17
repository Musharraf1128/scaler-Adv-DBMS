# Design Decisions

## Language: Python

We chose Python over C/C++ for rapid prototyping and readability. The entire
engine fits in ~1500 lines of well-commented code. Every data structure is
visible and debuggable without a build step. The trade-off is performance —
a C++ implementation would be 10-100x faster — but for a teaching project
the clarity advantage is decisive.

## Storage: Slotted Pages (4 KiB)

**Why slotted pages?** Records have variable length (`TEXT` columns vary in size).
A slotted page uses a slot directory at the top pointing to record bodies packed
from the bottom, with free space in the middle. This gives us:
- Stable RIDs: a record's `(page_id, slot_id)` never changes when neighbors are added
- Efficient deletion: flipping a slot to a tombstone without moving bytes
- Variable-length record support without fragmentation

**Why 4 KiB?** Matches the common OS page size and filesystem block size.
PostgreSQL uses 8 KiB, SQLite uses 4 KiB. Smaller pages waste less space
on partially-filled pages; larger pages reduce tree height.

## Index: B+ Tree over Hash Index

**Why B+ tree?** It keeps keys ordered, supporting both equality (`id = 7`) and
range (`id > 100`) predicates. All data pointers live in linked leaf nodes, so
range scans are a straight walk. A hash index gives O(1) equality lookups but
cannot serve range queries, ORDER BY, or prefix matching.

**In-memory index.** The B+ tree is rebuilt from the heap file on startup.
This avoids maintaining a second on-disk format and keeps the heap as the single
source of truth. The trade-off is startup cost — acceptable for small datasets.

## Buffer Pool: LRU over Clock-Sweep

**Why LRU?** Simpler to implement and reason about. Python's `OrderedDict` gives
us LRU semantics for free — `move_to_end()` on access, evict from the front.

**Why not clock-sweep?** Clock-sweep (used by PostgreSQL) gives near-LRU quality
at O(1) per access without a linked list, and better resists sequential flooding.
For a teaching project, LRU is clearer. We document the LRU-K and clock-sweep
alternatives in the study guide.

## Query Execution: Volcano Model

**Why Volcano/Iterator?** Every operator implements `open()`, `next()`, `close()`.
Operators compose uniformly into pipelines. This is the same model used by
PostgreSQL. It's memory-efficient (one tuple at a time) and conceptually clean.

**Operators implemented:**
- `SeqScan` — full table scan
- `Filter` — WHERE predicate evaluation
- `Projection` — column selection
- `NestedLoopJoin` — O(n×m) brute force join
- `HashJoin` — O(n+m) build-probe join (in `minidb.py`)

## Parser: Regex over Formal Grammar

**Why regex?** A hand-written regex parser is ~200 lines and covers all the SQL
we need (CREATE, INSERT, SELECT with WHERE/JOIN/ORDER BY, UPDATE, DELETE, EXPLAIN).
A formal grammar (yacc/bison) adds complexity without teaching benefit for this scope.

The reference C++ MiniDB uses a recursive-descent parser, which is the natural
next step up from regex. Both produce structured command representations (AST).

## Concurrency: Strict 2PL

**Why Strict 2PL?** It's the simplest correct concurrency control scheme.
All locks are held until commit/abort, preventing cascading rollbacks and
guaranteeing serializability. We use table-level locking for simplicity;
real databases use row-level locking for better concurrency.

**MVCC alternative.** The reference C++ MiniDB implements MVCC (multi-version
concurrency control) where readers work off consistent snapshots and never block
writers. We document MVCC in the study guide but implement Strict 2PL for clarity.

## Durability: WAL (Write-Ahead Logging)

**Why WAL?** The fundamental rule: write the log record before writing the data page.
If the system crashes, the log is the source of truth for recovery. Our WAL stores
JSON Lines (one record per line) with before/after values for undo/redo.

**Recovery: ARIES.** Three phases: Analysis (find active transactions), Redo
(replay committed operations), Undo (rollback uncommitted operations). This is
the gold standard used by most production databases.
