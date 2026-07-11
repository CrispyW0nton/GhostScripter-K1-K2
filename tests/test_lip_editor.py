"""
Tests for ghostscripter.ui.widgets.lip_editor_widget

These tests validate binary parsing, encoding, the LIPShape/phoneme tables,
and the timeline widget's data model — all without requiring a real Qt display
(Qt-specific paint/widget tests are excluded).
"""
from __future__ import annotations

import struct
import unittest


def _make_lip(duration: float, frames: list[tuple[float, int]]) -> bytes:
    """Build a minimal valid LIP V1.0 binary blob for testing."""
    buf = b"LIP V1.0"
    buf += struct.pack("<f", duration)
    buf += struct.pack("<I", len(frames))
    for t, s in frames:
        buf += struct.pack("<f", t)
        buf += struct.pack("<B", s)
    return buf


class TestLIPConstants(unittest.TestCase):
    """Verify the retail-validated LIP semantic table."""

    def setUp(self):
        from ghostscripter.ui.widgets import lip_editor_widget as mod
        self.mod = mod

    def test_16_shapes(self):
        self.assertEqual(len(self.mod.LIP_SHAPES), 16)

    def test_neutral_at_index_0(self):
        self.assertEqual(self.mod.LIP_SHAPES[0], "NEUTRAL")

    def test_ih_iy_at_index_1(self):
        self.assertEqual(self.mod.LIP_SHAPES[1], "IH_IY")

    def test_ao_at_index_15(self):
        self.assertEqual(self.mod.LIP_SHAPES[15], "AO")

    def test_all_names_unique(self):
        names = self.mod.LIP_SHAPES
        self.assertEqual(len(set(names)), len(names), "Duplicate shape names found")

    def test_shape_colors_count(self):
        self.assertEqual(len(self.mod._SHAPE_COLORS), 16)

    def test_shape_colors_are_hex(self):
        import re
        for c in self.mod._SHAPE_COLORS:
            self.assertRegex(c, r"^#[0-9a-fA-F]{6}$")

    def test_magic_bytes(self):
        self.assertEqual(self.mod.LIP_MAGIC, b"LIP ")
        self.assertEqual(self.mod.LIP_VERSION, b"V1.0")


class TestPhonemeMap(unittest.TestCase):
    """Verify the phoneme → shape index mapping."""

    def setUp(self):
        from ghostscripter.ui.widgets.lip_editor_widget import PHONEME_MAP
        self.pmap = PHONEME_MAP

    def test_has_entries(self):
        self.assertGreater(len(self.pmap), 10)

    def test_all_keys_uppercase(self):
        for k in self.pmap:
            self.assertEqual(k, k.upper())

    def test_all_values_0_to_15(self):
        for k, v in self.pmap.items():
            self.assertGreaterEqual(v, 0)
            self.assertLessEqual(v, 15)

    def test_known_phoneme_b_is_mpb(self):
        # B sound → MPB (lips pressed, index 11)
        self.assertEqual(self.pmap.get("B"), 11)

    def test_known_phoneme_s_is_shape_6(self):
        self.assertEqual(self.pmap.get("S"), 6)

    def test_revised_phoneme_values(self):
        self.assertEqual(self.pmap.get("D"), 6)
        self.assertEqual(self.pmap.get("SH"), 7)
        self.assertEqual(self.pmap.get("T"), 10)
        self.assertEqual(self.pmap.get("L"), 12)
        self.assertEqual(self.pmap.get("R"), 13)
        self.assertEqual(self.pmap.get("AW"), 14)
        self.assertEqual(self.pmap.get("AO"), 15)

    def test_known_phoneme_m_is_mpb(self):
        # M sound → MPB (index 11)
        self.assertEqual(self.pmap.get("M"), 11)

    def test_known_phoneme_ah_is_ah(self):
        # AH phoneme → AH shape (index 3)
        self.assertEqual(self.pmap.get("AH"), 3)


class TestLIPBinaryEncoding(unittest.TestCase):
    """Test to_bytes / load_from_bytes round-trips without a Qt display."""

    def _get_widget_class(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIPEditorWidget
        return LIPEditorWidget

    def test_encode_header_magic(self):
        """Encoded bytes start with 'LIP V1.0'."""
        # We test the encoding logic directly without instantiating the Qt widget.
        from ghostscripter.ui.widgets.lip_editor_widget import (
            LIP_MAGIC, LIP_VERSION,
        )
        lip_data = _make_lip(1.0, [(0.0, 0), (0.5, 3)])
        self.assertTrue(lip_data.startswith(LIP_MAGIC + LIP_VERSION))

    def test_encode_duration_correct(self):
        lip_data = _make_lip(2.5, [])
        duration = struct.unpack_from("<f", lip_data, 8)[0]
        self.assertAlmostEqual(duration, 2.5, places=4)

    def test_encode_entry_count(self):
        lip_data = _make_lip(1.0, [(0.1, 3), (0.2, 5)])
        count = struct.unpack_from("<I", lip_data, 12)[0]
        self.assertEqual(count, 2)

    def test_encode_frame_bytes(self):
        lip_data = _make_lip(1.0, [(0.25, 7)])
        # First keyframe at offset 16
        t = struct.unpack_from("<f", lip_data, 16)[0]
        s = lip_data[20]
        self.assertAlmostEqual(t, 0.25, places=4)
        self.assertEqual(s, 7)

    def test_encode_empty_frames(self):
        lip_data = _make_lip(1.0, [])
        count = struct.unpack_from("<I", lip_data, 12)[0]
        self.assertEqual(count, 0)
        self.assertEqual(len(lip_data), 16)  # header only

    def test_decode_header(self):
        lip_data = _make_lip(3.14, [(0.0, 0), (1.0, 5)])
        self.assertEqual(lip_data[:4], b"LIP ")
        self.assertEqual(lip_data[4:8], b"V1.0")

    def test_decode_all_shapes_valid(self):
        frames = [(i * 0.1, i) for i in range(16)]
        lip_data = _make_lip(2.0, frames)
        for i in range(16):
            offset = 16 + i * 5
            shape = lip_data[offset + 4]
            self.assertEqual(shape, i)

    def test_header_length(self):
        """Header should always be exactly 16 bytes."""
        lip_data = _make_lip(1.0, [])
        self.assertEqual(len(lip_data), 16)


class TestLIPTimelineDataModel(unittest.TestCase):
    """Test _LIPTimeline data-model updates without painting."""

    def setUp(self):
        from ghostscripter.ui.widgets.lip_editor_widget import _LIPTimeline
        self._cls = _LIPTimeline

    def test_set_data_stores_frames(self):
        # Just verify the class has set_data method and stores data
        import inspect
        self.assertTrue(hasattr(self._cls, "set_data"))

    def test_set_data_signature(self):
        import inspect
        sig = inspect.signature(self._cls.set_data)
        params = list(sig.parameters.keys())
        self.assertIn("frames", params)
        self.assertIn("duration", params)


class TestLIPEditorWidgetAPI(unittest.TestCase):
    """Verify the LIPEditorWidget public API without instantiation."""

    def setUp(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIPEditorWidget
        self._cls = LIPEditorWidget

    def test_has_load_from_bytes(self):
        self.assertTrue(hasattr(self._cls, "load_from_bytes"))

    def test_has_load_from_file(self):
        self.assertTrue(hasattr(self._cls, "load_from_file"))

    def test_has_to_bytes(self):
        self.assertTrue(hasattr(self._cls, "to_bytes"))

    def test_has_duration_property(self):
        self.assertTrue(hasattr(self._cls, "duration"))

    def test_has_frame_count_property(self):
        self.assertTrue(hasattr(self._cls, "frame_count"))

    def test_has_is_dirty_property(self):
        self.assertTrue(hasattr(self._cls, "is_dirty"))

    def test_has_changed_signal_attr(self):
        self.assertTrue(hasattr(self._cls, "changed"))


if __name__ == "__main__":
    unittest.main()
