from __future__ import annotations

from pathlib import Path

import pytest

from ghostscripter.core.export.erf_writer import ERFWriter, ExportEntry, RESTYPE_IDS
from ghostscripter.core.resource_manager import EXT_RESTYPE, ResourceEntry


def test_type_2045_accepts_both_documented_spellings():
    assert RESTYPE_IDS[".dft"] == 2045
    assert RESTYPE_IDS[".dtf"] == 2045
    assert EXT_RESTYPE[".dft"] == 2045
    assert EXT_RESTYPE[".dtf"] == 2045


def test_unknown_extension_is_never_silently_encoded_as_generic_type(tmp_path: Path):
    path = tmp_path / "mystery.nope"
    path.write_bytes(b"payload")
    with pytest.raises(ValueError, match="Unknown KotOR resource extension"):
        ExportEntry.from_file(path)
    with pytest.raises(ValueError, match="Unknown KotOR resource extension"):
        ERFWriter().add_resource("mystery", "nope", b"payload")


def test_resource_entry_preserves_unknown_override_extension():
    entry = ResourceEntry("mystery", -1, ".nope")
    assert entry.filename == "mystery.nope"

