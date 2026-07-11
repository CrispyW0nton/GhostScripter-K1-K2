from __future__ import annotations

import configparser
import io

import pytest

from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile


def _table(text: str, name: str = "appearance.2da") -> TwoDAFile:
    return TwoDAFile.from_text(text, name)


def test_changes_ini_uses_real_tslpatcher_sections():
    original = _table("""2DA V2.0

 label value
0 base  1
""")
    modified = _table("""2DA V2.0

 label value added
0 base  2     X
1 new   3     Y
""")
    output = modified.export_changes_ini(original)
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_file(io.StringIO(output))

    assert parser["2DAList"]["Table0"] == "appearance.2da"
    file_section = parser["appearance.2da"]
    assert file_section["AddColumn0"] == "appearance_add_column_0"
    assert file_section["ChangeRow0"] == "appearance_change_row_0"
    assert file_section["AddRow0"] == "appearance_add_row_0"
    assert parser["appearance_change_row_0"]["RowIndex"] == "0"
    assert parser["appearance_change_row_0"]["value"] == "2"
    assert parser["appearance_add_row_0"]["RowLabel"] == "1"


def test_changes_ini_refuses_unrepresentable_deletion():
    original = _table("""2DA V2.0

 value
0 1
1 2
""")
    modified = _table("""2DA V2.0

 value
0 1
""")
    with pytest.raises(ValueError, match="DeleteRow"):
        modified.export_changes_ini(original)


def test_inline_cell_and_column_edits_are_undoable():
    table = _table("""2DA V2.0

 value
0 old
""")
    assert table.set_cell_by_index(0, "value", "new")
    assert table.undo()
    assert table.rows[0].data["value"] == "old"

    table.add_column("extra", "x")
    assert "extra" in table.columns
    assert table.undo()
    assert "extra" not in table.columns

