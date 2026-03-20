#!/usr/bin/env python3
"""
test_syntax_highlighter.py — Tests for the NSSSyntaxHighlighter and
NWScript parser (no Qt display, only logic).
"""
import sys
import tempfile
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.nwscript.parser import (
    NWScriptDB, NWFunction, NWParam, NWConstant, parse_nwscript,
)


SIMPLE_NWSCRIPT_NSS = """\
void ActionStartConversation( object oObjectToConverse, string sDialogResRef = "", int bPrivateConversation = FALSE );
int GetGlobalNumber( string sVarname );
void SetGlobalNumber( string sVarname, int nValue );
object GetObjectByTag( string sTag, int nNthObject = 0 );
int GetIsObjectValid( object oObject );
int OBJECT_TYPE_CREATURE = 1;
int ALIGNMENT_LIGHT_SIDE = 70;
"""


def _make_temp_nss(content: str) -> Path:
    """Write content to a temp .nss file and return its Path."""
    fd, path_str = tempfile.mkstemp(suffix=".nss")
    os.close(fd)
    p = Path(path_str)
    p.write_text(content, encoding="utf-8")
    return p


class TestNWScriptParser(unittest.TestCase):
    """Tests for the NWScript .nss parser (parse_nwscript takes a Path)."""

    def setUp(self):
        self._temp = _make_temp_nss(SIMPLE_NWSCRIPT_NSS)

    def tearDown(self):
        try:
            self._temp.unlink()
        except Exception:
            pass

    def test_parse_sample_functions(self):
        functions, constants = parse_nwscript(self._temp)
        names = [f.name for f in functions]
        self.assertIn("ActionStartConversation", names)
        self.assertIn("GetGlobalNumber", names)
        self.assertIn("SetGlobalNumber", names)

    def test_function_has_params(self):
        functions, _ = parse_nwscript(self._temp)
        func_map = {f.name: f for f in functions}
        ac = func_map.get("ActionStartConversation")
        self.assertIsNotNone(ac, "ActionStartConversation must be parsed")
        self.assertGreater(len(ac.params), 0)

    def test_function_return_type(self):
        functions, _ = parse_nwscript(self._temp)
        func_map = {f.name: f for f in functions}
        gg = func_map.get("GetGlobalNumber")
        self.assertIsNotNone(gg)
        self.assertEqual(gg.return_type, "int")

    def test_void_return_type(self):
        functions, _ = parse_nwscript(self._temp)
        func_map = {f.name: f for f in functions}
        sg = func_map.get("SetGlobalNumber")
        self.assertIsNotNone(sg)
        self.assertEqual(sg.return_type, "void")

    def test_optional_params_have_defaults(self):
        functions, _ = parse_nwscript(self._temp)
        func_map = {f.name: f for f in functions}
        got = func_map.get("GetObjectByTag")
        self.assertIsNotNone(got)
        optional = [p for p in got.params if p.default is not None]
        self.assertGreater(len(optional), 0)

    def test_empty_source_no_crash(self):
        """Parsing an empty file must not raise."""
        empty = _make_temp_nss("")
        try:
            functions, constants = parse_nwscript(empty)
            self.assertIsInstance(functions, list)
            self.assertIsInstance(constants, list)
        finally:
            empty.unlink()

    def test_comments_only_no_crash(self):
        """Source with only comments must parse without error."""
        src_path = _make_temp_nss("// This is a comment\n// Another comment\n")
        try:
            functions, _ = parse_nwscript(src_path)
            self.assertEqual(len(functions), 0)
        finally:
            src_path.unlink()

    def test_constants_parsed(self):
        functions, constants = parse_nwscript(self._temp)
        names = [c.name for c in constants]
        self.assertIn("OBJECT_TYPE_CREATURE", names)

    def test_constant_value(self):
        _, constants = parse_nwscript(self._temp)
        cmap = {c.name: c for c in constants}
        self.assertEqual(cmap["OBJECT_TYPE_CREATURE"].value, "1")

    def test_nonexistent_file_no_crash(self):
        """parse_nwscript on missing file should return empty lists."""
        functions, constants = parse_nwscript(Path("/nonexistent/path.nss"))
        self.assertEqual(functions, [])
        self.assertEqual(constants, [])


class TestNWFunction(unittest.TestCase):
    """Tests for the NWFunction dataclass."""

    def _make_func(self):
        return NWFunction(
            return_type="int",
            name="GetFoo",
            params=[
                NWParam(type="object", name="oTarget"),
                NWParam(type="int", name="nMode", default="0"),
            ],
            comment="Get foo value.",
            line_number=1,
        )

    def test_signature_format(self):
        f = self._make_func()
        sig = f.signature
        self.assertIn("GetFoo", sig)
        self.assertIn("object oTarget", sig)
        self.assertIn("int nMode", sig)

    def test_signature_includes_return_type(self):
        f = self._make_func()
        sig = f.signature
        self.assertIn("int", sig)

    def test_call_snippet(self):
        f = self._make_func()
        snippet = f.call_snippet
        self.assertIn("GetFoo(", snippet)

    def test_call_snippet_has_params(self):
        f = self._make_func()
        snippet = f.call_snippet
        self.assertIn("oTarget", snippet)
        self.assertIn("nMode", snippet)

    def test_category_global_variable(self):
        f = NWFunction("int", "GetGlobalNumber", [], "", 1)
        self.assertEqual(f.category, "Global Variables")

    def test_category_action(self):
        f = NWFunction("void", "ActionStartConversation", [], "", 1)
        self.assertEqual(f.category, "Actions")

    def test_category_effect(self):
        f = NWFunction("effect", "EffectDamage", [], "", 1)
        self.assertEqual(f.category, "Effects")

    def test_category_misc(self):
        f = NWFunction("void", "AdjustAlignment", [], "", 1)
        self.assertIsInstance(f.category, str)

    def test_optional_default_in_signature(self):
        f = self._make_func()
        sig = f.signature
        # The default "= 0" should appear for the optional param
        self.assertIn("= 0", sig)


class TestNWScriptDB(unittest.TestCase):
    """Tests for the NWScriptDB class."""

    def _make_db(self) -> NWScriptDB:
        """Build a DB by loading the temp NWScript source."""
        temp = _make_temp_nss(SIMPLE_NWSCRIPT_NSS)
        db = NWScriptDB("K1")
        db._load(temp)
        temp.unlink()
        return db

    def test_db_contains_known_function(self):
        db = self._make_db()
        names = {f.name for f in db.functions}
        self.assertIn("GetGlobalNumber", names)

    def test_search_functions_prefix(self):
        db = self._make_db()
        results = db.search_functions("Get")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("get", r.name.lower())

    def test_search_functions_empty_prefix(self):
        db = self._make_db()
        results = db.search_functions("")
        self.assertEqual(len(results), len(db.functions))

    def test_search_functions_no_match(self):
        db = self._make_db()
        results = db.search_functions("ZZZNonExistent")
        self.assertEqual(len(results), 0)

    def test_function_count(self):
        db = self._make_db()
        self.assertEqual(len(db.functions), 5)

    def test_game_attribute(self):
        db = NWScriptDB("K2")
        self.assertEqual(db.game, "K2")

    def test_get_function_by_name(self):
        db = self._make_db()
        f = db.get_function("GetGlobalNumber")
        self.assertIsNotNone(f)
        self.assertEqual(f.name, "GetGlobalNumber")

    def test_get_missing_function_returns_none(self):
        db = self._make_db()
        self.assertIsNone(db.get_function("NonExistentFunction"))

    def test_autocomplete_prefix(self):
        db = self._make_db()
        results = db.autocomplete("Get")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r.lower().startswith("get"))

    def test_constants_loaded(self):
        db = self._make_db()
        self.assertGreater(len(db.constants), 0)

    def test_constant_lookup(self):
        db = self._make_db()
        c = db.get_constant("OBJECT_TYPE_CREATURE")
        self.assertIsNotNone(c)
        self.assertEqual(c.value, "1")

    def test_category_groupings_built(self):
        db = self._make_db()
        cats = db.function_categories
        self.assertIsInstance(cats, dict)
        self.assertGreater(len(cats), 0)

    def test_invalidate_cache(self):
        """invalidate_cache should not raise."""
        from ghostscripter.core.nwscript.parser import invalidate_cache
        invalidate_cache()  # should not raise


if __name__ == "__main__":
    unittest.main()
