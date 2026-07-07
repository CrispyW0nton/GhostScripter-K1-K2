"""
GhostScripter-K1-K2 — JRL (Journal) GFF3 Writer + Reader
=========================================================
Reads and writes KotOR .jrl journal files in GFF V3.2 binary format.

GFF field layout for JRL (verified against retail K1 global.jrl)
  Root struct (0xFFFFFFFF)
    Categories  LIST
      Category struct (type 0)
        Name        CEXOLOCSTRING  (TLK StrRef + optional custom string)
        Tag         CEXOSTRING
        Priority    DWORD
        Comment     CEXOSTRING
        EntryList   LIST
          Entry struct (type 0)
            ID          DWORD
            Text        CEXOLOCSTRING
            End         WORD (UInt16)
            Comment     CEXOSTRING

References:
  - Retail K1 global.jrl (Categories → EntryList → ID/End/Text/XP_Percentage)
  - xoreos-tools Aurora JRL parsing
  - PyKotor resource/generics/jrl.py field names
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import List, Optional

from ghostscripter.core.models.journal import (
    JournalFile, JournalCategory, JournalEntry, create_quest_journal,
)
from ghostscripter.core.export.gff_writer import (
    GFF3Writer, GFFStruct, GFFType,
)


# ── JRL Writer ─────────────────────────────────────────────────


class JRLWriter:
    """
    Serialises a JournalFile to GFF V3.2 binary (.jrl).
    """

    def export(self, journal: JournalFile) -> bytes:
        w = GFF3Writer("JRL ")
        root = w.root

        cat_structs: List[GFFStruct] = []
        for cat in journal.categories:
            cs = GFFStruct(0)
            name_strref = max(cat.name_strref, -1)
            cs.add_locstring("Name", name_strref, cat.name)
            cs.add_cexo("Tag", cat.tag)
            cs.add_dword("Priority", cat.priority)
            cs.add_cexo("Comment", cat.comment)

            entry_structs: List[GFFStruct] = []
            for entry in cat.entries:
                es = GFFStruct(0)
                es.add_dword("ID", entry.state_id)
                text_strref = max(entry.text_strref, -1)
                es.add_locstring("Text", text_strref, entry.text)
                # Retail JRLs store End as a WORD (UInt16), not a BYTE —
                # the engine's typed GFF getter ignores a mistyped field.
                es.add_word("End", 1 if entry.is_end else 0)
                es.add_cexo("Comment", entry.comment)
                entry_structs.append(es)

            # The engine reads "EntryList" (verified against K1 global.jrl);
            # "Entries" is not recognised by the game.
            cs.add_list("EntryList", entry_structs)
            cat_structs.append(cs)

        root.add_list("Categories", cat_structs)
        return w.build()


class JRLExporter:
    """Thin wrapper matching the DLGExporter interface."""

    def export(self, journal: JournalFile, target_game: str = "K1") -> bytes:
        return JRLWriter().export(journal)


# ── JRL Reader ─────────────────────────────────────────────────


class JRLImporter:
    """
    Deserialises a GFF V3.2 .jrl binary into a JournalFile.

    Uses a lightweight GFF3 reader that walks the binary directly,
    shared with the DLGImporter pattern.
    """

    def import_from_bytes(self, data: bytes) -> JournalFile:
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        reader = GFF3Reader(data)
        root = reader.parse()
        return self._parse_root(root)

    def import_from_file(self, path: Path) -> JournalFile:
        return self.import_from_bytes(path.read_bytes())

    # ── Parsing helpers ───────────────────────────────────────

    def _parse_root(self, root: dict) -> JournalFile:
        journal = JournalFile()
        cat_list = root.get("Categories", [])
        for cd in cat_list:
            journal.categories.append(self._parse_category(cd))
        return journal

    def _parse_category(self, cd: dict) -> JournalCategory:
        name_field = cd.get("Name", ("", ""))
        if isinstance(name_field, tuple):
            strref, text = name_field
        elif isinstance(name_field, str):
            strref, text = -1, name_field
        else:
            strref, text = -1, str(name_field)

        cat = JournalCategory(
            tag=str(cd.get("Tag", "")),
            name=text,
            name_strref=int(strref) if strref is not None else -1,
            priority=int(cd.get("Priority", 0)),
            comment=str(cd.get("Comment", "")),
        )
        # "EntryList" is the retail label; "Entries" is read as a fallback
        # for journals written by GhostScripter ≤ 3.6.0.
        for ed in cd.get("EntryList", cd.get("Entries", [])):
            cat.entries.append(self._parse_entry(ed))
        return cat

    def _parse_entry(self, ed: dict) -> JournalEntry:
        text_field = ed.get("Text", ("", ""))
        if isinstance(text_field, tuple):
            strref, text = text_field
        elif isinstance(text_field, str):
            strref, text = -1, text_field
        else:
            strref, text = -1, str(text_field)

        return JournalEntry(
            state_id=int(ed.get("ID", 0)),
            text=text,
            text_strref=int(strref) if strref is not None else -1,
            is_end=bool(ed.get("End", 0)),
            is_quest_entry=bool(ed.get("QuestEntry", 1)),
            comment=str(ed.get("Comment", "")),
        )
