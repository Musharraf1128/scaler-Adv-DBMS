"""
Query Executor — Runs parsed queries using the Volcano/Iterator model.

WHAT THIS DOES (for viva):
- Takes the parsed command (from parser.py) and executes it.
- Uses the VOLCANO MODEL (also called Iterator model):
  Each operator is a "pull-based" iterator with open(), next(), close().
  Operators form a PIPELINE: SeqScan -> Filter -> Projection -> Output

KEY CONCEPTS:
- Volcano/Iterator Model: Each operator implements next() which pulls one tuple at a time.
- SeqScan: Reads all tuples from a table (full table scan).
- Filter: Passes through only tuples matching a WHERE condition.
- Projection: Selects only certain columns (SELECT col1, col2).
- Nested Loop Join: For each row in table A, scan ALL rows in table B looking for matches.
- Sort: External sort for ORDER BY (we use Python's sort for simplicity).

VIVA TIP: "The Volcano model processes one tuple at a time through a pipeline 
of operators. This is memory-efficient because we don't need to materialize 
the entire result set at once. PostgreSQL uses this model."
"""


class SeqScanOperator:
    """
    Sequential Scan — reads ALL records from a table.
    This is the most basic access method. O(n) — reads every page.
    
    VIVA TIP: "SeqScan is used when there's no index on the column 
    we're searching. It must read every single page."
    """

    def __init__(self, records):
        self.records = records  # list of (rid, record) tuples
        self.index = 0

    def open(self):
        self.index = 0

    def next(self):
        if self.index < len(self.records):
            result = self.records[self.index]
            self.index += 1
            return result
        return None

    def close(self):
        pass


class FilterOperator:
    """
    Filter — applies a WHERE condition.
    Wraps another operator and only passes through matching tuples.
    
    VIVA TIP: "Filter is a selection operator (σ in relational algebra).
    In the Volcano model, it pulls tuples from its child operator and 
    only passes through those that satisfy the predicate."
    """

    def __init__(self, child, column, op, value):
        self.child = child
        self.column = column
        self.op = op
        self.value = value

    def open(self):
        self.child.open()

    def next(self):
        while True:
            row = self.child.next()
            if row is None:
                return None
            rid, record = row
            col_val = record.data.get(self.column)
            if col_val is not None and self._compare(col_val, self.op, self.value):
                return row

    def _compare(self, a, op, b):
        """Apply comparison operator."""
        if op == "=":
            return a == b
        elif op == "!=":
            return a != b
        elif op == ">":
            return a > b
        elif op == "<":
            return a < b
        elif op == ">=":
            return a >= b
        elif op == "<=":
            return a <= b
        return False

    def close(self):
        self.child.close()


class ProjectionOperator:
    """
    Projection — selects specific columns.
    If columns = ["*"], passes everything through.
    
    VIVA TIP: "Projection is π in relational algebra. It reduces 
    the width of tuples by keeping only the requested columns."
    """

    def __init__(self, child, columns):
        self.child = child
        self.columns = columns

    def open(self):
        self.child.open()

    def next(self):
        row = self.child.next()
        if row is None:
            return None
        rid, record = row
        if self.columns == ["*"]:
            return row
        # Project only requested columns
        projected = {k: v for k, v in record.data.items() if k in self.columns}
        from storage import Record
        return (rid, Record(projected))

    def close(self):
        self.child.close()


class NestedLoopJoinOperator:
    """
    Nested Loop Join — the simplest join algorithm.
    For each row in the outer table, scan ALL rows in the inner table.
    
    Time complexity: O(n * m) where n, m are the sizes of the two tables.
    
    VIVA TIP: "This is the brute force join. For each outer tuple, we 
    scan the entire inner table. It's simple but slow — O(n*m). 
    Better alternatives are Sort-Merge Join and Hash Join."
    """

    def __init__(self, outer_records, inner_records, join_col):
        self.outer = outer_records
        self.inner = inner_records
        self.join_col = join_col
        self.results = []
        self.index = 0

    def open(self):
        self.results = []
        self.index = 0
        # Nested loop: for each outer row, check all inner rows
        for _, outer_rec in self.outer:
            for _, inner_rec in self.inner:
                if outer_rec.data.get(self.join_col) == inner_rec.data.get(self.join_col):
                    # Merge the two records
                    merged = {**outer_rec.data, **inner_rec.data}
                    from storage import Record
                    self.results.append((None, Record(merged)))

    def next(self):
        if self.index < len(self.results):
            result = self.results[self.index]
            self.index += 1
            return result
        return None

    def close(self):
        pass


def execute_pipeline(operator) -> list:
    """
    Run a Volcano-model pipeline and collect all results.
    
    This is the "pull" model: we keep calling next() until 
    the operator returns None (no more tuples).
    """
    operator.open()
    results = []
    while True:
        row = operator.next()
        if row is None:
            break
        results.append(row)
    operator.close()
    return results
