from __future__ import annotations

import asyncio
import base64
import json

from ghostscripter.core.nwscript.compiler_defs import install_pykotor_definitions


def _compile(source: str, game: str = "K2") -> dict:
    from ghostscripter.mcp.tools_pkg.handlers_write import _compile_script

    result = asyncio.run(
        _compile_script({"game": game, "source": source, "resref": "audit_test"})
    )
    return json.loads(result[0].text)


def test_pykotor_uses_complete_bundled_k2_tables():
    from pykotor.resource.formats.ncs import ncs_auto

    install_pykotor_definitions("K2")
    assert len(ncs_auto.TSL_FUNCTIONS) == 877
    assert len(ncs_auto.TSL_CONSTANTS) == 1805
    assert ncs_auto.TSL_FUNCTIONS[876].name == "RebuildPartyTable"
    assert any(c.name == "FORM_CONSULAR_ENDURING_FORCE_I" for c in ncs_auto.TSL_CONSTANTS)


def test_play_pazaak_signature_keeps_first_parameter():
    from pykotor.resource.formats.ncs import ncs_auto

    install_pykotor_definitions("K2")
    function = ncs_auto.TSL_FUNCTIONS[364]
    assert function.name == "PlayPazaak"
    assert [param.name for param in function.params] == [
        "nOpponentPazaakDeck",
        "sEndScript",
        "nMaxWager",
        "bShowTutorial",
        "oOpponent",
    ]


def test_valid_missing_k2_action_and_constant_compile():
    data = _compile(
        "void main() { int n = FORM_CONSULAR_ENDURING_FORCE_I; "
        "RebuildPartyTable(); PlayPazaak(0, \"end\", 100); }"
    )
    assert data["success"] is True, data
    assert base64.b64decode(data["data_base64"]).startswith(b"NCS V1.0")


def test_invalid_old_play_pazaak_signature_is_rejected():
    data = _compile('void main() { PlayPazaak("end", 100); }')
    assert data["success"] is False
    assert "error" in data

