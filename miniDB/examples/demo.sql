-- MiniDB demo
-- run with: python3 main.py < examples/demo.sql

-- Two tables, each with a primary-key B+ tree index
CREATE TABLE users (id, name, age)
CREATE TABLE orders (oid, uid, item)

-- Rows land in slotted heap pages through the buffer pool
INSERT INTO users VALUES (1, 'alice', 30)
INSERT INTO users VALUES (2, 'bob', 25)
INSERT INTO users VALUES (3, 'carol', 41)
INSERT INTO orders VALUES (100, 1, 'keyboard')
INSERT INTO orders VALUES (101, 3, 'monitor')
INSERT INTO orders VALUES (102, 1, 'mouse')

-- Scan + filter (Volcano pipeline: SeqScan -> Filter -> Projection)
SELECT name, age FROM users WHERE age > 28

-- The optimizer chooses the B+ tree index for a primary-key equality match
EXPLAIN SELECT * FROM users WHERE id = 2
SELECT * FROM users WHERE id = 2

-- ORDER BY uses a sort operator
SELECT * FROM users ORDER BY age

-- Hash Join between two tables
SELECT * FROM users JOIN orders ON users.id = orders.uid

-- Transaction with WAL logging
BEGIN
UPDATE users SET age = 26 WHERE id = 2
SELECT * FROM users WHERE id = 2
COMMIT

-- DELETE with filter
DELETE FROM users WHERE id = 3
SELECT * FROM users

.tables
.index users
.wal
.quit
