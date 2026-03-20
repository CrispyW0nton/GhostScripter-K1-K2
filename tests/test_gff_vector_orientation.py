#!/usr/bin/env python3
"""
test_gff_vector_orientation.py — Tests for VECTOR and ORIENTATION GFF3 field types.

Covers:
  - VECTOR (type 17) write + read roundtrip via GFF3Writer / GFF3Reader
  - ORIENTATION (type 16) write + read roundtrip
  - Both fields in same GFF struct
  - Precision of floats across roundtrip
  - add_orientation() helper on GFFStruct
  - GFF3Writer._encode_field for ORIENTATION
  - Zero-value VECTOR and ORIENTATION
  - UTC-style creature struct with Position + Orientation
"""
import math
import struct as _struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.export.gff_writer import GFFType, GFFStruct, GFF3Writer
from ghostscripter.core.export.dlg_reader import GFF3Reader


# ── Helpers ────────────────────────────────────────────────────────────────────

def _roundtrip(setup_fn, file_type: str = "TST ") -> dict:
    """Write a GFF with setup_fn, parse it back, return root dict."""
    w = GFF3Writer(file_type)
    setup_fn(w.root)
    data = w.build()
    r = GFF3Reader(data)
    return r.parse()


def _approx_equal(a: float, b: float, places: int = 5) -> bool:
    return abs(a - b) < 10 ** (-places)


# ── VECTOR Tests ───────────────────────────────────────────────────────────────

class TestVectorRoundtrip(unittest.TestCase):

    def test_vector_type_id(self):
        """GFFType.VECTOR must be 17."""
        self.assertEqual(GFFType.VECTOR, 17)

    def test_basic_vector_roundtrip(self):
        def setup(root): root.add_vector("Position", 1.0, 2.5, -3.14)
        d = _roundtrip(setup)
        pos = d.get("Position")
        self.assertIsNotNone(pos)
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 3)

    def test_vector_x_value(self):
        def setup(root): root.add_vector("Pos", 10.5, 0.0, 0.0)
        d = _roundtrip(setup)
        self.assertAlmostEqual(d["Pos"][0], 10.5, places=4)

    def test_vector_y_value(self):
        def setup(root): root.add_vector("Pos", 0.0, 20.75, 0.0)
        d = _roundtrip(setup)
        self.assertAlmostEqual(d["Pos"][1], 20.75, places=4)

    def test_vector_z_value(self):
        def setup(root): root.add_vector("Pos", 0.0, 0.0, -5.0)
        d = _roundtrip(setup)
        self.assertAlmostEqual(d["Pos"][2], -5.0, places=4)

    def test_zero_vector(self):
        def setup(root): root.add_vector("Origin", 0.0, 0.0, 0.0)
        d = _roundtrip(setup)
        pos = d.get("Origin")
        self.assertEqual(pos, (0.0, 0.0, 0.0))

    def test_negative_all_components(self):
        def setup(root): root.add_vector("Neg", -1.5, -2.5, -3.5)
        d = _roundtrip(setup)
        pos = d["Neg"]
        self.assertAlmostEqual(pos[0], -1.5, places=4)
        self.assertAlmostEqual(pos[1], -2.5, places=4)
        self.assertAlmostEqual(pos[2], -3.5, places=4)

    def test_large_coordinates(self):
        def setup(root): root.add_vector("Far", 9999.9, -8888.8, 7777.7)
        d = _roundtrip(setup)
        pos = d["Far"]
        self.assertAlmostEqual(pos[0], 9999.9, places=1)

    def test_vector_field_in_field_data(self):
        """VECTOR is stored in field_data (not inline) — verify binary structure."""
        w = GFF3Writer("TST ")
        w.root.add_vector("P", 1.0, 2.0, 3.0)
        data = w.build()
        # Field type at field section offset (struct section = 12 bytes)
        field_type = _struct.unpack_from("<I", data, 56 + 12)[0]
        self.assertEqual(field_type, 17)  # GFFType.VECTOR

    def test_multiple_vectors_in_one_struct(self):
        def setup(root):
            root.add_vector("Pos", 1.0, 2.0, 3.0)
            root.add_vector("Dir", 0.0, 1.0, 0.0)
        d = _roundtrip(setup)
        self.assertIn("Pos", d)
        self.assertIn("Dir", d)
        self.assertAlmostEqual(d["Pos"][0], 1.0, places=4)
        self.assertAlmostEqual(d["Dir"][1], 1.0, places=4)


# ── ORIENTATION Tests ──────────────────────────────────────────────────────────

class TestOrientationRoundtrip(unittest.TestCase):

    def test_orientation_type_id(self):
        """GFFType.ORIENTATION must be 16."""
        self.assertEqual(GFFType.ORIENTATION, 16)

    def test_add_orientation_helper_exists(self):
        """GFFStruct must have add_orientation method."""
        s = GFFStruct()
        self.assertTrue(hasattr(s, "add_orientation"))

    def test_basic_orientation_roundtrip(self):
        def setup(root): root.add_orientation("Facing", 1.0, 0.0, 0.0, 0.0)
        d = _roundtrip(setup)
        ori = d.get("Facing")
        self.assertIsNotNone(ori)
        self.assertIsInstance(ori, tuple)
        self.assertEqual(len(ori), 4)

    def test_orientation_w_component(self):
        def setup(root): root.add_orientation("Q", 0.707, 0.0, 0.707, 0.0)
        d = _roundtrip(setup)
        ori = d["Q"]
        self.assertAlmostEqual(ori[0], 0.707, places=3)

    def test_orientation_x_component(self):
        def setup(root): root.add_orientation("Q", 0.0, 1.0, 0.0, 0.0)
        d = _roundtrip(setup)
        ori = d["Q"]
        self.assertAlmostEqual(ori[1], 1.0, places=4)

    def test_orientation_y_component(self):
        def setup(root): root.add_orientation("Q", 0.0, 0.0, 1.0, 0.0)
        d = _roundtrip(setup)
        ori = d["Q"]
        self.assertAlmostEqual(ori[2], 1.0, places=4)

    def test_orientation_z_component(self):
        def setup(root): root.add_orientation("Q", 0.0, 0.0, 0.0, 1.0)
        d = _roundtrip(setup)
        ori = d["Q"]
        self.assertAlmostEqual(ori[3], 1.0, places=4)

    def test_identity_quaternion(self):
        """Identity quaternion (1, 0, 0, 0) roundtrip."""
        def setup(root): root.add_orientation("Identity", 1.0, 0.0, 0.0, 0.0)
        d = _roundtrip(setup)
        ori = d["Identity"]
        self.assertAlmostEqual(ori[0], 1.0, places=4)
        self.assertAlmostEqual(ori[1], 0.0, places=4)
        self.assertAlmostEqual(ori[2], 0.0, places=4)
        self.assertAlmostEqual(ori[3], 0.0, places=4)

    def test_90_degree_rotation(self):
        """90-degree rotation around Z: quaternion (cos45, 0, 0, sin45)."""
        cos45 = math.cos(math.pi / 4)
        sin45 = math.sin(math.pi / 4)
        def setup(root): root.add_orientation("RotZ90", cos45, 0.0, 0.0, sin45)
        d = _roundtrip(setup)
        ori = d["RotZ90"]
        self.assertAlmostEqual(ori[0], cos45, places=4)
        self.assertAlmostEqual(ori[3], sin45, places=4)

    def test_orientation_field_in_field_data(self):
        """ORIENTATION is stored in field_data — verify binary field type."""
        w = GFF3Writer("TST ")
        w.root.add_orientation("Q", 1.0, 0.0, 0.0, 0.0)
        data = w.build()
        field_type = _struct.unpack_from("<I", data, 56 + 12)[0]
        self.assertEqual(field_type, 16)  # GFFType.ORIENTATION

    def test_orientation_size_in_binary(self):
        """ORIENTATION stores 4 floats (16 bytes) in field_data."""
        w = GFF3Writer("TST ")
        w.root.add_orientation("Q", 1.0, 0.0, 0.0, 0.0)
        data = w.build()
        # Get field_data offset from header
        fdata_off = _struct.unpack_from("<I", data, 32)[0]
        # First 16 bytes of field_data should be 4 floats
        floats = _struct.unpack_from("<ffff", data, fdata_off)
        self.assertAlmostEqual(floats[0], 1.0, places=4)
        self.assertAlmostEqual(floats[1], 0.0, places=4)


# ── Combined Vector + Orientation Tests ───────────────────────────────────────

class TestVectorOrientationCombined(unittest.TestCase):

    def test_utc_style_struct(self):
        """Simulate a creature UTC with Position + Orientation + Tag."""
        def setup(root):
            root.add_vector("Position", 42.5, -10.0, 0.0)
            root.add_orientation("Orientation", 1.0, 0.0, 0.0, 0.0)
            root.add_resref("TemplateResRef", "k_mand_001")
            root.add_cexo("Tag", "k_mandalorian")
            root.add_dword("Appearance_Type", 248)

        d = _roundtrip(setup, "UTC ")
        self.assertIn("Position", d)
        self.assertIn("Orientation", d)
        self.assertEqual(d.get("Tag"), "k_mandalorian")
        self.assertAlmostEqual(d["Position"][0], 42.5, places=4)
        self.assertAlmostEqual(d["Orientation"][0], 1.0, places=4)

    def test_vector_and_orientation_independent(self):
        """VECTOR and ORIENTATION fields must not interfere with each other."""
        def setup(root):
            root.add_vector("Pos", 5.0, 10.0, 15.0)
            root.add_orientation("Rot", 0.707, 0.0, 0.707, 0.0)
        d = _roundtrip(setup)
        pos = d["Pos"]
        rot = d["Rot"]
        self.assertAlmostEqual(pos[0], 5.0, places=4)
        self.assertAlmostEqual(rot[0], 0.707, places=3)

    def test_vector_does_not_corrupt_nearby_fields(self):
        """Fields after VECTOR should still be readable."""
        def setup(root):
            root.add_cexo("Before", "hello")
            root.add_vector("Middle", 1.0, 2.0, 3.0)
            root.add_cexo("After", "world")
        d = _roundtrip(setup)
        self.assertEqual(d.get("Before"), "hello")
        self.assertEqual(d.get("After"), "world")

    def test_orientation_does_not_corrupt_nearby_fields(self):
        """Fields after ORIENTATION should still be readable."""
        def setup(root):
            root.add_dword("ID", 999)
            root.add_orientation("Facing", 1.0, 0.0, 0.0, 0.0)
            root.add_resref("Script", "k_test")
        d = _roundtrip(setup)
        self.assertEqual(d.get("ID"), 999)
        self.assertEqual(d.get("Script"), "k_test")

    def test_are_style_git_struct(self):
        """Simulate a GIT creature instance with all spatial fields."""
        def setup(root):
            inner = GFFStruct(4)  # creature instance
            inner.add_resref("TemplateResRef", "k_kart_001")
            inner.add_vector("XPosition", 10.0, 20.0, 0.0)
            inner.add_orientation("XOrientation", 1.0, 0.0, 0.0, 0.0)
            inner.add_byte("Active", 1)
            root.add_list("Creature List", [inner])

        d = _roundtrip(setup, "GIT ")
        creatures = d.get("Creature List", [])
        self.assertEqual(len(creatures), 1)
        c = creatures[0]
        self.assertIn("XPosition", c)
        self.assertIn("XOrientation", c)
        pos = c["XPosition"]
        self.assertAlmostEqual(pos[0], 10.0, places=4)


# ── Precision Tests ────────────────────────────────────────────────────────────

class TestVectorOrientationPrecision(unittest.TestCase):

    def test_vector_float32_precision(self):
        """Verify that float32 precision is acceptable for KotOR coordinates."""
        # KotOR uses single-precision floats for all spatial data
        test_vals = [0.0, 1.0, -1.0, 3.14159, 100.001, -999.999]
        for v in test_vals:
            def setup(root, val=v): root.add_vector("P", val, 0.0, 0.0)
            d = _roundtrip(setup)
            recovered = d["P"][0]
            # float32 has ~7 significant decimal digits
            self.assertAlmostEqual(recovered, v, places=3,
                                   msg=f"Float32 precision failed for {v}")

    def test_orientation_normalised_unit_quaternion(self):
        """A unit quaternion should remain ~unit length after roundtrip."""
        # Normalised 45-deg rotation around Y
        angle = math.pi / 4
        w = math.cos(angle / 2)
        y = math.sin(angle / 2)

        def setup(root): root.add_orientation("Q", w, 0.0, y, 0.0)
        d = _roundtrip(setup)
        ori = d["Q"]
        mag_sq = ori[0]**2 + ori[1]**2 + ori[2]**2 + ori[3]**2
        self.assertAlmostEqual(mag_sq, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
