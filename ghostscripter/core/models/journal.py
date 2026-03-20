"""
GhostScripter-K1-K2 — Journal (.jrl) GFF Format
================================================
KotOR .jrl files store the game's quest/journal database.

GFF structure
-------------
  Top-level struct (type 0xFFFFFFFF)
    Categories  LIST of category structs
      Each category struct:
        Name        CEXOLOCSTRING  — display name (TLK StrRef)
        Tag         CEXOSTRING     — category tag (e.g. "K_SWG_MYQUEST")
        Priority    DWORD          — display priority
        Comment     CEXOSTRING
        Entries     LIST of entry structs
          Each entry struct:
            ID          DWORD      — state number (0, 1, 2 …)
            Text        CEXOLOCSTRING
            End         BYTE       — 1 = quest complete
            QuestEntry  BYTE       — 1 = marks a quest update
            Comment     CEXOSTRING

References
----------
  - nwnlexicon JournalGFF field descriptions
  - TK102 NWN2 JournalTool (field names identical to KotOR)
  - PyKotor pykotor/resource/formats/gff/jrl.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any


# ── Data model ─────────────────────────────────────────────────


@dataclass
class JournalEntry:
    """A single journal state within a quest category."""
    state_id: int = 0
    text: str = ""
    text_strref: int = -1
    is_end: bool = False
    is_quest_entry: bool = True
    comment: str = ""

    def to_dict(self) -> dict:
        return {
            "state_id": self.state_id,
            "text": self.text,
            "text_strref": self.text_strref,
            "is_end": self.is_end,
            "is_quest_entry": self.is_quest_entry,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JournalEntry":
        return cls(
            state_id=d.get("state_id", 0),
            text=d.get("text", ""),
            text_strref=d.get("text_strref", -1),
            is_end=d.get("is_end", False),
            is_quest_entry=d.get("is_quest_entry", True),
            comment=d.get("comment", ""),
        )


@dataclass
class JournalCategory:
    """A quest category (one quest) in the journal."""
    tag: str = ""
    name: str = ""
    name_strref: int = -1
    priority: int = 0
    comment: str = ""
    entries: List[JournalEntry] = field(default_factory=list)

    def add_entry(self, state_id: int, text: str = "",
                  is_end: bool = False) -> JournalEntry:
        e = JournalEntry(state_id=state_id, text=text, is_end=is_end)
        self.entries.append(e)
        return e

    def get_entry(self, state_id: int) -> JournalEntry | None:
        return next((e for e in self.entries if e.state_id == state_id), None)

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "name": self.name,
            "name_strref": self.name_strref,
            "priority": self.priority,
            "comment": self.comment,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JournalCategory":
        cat = cls(
            tag=d.get("tag", ""),
            name=d.get("name", ""),
            name_strref=d.get("name_strref", -1),
            priority=d.get("priority", 0),
            comment=d.get("comment", ""),
        )
        for ed in d.get("entries", []):
            cat.entries.append(JournalEntry.from_dict(ed))
        return cat


@dataclass
class JournalFile:
    """
    Represents a KotOR .jrl journal file.

    A JRL file contains a list of quest categories, each with a set of
    numbered state entries.  The file is a GFF V3.2 binary.
    """
    name: str = "journal"
    file_path: Path | None = None
    categories: List[JournalCategory] = field(default_factory=list)

    # ── Category CRUD ─────────────────────────────────────────

    def add_category(self, tag: str, name: str = "",
                     priority: int = 0,
                     comment: str = "") -> JournalCategory:
        cat = JournalCategory(tag=tag, name=name, priority=priority,
                              comment=comment)
        self.categories.append(cat)
        return cat

    def get_category(self, tag: str) -> JournalCategory | None:
        return next((c for c in self.categories if c.tag == tag), None)

    def remove_category(self, tag: str) -> bool:
        before = len(self.categories)
        self.categories = [c for c in self.categories if c.tag != tag]
        return len(self.categories) < before

    # ── Serialisation ─────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "categories": [c.to_dict() for c in self.categories],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JournalFile":
        jrl = cls(name=d.get("name", "journal"))
        for cd in d.get("categories", []):
            jrl.categories.append(JournalCategory.from_dict(cd))
        return jrl

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "JournalFile":
        import json
        return cls.from_dict(json.loads(text))


# ── Default factory ────────────────────────────────────────────

def create_quest_journal(quest_name: str, quest_tag: str,
                         game: str = "K1") -> JournalFile:
    """
    Create a minimal journal file with one quest category.
    The quest has 3 default states: 0 (inactive), 1 (started), 10 (complete).
    """
    jrl = JournalFile(name=quest_tag)
    cat = jrl.add_category(tag=quest_tag, name=quest_name, priority=25)
    cat.add_entry(0, "")                              # inactive / not yet started
    cat.add_entry(1, f"Started: {quest_name}", is_end=False)
    cat.add_entry(10, f"Completed: {quest_name}", is_end=True)
    return jrl
