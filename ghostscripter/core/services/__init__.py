"""
GhostScripter — Core Services Layer
=====================================
Domain services that provide high-level, cohesive operations to consumers
(MCP tools, UI widgets, IPC handlers) without exposing implementation details.

Coupling model applied  (Khononov, "Balancing Coupling in Software Design")
---------------------------------------------------------------------------
  Layer distance   : MEDIUM  (UI / MCP → services → readers/writers)
  Integration str  : FUNCTIONAL within each service (same business slice)
                     CONTRACT  between services and callers
  Volatility       : MEDIUM for format details, LOW for service interface

  ∴ Balance = (FUNCTIONAL XOR LOW-distance within service) = HIGH COHESION ✓
              (CONTRACT XOR MEDIUM-distance to callers)   = LOOSE COUPLING ✓

Design principles applied
-------------------------
  • Vertical Slice Architecture: each service handles one complete domain slice
    (Dialogue, TwoDA, Journal) rather than being a horizontal "reader" or "writer"
  • Deep Modules: large hidden complexity (binary parsing, GFF field dispatch,
    row-label lookup) behind a small, stable public surface
  • Information Hiding: callers never see GFF structs, binary offsets, or
    field-type IDs — only domain objects and Python dicts
  • Aggregate Pattern: each service is the single place where its domain
    objects are both loaded *and* saved, keeping distance low for
    functional coupling between read/write operations
  • Dependency Inversion: services accept ResourceReaderPort, not
    ResourceManager directly, so tests can inject fakes
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger(__name__)


# ─── Dialogue Service ─────────────────────────────────────────────────────────

class DialogueService:
    """
    Single entry-point for all dialogue (DLG) operations.

    Hides: binary GFF parsing, field name mapping, branch reconstruction,
           text strref resolution, K1 vs K2 field differences.
    Exposes: load by resref, export to binary, convert to JSON-safe dict.
    """

    FIDELITY_SCHEMA = "ghostscripter.dlg.source-gff.v1"

    def __init__(self, resource_reader=None):
        """
        Parameters
        ----------
        resource_reader : ResourceReaderPort-compatible object, optional
            Injected at construction so callers and tests can substitute
            any implementation.  If None, operations requiring game data
            will raise ValueError.
        """
        self._rm = resource_reader

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, resref: str) -> Any:
        """
        Load a dialogue by resref from the injected resource reader.

        Returns a DialogueFile domain object.

        Raises
        ------
        FileNotFoundError  — if the DLG resource is not present
        ValueError         — if no resource reader was injected
        """
        if self._rm is None:
            raise ValueError("DialogueService requires a resource reader; "
                             "pass one at construction.")
        raw = self._rm.read(f"{resref.lower()}.dlg")
        if raw is None:
            raise FileNotFoundError(f"DLG not found: {resref}")
        return self.parse_bytes(raw)

    @staticmethod
    def parse_bytes(data: bytes) -> Any:
        """Parse raw DLG binary bytes → DialogueFile."""
        from ghostscripter.core.export import DLGImporter
        return DLGImporter().import_from_bytes(data)

    # ── Export ───────────────────────────────────────────────────────────────

    @staticmethod
    def to_binary(dialogue: Any, target_game: str = "K1") -> bytes:
        """Serialise a DialogueFile → GFF V3.2 binary bytes."""
        from ghostscripter.core.export.dlg_writer import DLGExporter
        return DLGExporter().export(dialogue, target_game)

    @staticmethod
    def to_binary_b64(dialogue: Any, target_game: str = "K1") -> str:
        """Return base64-encoded binary DLG (for JSON transport)."""
        return base64.b64encode(
            DialogueService.to_binary(dialogue, target_game)
        ).decode("ascii")

    # ── DTO conversion ────────────────────────────────────────────────────────

    @staticmethod
    def node_to_dict(node: Any, is_reply: bool,
                     include_branches: bool = True) -> Dict[str, Any]:
        """
        Convert a DialogueNode to a JSON-safe dict (Data Transfer Object).

        This is the boundary representation used by the MCP layer and
        external callers.  Internal field names (e.g. text_strref) are
        mapped to the stable public contract names.
        """
        d: Dict[str, Any] = {
            "text": node.text,
            "strref": node.text_strref,
        }
        if not is_reply:
            d["speaker"] = node.speaker
        else:
            d["listener"] = getattr(node, "listener", "")
        if node.script1:
            d["script1"] = node.script1
        if node.script2:
            d["script2"] = node.script2
        if getattr(node, "vo_resref", ""):
            d["vo_resref"] = node.vo_resref
        if getattr(node, "sound", ""):
            d["sound"] = node.sound
        if include_branches and node.branches:
            d["branches"] = [
                {
                    "index": b.target_node_id,
                    # ``is_reply`` is retained for the original public
                    # contract; ``is_child`` is the accurate DLG field name.
                    "is_reply": b.is_child,
                    "is_child": b.is_child,
                    "active_script": b.active_script,
                    "active_script2": b.active_script2,
                    "link_comment": b.link_comment,
                    "display_inactive": b.display_inactive,
                }
                for b in node.branches
            ]
        return d

    @staticmethod
    def to_dict(dialogue: Any, include_branches: bool = True,
                include_fidelity: bool = True) -> Dict[str, Any]:
        """Return a JSON-safe dialogue DTO.

        Imported DLGs include a clearly named ``source_fidelity`` capsule by
        default.  The capsule carries the original binary so a public
        ``readDLG`` response can be passed back to ``writeDLG`` without losing
        StuntList, localized variants, root metadata, or conditional fields
        that are intentionally not flattened into this compact DTO.
        """
        result: Dict[str, Any] = {
            "entry_count": len(dialogue.entries),
            "reply_count": len(dialogue.replies),
            "starters": [
                {
                    "index": s.target_node_id,
                    "is_reply": s.is_child,
                    "is_child": s.is_child,
                    "active_script": s.active_script,
                    "active_script2": s.active_script2,
                    "link_comment": s.link_comment,
                    "display_inactive": s.display_inactive,
                }
                for s in dialogue.starters
            ],
            "entries": [
                DialogueService.node_to_dict(e, False, include_branches)
                for e in dialogue.entries
            ],
            "replies": [
                DialogueService.node_to_dict(r, True, include_branches)
                for r in dialogue.replies
            ],
            "skippable": dialogue.skippable,
            "delay_entry": dialogue.delay_entry,
            "delay_reply": dialogue.delay_reply,
            "ambient_track": dialogue.ambient_track,
            "animated_cut": dialogue.animated_cut,
            "camera_model": dialogue.camera_model,
            "conversation_type": dialogue.conversation_type,
            "computer_type": dialogue.computer_type,
            "old_hit_check": dialogue.old_hit_check,
            "unequip_items": dialogue.unequip_items,
            "unequip_h_item": dialogue.unequip_h_item,
            "word_count": dialogue.word_count,
        }
        if dialogue.on_end:
            result["end_script"] = dialogue.on_end
        if dialogue.on_abort:
            result["abort_script"] = dialogue.on_abort

        if include_fidelity:
            source_bytes = getattr(dialogue, "_source_bytes", None)
            if source_bytes is None and getattr(dialogue, "_raw_gff", None) is not None:
                try:
                    from pykotor.resource.formats.gff import bytes_gff  # type: ignore
                    source_bytes = bytes_gff(dialogue._raw_gff)
                except Exception:
                    source_bytes = None
            if source_bytes is not None:
                result["source_fidelity"] = {
                    "schema": DialogueService.FIDELITY_SCHEMA,
                    "required_for_lossless_save": True,
                    "source_game": getattr(dialogue, "source_game", None),
                    "binary_base64": base64.b64encode(source_bytes).decode("ascii"),
                }
        return result

    # ── Builder (dict → model) ────────────────────────────────────────────────

    @staticmethod
    def from_dict(dlg_dict: Dict[str, Any]) -> Any:
        """
        Build a DialogueFile from the dict format produced by to_dict().

        This is the inverse of to_dict() — used by writeDLG in the MCP layer.
        Centralises the mapping so the MCP handler stays thin.
        """
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch,
        )

        fidelity_present = "source_fidelity" in dlg_dict
        if fidelity_present:
            from ghostscripter.core.export.dlg_reader import DLGImporter
            from ghostscripter.core.export.dlg_writer import DLGFidelityError

            fidelity = dlg_dict.get("source_fidelity")
            if not isinstance(fidelity, dict):
                raise DLGFidelityError(
                    "Imported dialogue DTO is fidelity-sensitive, but "
                    "'source_fidelity' is not an object. No file was written."
                )
            if fidelity.get("schema") != DialogueService.FIDELITY_SCHEMA:
                raise DLGFidelityError(
                    "Imported dialogue DTO uses an unknown source_fidelity "
                    f"schema {fidelity.get('schema')!r}. No file was written."
                )
            encoded = fidelity.get("binary_base64")
            if not isinstance(encoded, str) or not encoded:
                raise DLGFidelityError(
                    "Imported dialogue DTO requires its source_fidelity "
                    "binary_base64 payload for a lossless save. No file was written."
                )
            try:
                source = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise DLGFidelityError(
                    "Imported dialogue DTO has an invalid source_fidelity "
                    f"base64 payload ({exc}). No file was written."
                ) from exc
            if not source.startswith(b"DLG V3.2"):
                raise DLGFidelityError(
                    "source_fidelity payload is not a KotOR DLG V3.2 file. "
                    "No file was written."
                )
            dlg = DLGImporter().import_from_bytes(source)
        else:
            # Normal authoring DTO: no source tree is needed or expected.
            dlg = DialogueFile()

        if "end_script" in dlg_dict:
            dlg.on_end = str(dlg_dict.get("end_script") or "")
        if "abort_script" in dlg_dict:
            dlg.on_abort = str(dlg_dict.get("abort_script") or "")

        root_fields = {
            "skippable": ("skippable", bool),
            "delay_entry": ("delay_entry", int),
            "delay_reply": ("delay_reply", int),
            "ambient_track": ("ambient_track", str),
            "animated_cut": ("animated_cut", bool),
            "camera_model": ("camera_model", str),
            "conversation_type": ("conversation_type", int),
            "computer_type": ("computer_type", int),
            "old_hit_check": ("old_hit_check", bool),
            "unequip_items": ("unequip_items", bool),
            "unequip_h_item": ("unequip_h_item", bool),
            "word_count": ("word_count", int),
        }
        for dto_key, (attr, converter) in root_fields.items():
            if dto_key in dlg_dict:
                setattr(dlg, attr, converter(dlg_dict[dto_key]))

        def _branch(d: dict, existing: DialogueBranch | None = None,
                    default_index: int = -1) -> DialogueBranch:
            if not isinstance(d, dict):
                raise ValueError("Each dialogue branch must be a JSON object.")
            br = existing or DialogueBranch()
            if "index" in d:
                br.target_node_id = int(d["index"])
            elif existing is None:
                br.target_node_id = default_index
            if "is_child" in d:
                br.is_child = bool(d["is_child"])
            elif "is_reply" in d:
                br.is_child = bool(d["is_reply"])
            if "active_script" in d:
                br.active_script = str(d["active_script"] or "")
            if "active_script2" in d:
                br.active_script2 = str(d["active_script2"] or "")
            if "link_comment" in d:
                br.link_comment = str(d["link_comment"] or "")
            if "display_inactive" in d:
                br.display_inactive = bool(d["display_inactive"])
            return br

        def _node(d: dict, node_type: str, node_id: int,
                  existing: DialogueNode | None = None) -> DialogueNode:
            if not isinstance(d, dict):
                raise ValueError("Each dialogue node must be a JSON object.")
            n = existing or DialogueNode(node_id=node_id, node_type=node_type)
            n.node_id = node_id
            n.node_type = node_type
            mappings = {
                "text": ("text", str),
                "strref": ("text_strref", int),
                "speaker": ("speaker", str),
                "listener": ("listener", str),
                "script1": ("script1", str),
                "script2": ("script2", str),
                "vo_resref": ("vo_resref", str),
                "sound": ("sound", str),
            }
            for dto_key, (attr, converter) in mappings.items():
                if dto_key in d:
                    raw_value = d[dto_key]
                    setattr(
                        n, attr,
                        converter(raw_value or "")
                        if converter is str else converter(raw_value),
                    )
            if "branches" in d:
                branch_data = d.get("branches")
                if not isinstance(branch_data, list):
                    raise ValueError("Dialogue node 'branches' must be an array.")
                originals = list(n.branches)
                n.branches = [
                    _branch(
                        branch_d,
                        originals[i] if i < len(originals) else None,
                    )
                    for i, branch_d in enumerate(branch_data)
                ]
                for i, branch in enumerate(n.branches):
                    branch.branch_id = i
            return n

        def _nodes(dto_key: str, node_type: str,
                   originals: List[DialogueNode]) -> List[DialogueNode]:
            if dto_key not in dlg_dict:
                return originals if fidelity_present else []
            items = dlg_dict.get(dto_key)
            if not isinstance(items, list):
                raise ValueError(f"Dialogue '{dto_key}' must be an array.")
            return [
                _node(
                    item, node_type, i,
                    originals[i] if i < len(originals) else None,
                )
                for i, item in enumerate(items)
            ]

        dlg.entries = _nodes("entries", "entry", list(dlg.entries))
        dlg.replies = _nodes("replies", "reply", list(dlg.replies))

        if "starters" in dlg_dict:
            starter_data = dlg_dict.get("starters")
            if not isinstance(starter_data, list):
                raise ValueError("Dialogue 'starters' must be an array.")
            originals = list(dlg.starters)
            dlg.starters = [
                _branch(
                    item,
                    originals[i] if i < len(originals) else None,
                    default_index=0,
                )
                for i, item in enumerate(starter_data)
            ]
            for i, branch in enumerate(dlg.starters):
                branch.branch_id = i
        elif not fidelity_present:
            dlg.starters = []

        return dlg


# ─── TwoDA Service ─────────────────────────────────────────────────────────────

class TwoDAService:
    """
    Single entry-point for all 2DA table operations.

    Hides: binary vs text format detection, offset arithmetic, string-table
           internment, sentinel handling.
    Exposes: load by resref, row/cell lookup, filtered iteration,
             TSLPatcher patch generation, pagination.
    """

    def __init__(self, resource_reader=None):
        self._rm = resource_reader

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, resref: str) -> Any:
        """Load a 2DA by resref.  Returns a TwoDAFile domain object."""
        if self._rm is None:
            raise ValueError("TwoDAService requires a resource reader.")
        raw = self._rm.read(f"{resref.lower()}.2da")
        if raw is None:
            raise FileNotFoundError(f"2DA not found: {resref}")
        return self.parse_bytes(raw, resref)

    @staticmethod
    def parse_bytes(data: bytes, name: str = "") -> Any:
        """Auto-detect format and parse 2DA bytes → TwoDAFile."""
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        return TwoDAFile.from_bytes(data, f"{name}.2da" if name else "")

    @staticmethod
    def parse_text(text: str) -> Any:
        """Parse a V2.0 text 2DA string → TwoDAFile."""
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        return TwoDAFile.from_text(text)

    # ── Lookup ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_cell(tda: Any, row: int | str, column: str) -> str | None:
        """
        Return a single cell value.

        Parameters
        ----------
        row    : int (index), str of a digit ("0","1",...) for index lookup,
                 OR a string label value to search in the 'label' column
                 (i.e. row.data.get('label')), which is how KotOR 2DA files
                 identify rows semantically.
        column : column name

        Returns None if either the row or column doesn't exist.

        Note on KotOR 2DA row identity
        --------------------------------
        TwoDARow.label is the *row index* as a string ("0", "1", ...).
        The human-readable label (e.g. "Scoundrel", "Human") lives in
        row.data["label"] — the first data column.  This method searches
        the "label" data column when a non-numeric string is given.
        """
        target = None
        if isinstance(row, int) or (isinstance(row, str) and str(row).isdigit()):
            idx = int(row)
            if 0 <= idx < len(tda.rows):
                target = tda.rows[idx]
        else:
            # Search by the 'label' data column (KotOR semantic row name)
            row_lower = str(row).lower()
            for r in tda.rows:
                # Try data["label"] column first (standard KotOR 2DA)
                label_col = r.data.get("label", r.data.get("Label", ""))
                if label_col.lower() == row_lower:
                    target = r
                    break
        if target is None or column not in target.data:
            return None
        return target.data[column]

    @staticmethod
    def rows_to_dicts(tda: Any,
                      columns: list[str] | None = None,
                      query: str = "",
                      row_query: str = "",
                      limit: int = 100,
                      offset: int = 0) -> Dict[str, Any]:
        """
        Return a paginated, optionally filtered JSON-safe summary of rows.

        This is the DTO conversion for the MCP readTwoDA tool.
        ``query`` and ``row_query`` are aliases — ``query`` takes precedence.
        """
        cols = columns if columns else tda.columns
        cols = [c for c in cols if c in tda.columns]

        effective_query = query or row_query
        rows = tda.rows
        if effective_query:
            q = effective_query.lower()
            rows = [r for r in rows if any(
                q in str(v).lower() for v in r.data.values()
            )]

        total = len(rows)
        page = rows[offset: offset + limit]

        result_rows = []
        for r in page:
            row_data: Dict[str, Any] = {"__label": r.label}
            for c in cols:
                row_data[c] = r.data.get(c, "****")
            result_rows.append(row_data)

        return {
            "columns": cols,
            "total_rows": total,
            "offset": offset,
            "returned": len(result_rows),
            "rows": result_rows,
        }

    # ── Patch generation ──────────────────────────────────────────────────────

    @staticmethod
    def diff_to_ini(original: Any, modified: Any) -> str:
        """
        Return a TSLPatcher changes.ini section string describing the diff.

        This is the Aggregate method — it needs both the original and
        modified TwoDAFile objects, so they are kept physically close here.
        """
        return modified.export_changes_ini(original)

    # ── Serialisation ─────────────────────────────────────────────────────────

    @staticmethod
    def to_text(tda: Any) -> str:
        """Serialise a TwoDAFile to V2.0 text format."""
        return tda.to_text()

    @staticmethod
    def to_binary(tda: Any) -> bytes:
        """Serialise a TwoDAFile to V2.b binary format."""
        return tda.to_binary()

    @staticmethod
    def set_cell(tda: Any, row: int, column: str, value: str) -> None:
        """Set a single cell value in a TwoDAFile by row index and column name."""
        if 0 <= row < len(tda.rows):
            tda.rows[row].data[column] = value

    @staticmethod
    def build_from_dicts(resref: str, columns: List[str],
                          rows: List[Dict[str, str]]) -> Any:
        """
        Build a new TwoDAFile from a list of column names and row dicts.

        Each row dict must have a 'label' key (the row's index label) plus
        one key per column.  Missing values default to '****' (KotOR empty).
        """
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile, TwoDARow

        tda = TwoDAFile.__new__(TwoDAFile)
        tda.filename     = f"{resref}.2da"
        tda.columns      = list(columns)
        tda.rows         = []
        tda._undo_stack  = []
        tda._redo_stack  = []

        for r in rows:
            label    = str(r.get("label", ""))
            row_data = {col: str(r.get(col, "****")) for col in columns}
            tda.rows.append(TwoDARow(label=label, data=row_data))

        return tda


# ─── Journal Service ───────────────────────────────────────────────────────────

class JournalService:
    """
    Single entry-point for all journal (JRL) operations.

    Hides: GFF field parsing, CEXOLOCSTRING handling, category/entry ID
           assignment, binary serialisation.
    Exposes: load by resref, filter by category tag, export to binary,
             convert to JSON-safe summary.
    """

    def __init__(self, resource_reader=None):
        self._rm = resource_reader

    def load(self, resref: str = "global") -> Any:
        """Load the journal by resref.  Returns a JournalFile domain object."""
        if self._rm is None:
            raise ValueError("JournalService requires a resource reader.")
        raw = self._rm.read(f"{resref.lower()}.jrl")
        if raw is None:
            raise FileNotFoundError(f"JRL not found: {resref}")
        return self.parse_bytes(raw)

    @staticmethod
    def parse_bytes(data: bytes) -> Any:
        """Parse raw JRL binary bytes → JournalFile."""
        from ghostscripter.core.export import JRLImporter
        return JRLImporter().import_from_bytes(data)

    @staticmethod
    def to_dict(journal: Any,
                category_filter: str = "") -> Dict[str, Any]:
        """
        Return a JSON-safe dict summarising all quest categories.

        Optionally filter by a case-insensitive substring of the category tag.
        """
        cats = []
        for cat in journal.categories:
            if category_filter and category_filter.lower() not in cat.tag.lower():
                continue
            cats.append({
                "tag": cat.tag,
                "name": cat.name,
                "priority": cat.priority,
                "entries": [
                    {
                        "state_id": e.state_id,
                        "text": e.text[:120] if e.text else "",
                        "is_end": e.is_end,
                        "is_quest_entry": e.is_quest_entry,
                    }
                    for e in cat.entries
                ],
            })
        return {"category_count": len(cats), "categories": cats}


# ─── GFF Service ──────────────────────────────────────────────────────────────

class GFFService:
    """
    Thin service layer for generic GFF parsing and writing.

    "Generic" here means any GFF-based file that the caller wants to
    inspect as a raw dict (ARE, UTC, UTP, GIT, …) rather than via a
    higher-level domain model.
    """

    def __init__(self, resource_reader=None):
        self._rm = resource_reader

    def load(self, resref: str, restype: str) -> Dict[str, Any]:
        """Parse a GFF resource and return its field dict."""
        if self._rm is None:
            raise ValueError("GFFService requires a resource reader.")
        raw = self._rm.read(f"{resref.lower()}.{restype.lower()}")
        if raw is None:
            raise FileNotFoundError(f"{resref}.{restype} not found")
        return self.parse_bytes(raw)

    @staticmethod
    def parse_bytes(data: bytes) -> Dict[str, Any]:
        """Parse raw GFF bytes → convenient, untyped field dict.

        This representation is for read-only domain consumers.  It does not
        retain enough type information for a safe generic write; MCP
        round-tripping uses :meth:`parse_typed_bytes` instead.
        """
        from ghostscripter.core.export import GFF3Reader
        return GFF3Reader(data).parse()

    @staticmethod
    def parse_typed_bytes(
        data: bytes,
        *,
        max_depth: int | None = None,
    ) -> Dict[str, Any]:
        """Parse raw GFF bytes into the lossless typed JSON schema."""
        from ghostscripter.core.gff_codec import read_typed_gff
        return read_typed_gff(data, max_depth=max_depth)

    @staticmethod
    def write_typed(document: Dict[str, Any]) -> bytes:
        """Write a complete typed GFF document without inferring types."""
        from ghostscripter.core.gff_codec import write_typed_gff
        return write_typed_gff(document)

    @staticmethod
    def write(
        file_type: str,
        fields: Dict[str, Any],
        *,
        allow_lossy: bool = False,
    ) -> bytes:
        """
        Build a GFF binary from an ambiguous legacy field dict.

        This compatibility path necessarily guesses types (``int`` becomes
        ``UInt32``, for example) and must therefore be explicitly opted into.
        New code should use :meth:`write_typed` with the schema returned by
        :meth:`parse_typed_bytes`.
        """
        if not allow_lossy:
            raise ValueError(
                "untyped GFF fields are ambiguous; use the typed document from "
                "readGFF, or explicitly set allow_lossy=True for a new legacy file"
            )
        from ghostscripter.core.export import GFF3Writer, GFFStruct
        import math

        if not isinstance(fields, dict):
            raise ValueError("legacy GFF fields must be a dictionary")

        w = GFF3Writer(file_type.ljust(4)[:4])

        def _add(node: Any, d: dict, path: str = "root") -> None:
            for key, val in d.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} field labels must be strings")
                if key.startswith("__"):
                    continue
                try:
                    label_bytes = key.encode("ascii", errors="strict")
                except UnicodeEncodeError as exc:
                    raise ValueError(f"{path}.{key} label must be ASCII") from exc
                if len(label_bytes) > 16:
                    raise ValueError(
                        f"{path}.{key} label exceeds GFF's 16-byte limit"
                    )
                if isinstance(val, str):
                    try:
                        val.encode("cp1252", errors="strict")
                    except UnicodeEncodeError as exc:
                        raise ValueError(
                            f"{path}.{key} cannot be represented in KotOR's cp1252 encoding"
                        ) from exc
                    node.add_cexo(key, val)
                elif isinstance(val, bool):
                    node.add_byte(key, int(val))
                elif isinstance(val, int):
                    if not 0 <= val <= 0xFFFFFFFF:
                        raise ValueError(
                            f"{path}.{key} is outside the inferred UInt32 range; "
                            "use a typed document for signed/64-bit fields"
                        )
                    node.add_dword(key, val)
                elif isinstance(val, float):
                    if not math.isfinite(val):
                        raise ValueError(f"{path}.{key} must be a finite float")
                    node.add_float(key, val)
                elif isinstance(val, dict):
                    s = GFFStruct()
                    _add(s, val, f"{path}.{key}")
                    node.add_struct(key, s)
                elif isinstance(val, list):
                    structs = []
                    for index, item in enumerate(val):
                        if not isinstance(item, dict):
                            raise ValueError(
                                f"{path}.{key}[{index}] must be a struct object; "
                                "legacy GFF lists cannot contain scalar values"
                            )
                        s = GFFStruct()
                        _add(s, item, f"{path}.{key}[{index}]")
                        structs.append(s)
                    node.add_list(key, structs)
                else:
                    raise ValueError(
                        f"{path}.{key} uses unsupported legacy value type "
                        f"{type(val).__name__}; use a typed document"
                    )

        _add(w.root, fields)
        return w.build()


# ─── TLK Service ──────────────────────────────────────────────────────────────

class TLKService:
    """
    Single entry-point for all TLK (talk table) operations.

    Coupling model
    --------------
      This service owns the «TLK» vertical slice.  It hides:
        • Binary struct parsing (header, 40-byte entry descriptors, string block)
        • Codepage detection (cp1252 for Western, cp949/950/936/932 for CJK)
        • Strref-to-text resolution

      Callers (MCP readTLK, UI dialogue editor) depend ONLY on this service,
      never on TLKFile directly — fulfilling Contract Coupling at medium distance.

    Design: Deep Module + Dependency Inversion
      The resource_reader parameter follows the ResourceReaderPort contract so
      tests can inject a fake without loading game data.
    """

    def __init__(self, resource_reader=None) -> None:
        self._rm = resource_reader

    # ── Loading ──────────────────────────────────────────────────────────────

    def load(self, resref: str = "dialog") -> Any:
        """Load a TLK by resref (default: 'dialog' → dialog.tlk)."""
        if self._rm is None:
            raise ValueError("TLKService requires a resource reader.")
        name = f"{resref.lower()}.tlk"
        raw = self._rm.read(name)
        if raw is None:
            raise FileNotFoundError(f"TLK not found: {name}")
        return self.parse_bytes(raw, name)

    @staticmethod
    def parse_bytes(data: bytes, filename: str = "") -> Any:
        """Parse raw TLK binary bytes → TLKFile domain object."""
        from ghostscripter.core.models.tlk import TLKFile
        return TLKFile.from_bytes(data, filename)

    # ── Lookup ───────────────────────────────────────────────────────────────

    @staticmethod
    def lookup(tlk: Any, strrefs: List[int]) -> List[Dict[str, Any]]:
        """
        Return a list of dicts for the given strrefs.

        Each dict has keys: strref, text, sound_resref, flags.
        Out-of-range strrefs produce {"strref": N, "error": "out of range"}.
        """
        results: List[Dict[str, Any]] = []
        for strref in strrefs:
            if 0 <= strref < len(tlk.entries):
                entry = tlk.entries[strref]
                results.append({
                    "strref": strref,
                    "text": entry.text,
                    "sound_resref": entry.sound_resref,
                    "flags": entry.flags,
                })
            else:
                results.append({"strref": strref, "error": "out of range"})
        return results

    @staticmethod
    def summary(tlk: Any) -> Dict[str, Any]:
        """Return a JSON-safe summary dict for describeResource."""
        from ghostscripter.core.models.tlk import LANGUAGE_IDS
        samples: List[Dict[str, Any]] = []
        for i, entry in enumerate(tlk.entries[:50]):
            if entry.text.strip():
                samples.append({"strref": i, "text": entry.text[:80]})
                if len(samples) >= 3:
                    break
        return {
            "type": "TLK",
            "entry_count": len(tlk.entries),
            "language_id": tlk.language_id,
            "language_name": LANGUAGE_IDS.get(tlk.language_id, "Unknown"),
            "sample_entries": samples,
        }

    @staticmethod
    def search(tlk: Any, query: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Return up to *limit* entries whose text contains *query*."""
        q = query.lower()
        results: List[Dict[str, Any]] = []
        for i, entry in enumerate(tlk.entries):
            if q in entry.text.lower():
                results.append({
                    "strref": i,
                    "text": entry.text[:200],
                    "sound_resref": entry.sound_resref,
                })
                if len(results) >= limit:
                    break
        return results


# ─── NWScript Service ─────────────────────────────────────────────────────────

class NWScriptService:
    """
    Single entry-point for all NWScript database operations.

    Coupling model
    --------------
      This service owns the «NWScript» vertical slice.  It hides:
        • NWScript.nss binary/text parsing (field-prefix disambiguation between
          K1 and K2 function names)
        • Case-insensitive search caching
        • Category grouping
        • Signature + call-snippet formatting

      Callers depend ONLY on this service's stable interface, never on
      NWScriptDB internals — fulfilling Contract Coupling at medium-high distance.

    Design: Deep Module + Singleton cache (via NWScriptDB.load)
      NWScriptDB.load() is already a cached factory; this service exposes it
      through a clean DTO boundary so callers receive plain dicts, not domain
      objects with internal implementation details.
    """

    @staticmethod
    def load(game_id: str) -> Any:
        """Return the cached NWScriptDB for *game_id* ('K1' or 'K2')."""
        from ghostscripter.core.nwscript.parser import NWScriptDB
        return NWScriptDB.load(game_id)

    @staticmethod
    def search(db: Any, query: str, kind: str = "functions",
               category_filter: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search functions and/or constants in the database.

        Parameters
        ----------
        db             : NWScriptDB instance (from load())
        query          : substring to search for (case-insensitive)
        kind           : 'functions', 'constants', or 'all'
        category_filter: optional category substring filter
        limit          : maximum total results to return

        Returns a list of result dicts with a 'kind' discriminator field.
        """
        results: List[Dict[str, Any]] = []

        if kind in ("functions", "all"):
            funcs = db.search_functions(query)
            if category_filter:
                funcs = [f for f in funcs
                         if category_filter.lower() in f.category.lower()]
            for f in funcs[:limit]:
                results.append({
                    "kind": "function",
                    "name": f.name,
                    "signature": f.signature,
                    "return_type": f.return_type,
                    "category": f.category,
                    "param_count": len(f.params),
                })

        if kind in ("constants", "all"):
            consts = db.search_constants(query)
            if category_filter:
                consts = [c for c in consts
                          if category_filter.lower() in c.category.lower()]
            remaining = limit - len(results)
            for c in consts[:remaining]:
                results.append({
                    "kind": "constant",
                    "name": c.name,
                    "type": c.type,
                    "value": c.value,
                    "category": c.category,
                })

        return results

    @staticmethod
    def signature(db: Any, func_name: str) -> dict[str, Any] | None:
        """
        Return a full signature dict for *func_name*, or None if not found.

        The returned dict is the stable DTO consumed by the MCP
        nwscriptSignature tool.
        """
        func = db.get_function(func_name)
        if func is None:
            return None
        return {
            "name": func.name,
            "return_type": func.return_type,
            "signature": func.signature,
            "call_snippet": func.call_snippet,
            "category": func.category,
            "line_number": func.line_number,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default": p.default,
                    "is_optional": p.default is not None,
                }
                for p in func.params
            ],
        }

    @staticmethod
    def categories(db: Any, kind: str = "functions") -> Dict[str, Any]:
        """
        Return category-count dicts for functions and/or constants.

        This hides the dict-of-lists structure of NWScriptDB.function_categories
        behind a stable DTO.
        """
        result: Dict[str, Any] = {}
        if kind in ("functions", "all"):
            cats = db.function_categories
            result["function_categories"] = {
                cat: len(fns)
                for cat, fns in sorted(cats.items(), key=lambda x: -len(x[1]))
            }
            result["total_functions"] = len(db.functions)
        if kind in ("constants", "all"):
            cats = db.constant_categories
            result["constant_categories"] = {
                cat: len(cs)
                for cat, cs in sorted(cats.items(), key=lambda x: -len(x[1]))
            }
            result["total_constants"] = len(db.constants)
        return result


# ─── ERF Service ──────────────────────────────────────────────────────────────

class ERFService:
    """Single entry point for ERF / MOD / SAV archive operations.

    Wraps ERFWriter to keep the MCP tool layer free of direct
    import-coupling to the export sub-module.
    """

    @staticmethod
    def build(
        files: list[dict],
        archive_type: str = "MOD ",
    ) -> bytes:
        """Pack *files* into a binary ERF archive.

        Parameters
        ----------
        files:
            List of dicts, each with keys:
              ``resref``   – resource reference (≤ 16 chars)
              ``restype``  – extension without dot (e.g. ``"utc"``)
              ``data_b64`` – base64-encoded file contents
        archive_type:
            Four-char ERF type string: ``"ERF "``, ``"MOD "``, or ``"SAV "``.

        Returns
        -------
        bytes
            Raw ERF binary.

        Raises
        ------
        ValueError
            If *files* is empty or a base64 payload cannot be decoded.
        """
        from ghostscripter.core.export.erf_writer import ERFWriter

        if not files:
            raise ValueError("writeERF: 'files' list must not be empty.")

        writer = ERFWriter(file_type=archive_type)
        warnings: list[str] = []
        for index, item in enumerate(files):
            resref = str(item.get("resref", ""))
            if not resref or len(resref) > 16 or not resref.isascii():
                raise ValueError(
                    f"Invalid ERF ResRef {resref!r}; expected 1-16 ASCII characters."
                )
            restype = str(item.get("restype", "")).lower().lstrip(".")
            raw_b64 = item.get("data_b64", "")
            try:
                data = base64.b64decode(raw_b64, validate=True)
            except Exception as exc:
                raise ValueError(
                    f"writeERF: files[{index}] ({resref!r}) has invalid base64: {exc}"
                ) from exc
            writer.add_resource(resref, restype, data)

        erf_bytes = writer.build()
        return erf_bytes, warnings
