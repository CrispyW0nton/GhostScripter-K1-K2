"""
GhostScripter-K1-K2 — 2DA File Manager
Enhanced with TSLPatcher-style operations:
  - CopyRow: duplicate an existing row with overrides
  - AddRow:  add a new row (or update existing via exclusive column)
  - ModifyRow: change specific cells in existing rows
  - ColumnAdd: add a new column with a default value
  - 2DAMEMORY: token-based value references for chained edits
  - Export changes.ini: generate TSLPatcher-compatible patch files

Improvements (open-source tools):
  - to_binary(): write binary 2DA V2.b format (matching xoreos-tools layout)
  - Undo/redo now uses collections.deque for O(1) bounded growth
  - search() uses cachetools.LRUCache for O(1) repeated queries
  - find_rows_where(): fast exact-column lookup

References:
  - TSLPatcher lib/site/Bioware/TwoDA.pm (add_row, change_cell, copy_row)
  - PyKotor tslpatcher/mods/twoda.py (AddRow2DA, CopyRow2DA, Modify2DA)
  - xoreos-tools 2dafile.cpp (binary 2DA format)
"""
from __future__ import annotations

import collections
import copy
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Optional fast-lookup dependencies ─────────────────────────
try:
    from cachetools import LRUCache as _LRUCache
    _HAS_CACHETOOLS = True
except ImportError:  # pragma: no cover
    _HAS_CACHETOOLS = False


# ── Row ────────────────────────────────────────────────────────

@dataclass
class TwoDARow:
    label: str
    data: Dict[str, str] = field(default_factory=dict)

    def get(self, column: str, default: str = "****") -> str:
        return self.data.get(column, default)

    def set(self, column: str, value: str):
        self.data[column] = value

    def update_values(self, changes: Dict[str, str]):
        """Apply a dict of {column: value} changes (TSLPatcher apply pattern)."""
        for col, val in changes.items():
            self.data[col] = val

    def copy_data(self) -> Dict[str, str]:
        return dict(self.data)

    def get_all_values(self) -> List[str]:
        """Return all cell values as a list (used for search/filter)."""
        return list(self.data.values())


# ── 2DA File ───────────────────────────────────────────────────

class TwoDAFile:
    """
    Parse, edit, and write a 2DA file.
    Supports the full TSLPatcher operation set.
    """

    # Maximum undo history depth (prevents unbounded memory growth)
    _MAX_HISTORY = 50
    # LRU cache size for search queries
    _SEARCH_CACHE_SIZE = 64

    def __init__(self, filename: str = ""):
        self.filename = filename
        self.file_path: Path | None = None
        self.rows: list[TwoDARow] = []
        self.columns: list[str] = []
        # Undo/redo stacks — deque(maxlen) gives O(1) auto-trim at max depth
        self._history: collections.deque = collections.deque(
            maxlen=self._MAX_HISTORY
        )
        self._redo_stack: list[tuple[list[TwoDARow], list[str]]] = []
        # Per-instance LRU search cache
        if _HAS_CACHETOOLS:
            self._search_cache: Any = _LRUCache(maxsize=self._SEARCH_CACHE_SIZE)
        else:
            self._search_cache = None

    # ── I/O ──────────────────────────────────────────────────

    @classmethod
    def from_file(cls, file_path: Path) -> "TwoDAFile":
        obj = cls(file_path.name)
        obj.file_path = file_path

        with open(file_path, "rb") as f:
            raw = f.read()

        if raw[:9] == b"2DA V2.b\n":
            obj._parse_binary(raw)
        else:
            text = raw.decode("utf-8", errors="replace")
            obj._parse_lines(text.splitlines(keepends=True))
        return obj

    @classmethod
    def from_bytes(cls, data: bytes, filename: str = "unnamed.2da") -> "TwoDAFile":
        """Parse a 2DA from raw bytes (binary V2.b or text V2.0)."""
        obj = cls(filename)
        if data[:9] == b"2DA V2.b\n":
            obj._parse_binary(data)
        else:
            text = data.decode("utf-8", errors="replace")
            obj._parse_lines(text.splitlines(keepends=True))
        return obj

    @classmethod
    def from_text(cls, text: str, filename: str = "unnamed.2da") -> "TwoDAFile":
        obj = cls(filename)
        obj._parse_lines(text.splitlines(keepends=True))
        return obj

    @classmethod
    def from_binary(cls, data: bytes, filename: str = "unnamed.2da") -> "TwoDAFile":
        """
        Parse a KotOR binary 2DA file (format '2DA V2.b') from raw bytes.

        This is a named alias for from_bytes() that accepts only binary data.
        Based on OldRepublicDevs/PyKotor TwoDABinaryReader and
        swkotor.exe C2DA::Load2DArray @ 0x004143b0.

        Raises ValueError if the data is not a valid binary 2DA.
        """
        if len(data) < 9 or data[:4] != b"2DA ":
            raise ValueError(f"Not a 2DA file (magic={data[:4]!r})")
        if data[4:8] != b"V2.b":
            raise ValueError(f"Unsupported 2DA version (got {data[4:8]!r}; expected b'V2.b')")
        obj = cls(filename)
        obj._parse_binary(data)
        return obj

    def _parse_binary(self, raw: bytes):
        """
        Parse KotOR binary 2DA format (2DA V2.b).

        Layout:
          '2DA V2.b\\n'          -- 9-byte header
          col1\\tcol2\\t...\\t\\x00  -- tab-separated column names, null-terminated
          uint32                 -- row count
          lbl0\\tlbl1\\t...\\t\\x00  -- tab-separated row labels, null-terminated
          uint16[row_count * col_count]  -- cell string-table byte offsets
                                           (0xFFFF = blank / '****')
          <string table>         -- null-terminated strings, concatenated,
                                   directly follows cell array (no size prefix)

        Reference: xoreos-tools/src/aurora/2dafile.cpp
        """
        pos = 0

        # Header
        nl = raw.index(b"\n", pos)
        pos = nl + 1

        # Column names: tab-separated, ends with \\t\\x00
        col_end = raw.index(b"\t\x00", pos)
        cols_raw = raw[pos:col_end].decode("latin-1", errors="replace")
        self.columns = [c for c in cols_raw.split("\t") if c]
        pos = col_end + 2
        n_cols = len(self.columns)

        # Row count (uint32 LE)
        (row_count,) = struct.unpack_from("<I", raw, pos)
        pos += 4

        # Row labels: tab-separated, exactly row_count labels.
        # Each label ends with '\t' (no trailing null — matches xoreos and real KotOR files).
        if row_count == 0:
            row_labels = []
        else:
            row_labels = []
            while len(row_labels) < row_count and pos < len(raw):
                try:
                    tab = raw.index(b"\t", pos)
                    label = raw[pos:tab].decode("latin-1", errors="replace")
                    row_labels.append(label)
                    pos = tab + 1
                except ValueError:
                    # No more tabs — use remaining bytes as last label
                    remaining = raw[pos:].split(b"\x00")[0]
                    row_labels.append(remaining.decode("latin-1", errors="replace"))
                    pos = len(raw)
                    break

        # Cell index array: row_count * n_cols uint16 LE values
        # (0xFFFF = blank cell / '****')
        n_cells = row_count * n_cols
        if n_cells > 0:
            cell_data = struct.unpack_from(f"<{n_cells}H", raw, pos)
        else:
            cell_data = ()
        pos += n_cells * 2

        # Sentinel: 2-byte uint16 LE = total size of string data section
        # (present in xoreos/real KotOR format; skip it)
        if pos + 2 <= len(raw):
            pos += 2

        # String table: all remaining bytes, null-terminated strings indexed by byte offset
        # 0xFFFF = blank cell ('****')
        str_data = raw[pos:]
        _strings: Dict[int, str] = {}
        sp = 0
        while sp < len(str_data):
            try:
                nul = str_data.index(b"\x00", sp)
                s = str_data[sp:nul].decode("latin-1", errors="replace")
                _strings[sp] = s
                sp = nul + 1
            except ValueError:
                break

        # Build rows
        self.rows = []
        for r in range(row_count):
            label = row_labels[r] if r < len(row_labels) else str(r)
            row_d: Dict[str, str] = {}
            for c, col in enumerate(self.columns):
                idx = cell_data[r * n_cols + c] if n_cells > 0 else 0xFFFF
                if idx == 0xFFFF:
                    row_d[col] = "****"
                else:
                    row_d[col] = _strings.get(idx, "****")
            self.rows.append(TwoDARow(label=label, data=row_d))


    def _parse_lines(self, lines: list):
        if not lines:
            return

        # Find the 2DA V2.0 header
        header_idx = next(
            (i for i, l in enumerate(lines) if l.strip().upper().startswith("2DA")), 0
        )

        # Column header is 2 lines after header (skip blank line)
        col_idx = header_idx + 2
        if col_idx < len(lines):
            self.columns = lines[col_idx].split()

        # Data rows start after column header
        for line in lines[col_idx + 1:]:
            parts = _split_2da_line(line)
            if not parts:
                continue
            label = parts[0]
            values = parts[1:]
            row_data = {}
            for i, col in enumerate(self.columns):
                row_data[col] = values[i] if i < len(values) else "****"
            self.rows.append(TwoDARow(label=label, data=row_data))

    def to_text(self) -> str:
        """Serialize to 2DA V2.0 text format."""
        # Calculate column widths for alignment
        widths = {}
        for col in self.columns:
            widths[col] = len(col)
        for row in self.rows:
            for col in self.columns:
                widths[col] = max(widths[col], len(row.data.get(col, "****")))

        lines = ["2DA V2.0\n", "\n"]

        # Column header line
        row_num_width = max(4, len(str(max(len(self.rows) - 1, 0))))
        header = " " * (row_num_width + 1)
        for col in self.columns:
            header += col.ljust(widths[col] + 2)
        lines.append(header.rstrip() + "\n")

        # Data rows
        for row in self.rows:
            line = row.label.ljust(row_num_width + 1)
            for col in self.columns:
                val = row.data.get(col, "****")
                line += val.ljust(widths[col] + 2)
            lines.append(line.rstrip() + "\n")

        return "".join(lines)

    def save(self, file_path: Path | None = None):
        target = file_path or self.file_path
        if not target:
            raise ValueError("No file path specified")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.to_text())

    # ── Undo/Redo ─────────────────────────────────────────────

    def _save_state(self):
        """Push current state to undo history.

        Uses deque(maxlen=_MAX_HISTORY) so the oldest entry is automatically
        discarded in O(1) — no manual pop(0) needed.
        """
        state_rows = [TwoDARow(r.label, dict(r.data)) for r in self.rows]
        state_cols = list(self.columns)
        self._history.append((state_rows, state_cols))
        self._redo_stack.clear()
        # Invalidate search cache after any mutation
        if self._search_cache is not None:
            self._search_cache.clear()

    def undo(self) -> bool:
        if not self._history:
            return False
        # Push current to redo
        self._redo_stack.append(
            ([TwoDARow(r.label, dict(r.data)) for r in self.rows], list(self.columns))
        )
        rows, cols = self._history.pop()
        self.rows = rows
        self.columns = cols
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._history.append(
            ([TwoDARow(r.label, dict(r.data)) for r in self.rows], list(self.columns))
        )
        rows, cols = self._redo_stack.pop()
        self.rows = rows
        self.columns = cols
        return True

    # ── Row Operations ────────────────────────────────────────

    def add_row(self, label: str, data: Dict[str, str],
                exclusive_column: str = None) -> int:
        """
        Add a new row. If exclusive_column is set and a row already has
        that column value, update it instead (TSLPatcher AddRow behaviour).
        Returns the index of the new/modified row.
        """
        self._save_state()
        if exclusive_column and exclusive_column in data:
            exclusive_val = data[exclusive_column]
            for idx, row in enumerate(self.rows):
                if row.data.get(exclusive_column) == exclusive_val:
                    row.update_values(data)
                    return idx

        # Auto-number label if not provided or duplicate
        if not label or any(r.label == label for r in self.rows):
            label = str(len(self.rows))

        full_data = {col: "****" for col in self.columns}
        full_data.update(data)
        row = TwoDARow(label=label, data=full_data)
        self.rows.append(row)
        return len(self.rows) - 1

    def copy_row(self, source_index: int, new_label: str = None,
                 overrides: Dict[str, str] = None,
                 exclusive_column: str = None) -> int:
        """
        Copy an existing row to a new row, optionally with cell overrides.
        TSLPatcher CopyRow behaviour:
          - If exclusive_column is set and a row already has that value,
            update it (copy source → target, then apply overrides).
          - Otherwise append a new row.
        Returns the index of the new/modified row.
        """
        self._save_state()
        if not (0 <= source_index < len(self.rows)):
            raise IndexError(f"Source row {source_index} out of range")

        source = self.rows[source_index]
        new_data = source.copy_data()
        if overrides:
            new_data.update(overrides)

        if exclusive_column and overrides and exclusive_column in overrides:
            exclusive_val = overrides[exclusive_column]
            for idx, row in enumerate(self.rows):
                if row.data.get(exclusive_column) == exclusive_val:
                    # Copy source into target, then apply overrides
                    row.update_values(source.copy_data())
                    row.update_values(overrides)
                    return idx

        label = new_label if new_label else str(len(self.rows))
        if any(r.label == label for r in self.rows):
            label = str(len(self.rows))
        new_row = TwoDARow(label=label, data=new_data)
        self.rows.append(new_row)
        return len(self.rows) - 1

    def modify_row(self, row_index, changes: Dict[str, str]) -> bool:
        """
        Modify specific cells in an existing row (TSLPatcher ModifyRow).
        Adds any missing columns automatically.

        Args:
            row_index: int index OR string label of the row to modify.
            changes: dict of {column: value} pairs to update.
        """
        self._save_state()
        # Support both integer index and string label
        if isinstance(row_index, str):
            idx = next((i for i, r in enumerate(self.rows) if r.label == row_index), None)
            if idx is None:
                return False
        else:
            idx = int(row_index)
            if not (0 <= idx < len(self.rows)):
                return False
        # Add any new columns that appear in changes
        for col in changes:
            if col not in self.columns:
                self.add_column(col)
        self.rows[idx].update_values(changes)
        return True

    def remove_row(self, label: str) -> bool:
        self._save_state()
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.label != label]
        return len(self.rows) < before

    def remove_row_by_index(self, index: int) -> bool:
        self._save_state()
        if 0 <= index < len(self.rows):
            self.rows.pop(index)
            return True
        return False

    def get_row(self, label: str) -> TwoDARow | None:
        return next((r for r in self.rows if r.label == label), None)

    def get_row_by_index(self, index: int) -> TwoDARow | None:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    def find_rows_by_column(self, column: str, value: str) -> List[TwoDARow]:
        return [r for r in self.rows if r.data.get(column) == value]

    def set_cell(self, label: str, column: str, value: str) -> bool:
        """Set a cell value by row label.  Saves undo state before modifying."""
        row = self.get_row(label)
        if row:
            self._save_state()   # Fix: must save before mutating
            row.data[column] = value
            return True
        return False

    def set_cell_by_index(self, row_index: int, column: str, value: str) -> bool:
        """Set a cell value by row index.  Saves undo state before modifying."""
        row = self.get_row_by_index(row_index)
        if row:
            self._save_state()   # Fix: must save before mutating
            if column not in self.columns:
                # add_column internally mutates self.columns and all rows;
                # the _save_state above already captured the pre-mutation state.
                self.columns.append(column)
                for r in self.rows:
                    r.data.setdefault(column, "****")
            row.data[column] = value
            return True
        return False

    # ── Column Operations ─────────────────────────────────────

    def add_column(self, name: str, default: str = "****"):
        """Add a new column (TSLPatcher ColumnAdd)."""
        if name not in self.columns:
            self._save_state()
            self.columns.append(name)
            for row in self.rows:
                row.data.setdefault(name, default)

    def rename_column(self, old_name: str, new_name: str) -> bool:
        if old_name not in self.columns or new_name in self.columns:
            return False
        idx = self.columns.index(old_name)
        self.columns[idx] = new_name
        for row in self.rows:
            if old_name in row.data:
                row.data[new_name] = row.data.pop(old_name)
        return True

    def remove_column(self, name: str) -> bool:
        if name not in self.columns:
            return False
        self.columns.remove(name)
        for row in self.rows:
            row.data.pop(name, None)
        return True

    # ── Search ────────────────────────────────────────────────

    def search(self, query: str) -> List[TwoDARow]:
        """Return rows whose label or any cell value contains *query* (case-insensitive).

        Results are LRU-cached (cachetools) so repeated UI queries after
        non-mutating calls are O(1).
        """
        q = query.lower()
        if self._search_cache is not None:
            hit = self._search_cache.get(q)
            if hit is not None:
                return hit
        result = [
            r for r in self.rows
            if q in r.label.lower() or any(q in v.lower() for v in r.data.values())
        ]
        if self._search_cache is not None:
            self._search_cache[q] = result
        return result

    def find_rows_where(self, column: str, value: str,
                        case_sensitive: bool = False) -> List[TwoDARow]:
        """Return all rows where *column* exactly equals *value*.

        More efficient than :meth:`search` when you know the column and
        exact value you're looking for.
        """
        if case_sensitive:
            return [r for r in self.rows if r.data.get(column) == value]
        v = value.lower()
        return [r for r in self.rows if r.data.get(column, "").lower() == v]

    # ── TSLPatcher Export ─────────────────────────────────────

    def export_changes_ini(self, original: "TwoDAFile") -> str:
        """
        Generate a changes.ini-style patch that transforms original → self.
        This is the TSLPatcher format used for mod distribution.
        """
        if len(self.rows) < len(original.rows):
            raise ValueError(
                "TSLPatcher 2DAList has no DeleteRow operation; export a replacement "
                "2DA or restore deleted rows."
            )
        for index, original_row in enumerate(original.rows):
            if self.rows[index].label != original_row.label:
                raise ValueError(
                    "TSLPatcher cannot safely express reordered or renamed existing "
                    f"row labels (first mismatch at row {index})."
                )

        filename = Path(self.filename).name
        section_prefix = re.sub(r"[^A-Za-z0-9_]", "_", Path(filename).stem)
        operations: list[str] = []
        sections: list[list[str]] = []

        new_columns = [col for col in self.columns if col not in original.columns]
        for operation_index, column in enumerate(new_columns):
            section = f"{section_prefix}_add_column_{operation_index}"
            operations.append(f"AddColumn{operation_index}={section}")
            body = [f"[{section}]", f"ColumnLabel={column}", "DefaultValue=****"]
            for row_index in range(len(original.rows)):
                value = self.rows[row_index].data.get(column, "****")
                if value != "****":
                    body.append(f"I{row_index}={value}")
            sections.append(body)

        change_index = 0
        for row_index, original_row in enumerate(original.rows):
            row = self.rows[row_index]
            diffs = [
                (column, row.data.get(column, "****"))
                for column in original.columns
                if row.data.get(column, "****")
                != original_row.data.get(column, "****")
            ]
            if not diffs:
                continue
            section = f"{section_prefix}_change_row_{change_index}"
            operations.append(f"ChangeRow{change_index}={section}")
            body = [f"[{section}]", f"RowIndex={row_index}"]
            body.extend(f"{column}={value}" for column, value in diffs)
            sections.append(body)
            change_index += 1

        add_index = 0
        for row in self.rows[len(original.rows):]:
            section = f"{section_prefix}_add_row_{add_index}"
            operations.append(f"AddRow{add_index}={section}")
            body = [f"[{section}]", f"RowLabel={row.label}"]
            body.extend(
                f"{column}={row.data.get(column, '****')}"
                for column in self.columns
                if row.data.get(column, "****") != "****"
            )
            sections.append(body)
            add_index += 1

        lines = ["[2DAList]", f"Table0={filename}", "", f"[{filename}]"]
        lines.extend(operations)
        for section in sections:
            lines.append("")
            lines.extend(section)
        return "\n".join(lines) + "\n"

    # ── Binary I/O ────────────────────────────────────────────

    def to_binary(self) -> bytes:
        """Serialise to the KotOR binary 2DA V2.b format.

        Layout matches xoreos-tools/src/aurora/2dafile.cpp writeBinary():
          '2DA V2.b\n'               9-byte header
          col0\tcol1\t...\t\x00      tab-sep column names, null-terminated
          uint32 LE                  row count
          lbl0\tlbl1\t...\t          tab-sep row labels (NO trailing null)
          uint16 LE * (rows*cols)    cell byte offsets into string table
                                     (0xFFFF = blank / '****')
          uint16 LE                  sentinel: total byte size of string data
          <string data>              null-terminated strings concatenated
        """
        buf = bytearray()

        # Header
        buf += b"2DA V2.b\n"

        # Column names: tab-separated, null-terminated
        buf += ("\t".join(self.columns) + "\t").encode("latin-1") + b"\x00"

        # Row count
        buf += struct.pack("<I", len(self.rows))

        # Row labels: tab-separated (no trailing null — matches xoreos format)
        for row in self.rows:
            buf += row.label.encode("latin-1", errors="replace") + b"\t"

        # Build deduplicated string table with interning
        string_table = bytearray()
        str_offsets: Dict[str, int] = {}

        def _intern(s: str) -> int:
            """Intern string into table; returns byte offset (0xFFFF = blank)."""
            if s == "****":
                return 0xFFFF
            if s not in str_offsets:
                off = len(string_table)
                str_offsets[s] = off
                string_table.extend(s.encode("latin-1", errors="replace") + b"\x00")
            return str_offsets[s]

        # Cell index array
        cell_array = bytearray()
        for row in self.rows:
            for col in self.columns:
                val = row.data.get(col, "****")
                cell_array += struct.pack("<H", _intern(val))

        buf += cell_array
        # Sentinel: total byte size of string data (matches xoreos writeBinary)
        buf += struct.pack("<H", len(string_table))
        buf += string_table

        return bytes(buf)

    def save_binary(self, file_path: Path | None = None):
        """Write a binary 2DA V2.b file."""
        target = file_path or self.file_path
        if not target:
            raise ValueError("No file path specified")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_binary())

    # ── PyKotor-compatible ergonomic accessors ────────────────

    def get_cell(self, row_index: int, column: str) -> str:
        """Return the cell value at *row_index* / *column*.

        Mirrors PyKotor's ``TwoDA.get_cell(row, col)`` contract:
        returns the empty string ``""`` for blank cells (stored as "****")
        and raises ``IndexError`` for an out-of-range *row_index*.

        >>> t = TwoDAFile(); t.columns = ["x"]; t.add_row("0", {"x": "5"})
        >>> t.get_cell(0, "x")
        '5'
        """
        row = self.get_row_by_index(row_index)
        if row is None:
            raise IndexError(f"Row index {row_index} out of range (len={len(self.rows)})")
        val = row.data.get(column, "****")
        return "" if val == "****" else val

    def label_max(self) -> int:
        """Return the number of rows.

        Mirrors PyKotor's ``TwoDA.label_max()`` which counts rows for
        auto-numbering purposes (next-row label = ``label_max()``).
        """
        return len(self.rows)

    def __iter__(self):
        """Iterate over TwoDARow objects.

        Mirrors PyKotor's iterable TwoDA: ``for row in twoda``.
        """
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __repr__(self):
        return (f"TwoDAFile({self.filename!r}, "
                f"{len(self.rows)} rows, {len(self.columns)} cols)")


# ── Helpers ────────────────────────────────────────────────────


def detect_2da(data: bytes) -> str:
    """Return a format tag for the given raw 2DA bytes.

    Mirrors PyKotor's ``detect_2da(data) -> ResourceType`` pattern,
    but returns a plain string tag since GhostScripter has no ResourceType enum.

    Returns:
        ``"binary"``  — KotOR binary 2DA V2.b
        ``"text"``    — KotOR text 2DA V2.0
        ``"unknown"`` — unrecognised data
    """
    if not data:
        return "unknown"
    if data[:9] == b"2DA V2.b\n":
        return "binary"
    try:
        head = data[:20].decode("utf-8", errors="strict").strip().upper()
    except UnicodeDecodeError:
        return "unknown"
    if head.startswith("2DA"):
        return "text"
    return "unknown"

def _split_2da_line(line: str) -> List[str]:
    """
    Split a 2DA data line respecting quoted strings.
    KotOR 2DA doesn't actually use quotes but we handle them defensively.
    """
    parts = []
    current = ""
    in_quote = False
    for ch in line.rstrip("\r\n"):
        if ch == '"':
            in_quote = not in_quote
        elif ch in (" ", "\t") and not in_quote:
            if current:
                parts.append(current)
                current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


# ── GlobalCat Manager ─────────────────────────────────────────

class GlobalCatManager:
    """Specialized manager for globalcat.2da."""

    def __init__(self, globalcat: TwoDAFile):
        self.globalcat = globalcat

    def _get_name_col(self) -> str:
        for candidate in ("Name", "name", "VarName", "Label"):
            if candidate in self.globalcat.columns:
                return candidate
        return self.globalcat.columns[0] if self.globalcat.columns else "Name"

    def variable_exists(self, var_name: str) -> bool:
        col = self._get_name_col()
        return any(r.data.get(col, "") == var_name for r in self.globalcat.rows)

    def add_variable(self, var_name: str, var_type: str = "Boolean") -> bool:
        if self.variable_exists(var_name):
            return False
        label = str(len(self.globalcat.rows))
        row_data = {col: "****" for col in self.globalcat.columns}
        name_col = self._get_name_col()
        row_data[name_col] = var_name
        for type_col in ("Type", "type", "VarType"):
            if type_col in self.globalcat.columns:
                row_data[type_col] = var_type
                break
        self.globalcat.add_row(label, row_data)
        return True

    def get_variables(self) -> List[Dict[str, str]]:
        name_col = self._get_name_col()
        return [
            {"label": r.label, "name": r.data.get(name_col, ""), "data": r.data}
            for r in self.globalcat.rows
        ]

    def export_ini_block(self) -> str:
        """Export globalcat.2da entries in TSLPatcher changes.ini format."""
        lines = [f"[globalcat.2da]"]
        for row in self.globalcat.rows:
            name_col = self._get_name_col()
            name = row.data.get(name_col, "****")
            cells = ", ".join(f"{col}={val}" for col, val in row.data.items())
            lines.append(f"AddRow {row.label}={cells}")
        return "\n".join(lines)
