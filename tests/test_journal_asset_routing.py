"""
Tests for Asset Library → Journal Editor routing.

Double-clicking a .jrl resource (e.g. global.jrl) in the Asset Library must
open it in the Journal Editor tab, not dump a "Detailed viewer not yet
available" summary in the detail panel. Covers:

- open_asset_from_library() routes ".jrl" to _open_journal_asset()
- _open_journal_asset() parses the bytes and opens the Journal Editor
- an already-open Journal Editor tab is reused (journal swapped in-place)
- missing / unparsable data is logged, never raises
"""

import os
import sys
import unittest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ghostscripter.core.models.journal import JournalFile, JournalCategory
from ghostscripter.core.export.jrl_writer import JRLExporter


def _sample_jrl_bytes() -> bytes:
    """A minimal but real .jrl binary with one quest and two states."""
    jrl = JournalFile(name="global")
    cat = JournalCategory(tag="k_test_quest", name="Test Quest", priority=1)
    cat.add_entry(10, "Quest started.")
    cat.add_entry(20, "Quest finished.", is_end=True)
    jrl.categories.append(cat)
    return JRLExporter().export(jrl)


def _fake_tabs(widgets=()):
    """Duck-typed stand-in for MainWindow.editor_tabs (QTabWidget)."""
    tabs = mock.MagicMock()
    tabs.count.return_value = len(widgets)
    tabs.widget.side_effect = lambda i: widgets[i]
    return tabs


def _make_stub():
    """A MainWindow stand-in carrying only what _open_journal_asset touches."""
    from ghostscripter.ui.main_window import MainWindow

    stub = mock.MagicMock()
    stub.editor_tabs = _fake_tabs()
    stub.logs = []
    stub.log = stub.logs.append
    # Bind the real implementation under test onto the stub
    stub._open_journal_asset = MainWindow._open_journal_asset.__get__(stub)
    return stub


class TestJrlAssetRouting(unittest.TestCase):
    """open_asset_from_library must send .jrl to the Journal Editor."""

    @classmethod
    def setUpClass(cls):
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            cls._app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            raise unittest.SkipTest("Qt not available in this environment")

    def test_jrl_ext_routes_to_journal_asset_opener(self):
        from ghostscripter.ui.main_window import MainWindow

        stub = mock.MagicMock()
        stub.logs = []
        stub.log = stub.logs.append
        data = _sample_jrl_bytes()
        MainWindow.open_asset_from_library(stub, "global", ".jrl", data)

        stub._open_journal_asset.assert_called_once_with("global", data)
        stub._open_gff_asset.assert_not_called()

    def test_jrl_with_no_data_retries_resource_manager(self):
        from ghostscripter.ui.main_window import MainWindow

        stub = mock.MagicMock()
        stub.logs = []
        stub.log = stub.logs.append
        data = _sample_jrl_bytes()
        stub._read_asset_from_rm.return_value = data
        MainWindow.open_asset_from_library(stub, "global", ".jrl", None)

        stub._read_asset_from_rm.assert_called_once_with("global", ".jrl")
        stub._open_journal_asset.assert_called_once_with("global", data)

    def test_valid_jrl_opens_journal_editor(self):
        stub = _make_stub()
        stub._open_journal_asset("global", _sample_jrl_bytes())

        stub.open_journal_editor.assert_called_once()
        jrl = stub.open_journal_editor.call_args.kwargs["journal"]
        self.assertIsInstance(jrl, JournalFile)
        self.assertEqual(jrl.name, "global")
        self.assertEqual(len(jrl.categories), 1)
        self.assertEqual(jrl.categories[0].tag, "k_test_quest")
        self.assertEqual(len(jrl.categories[0].entries), 2)

    def test_existing_editor_tab_is_reused(self):
        from ghostscripter.ui.widgets.journal_editor_widget import JournalEditorWidget

        editor = JournalEditorWidget()
        stub = _make_stub()
        stub.editor_tabs = _fake_tabs([editor])
        stub._open_journal_asset("global", _sample_jrl_bytes())

        stub.open_journal_editor.assert_not_called()
        stub.editor_tabs.setCurrentIndex.assert_called_once_with(0)
        self.assertEqual(editor.journal.name, "global")
        self.assertEqual(editor.journal.categories[0].tag, "k_test_quest")
        self.assertFalse(editor.is_dirty)

    def test_no_data_logs_and_does_not_open(self):
        stub = _make_stub()
        stub._open_journal_asset("global", None)

        stub.open_journal_editor.assert_not_called()
        self.assertTrue(any("✗" in line for line in stub.logs))

    def test_garbage_data_logs_and_does_not_open(self):
        stub = _make_stub()
        stub._open_journal_asset("global", b"not a gff file at all")

        stub.open_journal_editor.assert_not_called()
        self.assertTrue(any("Could not parse" in line for line in stub.logs))


if __name__ == "__main__":
    unittest.main()
