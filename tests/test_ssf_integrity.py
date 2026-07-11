from __future__ import annotations

import asyncio
import base64
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import mcp.types as types
import pytest

from ghostscripter.core.ssf import (
    SSF_DEFAULT_ENTRY_COUNT,
    SSF_SLOT_NAMES,
    decode_ssf,
    encode_ssf,
)
from ghostscripter.mcp.tools_pkg.handlers_query import _read_ssf
from ghostscripter.mcp.tools_pkg.handlers_write import _write_ssf


def _payload(response: list[types.TextContent]) -> dict:
    return json.loads(response[0].text)


def test_canonical_names_match_pykotor_ssfsound() -> None:
    from pykotor.resource.formats.ssf.ssf_data import SSFSound

    assert SSF_SLOT_NAMES == tuple(sound.name for sound in SSFSound)
    assert len(SSF_SLOT_NAMES) == 28


def test_new_file_encoding_matches_pykotor_byte_for_byte() -> None:
    from pykotor.resource.formats.ssf import SSF, SSFSound, bytes_ssf

    values = [20_000 + index for index in range(28)]
    pykotor_ssf = SSF()
    for sound, value in zip(SSFSound, values):
        pykotor_ssf.set_data(sound, value)

    assert encode_ssf(values + [-1] * 12) == bytes_ssf(pykotor_ssf)


def test_all_28_named_slots_round_trip_through_mcp_handlers() -> None:
    assigned = {name: 10_000 + index for index, name in enumerate(SSF_SLOT_NAMES)}
    written = _payload(
        asyncio.run(
            _write_ssf({"game": "K1", "resref": "all_slots", "slots": assigned})
        )
    )

    raw = base64.b64decode(written["data"])
    assert raw[:8] == b"SSF V1.1"
    assert len(raw) == 12 + SSF_DEFAULT_ENTRY_COUNT * 4 == 172
    assert written["slot_count"] == 28
    assert written["assigned_slot_count"] == 28
    assert written["entry_count"] == 40
    assert decode_ssf(raw) == tuple(assigned.values()) + (-1,) * 12

    rm = MagicMock()
    rm.read.return_value = raw
    with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
        read = _payload(
            asyncio.run(
                _read_ssf(
                    {"game": "K1", "resref": "all_slots", "resolve_tlk": False}
                )
            )
        )

    assert [(slot["name"], slot["strref"]) for slot in read["slots"]] == list(
        assigned.items()
    )
    assert read["slot_count"] == 28
    assert read["entry_count"] == 40
    assert read["unknown_slots"] == [
        {"index": index, "strref": -1} for index in range(28, 40)
    ]


def test_retail_length_unknown_tail_is_exposed_and_preserved() -> None:
    # K1 retail includes 208-byte SSFs (49 table entries), with meaningful
    # values observed beyond the 28 named KotOR slots.
    original_entries = list(range(49))
    original_entries[33] = 456_789
    raw = encode_ssf(original_entries)
    assert len(raw) == 208

    rm = MagicMock()
    rm.read.return_value = raw
    with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
        read = _payload(
            asyncio.run(
                _read_ssf({"game": "K1", "resref": "retail", "resolve_tlk": False})
            )
        )

    assert read["entry_count"] == 49
    assert read["unknown_slots"][5] == {"index": 33, "strref": 456_789}

    canonical = {slot["name"]: slot["strref"] for slot in read["slots"]}
    rewritten = _payload(
        asyncio.run(
            _write_ssf(
                {
                    "game": "K1",
                    "resref": "retail",
                    "slots": canonical,
                    "unknown_slots": read["unknown_slots"],
                }
            )
        )
    )
    assert base64.b64decode(rewritten["data"]) == raw


@pytest.mark.parametrize(
    "malformed",
    [
        b"",
        b"SSF\x00V1.1" + struct.pack("<I", 12) + bytes(28 * 4),
        b"SSF V1.0" + struct.pack("<I", 12) + bytes(28 * 4),
        b"SSF V1.1" + struct.pack("<I", 8) + bytes(28 * 4),
        b"SSF V1.1" + struct.pack("<I", 999) + bytes(28 * 4),
        b"SSF V1.1" + struct.pack("<I", 12) + bytes(27 * 4),
        b"SSF V1.1" + struct.pack("<I", 12) + bytes(28 * 4) + b"x",
    ],
)
def test_decode_rejects_malformed_header_version_offset_and_size(malformed: bytes) -> None:
    with pytest.raises(ValueError):
        decode_ssf(malformed)


def test_read_ssf_reports_malformed_input_as_error() -> None:
    rm = MagicMock()
    rm.read.return_value = b"SSF V1.0" + struct.pack("<I", 12) + bytes(28 * 4)
    with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
        result = _payload(
            asyncio.run(
                _read_ssf({"game": "K2", "resref": "invalid", "resolve_tlk": False})
            )
        )
    assert "error" in result
    assert "unsupported version" in result["error"]


def test_write_override_receives_data_b64_and_returns_json_object() -> None:
    override_response = [
        types.TextContent(
            type="text",
            text=json.dumps({"written": True, "path": "Override/test.ssf"}),
        )
    ]
    mocked_override = AsyncMock(return_value=override_response)
    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_write._write_override", mocked_override
    ):
        result = _payload(
            asyncio.run(
                _write_ssf(
                    {
                        "game": "K2",
                        "resref": "test",
                        "slots": {},
                        "write_override": True,
                    }
                )
            )
        )

    override_args = mocked_override.await_args.args[0]
    assert "data_b64" in override_args
    assert "data" not in override_args
    assert result["write_override"] == {
        "written": True,
        "path": "Override/test.ssf",
    }
