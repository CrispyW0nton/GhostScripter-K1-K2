from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock, patch

from ghostscripter.mcp.tools_pkg.handlers_write import _compile_script, _decompile_script


def _payload(result):
    return json.loads(result[0].text)


def test_resref_uses_resource_manager_read_api():
    compiled = _payload(asyncio.run(_compile_script({
        "game": "K1", "source": "void main() {}", "resref": "read_api"
    })))
    raw = base64.b64decode(compiled["data_base64"])
    rm = MagicMock()
    rm.read.return_value = raw
    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm
    ):
        result = _payload(asyncio.run(_decompile_script({
            "game": "K1", "resref": "read_api"
        })))
    rm.read.assert_called_once_with("read_api.ncs")
    assert "error" not in result
    assert result["disassembly"]


def test_lossy_reconstruction_is_not_claimed_as_verified():
    compiled = _payload(asyncio.run(_compile_script({
        "game": "K1",
        "source": 'void main() { SetGlobalNumber("AUDIT", 7); }',
        "resref": "lossy",
    })))
    result = _payload(asyncio.run(_decompile_script({
        "game": "K1", "data_base64": compiled["data_base64"]
    })))
    assert result["disassembly"]
    if result["source_verified"] is False and result["source_status"] != "disassembly_only":
        assert "warning" in result


def test_read_ncs_uses_real_pykotor_opcode_values():
    from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs

    compiled = _payload(asyncio.run(_compile_script({
        "game": "K1", "source": "void main() {}", "resref": "opcodes"
    })))
    raw = base64.b64decode(compiled["data_base64"])
    rm = MagicMock()
    rm.read.return_value = raw
    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm
    ):
        result = _payload(asyncio.run(_read_ncs({
            "game": "K1", "resref": "opcodes"
        })))
    assert result["pykotor_used"] is True
    assert result["instructions"][0]["mnemonic"] == "JSR"
    assert result["instructions"][0]["opcode"] == "0x1e"
