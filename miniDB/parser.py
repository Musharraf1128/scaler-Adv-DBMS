"""
SQL Parser — Converts SQL text into structured commands.

WHAT THIS DOES (for viva):
- Users type SQL like "SELECT * FROM students WHERE grade > 80"
- The parser breaks this into tokens (LEXING) and then into a structured
  command (PARSING) that the executor can understand.
- In real databases, parsing produces an AST (Abstract Syntax Tree).
- Our simplified version produces a command dict (same idea, simpler).

KEY CONCEPTS:
- Lexing/Tokenization: Breaking "SELECT * FROM t" into ["SELECT", "*", "FROM", "t"]
- Parsing: Converting tokens into a structured representation (AST or dict)
- Logical Plan: The parsed query before optimization (what to do, not how)

VIVA TIP: "The parser is the first stage of the query processing pipeline.
It takes raw SQL text, tokenizes it, validates syntax, and produces a 
logical plan that the query executor can process."
"""

import re


def parse(sql: str) -> dict:
    """
    Parse a SQL statement into a command dictionary.

    Supported statements:
    - CREATE TABLE name (col1, col2, ...)
    - INSERT INTO name VALUES (val1, val2, ...)
    - SELECT col1, col2 FROM name [WHERE condition] [ORDER BY col]
    - DELETE FROM name WHERE condition
    - UPDATE name SET col=val WHERE condition

    Returns a dict like:
    {"type": "SELECT", "table": "students", "columns": ["*"], 
     "where": {"column": "grade", "op": ">", "value": 80}}
    """
    sql = sql.strip().rstrip(";")
    tokens = sql.split()

    if not tokens:
        return {"type": "ERROR", "message": "Empty query"}

    command = tokens[0].upper()

    if command == "CREATE":
        return _parse_create(sql)
    elif command == "INSERT":
        return _parse_insert(sql)
    elif command == "SELECT":
        return _parse_select(sql)
    elif command == "DELETE":
        return _parse_delete(sql)
    elif command == "UPDATE":
        return _parse_update(sql)
    elif command == "EXPLAIN":
        # EXPLAIN wraps a SELECT — parse the inner SELECT and tag it
        inner_sql = sql[len("EXPLAIN"):].strip()
        result = _parse_select(inner_sql)
        if result["type"] == "SELECT":
            result["explain"] = True
        return result
    else:
        return {"type": "ERROR", "message": f"Unknown command: {command}"}


def _parse_create(sql: str) -> dict:
    """Parse: CREATE TABLE students (id, name, grade)"""
    match = re.match(
        r"CREATE\s+TABLE\s+(\w+)\s*\((.+)\)", sql, re.IGNORECASE
    )
    if not match:
        return {"type": "ERROR", "message": "Invalid CREATE TABLE syntax"}

    table_name = match.group(1)
    columns = [col.strip() for col in match.group(2).split(",")]

    return {"type": "CREATE", "table": table_name, "columns": columns}


def _parse_insert(sql: str) -> dict:
    """Parse: INSERT INTO students VALUES (1, 'Alice', 90)"""
    match = re.match(
        r"INSERT\s+INTO\s+(\w+)\s+VALUES\s*\((.+)\)", sql, re.IGNORECASE
    )
    if not match:
        return {"type": "ERROR", "message": "Invalid INSERT syntax"}

    table_name = match.group(1)
    raw_values = match.group(2)

    values = []
    for v in raw_values.split(","):
        v = v.strip().strip("'\"")
        try:
            values.append(int(v))
        except ValueError:
            values.append(v)

    return {"type": "INSERT", "table": table_name, "values": values}


def _parse_select(sql: str) -> dict:
    """Parse: SELECT * FROM students [JOIN orders ON students.id = orders.uid] [WHERE grade > 80] [ORDER BY name]"""
    result = {"type": "SELECT", "columns": [], "table": "", "where": None,
              "order_by": None, "join": None, "explain": False}

    # Remove ORDER BY first
    order_match = re.search(r"\s+ORDER\s+BY\s+(\w+)", sql, re.IGNORECASE)
    if order_match:
        result["order_by"] = order_match.group(1)
        sql = sql[: order_match.start()]

    # Check for WHERE
    where_match = re.search(
        r"\s+WHERE\s+(\w+)\s*(=|!=|>|<|>=|<=)\s*(.+)$", sql, re.IGNORECASE
    )
    if where_match:
        col = where_match.group(1)
        op = where_match.group(2)
        val = where_match.group(3).strip().strip("'\"")
        try:
            val = int(val)
        except ValueError:
            pass
        result["where"] = {"column": col, "op": op, "value": val}
        sql = sql[: where_match.start()]

    # Check for JOIN ... ON ...
    join_match = re.search(
        r"\s+JOIN\s+(\w+)\s+ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)",
        sql, re.IGNORECASE
    )
    if join_match:
        result["join"] = {
            "table": join_match.group(1),
            "left_table": join_match.group(2),
            "left_col": join_match.group(3),
            "right_table": join_match.group(4),
            "right_col": join_match.group(5),
        }
        sql = sql[: join_match.start()]

    # Parse SELECT ... FROM ...
    select_from = re.match(
        r"SELECT\s+(.+?)\s+FROM\s+(\w+)", sql, re.IGNORECASE
    )
    if not select_from:
        return {"type": "ERROR", "message": "Invalid SELECT syntax"}

    cols = select_from.group(1)
    result["columns"] = [c.strip() for c in cols.split(",")]
    result["table"] = select_from.group(2)

    return result


def _parse_delete(sql: str) -> dict:
    """Parse: DELETE FROM students WHERE id = 1"""
    result = {"type": "DELETE", "table": "", "where": None}

    where_match = re.search(
        r"\s+WHERE\s+(\w+)\s*(=|!=|>|<|>=|<=)\s*(.+)$", sql, re.IGNORECASE
    )
    if where_match:
        col = where_match.group(1)
        op = where_match.group(2)
        val = where_match.group(3).strip().strip("'\"")
        try:
            val = int(val)
        except ValueError:
            pass
        result["where"] = {"column": col, "op": op, "value": val}
        sql = sql[: where_match.start()]

    table_match = re.match(r"DELETE\s+FROM\s+(\w+)", sql, re.IGNORECASE)
    if not table_match:
        return {"type": "ERROR", "message": "Invalid DELETE syntax"}
    result["table"] = table_match.group(1)

    return result


def _parse_update(sql: str) -> dict:
    """Parse: UPDATE students SET grade = 95 WHERE id = 1"""
    result = {"type": "UPDATE", "table": "", "set": {}, "where": None}

    where_match = re.search(
        r"\s+WHERE\s+(\w+)\s*(=|!=|>|<|>=|<=)\s*(.+)$", sql, re.IGNORECASE
    )
    if where_match:
        col = where_match.group(1)
        op = where_match.group(2)
        val = where_match.group(3).strip().strip("'\"")
        try:
            val = int(val)
        except ValueError:
            pass
        result["where"] = {"column": col, "op": op, "value": val}
        sql = sql[: where_match.start()]

    match = re.match(
        r"UPDATE\s+(\w+)\s+SET\s+(\w+)\s*=\s*(.+)", sql, re.IGNORECASE
    )
    if not match:
        return {"type": "ERROR", "message": "Invalid UPDATE syntax"}

    result["table"] = match.group(1)
    set_col = match.group(2)
    set_val = match.group(3).strip().strip("'\"")
    try:
        set_val = int(set_val)
    except ValueError:
        pass
    result["set"] = {set_col: set_val}

    return result
