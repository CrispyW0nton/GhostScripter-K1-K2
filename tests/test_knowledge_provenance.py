from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ghostscripter.core.nwscript.parser import NWScriptDB


ROOT = Path(__file__).resolve().parents[1]


def test_nwscript_manifest_matches_bundled_files_and_parser():
    scripts = ROOT / "resources" / "scripts"
    manifest = json.loads((scripts / "manifest.json").read_text(encoding="utf-8"))
    for game, relative in (("K1", "k1/nwscript.nss"), ("K2", "k2/nwscript.nss")):
        entry = manifest["files"][relative]
        path = scripts / relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        db = NWScriptDB.load(game)
        assert len(db.functions) == entry["function_count"]
        assert len(db.constant_declarations) == entry["constant_declaration_count"]
        assert len(db.constants) == entry["active_unique_constant_count"]

