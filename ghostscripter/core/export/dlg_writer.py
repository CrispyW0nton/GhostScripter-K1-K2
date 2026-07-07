"""
GhostScripter-K1-K2 — GFF3 Binary Writer + DLG Exporter

GFF3 binary format (used by KotOR 1 & 2 for .dlg, .utc, .utp, etc.):

Header (56 bytes):
  FileType     4 chars   e.g. "DLG "
  FileVersion  4 chars   "V3.2"
  StructOffset DWORD
  StructCount  DWORD
  FieldOffset  DWORD
  FieldCount   DWORD
  LabelOffset  DWORD
  LabelCount   DWORD
  FieldDataOffset  DWORD
  FieldDataCount   DWORD
  FieldIndicesOffset  DWORD
  FieldIndicesCount   DWORD
  ListIndicesOffset   DWORD
  ListIndicesCount    DWORD

Struct:
  Type         DWORD  (0xFFFFFFFF = top-level)
  DataOrDataOffset  DWORD  (if fieldCount==1: field index; else: offset into FieldIndices)
  FieldCount   DWORD

Field:
  Type         DWORD  (see GFFFieldType enum)
  LabelIndex   DWORD
  DataOrDataOffset  DWORD

References:
  - xoreos-tools src/aurora/gff3writer.cpp
  - PyKotor pykotor/resource/formats/gff/io_gff.py
  - TSLPatcher lib/site/Bioware/GFF.pm
  - TK102 DLGEditor dlgeditor_234.pl (field creation patterns)
"""

from __future__ import annotations

import logging
import struct
from enum import IntEnum
from pathlib import Path

log = logging.getLogger(__name__)
from typing import Any, Dict, List, Optional, Tuple

from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch, DLGAnimation,
)

# ── Shared GFF3 engine ────────────────────────────────────────────────────────
# GFFType, GFFStruct and GFF3Writer are now defined in gff_writer.py.
# We re-export them here so that code importing from dlg_writer keeps working.
from ghostscripter.core.export.gff_writer import (   # noqa: F401
    GFFType, GFFStruct, GFF3Writer,
)
from ghostscripter.core.export.erf_writer import RESTYPE_IDS as _SHARED_RESTYPE_IDS
# Also keep bare IntEnum import for local use elsewhere in this file
from enum import IntEnum as _IntEnum  # used by ERFWriter below


# ── DLG Exporter ──────────────────────────────────────────────

class DLGExporter:
    """
    Convert a DialogueFile to GFF3 binary (.dlg).
    Produces files compatible with KotOR 1 and TSL.

    References:
    - TK102 dlgeditor_234.pl — all field names verified against this
    - PyKotor resource/generics/dlg/ — full field list
    - xoreos-tools gff3writer — binary layout
    """

    def export(self, dlg: DialogueFile, target_game: str = "K1") -> bytes:
        """Return GFF3 binary bytes for the .dlg file."""
        w = GFF3Writer("DLG ")
        r = w.root

        # Top-level fields
        r.add_resref("EndConversation", dlg.on_end or "")
        r.add_resref("EndConverAbort",  dlg.on_abort or "")
        r.add_byte("Skippable",      1 if dlg.skippable else 0)
        r.add_dword("DelayEntry",    dlg.delay_entry)
        r.add_dword("DelayReply",    dlg.delay_reply)
        r.add_resref("AmbientTrack", dlg.ambient_track or "")
        r.add_byte("AnimatedCut",    1 if dlg.animated_cut else 0)
        r.add_resref("CameraModel",  dlg.camera_model or "")
        r.add_int("ConversationType", dlg.conversation_type)
        r.add_byte("ComputerType",   dlg.computer_type)
        r.add_byte("OldHitCheck",    1 if dlg.old_hit_check else 0)
        r.add_byte("UnequipItems",   1 if dlg.unequip_items else 0)
        r.add_byte("UnequipHItem",   1 if dlg.unequip_h_item else 0)

        if target_game == "K2":
            r.add_dword("NumWords", dlg.word_count)

        # EntryList
        entry_structs = [self._make_node_struct(e, "entry", target_game)
                         for e in dlg.entries]
        r.add_list("EntryList", entry_structs)

        # ReplyList
        reply_structs = [self._make_node_struct(rp, "reply", target_game)
                         for rp in dlg.replies]
        r.add_list("ReplyList", reply_structs)

        # StartingList — links into EntryList
        starter_structs = [self._make_link_struct(b, target_game)
                           for b in dlg.starters]
        r.add_list("StartingList", starter_structs)

        return w.build()

    def _make_node_struct(self, node: DialogueNode,
                          node_type: str, game: str) -> GFFStruct:
        s = GFFStruct(0)
        s.add_locstring("Text", node.text_strref if node.text_strref >= 0 else -1,
                        node.text)

        # script / actions — warn if script name exceeds KotOR's 16-char ResRef limit
        for _field, _val in (("Script", node.script1), ("Script2", node.script2)):
            if _val and len(_val) > 16:
                log.warning(
                    "Node %d %s '%s' is %d chars — will be silently truncated to 16 "
                    "(KotOR ResRef limit). Rename the script.",
                    node.node_id, _field, _val, len(_val)
                )
        s.add_resref("Script", node.script1)
        if game == "K2":
            s.add_resref("Script2", node.script2)

        if node_type == "entry":
            s.add_cexo("Speaker",  node.speaker)

        s.add_cexo("Listener", node.listener)
        s.add_resref("VO_ResRef", node.vo_resref)
        s.add_resref("Sound",     node.sound)
        s.add_byte("SoundExists", node.sound_exists)

        # AnimList
        anim_structs = []
        for anim in node.animations:
            a = GFFStruct(0)
            a.add_cexo("Participant", anim.participant)
            a.add_dword("Animation", anim.animation_id)
            anim_structs.append(a)
        s.add_list("AnimList", anim_structs)

        s.add_dword("Delay", node.delay & 0xFFFFFFFF)
        s.add_dword("WaitFlags", node.wait_flags)
        s.add_cexo("Quest",  node.quest)
        s.add_dword("QuestEntry", node.quest_entry)
        s.add_int("PlotIndex", node.plot_index)
        s.add_float("PlotXPPercentage", node.plot_xp_percentage)

        s.add_byte("FadeType",  node.fade_type)
        s.add_vector("FadeColor", node.fade_color_r, node.fade_color_g, node.fade_color_b)
        s.add_float("FadeDelay",  node.fade_delay)
        s.add_float("FadeLength", node.fade_length)
        s.add_int("CameraAngle", node.camera_angle)

        if game == "K2":
            if node.camera_id is not None:
                s.add_int("CameraID", node.camera_id)
            if node.camera_animation is not None:
                s.add_dword("CameraAnimation", node.camera_animation)
            if node.camera_fov is not None:
                s.add_float("CamFieldOfView", node.camera_fov)
            if node.camera_height is not None:
                s.add_float("CamHeightOffset", node.camera_height)
            if node.camera_effect is not None:
                s.add_int("CamVidEffect", node.camera_effect)
            if node.target_height is not None:
                s.add_float("TarHeightOffset", node.target_height)
            s.add_byte("NodeUnskippable", 1 if node.node_unskippable else 0)
            s.add_int("AlienRaceNode",   node.alien_race_node)
            s.add_int("Emotion",         node.emotion_id)
            s.add_int("FacialAnim",      node.facial_id)
            s.add_int("NodeID",          node.node_id_tsl)
            s.add_int("PostProcNode",    node.post_proc_node)
            s.add_byte("RecordVO",              1 if node.record_vo else 0)
            s.add_byte("RecordNoVOOverri",      1 if node.record_no_vo_override else 0)
            s.add_byte("VOTextChanged",         1 if node.vo_text_changed else 0)
            # Script params
            s.add_int("ActionParam1",  node.script1_param1)
            s.add_int("ActionParam2",  node.script1_param2)
            s.add_int("ActionParam3",  node.script1_param3)
            s.add_int("ActionParam4",  node.script1_param4)
            s.add_int("ActionParam5",  node.script1_param5)
            s.add_cexo("ActionParamStrA", node.script1_param_str)
            s.add_int("ActionParam1b", node.script2_param1)
            s.add_int("ActionParam2b", node.script2_param2)
            s.add_int("ActionParam3b", node.script2_param3)
            s.add_int("ActionParam4b", node.script2_param4)
            s.add_int("ActionParam5b", node.script2_param5)
            s.add_cexo("ActionParamStrB", node.script2_param_str)

        # Outgoing links
        if node_type == "entry":
            link_structs = [self._make_link_struct(b, game) for b in node.branches]
            s.add_list("RepliesList", link_structs)
        else:
            link_structs = [self._make_link_struct(b, game) for b in node.branches]
            s.add_list("EntriesList", link_structs)

        return s

    def _make_link_struct(self, branch: DialogueBranch, game: str) -> GFFStruct:
        s = GFFStruct(0)
        s.add_dword("Index",  max(0, branch.target_node_id))
        s.add_resref("Active", branch.active_script or "")
        s.add_byte("IsChild",  1 if branch.is_child else 0)
        if game == "K2":
            s.add_resref("Active2", branch.active_script2 or "")
            s.add_byte("DisplayInactive", 1 if branch.display_inactive else 0)
        return s


# ── ERF / Override Exporter ────────────────────────────────────
# (Kept from original; ERF binary structure unchanged)

class ERFWriter:
    """
    Writes ERF/MOD/SAV archives.

    ERF header (160 bytes):
      FileType    4 chars  "ERF " / "MOD " / "SAV "
      FileVersion 4 chars  "V1.0"
      LanguageCount DWORD
      LocalizedStringSize DWORD
      EntryCount  DWORD
      OffsetToLocalizedStrings DWORD
      OffsetToKeyList DWORD
      OffsetToResourceList DWORD
      BuildYear   DWORD
      BuildDay    DWORD
      DescriptionStrRef DWORD
      Reserved    116 bytes

    Key entries (24 bytes each):
      ResRef  16 chars
      ResID   DWORD
      ResType WORD
      Unused  WORD

    Resource entries (8 bytes each):
      OffsetToResource DWORD
      ResourceSize     DWORD
    """

    # Single source of truth — the verified table in erf_writer.py
    # (values cross-checked against PyKotor and retail module RIMs).
    RESTYPE_MAP: Dict[str, int] = _SHARED_RESTYPE_IDS

    def __init__(self, file_type: str = "ERF "):
        self.file_type = file_type.ljust(4)[:4]
        self.resources: List[Tuple[str, bytes]] = []

    def add_resource(self, resref: str, data: bytes):
        self.resources.append((resref, data))

    def build(self) -> bytes:
        import datetime
        now = datetime.datetime.now()
        year = now.year - 1900
        day  = now.timetuple().tm_yday - 1

        entry_count = len(self.resources)
        key_list_offset = 160
        res_list_offset = key_list_offset + 24 * entry_count
        data_offset     = res_list_offset + 8  * entry_count

        header = struct.pack(
            "<4s4sIIIIIIII",
            self.file_type.encode("ascii"),
            b"V1.0",
            0,                     # LanguageCount
            0,                     # LocalizedStringSize
            entry_count,
            160,                   # OffsetToLocalizedStrings (past header)
            key_list_offset,
            res_list_offset,
            year,
            day,
        )
        # Pad description strref + reserved
        header += struct.pack("<I", 0xFFFFFFFF)
        header += b"\x00" * 116
        assert len(header) == 160

        key_list = bytearray()
        res_list = bytearray()
        res_data = bytearray()

        for res_id, (resref, data) in enumerate(self.resources):
            stem  = Path(resref).stem[:16]
            ext   = Path(resref).suffix.lower()
            rtype = self.RESTYPE_MAP.get(ext, 0)

            key_list += stem.encode("ascii").ljust(16, b"\x00")
            key_list += struct.pack("<IHH", res_id, rtype, 0)

            offset_in_data = len(res_data)
            res_list += struct.pack("<II", data_offset + offset_in_data, len(data))
            res_data += data

        return header + bytes(key_list) + bytes(res_list) + bytes(res_data)


class OverrideExporter:
    """Write files directly to a KotOR Override folder."""

    def __init__(self, override_path: str):
        self.override_path = Path(override_path)

    def export(self, resref: str, data: bytes):
        self.override_path.mkdir(parents=True, exist_ok=True)
        dest = self.override_path / resref
        dest.write_bytes(data)


# ── DLG round-trip test ────────────────────────────────────────

def _test_roundtrip():
    from ghostscripter.core.models.dialogue import create_simple_dialogue
    dlg = create_simple_dialogue("test", "npc_001")
    exporter = DLGExporter()
    data = exporter.export(dlg, "K1")
    assert data[:4] == b"DLG ", f"Bad magic: {data[:4]}"
    assert data[4:8] == b"V3.2",  f"Bad version: {data[4:8]}"
    print(f"DLG export OK: {len(data)} bytes")
    return data


if __name__ == "__main__":
    _test_roundtrip()
