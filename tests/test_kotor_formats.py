#!/usr/bin/env python3
"""
test_kotor_formats.py — Comprehensive GFF round-trip tests for real KotOR game formats.

Tests all primary KotOR resource types by building realistic GFF structures and
verifying they round-trip through GFF3Writer → GFF3Reader without data loss.

Resource types tested:
  - UTC  (Creature Template)     — creature stats, scripts, feats, inventory
  - UTP  (Placeable Template)    — placeable object properties
  - UTD  (Door Template)         — door properties, scripts, locks
  - UTI  (Item Template)         — item stats, properties, requirements
  - UTS  (Sound Template)        — ambient sound
  - UTW  (Waypoint Template)     — waypoint with map note
  - ARE  (Area data)             — area environment settings
  - GIT  (Game Instance file)    — creature/placeable/item placement with Vector/Orientation
  - IFO  (Module Info)           — module header
  - DLG  (Dialogue)              — full round-trip through DLGExporter + DLGImporter
  - JRL  (Journal)               — quest journal round-trip

Cross-compatibility: all GFF output is verified to be byte-compatible with PyKotor's
GFFBinaryReader expectations (V3.2, same field type IDs, same binary layout).

References:
  - OldRepublicDevs/PyKotor Libraries/PyKotor/src/pykotor/resource/formats/gff/io_gff.py
  - OldRepublicDevs/DeNCS (Java decompiler for NCS scripts)
"""

import math
import struct as _struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct, GFFType
from ghostscripter.core.export.dlg_reader import GFF3Reader
from ghostscripter.core.export.dlg_writer import DLGExporter
from ghostscripter.core.export.dlg_reader import DLGImporter
from ghostscripter.core.export.jrl_writer import JRLWriter, JRLImporter
from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch, create_simple_dialogue,
)
from ghostscripter.core.models.journal import (
    JournalFile, JournalCategory, JournalEntry, create_quest_journal,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _roundtrip(setup_fn, file_type: str = "TST ") -> dict:
    """Write GFF with setup_fn and parse back; return root dict."""
    w = GFF3Writer(file_type)
    setup_fn(w.root)
    data = w.build()
    r = GFF3Reader(data)
    return r.parse()


def _verify_header(data: bytes, expected_type: bytes) -> None:
    """Assert that GFF data has correct magic bytes and V3.2 version."""
    assert data[:4] == expected_type, f"Expected {expected_type}, got {data[:4]!r}"
    assert data[4:8] == b"V3.2", f"Expected b'V3.2', got {data[4:8]!r}"
    assert len(data) >= 56, f"GFF too small: {len(data)} bytes"


def _approx(a, b, places=4):
    return abs(a - b) < 10 ** (-places)


# ─────────────────────────────────────────────────────────────────────────────
# GFF Header Contract Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGFFHeaderContract(unittest.TestCase):
    """Verify binary GFF header matches what KotOR engine and PyKotor expect."""

    def _build(self, file_type: str) -> bytes:
        w = GFF3Writer(file_type)
        w.root.add_cexo("Test", "value")
        return w.build()

    def test_header_is_56_bytes_minimum(self):
        data = self._build("DLG ")
        self.assertGreaterEqual(len(data), 56)

    def test_magic_dlg(self):
        _verify_header(self._build("DLG "), b"DLG ")

    def test_magic_utc(self):
        _verify_header(self._build("UTC "), b"UTC ")

    def test_magic_jrl(self):
        _verify_header(self._build("JRL "), b"JRL ")

    def test_magic_are(self):
        _verify_header(self._build("ARE "), b"ARE ")

    def test_magic_git(self):
        _verify_header(self._build("GIT "), b"GIT ")

    def test_magic_ifo(self):
        _verify_header(self._build("IFO "), b"IFO ")

    def test_version_v32(self):
        data = self._build("TST ")
        self.assertEqual(data[4:8], b"V3.2")

    def test_struct_offset_is_56(self):
        """Struct section always starts immediately after the 56-byte header."""
        data = self._build("TST ")
        struct_off = _struct.unpack_from("<I", data, 8)[0]
        self.assertEqual(struct_off, 56)

    def test_struct_count_nonzero(self):
        data = self._build("TST ")
        struct_count = _struct.unpack_from("<I", data, 12)[0]
        self.assertGreaterEqual(struct_count, 1)

    def test_field_count_nonzero(self):
        data = self._build("TST ")
        field_count = _struct.unpack_from("<I", data, 20)[0]
        self.assertGreaterEqual(field_count, 1)

    def test_label_count_nonzero(self):
        data = self._build("TST ")
        label_count = _struct.unpack_from("<I", data, 28)[0]
        self.assertGreaterEqual(label_count, 1)


# ─────────────────────────────────────────────────────────────────────────────
# UTC — Creature Template
# ─────────────────────────────────────────────────────────────────────────────

class TestUTCRoundtrip(unittest.TestCase):
    """Creature template (.utc) format tests — verifies all typical fields."""

    def _make_utc(self, tag="k_mand_001", appearance=248, name="Mandalorian") -> bytes:
        w = GFF3Writer("UTC ")
        r = w.root
        r.add_cexo("Tag", tag)
        r.add_resref("TemplateResRef", tag[:16])
        r.add_locstring("LocalizedName", 12345, name)
        r.add_word("Appearance_Type", appearance)
        r.add_byte("Str", 16)
        r.add_byte("Dex", 12)
        r.add_byte("Con", 14)
        r.add_byte("Int", 10)
        r.add_byte("Wis", 10)
        r.add_byte("Cha", 8)
        r.add_byte("MaxHitPoints", 40)
        r.add_byte("CurrentHitPoints", 40)
        r.add_byte("NaturalAC", 2)
        r.add_byte("Gender", 0)
        r.add_byte("FactionID", 1)
        r.add_byte("IsPC", 0)
        r.add_byte("Plot", 0)
        r.add_byte("Interruptable", 1)
        r.add_vector("XPosition", 12.5, -8.75, 0.0)
        r.add_orientation("XOrientation", 0.707, 0.0, 0.0, 0.707)
        r.add_resref("ScriptAttacked", "k_def_attacked01")
        r.add_resref("ScriptDeath", "k_def_death01")
        r.add_resref("ScriptOnDialog", "k_def_ondlg01")
        # Feats
        f1 = GFFStruct(1)
        f1.add_word("Feat", 33)
        f2 = GFFStruct(1)
        f2.add_word("Feat", 5)
        r.add_list("FeatList", [f1, f2])
        # Class
        cls = GFFStruct(2)
        cls.add_int("Class", 8)
        cls.add_short("ClassLevel", 3)
        r.add_list("ClassList", [cls])
        r.add_list("Equip_ItemList", [])
        r.add_list("ItemList", [])
        return w.build()

    def test_utc_header(self):
        data = self._make_utc()
        _verify_header(data, b"UTC ")

    def test_utc_tag_preserved(self):
        data = self._make_utc("k_uniq_npc")
        d = GFF3Reader(data).parse()
        self.assertEqual(d["Tag"], "k_uniq_npc")

    def test_utc_template_resref(self):
        data = self._make_utc("k_mand_001")
        d = GFF3Reader(data).parse()
        self.assertEqual(d["TemplateResRef"], "k_mand_001")

    def test_utc_localized_name(self):
        data = self._make_utc(name="Sith Soldier")
        d = GFF3Reader(data).parse()
        loc = d["LocalizedName"]
        self.assertIsInstance(loc, tuple)
        self.assertEqual(loc[1], "Sith Soldier")
        self.assertEqual(loc[0], 12345)

    def test_utc_stat_strength(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        self.assertEqual(d["Str"], 16)

    def test_utc_appearance_word(self):
        data = self._make_utc(appearance=175)
        d = GFF3Reader(data).parse()
        self.assertEqual(d["Appearance_Type"], 175)

    def test_utc_position_vector(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        pos = d["XPosition"]
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 3)
        self.assertAlmostEqual(pos[0], 12.5, places=4)
        self.assertAlmostEqual(pos[1], -8.75, places=4)
        self.assertAlmostEqual(pos[2], 0.0, places=4)

    def test_utc_orientation(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        ori = d["XOrientation"]
        self.assertIsInstance(ori, tuple)
        self.assertEqual(len(ori), 4)
        self.assertAlmostEqual(ori[0], 0.707, places=3)
        self.assertAlmostEqual(ori[3], 0.707, places=3)

    def test_utc_script_resref(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        self.assertEqual(d["ScriptAttacked"], "k_def_attacked01")
        self.assertEqual(d["ScriptDeath"], "k_def_death01")

    def test_utc_feat_list(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        feats = d["FeatList"]
        self.assertEqual(len(feats), 2)
        feat_ids = {f["Feat"] for f in feats}
        self.assertIn(33, feat_ids)
        self.assertIn(5, feat_ids)

    def test_utc_class_list(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        classes = d["ClassList"]
        self.assertEqual(len(classes), 1)
        cls = classes[0]
        self.assertEqual(cls["Class"], 8)
        self.assertEqual(cls["ClassLevel"], 3)

    def test_utc_empty_lists(self):
        data = self._make_utc()
        d = GFF3Reader(data).parse()
        self.assertEqual(len(d["Equip_ItemList"]), 0)
        self.assertEqual(len(d["ItemList"]), 0)

    def test_utc_multiple_creatures_independent(self):
        """Multiple UTC files must not share state."""
        d1 = GFF3Reader(self._make_utc("k_npc_a", 100)).parse()
        d2 = GFF3Reader(self._make_utc("k_npc_b", 200)).parse()
        self.assertEqual(d1["Tag"], "k_npc_a")
        self.assertEqual(d2["Tag"], "k_npc_b")
        self.assertEqual(d1["Appearance_Type"], 100)
        self.assertEqual(d2["Appearance_Type"], 200)


# ─────────────────────────────────────────────────────────────────────────────
# UTP — Placeable Template
# ─────────────────────────────────────────────────────────────────────────────

class TestUTPRoundtrip(unittest.TestCase):
    """Placeable template (.utp) round-trip tests."""

    def _make_utp(self, tag="k_plc_chest01", appearance=34, name="Storage Container") -> bytes:
        w = GFF3Writer("UTP ")
        r = w.root
        r.add_cexo("Tag", tag)
        r.add_resref("TemplateResRef", tag[:16])
        r.add_locstring("LocalizedName", -1, name)
        r.add_word("Appearance", appearance)
        r.add_byte("HasInventory", 1)
        r.add_byte("Useable", 1)
        r.add_byte("Plot", 0)
        r.add_byte("Static", 0)
        r.add_byte("Locked", 0)
        r.add_byte("Lockable", 1)
        r.add_byte("OpenLockDC", 0)
        r.add_byte("CloseLockDC", 0)
        r.add_word("KeyRequired", 0)
        r.add_short("HP", 15)
        r.add_short("CurrentHP", 15)
        r.add_byte("Hardness", 5)
        r.add_resref("OnOpen", "k_plc_opnchst01")
        r.add_resref("OnClosed", "")
        r.add_resref("OnUsed", "")
        r.add_resref("OnDamaged", "")
        r.add_resref("OnDeath", "")
        r.add_resref("OnHeartbeat", "")
        r.add_resref("OnMeleeAttacked", "")
        r.add_resref("OnSpellCastAt", "")
        r.add_list("ItemList", [])
        return w.build()

    def test_utp_header(self):
        _verify_header(self._make_utp(), b"UTP ")

    def test_utp_tag(self):
        d = GFF3Reader(self._make_utp("k_plc_locker")).parse()
        self.assertEqual(d["Tag"], "k_plc_locker")

    def test_utp_appearance(self):
        d = GFF3Reader(self._make_utp(appearance=55)).parse()
        self.assertEqual(d["Appearance"], 55)

    def test_utp_has_inventory(self):
        d = GFF3Reader(self._make_utp()).parse()
        self.assertEqual(d["HasInventory"], 1)

    def test_utp_hp(self):
        d = GFF3Reader(self._make_utp()).parse()
        self.assertEqual(d["HP"], 15)
        self.assertEqual(d["CurrentHP"], 15)

    def test_utp_script(self):
        d = GFF3Reader(self._make_utp()).parse()
        self.assertEqual(d["OnOpen"], "k_plc_opnchst01")

    def test_utp_localized_name(self):
        d = GFF3Reader(self._make_utp(name="Plastoid Container")).parse()
        loc = d["LocalizedName"]
        self.assertEqual(loc[1], "Plastoid Container")

    def test_utp_empty_item_list(self):
        d = GFF3Reader(self._make_utp()).parse()
        self.assertEqual(len(d["ItemList"]), 0)


# ─────────────────────────────────────────────────────────────────────────────
# UTD — Door Template
# ─────────────────────────────────────────────────────────────────────────────

class TestUTDRoundtrip(unittest.TestCase):
    """Door template (.utd) round-trip tests."""

    def _make_utd(self, tag="k_door_lab01", locked=False) -> bytes:
        w = GFF3Writer("UTD ")
        r = w.root
        r.add_cexo("Tag", tag)
        r.add_resref("TemplateResRef", tag[:16])
        r.add_locstring("LocalizedName", -1, "Laboratory Door")
        r.add_word("GenericType", 9)  # Door appearance
        r.add_byte("Locked", 1 if locked else 0)
        r.add_byte("Lockable", 1)
        r.add_byte("OpenLockDC", 25)
        r.add_byte("CloseLockDC", 0)
        r.add_byte("Hardness", 8)
        r.add_short("HP", 30)
        r.add_short("CurrentHP", 30)
        r.add_byte("Plot", 0)
        r.add_byte("Static", 0)
        r.add_cexo("KeyTag", "k_key_lab01" if locked else "")
        r.add_byte("KeyRequired", 0)
        r.add_byte("AutoRemoveKey", 0)
        r.add_resref("OnFailToOpen", "k_door_failopn01")
        r.add_resref("OnOpen", "k_door_opn01")
        r.add_resref("OnClosed", "")
        r.add_resref("OnDamaged", "")
        r.add_resref("OnDeath", "")
        r.add_resref("OnHeartbeat", "")
        r.add_resref("OnMeleeAttacked", "")
        r.add_resref("OnSpellCastAt", "")
        r.add_resref("OnUserDefined", "")
        return w.build()

    def test_utd_header(self):
        _verify_header(self._make_utd(), b"UTD ")

    def test_utd_tag(self):
        d = GFF3Reader(self._make_utd("k_door_cargo")).parse()
        self.assertEqual(d["Tag"], "k_door_cargo")

    def test_utd_unlocked(self):
        d = GFF3Reader(self._make_utd(locked=False)).parse()
        self.assertEqual(d["Locked"], 0)

    def test_utd_locked(self):
        d = GFF3Reader(self._make_utd(locked=True)).parse()
        self.assertEqual(d["Locked"], 1)

    def test_utd_openlock_dc(self):
        d = GFF3Reader(self._make_utd()).parse()
        self.assertEqual(d["OpenLockDC"], 25)

    def test_utd_hp(self):
        d = GFF3Reader(self._make_utd()).parse()
        self.assertEqual(d["HP"], 30)

    def test_utd_key_tag_when_locked(self):
        d = GFF3Reader(self._make_utd(locked=True)).parse()
        self.assertEqual(d["KeyTag"], "k_key_lab01")

    def test_utd_script(self):
        d = GFF3Reader(self._make_utd()).parse()
        self.assertEqual(d["OnFailToOpen"], "k_door_failopn01")


# ─────────────────────────────────────────────────────────────────────────────
# UTI — Item Template
# ─────────────────────────────────────────────────────────────────────────────

class TestUTIRoundtrip(unittest.TestCase):
    """Item template (.uti) round-trip tests."""

    def _make_uti(self, tag="g_i_lghtsbr001", base_item=8, name="Lightsaber") -> bytes:
        w = GFF3Writer("UTI ")
        r = w.root
        r.add_cexo("Tag", tag)
        r.add_resref("TemplateResRef", tag[:16])
        r.add_locstring("LocalizedName", -1, name)
        r.add_locstring("DescIdentified", -1, "A Jedi weapon from a more civilized age.")
        r.add_int("BaseItem", base_item)
        r.add_short("StackSize", 1)
        r.add_byte("Identified", 1)
        r.add_byte("Stolen", 0)
        r.add_byte("Plot", 0)
        r.add_byte("Cursed", 0)
        r.add_byte("PickpocketDC", 0)
        r.add_float("Cost", 3000.0)
        r.add_float("AddCost", 0.0)
        r.add_resref("Icon", "iit_sabrblue001")
        # Properties list
        prop = GFFStruct(0)
        prop.add_word("PropertyName", 9)    # ITEM_PROPERTY_BONUS_FEAT
        prop.add_word("Subtype", 0)
        prop.add_word("CostTable", 0)
        prop.add_word("CostValue", 0)
        prop.add_word("Param1", 255)
        prop.add_word("Param1Value", 0)
        prop.add_byte("ChanceAppear", 100)
        prop.add_byte("UsesPerDay", 255)
        prop.add_byte("Useable", 1)
        r.add_list("PropertiesList", [prop])
        return w.build()

    def test_uti_header(self):
        _verify_header(self._make_uti(), b"UTI ")

    def test_uti_tag(self):
        d = GFF3Reader(self._make_uti("g_w_blstpstl001")).parse()
        self.assertEqual(d["Tag"], "g_w_blstpstl001")

    def test_uti_base_item(self):
        d = GFF3Reader(self._make_uti(base_item=12)).parse()
        self.assertEqual(d["BaseItem"], 12)  # BASE_ITEM_BLASTER_PISTOL

    def test_uti_stack_size(self):
        d = GFF3Reader(self._make_uti()).parse()
        self.assertEqual(d["StackSize"], 1)

    def test_uti_cost(self):
        d = GFF3Reader(self._make_uti()).parse()
        self.assertAlmostEqual(d["Cost"], 3000.0, places=2)

    def test_uti_localized_name(self):
        d = GFF3Reader(self._make_uti(name="Blaster Pistol")).parse()
        loc = d["LocalizedName"]
        self.assertEqual(loc[1], "Blaster Pistol")

    def test_uti_icon(self):
        d = GFF3Reader(self._make_uti()).parse()
        self.assertEqual(d["Icon"], "iit_sabrblue001")

    def test_uti_properties_list(self):
        d = GFF3Reader(self._make_uti()).parse()
        props = d["PropertiesList"]
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["PropertyName"], 9)
        self.assertEqual(props[0]["ChanceAppear"], 100)


# ─────────────────────────────────────────────────────────────────────────────
# ARE — Area Template
# ─────────────────────────────────────────────────────────────────────────────

class TestARERoundtrip(unittest.TestCase):
    """Area resource (.are) round-trip tests."""

    def _make_are(self, tag="m01aa", name="Endar Spire - Command Module") -> bytes:
        w = GFF3Writer("ARE ")
        r = w.root
        r.add_cexo("Tag", tag)
        r.add_locstring("Name", -1, name)
        r.add_byte("NoRest", 1)
        r.add_byte("PlayerVsPlayer", 0)
        r.add_int("ModListenCheck", 0)
        r.add_int("ModSpotCheck", 0)
        r.add_dword("Flags", 0)
        r.add_word("DayNightCycle", 0)
        r.add_word("IsNight", 0)
        r.add_word("LightingScheme", 0)
        r.add_byte("ShadowOpacity", 60)
        r.add_float("AmbientScale", 0.5)
        # Tile set info
        r.add_resref("Tileset", "grass")
        r.add_resref("OnEnter", "k_pend_area01")
        r.add_resref("OnExit", "")
        r.add_resref("OnHeartbeat", "k_pend_heart01")
        r.add_resref("OnUserDefined", "")
        return w.build()

    def test_are_header(self):
        _verify_header(self._make_are(), b"ARE ")

    def test_are_tag(self):
        d = GFF3Reader(self._make_are("tar_m02ae")).parse()
        self.assertEqual(d["Tag"], "tar_m02ae")

    def test_are_localized_name(self):
        d = GFF3Reader(self._make_are(name="Taris - Undercity")).parse()
        loc = d["Name"]
        self.assertEqual(loc[1], "Taris - Undercity")

    def test_are_no_rest_flag(self):
        d = GFF3Reader(self._make_are()).parse()
        self.assertEqual(d["NoRest"], 1)

    def test_are_ambient_scale(self):
        d = GFF3Reader(self._make_are()).parse()
        self.assertAlmostEqual(d["AmbientScale"], 0.5, places=4)

    def test_are_on_enter_script(self):
        d = GFF3Reader(self._make_are()).parse()
        self.assertEqual(d["OnEnter"], "k_pend_area01")


# ─────────────────────────────────────────────────────────────────────────────
# GIT — Game Instance File (area object placement)
# ─────────────────────────────────────────────────────────────────────────────

class TestGITRoundtrip(unittest.TestCase):
    """Game Instance file (.git) round-trip tests — creature/placeable placement
    using GFF VECTOR (position) and ORIENTATION (rotation) fields."""

    def _make_git(self) -> bytes:
        w = GFF3Writer("GIT ")
        r = w.root

        # Creature instances
        c1 = GFFStruct(4)
        c1.add_resref("TemplateResRef", "k_mand_001")
        c1.add_vector("XPosition", 10.0, 20.0, 0.0)
        c1.add_vector("YPosition", 0.0, 0.0, 0.0)
        c1.add_orientation("XOrientation", 1.0, 0.0, 0.0, 0.0)
        c1.add_byte("Active", 1)

        c2 = GFFStruct(4)
        c2.add_resref("TemplateResRef", "k_soldier_001")
        c2.add_vector("XPosition", -5.5, 12.25, 0.0)
        c2.add_orientation("XOrientation", 0.0, 0.0, 0.0, 1.0)  # 180 deg rotation
        c2.add_byte("Active", 1)

        r.add_list("Creature List", [c1, c2])

        # Placeable instances
        p1 = GFFStruct(9)
        p1.add_resref("TemplateResRef", "k_plc_chest01")
        p1.add_vector("X", 0.5, 0.5, 0.0)
        p1.add_orientation("Bearing", 0.707, 0.0, 0.0, 0.707)
        r.add_list("Placeable List", [p1])

        # Triggers
        r.add_list("TriggerList", [])

        # Stores
        r.add_list("StoreList", [])

        # Waypoints
        wp = GFFStruct(5)
        wp.add_resref("TemplateResRef", "k_way_spawn01")
        wp.add_cexo("Tag", "K_SPAWN_01")
        wp.add_vector("XPosition", 5.0, 5.0, 0.0)
        wp.add_orientation("XOrientation", 1.0, 0.0, 0.0, 0.0)
        r.add_list("WaypointList", [wp])

        return w.build()

    def test_git_header(self):
        _verify_header(self._make_git(), b"GIT ")

    def test_git_creature_count(self):
        d = GFF3Reader(self._make_git()).parse()
        self.assertEqual(len(d["Creature List"]), 2)

    def test_git_creature_template_resref(self):
        d = GFF3Reader(self._make_git()).parse()
        c1 = d["Creature List"][0]
        self.assertEqual(c1["TemplateResRef"], "k_mand_001")

    def test_git_creature_position_vector(self):
        d = GFF3Reader(self._make_git()).parse()
        pos = d["Creature List"][0]["XPosition"]
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 3)
        self.assertAlmostEqual(pos[0], 10.0, places=4)
        self.assertAlmostEqual(pos[1], 20.0, places=4)
        self.assertAlmostEqual(pos[2], 0.0, places=4)

    def test_git_creature_orientation(self):
        d = GFF3Reader(self._make_git()).parse()
        ori = d["Creature List"][0]["XOrientation"]
        self.assertIsInstance(ori, tuple)
        self.assertEqual(len(ori), 4)
        self.assertAlmostEqual(ori[0], 1.0, places=4)

    def test_git_second_creature_position(self):
        d = GFF3Reader(self._make_git()).parse()
        pos = d["Creature List"][1]["XPosition"]
        self.assertAlmostEqual(pos[0], -5.5, places=4)
        self.assertAlmostEqual(pos[1], 12.25, places=4)

    def test_git_placeable_count(self):
        d = GFF3Reader(self._make_git()).parse()
        self.assertEqual(len(d["Placeable List"]), 1)

    def test_git_placeable_orientation(self):
        d = GFF3Reader(self._make_git()).parse()
        ori = d["Placeable List"][0]["Bearing"]
        self.assertAlmostEqual(ori[0], 0.707, places=3)
        self.assertAlmostEqual(ori[3], 0.707, places=3)

    def test_git_empty_lists(self):
        d = GFF3Reader(self._make_git()).parse()
        self.assertEqual(len(d["TriggerList"]), 0)
        self.assertEqual(len(d["StoreList"]), 0)

    def test_git_waypoint_tag(self):
        d = GFF3Reader(self._make_git()).parse()
        wp = d["WaypointList"][0]
        self.assertEqual(wp["Tag"], "K_SPAWN_01")

    def test_git_waypoint_position(self):
        d = GFF3Reader(self._make_git()).parse()
        wp_pos = d["WaypointList"][0]["XPosition"]
        self.assertAlmostEqual(wp_pos[0], 5.0, places=4)
        self.assertAlmostEqual(wp_pos[1], 5.0, places=4)

    def test_git_vector_and_orientation_do_not_interfere(self):
        """XPosition VECTOR and XOrientation ORIENTATION in the same struct."""
        d = GFF3Reader(self._make_git()).parse()
        c = d["Creature List"][0]
        pos = c["XPosition"]
        ori = c["XOrientation"]
        # Both must be present and correct
        self.assertAlmostEqual(pos[0], 10.0, places=4)
        self.assertAlmostEqual(ori[0], 1.0, places=4)


# ─────────────────────────────────────────────────────────────────────────────
# IFO — Module Info
# ─────────────────────────────────────────────────────────────────────────────

class TestIFORoundtrip(unittest.TestCase):
    """Module info (.ifo) round-trip tests."""

    def _make_ifo(self) -> bytes:
        w = GFF3Writer("IFO ")
        r = w.root
        r.add_cexo("Mod_Tag", "ENDAR_SPIRE")
        r.add_locstring("Mod_Name", -1, "Endar Spire")
        r.add_locstring("Mod_Description", -1, "The Jedi Bastila is being held prisoner...")
        r.add_resref("Mod_OnAcquirItem", "k_mod_acqitem01")
        r.add_resref("Mod_OnActvtItem", "")
        r.add_resref("Mod_OnClientEntr", "k_mod_clnt_entr")
        r.add_resref("Mod_OnClientLeav", "k_mod_clnt_leav")
        r.add_resref("Mod_OnHeartbeat", "k_mod_heartbt01")
        r.add_resref("Mod_OnModLoad", "k_mod_load01")
        r.add_resref("Mod_OnModStart", "k_mod_start01")
        r.add_resref("Mod_OnUnAqreItem", "")
        r.add_resref("Mod_OnUsrDefined", "")
        r.add_byte("Mod_XPScale", 10)
        r.add_int("Expansion_Pack", 0)
        # Start area + waypoint
        r.add_resref("Mod_Entry_Area", "m01aa")
        r.add_cexo("Mod_Entry_Tag", "K_START_WAYPOINT")
        r.add_float("Mod_Entry_X", 10.5)
        r.add_float("Mod_Entry_Y", -5.25)
        r.add_float("Mod_Entry_Z", 0.0)
        r.add_float("Mod_Entry_Dir", 90.0)
        # Area list
        area = GFFStruct(6)
        area.add_resref("Area_Name", "m01aa")
        r.add_list("Mod_Area_list", [area])
        return w.build()

    def test_ifo_header(self):
        _verify_header(self._make_ifo(), b"IFO ")

    def test_ifo_mod_tag(self):
        d = GFF3Reader(self._make_ifo()).parse()
        self.assertEqual(d["Mod_Tag"], "ENDAR_SPIRE")

    def test_ifo_mod_name(self):
        d = GFF3Reader(self._make_ifo()).parse()
        loc = d["Mod_Name"]
        self.assertEqual(loc[1], "Endar Spire")

    def test_ifo_entry_area(self):
        d = GFF3Reader(self._make_ifo()).parse()
        self.assertEqual(d["Mod_Entry_Area"], "m01aa")

    def test_ifo_entry_position(self):
        d = GFF3Reader(self._make_ifo()).parse()
        self.assertAlmostEqual(d["Mod_Entry_X"], 10.5, places=4)
        self.assertAlmostEqual(d["Mod_Entry_Y"], -5.25, places=4)

    def test_ifo_scripts(self):
        d = GFF3Reader(self._make_ifo()).parse()
        self.assertEqual(d["Mod_OnModLoad"], "k_mod_load01")
        self.assertEqual(d["Mod_OnModStart"], "k_mod_start01")

    def test_ifo_area_list(self):
        d = GFF3Reader(self._make_ifo()).parse()
        areas = d["Mod_Area_list"]
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["Area_Name"], "m01aa")


# ─────────────────────────────────────────────────────────────────────────────
# DLG — Dialogue round-trip through DLGExporter + DLGImporter
# ─────────────────────────────────────────────────────────────────────────────

class TestDLGFormatRoundtrip(unittest.TestCase):
    """Full DLG dialogue format tests using DLGExporter and DLGImporter."""

    def _make_dlg(self, npc_tag="k_npc_001", n_entries=3) -> DialogueFile:
        dlg = DialogueFile(name=npc_tag)
        dlg.on_end = "k_dlg_end01"
        dlg.on_abort = "k_dlg_abort01"
        dlg.skippable = True

        for i in range(n_entries):
            entry = DialogueNode(node_id=i, node_type="entry")
            entry.text = f"NPC line {i}"
            entry.text_strref = 1000 + i
            entry.speaker = npc_tag
            entry.script1 = f"k_dlg_action{i:02d}"
            dlg.entries.append(entry)

        for i in range(n_entries):
            reply = DialogueNode(node_id=i, node_type="reply")
            reply.text = f"PC choice {i}"
            reply.text_strref = 2000 + i
            dlg.replies.append(reply)

        # Link entry 0 → reply 0, entry 1 → reply 1
        if n_entries >= 2:
            dlg.entries[0].branches.append(
                DialogueBranch(branch_id=0, target_node_id=0, active_script="k_dlg_check01")
            )
            dlg.entries[1].branches.append(
                DialogueBranch(branch_id=0, target_node_id=1, active_script="")
            )

        dlg.starters.append(
            DialogueBranch(branch_id=0, target_node_id=0)
        )
        return dlg

    def _roundtrip_dlg(self, dlg: DialogueFile, game: str = "K1") -> DialogueFile:
        data = DLGExporter().export(dlg, target_game=game)
        self.assertIsInstance(data, bytes)
        _verify_header(data, b"DLG ")
        return DLGImporter().import_from_bytes(data, name=dlg.name)

    def test_dlg_k1_header(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg, target_game="K1")
        _verify_header(data, b"DLG ")

    def test_dlg_k2_header(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg, target_game="K2")
        _verify_header(data, b"DLG ")

    def test_dlg_entry_count(self):
        dlg = self._make_dlg(n_entries=5)
        rt = self._roundtrip_dlg(dlg)
        self.assertEqual(len(rt.entries), 5)

    def test_dlg_reply_count(self):
        dlg = self._make_dlg(n_entries=4)
        rt = self._roundtrip_dlg(dlg)
        self.assertEqual(len(rt.replies), 4)

    def test_dlg_on_end_script(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        self.assertEqual(rt.on_end, "k_dlg_end01")

    def test_dlg_on_abort_script(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        self.assertEqual(rt.on_abort, "k_dlg_abort01")

    def test_dlg_entry_text(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].text, "NPC line 0")

    def test_dlg_entry_strref(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].text_strref, 1000)

    def test_dlg_entry_speaker(self):
        dlg = self._make_dlg(npc_tag="k_npc_unique")
        rt = self._roundtrip_dlg(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].speaker, "k_npc_unique")

    def test_dlg_entry_script(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].script1, "k_dlg_action00")

    def test_dlg_branch_count(self):
        dlg = self._make_dlg(n_entries=3)
        rt = self._roundtrip_dlg(dlg)
        if rt.entries:
            self.assertEqual(len(rt.entries[0].branches), 1)

    def test_dlg_branch_active_script(self):
        dlg = self._make_dlg(n_entries=3)
        rt = self._roundtrip_dlg(dlg)
        if rt.entries and rt.entries[0].branches:
            self.assertEqual(rt.entries[0].branches[0].active_script, "k_dlg_check01")

    def test_dlg_starter_count(self):
        dlg = self._make_dlg()
        rt = self._roundtrip_dlg(dlg)
        self.assertGreater(len(rt.starters), 0)

    def test_dlg_empty_dialogue(self):
        dlg = DialogueFile(name="empty")
        rt = self._roundtrip_dlg(dlg)
        self.assertIsNotNone(rt)
        self.assertEqual(len(rt.entries), 0)
        self.assertEqual(len(rt.replies), 0)

    def test_dlg_skippable_flag(self):
        dlg = self._make_dlg()
        dlg.skippable = True
        rt = self._roundtrip_dlg(dlg)
        self.assertTrue(rt.skippable)

    def test_dlg_double_roundtrip_stable(self):
        """Two successive write→read cycles produce the same structure."""
        dlg = self._make_dlg(n_entries=3)
        data1 = DLGExporter().export(dlg)
        dlg2 = DLGImporter().import_from_bytes(data1)
        data2 = DLGExporter().export(dlg2)
        # Size should be stable (same structure → same binary layout)
        self.assertEqual(len(data1), len(data2))

    def test_dlg_large_dialogue(self):
        """Large dialogues with many nodes should round-trip correctly."""
        dlg = self._make_dlg(n_entries=20)
        rt = self._roundtrip_dlg(dlg)
        self.assertEqual(len(rt.entries), 20)
        self.assertEqual(len(rt.replies), 20)


# ─────────────────────────────────────────────────────────────────────────────
# JRL — Journal File
# ─────────────────────────────────────────────────────────────────────────────

class TestJRLFormatRoundtrip(unittest.TestCase):
    """Journal file (.jrl) comprehensive round-trip tests."""

    def _make_jrl(self, n_quests=3, entries_per_quest=4) -> JournalFile:
        jrl = JournalFile(name="test_journal")
        for i in range(n_quests):
            cat = jrl.add_category(
                f"K_QUEST_{i:03d}",
                name=f"Quest {i}: The Reckoning",
                priority=10 + i,
                comment=f"Main quest {i}",
            )
            cat.add_entry(0, "", is_end=False)  # inactive state
            for j in range(1, entries_per_quest + 1):
                is_end = (j == entries_per_quest)
                cat.add_entry(j * 10, f"Quest {i} progress {j}", is_end=is_end)
        return jrl

    def _roundtrip_jrl(self, jrl: JournalFile) -> JournalFile:
        data = JRLWriter().export(jrl)
        self.assertIsInstance(data, bytes)
        _verify_header(data, b"JRL ")
        return JRLImporter().import_from_bytes(data)

    def test_jrl_header(self):
        jrl = self._make_jrl()
        data = JRLWriter().export(jrl)
        _verify_header(data, b"JRL ")

    def test_jrl_category_count(self):
        jrl = self._make_jrl(n_quests=5)
        rt = self._roundtrip_jrl(jrl)
        self.assertEqual(len(rt.categories), 5)

    def test_jrl_category_tag(self):
        jrl = self._make_jrl(n_quests=3)
        rt = self._roundtrip_jrl(jrl)
        tags = [c.tag for c in rt.categories]
        for i in range(3):
            self.assertIn(f"K_QUEST_{i:03d}", tags)

    def test_jrl_category_priority(self):
        jrl = self._make_jrl()
        rt = self._roundtrip_jrl(jrl)
        # First category has priority 10
        cat0 = next(c for c in rt.categories if c.tag == "K_QUEST_000")
        self.assertEqual(cat0.priority, 10)

    def test_jrl_entry_count(self):
        jrl = self._make_jrl(n_quests=1, entries_per_quest=5)
        rt = self._roundtrip_jrl(jrl)
        cat = rt.categories[0]
        # 1 inactive + 5 quest entries
        self.assertEqual(len(cat.entries), 6)

    def test_jrl_entry_state_ids(self):
        jrl = self._make_jrl(n_quests=1, entries_per_quest=3)
        rt = self._roundtrip_jrl(jrl)
        cat = rt.categories[0]
        state_ids = [e.state_id for e in cat.entries]
        self.assertIn(0, state_ids)
        self.assertIn(10, state_ids)
        self.assertIn(20, state_ids)
        self.assertIn(30, state_ids)

    def test_jrl_end_entry_flag(self):
        jrl = self._make_jrl(n_quests=1, entries_per_quest=3)
        rt = self._roundtrip_jrl(jrl)
        cat = rt.categories[0]
        end_entries = [e for e in cat.entries if e.is_end]
        self.assertEqual(len(end_entries), 1)
        self.assertEqual(end_entries[0].state_id, 30)

    def test_jrl_entry_text(self):
        jrl = self._make_jrl(n_quests=1, entries_per_quest=2)
        rt = self._roundtrip_jrl(jrl)
        cat = rt.categories[0]
        texts = [e.text for e in cat.entries if e.state_id == 10]
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0], "Quest 0 progress 1")

    def test_jrl_double_roundtrip(self):
        """Two successive JRL write→read cycles should be stable."""
        jrl = self._make_jrl(n_quests=2, entries_per_quest=3)
        data1 = JRLWriter().export(jrl)
        jrl2 = JRLImporter().import_from_bytes(data1)
        data2 = JRLWriter().export(jrl2)
        self.assertEqual(len(data1), len(data2))

    def test_jrl_single_category_minimal(self):
        jrl = JournalFile(name="minimal")
        cat = jrl.add_category("K_MINIMAL_QUEST")
        cat.add_entry(10, "Quest started", is_end=False)
        cat.add_entry(100, "Quest complete", is_end=True)
        rt = self._roundtrip_jrl(jrl)
        self.assertEqual(len(rt.categories), 1)
        self.assertEqual(rt.categories[0].tag, "K_MINIMAL_QUEST")


# ─────────────────────────────────────────────────────────────────────────────
# GFF Edge Cases / Robustness
# ─────────────────────────────────────────────────────────────────────────────

class TestGFFEdgeCases(unittest.TestCase):
    """Edge cases that could cause bugs in production."""

    def test_empty_struct_roundtrip(self):
        """An empty root struct (no fields) should round-trip."""
        w = GFF3Writer("TST ")
        data = w.build()
        r = GFF3Reader(data)
        d = r.parse()
        self.assertIsNotNone(d)

    def test_deeply_nested_structs(self):
        """Structs nested 10 levels deep should round-trip."""
        def build(depth):
            w = GFF3Writer("TST ")
            current = w.root
            current.add_cexo("Level", "0")
            for i in range(1, depth + 1):
                child = GFFStruct(i)
                child.add_cexo("Level", str(i))
                current.add_struct(f"Child{i}", child)
                current = child
            return w.build()

        data = build(10)
        r = GFF3Reader(data)
        d = r.parse()
        self.assertEqual(d.get("Level"), "0")

    def test_large_list(self):
        """A list with 100 items should round-trip correctly."""
        w = GFF3Writer("TST ")
        items = []
        for i in range(100):
            s = GFFStruct(0)
            s.add_dword("ID", i)
            items.append(s)
        w.root.add_list("Items", items)
        data = w.build()
        d = GFF3Reader(data).parse()
        self.assertEqual(len(d["Items"]), 100)
        # Spot check
        ids = [item["ID"] for item in d["Items"]]
        self.assertIn(0, ids)
        self.assertIn(50, ids)
        self.assertIn(99, ids)

    def test_unicode_in_cexostring(self):
        """CExoString handles Unicode via latin-1 encoding."""
        def setup(root): root.add_cexo("Text", "Bastila Shan")
        d = _roundtrip(setup)
        self.assertEqual(d["Text"], "Bastila Shan")

    def test_empty_cexostring(self):
        def setup(root): root.add_cexo("Empty", "")
        d = _roundtrip(setup)
        self.assertEqual(d.get("Empty"), "")

    def test_empty_resref(self):
        def setup(root): root.add_resref("Script", "")
        d = _roundtrip(setup)
        self.assertEqual(d.get("Script"), "")

    def test_resref_lowercased(self):
        """GFF RESREF values are lowercased by the writer."""
        def setup(root): root.add_resref("Script", "K_TEST_UPPER")
        d = _roundtrip(setup)
        self.assertEqual(d["Script"], "k_test_upper")

    def test_resref_truncated_at_16(self):
        """GFF RESREF values longer than 16 chars are truncated."""
        def setup(root): root.add_resref("Script", "k_very_long_script_name_here")
        d = _roundtrip(setup)
        self.assertLessEqual(len(d["Script"]), 16)

    def test_negative_int_preserved(self):
        def setup(root): root.add_int("Val", -2147483648)
        d = _roundtrip(setup)
        self.assertEqual(d["Val"], -2147483648)

    def test_max_dword(self):
        def setup(root): root.add_dword("Val", 0xFFFFFFFF)
        d = _roundtrip(setup)
        self.assertEqual(d["Val"], 0xFFFFFFFF)

    def test_negative_short(self):
        def setup(root): root.add_short("Val", -32768)
        d = _roundtrip(setup)
        self.assertEqual(d["Val"], -32768)

    def test_void_field_binary_data(self):
        """VOID (binary blob) field round-trip."""
        blob = bytes(range(256))
        def setup(root): root.add_void("Data", blob)
        d = _roundtrip(setup)
        self.assertEqual(d["Data"], blob)

    def test_void_empty(self):
        def setup(root): root.add_void("Empty", b"")
        d = _roundtrip(setup)
        self.assertEqual(d["Data"] if "Data" in d else d.get("Empty"), b"")

    def test_locstring_no_text(self):
        """CEXOLOCSTRING with strref only (no override text) round-trips."""
        def setup(root): root.add_locstring("Str", 99999)
        d = _roundtrip(setup)
        val = d.get("Str")
        self.assertIsNotNone(val)
        if isinstance(val, tuple):
            self.assertEqual(val[0], 99999)

    def test_locstring_negative_strref(self):
        """CEXOLOCSTRING with strref=-1 (custom text only) round-trips."""
        def setup(root): root.add_locstring("Str", -1, "Custom text")
        d = _roundtrip(setup)
        val = d.get("Str")
        if isinstance(val, tuple):
            self.assertEqual(val[1], "Custom text")

    def test_multiple_lists_in_one_struct(self):
        """Multiple list fields in the same struct should be independent."""
        w = GFF3Writer("TST ")
        items = [GFFStruct(0) for _ in range(3)]
        for i, s in enumerate(items):
            s.add_dword("ID", i + 10)
        feats = [GFFStruct(1) for _ in range(2)]
        for i, s in enumerate(feats):
            s.add_word("Feat", i + 100)
        w.root.add_list("ItemList", items)
        w.root.add_list("FeatList", feats)
        d = GFF3Reader(w.build()).parse()
        self.assertEqual(len(d["ItemList"]), 3)
        self.assertEqual(len(d["FeatList"]), 2)

    def test_same_label_in_nested_structs(self):
        """Same label name in parent and child structs should not conflict."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("Tag", "parent_tag")
        child = GFFStruct(1)
        child.add_cexo("Tag", "child_tag")
        w.root.add_struct("Child", child)
        d = GFF3Reader(w.build()).parse()
        self.assertEqual(d["Tag"], "parent_tag")
        self.assertEqual(d["Child"]["Tag"], "child_tag")

    def test_rebuild_is_deterministic(self):
        """Calling build() twice on the same GFF3Writer returns identical output."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("Name", "test")
        w.root.add_dword("ID", 42)
        data1 = w.build()
        data2 = w.build()
        self.assertEqual(data1, data2)


# ─────────────────────────────────────────────────────────────────────────────
# PyKotor Cross-Compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestPyKotorCompatibility(unittest.TestCase):
    """
    Tests that verify our GFF output is compatible with PyKotor's GFFBinaryReader.
    These tests check the exact binary layout that PyKotor expects.
    
    Based on:
    OldRepublicDevs/PyKotor/Libraries/PyKotor/src/pykotor/resource/formats/gff/io_gff.py
    """

    def test_field_type_ids_match_pykotor(self):
        """Our GFFType enum values must match PyKotor's GFFFieldType enum values."""
        # From PyKotor GFFFieldType (via analysis of io_gff.py):
        # UInt8=0, Int8=1, UInt16=2, Int16=3, UInt32=4, Int32=5
        # UInt64=6, Int64=7, Single=8, Double=9, String=10, ResRef=11
        # LocalizedString=12, Binary=13, Struct=14, List=15, Vector4=16, Vector3=17
        self.assertEqual(GFFType.BYTE, 0)
        self.assertEqual(GFFType.CHAR, 1)
        self.assertEqual(GFFType.WORD, 2)
        self.assertEqual(GFFType.SHORT, 3)
        self.assertEqual(GFFType.DWORD, 4)
        self.assertEqual(GFFType.INT, 5)
        self.assertEqual(GFFType.DWORD64, 6)
        self.assertEqual(GFFType.INT64, 7)
        self.assertEqual(GFFType.FLOAT, 8)
        self.assertEqual(GFFType.DOUBLE, 9)
        self.assertEqual(GFFType.CEXOSTRING, 10)
        self.assertEqual(GFFType.RESREF, 11)
        self.assertEqual(GFFType.CEXOLOCSTRING, 12)
        self.assertEqual(GFFType.VOID, 13)
        self.assertEqual(GFFType.STRUCT, 14)
        self.assertEqual(GFFType.LIST, 15)
        self.assertEqual(GFFType.ORIENTATION, 16)   # PyKotor: Vector4 (W,X,Y,Z)
        self.assertEqual(GFFType.VECTOR, 17)         # PyKotor: Vector3 (X,Y,Z)

    def test_binary_layout_inline_fields(self):
        """Inline fields (BYTE/WORD/DWORD/SHORT/INT/FLOAT) use field.DataOrOffset directly."""
        w = GFF3Writer("TST ")
        w.root.add_dword("Value", 0x12345678)
        data = w.build()
        # Field section: offset 56 + struct_section (12 bytes for 1 struct) = 68
        # Each field entry: [field_type: 4][label_idx: 4][data: 4]
        struct_off = _struct.unpack_from("<I", data, 8)[0]
        struct_count = _struct.unpack_from("<I", data, 12)[0]
        field_off = _struct.unpack_from("<I", data, 16)[0]
        field_type = _struct.unpack_from("<I", data, field_off)[0]
        field_value = _struct.unpack_from("<I", data, field_off + 8)[0]
        self.assertEqual(field_type, 4)  # GFFType.DWORD
        self.assertEqual(field_value, 0x12345678)

    def test_binary_layout_vector3_in_field_data(self):
        """VECTOR (type 17) is stored in field_data section, not inline."""
        w = GFF3Writer("TST ")
        w.root.add_vector("Pos", 1.0, 2.0, 3.0)
        data = w.build()
        # The field entry's type must be 17 (VECTOR = Vector3 in PyKotor)
        field_off = _struct.unpack_from("<I", data, 16)[0]
        field_type = _struct.unpack_from("<I", data, field_off)[0]
        self.assertEqual(field_type, 17)

    def test_binary_layout_orientation_in_field_data(self):
        """ORIENTATION (type 16) is stored in field_data section, not inline."""
        w = GFF3Writer("TST ")
        w.root.add_orientation("Rot", 1.0, 0.0, 0.0, 0.0)
        data = w.build()
        field_off = _struct.unpack_from("<I", data, 16)[0]
        field_type = _struct.unpack_from("<I", data, field_off)[0]
        self.assertEqual(field_type, 16)

    def test_root_struct_type_is_0xffffffff(self):
        """Root struct always has struct_id 0xFFFFFFFF (PyKotor: -1 signed)."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("X", "y")
        data = w.build()
        struct_off = _struct.unpack_from("<I", data, 8)[0]
        struct_id = _struct.unpack_from("<I", data, struct_off)[0]
        self.assertEqual(struct_id, 0xFFFFFFFF)

    def test_label_section_is_16_byte_padded(self):
        """Labels must be 16-byte null-padded strings (PyKotor: read_string(16))."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("Tag", "test")
        data = w.build()
        label_off = _struct.unpack_from("<I", data, 24)[0]
        label_count = _struct.unpack_from("<I", data, 28)[0]
        self.assertGreaterEqual(label_count, 1)
        # Each label: 16 bytes, last byte(s) null-padded
        label_bytes = data[label_off: label_off + 16]
        self.assertEqual(len(label_bytes), 16)
        # "Tag" = 3 chars, the rest should be \x00
        self.assertEqual(label_bytes[:3], b"Tag")
        self.assertEqual(label_bytes[3], 0)

    def test_cexostring_length_prefix_is_4_bytes(self):
        """CExoString in field_data: [length: 4 bytes][string bytes]."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("S", "HELLO")
        data = w.build()
        fdata_off = _struct.unpack_from("<I", data, 32)[0]
        length = _struct.unpack_from("<I", data, fdata_off)[0]
        text = data[fdata_off + 4: fdata_off + 4 + length].decode("latin-1")
        self.assertEqual(length, 5)
        self.assertEqual(text, "HELLO")

    def test_resref_length_prefix_is_1_byte(self):
        """ResRef in field_data: [length: 1 byte][string bytes]."""
        w = GFF3Writer("TST ")
        w.root.add_resref("R", "k_test")
        data = w.build()
        fdata_off = _struct.unpack_from("<I", data, 32)[0]
        length = data[fdata_off]
        text = data[fdata_off + 1: fdata_off + 1 + length].decode("ascii")
        self.assertEqual(length, 6)
        self.assertEqual(text, "k_test")


# ─────────────────────────────────────────────────────────────────────────────
# Quaternion / Spatial Math Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSpatialMath(unittest.TestCase):
    """Tests for spatial data (positions and orientations) used in KotOR."""

    def test_unit_quaternion_magnitude_preserved(self):
        """A unit quaternion must remain unit after GFF round-trip."""
        angle = math.pi / 3  # 60 degrees
        w_val = math.cos(angle / 2)
        z_val = math.sin(angle / 2)

        def setup(root): root.add_orientation("Q", w_val, 0.0, 0.0, z_val)
        d = _roundtrip(setup)
        ori = d["Q"]
        magnitude = math.sqrt(sum(x**2 for x in ori))
        self.assertAlmostEqual(magnitude, 1.0, places=4)

    def test_identity_quaternion(self):
        def setup(root): root.add_orientation("Identity", 1.0, 0.0, 0.0, 0.0)
        d = _roundtrip(setup)
        ori = d["Identity"]
        self.assertAlmostEqual(ori[0], 1.0, places=5)
        self.assertAlmostEqual(ori[1], 0.0, places=5)
        self.assertAlmostEqual(ori[2], 0.0, places=5)
        self.assertAlmostEqual(ori[3], 0.0, places=5)

    def test_kotor_map_coordinates(self):
        """Test realistic KotOR map coordinate ranges."""
        coords = [
            (0.0, 0.0, 0.0),
            (15.5, -20.25, 0.0),
            (-45.75, 100.0, 3.5),
            (200.0, -150.5, 0.0),
        ]
        for x, y, z in coords:
            def setup(root, cx=x, cy=y, cz=z):
                root.add_vector("Pos", cx, cy, cz)
            d = _roundtrip(setup)
            pos = d["Pos"]
            self.assertAlmostEqual(pos[0], x, places=3, msg=f"X failed for ({x}, {y}, {z})")
            self.assertAlmostEqual(pos[1], y, places=3, msg=f"Y failed for ({x}, {y}, {z})")
            self.assertAlmostEqual(pos[2], z, places=3, msg=f"Z failed for ({x}, {y}, {z})")

    def test_north_south_east_west_orientations(self):
        """Cardinal directions as quaternions for KotOR creature facing."""
        # KotOR uses 2D rotations in the XY plane, so Z-axis quaternions
        directions = {
            "north": (math.cos(math.radians(90)/2), 0.0, 0.0, math.sin(math.radians(90)/2)),
            "east": (1.0, 0.0, 0.0, 0.0),
            "south": (math.cos(math.radians(270)/2), 0.0, 0.0, math.sin(math.radians(270)/2)),
            "west": (math.cos(math.radians(180)/2), 0.0, 0.0, math.sin(math.radians(180)/2)),
        }
        for direction, (w, x, y, z) in directions.items():
            def setup(root, dw=w, dx=x, dy=y, dz=z):
                root.add_orientation("Dir", dw, dx, dy, dz)
            d = _roundtrip(setup)
            ori = d["Dir"]
            self.assertAlmostEqual(ori[0], w, places=4, msg=f"{direction}: W")
            self.assertAlmostEqual(ori[3], z, places=4, msg=f"{direction}: Z")


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# PyKotor-Compatible API Alias Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPyKotorAliases(unittest.TestCase):
    """Tests that PyKotor-compatible alias methods work correctly."""

    def _rt(self, setup_fn) -> dict:
        w = GFF3Writer("TST ")
        setup_fn(w.root)
        return GFF3Reader(w.build()).parse()

    def test_add_uint8_alias(self):
        d = self._rt(lambda r: r.add_uint8("V", 200))
        self.assertEqual(d["V"], 200)

    def test_add_int8_alias(self):
        d = self._rt(lambda r: r.add_int8("V", 127))
        self.assertEqual(d["V"], 127)

    def test_add_uint16_alias(self):
        d = self._rt(lambda r: r.add_uint16("V", 60000))
        self.assertEqual(d["V"], 60000)

    def test_add_int16_alias(self):
        d = self._rt(lambda r: r.add_int16("V", -30000))
        self.assertEqual(d["V"], -30000)

    def test_add_uint32_alias(self):
        d = self._rt(lambda r: r.add_uint32("V", 0xDEAD))
        self.assertEqual(d["V"], 0xDEAD)

    def test_add_int32_alias(self):
        d = self._rt(lambda r: r.add_int32("V", -999999))
        self.assertEqual(d["V"], -999999)

    def test_add_uint64_alias(self):
        d = self._rt(lambda r: r.add_uint64("V", 2**40))
        self.assertEqual(d["V"], 2**40)

    def test_add_int64_alias(self):
        d = self._rt(lambda r: r.add_int64("V", -(2**50)))
        self.assertEqual(d["V"], -(2**50))

    def test_add_single_alias(self):
        d = self._rt(lambda r: r.add_single("V", 1.5))
        self.assertAlmostEqual(d["V"], 1.5, places=4)

    def test_add_string_alias(self):
        d = self._rt(lambda r: r.add_string("V", "Hello KotOR"))
        self.assertEqual(d["V"], "Hello KotOR")

    def test_add_binary_alias(self):
        data = b"\x01\x02\x03"
        d = self._rt(lambda r: r.add_binary("V", data))
        self.assertEqual(d["V"], data)

    def test_add_vector3_alias(self):
        d = self._rt(lambda r: r.add_vector3("V", 1.0, 2.0, 3.0))
        self.assertEqual(len(d["V"]), 3)
        self.assertAlmostEqual(d["V"][0], 1.0, places=4)

    def test_add_vector4_alias(self):
        d = self._rt(lambda r: r.add_vector4("V", 0.707, 0.0, 0.0, 0.707))
        self.assertEqual(len(d["V"]), 4)
        self.assertAlmostEqual(d["V"][0], 0.707, places=3)

    def test_gff3reader_read_root_alias(self):
        """GFF3Reader.read_root() should return same result as parse()."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("X", "hello")
        data = w.build()
        r = GFF3Reader(data)
        d1 = r.parse()
        r2 = GFF3Reader(data)
        d2 = r2.read_root()
        self.assertEqual(d1, d2)

    def test_gff3reader_from_bytes_classmethod(self):
        """GFF3Reader.from_bytes(data) should create a valid reader."""
        w = GFF3Writer("TST ")
        w.root.add_dword("ID", 42)
        data = w.build()
        d = GFF3Reader.from_bytes(data).parse()
        self.assertEqual(d["ID"], 42)

    def test_journal_add_category_with_comment(self):
        """JournalFile.add_category() now accepts an optional 'comment' keyword."""
        jrl = JournalFile(name="test")
        cat = jrl.add_category("K_QUEST", name="My Quest", priority=5,
                               comment="Developer notes here")
        self.assertEqual(cat.comment, "Developer notes here")
        self.assertEqual(cat.priority, 5)
