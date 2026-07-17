"""
B+ Tree Index — Fast lookup structure.

WHAT THIS DOES (for viva):
- Without an index, finding a record requires scanning ALL pages (O(n)).
- A B+ Tree gives us O(log n) search, insert, delete.
- Internal nodes store KEYS + CHILD POINTERS (for navigation).
- Leaf nodes store KEYS + RECORD POINTERS (RIDs) + a NEXT pointer to sibling leaf.
- All actual data pointers are in leaf nodes (unlike B-tree where data can be in any node).

KEY CONCEPTS:
- Order (max_keys): Max keys per node. If exceeded, the node SPLITS.
- Split: When a node overflows, split into two and push middle key UP to parent.
- Merge: When a node underflows after deletion, merge with sibling.
- All leaves are at the same depth (perfectly balanced).
- Leaf nodes are linked (next pointers) for efficient range scans.

VIVA TIP: "B+ trees are the most common index structure in databases like 
PostgreSQL and MySQL. All data pointers live in leaf nodes, which are linked 
together for fast range queries. The tree stays balanced because splits 
propagate upward."
"""


class BPlusTreeNode:
    """A node in the B+ tree. Can be internal or leaf."""

    def __init__(self, is_leaf=True):
        self.is_leaf = is_leaf
        self.keys = []        # Search keys
        self.children = []    # For internal: child nodes. For leaf: record values/RIDs
        self.next = None      # For leaf nodes: pointer to next leaf (for range scans)
        self.parent = None


class BPlusTree:
    """
    Simple in-memory B+ Tree index.

    order = max number of keys per node.
    When a node has more than `order` keys, it splits.
    
    Supports: search, insert, range_search, delete
    """

    def __init__(self, order: int = 4):
        self.root = BPlusTreeNode(is_leaf=True)
        self.order = order  # max keys per node

    def search(self, key):
        """
        Search for a key. Returns the associated value (RID) or None.
        
        Algorithm: Start at root, go down to the correct leaf,
        then linear search within the leaf.
        
        Time: O(log n) — we only visit one node per level.
        """
        leaf = self._find_leaf(key)
        for i, k in enumerate(leaf.keys):
            if k == key:
                return leaf.children[i]
        return None

    def range_search(self, start_key, end_key):
        """
        Range query: find all records with start_key <= key <= end_key.
        
        Uses the linked list of leaf nodes to scan efficiently.
        This is WHY leaf nodes have 'next' pointers!
        """
        results = []
        leaf = self._find_leaf(start_key)

        while leaf is not None:
            for i, k in enumerate(leaf.keys):
                if start_key <= k <= end_key:
                    results.append((k, leaf.children[i]))
                elif k > end_key:
                    return results
            leaf = leaf.next  # follow the linked list to next leaf

        return results

    def insert(self, key, value):
        """
        Insert a key-value pair into the B+ tree.
        
        Algorithm:
        1. Find the correct leaf node.
        2. Insert the key in sorted order.
        3. If the leaf overflows (> order keys), SPLIT it.
        4. Splitting may cascade up to the root.
        
        VIVA TIP: "Insertion always happens at a leaf. If the leaf is full,
        we split it into two leaves and push the middle key up to the parent.
        If the parent also overflows, we split that too — this can go all
        the way up to the root, which is how the tree grows taller."
        """
        leaf = self._find_leaf(key)

        # Insert key in sorted position within the leaf
        idx = 0
        while idx < len(leaf.keys) and leaf.keys[idx] < key:
            idx += 1

        # Update if key already exists
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            leaf.children[idx] = value
            return

        leaf.keys.insert(idx, key)
        leaf.children.insert(idx, value)

        # Check if leaf overflows
        if len(leaf.keys) > self.order:
            self._split_leaf(leaf)

    def delete(self, key):
        """
        Delete a key from the B+ tree.
        Simplified version: just removes from the leaf (no rebalancing/merging).
        
        VIVA TIP: "In a full implementation, deletion may cause underflow,
        requiring redistribution from siblings or merging nodes. Our simplified
        version just removes the key from the leaf."
        """
        leaf = self._find_leaf(key)
        for i, k in enumerate(leaf.keys):
            if k == key:
                leaf.keys.pop(i)
                leaf.children.pop(i)
                return True
        return False

    def _find_leaf(self, key) -> BPlusTreeNode:
        """Navigate from root to the correct leaf node."""
        node = self.root
        while not node.is_leaf:
            # Find which child to follow
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            node = node.children[i]
        return node

    def _split_leaf(self, leaf):
        """
        Split an overflowing leaf node.
        
        1. Create new leaf with the upper half of keys.
        2. Push the first key of new leaf UP to parent.
        3. Maintain the leaf linked list.
        """
        mid = len(leaf.keys) // 2
        new_leaf = BPlusTreeNode(is_leaf=True)

        # Move upper half to new leaf
        new_leaf.keys = leaf.keys[mid:]
        new_leaf.children = leaf.children[mid:]
        leaf.keys = leaf.keys[:mid]
        leaf.children = leaf.children[:mid]

        # Maintain linked list
        new_leaf.next = leaf.next
        leaf.next = new_leaf

        # Push up the first key of new_leaf to parent
        push_up_key = new_leaf.keys[0]
        self._insert_into_parent(leaf, push_up_key, new_leaf)

    def _split_internal(self, node):
        """Split an overflowing internal node."""
        mid = len(node.keys) // 2
        push_up_key = node.keys[mid]

        new_node = BPlusTreeNode(is_leaf=False)
        new_node.keys = node.keys[mid + 1 :]
        new_node.children = node.children[mid + 1 :]
        node.keys = node.keys[:mid]
        node.children = node.children[: mid + 1]

        # Update parent pointers
        for child in new_node.children:
            child.parent = new_node

        self._insert_into_parent(node, push_up_key, new_node)

    def _insert_into_parent(self, left, key, right):
        """Insert a key into the parent after a split."""
        if left.parent is None:
            # Create new root
            new_root = BPlusTreeNode(is_leaf=False)
            new_root.keys = [key]
            new_root.children = [left, right]
            left.parent = new_root
            right.parent = new_root
            self.root = new_root
        else:
            parent = left.parent
            # Find position for new key
            idx = 0
            while idx < len(parent.keys) and parent.keys[idx] < key:
                idx += 1
            parent.keys.insert(idx, key)
            parent.children.insert(idx + 1, right)
            right.parent = parent

            # Check if parent overflows
            if len(parent.keys) > self.order:
                self._split_internal(parent)

    def print_tree(self):
        """Pretty print the B+ tree (for debugging / demo)."""
        if not self.root:
            print("Empty tree")
            return

        levels = []
        current_level = [self.root]

        while current_level:
            level_keys = []
            next_level = []
            for node in current_level:
                level_keys.append(str(node.keys))
                if not node.is_leaf:
                    next_level.extend(node.children)
            levels.append(" | ".join(level_keys))
            current_level = next_level

        for i, level in enumerate(levels):
            prefix = "Root:  " if i == 0 else f"L{i}:    "
            print(f"{prefix}{level}")

        # Print leaf chain
        leaf = self.root
        while not leaf.is_leaf:
            leaf = leaf.children[0]
        chain = []
        while leaf:
            chain.append(str(leaf.keys))
            leaf = leaf.next
        print(f"Leaves: {' -> '.join(chain)}")
