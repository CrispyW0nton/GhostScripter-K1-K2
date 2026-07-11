"""ResourceManager integration tests for Modules/ archive discovery."""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from ghostscripter.core.export.erf_writer import ERFWriter
from ghostscripter.core.resource_manager.resource_manager import (
    EXT_RESTYPE,
    ResourceManager,
)


def _write_erf(path: Path, file_type: str, resources: list[tuple[str, str, bytes]]) -> None:
    writer = ERFWriter(file_type)
    for resref, extension, data in resources:
        writer.add_resource(resref, extension, data)
    path.write_bytes(writer.build())


def _write_rim(path: Path, resources: list[tuple[str, str, bytes]]) -> None:
    """Write the small subset of RIM V1.0 needed by the reader tests."""
    table_offset = 20
    data_offset = table_offset + len(resources) * 32
    table = bytearray()
    payload = bytearray()

    for resource_id, (resref, extension, data) in enumerate(resources):
        restype = EXT_RESTYPE[f".{extension.lstrip('.').lower()}"]
        encoded_resref = resref.encode("ascii")[:16].ljust(16, b"\x00")
        table += encoded_resref
        table += struct.pack(
            "<IIII",
            restype,
            resource_id,
            data_offset + len(payload),
            len(data),
        )
        payload += data

    header = b"RIM " + b"V1.0" + struct.pack("<III", 0, len(resources), table_offset)
    path.write_bytes(header + table + payload)


class TestResourceManagerModuleArchives(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.game_dir = Path(self._tmp.name)
        # Deliberately mixed-case: discovery must work on case-sensitive hosts.
        self.modules_dir = self.game_dir / "MoDuLeS"
        self.modules_dir.mkdir()
        self.override_dir = self.game_dir / "override"
        self.override_dir.mkdir()
        self.texture_dir = self.game_dir / "TexturePacks"
        self.texture_dir.mkdir()

        _write_erf(
            self.modules_dir / "001test.mod",
            "MOD ",
            [
                ("module", "ifo", b"ifo-from-001-mod"),
                ("modbeats", "dlg", b"from-mod"),
                ("overridebeats", "dlg", b"under-override"),
                ("sharedarea", "git", b"git-from-001-mod"),
            ],
        )
        _write_erf(
            self.modules_dir / "001test_dlg.erf",
            "ERF ",
            [("erfonly", "dlg", b"from-erf")],
        )
        _write_rim(
            self.modules_dir / "001test_s.rim",
            [
                ("modbeats", "dlg", b"from-rim"),
                ("rimonly", "utc", b"from-rim-only"),
                ("module", "ifo", b"ambiguous-module-metadata"),
            ],
        )
        _write_rim(
            self.modules_dir / "002other.rim",
            [
                ("module", "ifo", b"ifo-from-002-rim"),
                ("sharedarea", "git", b"git-from-002-rim"),
            ],
        )
        _write_erf(
            self.texture_dir / "swpc_tex_tpa.erf",
            "ERF ",
            [("texture_only", "tpc", b"texture-data")],
        )
        (self.override_dir / "overridebeats.dlg").write_bytes(b"from-override")

        self.rm = ResourceManager()
        self.assertTrue(self.rm.load_game(self.game_dir))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_game_scans_module_erf_mod_and_rim_archives(self) -> None:
        self.assertEqual(len(self.rm._erfs), 3)  # MOD + module ERF + texture ERF
        self.assertEqual(len(self.rm._rims), 2)

    def test_read_resolves_each_archive_family(self) -> None:
        self.assertEqual(self.rm.read("erfonly.dlg"), b"from-erf")
        self.assertEqual(self.rm.read("rimonly.utc"), b"from-rim-only")
        self.assertEqual(self.rm.read("texture_only.tpc"), b"texture-data")

    def test_precedence_is_override_then_mod_then_rim(self) -> None:
        self.assertEqual(self.rm.read("overridebeats.dlg"), b"from-override")
        self.assertEqual(self.rm.read("modbeats.dlg"), b"from-mod")

    def test_list_by_type_includes_archives_and_deduplicates(self) -> None:
        dlg_entries = self.rm.list_by_type(".dlg")
        by_name = {entry.filename: entry for entry in dlg_entries}

        self.assertEqual(set(by_name), {"overridebeats.dlg", "modbeats.dlg", "erfonly.dlg"})
        self.assertIn("override", by_name["overridebeats.dlg"].source_file.lower())
        self.assertTrue(by_name["modbeats.dlg"].source_file.lower().endswith(".mod"))
        self.assertEqual(
            sum(entry.filename == "modbeats.dlg" for entry in dlg_entries),
            1,
        )

        tpc_entries = self.rm.list_by_type("tpc")
        self.assertEqual([entry.filename for entry in tpc_entries], ["texture_only.tpc"])

    def test_search_includes_module_resources(self) -> None:
        matches = self.rm.search("rimonly")
        self.assertEqual([entry.filename for entry in matches], ["rimonly.utc"])
        self.assertTrue(matches[0].source_file.lower().endswith(".rim"))

    def test_ambiguous_generic_module_ifo_is_not_globally_resolved(self) -> None:
        self.assertIsNone(self.rm.read("module.ifo"))
        self.assertNotIn("module.ifo", [entry.filename for entry in self.rm.list_by_type("ifo")])

    def test_module_context_resolves_the_requested_capsule_only(self) -> None:
        self.assertEqual(
            self.rm.read_from_module("001test", "module.ifo"),
            b"ifo-from-001-mod",
        )
        self.assertEqual(
            self.rm.read_from_module("002other", "module.ifo"),
            b"ifo-from-002-rim",
        )
        self.assertIsNone(self.rm.read_from_module("not-a-module", "module.ifo"))

    def test_contextual_resource_read_does_not_borrow_another_module(self) -> None:
        self.assertEqual(
            self.rm.read_from_module("001test", "sharedarea.git"),
            b"git-from-001-mod",
        )
        self.assertEqual(
            self.rm.read_from_module("002other", "sharedarea.git"),
            b"git-from-002-rim",
        )
        self.assertEqual(
            self.rm.module_ids_for_resource("sharedarea.git"),
            ("001test", "002other"),
        )

    def test_module_sources_preserve_capsule_precedence(self) -> None:
        sources = [path.name for path in self.rm.module_sources("001test")]
        self.assertEqual(
            sources,
            ["001test.mod", "001test_dlg.erf", "001test_s.rim"],
        )

    def test_reloading_does_not_duplicate_archive_readers_or_entries(self) -> None:
        self.assertTrue(self.rm.load_game(self.game_dir))
        self.assertEqual(len(self.rm._erfs), 3)
        self.assertEqual(len(self.rm._rims), 2)
        self.assertEqual(
            [entry.filename for entry in self.rm.list_by_type("dlg")].count("modbeats.dlg"),
            1,
        )

    def test_explicit_erf_addition_reindexes_and_invalidates_cached_read(self) -> None:
        self.assertEqual(self.rm.read("rimonly.utc"), b"from-rim-only")
        replacement = self.game_dir / "replacement.mod"
        _write_erf(replacement, "MOD ", [("rimonly", "utc", b"replacement")])

        self.assertTrue(self.rm.add_erf(replacement))
        self.assertEqual(self.rm.read("rimonly.utc"), b"replacement")
        listed = [entry for entry in self.rm.list_by_type("utc") if entry.resref == "rimonly"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(Path(listed[0].source_file), replacement)


if __name__ == "__main__":
    unittest.main()
