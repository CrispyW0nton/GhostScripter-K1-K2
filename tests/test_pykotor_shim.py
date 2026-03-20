"""Tests for ghostscripter.core.pykotor_shim — PyKotor compatibility shim."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestShimInstallationImport(unittest.TestCase):
    def test_module_imports_cleanly(self):
        """ShimInstallation can be imported without pykotor installed."""
        from ghostscripter.core.pykotor_shim import ShimInstallation
        self.assertTrue(callable(ShimInstallation))

    def test_get_installation_factory_imports(self):
        from ghostscripter.core.pykotor_shim import get_installation
        self.assertTrue(callable(get_installation))

    def test_backed_by_pykotor_false_without_library(self):
        """Without pykotor installed, backed_by_pykotor should be False."""
        from ghostscripter.core import pykotor_shim
        if pykotor_shim._PYKOTOR_AVAILABLE:
            self.skipTest("pykotor is installed — skip internal-RM path test")
        shim = pykotor_shim.ShimInstallation("/tmp/nonexistent_path", "K1")
        self.assertFalse(shim.backed_by_pykotor)


class TestShimInstallationNonExistentPath(unittest.TestCase):
    """ShimInstallation with a path that doesn't exist should not crash."""

    def setUp(self):
        from ghostscripter.core.pykotor_shim import ShimInstallation
        self.shim = ShimInstallation("/tmp/nonexistent_kotor", "K1")

    def test_resource_returns_none(self):
        result = self.shim.resource("appearance", "2da")
        self.assertIsNone(result)

    def test_list_by_type_returns_empty(self):
        result = self.shim.list_by_type("2da")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_override_path_returns_none(self):
        result = self.shim.override_path()
        self.assertIsNone(result)

    def test_chitin_path_returns_none(self):
        result = self.shim.chitin_path()
        self.assertIsNone(result)

    def test_path_property(self):
        self.assertIsInstance(self.shim.path, Path)


class TestShimInstallationWithMockedRM(unittest.TestCase):
    """Test ShimInstallation using a mocked internal ResourceManager."""

    def _make_shim_with_mock_rm(self):
        """Create a ShimInstallation that has a mock ResourceManager."""
        from ghostscripter.core import pykotor_shim as shim_mod

        # Skip if pykotor is available (would use real backend)
        if shim_mod._PYKOTOR_AVAILABLE:
            self.skipTest("pykotor installed — would use real backend")

        mock_rm = MagicMock()
        mock_rm.read.return_value = b"MOCK_DATA"
        mock_rm.list_by_type.return_value = [
            MagicMock(resref="appearance"),
            MagicMock(resref="baseitems"),
        ]

        shim = shim_mod.ShimInstallation.__new__(shim_mod.ShimInstallation)
        shim._path = Path("/fake/kotor")
        shim._game_id = "K1"
        shim._real = None
        shim._rm = mock_rm
        return shim, mock_rm

    def test_resource_delegates_to_rm(self):
        shim, mock_rm = self._make_shim_with_mock_rm()
        result = shim.resource("appearance", "2da")
        self.assertEqual(result, b"MOCK_DATA")
        mock_rm.read.assert_called_once_with("appearance.2da")

    def test_list_by_type_delegates_to_rm(self):
        shim, mock_rm = self._make_shim_with_mock_rm()
        result = shim.list_by_type("2da")
        self.assertIsInstance(result, list)
        self.assertIn("appearance", result)

    def test_list_by_type_returns_sorted(self):
        from ghostscripter.core import pykotor_shim as shim_mod
        if shim_mod._PYKOTOR_AVAILABLE:
            self.skipTest("pykotor installed")

        mock_rm = MagicMock()
        mock_rm.list_by_type.return_value = [
            MagicMock(resref="z_item"),
            MagicMock(resref="a_item"),
            MagicMock(resref="m_item"),
        ]
        shim = shim_mod.ShimInstallation.__new__(shim_mod.ShimInstallation)
        shim._path = Path("/fake")
        shim._game_id = "K1"
        shim._real = None
        shim._rm = mock_rm
        result = shim.list_by_type("uti")
        self.assertEqual(result, sorted(result))

    def test_resource_returns_none_on_rm_exception(self):
        from ghostscripter.core import pykotor_shim as shim_mod
        if shim_mod._PYKOTOR_AVAILABLE:
            self.skipTest("pykotor installed")

        mock_rm = MagicMock()
        mock_rm.read.side_effect = Exception("disk error")
        shim = shim_mod.ShimInstallation.__new__(shim_mod.ShimInstallation)
        shim._path = Path("/fake")
        shim._game_id = "K1"
        shim._real = None
        shim._rm = mock_rm
        result = shim.resource("appearance", "2da")
        self.assertIsNone(result)


class TestGetInstallationFactory(unittest.TestCase):
    def test_returns_none_when_path_not_found(self):
        from ghostscripter.core.pykotor_shim import get_installation
        with patch("ghostscripter.mcp.tools_pkg._helpers._find_game_path", return_value=None):
            result = get_installation("K1")
        self.assertIsNone(result)

    def test_returns_none_for_nonexistent_explicit_path(self):
        from ghostscripter.core.pykotor_shim import get_installation
        result = get_installation("K1", path="/tmp/totally_fake_path_12345")
        self.assertIsNone(result)

    def test_returns_shim_for_valid_path(self):
        import tempfile
        import os
        from ghostscripter.core.pykotor_shim import get_installation, ShimInstallation

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal installation structure
            (Path(tmpdir) / "chitin.key").touch()
            result = get_installation("K1", path=tmpdir)
        # After the tmpdir is gone, result may be a ShimInstallation (path no longer exists)
        # Just verify the type was correct at construction time
        self.assertIsInstance(result, ShimInstallation)


class TestShimPykotorAvailableFlag(unittest.TestCase):
    def test_flag_is_bool(self):
        from ghostscripter.core import pykotor_shim
        self.assertIsInstance(pykotor_shim._PYKOTOR_AVAILABLE, bool)


if __name__ == "__main__":
    unittest.main()
