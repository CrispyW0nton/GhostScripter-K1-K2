"""
GhostScripter-K1-K2 — 2DA File Manager
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class TwoDARow:
    label: str
    data: Dict[str, str] = field(default_factory=dict)

    def get(self, column: str, default: str = "****") -> str:
        return self.data.get(column, default)


class TwoDAFile:
    """Parse, edit, and write a 2DA file."""

    def __init__(self, filename: str = ""):
        self.filename = filename
        self.file_path: Optional[Path] = None
        self.rows: List[TwoDARow] = []
        self.columns: List[str] = []

    # ── I/O ──────────────────────────────────────────────────

    @classmethod
    def from_file(cls, file_path: Path) -> "TwoDAFile":
        obj = cls(file_path.name)
        obj.file_path = file_path

        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if not lines:
            return obj

        # Find the 2DA header line
        header_idx = next(
            (i for i, l in enumerate(lines) if l.strip().startswith("2DA")), 0
        )

        # Column header line is 2 lines after header (skip blank)
        col_idx = header_idx + 2
        if col_idx < len(lines):
            obj.columns = lines[col_idx].split()

        # Rows start 2 lines after column headers
        for line in lines[col_idx + 1:]:
            parts = line.split()
            if not parts:
                continue
            label = parts[0]
            # Map values to columns
            values = parts[1:]
            row_data = {}
            for i, col in enumerate(obj.columns):
                row_data[col] = values[i] if i < len(values) else "****"
            obj.rows.append(TwoDARow(label=label, data=row_data))

        return obj

    @classmethod
    def from_text(cls, text: str, filename: str = "unnamed.2da") -> "TwoDAFile":
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".2da",
                                         delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        obj = cls.from_file(Path(tmp_path))
        obj.filename = filename
        obj.file_path = None
        os.unlink(tmp_path)
        return obj

    def to_text(self) -> str:
        lines = ["2DA V2.0\n", "\n"]
        lines.append("    " + "    ".join(self.columns) + "\n")
        for row in self.rows:
            parts = [row.label]
            for col in self.columns:
                parts.append(row.data.get(col, "****"))
            lines.append("    ".join(parts) + "\n")
        return "".join(lines)

    def save(self, file_path: Optional[Path] = None):
        target = file_path or self.file_path
        if not target:
            raise ValueError("No file path specified")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(self.to_text())

    # ── Row Operations ────────────────────────────────────────

    def add_row(self, label: str, data: Dict[str, str]) -> int:
        row = TwoDARow(label=label, data=data)
        self.rows.append(row)
        return len(self.rows) - 1

    def remove_row(self, label: str) -> bool:
        before = len(self.rows)
        self.rows = [r for r in self.rows if r.label != label]
        return len(self.rows) < before

    def get_row(self, label: str) -> Optional[TwoDARow]:
        return next((r for r in self.rows if r.label == label), None)

    def get_row_by_index(self, index: int) -> Optional[TwoDARow]:
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return None

    def find_rows_by_column(self, column: str, value: str) -> List[TwoDARow]:
        return [r for r in self.rows if r.data.get(column) == value]

    def set_cell(self, label: str, column: str, value: str) -> bool:
        row = self.get_row(label)
        if row:
            row.data[column] = value
            return True
        return False

    # ── Column Operations ─────────────────────────────────────

    def add_column(self, name: str, default: str = "****"):
        if name not in self.columns:
            self.columns.append(name)
            for row in self.rows:
                row.data.setdefault(name, default)

    # ── Search ────────────────────────────────────────────────

    def search(self, query: str) -> List[TwoDARow]:
        q = query.lower()
        return [
            r for r in self.rows
            if q in r.label.lower() or any(q in v.lower() for v in r.data.values())
        ]

    def __len__(self):
        return len(self.rows)

    def __repr__(self):
        return f"TwoDAFile({self.filename!r}, {len(self.rows)} rows, {len(self.columns)} cols)"


# ── GlobalCat Manager ─────────────────────────────────────────

class GlobalCatManager:
    """Specialized manager for globalcat.2da."""

    def __init__(self, globalcat: TwoDAFile):
        self.globalcat = globalcat

    def _get_name_col(self) -> str:
        """Detect the variable name column."""
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
        # Try common type column names
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
