"""Integrity tests for the typed readGFF/writeGFF interchange."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ghostscripter.core.gff_codec import (
    GFFSchemaError,
    TYPED_GFF_SCHEMA,
    read_typed_gff,
    write_typed_gff,
)
from ghostscripter.core.services import GFFService


def _all_field_types_gff() -> bytes:
    """Build one resource containing every canonical GFF field type (0-17)."""
    from pykotor.common.language import LocalizedString
    from pykotor.common.misc import ResRef
    from pykotor.resource.formats.gff import write_gff
    from pykotor.resource.formats.gff.gff_data import (
        GFF,
        GFFContent,
        GFFList,
        GFFStruct,
    )
    from pykotor.resource.type import ResourceType
    from utility.common.geometry import Vector3, Vector4

    gff = GFF(GFFContent.UTC)
    root = gff.root
    root.set_uint8("UInt8", 255)
    root.set_int8("Int8", -128)
    root.set_uint16("UInt16", 65535)
    root.set_int16("Int16", -32768)
    root.set_uint32("UInt32", 0xF1234567)
    root.set_int32("Int32", -2_000_000_000)
    root.set_uint64("UInt64", 0xFEDCBA9876543210)
    root.set_int64("Int64", -0x123456789ABCDEF)
    root.set_single("Single", -12.5)
    root.set_double("Double", 1.0 / 3.0)
    root.set_string("String", "Bastila — café")
    root.set_resref("ResRef", ResRef("MixedCaseRef"))
    root.set_locstring(
        "LocString",
        LocalizedString(-1, {0: "English male", 1: "English female", 2: "French male"}),
    )
    root.set_binary("Binary", b"\x00\xff\x10KotOR\x00")

    child = GFFStruct(0x12345678)
    child.set_int32("ChildValue", -42)
    root.set_struct("Struct", child)

    items = GFFList()
    first = GFFStruct(7)
    first.set_string("Name", "first")
    second = GFFStruct(8)
    second.set_resref("Template", ResRef("UPPER_REF"))
    items.append(first)
    items.append(second)
    root.set_list("List", items)
    root.set_vector4("Vector4", Vector4(1.25, -2.5, 3.75, -4.0))
    root.set_vector3("Vector3", Vector3(-5.5, 6.25, 7.0))

    target = bytearray()
    write_gff(gff, target, ResourceType.GFF)
    return bytes(target)


def test_all_18_field_types_json_roundtrip_byte_identical() -> None:
    original = _all_field_types_gff()
    document = read_typed_gff(original)

    # Exercise actual MCP transport semantics, not merely an in-memory dict.
    transported = json.loads(json.dumps(document))
    rebuilt = write_typed_gff(transported)

    assert document["schema"] == TYPED_GFF_SCHEMA
    assert document["file_type"] == "UTC "
    assert document["content"] == "UTC"
    assert document["file_version"] == "V3.2"
    assert document["complete"] is True
    assert [field["type_id"] for field in document["root"]["fields"]] == list(range(18))
    assert rebuilt == original


def test_64_bit_integers_use_decimal_strings_for_json_safety() -> None:
    document = read_typed_gff(_all_field_types_gff())
    fields = {field["label"]: field for field in document["root"]["fields"]}
    assert fields["UInt64"]["value"] == str(0xFEDCBA9876543210)
    assert fields["Int64"]["value"] == str(-0x123456789ABCDEF)


def test_localized_string_keeps_all_substrings_and_order() -> None:
    document = read_typed_gff(_all_field_types_gff())
    loc = next(field for field in document["root"]["fields"] if field["label"] == "LocString")
    assert loc["value"] == {
        "stringref": -1,
        "substrings": [
            {"id": 0, "text": "English male"},
            {"id": 1, "text": "English female"},
            {"id": 2, "text": "French male"},
        ],
    }


def test_depth_limited_preview_is_marked_incomplete_and_refused() -> None:
    preview = read_typed_gff(_all_field_types_gff(), max_depth=1)
    assert preview["complete"] is False
    with pytest.raises(GFFSchemaError, match="incomplete|truncated"):
        write_typed_gff(preview)


def test_untyped_service_write_requires_explicit_lossy_opt_in() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        GFFService.write("UTC ", {"MaxHitPoints": 60})

    data = GFFService.write(
        "UTC ", {"MaxHitPoints": 60}, allow_lossy=True
    )
    assert data[:8] == b"UTC V3.2"


def test_type_name_and_id_conflict_is_rejected() -> None:
    document = read_typed_gff(_all_field_types_gff())
    document["root"]["fields"][0]["type_id"] = 5
    with pytest.raises(GFFSchemaError, match="conflicts"):
        write_typed_gff(document)


def test_mcp_read_response_is_directly_writable_without_type_loss() -> None:
    from ghostscripter.mcp.tools_pkg.handlers_read import _read_gff
    from ghostscripter.mcp.tools_pkg.handlers_write import _write_gff

    original = _all_field_types_gff()

    class _ResourceReader:
        @staticmethod
        def read(filename: str) -> bytes | None:
            return original if filename == "alltypes.utc" else None

    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        return_value=_ResourceReader(),
    ):
        read_result = asyncio.run(
            _read_gff({"game": "K1", "resref": "alltypes", "restype": "utc"})
        )
    document = json.loads(read_result[0].text)
    assert document["complete"] is True
    assert document["source"]["size_bytes"] == len(original)

    write_result = asyncio.run(_write_gff({"document": document}))
    payload = json.loads(write_result[0].text)
    assert payload["fidelity"] == "lossless_typed"
    assert base64.b64decode(payload["data_base64"]) == original


@pytest.mark.parametrize(
    ("game", "install_path"),
    [
        ("K1", Path(r"C:\Program Files (x86)\Steam\steamapps\common\swkotor")),
        (
            "K2",
            Path(
                r"C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II"
            ),
        ),
    ],
)
def test_retail_global_jrl_typed_roundtrip_byte_identical(
    game: str,
    install_path: Path,
) -> None:
    if not install_path.is_dir():
        pytest.skip(f"{game} retail installation is not available")

    from ghostscripter.core.resource_manager.resource_manager import ResourceManager

    manager = ResourceManager()
    assert manager.load_game(install_path)
    original = manager.read("global.jrl")
    assert original is not None

    document = GFFService.parse_typed_bytes(original)
    transported = json.loads(json.dumps(document))
    rebuilt = GFFService.write_typed(transported)

    # PyKotor's canonical writer retains the original table ordering for both
    # shipped journals, allowing the strongest possible verification.
    assert rebuilt == original
