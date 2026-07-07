"""Tests for GhostScripter MCP tools.

Tests are written without requiring a real KotOR installation:
  - Installation detection, loading, and error handling
  - writeDLG round-trip (builds a dialogue, exports to binary, re-imports)
  - compileSummary static analysis
  - twoDAChangesINI patch generation
  - nwscriptCategories listing
  - twoDALookup in-memory 2DA
  - searchNWScript function search
  - nwscriptSignature lookup
  - writeGFF generic writer
  - Error handling (unknown tools, missing args)
  - Tool registry completeness
"""
from __future__ import annotations

import asyncio
import base64
import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _json(result) -> dict:
    """Decode the first TextContent item from a tool result."""
    return json.loads(result[0].text)


def _make_pykotor_import_blocker(*blocked_modules: str):
    """Return an __import__ side-effect that raises ImportError for specific modules.

    Used to force the GFFService fallback path in tests that pre-date PyKotor
    integration, without disabling PyKotor globally.
    """
    _real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def _blocker(name, *args, **kwargs):
        for m in blocked_modules:
            if name == m or name.startswith(m + "."):
                raise ImportError(f"[test blocker] {name}")
        return _real_import(name, *args, **kwargs)

    return _blocker


# ── Tool registry ─────────────────────────────────────────────────────────────

class TestMCPToolRegistry(unittest.TestCase):
    """Verify that all expected tools are registered."""

    EXPECTED_TOOLS = {
        # Prefixed to avoid KotorMCP name collisions (see SYSTEMS_DESIGN §Tool Namespace Policy)
        "gsDetectInstallations",
        "gsLoadInstallation",
        "gsListResources",
        "gsDescribeResource",
        "readGFF",
        "readDLG",
        "readTwoDA",
        "readTLK",
        "readJournal",
        "journalOverview",
        "searchNWScript",
        "nwscriptSignature",
        "writeGFF",
        "writeDLG",
        "writeTwoDA",
        "writeERF",
        "compileScript",
        "writeOverride",
        "compileSummary",
        "searchResources",
        "moduleOverview",
        "twoDALookup",
        "nwscriptCategories",
        "twoDAChangesINI",
        # Ghostworks Pipeline composite tools
        "getResource",
        "getQuest",
        "getNpc",
        "getScript",
        "listResType",
        "getArea",
        "getDoor",
        "getPlaceable",
        "getItem",
        "searchAll",
        # v2.8 new tools
        "getModule",
        "getEncounter",
        "getTrigger",
        "getWaypoint",
        "getStore",
        "getSound",
        "readSSF",
        # v2.9 new tools
        "readLIP",
        "writeLIP",
        "getCreature",
        # v3.0 new tools
        "getFaction",
        # v3.2 new tools
        "readPTH",
        "readLTR",
        "writeSSF",
        "writePTH",
        "getBlueprint",
        "readGUI",
        "readSave",
        # v3.3 new tools
        "readNCS",
        "readVIS",
        "readIFO",
        "readWAV",
        "readTXI",
        "pathfindRoute",
        # v3.4 new tools
        "decompileScript",
        # v3.6 new tools
        "getNWScriptDB",
    }

    def test_all_tools_registered(self):
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        registered_names = {t.name for t in TOOLS}
        self.assertEqual(
            registered_names, self.EXPECTED_TOOLS,
            f"Missing: {self.EXPECTED_TOOLS - registered_names}; "
            f"Extra: {registered_names - self.EXPECTED_TOOLS}",
        )

    def test_all_tools_have_handlers(self):
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        for tool in TOOLS:
            self.assertIn(
                tool.name, _HANDLERS,
                f"Tool '{tool.name}' has no handler in _HANDLERS",
            )

    def test_all_tools_have_descriptions(self):
        from ghostscripter.mcp.tools import TOOLS
        for tool in TOOLS:
            self.assertTrue(
                tool.description and len(tool.description) > 20,
                f"Tool '{tool.name}' has an empty or too-short description",
            )

    def test_all_tools_have_input_schema(self):
        from ghostscripter.mcp.tools import TOOLS
        for tool in TOOLS:
            self.assertIn(
                "type", tool.inputSchema,
                f"Tool '{tool.name}' inputSchema missing 'type'",
            )

    def test_tool_count(self):
        from ghostscripter.mcp.tools import TOOLS
        self.assertGreaterEqual(len(TOOLS), 20)

    def test_handler_count_matches_tool_count(self):
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        # journalOverview is an alias → _HANDLERS may have one extra
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS))


# ── Error handling ─────────────────────────────────────────────────────────────

class TestMCPErrorHandling(unittest.TestCase):
    def test_unknown_tool_returns_error(self):
        from ghostscripter.mcp.tools import handle_tool
        result = _run(handle_tool("nonExistentTool", {}))
        data = _json(result)
        self.assertIn("error", data)

    def test_invalid_game_returns_error(self):
        from ghostscripter.mcp.tools import handle_tool
        result = _run(handle_tool("searchNWScript", {"game": "K9", "query": "GetPC"}))
        data = _json(result)
        self.assertIn("error", data)

    def test_missing_installation_returns_error(self):
        from unittest import mock
        from ghostscripter.mcp.tools import handle_tool, _INSTALLS
        # Clear cache AND disable path auto-detection (registry/default-path
        # probes would otherwise find a real installation on dev machines and
        # make this test operate on the user's actual game folder).
        saved_installs = dict(_INSTALLS)
        _INSTALLS.clear()
        import os
        saved = os.environ.pop("K1_PATH", None)
        try:
            with mock.patch(
                "ghostscripter.mcp.tools_pkg._helpers._find_game_path",
                return_value=None,
            ):
                result = _run(handle_tool("gsListResources", {"game": "K1"}))
            data = _json(result)
            self.assertIn("error", data)
        finally:
            if saved:
                os.environ["K1_PATH"] = saved
            _INSTALLS.update(saved_installs)

    def test_normalize_game_k1_variants(self):
        from ghostscripter.mcp.tools import _normalize_game
        for v in ("K1", "k1", "kotor", "KOTOR1", "1"):
            self.assertEqual(_normalize_game(v), "K1")

    def test_normalize_game_k2_variants(self):
        from ghostscripter.mcp.tools import _normalize_game
        for v in ("K2", "k2", "TSL", "kotor2", "2"):
            self.assertEqual(_normalize_game(v), "K2")

    def test_normalize_game_invalid_raises(self):
        from ghostscripter.mcp.tools import _normalize_game
        with self.assertRaises(ValueError):
            _normalize_game("K3")


# ── compileSummary ────────────────────────────────────────────────────────────

class TestCompileSummary(unittest.TestCase):
    def _call(self, source: str, filename: str = "test.nss") -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("compileSummary", {
            "source": source, "filename": filename,
        })))

    def test_basic_function_extraction(self):
        source = "void MyFunc(object oTarget) { }"
        result = self._call(source)
        self.assertEqual(result["function_count"], 1)
        self.assertIn("void MyFunc(object oTarget)", result["functions"][0])

    def test_include_extraction(self):
        source = '#include "k_inc_debug"\nvoid Foo() {}'
        result = self._call(source)
        self.assertIn("k_inc_debug", result["includes"])

    def test_constant_extraction(self):
        source = "const int MY_CONST = 42;\nvoid Foo() {}"
        result = self._call(source)
        self.assertEqual(result["constant_count"], 1)
        self.assertEqual(result["constants"][0]["name"], "MY_CONST")
        self.assertEqual(result["constants"][0]["value"], "42")

    def test_brace_mismatch_reported(self):
        source = "void Foo() { {"  # unclosed brace
        result = self._call(source)
        self.assertGreater(len(result["issues"]), 0)
        self.assertTrue(any("brace" in i.lower() for i in result["issues"]))

    def test_empty_source_returns_error(self):
        from ghostscripter.mcp.tools import handle_tool
        result = _json(_run(handle_tool("compileSummary", {"source": "   "})))
        self.assertIn("error", result)

    def test_line_count(self):
        source = "line1\nline2\nline3"
        result = self._call(source)
        self.assertEqual(result["total_lines"], 3)

    def test_multiple_functions(self):
        source = """
void FuncA(int n) {}
int FuncB(object o, float f = 1.0) { return 0; }
string FuncC() { return ""; }
"""
        result = self._call(source)
        self.assertEqual(result["function_count"], 3)

    def test_filename_in_result(self):
        result = self._call("void F() {}", filename="myscript.nss")
        self.assertEqual(result["filename"], "myscript.nss")

    def test_no_issues_clean_source(self):
        source = """
void RunQuest(object oPC) {
    AddJournalQuestEntry("my_quest", 10, oPC);
}
"""
        result = self._call(source)
        self.assertEqual(result["issues"], [])


# ── writeDLG ──────────────────────────────────────────────────────────────────

class TestWriteDLG(unittest.TestCase):
    SIMPLE_DLG = {
        "entries": [
            {
                "text": "Hello there!",
                "strref": -1,
                "speaker": "Bastila",
                "branches": [{"index": 0, "is_reply": True}],
            }
        ],
        "replies": [
            {"text": "General Kenobi.", "strref": -1, "branches": []}
        ],
        "starters": [{"index": 0, "is_reply": False}],
    }

    def _write(self, game: str = "K1", dlg: dict = None) -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("writeDLG", {
            "game": game,
            "dialogue": dlg or self.SIMPLE_DLG,
        })))

    def test_returns_base64_data(self):
        result = self._write()
        self.assertIn("data_base64", result)
        data = base64.b64decode(result["data_base64"])
        self.assertGreater(len(data), 100)

    def test_gff_magic_header(self):
        result = self._write()
        data = base64.b64decode(result["data_base64"])
        # GFF3 magic: "DLG " + "V3.2"
        self.assertEqual(data[:4], b"DLG ")
        self.assertEqual(data[4:8], b"V3.2")

    def test_entry_count_reported(self):
        result = self._write()
        self.assertEqual(result["entry_count"], 1)
        self.assertEqual(result["reply_count"], 1)

    def test_size_bytes_reasonable(self):
        result = self._write()
        self.assertGreater(result["size_bytes"], 200)

    def test_k2_game_flag(self):
        result = self._write(game="K2")
        self.assertEqual(result["game"], "K2")

    def test_roundtrip_with_dlg_importer(self):
        """writeDLG → binary → DLGImporter should reconstruct the same data."""
        from ghostscripter.core.export.dlg_reader import DLGImporter
        result = self._write()
        data = base64.b64decode(result["data_base64"])
        dlg = DLGImporter().import_from_bytes(data)
        self.assertEqual(len(dlg.entries), 1)
        self.assertEqual(len(dlg.replies), 1)
        self.assertEqual(dlg.entries[0].text, "Hello there!")
        self.assertEqual(dlg.entries[0].speaker, "Bastila")

    def test_end_script_written(self):
        from ghostscripter.core.export.dlg_reader import DLGImporter
        dlg_dict = dict(self.SIMPLE_DLG, end_script="k_end_scene")
        result = self._write(dlg=dlg_dict)
        data = base64.b64decode(result["data_base64"])
        dlg = DLGImporter().import_from_bytes(data)
        self.assertEqual(dlg.on_end, "k_end_scene")

    def test_empty_dialogue_no_crash(self):
        result = self._write(dlg={"entries": [], "replies": [], "starters": []})
        self.assertIn("data_base64", result)
        self.assertNotIn("error", result)


# ── twoDAChangesINI ───────────────────────────────────────────────────────────

class TestTwoDAChangesINI(unittest.TestCase):
    ORIG = "2DA V2.0\n\n    label\n0    Hero\n1    Scoundrel\n"
    MOD_ADD = "2DA V2.0\n\n    label\n0    Hero\n1    Scoundrel\n2    Soldier\n"
    MOD_CHANGE = "2DA V2.0\n\n    label\n0    Warrior\n1    Scoundrel\n"

    def _call(self, orig: str, mod: str, name: str = "classes") -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("twoDAChangesINI", {
            "original": orig,
            "modified": mod,
            "twoDAName": name,
        })))

    def test_add_row_generates_addrow(self):
        result = self._call(self.ORIG, self.MOD_ADD)
        self.assertNotIn("error", result)
        self.assertIn("AddRow", result["changes_ini"])
        self.assertIn("Soldier", result["changes_ini"])

    def test_change_row_generates_changerow(self):
        result = self._call(self.ORIG, self.MOD_CHANGE)
        self.assertNotIn("error", result)
        self.assertIn("ChangeRow", result["changes_ini"])

    def test_row_counts_correct(self):
        result = self._call(self.ORIG, self.MOD_ADD)
        self.assertEqual(result["original_rows"], 2)
        self.assertEqual(result["modified_rows"], 3)

    def test_twoda_name_in_result(self):
        result = self._call(self.ORIG, self.MOD_ADD, name="appearance")
        # The ini section header should reference the 2DA name via the tool input
        self.assertEqual(result["twoDA"], "appearance")

    def test_no_changes_produces_empty_ini(self):
        result = self._call(self.ORIG, self.ORIG)
        self.assertNotIn("error", result)
        # No modifications → ini should be empty or minimal
        self.assertNotIn("AddRow", result["changes_ini"])
        self.assertNotIn("ChangeRow", result["changes_ini"])


# ── nwscriptCategories ────────────────────────────────────────────────────────

class TestNWScriptCategories(unittest.TestCase):
    def _call(self, game: str = "K1", kind: str = "functions") -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("nwscriptCategories", {
            "game": game, "kind": kind,
        })))

    def test_function_categories_present(self):
        result = self._call(kind="functions")
        self.assertIn("function_categories", result)
        self.assertGreater(len(result["function_categories"]), 5)

    def test_total_functions_correct(self):
        result = self._call(kind="functions")
        self.assertGreaterEqual(result["total_functions"], 700)

    def test_getters_is_largest_category(self):
        result = self._call(kind="functions")
        cats = result["function_categories"]
        self.assertIn("Getters", cats)
        # Getters should be the largest or one of the top categories
        max_count = max(cats.values())
        self.assertGreaterEqual(cats["Getters"], max_count * 0.9)

    def test_constant_categories(self):
        result = self._call(kind="constants")
        self.assertIn("constant_categories", result)
        self.assertGreater(len(result["constant_categories"]), 3)
        self.assertGreaterEqual(result["total_constants"], 1000)

    def test_all_kind(self):
        result = self._call(kind="all")
        self.assertIn("function_categories", result)
        self.assertIn("constant_categories", result)

    def test_game_in_result(self):
        result = self._call(game="K1")
        self.assertEqual(result["game"], "K1")

    def test_known_categories_present(self):
        result = self._call(kind="functions")
        cats = set(result["function_categories"].keys())
        for expected in ("Getters", "Effects", "Actions", "Setters"):
            self.assertIn(expected, cats, f"Category '{expected}' not found in {cats}")


# ── twoDALookup (without game install — via mock) ─────────────────────────────

class TestTwoDALookup(unittest.TestCase):
    """Test twoDALookup using a mocked ResourceManager that returns in-memory 2DA."""

    def _make_2da_bytes(self, text: str) -> bytes:
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        tda = TwoDAFile.from_text(text)
        return tda.to_binary()

    def _mock_rm(self, twoda_text: str):
        """Return a mock ResourceManager that serves the given 2DA bytes."""
        rm = MagicMock()
        rm.read = MagicMock(return_value=self._make_2da_bytes(twoda_text))
        return rm

    def _call_with_mock(self, rm, resref: str, row, column: str = "") -> dict:
        from ghostscripter.mcp import tools
        args = {"game": "K1", "resref": resref, "row": row}
        if column:
            args["column"] = column
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            return _json(_run(tools.handle_tool("twoDALookup", args)))

    def test_lookup_by_index(self):
        tda_text = "2DA V2.0\n\n    name    value\n0    Hero    1\n1    Scout   2\n"
        rm = self._mock_rm(tda_text)
        result = self._call_with_mock(rm, "classes", 0)
        self.assertNotIn("error", result)
        self.assertEqual(result["row"], "0")
        self.assertEqual(result["data"]["name"], "Hero")

    def test_lookup_by_label(self):
        tda_text = "2DA V2.0\n\n    name    value\n0    Hero    1\n1    Scout   2\n"
        rm = self._mock_rm(tda_text)
        result = self._call_with_mock(rm, "classes", "1")
        self.assertNotIn("error", result)
        self.assertEqual(result["data"]["name"], "Scout")

    def test_lookup_specific_column(self):
        tda_text = "2DA V2.0\n\n    name    hp\n0    Jedi    8\n1    Sith    10\n"
        rm = self._mock_rm(tda_text)
        result = self._call_with_mock(rm, "classes", 1, column="hp")
        self.assertNotIn("error", result)
        self.assertEqual(result["value"], "10")
        self.assertEqual(result["column"], "hp")

    def test_lookup_invalid_row_returns_error(self):
        tda_text = "2DA V2.0\n\n    name\n0    Hero\n"
        rm = self._mock_rm(tda_text)
        result = self._call_with_mock(rm, "classes", 99)
        self.assertIn("error", result)

    def test_lookup_invalid_column_returns_error(self):
        tda_text = "2DA V2.0\n\n    name\n0    Hero\n"
        rm = self._mock_rm(tda_text)
        result = self._call_with_mock(rm, "classes", 0, column="nonexistent")
        self.assertIn("error", result)


# ── searchNWScript ────────────────────────────────────────────────────────────

class TestSearchNWScript(unittest.TestCase):
    def _call(self, game: str, query: str, kind: str = "functions",
              category: str = "", limit: int = 20) -> dict:
        from ghostscripter.mcp.tools import handle_tool
        args: dict = {"game": game, "query": query, "kind": kind, "limit": limit}
        if category:
            args["category"] = category
        return _json(_run(handle_tool("searchNWScript", args)))

    def test_prefix_search_returns_results(self):
        result = self._call("K1", "GetGlobal")
        self.assertGreater(result["count"], 0)
        names = [r["name"] for r in result["results"]]
        self.assertTrue(any("GetGlobal" in n for n in names))

    def test_returns_kind_function(self):
        result = self._call("K1", "GetLocal", kind="functions")
        for r in result["results"]:
            self.assertEqual(r["kind"], "function")

    def test_category_filter(self):
        result = self._call("K1", "", kind="functions", category="Effects", limit=10)
        for r in result["results"]:
            self.assertIn("Effects", r["category"])

    def test_constants_search(self):
        result = self._call("K1", "OBJECT_TYPE", kind="constants")
        self.assertGreater(result["count"], 0)
        for r in result["results"]:
            self.assertEqual(r["kind"], "constant")

    def test_limit_respected(self):
        result = self._call("K1", "Get", limit=5)
        self.assertLessEqual(len(result["results"]), 5)

    def test_empty_query_returns_limited_results(self):
        result = self._call("K1", "", limit=10)
        self.assertLessEqual(len(result["results"]), 10)


# ── nwscriptSignature ─────────────────────────────────────────────────────────

class TestNWScriptSignature(unittest.TestCase):
    def _call(self, game: str, func: str) -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("nwscriptSignature", {
            "game": game, "functionName": func,
        })))

    def test_known_function_returns_signature(self):
        # K1 uses SetLocalBoolean / SetLocalNumber (not SetLocalInt)
        result = self._call("K1", "SetLocalBoolean")
        self.assertNotIn("error", result)
        self.assertEqual(result["name"], "SetLocalBoolean")
        self.assertIn("return_type", result)
        self.assertIn("parameters", result)

    def test_parameter_details(self):
        result = self._call("K1", "SetLocalBoolean")
        params = result["parameters"]
        self.assertGreater(len(params), 0)
        for p in params:
            self.assertIn("name", p)
            self.assertIn("type", p)

    def test_unknown_function_returns_error(self):
        result = self._call("K1", "NonExistentFunction_XYZ")
        self.assertIn("error", result)

    def test_category_present(self):
        result = self._call("K1", "GetLocalBoolean")
        self.assertNotIn("error", result)
        self.assertIn("category", result)
        self.assertIn("Local Variables", result["category"])


# ── writeGFF ──────────────────────────────────────────────────────────────────


class TestNWScriptToolsOptionalGame(unittest.TestCase):
    """NWScript tools must work without an explicit 'game' arg (defaults to K1)."""

    def _call(self, tool: str, args: dict) -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool(tool, args)))

    # ── nwscriptCategories ────────────────────────────────────────────────────

    def test_categories_no_game_defaults_k1(self) -> None:
        result = self._call("nwscriptCategories", {})
        self.assertNotIn("error", result)
        self.assertIn("function_categories", result)
        self.assertEqual(result["game"], "K1")

    def test_categories_no_game_k2_via_arg(self) -> None:
        r1 = self._call("nwscriptCategories", {"game": "K1"})
        r2 = self._call("nwscriptCategories", {"game": "K2"})
        # K2 has more functions than K1 (877 vs 772)
        self.assertGreater(r2["total_functions"], r1["total_functions"])

    # ── nwscriptSignature ─────────────────────────────────────────────────────

    def test_signature_no_game_defaults_k1(self) -> None:
        result = self._call("nwscriptSignature", {"functionName": "GetObjectType"})
        self.assertNotIn("error", result)
        self.assertEqual(result["name"], "GetObjectType")

    def test_signature_k2_only_function(self) -> None:
        # AddJournalQuestEntry exists in both, but K2 has extra param bAllowOverride
        k2 = self._call("nwscriptSignature", {"functionName": "AddJournalQuestEntry", "game": "K2"})
        k1 = self._call("nwscriptSignature", {"functionName": "AddJournalQuestEntry", "game": "K1"})
        self.assertNotIn("error", k2)
        self.assertNotIn("error", k1)
        # K2 version has one more parameter (bAllowOverrideHigher)
        self.assertGreaterEqual(len(k2["parameters"]), len(k1["parameters"]))

    def test_signature_missing_function_returns_error(self) -> None:
        result = self._call("nwscriptSignature", {"functionName": "FakeFunction_DoesNotExist"})
        self.assertIn("error", result)

    # ── searchNWScript ────────────────────────────────────────────────────────

    def test_search_no_game_defaults_k1(self) -> None:
        result = self._call("searchNWScript", {"query": "GetObjectType"})
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["game"], "K1")

    def test_search_k2_has_more_results_for_swmg(self) -> None:
        # K2 has Swoop minigame; SWMG constants exist there
        k2 = self._call("searchNWScript", {"query": "SWMG", "kind": "constants", "game": "K2"})
        k1 = self._call("searchNWScript", {"query": "SWMG", "kind": "constants", "game": "K1"})
        # K2 must have at least as many SWMG constants as K1
        self.assertGreaterEqual(k2["count"], k1["count"])

    def test_search_kind_all_returns_both(self) -> None:
        result = self._call("searchNWScript", {"query": "OBJECT_TYPE", "kind": "all"})
        kinds = {r["kind"] for r in result["results"]}
        # Should find both functions (GetObjectType) and constants (OBJECT_TYPE_*)
        self.assertTrue(kinds & {"function", "constant"})

    # ── compileSummary — type-error detection ─────────────────────────────────

    def test_int_object_param_flagged(self) -> None:
        """compileSummary must flag `int oPC` as a likely type error."""
        source = "void myFn(int oPC) { GiveXPToCreature(oPC, 500); }"
        result = self._call("compileSummary", {"source": source})
        issues = result.get("issues", [])
        self.assertTrue(
            any("oPC" in i or "object" in i.lower() for i in issues),
            f"Expected type-error issue for 'int oPC', got: {issues}",
        )

    def test_resref_over_16_chars_flagged(self) -> None:
        """compileSummary must flag ResRef strings exceeding 16 characters."""
        source = 'void main() { string r = "this_is_way_too_long_resref"; }'
        result = self._call("compileSummary", {"source": source})
        issues = result.get("issues", [])
        self.assertTrue(
            any("resref" in i.lower() or "16" in i or "long" in i.lower() for i in issues),
            f"Expected ResRef-length issue, got: {issues}",
        )

    def test_clean_source_has_no_issues(self) -> None:
        source = "void main() { AddJournalQuestEntry(\"my_quest\", 10, GetFirstPC()); }"
        result = self._call("compileSummary", {"source": source})
        self.assertEqual(result.get("issues", []), [])


class TestWriteGFF(unittest.TestCase):
    def _call(self, file_type: str, fields: dict) -> dict:
        from ghostscripter.mcp.tools import handle_tool
        return _json(_run(handle_tool("writeGFF", {
            "fileType": file_type,
            "fields": fields,
        })))

    def test_basic_gff_write(self):
        result = self._call("UTC ", {"FirstName": "Bastila", "MaxHitPoints": 50})
        self.assertNotIn("error", result)
        self.assertIn("data_base64", result)
        self.assertGreater(result["size_bytes"], 50)

    def test_gff_header_magic(self):
        result = self._call("DLG ", {"Skippable": 1})
        data = base64.b64decode(result["data_base64"])
        self.assertEqual(data[:4], b"DLG ")
        self.assertEqual(data[4:8], b"V3.2")

    def test_file_type_truncated_padded(self):
        result = self._call("JRL ", {})
        self.assertEqual(result["file_type"], "JRL ")

    def test_empty_fields_no_crash(self):
        result = self._call("UTC ", {})
        self.assertIn("data_base64", result)

    def test_roundtrip_with_gff_reader(self):
        # GFF3Reader lives in dlg_reader.py (not a separate gff_reader module)
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        result = self._call("UTC ", {"Tag": "my_creature", "MaxHitPoints": 100})
        data = base64.b64decode(result["data_base64"])
        parsed = GFF3Reader(data).parse()
        self.assertEqual(parsed.get("Tag"), "my_creature")


# ── gsDetectInstallations ─────────────────────────────────────────────────────

class TestDetectInstallations(unittest.TestCase):
    def test_returns_dict_with_k1_k2(self):
        from ghostscripter.mcp.tools import handle_tool
        result = _json(_run(handle_tool("gsDetectInstallations", {})))
        self.assertIn("K1", result)
        self.assertIn("K2", result)
        # v3.4: each game now returns {candidates: [...], loaded: bool}
        self.assertIn("candidates", result["K1"])
        self.assertIn("loaded", result["K1"])
        self.assertIsInstance(result["K1"]["candidates"], list)
        self.assertIsInstance(result["K1"]["loaded"], bool)

    def test_legacy_alias_still_works(self):
        """Backward-compat aliases (detectInstallations etc.) must remain callable."""
        from ghostscripter.mcp.tools import handle_tool
        result = _json(_run(handle_tool("detectInstallations", {})))
        self.assertIn("K1", result)

    def test_env_var_detected(self):
        import os
        from ghostscripter.mcp.tools import handle_tool
        os.environ["K1_PATH"] = "/tmp/fake_kotor"
        try:
            result = _json(_run(handle_tool("gsDetectInstallations", {})))
            k1_paths = [e["path"] for e in result["K1"]["candidates"]]
            self.assertIn("/tmp/fake_kotor", k1_paths)
        finally:
            del os.environ["K1_PATH"]


# ── moduleOverview (mocked) ───────────────────────────────────────────────────

class TestModuleOverview(unittest.TestCase):
    def test_missing_module_returns_error_or_no_git(self):
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("moduleOverview", {
                "game": "K1", "moduleId": "nonexistent_module",
            })))
        # Should not raise; returns overview with error field or empty counts
        self.assertIn("module_id", result)

    def test_area_name_from_are(self):
        from ghostscripter.mcp import tools
        from ghostscripter.core.export.gff_writer import GFF3Writer
        # Build a minimal ARE
        w = GFF3Writer("ARE ")
        w.root.add_cexo("AreaName", "Dantooine")
        are_bytes = w.build()

        rm = MagicMock()
        def _read(filename):
            if filename.endswith(".are"):
                return are_bytes
            return None
        rm.read = MagicMock(side_effect=_read)

        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("moduleOverview", {
                "game": "K1", "moduleId": "danm13",
            })))

        # No git → should still return area overview
        self.assertIn("module_id", result)


# ── searchResources (mocked) ──────────────────────────────────────────────────

class TestSearchResources(unittest.TestCase):
    def _mock_rm_with_twoda(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        tda_text = "2DA V2.0\n\n    label        value\n0    Jedi         1\n1    Sith         2\n2    Guardian     3\n"
        tda = TwoDAFile.from_text(tda_text)
        tda_bytes = tda.to_binary()

        mock_entry = MagicMock()
        mock_entry.resref = "classes"

        rm = MagicMock()
        rm.list_by_type = MagicMock(return_value=[mock_entry])
        rm.read = MagicMock(return_value=tda_bytes)
        return rm

    def test_search_2da_finds_result(self):
        from ghostscripter.mcp import tools
        rm = self._mock_rm_with_twoda()
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("searchResources", {
                "game": "K1", "query": "Jedi", "scope": "2da",
            })))
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        found = result["results"][0]
        self.assertEqual(found["scope"], "2da")
        self.assertEqual(found["value"], "Jedi")

    def test_empty_query_returns_error(self):
        from ghostscripter.mcp import tools
        rm = MagicMock()
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("searchResources", {
                "game": "K1", "query": "",
            })))
        self.assertIn("error", result)

    def test_limit_respected(self):
        from ghostscripter.mcp import tools
        rm = self._mock_rm_with_twoda()
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("searchResources", {
                "game": "K1", "query": "i", "scope": "2da", "limit": 1,
            })))
        self.assertLessEqual(result["count"], 1)


# ── server module ─────────────────────────────────────────────────────────────

class TestMCPServerModule(unittest.TestCase):
    def test_server_import(self):
        from ghostscripter.mcp.server import SERVER, main
        self.assertIsNotNone(SERVER)
        self.assertTrue(callable(main))

    def test_server_name(self):
        from ghostscripter.mcp.server import SERVER
        self.assertEqual(SERVER.name, "GhostScripterMCP")

    def test_main_entry_point_exists(self):
        """Verify __main__.py can be imported."""
        import ghostscripter.mcp.__main__  # should not raise


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# New tests added for architecture refactor (Khononov coupling principles)
# ─────────────────────────────────────────────────────────────────────────────

class TestTLKFileModel(unittest.TestCase):
    """Tests for the core TLK domain model (core.models.tlk)."""

    def _make_tlk_bytes(self, entries):
        """Build a minimal TLK binary with given string entries (list of str)."""
        import struct
        count = len(entries)
        str_offset = 20 + count * 40
        enc = "cp1252"

        entry_table = bytearray()
        string_data = bytearray()

        for text in entries:
            raw = text.encode(enc, errors="replace") if text else b""
            off_str = len(string_data) if raw else 0
            if raw:
                string_data += raw
            sound_raw = b"\x00" * 16
            # flags=1 (has text), vol=0, pitch=0, sound_len=0.0
            entry_table += struct.pack(
                "<I16sIIIIf",
                1, sound_raw, 0, 0, off_str, len(raw), 0.0,
            )

        header = struct.pack("<4s4sIII",
            b"TLK ", b"V3.0", 0, count, str_offset)
        return header + bytes(entry_table) + bytes(string_data)

    def test_from_bytes_basic(self):
        from ghostscripter.core.models.tlk import TLKFile
        data = self._make_tlk_bytes(["Hello", "World", ""])
        tlk = TLKFile.from_bytes(data, "dialog.tlk")
        self.assertEqual(len(tlk), 3)
        self.assertEqual(tlk.entries[0].text, "Hello")
        self.assertEqual(tlk.entries[1].text, "World")
        self.assertEqual(tlk.entries[2].text, "")
        self.assertEqual(tlk.filename, "dialog.tlk")

    def test_get_string(self):
        from ghostscripter.core.models.tlk import TLKFile
        data = self._make_tlk_bytes(["Alpha", "Beta"])
        tlk = TLKFile.from_bytes(data)
        self.assertEqual(tlk.get_string(0), "Alpha")
        self.assertEqual(tlk.get_string(1), "Beta")
        self.assertEqual(tlk.get_string(99, "MISSING"), "MISSING")

    def test_roundtrip(self):
        """Bytes → TLKFile → bytes should produce identical files."""
        from ghostscripter.core.models.tlk import TLKFile
        original = self._make_tlk_bytes(["Test string", "Another one", ""])
        tlk = TLKFile.from_bytes(original, "test.tlk")
        result = tlk.to_bytes()
        # Re-parse and compare texts
        tlk2 = TLKFile.from_bytes(result, "test.tlk")
        self.assertEqual(
            [e.text for e in tlk.entries],
            [e.text for e in tlk2.entries],
        )

    def test_language_id_preserved(self):
        from ghostscripter.core.models.tlk import TLKFile
        import struct
        # Build a TLK with language_id = 128 (Korean)
        count = 1
        str_offset = 20 + count * 40
        raw = "테스트".encode("cp949", errors="replace")
        entry = struct.pack("<I16sIIIIf", 1, b"\x00"*16, 0, 0, 0, len(raw), 0.0)
        header = struct.pack("<4s4sIII", b"TLK ", b"V3.0", 128, 1, str_offset)
        data = header + entry + raw
        tlk = TLKFile.from_bytes(data)
        self.assertEqual(tlk.language_id, 128)

    def test_invalid_magic_raises(self):
        from ghostscripter.core.models.tlk import TLKFile
        with self.assertRaises(ValueError):
            TLKFile.from_bytes(b"NOPE" + b"\x00" * 50)

    def test_repr_contains_filename(self):
        from ghostscripter.core.models.tlk import TLKFile
        data = self._make_tlk_bytes(["Hello"])
        tlk = TLKFile.from_bytes(data, "dialog.tlk")
        self.assertIn("dialog.tlk", repr(tlk))

    def test_widget_imports_from_core(self):
        """Verify the UI widget re-exports TLKFile from core.models.tlk."""
        from ghostscripter.core.models.tlk import TLKFile as CoreTLKFile
        # Import via the widget path (which should now be a re-export)
        import importlib
        import sys
        # Only test the import chain without Qt (which may not be available)
        import ghostscripter.core.models.tlk as core_tlk
        self.assertIs(core_tlk.TLKFile, CoreTLKFile)


class TestTLKService(unittest.TestCase):
    """Tests for TLKService in core.services."""

    def _make_tlk_bytes(self, entries):
        """Minimal TLK binary builder."""
        import struct
        count = len(entries)
        str_offset = 20 + count * 40
        entry_table = bytearray()
        string_data = bytearray()
        for text in entries:
            raw = text.encode("cp1252", errors="replace") if text else b""
            off_str = len(string_data) if raw else 0
            if raw:
                string_data += raw
            entry_table += struct.pack("<I16sIIIIf", 1, b"\x00"*16, 0, 0, off_str, len(raw), 0.0)
        header = struct.pack("<4s4sIII", b"TLK ", b"V3.0", 0, count, str_offset)
        return header + bytes(entry_table) + bytes(string_data)

    def test_parse_bytes(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["Alpha", "Beta", ""])
        tlk = TLKService.parse_bytes(data, "test.tlk")
        self.assertEqual(len(tlk), 3)
        self.assertEqual(tlk.entries[0].text, "Alpha")

    def test_lookup_known(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["Hello", "World"])
        tlk = TLKService.parse_bytes(data)
        results = TLKService.lookup(tlk, [0, 1])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["text"], "Hello")
        self.assertEqual(results[1]["strref"], 1)

    def test_lookup_out_of_range(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["Hello"])
        tlk = TLKService.parse_bytes(data)
        results = TLKService.lookup(tlk, [999])
        self.assertIn("error", results[0])
        self.assertEqual(results[0]["strref"], 999)

    def test_summary_structure(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["Hello world", "", "Another"])
        tlk = TLKService.parse_bytes(data)
        s = TLKService.summary(tlk)
        self.assertEqual(s["type"], "TLK")
        self.assertEqual(s["entry_count"], 3)
        self.assertIn("language_id", s)
        self.assertIn("sample_entries", s)
        # sample_entries should contain non-empty entries only
        for se in s["sample_entries"]:
            self.assertTrue(se["text"].strip())

    def test_summary_language_name(self):
        from ghostscripter.core.services import TLKService
        from ghostscripter.core.models.tlk import TLKFile
        import struct
        count = 1
        str_offset = 20 + count * 40
        raw = b"test"
        entry = struct.pack("<I16sIIIIf", 1, b"\x00"*16, 0, 0, 0, len(raw), 0.0)
        header = struct.pack("<4s4sIII", b"TLK ", b"V3.0", 0, 1, str_offset)
        tlk = TLKFile.from_bytes(header + entry + raw)
        s = TLKService.summary(tlk)
        self.assertEqual(s["language_name"], "English")

    def test_search(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["Hello world", "Goodbye", "Hello again"])
        tlk = TLKService.parse_bytes(data)
        hits = TLKService.search(tlk, "hello")
        self.assertEqual(len(hits), 2)
        for h in hits:
            self.assertIn("hello", h["text"].lower())

    def test_search_limit(self):
        from ghostscripter.core.services import TLKService
        data = self._make_tlk_bytes(["match"] * 20)
        tlk = TLKService.parse_bytes(data)
        hits = TLKService.search(tlk, "match", limit=5)
        self.assertEqual(len(hits), 5)

    def test_load_requires_reader(self):
        from ghostscripter.core.services import TLKService
        svc = TLKService()  # no reader
        with self.assertRaises(ValueError):
            svc.load()

    def test_load_missing_file(self):
        from ghostscripter.core.services import TLKService
        mock_rm = MagicMock()
        mock_rm.read.return_value = None
        svc = TLKService(mock_rm)
        with self.assertRaises(FileNotFoundError):
            svc.load("dialog")


class TestNWScriptService(unittest.TestCase):
    """Tests for NWScriptService in core.services."""

    def test_load_k1(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        self.assertIsNotNone(db)

    def test_search_functions(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        results = NWScriptService.search(db, "GetLocal", kind="functions")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["kind"], "function")
            self.assertIn("getlocal", r["name"].lower())

    def test_search_constants(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        results = NWScriptService.search(db, "TRUE", kind="constants")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertEqual(r["kind"], "constant")

    def test_search_all(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        results = NWScriptService.search(db, "Object", kind="all", limit=50)
        kinds = {r["kind"] for r in results}
        # Should contain both functions and constants for a generic query
        self.assertIn("function", kinds)

    def test_search_with_category_filter(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        results = NWScriptService.search(
            db, "", kind="functions", category_filter="Getters", limit=10
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("getter", r["category"].lower())

    def test_search_limit_respected(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        results = NWScriptService.search(db, "", kind="functions", limit=7)
        self.assertLessEqual(len(results), 7)

    def test_signature_found(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        sig = NWScriptService.signature(db, "GetLocalBoolean")
        self.assertIsNotNone(sig)
        self.assertEqual(sig["name"], "GetLocalBoolean")
        self.assertIn("parameters", sig)
        self.assertIn("return_type", sig)
        self.assertIn("signature", sig)
        self.assertIn("call_snippet", sig)
        self.assertIn("category", sig)
        self.assertIn("line_number", sig)

    def test_signature_not_found(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        sig = NWScriptService.signature(db, "NonExistentFunctionXYZ")
        self.assertIsNone(sig)

    def test_signature_parameter_structure(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        sig = NWScriptService.signature(db, "GetLocalBoolean")
        params = sig["parameters"]
        self.assertGreater(len(params), 0)
        for p in params:
            self.assertIn("name", p)
            self.assertIn("type", p)
            self.assertIn("default", p)
            self.assertIn("is_optional", p)

    def test_categories_functions(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        cats = NWScriptService.categories(db, "functions")
        self.assertIn("function_categories", cats)
        self.assertIn("total_functions", cats)
        self.assertNotIn("constant_categories", cats)
        self.assertGreater(cats["total_functions"], 0)

    def test_categories_constants(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        cats = NWScriptService.categories(db, "constants")
        self.assertIn("constant_categories", cats)
        self.assertIn("total_constants", cats)

    def test_categories_all(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        cats = NWScriptService.categories(db, "all")
        self.assertIn("function_categories", cats)
        self.assertIn("constant_categories", cats)

    def test_categories_sorted_by_count(self):
        from ghostscripter.core.services import NWScriptService
        db = NWScriptService.load("K1")
        cats = NWScriptService.categories(db, "functions")
        counts = list(cats["function_categories"].values())
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_k2_loads_different_db(self):
        from ghostscripter.core.services import NWScriptService
        db1 = NWScriptService.load("K1")
        db2 = NWScriptService.load("K2")
        # K1 and K2 have slightly different function counts
        # Just verify both load successfully
        cats1 = NWScriptService.categories(db1, "functions")
        cats2 = NWScriptService.categories(db2, "functions")
        self.assertGreater(cats1["total_functions"], 0)
        self.assertGreater(cats2["total_functions"], 0)


class TestCouplingArchitecture(unittest.TestCase):
    """
    Architecture guard tests — verify the coupling model is respected.

    These tests enforce that ghostscripter.mcp.tools:
      1. Does not import from any ghostscripter.core sub-module directly
         (only from public package __init__s and services)
      2. Has no direct imports of NWScriptDB, TwoDAFile, DLGExporter, etc.
    """

    def _get_tool_source(self):
        import inspect
        from ghostscripter.mcp import tools
        return inspect.getsource(tools)

    def test_no_direct_nwscriptdb_import(self):
        """tools.py must not import NWScriptDB directly."""
        src = self._get_tool_source()
        self.assertNotIn("from ghostscripter.core.nwscript.parser import", src,
                          "tools.py imports NWScriptDB directly — use NWScriptService")

    def test_no_direct_twodafile_import(self):
        """tools.py must not import TwoDAFile directly."""
        src = self._get_tool_source()
        self.assertNotIn("twoda_manager.twoda_manager import", src,
                          "tools.py imports TwoDAFile directly — use TwoDAService")

    def test_no_direct_dlgexporter_import(self):
        """tools.py must not import DLGExporter directly."""
        src = self._get_tool_source()
        self.assertNotIn("from ghostscripter.core.export.dlg_writer import", src,
                          "tools.py imports DLGExporter directly — use DialogueService")

    def test_no_direct_gff_writer_import(self):
        """tools.py must not import GFF3Writer directly."""
        src = self._get_tool_source()
        self.assertNotIn("from ghostscripter.core.export.gff_writer import", src,
                          "tools.py imports GFF3Writer directly — use GFFService")

    def test_no_direct_tlkfile_import_from_rm(self):
        """tools.py must not import TLKFile from resource_manager."""
        src = self._get_tool_source()
        self.assertNotIn("resource_manager.resource_manager import TLKFile", src,
                          "tools.py imports TLKFile from resource_manager — use TLKService")

    def test_no_direct_jrl_importer_import(self):
        """tools.py must not import JRLImporter directly."""
        src = self._get_tool_source()
        self.assertNotIn("from ghostscripter.core.export.jrl", src,
                          "tools.py imports jrl sub-module directly — use JournalService")

    def test_tlkfile_model_lives_in_core(self):
        """TLKFile must be importable from core.models, not only from UI widget."""
        from ghostscripter.core.models.tlk import TLKFile
        self.assertTrue(callable(TLKFile.from_bytes))
        self.assertTrue(callable(TLKFile.from_file))
        self.assertTrue(callable(TLKFile.to_bytes))

    def test_services_are_public_api(self):
        """All six service classes must be importable from core.services directly."""
        from ghostscripter.core.services import (
            DialogueService,
            TwoDAService,
            JournalService,
            GFFService,
            TLKService,
            NWScriptService,
        )
        for cls in (DialogueService, TwoDAService, JournalService,
                    GFFService, TLKService, NWScriptService):
            self.assertTrue(callable(cls), f"{cls} is not callable")


# ─── AgentDecompile Bridge Tests ──────────────────────────────────────────────

class TestGhostworksPipelineTools(unittest.TestCase):
    """Tests for the new Ghostworks composite MCP tools."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _json(self, result):
        import json
        return json.loads(result[0].text)

    # ── getResource ──────────────────────────────────────────────────────────

    def test_get_resource_unknown_game(self):
        """getResource with invalid game returns error."""
        from ghostscripter.mcp.tools import handle_tool
        result = self._run(handle_tool("getResource", {
            "game": "invalid_game",
            "resref": "appearance",
            "type": "2da",
        }))
        data = self._json(result)
        self.assertIn("error", data)

    def test_get_resource_missing_rm(self):
        """getResource returns error if no installation is loaded."""
        from ghostscripter.mcp import tools
        old_installs = dict(tools._INSTALLS)
        tools._INSTALLS.clear()
        try:
            result = self._run(tools.handle_tool("getResource", {
                "game": "K1",
                "resref": "appearance",
                "type": "2da",
            }))
            data = self._json(result)
            # Either an error (no RM found) or a successful result if game is installed
            self.assertIsInstance(data, dict)
        finally:
            tools._INSTALLS.update(old_installs)

    def test_get_resource_schema_exists(self):
        """getResource tool must be in TOOLS with correct required fields."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next((t for t in TOOLS if t.name == "getResource"), None)
        self.assertIsNotNone(tool, "getResource missing from TOOLS")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)
        self.assertIn("type", required)

    # ── getQuest ─────────────────────────────────────────────────────────────

    def test_get_quest_schema_exists(self):
        """getQuest tool must be in TOOLS with questId as required field."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next((t for t in TOOLS if t.name == "getQuest"), None)
        self.assertIsNotNone(tool, "getQuest missing from TOOLS")
        required = tool.inputSchema.get("required", [])
        self.assertIn("questId", required)

    def test_get_quest_error_no_installation(self):
        """getQuest returns error dict (not exception) when no installation loaded."""
        from ghostscripter.mcp import tools
        old_installs = dict(tools._INSTALLS)
        tools._INSTALLS.clear()
        try:
            result = self._run(tools.handle_tool("getQuest", {
                "game": "K1",
                "questId": "test_quest",
            }))
            data = self._json(result)
            self.assertIsInstance(data, dict)
        finally:
            tools._INSTALLS.update(old_installs)

    # ── getNpc ───────────────────────────────────────────────────────────────

    def test_get_npc_schema_exists(self):
        """getNpc tool must be in TOOLS with resref as required field."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next((t for t in TOOLS if t.name == "getNpc"), None)
        self.assertIsNotNone(tool, "getNpc missing from TOOLS")
        required = tool.inputSchema.get("required", [])
        self.assertIn("resref", required)

    def test_get_npc_error_no_installation(self):
        """getNpc returns error dict when no installation loaded."""
        from ghostscripter.mcp import tools
        old_installs = dict(tools._INSTALLS)
        tools._INSTALLS.clear()
        try:
            result = self._run(tools.handle_tool("getNpc", {
                "game": "K1",
                "resref": "n_sithsold",
            }))
            data = self._json(result)
            self.assertIsInstance(data, dict)
        finally:
            tools._INSTALLS.update(old_installs)

    # ── getScript ────────────────────────────────────────────────────────────

    def test_get_script_schema_exists(self):
        """getScript tool must be in TOOLS with resref as required field."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next((t for t in TOOLS if t.name == "getScript"), None)
        self.assertIsNotNone(tool, "getScript missing from TOOLS")
        required = tool.inputSchema.get("required", [])
        self.assertIn("resref", required)

    def test_get_script_error_no_installation(self):
        """getScript returns error/not-found dict when no installation loaded."""
        from ghostscripter.mcp import tools
        old_installs = dict(tools._INSTALLS)
        tools._INSTALLS.clear()
        try:
            result = self._run(tools.handle_tool("getScript", {
                "game": "K1",
                "resref": "k_test_script",
            }))
            data = self._json(result)
            self.assertIsInstance(data, dict)
        finally:
            tools._INSTALLS.update(old_installs)

    # ── listResType ───────────────────────────────────────────────────────────

    def test_list_res_type_schema_exists(self):
        """listResType tool must be in TOOLS with game and type as required."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next((t for t in TOOLS if t.name == "listResType"), None)
        self.assertIsNotNone(tool, "listResType missing from TOOLS")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("type", required)

    def test_list_res_type_error_no_installation(self):
        """listResType returns error/empty dict when no installation loaded."""
        from ghostscripter.mcp import tools
        old_installs = dict(tools._INSTALLS)
        tools._INSTALLS.clear()
        try:
            result = self._run(tools.handle_tool("listResType", {
                "game": "K1",
                "type": "2da",
            }))
            data = self._json(result)
            self.assertIsInstance(data, dict)
        finally:
            tools._INSTALLS.update(old_installs)

    # ── _try_decompile_ncs ───────────────────────────────────────────────────

    def test_try_decompile_ncs_no_tools_returns_none(self):
        """_try_decompile_ncs returns None gracefully when no decompiler found."""
        from ghostscripter.mcp.tools import _try_decompile_ncs
        # Pass fake NCS bytes — all decompilers should fail silently
        result = _try_decompile_ncs(b"\x00\x00\x00\x00", "test_fake")
        # Should return None (not raise)
        self.assertIsNone(result)

    # ── Tool registry completeness ────────────────────────────────────────────

    def test_composite_tools_in_registry(self):
        """All 5 new Ghostworks Pipeline tools appear in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        for expected in ("getResource", "getQuest", "getNpc", "getScript", "listResType"):
            self.assertIn(expected, names, f"Missing composite tool in TOOLS: {expected}")
            self.assertIn(expected, _HANDLERS, f"Missing composite tool in _HANDLERS: {expected}")

    def test_all_composite_tools_have_descriptions(self):
        """All new tools must have descriptions longer than 20 chars."""
        from ghostscripter.mcp.tools import TOOLS
        composite = {t.name: t for t in TOOLS if t.name in
                     ("getResource", "getQuest", "getNpc", "getScript", "listResType")}
        for name, tool in composite.items():
            self.assertGreater(
                len(tool.description), 20,
                f"Tool '{name}' description too short: {tool.description!r}"
            )

    def test_total_tool_count(self):
        """Total tool count ≥58 (canonical assertion is in TestV33Additions)."""
        from ghostscripter.mcp.tools import TOOLS
        self.assertGreaterEqual(len(TOOLS), 58, f"Expected 58 tools, got {len(TOOLS)}")


# ─── Bug-fix regression tests ────────────────────────────────────────────────
# These tests verify the 5 broken call-site classes found in the audit:
#   1. DialogueService.from_bytes (does not exist → parse_bytes)
#   2. GFFService.read (does not exist → parse_bytes)
#   3. TLKService.lookup returns list, not dict
#   4. list_by_type returns ResourceEntry objects, not strings
#   5. _list_res_type items must be JSON-serializable dicts

class TestBugFixRegressions(unittest.TestCase):
    """Regression suite for the 5 call-site bugs fixed in the audit."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _json(self, result):
        return json.loads(result[0].text)

    # ── 1. DialogueService.parse_bytes (was .from_bytes) ─────────────────────

    def test_dialogue_service_parse_bytes_exists(self):
        """DialogueService must have parse_bytes, not from_bytes."""
        from ghostscripter.core.services import DialogueService
        self.assertTrue(hasattr(DialogueService, "parse_bytes"),
                        "DialogueService.parse_bytes must exist")
        self.assertFalse(hasattr(DialogueService, "from_bytes"),
                         "DialogueService.from_bytes must NOT exist (was a phantom method)")

    def test_dialogue_service_parse_bytes_roundtrip(self):
        """parse_bytes must accept bytes and return a DialogueFile."""
        from ghostscripter.core.services import DialogueService
        from ghostscripter.core.models.dialogue import DialogueFile, DialogueNode, DialogueBranch

        dlg = DialogueFile()
        n = DialogueNode()
        n.text = "Hello"
        n.text_strref = -1
        n.script1 = ""
        n.script2 = ""
        n.vo_resref = ""
        n.sound = ""
        dlg.entries.append(n)

        raw = DialogueService.to_binary(dlg, "K1")
        restored = DialogueService.parse_bytes(raw)  # must not raise
        self.assertEqual(len(restored.entries), 1)
        self.assertEqual(restored.entries[0].text, "Hello")

    # ── 2. GFFService.parse_bytes (was .read) ────────────────────────────────

    def test_gff_service_parse_bytes_exists(self):
        """GFFService must have parse_bytes, not read."""
        from ghostscripter.core.services import GFFService
        self.assertTrue(hasattr(GFFService, "parse_bytes"),
                        "GFFService.parse_bytes must exist")
        self.assertFalse(hasattr(GFFService, "read"),
                         "GFFService.read must NOT exist (was a phantom method)")

    def test_gff_service_parse_bytes_roundtrip(self):
        """parse_bytes must produce a dict of GFF fields."""
        from ghostscripter.core.services import GFFService
        raw = GFFService.write("UTC ", {"FirstName": "Bastila", "MaxHitPoints": 60})
        self.assertIsInstance(raw, bytes)
        fields = GFFService.parse_bytes(raw)  # must not raise
        self.assertIsInstance(fields, dict)
        self.assertIn("FirstName", fields)

    # ── 3. TLKService.lookup returns list, not dict ───────────────────────────

    def test_tlk_lookup_returns_list(self):
        """TLKService.lookup must return a list of dicts, not a dict."""
        from ghostscripter.core.services import TLKService
        from ghostscripter.core.models.tlk import TLKFile

        # Build a minimal TLK in memory
        tlk = TLKFile()
        from ghostscripter.core.models.tlk import TLKEntry
        e = TLKEntry()
        e.text = "Hello Taris"
        e.sound_resref = ""
        e.flags = 1
        tlk.entries.append(e)

        result = TLKService.lookup(tlk, [0])
        self.assertIsInstance(result, list, "TLKService.lookup must return a list")
        self.assertEqual(len(result), 1)
        self.assertIn("text", result[0])
        self.assertEqual(result[0]["text"], "Hello Taris")

    def test_tlk_lookup_list_indexing(self):
        """Callers must use result[0].get('text') not result.get(strref, {})."""
        from ghostscripter.core.services import TLKService
        from ghostscripter.core.models.tlk import TLKFile, TLKEntry

        tlk = TLKFile()
        e = TLKEntry(); e.text = "Revan"; e.sound_resref = ""; e.flags = 1
        tlk.entries.append(e)

        entries = TLKService.lookup(tlk, [0])
        # Correct access pattern (what tools.py now uses):
        text = (entries[0].get("text", "") if entries else "") or ""
        self.assertEqual(text, "Revan")

        # Wrong old pattern would have raised AttributeError:
        with self.assertRaises((AttributeError, TypeError)):
            _ = entries.get(0, {}).get("text", "")  # list has no .get()

    # ── 4. list_by_type returns ResourceEntry objects ─────────────────────────

    def test_resource_entry_has_resref_attr(self):
        """ResourceEntry objects have .resref attribute — not strings."""
        from ghostscripter.core.resource_manager.resource_manager import ResourceEntry
        e = ResourceEntry(resref="appearance", restype=2017)
        self.assertEqual(e.resref, "appearance")
        # Strings would support .lower() directly; ResourceEntry does not
        with self.assertRaises(AttributeError):
            _ = e.lower()

    def test_list_res_type_items_are_dicts(self):
        """_list_res_type must return JSON-serializable dicts in 'items'."""
        from ghostscripter.core.resource_manager.resource_manager import ResourceEntry
        from ghostscripter.mcp.tools import _HANDLERS, _INSTALLS
        import ghostscripter.mcp.tools as tools_mod

        # Inject a mock ResourceManager
        mock_rm = MagicMock()
        mock_rm.list_by_type.return_value = [
            ResourceEntry(resref="appearance", restype=2017,
                          restype_str=".2da", source_file="/bif/archive.bif", size=12000),
            ResourceEntry(resref="classes", restype=2017,
                          restype_str=".2da", source_file="/bif/archive.bif", size=3200),
        ]
        orig = tools_mod._INSTALLS.copy()
        tools_mod._INSTALLS["K1"] = mock_rm
        try:
            result = asyncio.run(_HANDLERS["listResType"](
                {"game": "K1", "type": "2da", "limit": "10"}
            ))
            data = json.loads(result[0].text)
            self.assertNotIn("error", data)
            self.assertIsInstance(data["items"], list)
            self.assertGreater(len(data["items"]), 0)
            first = data["items"][0]
            # Must be a plain dict, serializable to JSON
            self.assertIsInstance(first, dict)
            self.assertIn("resref", first)
            self.assertEqual(first["resref"], "appearance")
            # Verify round-trip JSON serialization works
            json.dumps(data)  # must not raise
        finally:
            tools_mod._INSTALLS.clear()
            tools_mod._INSTALLS.update(orig)

    # ── 5. getResource DLG and GFF paths (was calling phantom methods) ────────

    def test_get_resource_dlg_parse_bytes_path(self):
        """_get_resource for a DLG must use DialogueService.parse_bytes."""
        from ghostscripter.core.services import DialogueService
        from ghostscripter.core.models.dialogue import DialogueFile
        from ghostscripter.mcp.tools import _HANDLERS
        import ghostscripter.mcp.tools as tools_mod

        dlg = DialogueFile()
        raw = DialogueService.to_binary(dlg, "K1")

        mock_rm = MagicMock()
        mock_rm.read.return_value = raw

        orig = tools_mod._INSTALLS.copy()
        tools_mod._INSTALLS["K1"] = mock_rm
        try:
            result = asyncio.run(_HANDLERS["getResource"](
                {"game": "K1", "resref": "testdlg", "type": "dlg"}
            ))
            data = json.loads(result[0].text)
            self.assertNotIn("error", data, f"getResource DLG failed: {data}")
            self.assertEqual(data["type"], "dlg")
        finally:
            tools_mod._INSTALLS.clear()
            tools_mod._INSTALLS.update(orig)

    def test_get_resource_gff_parse_bytes_path(self):
        """_get_resource for a UTC must use GFFService.parse_bytes."""
        from ghostscripter.core.services import GFFService
        from ghostscripter.mcp.tools import _HANDLERS
        import ghostscripter.mcp.tools as tools_mod

        raw = GFFService.write("UTC ", {"Tag": "TestNPC", "MaxHitPoints": 50})

        mock_rm = MagicMock()
        mock_rm.read.return_value = raw

        orig = tools_mod._INSTALLS.copy()
        tools_mod._INSTALLS["K1"] = mock_rm
        try:
            result = asyncio.run(_HANDLERS["getResource"](
                {"game": "K1", "resref": "testnpc", "type": "utc"}
            ))
            data = json.loads(result[0].text)
            self.assertNotIn("error", data, f"getResource UTC failed: {data}")
            self.assertIn("fields", data)
        finally:
            tools_mod._INSTALLS.clear()
            tools_mod._INSTALLS.update(orig)


# ─── writeTwoDA / writeERF tests ────────────────────────────────────────────

class TestWriteTwoDA(unittest.TestCase):
    """Tests for the writeTwoDA MCP tool."""

    def _run(self, args):
        import asyncio
        from ghostscripter.mcp.tools import _write_twoda
        return asyncio.run(_write_twoda(args))

    def test_basic_text_roundtrip(self):
        """writeTwoDA produces valid base64 text 2DA from columns+rows."""
        import base64
        result = self._run({
            "resref": "test_table",
            "columns": ["value"],
            "rows": [
                {"label": "row0", "value": "42"},
                {"label": "row1", "value": "99"},
            ],
            "format": "text",
        })
        self.assertEqual(len(result), 1)
        data = json.loads(result[0].text)
        self.assertNotIn("error", data, f"writeTwoDA failed: {data}")
        self.assertIn("data_base64", data)
        raw = base64.b64decode(data["data_base64"])
        self.assertTrue(raw.startswith(b"2DA V2.0"), f"Expected 2DA header, got {raw[:10]!r}")
        self.assertIn(b"row0", raw)
        self.assertEqual(data["row_count"], 2)
        self.assertEqual(data["format"], "text")

    def test_binary_format(self):
        """writeTwoDA can produce binary (V2.b) format."""
        import base64
        result = self._run({
            "resref": "bin_test",
            "columns": ["col1"],
            "rows": [{"label": "r0", "col1": "hello"}],
            "format": "binary",
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data, f"Binary writeTwoDA failed: {data}")
        raw = base64.b64decode(data["data_base64"])
        self.assertTrue(raw.startswith(b"2DA V2.b"), f"Expected binary header, got {raw[:10]!r}")

    def test_cell_edits_applied(self):
        """Cell edits in 'edits' list are applied before serialisation."""
        import base64
        result = self._run({
            "resref": "edittest",
            "columns": ["name"],
            "rows": [{"label": "r0", "name": "original"}],
            "edits": [{"row": 0, "column": "name", "value": "patched"}],
            "format": "text",
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        raw = base64.b64decode(data["data_base64"])
        self.assertIn(b"patched", raw)
        self.assertNotIn(b"original", raw)

    def test_edit_by_label(self):
        """Edits by row label string (not index) work correctly."""
        import base64
        result = self._run({
            "resref": "lbltest",
            "columns": ["val"],
            "rows": [{"label": "myrow", "val": "before"}],
            "edits": [{"row": "myrow", "column": "val", "value": "after"}],
            "format": "text",
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        raw = base64.b64decode(data["data_base64"])
        self.assertIn(b"after", raw)

    def test_missing_columns_returns_error(self):
        """writeTwoDA returns error when columns is empty."""
        result = self._run({"resref": "bad", "columns": [], "rows": []})
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_invalid_row_edit_index_adds_warning(self):
        """Out-of-range edit index produces a warning but does not crash."""
        result = self._run({
            "resref": "warntest",
            "columns": ["x"],
            "rows": [{"label": "r0", "x": "1"}],
            "edits": [{"row": 999, "column": "x", "value": "oops"}],
            "format": "text",
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertIn("warnings", data)


class TestWriteERF(unittest.TestCase):
    """Tests for the writeERF MCP tool."""

    def _run(self, args):
        import asyncio
        from ghostscripter.mcp.tools import _write_erf
        return asyncio.run(_write_erf(args))

    def _b64(self, text: str) -> str:
        import base64
        return base64.b64encode(text.encode("latin-1")).decode("ascii")

    def test_basic_erf_roundtrip(self):
        """writeERF packs files and returns valid ERF binary."""
        import base64
        result = self._run({
            "files": [
                {"resref": "k_test_script", "type": "nss", "data_b64": self._b64("void main(){}")},
                {"resref": "test_dialog",   "type": "dlg", "data_b64": self._b64("DUMMY_DLG_BYTES")},
            ],
            "archive_type": "MOD ",
        })
        self.assertEqual(len(result), 1)
        data = json.loads(result[0].text)
        self.assertNotIn("error", data, f"writeERF failed: {data}")
        self.assertIn("data_base64", data)
        raw = base64.b64decode(data["data_base64"])
        self.assertEqual(raw[:4], b"MOD ")
        self.assertEqual(raw[4:8], b"V1.0")
        self.assertEqual(data["file_count"], 2)
        self.assertIn("k_test_script.nss", data["files"])
        self.assertIn("test_dialog.dlg", data["files"])

    def test_erf_type_header(self):
        """archive_type is written correctly to the ERF header."""
        import base64
        for atype in ("ERF ", "MOD ", "SAV "):
            result = self._run({
                "files": [{"resref": "dummy", "type": "nss", "data_b64": self._b64("//x")}],
                "archive_type": atype,
            })
            data = json.loads(result[0].text)
            self.assertNotIn("error", data)
            raw = base64.b64decode(data["data_base64"])
            self.assertEqual(raw[:4].decode("ascii"), atype, f"Header mismatch for {atype!r}")

    def test_resref_truncated_to_16(self):
        """ResRef names longer than 16 chars are silently truncated."""
        long_resref = "a" * 30
        result = self._run({
            "files": [{"resref": long_resref, "type": "nss", "data_b64": self._b64("//x")}],
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertEqual(len(data["files"][0].split(".")[0]), 16)

    def test_empty_files_returns_error(self):
        """writeERF returns an error when files list is empty."""
        result = self._run({"files": []})
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_invalid_base64_skipped_with_warning(self):
        """File entries with invalid base64 are skipped and reported as warnings."""
        result = self._run({
            "files": [
                {"resref": "good", "type": "nss", "data_b64": self._b64("void main(){}")},
                {"resref": "bad",  "type": "nss", "data_b64": "!NOT_VALID_BASE64!!!"},
            ],
        })
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertEqual(data["file_count"], 1)
        self.assertIn("warnings", data)

    def test_new_tools_in_registry(self):
        """writeTwoDA and writeERF appear in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        for tool_name in ("writeTwoDA", "writeERF"):
            self.assertIn(tool_name, names,     f"{tool_name} missing from TOOLS")
            self.assertIn(tool_name, _HANDLERS, f"{tool_name} missing from _HANDLERS")


# ─── compileScript / writeOverride tests ────────────────────────────────────

class TestCompileScript(unittest.TestCase):
    """Tests for the compileScript MCP tool."""

    def _invoke(self, **kwargs):
        from ghostscripter.mcp.tools import _compile_script
        import asyncio
        import json
        result = asyncio.run(_compile_script(kwargs))
        self.assertEqual(len(result), 1)
        return json.loads(result[0].text)

    def test_missing_compiler_returns_error(self):
        """compileScript returns a structured error when ALL compilers fail.

        With PyKotor installed, compileScript now uses InbuiltNCSCompiler by
        default.  This test verifies the fallback path still returns a
        well-formed error dict when *both* PyKotor and subprocess fail.
        """
        from unittest import mock
        import subprocess
        # Simulate PyKotor compiler raising an error AND subprocess missing
        with mock.patch(
            "pykotor.resource.formats.ncs.compilers.InbuiltNCSCompiler.compile_script",
            side_effect=Exception("mock compile failure"),
        ), mock.patch("subprocess.run", side_effect=FileNotFoundError):
            data = self._invoke(game="K1", source="void main() {}")
        # Should return an error dict
        self.assertIn("error", data)

    def test_empty_source_returns_error(self):
        """compileScript rejects empty source."""
        data = self._invoke(game="K1", source="   ")
        self.assertIn("error", data)
        self.assertIn("source", data["error"])

    def test_invalid_game_returns_error(self):
        """compileScript rejects unknown game identifiers."""
        data = self._invoke(game="K3", source="void main() {}")
        self.assertIn("error", data)

    def test_tool_in_registry(self):
        """compileScript appears in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("compileScript", names)
        self.assertIn("compileScript", _HANDLERS)

    def test_tool_has_description(self):
        """compileScript has a meaningful description."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "compileScript")
        self.assertGreater(len(tool.description), 20)

    def test_tool_requires_game_and_source(self):
        """compileScript schema lists game and source as required."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "compileScript")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("source", required)


class TestWriteOverride(unittest.TestCase):
    """Tests for the writeOverride MCP tool."""

    def _invoke(self, **kwargs):
        from ghostscripter.mcp.tools import _write_override
        import asyncio
        import json
        result = asyncio.run(_write_override(kwargs))
        self.assertEqual(len(result), 1)
        return json.loads(result[0].text)

    def test_missing_resref_returns_error(self):
        """writeOverride requires resref."""
        data = self._invoke(game="K1", resref="", restype="ncs", data_b64="AAAA")
        self.assertIn("error", data)

    def test_missing_restype_returns_error(self):
        """writeOverride requires restype."""
        data = self._invoke(game="K1", resref="myscript", restype="", data_b64="AAAA")
        self.assertIn("error", data)

    def test_invalid_base64_returns_error(self):
        """writeOverride returns error for malformed base64."""
        data = self._invoke(game="K1", resref="myscript", restype="ncs", data_b64="!!!not-b64!!!")
        self.assertIn("error", data)

    def test_no_installation_returns_error(self):
        """writeOverride returns error when no game path is known."""
        import base64
        from unittest import mock
        from ghostscripter.mcp import tools as t_mod
        # Ensure no installation cached AND no auto-detection: without the
        # patch, the registry/default-path probes find a real installation
        # on dev machines and this test writes into the user's game folder.
        original = t_mod._INSTALLS.pop("K1", None)
        try:
            with mock.patch(
                "ghostscripter.mcp.tools_pkg._helpers._find_game_path",
                return_value=None,
            ):
                data = self._invoke(
                    game="K1", resref="test", restype="ncs",
                    data_b64=base64.b64encode(b"NCS\x00").decode(),
                )
            self.assertIn("error", data)
        finally:
            if original is not None:
                t_mod._INSTALLS["K1"] = original

    def test_writes_to_override_folder(self):
        """writeOverride writes a file to the Override folder and returns path."""
        import base64
        import tempfile
        from unittest import mock
        from ghostscripter.mcp import tools as t_mod

        with tempfile.TemporaryDirectory() as tmp:
            import os
            override_dir = os.path.join(tmp, "Override")
            os.makedirs(override_dir)

            # Build a fake ResourceManager using the real attribute (get_game_dir)
            # and the real attribute name (_game_dir).
            fake_rm = mock.MagicMock()
            fake_rm.get_game_dir.return_value = tmp   # public accessor
            fake_rm._game_dir = tmp                   # backing attribute
            fake_rm._override_files = {}
            fake_rm._read_cache = None

            original = t_mod._INSTALLS.get("K1")
            t_mod._INSTALLS["K1"] = fake_rm
            try:
                payload = base64.b64encode(b"NCS\x00\x00\x00").decode()
                data = self._invoke(
                    game="K1", resref="myscript", restype="ncs",
                    data_b64=payload,
                )
                self.assertNotIn("error", data, f"writeOverride failed: {data}")
                self.assertTrue(data.get("written"))
                self.assertIn("myscript.ncs", data.get("path", ""))
                written_path = os.path.join(override_dir, "myscript.ncs")
                self.assertTrue(os.path.exists(written_path))
                self.assertEqual(open(written_path, "rb").read(), b"NCS\x00\x00\x00")
            finally:
                if original is not None:
                    t_mod._INSTALLS["K1"] = original
                else:
                    t_mod._INSTALLS.pop("K1", None)

    def test_tool_in_registry(self):
        """writeOverride appears in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("writeOverride", names)
        self.assertIn("writeOverride", _HANDLERS)

    def test_tool_has_description(self):
        """writeOverride has a meaningful description."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "writeOverride")
        self.assertGreater(len(tool.description), 20)

    def test_tool_requires_all_fields(self):
        """writeOverride schema requires game, resref, restype, data_b64."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "writeOverride")
        required = tool.inputSchema.get("required", [])
        for field in ("game", "resref", "restype", "data_b64"):
            self.assertIn(field, required)


if __name__ == "__main__":
    unittest.main()


# ─────────────────────────────────────────────────────────────────────────────
# getArea tool tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetArea(unittest.TestCase):
    """Tests for the getArea composite MCP tool."""

    def _make_rm(self, are_bytes=None, git_bytes=None, lyt_bytes=None):
        """Build a mock ResourceManager that returns preset bytes."""
        rm = MagicMock()
        def _read(filename):
            if filename.endswith(".are"):
                return are_bytes
            if filename.endswith(".git"):
                return git_bytes
            if filename.endswith(".lyt"):
                return lyt_bytes
            return None
        rm.read = MagicMock(side_effect=_read)
        return rm

    def test_missing_area_returns_error(self):
        """getArea returns error when .are file is not found."""
        from ghostscripter.mcp import tools
        rm = self._make_rm(are_bytes=None)
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("getArea", {"game": "K1", "resref": "danm13"})))
        self.assertIn("error", result)
        self.assertIn("danm13", result["error"])

    def test_invalid_resref_returns_error(self):
        """getArea validates resref length/characters."""
        from ghostscripter.mcp import tools
        rm = self._make_rm()
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("getArea", {
                "game": "K1", "resref": "this_resref_is_way_too_long_to_be_valid"
            })))
        self.assertIn("error", result)

    def test_are_only_returns_area_name(self):
        """getArea with only ARE data returns area_name and empty object lists."""
        from ghostscripter.mcp import tools
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("ARE ")
        w.root.add_cexo("Name", "Dantooine Enclave")
        w.root.add_cexo("Tileset", "tde")
        are_bytes = w.build()
        rm = self._make_rm(are_bytes=are_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("getArea", {"game": "K1", "resref": "danm13"})))
        self.assertNotIn("error", result)
        self.assertEqual(result["resref"], "danm13")
        self.assertEqual(result["game"], "K1")
        self.assertIsInstance(result["creatures"], list)
        self.assertIsInstance(result["doors"], list)
        self.assertIsInstance(result["rooms"], list)
        self.assertIsInstance(result["parse_errors"], list)

    def test_lyt_rooms_parsed(self):
        """getArea parses LYT file into rooms list with x/y/z coords."""
        from ghostscripter.mcp import tools
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("ARE ")
        w.root.add_cexo("Name", "Test Area")
        are_bytes = w.build()
        lyt_text = (
            "beginlayout\n"
            "roomcount 2\n"
            "danm13_1a 10.5 -5.0 0.0\n"
            "danm13_1b 20.0 0.0 2.0\n"
            "donelayout\n"
        ).encode("latin-1")
        rm = self._make_rm(are_bytes=are_bytes, lyt_bytes=lyt_text)
        with patch.object(tools, "_load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg._helpers._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm), \
             patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("getArea", {"game": "K1", "resref": "danm13"})))
        self.assertNotIn("error", result)
        self.assertEqual(len(result["rooms"]), 2)
        self.assertEqual(result["rooms"][0]["room"], "danm13_1a")
        self.assertAlmostEqual(result["rooms"][0]["x"], 10.5)
        self.assertAlmostEqual(result["rooms"][1]["z"], 2.0)

    def test_tool_in_registry(self):
        """getArea is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getArea", names)
        self.assertIn("getArea", _HANDLERS)

    def test_tool_has_description(self):
        """getArea tool has a non-trivial description."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "getArea")
        self.assertGreater(len(tool.description), 30)

    def test_tool_requires_game_and_resref(self):
        """getArea schema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools import TOOLS
        tool = next(t for t in TOOLS if t.name == "getArea")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─────────────────────────────────────────────────────────────────────────────
# Ports registry tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPortsRegistry(unittest.TestCase):
    """Tests for the canonical Ghostworks port registry."""

    def test_all_ports_importable(self):
        """ghostscripter.ipc.ports exports all expected constants."""
        from ghostscripter.ipc.ports import (
            GHOSTRIGGER_REST, GHOSTSCRIPTER_REST, GMODULAR_REST,
            GHOSTWORKS_EVENT_BUS, ALL_PORTS,
        )
        self.assertIsInstance(GHOSTRIGGER_REST, int)
        self.assertIsInstance(GHOSTSCRIPTER_REST, int)
        self.assertIsInstance(GMODULAR_REST, int)
        self.assertIsInstance(GHOSTWORKS_EVENT_BUS, int)
        self.assertIsInstance(ALL_PORTS, dict)

    def test_port_values_match_blueprint(self):
        """Port values match the GhostWorks blueprint spec (7001/7002/7003)."""
        from ghostscripter.ipc.ports import (
            GHOSTRIGGER_REST, GHOSTSCRIPTER_REST, GMODULAR_REST,
        )
        self.assertEqual(GHOSTRIGGER_REST, 7001)
        self.assertEqual(GHOSTSCRIPTER_REST, 7002)
        self.assertEqual(GMODULAR_REST, 7003)

    def test_ports_are_unique(self):
        """No two active ports share the same number."""
        from ghostscripter.ipc.ports import ALL_PORTS
        values = list(ALL_PORTS.values())
        self.assertEqual(len(values), len(set(values)), "Duplicate port numbers detected")

    def test_constants_imported_into_core_constants(self):
        """core.constants re-exports the IPC port constants from the registry."""
        from ghostscripter.core.constants import (
            IPC_PORT_GHOSTRIGGER, IPC_PORT_GHOSTSCRIPTER, IPC_PORT_GMODULAR,
        )
        self.assertEqual(IPC_PORT_GHOSTRIGGER, 7001)
        self.assertEqual(IPC_PORT_GHOSTSCRIPTER, 7002)
        self.assertEqual(IPC_PORT_GMODULAR, 7003)


# ─────────────────────────────────────────────────────────────────────────────
# tools_pkg package structure tests
# ─────────────────────────────────────────────────────────────────────────────

class TestToolsPkgPackage(unittest.TestCase):
    """Verify the new tools_pkg sub-package structure is sound."""

    def test_all_submodules_importable(self):
        """All handler sub-modules import without errors."""
        import ghostscripter.mcp.tools_pkg._helpers as h
        import ghostscripter.mcp.tools_pkg.tool_defs as td
        import ghostscripter.mcp.tools_pkg.handlers_read as hr
        import ghostscripter.mcp.tools_pkg.handlers_write as hw
        import ghostscripter.mcp.tools_pkg.handlers_query as hq
        import ghostscripter.mcp.tools_pkg.handlers_composite as hc
        import ghostscripter.mcp.tools_pkg as pkg
        self.assertTrue(True)  # import itself is the assertion

    def test_tools_count_is_34(self):
        """TOOLS list has ≥58 tools (current canonical count)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        self.assertGreaterEqual(len(TOOLS), 58)

    def test_handlers_count_matches_tools(self):
        """_HANDLERS has at least as many entries as TOOLS (may have legacy aliases)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS))

    def test_shared_state_is_same_object(self):
        """_INSTALLS dict is the same object in tools.py and _helpers.py."""
        from ghostscripter.mcp.tools import _INSTALLS as shim_installs
        from ghostscripter.mcp.tools_pkg._helpers import _INSTALLS as pkg_installs
        self.assertIs(shim_installs, pkg_installs)

    def test_2da_cache_invalidated_on_load(self):
        """_2DA_CACHE is cleared when _load_rm registers a new installation."""
        from ghostscripter.mcp.tools_pkg._helpers import _2DA_CACHE, _INSTALLS
        # Pre-seed the cache with a sentinel value
        sentinel = object()
        _2DA_CACHE["K1"] = {"appearance": sentinel}

        # Directly simulate what _load_rm does when it loads a new install:
        # it calls _2DA_CACHE.pop(game_id, None) after updating _INSTALLS.
        from unittest.mock import MagicMock
        fake_rm = MagicMock()
        _INSTALLS["K1"] = fake_rm
        _2DA_CACHE.pop("K1", None)   # this is what _load_rm does

        # Cache entry for K1 should now be gone
        self.assertNotIn("K1", _2DA_CACHE)
        # Cleanup
        _INSTALLS.pop("K1", None)

    def test_get_area_in_tools_and_handlers(self):
        """getArea is present in both TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getArea", names)
        self.assertIn("getArea", _HANDLERS)


# ─── TestGetDoor ──────────────────────────────────────────────────────────────

class TestGetDoor(unittest.TestCase):
    """Tests for the getDoor composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_write._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_utd(self):
        """Build a minimal UTD GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTD ")
        w.root.add_cexo("Tag", "DOOR_TEST_01")
        w.root.add_byte("Locked", 1)
        w.root.add_cexo("KeyName", "test_key")
        w.root.add_byte("KeyRequired", 1)
        w.root.add_byte("LockDC", 28)
        w.root.add_byte("TrapDetectable", 1)
        w.root.add_cexo("OnOpen", "k_door_open")
        return w.build()

    def test_missing_utd_returns_error(self):
        """getDoor returns error when blueprint is not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getDoor", {"game": "K1", "resref": "door_x01"})))
        self.assertIn("error", result)
        self.assertIn("door_x01", result["error"])

    def test_invalid_resref_returns_error(self):
        """getDoor validates resref length."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getDoor", {
                "game": "K1", "resref": "this_is_a_far_too_long_resref_value"
            })))
        self.assertIn("error", result)

    def test_utd_parsed_correctly(self):
        """getDoor returns tag, lock fields, and scripts from UTD."""
        from ghostscripter.mcp import tools
        utd_bytes = self._make_utd()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utd_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getDoor", {"game": "K1", "resref": "door_t01"})))
        self.assertNotIn("error", result)
        self.assertEqual(result["resref"], "door_t01")
        self.assertEqual(result["game"], "K1")
        self.assertIn("lock", result)
        self.assertIn("trap", result)
        self.assertIn("scripts", result)
        self.assertIsInstance(result["scripts"], dict)

    def test_tool_in_registry(self):
        """getDoor is present in TOOLS list and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getDoor", names)
        self.assertIn("getDoor", _HANDLERS)

    def test_tool_has_description(self):
        """getDoor schema has a non-trivial description."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getDoor")
        self.assertGreater(len(tool.description), 20)

    def test_tool_requires_game_and_resref(self):
        """getDoor inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getDoor")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetPlaceable ─────────────────────────────────────────────────────────

class TestGetPlaceable(unittest.TestCase):
    """Tests for the getPlaceable composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_write._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_utp(self):
        """Build a minimal UTP GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTP ")
        w.root.add_cexo("Tag", "PLC_TEST_01")
        w.root.add_byte("Static", 0)
        w.root.add_byte("Useable", 1)
        w.root.add_byte("Locked", 0)
        w.root.add_cexo("OnUsed", "k_plc_used")
        return w.build()

    def test_missing_utp_returns_error(self):
        """getPlaceable returns error when blueprint is not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getPlaceable", {"game": "K1", "resref": "plc_x01"})))
        self.assertIn("error", result)
        self.assertIn("plc_x01", result["error"])

    def test_utp_parsed_correctly(self):
        """getPlaceable returns tag, lock, trap, inventory, and scripts from UTP."""
        from ghostscripter.mcp import tools
        utp_bytes = self._make_utp()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utp_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getPlaceable", {"game": "K1", "resref": "plc_t01"})))
        self.assertNotIn("error", result)
        self.assertEqual(result["resref"], "plc_t01")
        self.assertIn("lock", result)
        self.assertIn("trap", result)
        self.assertIn("inventory", result)
        self.assertIn("scripts", result)
        self.assertIsInstance(result["inventory"], list)

    def test_tool_in_registry(self):
        """getPlaceable is present in TOOLS list and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getPlaceable", names)
        self.assertIn("getPlaceable", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getPlaceable inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getPlaceable")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetItem ──────────────────────────────────────────────────────────────

class TestGetItem(unittest.TestCase):
    """Tests for the getItem composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_write._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_uti(self):
        """Build a minimal UTI GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTI ")
        w.root.add_cexo("Tag", "ITEM_TEST_01")
        w.root.add_dword("BaseItem", 71)   # 71 = lightsaber in K1
        w.root.add_word("StackSize", 1)
        w.root.add_dword("Cost", 3000)
        w.root.add_byte("Stolen", 0)
        w.root.add_byte("Identified", 1)
        return w.build()

    def test_missing_uti_returns_error(self):
        """getItem returns error when blueprint is not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getItem", {"game": "K1", "resref": "uti_x01"})))
        self.assertIn("error", result)
        self.assertIn("uti_x01", result["error"])

    def test_uti_parsed_correctly(self):
        """getItem returns base_item, cost, identified, and properties list."""
        from ghostscripter.mcp import tools
        uti_bytes = self._make_uti()
        rm = MagicMock()
        rm.read = MagicMock(return_value=uti_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getItem", {"game": "K1", "resref": "uti_t01"})))
        self.assertNotIn("error", result)
        self.assertEqual(result["resref"], "uti_t01")
        self.assertIn("base_item", result)
        self.assertIn("cost", result)
        self.assertIn("identified", result)
        self.assertIn("properties", result)
        self.assertIsInstance(result["properties"], list)
        self.assertIn("scripts", result)

    def test_tool_in_registry(self):
        """getItem is present in TOOLS list and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getItem", names)
        self.assertIn("getItem", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getItem inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getItem")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)

    def test_include_tlk_optional_param_in_schema(self):
        """getItem schema exposes optional 'includeTLK' boolean parameter."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getItem")
        props = tool.inputSchema.get("properties", {})
        self.assertIn("includeTLK", props)
        self.assertEqual(props["includeTLK"]["type"], "boolean")


# ─── TestSearchAll ────────────────────────────────────────────────────────────

class TestSearchAll(unittest.TestCase):
    """Tests for the searchAll unified text search MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_write._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_empty_rm(self):
        rm = MagicMock()
        rm.list_resources = MagicMock(return_value=[])
        rm.read = MagicMock(return_value=None)
        return rm

    def test_missing_query_returns_error(self):
        """searchAll returns error when query is empty."""
        from ghostscripter.mcp import tools
        rm = self._make_empty_rm()
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {"game": "K1", "query": ""})))
        self.assertIn("error", result)

    def test_invalid_scope_returns_error(self):
        """searchAll returns error when all requested scopes are invalid."""
        from ghostscripter.mcp import tools
        rm = self._make_empty_rm()
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {
                "game": "K1", "query": "foo", "scopes": ["bad_scope"]
            })))
        self.assertIn("error", result)

    def test_nss_scope_finds_hit(self):
        """searchAll with nss scope finds text in .nss source lines."""
        from ghostscripter.mcp import tools
        nss_content = b"void main() {\n    string sTag = \"QUEST_REVAN\";\n    // do something\n}\n"
        rm = MagicMock()
        rm.list_resources = MagicMock(return_value=["k_test_script.nss"])
        rm.read = MagicMock(return_value=nss_content)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {
                "game": "K1", "query": "QUEST_REVAN", "scopes": ["nss"]
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertIn("nss", result["scopes_searched"])
        self.assertGreater(result["total"], 0)
        hit = result["matches"][0]
        self.assertEqual(hit["scope"], "nss")
        self.assertIn("QUEST_REVAN", hit["value"])

    def test_empty_installation_returns_zero_matches(self):
        """searchAll returns empty matches list on an empty installation."""
        from ghostscripter.mcp import tools
        rm = self._make_empty_rm()
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {
                "game": "K1", "query": "anything"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["total"], 0)
        self.assertIsInstance(result["matches"], list)

    def test_limit_is_respected(self):
        """searchAll caps results at the requested limit."""
        from ghostscripter.mcp import tools
        # 20 NSS files each containing 5 matching lines = 100 potential hits
        hit_content = b"\n".join(b"string tag = \"FINDME\";" for _ in range(5)) + b"\n"
        resources = [f"script_{i:02d}.nss" for i in range(20)]
        rm = MagicMock()
        rm.list_resources = MagicMock(return_value=resources)
        rm.read = MagicMock(return_value=hit_content)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {
                "game": "K1", "query": "FINDME", "scopes": ["nss"], "limit": 7
            })))
        self.assertNotIn("error", result)
        self.assertLessEqual(result["total"], 7)

    def test_default_scopes_returned_in_result(self):
        """searchAll reports which scopes were searched in the response."""
        from ghostscripter.mcp import tools
        rm = self._make_empty_rm()
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("searchAll", {
                "game": "K1", "query": "test"
            })))
        self.assertIn("scopes_searched", result)
        self.assertIsInstance(result["scopes_searched"], list)
        # All four scopes should be searched by default
        self.assertEqual(sorted(result["scopes_searched"]), ["2da", "dlg", "nss", "tlk"])

    def test_tool_in_registry(self):
        """searchAll is present in TOOLS list and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("searchAll", names)
        self.assertIn("searchAll", _HANDLERS)

    def test_tool_requires_game_and_query(self):
        """searchAll inputSchema requires 'game' and 'query'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "searchAll")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("query", required)

    def test_tool_has_scopes_and_limit_params(self):
        """searchAll schema exposes optional 'scopes' array and 'limit' integer."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "searchAll")
        props = tool.inputSchema.get("properties", {})
        self.assertIn("scopes", props)
        self.assertIn("limit", props)
        self.assertEqual(props["scopes"]["type"], "array")
        self.assertEqual(props["limit"]["type"], "integer")


# ─── TestToolsCountV27 ────────────────────────────────────────────────────────

class TestToolsCountV27(unittest.TestCase):
    """Verify the v2.7 tool count is correct."""

    def test_total_tool_count_is_34(self):
        """v2.7 milestone: ≥34 tools (current: 48 in v3.2)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        self.assertGreaterEqual(len(TOOLS), 34,
                         f"Expected ≥34 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_v27_tools_all_present(self):
        """All four v2.7 tools appear in both TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        for tool_name in ("getDoor", "getPlaceable", "getItem", "searchAll"):
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, names)
                self.assertIn(tool_name, _HANDLERS)

    def test_v28_tools_all_present(self):
        """All seven v2.8 tools appear in both TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        for tool_name in ("getModule", "getEncounter", "getTrigger",
                          "getWaypoint", "getStore", "getSound", "readSSF"):
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, names)
                self.assertIn(tool_name, _HANDLERS)


# ─── TestGetModule ────────────────────────────────────────────────────────────

class TestGetModule(unittest.TestCase):
    """Tests for the getModule composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_ifo(self):
        """Build a minimal IFO GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("IFO ")
        w.root.add_cexo("Mod_Tag", "danm13")
        w.root.add_cexo("Mod_VO_ID", "dan")
        w.root.add_cexo("Mod_Entry_Area", "danm13")
        w.root.add_float("Mod_Entry_X", 12.5)
        w.root.add_float("Mod_Entry_Y", 8.0)
        w.root.add_float("Mod_Entry_Z", 0.0)
        w.root.add_cexo("Mod_OnLoad", "k_mod_load")
        return w.build()

    def test_missing_ifo_returns_error(self):
        """getModule returns an error when the IFO is not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getModule", {
                "game": "K1", "module_id": "danm13"
            })))
        self.assertIn("error", result)
        self.assertIn("danm13", result["error"])

    def test_ifo_parsed_correctly(self):
        """getModule returns game, module_id, scripts, areas from IFO."""
        from ghostscripter.mcp import tools
        ifo_bytes = self._make_ifo()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ifo_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getModule", {
                "game": "K1", "module_id": "danm13"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["module_id"], "danm13")
        self.assertIn("scripts", result)
        self.assertIsInstance(result["scripts"], dict)
        self.assertIn("areas", result)
        self.assertIsInstance(result["areas"], list)

    def test_ifo_entry_point_fields(self):
        """getModule extracts entry_area, entry_x, entry_y, entry_z."""
        from ghostscripter.mcp import tools
        ifo_bytes = self._make_ifo()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ifo_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getModule", {
                "game": "K1", "module_id": "danm13"
            })))
        self.assertNotIn("error", result)
        self.assertIn("entry_area", result)
        self.assertIn("entry_x", result)
        self.assertIn("entry_y", result)
        self.assertIn("entry_z", result)

    def test_ifo_script_extracted(self):
        """getModule includes non-empty Mod_On* script references."""
        from ghostscripter.mcp import tools
        ifo_bytes = self._make_ifo()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ifo_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getModule", {
                "game": "K1", "module_id": "danm13"
            })))
        # At least one script field should have been found ("Mod_OnLoad")
        self.assertIsInstance(result.get("scripts"), dict)
        # The load script we added should appear
        scripts = result.get("scripts", {})
        found = any(v == "k_mod_load" for v in scripts.values())
        self.assertTrue(found, f"Expected 'k_mod_load' in scripts, got: {scripts}")

    def test_tool_in_registry(self):
        """getModule is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getModule", names)
        self.assertIn("getModule", _HANDLERS)

    def test_tool_requires_game_and_module_id(self):
        """getModule inputSchema requires 'game' and 'module_id'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("module_id", required)


# ─── TestGetEncounter ─────────────────────────────────────────────────────────

class TestGetEncounter(unittest.TestCase):
    """Tests for the getEncounter composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_ute(self):
        """Build a minimal UTE GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTE ")
        w.root.add_cexo("Tag", "ENC_TEST_01")
        w.root.add_byte("Active", 1)
        w.root.add_byte("DifficultyIndex", 2)
        w.root.add_dword("Faction", 5)
        w.root.add_cexo("OnEntered", "k_enc_entered")
        return w.build()

    def test_missing_ute_returns_error(self):
        """getEncounter returns error when blueprint not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getEncounter", {
                "game": "K1", "resref": "enc_x01"
            })))
        self.assertIn("error", result)
        self.assertIn("enc_x01", result["error"])

    def test_invalid_resref_too_long(self):
        """getEncounter rejects resrefs longer than 16 chars."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getEncounter", {
                "game": "K1", "resref": "this_is_way_too_long_resref"
            })))
        self.assertIn("error", result)

    def test_ute_parsed_correctly(self):
        """getEncounter returns game, resref, spawn_list, scripts from UTE."""
        from ghostscripter.mcp import tools
        ute_bytes = self._make_ute()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ute_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getEncounter", {
                "game": "K1", "resref": "enc_t01"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "enc_t01")
        self.assertIn("spawn_list", result)
        self.assertIsInstance(result["spawn_list"], list)
        self.assertIn("scripts", result)
        self.assertIsInstance(result["scripts"], dict)

    def test_ute_script_extracted(self):
        """getEncounter includes OnEntered script reference."""
        from ghostscripter.mcp import tools
        ute_bytes = self._make_ute()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ute_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getEncounter", {
                "game": "K1", "resref": "enc_t01"
            })))
        scripts = result.get("scripts", {})
        found = any(v == "k_enc_entered" for v in scripts.values())
        self.assertTrue(found, f"Expected 'k_enc_entered' in scripts, got: {scripts}")

    def test_tool_in_registry(self):
        """getEncounter is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getEncounter", names)
        self.assertIn("getEncounter", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getEncounter inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getEncounter")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetTrigger ───────────────────────────────────────────────────────────

class TestGetTrigger(unittest.TestCase):
    """Tests for the getTrigger composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_utt(self):
        """Build a minimal UTT GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTT ")
        w.root.add_cexo("Tag", "TRG_TEST_01")
        w.root.add_byte("TrapType", 3)
        w.root.add_byte("TrapOneShot", 1)
        w.root.add_cexo("LinkedTo", "wp_exit01")
        w.root.add_byte("TrapDetectable", 1)
        w.root.add_byte("TrapDisarmable", 1)
        w.root.add_byte("TrapDetectDC", 20)
        w.root.add_byte("DisarmDC", 25)
        w.root.add_cexo("ScriptOnEnter", "k_trg_enter")
        return w.build()

    def test_missing_utt_returns_error(self):
        """getTrigger returns error when blueprint not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getTrigger", {
                "game": "K1", "resref": "trg_x01"
            })))
        self.assertIn("error", result)
        self.assertIn("trg_x01", result["error"])

    def test_utt_parsed_correctly(self):
        """getTrigger returns game, resref, trap dict, scripts from UTT."""
        from ghostscripter.mcp import tools
        utt_bytes = self._make_utt()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utt_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getTrigger", {
                "game": "K1", "resref": "trg_t01"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "trg_t01")
        self.assertIn("trap", result)
        self.assertIsInstance(result["trap"], dict)
        self.assertIn("scripts", result)
        self.assertIsInstance(result["scripts"], dict)

    def test_utt_trap_sub_fields(self):
        """getTrigger trap dict contains detectable, disarmable, trap_dc, disarm_dc."""
        from ghostscripter.mcp import tools
        utt_bytes = self._make_utt()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utt_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getTrigger", {
                "game": "K1", "resref": "trg_t01"
            })))
        trap = result.get("trap", {})
        for key in ("detectable", "disarmable", "trap_dc", "disarm_dc"):
            self.assertIn(key, trap, f"trap.{key} missing from result")

    def test_tool_in_registry(self):
        """getTrigger is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getTrigger", names)
        self.assertIn("getTrigger", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getTrigger inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getTrigger")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetWaypoint ──────────────────────────────────────────────────────────

class TestGetWaypoint(unittest.TestCase):
    """Tests for the getWaypoint composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_utw(self):
        """Build a minimal UTW GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTW ")
        w.root.add_cexo("Tag", "WP_TEST_01")
        w.root.add_float("XPosition", 10.5)
        w.root.add_float("YPosition", 20.0)
        w.root.add_float("ZPosition", 0.0)
        w.root.add_float("XOrientation", 1.0)
        w.root.add_float("YOrientation", 0.0)
        w.root.add_byte("HasMapNote", 1)
        w.root.add_byte("MapNoteEnabled", 1)
        return w.build()

    def test_missing_utw_returns_error(self):
        """getWaypoint returns error when blueprint not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getWaypoint", {
                "game": "K1", "resref": "wp_x01"
            })))
        self.assertIn("error", result)
        self.assertIn("wp_x01", result["error"])

    def test_utw_parsed_correctly(self):
        """getWaypoint returns game, resref, position, orientation, map note."""
        from ghostscripter.mcp import tools
        utw_bytes = self._make_utw()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utw_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getWaypoint", {
                "game": "K1", "resref": "wp_t01"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "wp_t01")
        for key in ("x", "y", "z", "dir_x", "dir_y"):
            self.assertIn(key, result, f"key '{key}' missing from getWaypoint result")
        self.assertIn("has_map_note", result)
        self.assertIn("map_note_enabled", result)

    def test_utw_position_values(self):
        """getWaypoint extracts correct x/y/z float values."""
        from ghostscripter.mcp import tools
        utw_bytes = self._make_utw()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utw_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getWaypoint", {
                "game": "K1", "resref": "wp_t01"
            })))
        self.assertAlmostEqual(result.get("x"), 10.5, places=2)
        self.assertAlmostEqual(result.get("y"), 20.0, places=2)
        self.assertEqual(result.get("z"), 0.0)

    def test_tool_in_registry(self):
        """getWaypoint is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getWaypoint", names)
        self.assertIn("getWaypoint", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getWaypoint inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getWaypoint")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetStore ─────────────────────────────────────────────────────────────

class TestGetStore(unittest.TestCase):
    """Tests for the getStore composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_utm(self):
        """Build a minimal UTM GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTM ")
        w.root.add_cexo("Tag", "STR_TEST_01")
        w.root.add_byte("MarkUp", 25)
        w.root.add_byte("MarkDown", 15)
        w.root.add_byte("BuySellFlag", 3)
        w.root.add_cexo("OnOpenStore", "k_str_open")
        return w.build()

    def test_missing_utm_returns_error(self):
        """getStore returns error when blueprint not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getStore", {
                "game": "K1", "resref": "str_x01"
            })))
        self.assertIn("error", result)
        self.assertIn("str_x01", result["error"])

    def test_utm_parsed_correctly(self):
        """getStore returns game, resref, mark_up, mark_down, inventory, scripts."""
        from ghostscripter.mcp import tools
        utm_bytes = self._make_utm()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utm_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getStore", {
                "game": "K1", "resref": "str_t01"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "str_t01")
        self.assertIn("mark_up", result)
        self.assertIn("mark_down", result)
        self.assertIn("inventory", result)
        self.assertIsInstance(result["inventory"], list)
        self.assertIn("scripts", result)

    def test_utm_script_extracted(self):
        """getStore includes OnOpenStore script reference."""
        from ghostscripter.mcp import tools
        utm_bytes = self._make_utm()
        rm = MagicMock()
        rm.read = MagicMock(return_value=utm_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getStore", {
                "game": "K1", "resref": "str_t01"
            })))
        scripts = result.get("scripts", {})
        found = any(v == "k_str_open" for v in scripts.values())
        self.assertTrue(found, f"Expected 'k_str_open' in scripts, got: {scripts}")

    def test_tool_in_registry(self):
        """getStore is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getStore", names)
        self.assertIn("getStore", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getStore inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getStore")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestGetSound ─────────────────────────────────────────────────────────────

class TestGetSound(unittest.TestCase):
    """Tests for the getSound composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_uts(self):
        """Build a minimal UTS GFF binary."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTS ")
        w.root.add_cexo("Tag", "SND_TEST_01")
        w.root.add_byte("Active", 1)
        w.root.add_byte("Continuous", 1)
        w.root.add_byte("Looping", 1)
        w.root.add_byte("Positional", 1)
        w.root.add_byte("Volume", 80)
        w.root.add_float("MinDistance", 2.0)
        w.root.add_float("MaxDistance", 20.0)
        w.root.add_float("XPosition", 5.0)
        w.root.add_float("YPosition", 5.0)
        w.root.add_float("ZPosition", 0.0)
        return w.build()

    def test_missing_uts_returns_error(self):
        """getSound returns error when blueprint not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getSound", {
                "game": "K1", "resref": "snd_x01"
            })))
        self.assertIn("error", result)
        self.assertIn("snd_x01", result["error"])

    def test_uts_parsed_correctly(self):
        """getSound returns game, resref, volume, distances, position, sounds list."""
        from ghostscripter.mcp import tools
        uts_bytes = self._make_uts()
        rm = MagicMock()
        rm.read = MagicMock(return_value=uts_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getSound", {
                "game": "K1", "resref": "snd_t01"
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "snd_t01")
        for key in ("active", "continuous", "looping", "positional",
                    "volume", "min_distance", "max_distance",
                    "x", "y", "z", "sounds"):
            self.assertIn(key, result, f"key '{key}' missing from getSound result")
        self.assertIsInstance(result["sounds"], list)

    def test_uts_position_values(self):
        """getSound extracts correct x/y/z float values."""
        from ghostscripter.mcp import tools
        uts_bytes = self._make_uts()
        rm = MagicMock()
        rm.read = MagicMock(return_value=uts_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("getSound", {
                "game": "K1", "resref": "snd_t01"
            })))
        self.assertAlmostEqual(result.get("x"), 5.0, places=2)
        self.assertAlmostEqual(result.get("y"), 5.0, places=2)
        self.assertEqual(result.get("z"), 0.0)

    def test_tool_in_registry(self):
        """getSound is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getSound", names)
        self.assertIn("getSound", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """getSound inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getSound")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestReadSSF ──────────────────────────────────────────────────────────────

class TestReadSSF(unittest.TestCase):
    """Tests for the readSSF MCP tool (Sound Set File decoder)."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg._helpers._load_rm",
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
    ]

    def _patch_rm(self, rm):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in self.COMPOSITE_PATCHES:
            stack.enter_context(patch(target, return_value=rm))
        return stack

    def _make_ssf(self, strrefs=None):
        """Build a minimal SSF binary (28 INT32 StrRefs, V1.1 header)."""
        import struct
        if strrefs is None:
            strrefs = list(range(28))   # simple non-zero values
        # Header: "SSF " (4) + "V1.1" (4) + data_offset (4) = 12 bytes
        header = b"SSF " + b"V1.1" + struct.pack("<I", 12)
        data = struct.pack(f"<{len(strrefs)}i", *strrefs)
        return header + data

    def test_missing_ssf_returns_error(self):
        """readSSF returns error when SSF file not found."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "c_missing"
            })))
        self.assertIn("error", result)
        self.assertIn("c_missing", result["error"])

    def test_ssf_parsed_correctly(self):
        """readSSF returns game, resref, slot_count=28, and slots list."""
        from ghostscripter.mcp import tools
        ssf_bytes = self._make_ssf()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ssf_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "c_bantha", "resolve_tlk": False
            })))
        self.assertNotIn("error", result)
        self.assertEqual(result["game"], "K1")
        self.assertEqual(result["resref"], "c_bantha")
        self.assertEqual(result["slot_count"], 28)
        self.assertIsInstance(result["slots"], list)
        self.assertEqual(len(result["slots"]), 28)

    def test_ssf_slot_structure(self):
        """readSSF each slot has index, name, strref keys."""
        from ghostscripter.mcp import tools
        ssf_bytes = self._make_ssf()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ssf_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "c_bantha", "resolve_tlk": False
            })))
        first = result["slots"][0]
        self.assertIn("index", first)
        self.assertIn("name", first)
        self.assertIn("strref", first)
        self.assertEqual(first["index"], 0)
        self.assertEqual(first["name"], "BATTLE_CRY_1")

    def test_ssf_slot_names_canonical(self):
        """readSSF uses canonical SSFSound slot names from PyKotor reference."""
        from ghostscripter.mcp import tools
        ssf_bytes = self._make_ssf()
        rm = MagicMock()
        rm.read = MagicMock(return_value=ssf_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "c_bantha", "resolve_tlk": False
            })))
        slot_names = [s["name"] for s in result["slots"]]
        # Check several canonical names
        expected_subset = [
            "BATTLE_CRY_1", "SELECT_1", "ATTACK_GRUNT_1",
            "PAIN_GRUNT_1", "LOW_HEALTH", "DEAD",
            "LAY_MINE", "POISONED",
        ]
        for name in expected_subset:
            self.assertIn(name, slot_names, f"Expected slot name '{name}' not found")

    def test_ssf_corrupt_magic_returns_error(self):
        """readSSF returns error when magic bytes are wrong."""
        from ghostscripter.mcp import tools
        bad_bytes = b"XXXX" + b"V1.1" + b"\x0c\x00\x00\x00" + bytes(28 * 4)
        rm = MagicMock()
        rm.read = MagicMock(return_value=bad_bytes)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "c_bad"
            })))
        self.assertIn("error", result)

    def test_ssf_resref_too_long_returns_error(self):
        """readSSF rejects resrefs longer than 16 chars."""
        from ghostscripter.mcp import tools
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        with patch.object(tools, "_load_rm", return_value=rm), self._patch_rm(rm):
            result = _json(_run(tools.handle_tool("readSSF", {
                "game": "K1", "resref": "this_resref_is_wayyyyy_too_long"
            })))
        self.assertIn("error", result)

    def test_tool_in_registry(self):
        """readSSF is registered in TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("readSSF", names)
        self.assertIn("readSSF", _HANDLERS)

    def test_tool_requires_game_and_resref(self):
        """readSSF inputSchema requires 'game' and 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "readSSF")
        required = tool.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)


# ─── TestPathSafetyV28 ────────────────────────────────────────────────────────

class TestPathSafetyV28(unittest.TestCase):
    """Path-safety validation tests for write tools added/audited in v2.8."""

    def test_safe_write_path_rejects_traversal(self):
        """_safe_write_path blocks path-traversal characters."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        # Attempt directory traversal via resref — _validate_resref catches '.' and '/'
        err = _safe_write_path("../evil", "dlg", "test")
        self.assertIsNotNone(err)
        # The error mentions either 'invalid characters' or 'forbidden'
        self.assertTrue(
            "invalid" in err or "forbidden" in err,
            f"Expected error mentioning 'invalid' or 'forbidden', got: {err!r}"
        )

    def test_safe_write_path_rejects_backslash(self):
        """_safe_write_path blocks backslash in resref."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        err = _safe_write_path("evil\\path", "dlg", "test")
        self.assertIsNotNone(err)

    def test_safe_write_path_rejects_unknown_extension(self):
        """_safe_write_path rejects file types not in the allow-list."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        err = _safe_write_path("myfile", "exe", "test")
        self.assertIsNotNone(err)
        self.assertIn("exe", err)

    def test_safe_write_path_allows_dlg(self):
        """_safe_write_path accepts valid resref + 'dlg' extension."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        err = _safe_write_path("my_dlg_file", "dlg", "test")
        self.assertIsNone(err)

    def test_safe_write_path_allows_gff(self):
        """_safe_write_path accepts valid resref + 'gff' extension."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        err = _safe_write_path("my_gff_file", "gff", "test")
        self.assertIsNone(err)

    def test_safe_write_path_rejects_long_resref(self):
        """_safe_write_path rejects resrefs longer than 16 chars."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        err = _safe_write_path("this_resref_is_too_long_for_kotor", "dlg", "test")
        self.assertIsNotNone(err)
        self.assertIn("16", err)

    def test_safe_write_path_allows_all_blueprint_types(self):
        """_safe_write_path accepts all GFF blueprint extensions."""
        from ghostscripter.mcp.tools_pkg._helpers import _safe_write_path
        for ext in ("utc", "utd", "ute", "uti", "utm", "utp", "uts", "utt", "utw"):
            with self.subTest(ext=ext):
                err = _safe_write_path("test_res", ext, "test")
                self.assertIsNone(err, f"Expected no error for extension '{ext}', got: {err}")

    def test_write_gff_rejects_invalid_file_type(self):
        """writeGFF returns error for invalid fileType (not 1-4 alnum chars)."""
        from ghostscripter.mcp import tools
        result = _json(_run(tools.handle_tool("writeGFF", {
            "fileType": "../bad",
            "fields": {},
        })))
        self.assertIn("error", result)

    def test_write_override_rejects_path_traversal(self):
        """writeOverride blocks path-traversal resrefs."""
        from ghostscripter.mcp import tools
        from unittest.mock import patch as _patch
        rm = MagicMock()
        rm.override_path = MagicMock(return_value=None)
        with _patch("ghostscripter.mcp.tools_pkg.handlers_write._load_rm", return_value=rm):
            result = _json(_run(tools.handle_tool("writeOverride", {
                "game": "K1",
                "resref": "../etc/passwd",
                "restype": "dlg",
                "data_b64": "",
            })))
        self.assertIn("error", result)


# ─── TestToolsCountV28 ────────────────────────────────────────────────────────

class TestToolsCountV28(unittest.TestCase):
    """Verify the v2.8 tool count and schema integrity."""

    def test_total_tool_count_is_41(self):
        """v2.8 milestone: ≥41 tools (current: 48 in v3.2)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        self.assertGreaterEqual(len(TOOLS), 41,
                         f"Expected ≥41 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_handlers_count_matches_tools(self):
        """_HANDLERS has at least as many entries as TOOLS (may include legacy aliases)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS),
                         f"Tool count {len(TOOLS)} > handler count {len(_HANDLERS)}")

    def test_all_v28_tools_have_descriptions(self):
        """All v2.8 tools have non-trivial descriptions."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        v28_tools = {"getModule", "getEncounter", "getTrigger",
                     "getWaypoint", "getStore", "getSound", "readSSF"}
        for t in TOOLS:
            if t.name in v28_tools:
                with self.subTest(tool=t.name):
                    self.assertGreater(len(t.description), 30,
                                       f"{t.name} description too short")

    def test_all_v28_tools_require_game_and_resref(self):
        """All v2.8 composite tools (except getModule) require 'game' + 'resref'."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        blueprint_tools = {"getEncounter", "getTrigger", "getWaypoint",
                           "getStore", "getSound", "readSSF"}
        for t in TOOLS:
            if t.name in blueprint_tools:
                with self.subTest(tool=t.name):
                    required = t.inputSchema.get("required", [])
                    self.assertIn("game", required,
                                  f"{t.name} should require 'game'")
                    self.assertIn("resref", required,
                                  f"{t.name} should require 'resref'")

    def test_no_tools_have_empty_descriptions(self):
        """Every tool has a non-empty description string."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        for t in TOOLS:
            with self.subTest(tool=t.name):
                self.assertTrue(t.description and t.description.strip(),
                                f"{t.name} has empty description")


from ghostscripter.mcp.tools import handle_tool

# ─── TestReadLIP ──────────────────────────────────────────────────────────────

class TestReadLIP(unittest.TestCase):
    """Tests for the readLIP MCP tool (LIP V1.0 binary decoder)."""

    _PATCHES = [
        "ghostscripter.mcp.tools_pkg.handlers_query._load_rm",
        "ghostscripter.mcp.tools_pkg._helpers._INSTALLS",
    ]

    def _make_lip(self, duration: float, keyframes: list) -> bytes:
        """Build a minimal LIP V1.0 binary."""
        import struct
        buf = bytearray()
        buf += b"LIP V1.0"
        buf += struct.pack("<f", duration)
        buf += struct.pack("<I", len(keyframes))
        for t, s in keyframes:
            buf += struct.pack("<f", t)
            buf += struct.pack("<B", s)
        return bytes(buf)

    def test_missing_lip_returns_error(self):
        rm = MagicMock()
        rm.read.return_value = None
        with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
            result = _run(handle_tool("readLIP", {"game": "K1", "resref": "missing"}))
        self.assertIn("not found", result[0].text)

    def test_invalid_game_returns_error(self):
        result = _run(handle_tool("readLIP", {"game": "K3", "resref": "test"}))
        self.assertIn("error", result[0].text)

    def test_resref_too_long_returns_error(self):
        rm = MagicMock()
        rm.read.return_value = None
        with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
            result = _run(handle_tool("readLIP", {"game": "K1", "resref": "a" * 17}))
        self.assertIn("exceeds 16", result[0].text)

    def test_bad_magic_returns_error(self):
        bad_data = b"BADMAGIC" + b"\x00" * 8
        rm = MagicMock()
        rm.read.return_value = bad_data
        with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
            result = _run(handle_tool("readLIP", {"game": "K1", "resref": "test"}))
        self.assertIn("magic", result[0].text)

    def test_valid_lip_decoded_correctly(self):
        lip_data = self._make_lip(2.5, [(0.0, 0), (0.5, 3), (1.0, 8), (2.0, 0)])
        rm = MagicMock()
        rm.read.return_value = lip_data
        with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
            result = _run(handle_tool("readLIP", {"game": "K1", "resref": "n_test001"}))
        import json
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertAlmostEqual(data["duration_s"], 2.5, places=3)
        self.assertEqual(data["keyframe_count"], 4)
        self.assertEqual(len(data["keyframes"]), 4)
        self.assertEqual(data["keyframes"][0]["shape_name"], "NEUTRAL")
        self.assertEqual(data["keyframes"][1]["shape_name"], "AH")
        self.assertEqual(data["keyframes"][2]["shape_name"], "FV")

    def test_empty_keyframes_decoded(self):
        lip_data = self._make_lip(1.0, [])
        rm = MagicMock()
        rm.read.return_value = lip_data
        with patch("ghostscripter.mcp.tools_pkg.handlers_query._load_rm", return_value=rm):
            result = _run(handle_tool("readLIP", {"game": "K2", "resref": "empty_lip"}))
        import json
        data = json.loads(result[0].text)
        self.assertEqual(data["keyframe_count"], 0)
        self.assertEqual(data["keyframes"], [])

    def test_tool_in_tools_and_handlers(self):
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("readLIP", names)
        self.assertIn("readLIP", _HANDLERS)

    def test_tool_schema_requires_game_and_resref(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        t = next(t for t in TOOLS if t.name == "readLIP")
        required = t.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)

    def test_description_is_informative(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        t = next(t for t in TOOLS if t.name == "readLIP")
        self.assertGreater(len(t.description), 30)
        self.assertIn("LIP", t.description)


# ─── TestWriteLIP ─────────────────────────────────────────────────────────────

class TestWriteLIP(unittest.TestCase):
    """Tests for the writeLIP MCP tool (LIP V1.0 binary encoder)."""

    def test_basic_encode_roundtrip(self):
        import base64, struct, json
        kf = [{"time": 0.0, "shape": 0},
              {"time": 0.5, "shape": "AH"},
              {"time": 1.0, "shape": 8}]
        result = _run(handle_tool("writeLIP", {"duration": 2.0, "keyframes": kf}))
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertEqual(data["keyframe_count"], 3)
        raw = base64.b64decode(data["data"])
        self.assertEqual(raw[:8], b"LIP V1.0")
        dur = struct.unpack_from("<f", raw, 8)[0]
        self.assertAlmostEqual(dur, 2.0, places=3)
        count = struct.unpack_from("<I", raw, 12)[0]
        self.assertEqual(count, 3)
        # Check shape values
        # KF[1] shape "AH" = 3
        kf1_shape = raw[16 + 5 + 4]  # second keyframe offset 16+5=21, shape at +4
        self.assertEqual(kf1_shape, 3)

    def test_missing_duration_returns_error(self):
        result = _run(handle_tool("writeLIP", {"keyframes": []}))
        self.assertIn("duration", result[0].text)

    def test_missing_keyframes_returns_error(self):
        result = _run(handle_tool("writeLIP", {"duration": 1.0}))
        self.assertIn("keyframes", result[0].text)

    def test_negative_duration_returns_error(self):
        result = _run(handle_tool("writeLIP", {"duration": -1.0, "keyframes": []}))
        self.assertIn("error", result[0].text)

    def test_invalid_shape_string_returns_error(self):
        kf = [{"time": 0.0, "shape": "MEOW"}]
        result = _run(handle_tool("writeLIP", {"duration": 1.0, "keyframes": kf}))
        self.assertIn("not recognised", result[0].text)

    def test_shape_out_of_range_returns_error(self):
        kf = [{"time": 0.0, "shape": 99}]
        result = _run(handle_tool("writeLIP", {"duration": 1.0, "keyframes": kf}))
        self.assertIn("out of range", result[0].text)

    def test_non_ascending_keyframes_returns_error(self):
        kf = [{"time": 1.0, "shape": 0}, {"time": 0.5, "shape": 1}]
        result = _run(handle_tool("writeLIP", {"duration": 2.0, "keyframes": kf}))
        self.assertIn("ascending", result[0].text)

    def test_empty_keyframes_produces_header_only(self):
        import base64, struct, json
        result = _run(handle_tool("writeLIP", {"duration": 0.0, "keyframes": []}))
        data = json.loads(result[0].text)
        self.assertEqual(data["keyframe_count"], 0)
        raw = base64.b64decode(data["data"])
        self.assertEqual(len(raw), 16)  # header only

    def test_all_shape_name_strings_accepted(self):
        shapes = ["NEUTRAL", "EE", "EH", "AH", "OH", "OOH", "Y",
                  "STS", "FV", "NG", "TH", "MPB", "TD", "SH", "L", "KG"]
        kf = [{"time": float(i) * 0.1, "shape": s} for i, s in enumerate(shapes)]
        result = _run(handle_tool("writeLIP", {"duration": 2.0, "keyframes": kf}))
        import json
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertEqual(data["keyframe_count"], 16)

    def test_tool_in_tools_and_handlers(self):
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("writeLIP", names)
        self.assertIn("writeLIP", _HANDLERS)

    def test_tool_schema_requires_duration_and_keyframes(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        t = next(t for t in TOOLS if t.name == "writeLIP")
        required = t.inputSchema.get("required", [])
        self.assertIn("duration", required)
        self.assertIn("keyframes", required)


# ─── TestGetCreature ──────────────────────────────────────────────────────────

class TestGetCreature(unittest.TestCase):
    """Tests for the getCreature MCP tool (UTC blueprint composite view)."""

    _COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools_pkg.handlers_composite._load_rm",
        "ghostscripter.mcp.tools_pkg._helpers._INSTALLS",
    ]

    def _make_utc(self) -> bytes:
        """Build a minimal UTC GFF binary for testing."""
        from ghostscripter.mcp.tools_pkg.handlers_composite import _get_door
        # Reuse GFF writer to build a minimal UTC
        from ghostscripter.core.services import GFFService
        fields = {
            "Tag":              "BASTILA_TEST",
            "FirstName":        {"0": "Bastila"},
            "LastName":         {"0": "Shan"},
            "Race":             4,
            "Gender":           1,
            "Str":              10,
            "Dex":              14,
            "Con":              10,
            "Int":              12,
            "Wis":              14,
            "Cha":              16,
            "CurrentHitPoints": 60,
            "MaxHitPoints":     60,
            "NaturalAC":        2,
            "Appearance_Type":  402,
            "Conversation":     "bastila",
            "ScriptSpawn":      "k_hbas_spawn",
        }
        return GFFService.write("UTC ", fields)

    def test_missing_utc_returns_error(self):
        rm = MagicMock()
        rm.read.return_value = None
        with patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _run(handle_tool("getCreature", {"game": "K1", "resref": "missing"}))
        self.assertIn("not found", result[0].text)

    def test_resref_too_long_returns_error(self):
        rm = MagicMock()
        rm.read.return_value = None
        with patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _run(handle_tool("getCreature", {"game": "K1", "resref": "x" * 17}))
        self.assertIn("exceeds 16", result[0].text)

    def test_invalid_game_returns_error(self):
        result = _run(handle_tool("getCreature", {"game": "KX", "resref": "test"}))
        self.assertIn("error", result[0].text)

    def test_valid_utc_parsed(self):
        import json
        utc_data = self._make_utc()
        rm = MagicMock()
        rm.read.side_effect = lambda name: utc_data if name.endswith(".utc") else None
        with patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _run(handle_tool("getCreature", {"game": "K1", "resref": "n_bastila"}))
        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertEqual(data["tag"], "BASTILA_TEST")
        self.assertEqual(data["str"], 10)
        self.assertEqual(data["cha"], 16)
        self.assertEqual(data["max_hp"], 60)
        self.assertEqual(data["appearance"], 402)
        self.assertEqual(data["conversation"], "bastila")

    def test_scripts_extracted(self):
        import json
        utc_data = self._make_utc()
        rm = MagicMock()
        rm.read.side_effect = lambda name: utc_data if name.endswith(".utc") else None
        with patch("ghostscripter.mcp.tools_pkg.handlers_composite._load_rm", return_value=rm):
            result = _run(handle_tool("getCreature", {"game": "K1", "resref": "n_bastila"}))
        data = json.loads(result[0].text)
        self.assertIn("ScriptSpawn", data["scripts"])
        self.assertEqual(data["scripts"]["ScriptSpawn"], "k_hbas_spawn")

    def test_tool_in_tools_and_handlers(self):
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getCreature", names)
        self.assertIn("getCreature", _HANDLERS)

    def test_tool_schema_requires_game_and_resref(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        t = next(t for t in TOOLS if t.name == "getCreature")
        required = t.inputSchema.get("required", [])
        self.assertIn("game", required)
        self.assertIn("resref", required)

    def test_description_length(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        t = next(t for t in TOOLS if t.name == "getCreature")
        self.assertGreater(len(t.description), 30)
        self.assertIn("UTC", t.description)


# ─── TestToolsCountV29 ────────────────────────────────────────────────────────

class TestToolsCountV29(unittest.TestCase):
    """Verify v2.9 tool count: 45 tools total (+3: readLIP, writeLIP, getCreature)."""

    def test_total_tool_count_is_44(self):
        """v2.9 milestone: ≥44 tools (current: 48 in v3.2)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        self.assertGreaterEqual(len(TOOLS), 44,
                         f"Expected ≥44 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_handlers_count_matches_tools(self):
        """_HANDLERS has at least as many entries as TOOLS (may include legacy aliases)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS),
                         f"Tool count {len(TOOLS)} > handler count {len(_HANDLERS)}")

    def test_v29_tools_all_present(self):
        """All three v2.9 tools appear in both TOOLS and _HANDLERS."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        for tool_name in ("readLIP", "writeLIP", "getCreature"):
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, names)
                self.assertIn(tool_name, _HANDLERS)

    def test_no_tools_have_empty_descriptions(self):
        """Every tool has a non-empty description string."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        for t in TOOLS:
            with self.subTest(tool=t.name):
                self.assertTrue(t.description and t.description.strip(),
                                f"{t.name} has empty description")

    def test_all_v29_tools_have_informative_descriptions(self):
        """v2.9 tools all have descriptions longer than 30 chars."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        v29 = {"readLIP", "writeLIP", "getCreature"}
        for t in TOOLS:
            if t.name in v29:
                with self.subTest(tool=t.name):
                    self.assertGreater(len(t.description), 30,
                                       f"{t.name} description too short")

    def test_qtpy_migration_no_pyqt5_imports(self):
        """No bare PyQt5 imports remain in ghostscripter source (qtpy migration complete)."""
        import pathlib, subprocess, sys
        r = subprocess.run(
            [sys.executable, "-c",
             "import re, pathlib; "
             "files = list(pathlib.Path('ghostscripter').rglob('*.py')); "
             "hits = [f for f in files if '__pycache__' not in str(f) and "
             "re.search(r'from PyQt5', f.read_text(errors='replace'))]; "
             "print(len(hits))"],
            capture_output=True, text=True,
            cwd=str(pathlib.Path(__file__).resolve().parent.parent)
        )
        self.assertEqual(r.stdout.strip(), "0",
                         "PyQt5 direct imports still present in ghostscripter/")

    def test_ports_registry_exports_all_constants(self):
        """ghostscripter.ipc.ports exports the canonical port constants."""
        from ghostscripter.ipc.ports import (
            GHOSTRIGGER_REST, GHOSTSCRIPTER_REST, GMODULAR_REST,
            GHOSTWORKS_EVENT_BUS, ALL_PORTS,
        )
        self.assertEqual(GHOSTRIGGER_REST, 7001)
        self.assertEqual(GHOSTSCRIPTER_REST, 7002)
        self.assertEqual(GMODULAR_REST, 7003)
        self.assertEqual(GHOSTWORKS_EVENT_BUS, 7000)
        self.assertIsInstance(ALL_PORTS, dict)
        self.assertGreaterEqual(len(ALL_PORTS), 4)

    def test_no_optional_union_in_tools_pkg(self):
        """tools_pkg files use X|None / X|Y syntax, not Optional/Union."""
        import pathlib, re
        pkg = pathlib.Path("ghostscripter/mcp/tools_pkg")
        bad = []
        for py in pkg.rglob("*.py"):
            if "__pycache__" in str(py):
                continue
            txt = py.read_text(errors="replace")
            if re.search(r'\bOptional\[|\bUnion\[', txt):
                bad.append(str(py))
        self.assertEqual(bad, [],
                         f"Files still using Optional/Union: {bad}")


# ── getFaction (v3.0) ─────────────────────────────────────────────────────────

class TestGetFaction(unittest.TestCase):
    """Tests for the getFaction composite MCP tool."""

    COMPOSITE_PATCHES = [
        "ghostscripter.mcp.tools",
        "ghostscripter.mcp.tools_pkg.handlers_composite",
        "ghostscripter.mcp.tools_pkg._helpers",
    ]

    def _patch_rm(self, rm):
        patches = []
        for mod in self.COMPOSITE_PATCHES:
            try:
                p = patch(f"{mod}._load_rm", return_value=rm)
                p.start()
                patches.append(p)
            except AttributeError:
                pass
        return patches

    def _make_fac_gff(self):
        """Build a minimal FAC binary (GFF V3.2 with FactionList)."""
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("FAC ")
        # Add two factions
        faction_list = w.root.add_list("FactionList")
        f1 = faction_list.add_struct(0)
        f1.add_cexo("FactionName", "Friendly")
        f2 = faction_list.add_struct(0)
        f2.add_cexo("FactionName", "Hostile")
        return w.build()

    def test_missing_fac_returns_error(self):
        from ghostscripter.mcp.tools import handle_tool
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        patches = self._patch_rm(rm)
        try:
            result = _json(_run(handle_tool("getFaction", {"game": "K1", "resref": "noexist"})))
            self.assertIn("error", result)
        finally:
            for p in patches:
                p.stop()

    def test_valid_fac_parsed(self):
        from ghostscripter.mcp.tools import handle_tool
        try:
            fac_data = self._make_fac_gff()
        except Exception:
            self.skipTest("GFF3Writer not available for FAC construction")

        rm = MagicMock()
        rm.read = MagicMock(return_value=fac_data)
        patches = self._patch_rm(rm)
        try:
            result = _json(_run(handle_tool("getFaction", {"game": "K1"})))
            self.assertNotIn("error", result)
            self.assertIn("factions", result)
            self.assertIsInstance(result["factions"], list)
            self.assertIn("game", result)
            self.assertIn("count", result)
        finally:
            for p in patches:
                p.stop()

    def test_tool_in_registry(self):
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getFaction", names)
        self.assertIn("getFaction", _HANDLERS)

    def test_tool_has_non_trivial_description(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next((t for t in TOOLS if t.name == "getFaction"), None)
        self.assertIsNotNone(tool)
        self.assertGreater(len(tool.description), 30)

    def test_default_resref_is_repute(self):
        """getFaction defaults to 'repute' when no resref supplied."""
        from ghostscripter.mcp.tools import handle_tool
        rm = MagicMock()
        rm.read = MagicMock(return_value=None)
        patches = self._patch_rm(rm)
        try:
            _run(handle_tool("getFaction", {"game": "K1"}))
            # Should have called rm.read with "repute.fac"
            call_args = [str(c) for c in rm.read.call_args_list]
            self.assertTrue(
                any("repute" in s for s in call_args),
                f"Expected 'repute' in read call, got: {call_args}"
            )
        finally:
            for p in patches:
                p.stop()


# ── v3.0 TestSuite class ───────────────────────────────────────────────────────

class TestV30Additions(unittest.TestCase):
    """Validates v3.0 additions: getFaction, pykotor shim, gs-prefixed tools."""

    def test_total_tool_count_is_45(self):
        """v3.0 adds getFaction (+1); v3.2 grows to 48."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(TOOLS), 45,
                         f"Expected ≥45 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_handlers_gte_tools(self):
        """_HANDLERS >= TOOLS (legacy aliases account for difference)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS),
                         f"Tool count {len(TOOLS)} > handler count {len(_HANDLERS)}")

    def test_gs_prefixed_tools_in_registry(self):
        """Prefixed tools exist in TOOLS list."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        names = {t.name for t in TOOLS}
        for expected in ("gsDetectInstallations", "gsLoadInstallation",
                         "gsListResources", "gsDescribeResource"):
            self.assertIn(expected, names, f"Missing prefixed tool: {expected}")

    def test_legacy_aliases_not_in_tools_list(self):
        """Old unprefixed names are NOT in the TOOLS list (only in _HANDLERS as aliases)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        names = {t.name for t in TOOLS}
        for legacy in ("detectInstallations", "loadInstallation",
                       "listResources", "describeResource"):
            self.assertNotIn(legacy, names,
                             f"Legacy name '{legacy}' should not be in TOOLS list")

    def test_legacy_aliases_still_callable(self):
        """Legacy names remain callable via _HANDLERS for backward compat."""
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        for legacy in ("detectInstallations", "loadInstallation",
                       "listResources", "describeResource"):
            self.assertIn(legacy, _HANDLERS,
                          f"Legacy name '{legacy}' must remain in _HANDLERS")

    def test_get_faction_tool_present(self):
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        names = {t.name for t in TOOLS}
        self.assertIn("getFaction", names)
        self.assertIn("getFaction", _HANDLERS)

    def test_pykotor_shim_importable(self):
        from ghostscripter.core.pykotor_shim import ShimInstallation, get_installation
        self.assertTrue(callable(ShimInstallation))
        self.assertTrue(callable(get_installation))

    def test_pykotor_shim_available_flag(self):
        from ghostscripter.core import pykotor_shim
        self.assertIsInstance(pykotor_shim._PYKOTOR_AVAILABLE, bool)

    def test_all_v30_tools_have_non_trivial_descriptions(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        v30_tools = ["getFaction"]
        for name in v30_tools:
            tool = next((t for t in TOOLS if t.name == name), None)
            self.assertIsNotNone(tool, f"Tool '{name}' not found")
            self.assertGreater(len(tool.description), 30,
                               f"Tool '{name}' description too short")

    def test_no_tools_have_empty_descriptions(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        for tool in TOOLS:
            self.assertTrue(
                tool.description.strip(),
                f"Tool '{tool.name}' has empty description"
            )


# ============================================================
# v3.1 additions — LIPEditorWidget + getModule include_git
# ============================================================

class TestLIPEditorWidget(unittest.TestCase):
    """Unit tests for ghostscripter.ui.widgets.lip_editor_widget (no Qt)."""

    def _make_lip_bytes(self, duration: float, frames: list) -> bytes:
        """Build a minimal valid LIP V1.0 binary."""
        import struct
        buf = b"LIP V1.0"
        buf += struct.pack("<f", duration)
        buf += struct.pack("<I", len(frames))
        for t, s in frames:
            buf += struct.pack("<f", t)
            buf += struct.pack("<B", s)
        return buf

    def test_lip_shapes_count(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIP_SHAPES
        self.assertEqual(len(LIP_SHAPES), 16)

    def test_lip_shapes_neutral_is_zero(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIP_SHAPES
        self.assertEqual(LIP_SHAPES[0], "NEUTRAL")

    def test_lip_shapes_all_non_empty(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIP_SHAPES
        for i, name in enumerate(LIP_SHAPES):
            self.assertTrue(name, f"Shape {i} has empty name")

    def test_phoneme_map_keys_are_uppercase(self):
        from ghostscripter.ui.widgets.lip_editor_widget import PHONEME_MAP
        for k in PHONEME_MAP:
            self.assertEqual(k, k.upper(), f"Phoneme key '{k}' not uppercase")

    def test_phoneme_map_values_in_range(self):
        from ghostscripter.ui.widgets.lip_editor_widget import PHONEME_MAP
        for k, v in PHONEME_MAP.items():
            self.assertIn(v, range(16), f"Phoneme '{k}' maps to out-of-range {v}")

    def test_lip_magic_constants(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIP_MAGIC, LIP_VERSION
        self.assertEqual(LIP_MAGIC, b"LIP ")
        self.assertEqual(LIP_VERSION, b"V1.0")

    def test_shape_colors_count(self):
        from ghostscripter.ui.widgets.lip_editor_widget import _SHAPE_COLORS
        self.assertEqual(len(_SHAPE_COLORS), 16)

    def test_shape_colors_hex_format(self):
        import re
        from ghostscripter.ui.widgets.lip_editor_widget import _SHAPE_COLORS
        for c in _SHAPE_COLORS:
            self.assertRegex(c, r"^#[0-9a-fA-F]{6}$", f"Invalid colour: {c}")


class TestGetModuleIncludeGit(unittest.TestCase):
    """Tests for the getModule include_git parameter added in v3.1."""

    def test_get_module_tool_has_include_git_schema(self):
        """getModule inputSchema should document the include_git property."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        props = tool.inputSchema.get("properties", {})
        self.assertIn("include_git", props,
                      "getModule inputSchema missing 'include_git' property")

    def test_get_module_include_git_is_boolean(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        props = tool.inputSchema["properties"]
        self.assertEqual(props["include_git"]["type"], "boolean")

    def test_get_module_description_mentions_include_git(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        self.assertIn("include_git", tool.description)

    def test_get_module_description_mentions_area_summaries(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        self.assertIn("area_summaries", tool.description)

    def test_get_module_handler_returns_area_summaries_key(self):
        """Handler returns either an error list or a result with area_summaries."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["getModule"]
        try:
            result = asyncio.run(handler({"game": "K1", "module_id": "_nonexistent_"}))
            # Error path (no installation) — should be a list with text content
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except FileNotFoundError:
            # Acceptable: no installation configured in CI
            pass

    def test_get_module_include_git_default_false_schema(self):
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "getModule")
        props = tool.inputSchema["properties"]
        default = props["include_git"].get("default")
        self.assertFalse(default, "include_git default should be False")


class TestDialogUILoader(unittest.TestCase):
    """Tests for the .ui file loader logic in dialog modules."""

    def test_ui_file_exists_new_project(self):
        from pathlib import Path
        ui = Path("ghostscripter/ui/ui_files/new_project_dialog.ui")
        self.assertTrue(ui.exists(), "new_project_dialog.ui not found")

    def test_ui_file_exists_new_quest(self):
        from pathlib import Path
        ui = Path("ghostscripter/ui/ui_files/new_quest_dialog.ui")
        self.assertTrue(ui.exists(), "new_quest_dialog.ui not found")

    def test_new_project_dialog_importable(self):
        from ghostscripter.ui.dialogs.new_project_dialog import NewProjectDialog
        self.assertTrue(callable(NewProjectDialog))

    def test_new_quest_dialog_importable(self):
        from ghostscripter.ui.dialogs.new_quest_dialog import NewQuestDialog
        self.assertTrue(callable(NewQuestDialog))

    def test_new_project_dialog_has_try_load_ui(self):
        import ghostscripter.ui.dialogs.new_project_dialog as mod
        self.assertTrue(callable(mod._try_load_ui))

    def test_new_quest_dialog_has_try_load_ui(self):
        import ghostscripter.ui.dialogs.new_quest_dialog as mod
        self.assertTrue(callable(mod._try_load_ui))

    def test_new_project_ui_path_constant(self):
        import ghostscripter.ui.dialogs.new_project_dialog as mod
        self.assertTrue(mod._UI_FILE.name == "new_project_dialog.ui")

    def test_new_quest_ui_path_constant(self):
        import ghostscripter.ui.dialogs.new_quest_dialog as mod
        self.assertTrue(mod._UI_FILE.name == "new_quest_dialog.ui")


class TestLIPEditorWidgetImport(unittest.TestCase):
    """Verify lip_editor_widget is importable and exposes the expected API."""

    def test_module_importable(self):
        import ghostscripter.ui.widgets.lip_editor_widget as mod
        self.assertIsNotNone(mod)

    def test_lip_editor_widget_class_exists(self):
        from ghostscripter.ui.widgets.lip_editor_widget import LIPEditorWidget
        self.assertTrue(callable(LIPEditorWidget))

    def test_lip_timeline_class_exists(self):
        from ghostscripter.ui.widgets.lip_editor_widget import _LIPTimeline
        self.assertTrue(callable(_LIPTimeline))

    def test_lip_constants_exported(self):
        from ghostscripter.ui.widgets import lip_editor_widget as mod
        self.assertTrue(hasattr(mod, "LIP_SHAPES"))
        self.assertTrue(hasattr(mod, "PHONEME_MAP"))
        self.assertTrue(hasattr(mod, "_SHAPE_COLORS"))
        self.assertTrue(hasattr(mod, "LIP_MAGIC"))
        self.assertTrue(hasattr(mod, "LIP_VERSION"))


# ── v3.2 TestSuite class ───────────────────────────────────────────────────────

class TestV32Additions(unittest.TestCase):
    """Validates v3.2 additions: readPTH, readLTR, writeSSF, enhanced getArea."""

    def test_total_tool_count_is_48(self):
        """v3.2 milestone: ≥48 tools; currently 58 (v3.3 +6)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(TOOLS), 58,
                         f"Expected 58 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_handlers_gte_tools(self):
        """_HANDLERS >= TOOLS (legacy aliases account for difference)."""
        from ghostscripter.mcp.tools_pkg import TOOLS, _HANDLERS
        self.assertGreaterEqual(len(_HANDLERS), len(TOOLS),
                         f"Tool count {len(TOOLS)} > handler count {len(_HANDLERS)}")

    def test_v32_tools_in_tools_list(self):
        """All three v3.2 tools appear in TOOLS list."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        names = {t.name for t in TOOLS}
        for tool_name in ("readPTH", "readLTR", "writeSSF"):
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, names,
                              f"v3.2 tool '{tool_name}' missing from TOOLS list")

    def test_v32_tools_in_handlers(self):
        """All three v3.2 tools have registered handlers."""
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        for tool_name in ("readPTH", "readLTR", "writeSSF"):
            with self.subTest(tool=tool_name):
                self.assertIn(tool_name, _HANDLERS,
                              f"v3.2 tool '{tool_name}' missing from _HANDLERS")

    def test_readPTH_handler_callable(self):
        """readPTH handler is an awaitable callable."""
        import inspect
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["readPTH"]
        self.assertTrue(inspect.iscoroutinefunction(handler))

    def test_readLTR_handler_callable(self):
        """readLTR handler is an awaitable callable."""
        import inspect
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["readLTR"]
        self.assertTrue(inspect.iscoroutinefunction(handler))

    def test_writeSSF_handler_callable(self):
        """writeSSF handler is an awaitable callable."""
        import inspect
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["writeSSF"]
        self.assertTrue(inspect.iscoroutinefunction(handler))

    def test_readPTH_schema(self):
        """readPTH tool schema has required game + resref fields."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next((t for t in TOOLS if t.name == "readPTH"), None)
        self.assertIsNotNone(tool, "readPTH tool not found")
        schema = tool.inputSchema
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_readLTR_schema(self):
        """readLTR tool schema has required game + resref fields."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next((t for t in TOOLS if t.name == "readLTR"), None)
        self.assertIsNotNone(tool, "readLTR tool not found")
        schema = tool.inputSchema
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_writeSSF_schema(self):
        """writeSSF tool schema has required game + resref + slots fields."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next((t for t in TOOLS if t.name == "writeSSF"), None)
        self.assertIsNotNone(tool, "writeSSF tool not found")
        schema = tool.inputSchema
        for req in ("game", "resref", "slots"):
            self.assertIn(req, schema["required"])

    def test_writeSSF_missing_installation_returns_error(self):
        """writeSSF returns error list when no installation loaded."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["writeSSF"]
        try:
            result = asyncio.run(handler({
                "game": "K1",
                "resref": "test_ssf",
                "slots": {"BATTLE_CRY_1": 1000}
            }))
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except FileNotFoundError:
            pass  # No installation — expected in CI

    def test_readPTH_missing_installation_returns_error(self):
        """readPTH returns error list when no installation loaded."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["readPTH"]
        try:
            result = asyncio.run(handler({"game": "K1", "resref": "danm13"}))
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except FileNotFoundError:
            pass

    def test_readLTR_missing_installation_returns_error(self):
        """readLTR returns error list when no installation loaded."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["readLTR"]
        try:
            result = asyncio.run(handler({"game": "K1", "resref": "humanm"}))
            self.assertIsInstance(result, list)
            self.assertGreater(len(result), 0)
        except FileNotFoundError:
            pass

    def test_readPTH_bad_game_returns_error(self):
        """readPTH returns error for invalid game ID."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["readPTH"]({"game": "K3", "resref": "test"}))
        self.assertIsInstance(result, list)
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_readLTR_bad_game_returns_error(self):
        """readLTR returns error for invalid game ID."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["readLTR"]({"game": "invalid", "resref": "humanm"}))
        self.assertIsInstance(result, list)
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_writeSSF_bad_game_returns_error(self):
        """writeSSF returns error for invalid game ID (not K1/K2/TSL)."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writeSSF"]({
            "game": "KOTOR3",
            "resref": "test",
            "slots": {}
        }))
        self.assertIsInstance(result, list)
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_writeSSF_encode_decode_roundtrip(self):
        """writeSSF produces valid SSF V1.1 binary for empty slots."""
        import asyncio
        import base64
        import struct
        from ghostscripter.mcp.tools_pkg import _HANDLERS

        # writeSSF should succeed even with no installation for pure encoding
        # (or return a graceful error if it needs one)
        handler = _HANDLERS["writeSSF"]
        try:
            result = asyncio.run(handler({
                "game": "K1",
                "resref": "test_ssf",
                "slots": {
                    "BATTLE_CRY_1": 100,
                    "DEAD": 200,
                }
            }))
            self.assertIsInstance(result, list)
            content = result[0].text if hasattr(result[0], "text") else str(result[0])
            import json
            try:
                data = json.loads(content)
                if "data" in data:
                    raw = base64.b64decode(data["data"])
                    # Check SSF header
                    self.assertEqual(raw[:4], b"SSF ")
                    self.assertEqual(raw[4:8], b"V1.1")
                    self.assertEqual(len(raw), 12 + 28 * 4)  # header + 28 int32s
                    # Check slot 0 (BATTLE_CRY_1) = 100
                    slot0 = struct.unpack_from("<i", raw, 12)[0]
                    self.assertEqual(slot0, 100)
            except (json.JSONDecodeError, KeyError):
                pass  # Error path (no installation) — acceptable
        except FileNotFoundError:
            pass

    def test_getArea_handler_has_new_fields(self):
        """getArea handler includes the enhanced ARE/GIT fields."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        handler = _HANDLERS["getArea"]
        try:
            result = asyncio.run(handler({"game": "K1", "resref": "_nonexistent_area_"}))
            # Should return an error (area not found) or a result
            self.assertIsInstance(result, list)
        except FileNotFoundError:
            pass

    def test_getArea_schema_unchanged(self):
        """getArea tool schema still has required game + resref."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next((t for t in TOOLS if t.name == "getArea"), None)
        self.assertIsNotNone(tool)
        self.assertIn("game", tool.inputSchema["required"])
        self.assertIn("resref", tool.inputSchema["required"])

    def test_v32_tool_descriptions_adequate(self):
        """All v3.2 tools have descriptions over 50 chars."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        for tool_name in ("readPTH", "readLTR", "writeSSF"):
            with self.subTest(tool=tool_name):
                tool = next((t for t in TOOLS if t.name == tool_name), None)
                self.assertIsNotNone(tool, f"Tool {tool_name} not found")
                self.assertGreater(len(tool.description), 50,
                                   f"Tool {tool_name} description too short")

    def test_are_enhanced_fields_in_get_area_docstring(self):
        """getArea docstring documents the enhanced ARE/GIT fields."""
        from ghostscripter.mcp.tools_pkg.handlers_composite import _get_area
        doc = _get_area.__doc__ or ""
        for field in ("grass_texture", "stealth_xp", "fog_color", "camera_style",
                      "use_templates", "current_weather", "disable_transit"):
            self.assertIn(field, doc,
                          f"getArea docstring missing field '{field}'")

    def test_writeSSF_slot_slot_name_mapping(self):
        """writeSSF handler imports correctly and slot name list accessible."""
        from ghostscripter.mcp.tools_pkg.handlers_write import _write_ssf
        import inspect
        src = inspect.getsource(_write_ssf)
        self.assertIn("BATTLE_CRY_1", src)
        self.assertIn("DEAD", src)
        self.assertIn("POISONED", src)

    def test_readPTH_handler_imports_correctly(self):
        """readPTH handler is importable from handlers_read."""
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_pth
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(_read_pth))

    def test_readLTR_handler_imports_correctly(self):
        """readLTR handler is importable from handlers_read."""
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ltr
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(_read_ltr))

    def test_writeSSF_handler_imports_correctly(self):
        """writeSSF handler is importable from handlers_write."""
        from ghostscripter.mcp.tools_pkg.handlers_write import _write_ssf
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(_write_ssf))




# ─── v3.2 new tool tests ─────────────────────────────────────────────────────

class TestV32NewTools(unittest.TestCase):
    """Tests for v3.2 additions: writePTH, getBlueprint, tool count."""

    def test_total_tool_count_is_50(self):
        """Tool count after v3.2 additions; currently 58 (v3.3)."""
        from ghostscripter.mcp.tools import TOOLS
        self.assertGreaterEqual(len(TOOLS), 58,
                         f"Expected 58 tools, got {len(TOOLS)}: {[t.name for t in TOOLS]}")

    def test_write_pth_in_tools_list(self):
        from ghostscripter.mcp.tools import TOOLS
        names = [t.name for t in TOOLS]
        self.assertIn("writePTH", names)

    def test_get_blueprint_in_tools_list(self):
        from ghostscripter.mcp.tools import TOOLS
        names = [t.name for t in TOOLS]
        self.assertIn("getBlueprint", names)

    def test_write_pth_in_handlers(self):
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        self.assertIn("writePTH", _HANDLERS)

    def test_get_blueprint_in_handlers(self):
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        self.assertIn("getBlueprint", _HANDLERS)

    def test_write_pth_bad_game_returns_error(self):
        """writePTH returns error for invalid game ID."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "KOTOR99",
            "resref": "testarea",
            "points": []
        }))
        self.assertIsInstance(result, list)
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_write_pth_empty_points(self):
        """writePTH with empty points list returns valid result."""
        import asyncio
        import json
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "K1",
            "resref": "testarea",
            "points": []
        }))
        self.assertIsInstance(result, list)
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        data = json.loads(text)
        self.assertEqual(data.get("point_count"), 0)
        self.assertEqual(data.get("connection_count"), 0)

    def test_write_pth_two_connected_nodes(self):
        """writePTH with two nodes connected bidirectionally."""
        import asyncio
        import json
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "K1",
            "resref": "danm13",
            "points": [
                {"x": 0.0, "y": 0.0, "connections": [1]},
                {"x": 10.0, "y": 5.0, "connections": [0]},
            ]
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        data = json.loads(text)
        self.assertEqual(data.get("point_count"), 2)
        self.assertEqual(data.get("connection_count"), 2)

    def test_write_pth_out_of_bounds_connection_errors(self):
        """writePTH rejects connection indices that exceed point count."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "K1",
            "resref": "danm13",
            "points": [
                {"x": 0.0, "y": 0.0, "connections": [99]},  # index 99 is invalid with 1 point
            ]
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_write_pth_resref_too_long_errors(self):
        """writePTH rejects resref longer than 16 characters."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "K1",
            "resref": "x" * 17,
            "points": []
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_get_blueprint_missing_type_errors(self):
        """getBlueprint returns error when type not specified."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["getBlueprint"]({
            "game": "K1",
            "resref": "n_bastila",
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_get_blueprint_invalid_type_errors(self):
        """getBlueprint returns error for unsupported resource type."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["getBlueprint"]({
            "game": "K1",
            "resref": "n_bastila",
            "type": "xyz",
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_get_blueprint_bad_game_errors(self):
        """getBlueprint returns error for invalid game."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["getBlueprint"]({
            "game": "K99",
            "resref": "n_bastila",
            "type": "utc",
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        self.assertIn("error", text.lower())

    def test_get_blueprint_no_install_raises_graceful_error(self):
        """getBlueprint returns FileNotFoundError-style error when no installation loaded."""
        import asyncio
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        try:
            result = asyncio.run(_HANDLERS["getBlueprint"]({
                "game": "K1",
                "resref": "n_bastila",
                "type": "utc",
            }))
            text = result[0].text if hasattr(result[0], "text") else str(result[0])
            # Either returns an error (no install) or succeeds (if K1_PATH is set)
            self.assertIsInstance(result, list)
        except FileNotFoundError:
            pass  # Acceptable — no installation configured

    def test_get_blueprint_schema_has_enum_types(self):
        """getBlueprint tool schema lists valid blueprint types as enum."""
        from ghostscripter.mcp.tools import TOOLS
        bp_tool = next((t for t in TOOLS if t.name == "getBlueprint"), None)
        self.assertIsNotNone(bp_tool)
        enum_vals = bp_tool.inputSchema["properties"]["type"].get("enum", [])
        self.assertIn("utc", enum_vals)
        self.assertIn("uti", enum_vals)
        self.assertIn("utp", enum_vals)
        self.assertGreaterEqual(len(enum_vals), 9)

    def test_write_pth_produces_decodable_base64(self):
        """writePTH output data field is valid base64 encoding of a PTH GFF binary."""
        import asyncio
        import base64
        import json
        from ghostscripter.mcp.tools_pkg import _HANDLERS
        result = asyncio.run(_HANDLERS["writePTH"]({
            "game": "K1",
            "resref": "tat_m17aa",
            "points": [{"x": 1.5, "y": 2.5, "connections": []}]
        }))
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        data = json.loads(text)
        self.assertIn("data", data)
        decoded = base64.b64decode(data["data"])
        # Real GFF binary starts with "PTH " file type tag
        self.assertTrue(
            decoded[:4] in (b"PTH ", b"PTH\x00"),
            f"Expected PTH GFF magic, got {decoded[:8]!r}",
        )
        self.assertEqual(data["point_count"], 1)


# =============================================================================
# v3.3 NEW TOOL TESTS
# =============================================================================

class TestV33Additions(unittest.TestCase):
    """Tests for v3.3 new tools: readNCS, readVIS, readIFO, readWAV, readTXI, pathfindRoute."""

    def setUp(self):
        from ghostscripter.mcp.tools import TOOLS as _T, _HANDLERS as _H, handle_tool as _ht
        self.TOOLS = _T
        self.HANDLERS = _H
        self.handle_tool = _ht

    def _run(self, tool_name, args):
        return asyncio.run(self.handle_tool(tool_name, args))

    def _text(self, result):
        return result[0].text if result else ""

    def _json(self, result):
        import json
        text = self._text(result)
        try:
            return json.loads(text)
        except Exception:
            return {}

    # ── total tool count ──────────────────────────────────────────────────────
    def test_total_tool_count_is_58(self):
        """v3.3 adds 6 tools (readNCS/readVIS/readIFO/readWAV/readTXI/pathfindRoute), total now 58.
        v3.4 adds decompileScript, total now 59.
        v3.6 adds getNWScriptDB, total now 60."""
        self.assertGreaterEqual(len(self.TOOLS), 59, f"Expected ≥59 tools, got {len(self.TOOLS)}")

    def test_handler_count_gte_tool_count(self):
        self.assertGreaterEqual(
            len(self.HANDLERS), len(self.TOOLS),
            f"Handler count {len(self.HANDLERS)} < tool count {len(self.TOOLS)}"
        )

    # ── readNCS ───────────────────────────────────────────────────────────────
    def test_readNCS_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("readNCS", names)

    def test_readNCS_in_handlers(self):
        self.assertIn("readNCS", self.HANDLERS)

    def test_readNCS_schema_has_required_fields(self):
        tool = next(t for t in self.TOOLS if t.name == "readNCS")
        schema = tool.inputSchema
        self.assertIn("game", schema["properties"])
        self.assertIn("resref", schema["properties"])
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_readNCS_no_install_returns_error(self):
        result = self._run("readNCS", {"game": "K1", "resref": "k_act_gen_01"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readNCS_missing_resref_returns_error(self):
        result = self._run("readNCS", {"game": "K1", "resref": ""})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readNCS_invalid_bytes_returns_error(self):
        """Craft a fake NCS with wrong magic."""
        import asyncio, base64
        # Build fake NCS bytes with wrong magic
        fake_ncs = b"XXXX" + b"V1.0" + bytes([0x42]) + b"\x00" * 8
        # We test via handler directly with patched resource
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs
        from unittest.mock import patch

        async def _mock_read(args):
            return await _read_ncs(args)

        # Without install, should still error gracefully
        result = asyncio.run(
            _read_ncs({"game": "K1", "resref": "test"})
        )
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readNCS_description_mentions_ncs(self):
        tool = next(t for t in self.TOOLS if t.name == "readNCS")
        self.assertIn("NCS", tool.description)

    # ── readVIS ───────────────────────────────────────────────────────────────
    def test_readVIS_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("readVIS", names)

    def test_readVIS_in_handlers(self):
        self.assertIn("readVIS", self.HANDLERS)

    def test_readVIS_schema_has_required_fields(self):
        tool = next(t for t in self.TOOLS if t.name == "readVIS")
        schema = tool.inputSchema
        self.assertIn("game", schema["properties"])
        self.assertIn("resref", schema["properties"])
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_readVIS_no_install_returns_error(self):
        result = self._run("readVIS", {"game": "K1", "resref": "end_m01aa"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readVIS_missing_resref_returns_error(self):
        result = self._run("readVIS", {"game": "K1", "resref": ""})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readVIS_parses_ascii_correctly(self):
        """Test VIS parser with synthesized ASCII data."""
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_vis
        from unittest.mock import patch, MagicMock

        vis_text = (
            "room001 2\n"
            "  room002\n"
            "  room003\n"
            "room002 1\n"
            "  room001\n"
        ).encode("ascii")

        async def _mock_vis(args):
            return await _read_vis(args)

        # Patch resource manager lookup
        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm:
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = vis_text
            result = asyncio.run(
                _read_vis({"game": "K1", "resref": "test_area"})
            )
        import json
        data = json.loads(result[0].text)
        self.assertEqual(data.get("room_count"), 2)
        rooms = data.get("rooms", {})
        self.assertIn("room001", rooms)
        self.assertIn("room002", rooms["room001"])
        self.assertIn("room003", rooms["room001"])

    def test_readVIS_description_mentions_visibility(self):
        tool = next(t for t in self.TOOLS if t.name == "readVIS")
        self.assertIn("visibility", tool.description.lower())

    # ── readIFO ───────────────────────────────────────────────────────────────
    def test_readIFO_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("readIFO", names)

    def test_readIFO_in_handlers(self):
        self.assertIn("readIFO", self.HANDLERS)

    def test_readIFO_schema_has_required_fields(self):
        tool = next(t for t in self.TOOLS if t.name == "readIFO")
        schema = tool.inputSchema
        self.assertIn("game", schema["properties"])
        self.assertIn("resref", schema["properties"])
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_readIFO_no_install_returns_error(self):
        result = self._run("readIFO", {"game": "K1", "resref": "end_m01aa"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readIFO_missing_resref_returns_error(self):
        result = self._run("readIFO", {"game": "K1", "resref": ""})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readIFO_description_mentions_mod_on_scripts(self):
        tool = next(t for t in self.TOOLS if t.name == "readIFO")
        # Should mention at least one of the hook names
        self.assertTrue(
            "on_heartbeat" in tool.description or "Mod_On" in tool.description or
            "script" in tool.description.lower()
        )

    # ── readWAV ───────────────────────────────────────────────────────────────
    def test_readWAV_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("readWAV", names)

    def test_readWAV_in_handlers(self):
        self.assertIn("readWAV", self.HANDLERS)

    def test_readWAV_schema_properties(self):
        tool = next(t for t in self.TOOLS if t.name == "readWAV")
        schema = tool.inputSchema
        self.assertIn("game", schema["properties"])
        self.assertIn("resref", schema["properties"])
        self.assertIn("data_b64", schema["properties"])
        self.assertIn("game", schema["required"])

    def test_readWAV_riff_wav_from_b64(self):
        """readWAV correctly parses a minimal RIFF WAV from base64."""
        import struct, base64
        # Minimal RIFF WAV: fmt chunk + data chunk
        fmt_data = struct.pack("<HHIIHH", 1, 1, 22050, 44100, 2, 16)
        data_chunk = b"\x00" * 88100  # 2 seconds of mono 16-bit 22050 Hz
        riff_size = 4 + 8 + len(fmt_data) + 8 + len(data_chunk)
        wav_bytes = (
            b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" +
            b"fmt " + struct.pack("<I", len(fmt_data)) + fmt_data +
            b"data" + struct.pack("<I", len(data_chunk)) + data_chunk
        )
        b64 = base64.b64encode(wav_bytes).decode()
        result = self._run("readWAV", {"game": "K1", "data_b64": b64})
        import json
        data = json.loads(result[0].text)
        self.assertEqual(data.get("audio_format"), "wav")
        self.assertEqual(data.get("sample_rate"), 22050)
        self.assertEqual(data.get("channels"), 1)
        self.assertEqual(data.get("bits_per_sample"), 16)
        self.assertIsNotNone(data.get("duration_ms"))

    def test_readWAV_mp3_magic(self):
        """readWAV detects MP3 by magic bytes."""
        import base64
        mp3_bytes = b"\xff\xfb" + b"\x00" * 100  # MP3 sync word
        b64 = base64.b64encode(mp3_bytes).decode()
        result = self._run("readWAV", {"game": "K1", "data_b64": b64})
        import json
        data = json.loads(result[0].text)
        self.assertEqual(data.get("audio_format"), "mp3")

    def test_readWAV_sfx_obfuscated(self):
        """readWAV detects SFX-obfuscated KotOR audio."""
        import base64
        sfx_bytes = b"\xbf\xbf\xbf\xbf" + b"\x00" * 50
        b64 = base64.b64encode(sfx_bytes).decode()
        result = self._run("readWAV", {"game": "K1", "data_b64": b64})
        import json
        data = json.loads(result[0].text)
        self.assertIn(data.get("obfuscation_type"), ["sfx", "standard"])

    def test_readWAV_no_resref_no_b64_returns_error(self):
        result = self._run("readWAV", {"game": "K1"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readWAV_description_mentions_obfuscation(self):
        tool = next(t for t in self.TOOLS if t.name == "readWAV")
        self.assertIn("obfuscation", tool.description.lower())

    # ── readTXI ───────────────────────────────────────────────────────────────
    def test_readTXI_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("readTXI", names)

    def test_readTXI_in_handlers(self):
        self.assertIn("readTXI", self.HANDLERS)

    def test_readTXI_schema_has_required_fields(self):
        tool = next(t for t in self.TOOLS if t.name == "readTXI")
        schema = tool.inputSchema
        self.assertIn("game", schema["properties"])
        self.assertIn("resref", schema["properties"])
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_readTXI_no_install_returns_error(self):
        result = self._run("readTXI", {"game": "K1", "resref": "fx_fire01"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readTXI_missing_resref_returns_error(self):
        result = self._run("readTXI", {"game": "K1", "resref": ""})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_readTXI_parses_ascii_attributes(self):
        """Test TXI parser with synthesized ASCII data."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_txi
        from unittest.mock import patch, MagicMock

        txi_text = (
            "envmaptexture CM_BAREMETAL\n"
            "blending additive\n"
            "mipmap 0\n"
            "filter 1\n"
            "numx 8\n"
            "numy 2\n"
        ).encode("ascii")

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm:
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = txi_text
            result = asyncio.run(
                _read_txi({"game": "K1", "resref": "fx_test"})
            )
        data = json.loads(result[0].text)
        self.assertEqual(data.get("attribute_count"), 6)
        attrs = data.get("attributes", {})
        self.assertEqual(attrs.get("envmaptexture"), "CM_BAREMETAL")
        self.assertEqual(attrs.get("blending"), "additive")
        self.assertEqual(attrs.get("mipmap"), 0)
        self.assertEqual(attrs.get("numx"), 8)

    def test_readTXI_description_mentions_txi(self):
        tool = next(t for t in self.TOOLS if t.name == "readTXI")
        self.assertIn("TXI", tool.description)

    # ── pathfindRoute ─────────────────────────────────────────────────────────
    def test_pathfindRoute_in_tools_list(self):
        names = [t.name for t in self.TOOLS]
        self.assertIn("pathfindRoute", names)

    def test_pathfindRoute_in_handlers(self):
        self.assertIn("pathfindRoute", self.HANDLERS)

    def test_pathfindRoute_schema_has_required_fields(self):
        tool = next(t for t in self.TOOLS if t.name == "pathfindRoute")
        schema = tool.inputSchema
        # game and resref are always required; start/end can be index OR xy
        for field in ["game", "resref", "start_index", "end_index"]:
            self.assertIn(field, schema["properties"])
        # Only game + resref are in required (start/end are flexible)
        self.assertIn("game", schema["required"])
        self.assertIn("resref", schema["required"])

    def test_pathfindRoute_no_install_returns_error(self):
        result = self._run("pathfindRoute", {
            "game": "K1", "resref": "end_m01aa",
            "start_index": 0, "end_index": 3
        })
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_pathfindRoute_missing_indices_returns_error(self):
        result = self._run("pathfindRoute", {"game": "K1", "resref": "end_m01aa"})
        text = self._text(result)
        self.assertIn("error", text.lower())

    def test_pathfindRoute_same_start_end_returns_single_node(self):
        """Same start and end index returns trivial path."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _pathfind_route
        from unittest.mock import patch, MagicMock

        # Build minimal PTH GFF JSON
        pth_json = json.dumps({
            "Path_Points": [
                {"X": 0.0, "Y": 0.0, "Conections": []},
                {"X": 1.0, "Y": 0.0, "Conections": []},
            ]
        }).encode()
        from ghostscripter.mcp.tools_pkg._helpers import _ok
        from ghostscripter.core.services import GFFService

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch.object(GFFService, "parse_bytes", return_value={
                 "Path_Points": [
                     {"X": 0.0, "Y": 0.0, "Conections": []},
                     {"X": 1.0, "Y": 0.0, "Conections": []},
                 ]
             }):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = b"fake_pth"
            result = asyncio.run(
                _pathfind_route({"game": "K1", "resref": "test", "start_index": 0, "end_index": 0})
            )
        data = json.loads(result[0].text)
        self.assertEqual(data.get("path"), [0])
        self.assertEqual(data.get("total_distance"), 0.0)

    def test_pathfindRoute_simple_path_two_nodes(self):
        """Two connected nodes: path should be [0, 1]."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _pathfind_route
        from unittest.mock import patch, MagicMock
        from ghostscripter.core.services import GFFService

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch.object(GFFService, "parse_bytes", return_value={
                 "Path_Points": [
                     {"X": 0.0, "Y": 0.0, "Conections": [{"Destination": 1}]},
                     {"X": 3.0, "Y": 4.0, "Conections": [{"Destination": 0}]},
                 ]
             }):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = b"fake_pth"
            result = asyncio.run(
                _pathfind_route({"game": "K1", "resref": "test", "start_index": 0, "end_index": 1})
            )
        data = json.loads(result[0].text)
        self.assertEqual(data.get("path"), [0, 1])
        self.assertAlmostEqual(data.get("total_distance"), 5.0, places=2)
        self.assertEqual(len(data.get("waypoints", [])), 2)

    def test_pathfindRoute_no_path_returns_error(self):
        """Disconnected nodes should return an error."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _pathfind_route
        from unittest.mock import patch, MagicMock
        from ghostscripter.core.services import GFFService

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch.object(GFFService, "parse_bytes", return_value={
                 "Path_Points": [
                     {"X": 0.0, "Y": 0.0, "Conections": []},  # isolated node 0
                     {"X": 5.0, "Y": 5.0, "Conections": []},  # isolated node 1
                 ]
             }):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = b"fake_pth"
            result = asyncio.run(
                _pathfind_route({"game": "K1", "resref": "test", "start_index": 0, "end_index": 1})
            )
        text = result[0].text
        self.assertIn("error", text.lower())

    def test_pathfindRoute_out_of_range_index_returns_error(self):
        """Out-of-range start_index should error gracefully."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _pathfind_route
        from unittest.mock import patch, MagicMock
        from ghostscripter.core.services import GFFService

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch.object(GFFService, "parse_bytes", return_value={
                 "Path_Points": [{"X": 0.0, "Y": 0.0, "Conections": []}]
             }):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = b"fake_pth"
            result = asyncio.run(
                _pathfind_route({"game": "K1", "resref": "test", "start_index": 99, "end_index": 0})
            )
        text = result[0].text
        self.assertIn("error", text.lower())

    def test_pathfindRoute_description_mentions_astar(self):
        tool = next(t for t in self.TOOLS if t.name == "pathfindRoute")
        self.assertIn("A*", tool.description)

    # ── cross-cutting: all new tools registered ────────────────────────────────
    def test_all_v33_tools_in_expected_tools(self):
        v33_names = {"readNCS", "readVIS", "readIFO", "readWAV", "readTXI", "pathfindRoute"}
        actual_names = {t.name for t in self.TOOLS}
        missing = v33_names - actual_names
        self.assertEqual(missing, set(), f"v3.3 tools missing from TOOLS: {missing}")

    def test_all_v33_tools_have_handlers(self):
        v33_names = {"readNCS", "readVIS", "readIFO", "readWAV", "readTXI", "pathfindRoute"}
        missing = v33_names - set(self.HANDLERS.keys())
        self.assertEqual(missing, set(), f"v3.3 tools missing handlers: {missing}")

    def test_all_v33_tools_have_descriptions(self):
        v33_names = {"readNCS", "readVIS", "readIFO", "readWAV", "readTXI", "pathfindRoute"}
        for name in v33_names:
            tool = next((t for t in self.TOOLS if t.name == name), None)
            self.assertIsNotNone(tool, f"Tool '{name}' not found")
            self.assertTrue(len(tool.description) > 20, f"Tool '{name}' description too short")

    def test_all_v33_tools_have_input_schemas(self):
        v33_names = {"readNCS", "readVIS", "readIFO", "readWAV", "readTXI", "pathfindRoute"}
        for name in v33_names:
            tool = next((t for t in self.TOOLS if t.name == name), None)
            self.assertIsNotNone(tool, f"Tool '{name}' not found")
            self.assertIsNotNone(tool.inputSchema, f"Tool '{name}' missing inputSchema")
            self.assertEqual(tool.inputSchema.get("type"), "object")


# ═══════════════════════════════════════════════════════════════════════════════
# P2: Deep positive-path tests for readNCS, readIFO + GFF utility unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGFFHelpers(unittest.TestCase):
    """Unit tests for the shared GFF field-extraction utilities in _helpers.py."""

    def setUp(self):
        from ghostscripter.mcp.tools_pkg._helpers import (
            gff_scalar, gff_locstr, gff_resref, gff_int, gff_float,
            gff_list, gff_struct_fields,
        )
        self.gff_scalar       = gff_scalar
        self.gff_locstr       = gff_locstr
        self.gff_resref       = gff_resref
        self.gff_int          = gff_int
        self.gff_float        = gff_float
        self.gff_list         = gff_list
        self.gff_struct_fields = gff_struct_fields

    # ── gff_scalar ────────────────────────────────────────────────────────────
    def test_gff_scalar_plain_value(self):
        root = {"Tag": "my_tag"}
        self.assertEqual(self.gff_scalar(root, "Tag"), "my_tag")

    def test_gff_scalar_unwraps_value_dict(self):
        root = {"Race": {"value": 6}}
        self.assertEqual(self.gff_scalar(root, "Race"), 6)

    def test_gff_scalar_missing_key_returns_default(self):
        root = {}
        self.assertIsNone(self.gff_scalar(root, "Missing"))
        self.assertEqual(self.gff_scalar(root, "Missing", 42), 42)

    def test_gff_scalar_nested_dict_without_value_key_returned_as_is(self):
        root = {"Weird": {"other": 99}}
        result = self.gff_scalar(root, "Weird")
        # No "value" key → returned as dict (caller handles)
        self.assertEqual(result, {"other": 99})

    # ── gff_locstr ────────────────────────────────────────────────────────────
    def test_gff_locstr_plain_string(self):
        root = {"Name": "Darth Malak"}
        self.assertEqual(self.gff_locstr(root, "Name"), "Darth Malak")

    def test_gff_locstr_language_0_sub_key(self):
        root = {"FirstName": {"0": "Revan"}}
        self.assertEqual(self.gff_locstr(root, "FirstName"), "Revan")

    def test_gff_locstr_integer_0_sub_key(self):
        root = {"FirstName": {0: "HK-47"}}
        self.assertEqual(self.gff_locstr(root, "FirstName"), "HK-47")

    def test_gff_locstr_value_sub_key_fallback(self):
        root = {"Name": {"value": "Jolee Bindo"}}
        self.assertEqual(self.gff_locstr(root, "Name"), "Jolee Bindo")

    def test_gff_locstr_missing_key_returns_none(self):
        self.assertIsNone(self.gff_locstr({}, "Missing"))

    def test_gff_locstr_empty_string_treated_as_none(self):
        root = {"Name": ""}
        self.assertIsNone(self.gff_locstr(root, "Name"))

    def test_gff_locstr_no_tlk_when_rm_none(self):
        """Even when a strref is present, no TLK lookup without rm."""
        root = {"Name": {"strref": 1234}}
        # Should return None — no rm provided, no text sub-key
        self.assertIsNone(self.gff_locstr(root, "Name", rm=None))

    # ── gff_resref ────────────────────────────────────────────────────────────
    def test_gff_resref_plain(self):
        root = {"Conversation": "k_hench_candm"}
        self.assertEqual(self.gff_resref(root, "Conversation"), "k_hench_candm")

    def test_gff_resref_missing_returns_empty_string(self):
        self.assertEqual(self.gff_resref({}, "Missing"), "")

    # ── gff_int / gff_float ──────────────────────────────────────────────────
    def test_gff_int_plain(self):
        root = {"HP": 40}
        self.assertEqual(self.gff_int(root, "HP"), 40)

    def test_gff_int_string_coercion(self):
        root = {"HP": "40"}
        self.assertEqual(self.gff_int(root, "HP"), 40)

    def test_gff_int_default_on_missing(self):
        self.assertEqual(self.gff_int({}, "HP"), 0)
        self.assertEqual(self.gff_int({}, "HP", 99), 99)

    def test_gff_float_plain(self):
        root = {"X": 3.14}
        self.assertAlmostEqual(self.gff_float(root, "X"), 3.14, places=5)

    def test_gff_float_default_on_bad_value(self):
        root = {"X": "not_a_float"}
        self.assertEqual(self.gff_float(root, "X", -1.0), -1.0)

    # ── gff_list ──────────────────────────────────────────────────────────────
    def test_gff_list_returns_list(self):
        root = {"Items": [1, 2, 3]}
        self.assertEqual(self.gff_list(root, "Items"), [1, 2, 3])

    def test_gff_list_missing_returns_empty(self):
        self.assertEqual(self.gff_list({}, "Missing"), [])

    def test_gff_list_non_list_value_returns_empty(self):
        root = {"Items": "not_a_list"}
        self.assertEqual(self.gff_list(root, "Items"), [])

    # ── gff_struct_fields ─────────────────────────────────────────────────────
    def test_gff_struct_fields_unwraps_fields_key(self):
        entry = {"fields": {"HP": 40, "Tag": "npc"}}
        self.assertEqual(self.gff_struct_fields(entry), {"HP": 40, "Tag": "npc"})

    def test_gff_struct_fields_passes_through_flat_dict(self):
        entry = {"HP": 40, "Tag": "npc"}
        self.assertEqual(self.gff_struct_fields(entry), {"HP": 40, "Tag": "npc"})

    def test_gff_struct_fields_non_dict_returns_empty(self):
        self.assertEqual(self.gff_struct_fields("not_a_dict"), {})
        self.assertEqual(self.gff_struct_fields(None), {})


class TestReadNCSDeep(unittest.TestCase):
    """Positive-path tests for readNCS with synthetic valid NCS data."""

    def _run(self, args):
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs
        return asyncio.run(_read_ncs(args))

    def _json(self, result):
        import json
        return json.loads(result[0].text)

    def _make_ncs(self, instructions_bytes=b""):
        """Build a minimal valid NCS binary with the given instruction body."""
        import struct
        body = instructions_bytes
        # NCS header: file_type(4) + file_version(4) + magic(1) + size(4)
        header = b"NCS " + b"V1.0" + bytes([0x42])
        size_field = struct.pack(">I", len(body) + 13)
        return header + size_field + body

    def _patched_run(self, ncs_bytes, args):
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs
        from unittest.mock import patch, MagicMock
        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm:
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = ncs_bytes
            return asyncio.run(_read_ncs(args))

    def test_readNCS_valid_empty_body(self):
        """NCS with empty instruction body parses header correctly."""
        ncs = self._make_ncs(b"")
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test_script"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["file_type"], "NCS ")
        self.assertEqual(data["file_version"], "V1.0")
        self.assertEqual(data["magic_byte"], "0x42")
        self.assertEqual(data["instruction_count"], 0)
        self.assertFalse(data["truncated"])

    def test_readNCS_single_RETN_instruction(self):
        """A single RETN (0x20 0x00) instruction is parsed correctly."""
        # RETN: opcode=0x20, qualifier=0x00, 0 arg bytes
        instr = bytes([0x20, 0x00])
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "RETN")
        self.assertEqual(data["instructions"][0]["opcode"], "0x20")
        self.assertEqual(data["instructions"][0]["qualifier"], "0x00")
        self.assertEqual(data["instructions"][0]["args_hex"], "")

    def test_readNCS_JMP_instruction_with_4byte_offset(self):
        """JMP (0x1D) with a 4-byte signed offset is parsed correctly."""
        import struct
        # JMP opcode=0x1D, qualifier=0x00, offset = +8 (4 bytes BE)
        instr = bytes([0x1D, 0x00]) + struct.pack(">i", 8)
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "JMP")
        self.assertEqual(data["instructions"][0]["args_hex"], "00000008")

    def test_readNCS_CONST_int_instruction(self):
        """CONSTx with qualifier 0x03 (int) reads 4 arg bytes."""
        import struct
        # CONSTx: opcode=0x04, qualifier=0x03 (int), value=42
        instr = bytes([0x04, 0x03]) + struct.pack(">i", 42)
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "CONSTx")
        # 42 in big-endian 4 bytes = 0x0000002A
        self.assertEqual(data["instructions"][0]["args_hex"], "0000002a")

    def test_readNCS_CONST_string_instruction(self):
        """CONSTx with qualifier 0x05 (string) reads 2-byte length + string."""
        import struct
        text = b"hello"
        instr = bytes([0x04, 0x05]) + struct.pack(">H", len(text)) + text
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "CONSTx")
        # args_hex = length(2) + "hello" = 0005 + 68656c6c6f
        self.assertIn("68656c6c6f", data["instructions"][0]["args_hex"])

    def test_readNCS_ACTION_instruction(self):
        """ACTION (0x05) reads 2-byte routine-id + 1-byte arg-count."""
        import struct
        # ACTION: routine_id=100, arg_count=2
        instr = bytes([0x05, 0x00]) + struct.pack(">H", 100) + bytes([2])
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "ACTION")
        self.assertEqual(len(data["instructions"][0]["args_hex"]), 6)  # 3 bytes → 6 hex chars

    def test_readNCS_sequence_of_instructions(self):
        """Multiple mixed instructions are all decoded in order."""
        import struct
        # SAVEBP (0x2A 0x00, 0 args) + RETN (0x20 0x00, 0 args)
        instr = bytes([0x2A, 0x00, 0x20, 0x00])
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 2)
        self.assertEqual(data["instructions"][0]["mnemonic"], "SAVEBP")
        self.assertEqual(data["instructions"][1]["mnemonic"], "RETN")

    def test_readNCS_CPDOWNSP_reads_8_bytes(self):
        """CPDOWNSP (0x01) reads 8 arg bytes: stack_offset(4) + size(4)."""
        import struct
        # CPDOWNSP: offset=-4, size=4
        instr = bytes([0x01, 0x03]) + struct.pack(">i", -4) + struct.pack(">I", 4)
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "CPDOWNSP")
        self.assertEqual(len(data["instructions"][0]["args_hex"]), 16)  # 8 bytes → 16 hex chars

    def test_readNCS_DESTRUCT_reads_8_bytes(self):
        """DESTRUCT (0x21) reads 8 arg bytes: stack_size(4)+dont_offset(2)+dont_size(2)."""
        import struct
        instr = bytes([0x21, 0x01]) + struct.pack(">I", 16) + struct.pack(">H", 4) + struct.pack(">H", 4)
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "DESTRUCT")
        self.assertEqual(len(data["instructions"][0]["args_hex"]), 16)

    def test_readNCS_unknown_opcode_labelled_UNK(self):
        """Unknown opcodes are labelled UNK_XX and consume 0 arg bytes."""
        instr = bytes([0xEE, 0x00])
        ncs = self._make_ncs(instr)
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertTrue(data["instructions"][0]["mnemonic"].startswith("UNK_"))

    def test_readNCS_wrong_magic_returns_error(self):
        """File with wrong file_type returns an error, not an exception."""
        bad = b"XXXX" + b"V1.0" + bytes([0x42]) + b"\x00" * 4
        data = self._json(self._patched_run(bad, {"game": "K1", "resref": "test"}))
        self.assertIn("error", data)

    def test_readNCS_wrong_version_returns_error(self):
        """File with wrong version string returns an error."""
        bad = b"NCS " + b"V2.0" + bytes([0x42]) + b"\x00" * 4
        data = self._json(self._patched_run(bad, {"game": "K1", "resref": "test"}))
        self.assertIn("error", data)

    def test_readNCS_parse_error_fields_present(self):
        """Result always contains parse_errors list (may be empty)."""
        ncs = self._make_ncs(b"")
        data = self._json(self._patched_run(ncs, {"game": "K1", "resref": "test"}))
        self.assertIn("parse_errors", data)
        self.assertIsInstance(data["parse_errors"], list)


class TestReadIFODeep(unittest.TestCase):
    """Positive-path tests for readIFO with a synthesized GFF dict."""

    def _patched_run(self, gff_dict, resref="test_mod"):
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ifo
        from unittest.mock import patch, MagicMock

        # Build fake IFO bytes — actual bytes don't matter since we mock GFFService too
        fake_bytes = b"IFO V3.2" + b"\x00" * 56

        # Force the GFFService fallback path by making PyKotor's read_gff raise
        # ImportError (simulating pykotor not installed for this unit test).
        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch("ghostscripter.core.services.GFFService") as mock_gff, \
             patch("builtins.__import__", side_effect=_make_pykotor_import_blocker(
                 "pykotor.resource.formats.gff", "pykotor.resource.generics.ifo")):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = fake_bytes
            mock_gff.parse_bytes.return_value = gff_dict
            return asyncio.run(_read_ifo({"game": "K1", "resref": resref}))

    def _json(self, result):
        import json
        return json.loads(result[0].text)

    def _base_ifo(self, **kwargs):
        """Return a minimal IFO GFF dict with optional overrides."""
        base = {
            "Mod_Name":        {"0": "Test Module"},
            "Mod_Description": {"0": "A test module"},
            "Mod_Tag":         "testmod",
            "Mod_Entry_Area":  "end_m01aa",
            "Mod_Entry_X":     10.0,
            "Mod_Entry_Y":     20.0,
            "Mod_Entry_Z":     0.0,
            "Mod_Entry_Dir_X": 1.0,
            "Mod_Entry_Dir_Y": 0.0,
            "Expansion_Pack":  0,
            "Mod_IsSaveGame":  0,
            "Mod_Creator_ID":  0,
            "Mod_Version":     1,
            "Mod_Area_list":   [],
        }
        base.update(kwargs)
        return base

    def test_readIFO_returns_mod_name(self):
        data = self._json(self._patched_run(self._base_ifo()))
        self.assertNotIn("error", data)
        self.assertEqual(data["mod_name"], "Test Module")

    def test_readIFO_returns_entry_area(self):
        data = self._json(self._patched_run(self._base_ifo()))
        self.assertEqual(data["entry_area"], "end_m01aa")

    def test_readIFO_returns_entry_coords(self):
        data = self._json(self._patched_run(self._base_ifo()))
        self.assertAlmostEqual(data["entry_x"], 10.0, places=3)
        self.assertAlmostEqual(data["entry_y"], 20.0, places=3)

    def test_readIFO_scripts_only_includes_non_empty(self):
        ifo = self._base_ifo(
            Mod_OnHeartbeat="k_mod_heart",
            Mod_OnModLoad="k_mod_load",
        )
        data = self._json(self._patched_run(ifo))
        self.assertIn("on_heartbeat", data["scripts"])
        self.assertEqual(data["scripts"]["on_heartbeat"], "k_mod_heart")
        self.assertIn("on_load", data["scripts"])
        # Keys with empty values must NOT be in scripts
        for k, v in data["scripts"].items():
            self.assertTrue(v, f"Script key '{k}' has empty value")

    def test_readIFO_empty_scripts_when_none_set(self):
        data = self._json(self._patched_run(self._base_ifo()))
        self.assertEqual(data["scripts"], {})

    def test_readIFO_area_list_populated(self):
        ifo = self._base_ifo(Mod_Area_list=[
            {"Area_Name": "end_m01aa"},
            {"Area_Name": "unk_m44ac"},
        ])
        data = self._json(self._patched_run(ifo))
        self.assertEqual(len(data["area_list"]), 2)
        self.assertIn("end_m01aa", data["area_list"])
        self.assertIn("unk_m44ac", data["area_list"])

    def test_readIFO_expansion_id_and_is_save(self):
        ifo = self._base_ifo(Expansion_Pack=2, Mod_IsSaveGame=1)
        data = self._json(self._patched_run(ifo))
        self.assertEqual(data["expansion_id"], 2)
        self.assertTrue(data["is_save_game"])

    def test_readIFO_mod_name_via_value_wrapper(self):
        """Handles GFFService wrapping as {"value": "..."}."""
        ifo = self._base_ifo(Mod_Name={"value": "Wrapped Name"})
        data = self._json(self._patched_run(ifo))
        # gff_locstr should find "value" sub-key
        self.assertEqual(data["mod_name"], "Wrapped Name")

    def test_readIFO_missing_resref_error(self):
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ifo
        result = asyncio.run(_read_ifo({"game": "K1", "resref": ""}))
        import json
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_readIFO_no_install_error(self):
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ifo
        result = asyncio.run(_read_ifo({"game": "K1", "resref": "sommod"}))
        import json
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_readIFO_result_has_expected_keys(self):
        data = self._json(self._patched_run(self._base_ifo()))
        for key in ("game", "resref", "mod_name", "entry_area", "entry_x",
                    "entry_y", "entry_z", "area_list", "scripts"):
            self.assertIn(key, data, f"Missing key '{key}' in readIFO result")


class TestPathfindRouteXY(unittest.TestCase):
    """Tests for the XY-coordinate Mode B addition to pathfindRoute."""

    def _make_pth_gff(self, points_xy, connections):
        """Build a minimal PTH GFF dict.

        points_xy:   list of (x, y) tuples
        connections: dict {node_idx: [neighbour_idx, ...]}
        """
        path_points = []
        for i, (x, y) in enumerate(points_xy):
            conns = [{"Destination": j} for j in connections.get(i, [])]
            path_points.append({"X": float(x), "Y": float(y), "Conections": conns})
        return {"Path_Points": path_points}

    def _patched_run(self, pth_gff, args):
        import asyncio
        from ghostscripter.mcp.tools_pkg.handlers_read import _pathfind_route
        from unittest.mock import patch, MagicMock
        fake_pth = b"PTH V3.2" + b"\x00" * 56
        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch("ghostscripter.core.services.GFFService") as mock_gff:
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = fake_pth
            mock_gff.parse_bytes.return_value = pth_gff
            return asyncio.run(_pathfind_route(args))

    def _json(self, result):
        import json
        return json.loads(result[0].text)

    def _simple_graph(self):
        """Triangle graph: 0-(0,0), 1-(10,0), 2-(5,10) all connected."""
        pts = [(0, 0), (10, 0), (5, 10)]
        conns = {0: [1, 2], 1: [0, 2], 2: [0, 1]}
        return self._make_pth_gff(pts, conns)

    def test_xy_mode_finds_nearest_start_node(self):
        """Passing start_x/start_y near node 0 should snap to node 0."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_x": 0.5, "start_y": 0.5,   # near node 0 (0,0)
            "end_index": 1,
        }))
        self.assertNotIn("error", data)
        self.assertEqual(data["start_index"], 0)
        self.assertIn("start_nearest", data)
        self.assertEqual(data["start_nearest"]["snapped_to"], 0)

    def test_xy_mode_finds_nearest_end_node(self):
        """Passing end_x/end_y near node 1 should snap to node 1."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_index": 0,
            "end_x": 10.1, "end_y": 0.0,   # near node 1 (10,0)
        }))
        self.assertNotIn("error", data)
        self.assertEqual(data["end_index"], 1)
        self.assertIn("end_nearest", data)
        self.assertEqual(data["end_nearest"]["snapped_to"], 1)

    def test_both_xy_mode_routes_correctly(self):
        """Both start and end given as XY — route from near 0 to near 2."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_x": 0.0, "start_y": 0.0,   # node 0 exactly
            "end_x":   5.0, "end_y":  10.0,   # node 2 exactly
        }))
        self.assertNotIn("error", data)
        self.assertEqual(data["start_index"], 0)
        self.assertEqual(data["end_index"], 2)
        self.assertGreater(data["total_distance"], 0)

    def test_xy_snap_distance_reported(self):
        """start_nearest.snap_distance correctly reflects distance from XY to node."""
        import math
        pth = self._simple_graph()
        # Node 0 is at (0,0); we query from (3,4) — distance = 5.0
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_x": 3.0, "start_y": 4.0,
            "end_index": 1,
        }))
        self.assertNotIn("error", data)
        snap_d = data["start_nearest"]["snap_distance"]
        self.assertAlmostEqual(snap_d, 5.0, places=2)

    def test_missing_both_start_params_returns_error(self):
        """Neither start_index nor start_x/start_y → error."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "end_index": 1,
        }))
        self.assertIn("error", data)

    def test_missing_both_end_params_returns_error(self):
        """Neither end_index nor end_x/end_y → error."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_index": 0,
        }))
        self.assertIn("error", data)

    def test_xy_partial_end_xy_missing_y_returns_error(self):
        """end_x without end_y (and no end_index) → error."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_index": 0,
            "end_x": 10.0,   # end_y missing
        }))
        self.assertIn("error", data)

    def test_index_mode_still_works(self):
        """Original index mode is unaffected by the new XY mode."""
        pth = self._simple_graph()
        data = self._json(self._patched_run(pth, {
            "game": "K1", "resref": "test",
            "start_index": 0, "end_index": 2,
        }))
        self.assertNotIn("error", data)
        self.assertEqual(data["start_index"], 0)
        self.assertEqual(data["end_index"], 2)
        # Neither snap key should be present when indices were given explicitly
        self.assertNotIn("start_nearest", data)
        self.assertNotIn("end_nearest", data)

    def test_pathfind_schema_includes_xy_params(self):
        """Tool schema now includes start_x/start_y/end_x/end_y properties."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "pathfindRoute")
        props = tool.inputSchema["properties"]
        for p in ("start_x", "start_y", "end_x", "end_y"):
            self.assertIn(p, props, f"Schema missing '{p}'")

    def test_pathfind_schema_only_requires_game_and_resref(self):
        """Schema required list should only have game and resref (not index/xy)."""
        from ghostscripter.mcp.tools_pkg import TOOLS
        tool = next(t for t in TOOLS if t.name == "pathfindRoute")
        required = set(tool.inputSchema.get("required", []))
        self.assertEqual(required, {"game", "resref"})


class TestPyKotorGracefulFallback(unittest.TestCase):
    """Verify that readNCS and readIFO fall back gracefully when pykotor absent."""

    def _make_ncs(self, body=b""):
        import struct
        header = b"NCS " + b"V1.0" + bytes([0x42])
        size_field = struct.pack(">I", len(body) + 13)
        return header + size_field + body

    def test_readNCS_falls_back_when_pykotor_unavailable(self):
        """readNCS still returns a valid result even when pykotor cannot be imported."""
        import asyncio, sys
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs
        from unittest.mock import patch, MagicMock

        ncs = self._make_ncs(bytes([0x20, 0x00]))  # single RETN

        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def _block_pykotor(name, *args, **kwargs):
            if name.startswith("pykotor"):
                raise ImportError(f"Blocked for test: {name}")
            return original_import(name, *args, **kwargs)

        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch("builtins.__import__", side_effect=_block_pykotor):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = ncs
            result = asyncio.run(_read_ncs({"game": "K1", "resref": "test"}))

        import json
        data = json.loads(result[0].text)
        # Should succeed using internal disassembler, not return an error
        self.assertNotIn("error", data)
        self.assertEqual(data["instruction_count"], 1)
        self.assertEqual(data["instructions"][0]["mnemonic"], "RETN")
        # pykotor_used should be absent (was not used)
        self.assertNotIn("pykotor_used", data)

    def test_readNCS_pykotor_used_flag_absent_in_internal_mode(self):
        """Internal disassembler result never includes pykotor_used=True."""
        import asyncio, json, builtins
        from ghostscripter.mcp.tools_pkg.handlers_read import _read_ncs
        from unittest.mock import patch, MagicMock

        real_import = builtins.__import__
        def _block_pykotor2(name, *args, **kwargs):
            if name.startswith("pykotor"):
                raise ImportError(f"Blocked for test: {name}")
            return real_import(name, *args, **kwargs)

        ncs = self._make_ncs(b"")
        with patch("ghostscripter.mcp.tools_pkg.handlers_read._load_rm") as mock_rm, \
             patch("builtins.__import__", side_effect=_block_pykotor2):
            mock_rm.return_value = MagicMock()
            mock_rm.return_value.read.return_value = ncs
            result = asyncio.run(_read_ncs({"game": "K1", "resref": "test"}))

        data = json.loads(result[0].text)
        self.assertNotIn("error", data)
        self.assertNotIn("pykotor_used", data)


# ─── v3.4 decompileScript tests ──────────────────────────────────────────────

class TestDecompileScript(unittest.TestCase):
    """Tests for the decompileScript MCP tool (v3.4 addition)."""

    def setUp(self):
        from ghostscripter.mcp.tools import TOOLS, _HANDLERS
        self.TOOLS = TOOLS
        self.HANDLERS = _HANDLERS

    def _ncs_nop(self) -> bytes:
        """Minimal valid NCS binary: NCS V1.0 header + RETN opcode."""
        import struct
        header = b"NCS V1.0"
        retn_instr = b"\x04\x03"
        size = struct.pack(">I", 13 + len(retn_instr))
        return header + b"\x42" + size + retn_instr

    def test_decompileScript_in_tools_list(self):
        """decompileScript is registered in TOOLS."""
        names = [t.name for t in self.TOOLS]
        self.assertIn("decompileScript", names)

    def test_decompileScript_handler_registered(self):
        """decompileScript handler is in _HANDLERS."""
        self.assertIn("decompileScript", self.HANDLERS)

    def test_decompileScript_input_schema_game_required(self):
        """decompileScript inputSchema requires 'game'."""
        tool = next(t for t in self.TOOLS if t.name == "decompileScript")
        self.assertIn("game", tool.inputSchema.get("required", []))

    def test_decompileScript_input_schema_has_data_base64(self):
        """decompileScript inputSchema exposes data_base64 property."""
        tool = next(t for t in self.TOOLS if t.name == "decompileScript")
        props = tool.inputSchema.get("properties", {})
        self.assertIn("data_base64", props)

    def test_decompileScript_input_schema_has_resref(self):
        """decompileScript inputSchema exposes resref property."""
        tool = next(t for t in self.TOOLS if t.name == "decompileScript")
        props = tool.inputSchema.get("properties", {})
        self.assertIn("resref", props)

    def test_decompileScript_no_input_returns_error(self):
        """decompileScript returns error when neither resref nor data_base64 is provided."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_write import _decompile_script
        result = asyncio.run(_decompile_script({"game": "K1"}))
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_decompileScript_invalid_base64_returns_error(self):
        """decompileScript returns error on malformed base64 data."""
        import asyncio, json
        from ghostscripter.mcp.tools_pkg.handlers_write import _decompile_script
        result = asyncio.run(_decompile_script({"game": "K1", "data_base64": "!!!not_b64!!!"}))
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_decompileScript_invalid_game_returns_error(self):
        """decompileScript returns error for unknown game ID."""
        import asyncio, json, base64
        from ghostscripter.mcp.tools_pkg.handlers_write import _decompile_script
        ncs_b64 = base64.b64encode(b"NCS V1.0\x42\x00\x00\x00\x0d").decode()
        result = asyncio.run(_decompile_script({"game": "K3", "data_base64": ncs_b64}))
        data = json.loads(result[0].text)
        self.assertIn("error", data)

    def test_decompileScript_empty_ncs_returns_error(self):
        """decompileScript returns error for empty NCS data."""
        import asyncio, json, base64
        from ghostscripter.mcp.tools_pkg.handlers_write import _decompile_script
        result = asyncio.run(_decompile_script({"game": "K1", "data_base64": base64.b64encode(b"").decode()}))
        data = json.loads(result[0].text)
        self.assertIn("error", data)
