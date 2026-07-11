"""Capsule-context integration tests for module-facing MCP handlers."""
from __future__ import annotations

import asyncio
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct
from ghostscripter.core.models.tlk import TLKEntry, TLKFile
from ghostscripter.core.resource_manager.resource_manager import EXT_RESTYPE, ResourceManager
from ghostscripter.mcp.tools_pkg.handlers_composite import _get_area, _get_module
from ghostscripter.mcp.tools_pkg.handlers_query import _module_overview
from ghostscripter.mcp.tools_pkg.handlers_read import _read_ifo


def _write_rim(path: Path, resources: list[tuple[str, str, bytes]]) -> None:
    table_offset = 20
    data_offset = table_offset + len(resources) * 32
    table = bytearray()
    payload = bytearray()
    for resource_id, (resref, extension, data) in enumerate(resources):
        restype = EXT_RESTYPE[f".{extension}"]
        table += resref.encode("ascii")[:16].ljust(16, b"\x00")
        table += struct.pack(
            "<IIII", restype, resource_id, data_offset + len(payload), len(data),
        )
        payload += data
    path.write_bytes(
        b"RIM "
        + b"V1.0"
        + struct.pack("<III", 0, len(resources), table_offset)
        + table
        + payload
    )


def _ifo(module_id: str, area_resref: str) -> bytes:
    writer = GFF3Writer("IFO ")
    area = GFFStruct(6).add_resref("Area_Name", area_resref)
    writer.root.add_cexo("Mod_Tag", module_id)
    writer.root.add_resref("Mod_Entry_Area", area_resref)
    writer.root.add_list("Mod_Area_list", [area])
    return writer.build()


def _are(tag: str, name_strref: int) -> bytes:
    writer = GFF3Writer("ARE ")
    writer.root.add_locstring("Name", name_strref)
    writer.root.add_cexo("Tag", tag)
    return writer.build()


def _git(template: str) -> bytes:
    writer = GFF3Writer("GIT ")
    creature = GFFStruct(4).add_resref("TemplateResRef", template)
    creature.add_float("XPosition", 1.0).add_float("YPosition", 2.0)
    writer.root.add_list("Creature List", [creature])
    return writer.build()


def _decode(result) -> dict:
    return json.loads(result[0].text)


class TestModuleContextMCP(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.game_dir = Path(self.tempdir.name)
        modules = self.game_dir / "Modules"
        override = self.game_dir / "override"
        modules.mkdir()
        override.mkdir()

        _write_rim(modules / "alpha.rim", [
            ("module", "ifo", _ifo("alpha", "alpha_area")),
            ("alpha_area", "are", _are("alpha_tag", 1)),
            ("alpha_area", "git", _git("alpha_creature")),
            ("shared", "are", _are("alpha_shared", 1)),
        ])
        _write_rim(modules / "beta.rim", [
            ("module", "ifo", _ifo("beta", "beta_area")),
            ("beta_area", "are", _are("beta_tag", 2)),
            ("beta_area", "git", _git("beta_creature")),
            ("shared", "are", _are("beta_shared", 2)),
        ])

        tlk = TLKFile()
        for index, text in enumerate(("unused", "Alpha Live Name", "Beta Live Name")):
            entry = TLKEntry(index)
            entry.text = text
            tlk.entries.append(entry)
        (self.game_dir / "dialog.tlk").write_bytes(tlk.to_bytes())

        self.rm = ResourceManager()
        self.assertTrue(self.rm.load_game(self.game_dir))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_get_module_and_read_ifo_select_requested_capsule(self) -> None:
        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
            return_value=self.rm,
        ):
            alpha = _decode(asyncio.run(_get_module({
                "game": "K1", "module_id": "alpha",
            })))
            beta = _decode(asyncio.run(_get_module({
                "game": "K1", "module_id": "beta",
            })))
        self.assertEqual(alpha["tag"], "alpha")
        self.assertEqual(alpha["entry_area"], "alpha_area")
        self.assertEqual(beta["tag"], "beta")
        self.assertNotEqual(alpha["module_sources"], beta["module_sources"])

        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
            return_value=self.rm,
        ):
            read_alpha = _decode(asyncio.run(_read_ifo({
                "game": "K1", "resref": "alpha",
            })))
        self.assertEqual(read_alpha["tag"], "alpha")
        self.assertEqual(read_alpha["entry_area"], "alpha_area")

    def test_module_overview_uses_ifo_area_and_live_tlk_name(self) -> None:
        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
            return_value=self.rm,
        ):
            result = _decode(asyncio.run(_module_overview({
                "game": "K1", "moduleId": "alpha",
            })))
        self.assertEqual(result["area_resref"], "alpha_area")
        self.assertEqual(result["area_name"], "Alpha Live Name")
        self.assertEqual(result["creatures"][0]["template"], "alpha_creature")

    def test_get_area_discovers_unique_capsule_and_live_tlk_name(self) -> None:
        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
            return_value=self.rm,
        ):
            result = _decode(asyncio.run(_get_area({
                "game": "K1", "resref": "beta_area",
            })))
        self.assertEqual(result["module_id"], "beta")
        self.assertEqual(result["area_name"], "Beta Live Name")
        self.assertEqual(result["tag"], "beta_tag")

    def test_unknown_module_never_returns_first_generic_ifo(self) -> None:
        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
            return_value=self.rm,
        ):
            result = _decode(asyncio.run(_get_module({
                "game": "K1", "module_id": "missing",
            })))
        self.assertIn("error", result)
        self.assertIn("missing", result["error"])

    def test_get_area_rejects_ambiguous_capsule_without_module_id(self) -> None:
        with patch(
            "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
            return_value=self.rm,
        ):
            ambiguous = _decode(asyncio.run(_get_area({
                "game": "K1", "resref": "shared",
            })))
            explicit = _decode(asyncio.run(_get_area({
                "game": "K1", "resref": "shared", "module_id": "beta",
            })))
        self.assertIn("multiple modules", ambiguous["error"])
        self.assertEqual(explicit["module_id"], "beta")
        self.assertEqual(explicit["tag"], "beta_shared")


if __name__ == "__main__":
    unittest.main()
