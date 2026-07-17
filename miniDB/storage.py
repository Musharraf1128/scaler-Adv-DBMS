"""
Storage Engine — The lowest layer of miniDB.

WHAT THIS DOES (for viva):
- A real DB stores data on disk in fixed-size chunks called PAGES (like 4KB blocks).
- Each page uses a "slotted page" layout: a header at the top, records packed from the bottom.
- A HEAP FILE is just a collection of pages stored sequentially in a file.
- Records are variable-length rows (like a row in a table).

KEY CONCEPTS:
- Page: Fixed-size block (4096 bytes default). Unit of disk I/O.
- Slotted Page: Header has a slot directory pointing to where each record starts.
- Heap File: Unordered collection of pages. New records go wherever there's space.
- RID (Record ID): (page_id, slot_id) — uniquely identifies any record on disk.
"""

import struct
import os

# ----- Constants -----
PAGE_SIZE = 4096  # 4KB pages, same as SQLite/PostgreSQL default


class Record:
    """
    A single row/tuple in our database.
    We store records as: [4-byte length][raw bytes of the data]
    
    Think of it as one row in a table, e.g. (1, "Alice", 90)
    """

    def __init__(self, data: dict):
        self.data = data  # e.g. {"id": 1, "name": "Alice", "grade": 90}

    def serialize(self) -> bytes:
        """Convert record to bytes for disk storage."""
        # We use a simple format: key1=val1|key2=val2|...
        text = "|".join(f"{k}={v}" for k, v in self.data.items())
        raw = text.encode("utf-8")
        # Prefix with 4-byte length so we know how much to read back
        return struct.pack("I", len(raw)) + raw

    @staticmethod
    def deserialize(raw_bytes: bytes) -> "Record":
        """Read a record back from bytes."""
        length = struct.unpack("I", raw_bytes[:4])[0]
        text = raw_bytes[4 : 4 + length].decode("utf-8")
        data = {}
        for pair in text.split("|"):
            key, val = pair.split("=", 1)
            # Try to convert to int if possible
            try:
                data[key] = int(val)
            except ValueError:
                data[key] = val
        return Record(data)

    def byte_size(self) -> int:
        """Total bytes this record takes on disk (including length prefix)."""
        return len(self.serialize())

    def __repr__(self):
        return f"Record({self.data})"


class Page:
    """
    A fixed-size page (4096 bytes) using slotted-page layout.

    Layout:
    ┌──────────────────────────────────────────────┐
    │ Header: [num_records (2B)] [free_space_ptr (2B)] │
    │ Slot Directory: [offset1 (2B)][size1 (2B)] ...   │
    │ ... free space ...                               │
    │ ... records packed from bottom up ...             │
    └──────────────────────────────────────────────┘

    VIVA TIP: "Slotted pages let us store variable-length records.
    The slot directory at the top points to records at the bottom.
    Free space is in the middle."
    """

    HEADER_SIZE = 4  # 2 bytes num_records + 2 bytes free_space_pointer

    def __init__(self, page_id: int):
        self.page_id = page_id
        self.records = []  # list of Record objects
        self.dirty = False  # has this page been modified since last disk write?

    def can_fit(self, record: Record) -> bool:
        """Check if this page has room for one more record."""
        used = self.HEADER_SIZE + len(self.records) * 4  # slot directory
        for r in self.records:
            if r is not None:
                used += r.byte_size()
            else:
                used += 4  # tombstone size
        return used + record.byte_size() + 4 <= PAGE_SIZE  # +4 for new slot entry

    def insert(self, record: Record) -> int:
        """Insert a record, return the slot index."""
        if not self.can_fit(record):
            raise Exception("Page full!")
        slot_id = len(self.records)
        self.records.append(record)
        self.dirty = True
        return slot_id

    def delete(self, slot_id: int):
        """Delete a record by marking its slot as None (tombstone)."""
        if 0 <= slot_id < len(self.records):
            self.records[slot_id] = None  # tombstone — mark as deleted
            self.dirty = True

    def get(self, slot_id: int) -> Record:
        """Get a record by slot index."""
        if 0 <= slot_id < len(self.records):
            return self.records[slot_id]
        return None

    def serialize(self) -> bytes:
        """Serialize entire page to exactly PAGE_SIZE bytes."""
        # Pack all records
        record_bytes = []
        for r in self.records:
            if r is None:
                record_bytes.append(b"\x00\x00\x00\x00")  # tombstone = 4 zero bytes
            else:
                record_bytes.append(r.serialize())

        # Header: num_records
        data = struct.pack("H", len(self.records))
        # Then each record's bytes
        for rb in record_bytes:
            data += struct.pack("H", len(rb)) + rb

        # Pad to PAGE_SIZE
        data += b"\x00" * (PAGE_SIZE - len(data))
        return data

    @staticmethod
    def deserialize(page_id: int, raw: bytes) -> "Page":
        """Read a page from raw bytes."""
        page = Page(page_id)
        offset = 0
        num_records = struct.unpack("H", raw[offset : offset + 2])[0]
        offset += 2

        for _ in range(num_records):
            rec_len = struct.unpack("H", raw[offset : offset + 2])[0]
            offset += 2
            rec_bytes = raw[offset : offset + rec_len]
            offset += rec_len

            if rec_bytes == b"\x00\x00\x00\x00":
                page.records.append(None)  # tombstone
            else:
                page.records.append(Record.deserialize(rec_bytes))

        return page


class HeapFile:
    """
    A Heap File = a file on disk that stores pages sequentially.
    
    This is the simplest file organization — records are just appended
    wherever there is free space. No ordering, no indexing.

    VIVA TIP: "A heap file is an unordered collection of pages. 
    To find a record without an index, you must scan ALL pages (sequential scan).
    That's why we need indexes like B+ trees for fast lookups."
    """

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.pages = {}  # page_id -> Page  (in-memory cache, replaced by BufferPool later)
        self.num_pages = 0
        self._load()

    def _load(self):
        """Load existing pages from disk file."""
        if os.path.exists(self.filepath):
            size = os.path.getsize(self.filepath)
            self.num_pages = size // PAGE_SIZE
            # Don't load all pages into memory — that's the buffer pool's job
        else:
            # Create empty file
            with open(self.filepath, "wb") as f:
                pass

    def read_page(self, page_id: int) -> Page:
        """Read a specific page from disk."""
        with open(self.filepath, "rb") as f:
            f.seek(page_id * PAGE_SIZE)
            raw = f.read(PAGE_SIZE)
            if len(raw) < PAGE_SIZE:
                return Page(page_id)  # empty page
            return Page.deserialize(page_id, raw)

    def write_page(self, page: Page):
        """Write a page back to disk."""
        # Ensure file is big enough
        with open(self.filepath, "r+b" if os.path.getsize(self.filepath) > 0 else "wb") as f:
            f.seek(page.page_id * PAGE_SIZE)
            f.write(page.serialize())
        page.dirty = False

    def allocate_page(self) -> Page:
        """Create a new empty page at the end of the file."""
        page = Page(self.num_pages)
        self.num_pages += 1
        # Write empty page to disk to extend file
        with open(self.filepath, "ab") as f:
            f.write(b"\x00" * PAGE_SIZE)
        return page

    def insert_record(self, record: Record) -> tuple:
        """
        Insert a record into the heap file.
        Returns (page_id, slot_id) = the RID (Record ID).
        
        Strategy: scan pages for one with free space, else allocate new page.
        This is the "free space management" from your syllabus.
        """
        # Try existing pages first
        for pid in range(self.num_pages):
            page = self.read_page(pid)
            if page.can_fit(record):
                slot_id = page.insert(record)
                self.write_page(page)
                return (pid, slot_id)

        # No space found — allocate new page
        page = self.allocate_page()
        slot_id = page.insert(record)
        self.write_page(page)
        return (page.page_id, slot_id)

    def scan_all(self):
        """
        Sequential scan — read ALL records from ALL pages.
        This is the full table scan used by SeqScan operator.
        """
        results = []
        for pid in range(self.num_pages):
            page = self.read_page(pid)
            for slot_id, record in enumerate(page.records):
                if record is not None:
                    results.append(((pid, slot_id), record))
        return results

    def delete_record(self, page_id: int, slot_id: int):
        """Delete a record by its RID."""
        page = self.read_page(page_id)
        page.delete(slot_id)
        self.write_page(page)
