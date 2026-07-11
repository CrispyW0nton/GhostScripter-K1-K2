"""Retail-validated KotOR/TSL LIP mouth-shape semantics.

The numeric indices are the file format.  Labels and phoneme groupings below
follow the experimentally revised Reone mapping (commit fef1401c) and were
cross-checked against retail K1/K2 LIP files.  In particular, index 0 is the
neutral/rest pose; the older community table that calls it ``EE`` is wrong.
"""

from __future__ import annotations


LIP_SHAPES: tuple[str, ...] = (
    "NEUTRAL",
    "IH_IY",
    "EH_ER_EY",
    "AA_AE_AH",
    "OW_OY",
    "UH_UW_W",
    "D_DH_S_Y_Z",
    "CH_JH_SH_ZH",
    "F_V",
    "G_HH_K_NG",
    "T_TH",
    "B_M_P",
    "L_N",
    "R",
    "AW_AY",
    "AO",
)


PHONEME_MAP: dict[str, int] = {
    "AA": 3,
    "AE": 3,
    "AH": 3,
    "AO": 15,
    "AW": 14,
    "AY": 14,
    "B": 11,
    "CH": 7,
    "D": 6,
    "DH": 6,
    "EH": 2,
    "ER": 2,
    "EY": 2,
    "F": 8,
    "G": 9,
    "HH": 9,
    "IH": 1,
    "IY": 1,
    "JH": 7,
    "K": 9,
    "L": 12,
    "M": 11,
    "N": 12,
    "NG": 9,
    "OW": 4,
    "OY": 4,
    "P": 11,
    "R": 13,
    "S": 6,
    "SH": 7,
    "T": 10,
    "TH": 10,
    "UH": 5,
    "UW": 5,
    "V": 8,
    "W": 5,
    "Y": 6,
    "Z": 6,
    "ZH": 7,
}


# Non-phoneme spellings emitted by older GhostScripter releases.  Ambiguous
# phoneme names (SH, L, etc.) intentionally use PHONEME_MAP instead.
LEGACY_SHAPE_ALIASES: dict[str, int] = {
    "EE": 1,
    "OH": 4,
    "OOH": 5,
    "STS": 7,
    "FV": 8,
    "MPB": 11,
    "TD": 12,
    "KG": 15,
}


def shape_index(value: str) -> int | None:
    """Resolve a canonical group, ARPAbet phoneme, or legacy group name."""

    key = value.strip().upper().replace("/", "_").replace("-", "_")
    try:
        return LIP_SHAPES.index(key)
    except ValueError:
        return PHONEME_MAP.get(key, LEGACY_SHAPE_ALIASES.get(key))


def shape_name(index: int) -> str:
    """Return the verified semantic label for a numeric LIP shape."""

    if not 0 <= index < len(LIP_SHAPES):
        raise ValueError(f"LIP shape index {index} is outside 0..15")
    return LIP_SHAPES[index]

