"""KotOR Sound Set File (SSF V1.1) format constants and codecs.

KotOR assigns semantic names to the first 28 table entries.  Retail resources
can contain additional, undocumented entries, so readers must not discard the
tail.  New files use the common 40-entry layout emitted by PyKotor; callers
editing an existing file can pass its unknown entries back to the encoder.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable


SSF_MAGIC = b"SSF "
SSF_VERSION = b"V1.1"
SSF_HEADER_SIZE = 12

# Canonical KotOR order, matching PyKotor's SSFSound enum and the first 28
# fields in retail K1/K2 resources.
SSF_SLOT_NAMES: tuple[str, ...] = (
    "BATTLE_CRY_1",
    "BATTLE_CRY_2",
    "BATTLE_CRY_3",
    "BATTLE_CRY_4",
    "BATTLE_CRY_5",
    "BATTLE_CRY_6",
    "SELECT_1",
    "SELECT_2",
    "SELECT_3",
    "ATTACK_GRUNT_1",
    "ATTACK_GRUNT_2",
    "ATTACK_GRUNT_3",
    "PAIN_GRUNT_1",
    "PAIN_GRUNT_2",
    "LOW_HEALTH",
    "DEAD",
    "CRITICAL_HIT",
    "TARGET_IMMUNE",
    "LAY_MINE",
    "DISARM_MINE",
    "BEGIN_STEALTH",
    "BEGIN_SEARCH",
    "BEGIN_UNLOCK",
    "UNLOCK_FAILED",
    "UNLOCK_SUCCESS",
    "SEPARATED_FROM_PARTY",
    "REJOINED_PARTY",
    "POISONED",
)

SSF_SLOT_COUNT = len(SSF_SLOT_NAMES)

# PyKotor and the majority of retail K1/K2 SSFs use a 40-entry table: the 28
# named KotOR fields followed by 12 undocumented fields set to -1.  Some K1
# files are longer, which is why decoding is deliberately length-preserving.
SSF_DEFAULT_ENTRY_COUNT = 40
SSF_MAX_STRREF = 0xFFFFFFFE
SSF_UNSET_STRREF = 0xFFFFFFFF


def validate_strref(value: int) -> int:
    """Return *value* when it is representable in an SSF table.

    ``-1`` is the public sentinel for an unassigned sound.  Other values are
    unsigned 32-bit StrRefs; ``0xFFFFFFFF`` is reserved for that sentinel.
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("SSF StrRef must be an integer")
    if value < -1 or value > SSF_MAX_STRREF:
        raise ValueError(f"SSF StrRef {value} is outside -1..{SSF_MAX_STRREF}")
    return value


def decode_ssf(data: bytes) -> tuple[int, ...]:
    """Decode and validate an SSF V1.1 resource without dropping its tail."""

    if len(data) < SSF_HEADER_SIZE:
        raise ValueError(
            f"file is {len(data)} bytes; an SSF V1.1 header requires "
            f"{SSF_HEADER_SIZE} bytes"
        )
    if data[:4] != SSF_MAGIC:
        raise ValueError(f"unexpected file type {data[:4]!r}; expected {SSF_MAGIC!r}")
    if data[4:8] != SSF_VERSION:
        raise ValueError(
            f"unsupported version {data[4:8]!r}; expected {SSF_VERSION!r}"
        )

    data_offset = struct.unpack_from("<I", data, 8)[0]
    if data_offset < SSF_HEADER_SIZE:
        raise ValueError(
            f"table offset {data_offset} overlaps the {SSF_HEADER_SIZE}-byte header"
        )
    if data_offset > len(data):
        raise ValueError(
            f"table offset {data_offset} is beyond the {len(data)}-byte file"
        )

    table_size = len(data) - data_offset
    minimum_table_size = SSF_SLOT_COUNT * 4
    if table_size < minimum_table_size:
        raise ValueError(
            f"sound table is {table_size} bytes; {SSF_SLOT_COUNT} canonical "
            f"entries require at least {minimum_table_size} bytes"
        )
    if table_size % 4:
        raise ValueError(
            f"sound table size {table_size} is not a whole number of 32-bit entries"
        )

    raw_entries = struct.unpack_from(f"<{table_size // 4}I", data, data_offset)
    return tuple(-1 if value == SSF_UNSET_STRREF else value for value in raw_entries)


def encode_ssf(entries: Iterable[int]) -> bytes:
    """Encode a complete SSF table using the standard 12-byte V1.1 header."""

    values = tuple(validate_strref(value) for value in entries)
    if len(values) < SSF_SLOT_COUNT:
        raise ValueError(
            f"SSF requires at least {SSF_SLOT_COUNT} entries, got {len(values)}"
        )

    raw_values = tuple(SSF_UNSET_STRREF if value == -1 else value for value in values)
    return (
        SSF_MAGIC
        + SSF_VERSION
        + struct.pack("<I", SSF_HEADER_SIZE)
        + struct.pack(f"<{len(raw_values)}I", *raw_values)
    )
