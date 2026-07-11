from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from ghostscripter.core.resource_manager import ResourceManager
from ghostscripter.mcp.tools_pkg.handlers_composite import _get_creature


K1 = Path(r"C:\Program Files (x86)\Steam\steamapps\common\swkotor")


def test_retail_utc_uses_real_equipment_struct_ids_and_script_hooks():
    if not (K1 / "chitin.key").exists():
        return
    rm = ResourceManager()
    assert rm.load_game(K1)
    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm
    ):
        result = asyncio.run(_get_creature({
            "game": "K1", "resref": "p_bastilla", "include_tlk": False
        }))
    data = json.loads(result[0].text)
    assert data["equipment"]["armor"]["resref"] == "g_a_clothes01"
    assert data["scripts"]["ScriptOnNotice"] == "k_hen_percept01"
    assert "ScriptPerceived" not in data["scripts"]

