"""
Buffer Pool Manager — The caching layer between memory and disk.

WHAT THIS DOES (for viva):
- Reading from disk is SLOW (~10ms). Reading from RAM is FAST (~100ns).
- The buffer pool keeps frequently-used pages in memory (RAM).
- When memory is full, it must EVICT a page using a replacement policy.
- We implement LRU (Least Recently Used) — evict the page used longest ago.
- LRU-K is an improvement: tracks the K-th most recent access instead of just the last one.

KEY CONCEPTS:
- Frame: A slot in memory that holds one page.
- Pin Count: How many operations are currently using this page. Can't evict if pinned.
- Dirty Flag: True if the page was modified in memory but not yet written to disk.
- Page Table: Maps page_id → frame_id (which memory slot holds which page).
- LRU Replacement: When buffer is full, evict the least recently used unpinned page.

VIVA TIP: "The buffer pool is like a cache. It avoids expensive disk reads by 
keeping hot pages in memory. The pin count prevents evicting pages that are 
currently being used. Dirty pages must be flushed to disk before eviction."
"""

from collections import OrderedDict
from storage import Page, HeapFile, PAGE_SIZE


class BufferPool:
    """
    Buffer Pool with LRU replacement policy.
    
    Capacity = max number of pages we can keep in memory at once.
    When full and we need a new page, evict the LRU unpinned page.
    """

    def __init__(self, heap_file: HeapFile, capacity: int = 10):
        self.heap_file = heap_file
        self.capacity = capacity

        # Page table: page_id -> Page object (the "frame")
        self.page_table = OrderedDict()  # OrderedDict gives us LRU for free

        # Pin counts: page_id -> int (how many users are reading/writing this page)
        self.pin_count = {}

        # Stats for demonstration
        self.hits = 0
        self.misses = 0

    def fetch_page(self, page_id: int) -> Page:
        """
        Get a page. If it's in the buffer pool (HIT), return it.
        If not (MISS), read from disk, possibly evicting another page.
        
        This is the core function of the buffer pool.
        """
        if page_id in self.page_table:
            # CACHE HIT — move to end (most recently used)
            self.page_table.move_to_end(page_id)
            self.pin_count[page_id] = self.pin_count.get(page_id, 0) + 1
            self.hits += 1
            return self.page_table[page_id]

        # CACHE MISS — need to load from disk
        self.misses += 1

        # If buffer is full, evict LRU page
        if len(self.page_table) >= self.capacity:
            self._evict()

        # Read page from disk
        page = self.heap_file.read_page(page_id)
        self.page_table[page_id] = page
        self.pin_count[page_id] = 1
        return page

    def _evict(self):
        """
        Evict the Least Recently Used page that is not pinned.
        
        LRU Policy: The page at the FRONT of OrderedDict is the oldest.
        We scan from front to find an unpinned page to evict.
        
        VIVA TIP: "We can't evict a page that's currently being used (pinned).
        If it's dirty, we must flush it to disk first to not lose changes."
        """
        for page_id in list(self.page_table.keys()):
            if self.pin_count.get(page_id, 0) <= 0:
                page = self.page_table[page_id]
                # If dirty, write back to disk first!
                if page.dirty:
                    self.flush_page(page_id)
                del self.page_table[page_id]
                del self.pin_count[page_id]
                return

        raise Exception("Buffer pool full! All pages are pinned — cannot evict.")

    def unpin_page(self, page_id: int):
        """
        Unpin a page (done using it). Decrements pin count.
        A page can only be evicted when pin_count == 0.
        """
        if page_id in self.pin_count:
            self.pin_count[page_id] = max(0, self.pin_count[page_id] - 1)

    def flush_page(self, page_id: int):
        """Write a dirty page back to disk."""
        if page_id in self.page_table:
            self.heap_file.write_page(self.page_table[page_id])

    def flush_all(self):
        """Flush all dirty pages to disk."""
        for page_id, page in self.page_table.items():
            if page.dirty:
                self.heap_file.write_page(page)

    def new_page(self) -> Page:
        """Allocate a new page (via heap file) and bring it into the buffer pool."""
        if len(self.page_table) >= self.capacity:
            self._evict()
        page = self.heap_file.allocate_page()
        self.page_table[page.page_id] = page
        self.pin_count[page.page_id] = 1
        return page

    def get_stats(self) -> dict:
        """Return buffer pool statistics."""
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{self.hits / total * 100:.1f}%" if total > 0 else "N/A",
            "pages_in_memory": len(self.page_table),
            "capacity": self.capacity,
        }
