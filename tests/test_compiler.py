#!/usr/bin/env python3
"""
test_compiler.py — Tests for the NWScript compiler integration.

Tests compilation logic without requiring nwnnsscomp to be present:
  - Script model creation and saving
  - Syntax check fallback behaviour
  - CompilationError model
  - Script template generation
"""
import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.models.script import (
    ScriptFile, CompilationError,
    make_void_main_template, make_starting_conditional_template,
    make_quest_start_template,
)


VALID_NSS = """\
void main()
{
    int nState = GetGlobalNumber("K_SWG_MYQUEST");
    if (nState == 0) {
        SetGlobalNumber("K_SWG_MYQUEST", 1);
    }
}
"""

UNBALANCED_BRACE_NSS = """\
void main()
{
    int x = 1;
    if (x) {
        // missing closing brace
}
"""

UNBALANCED_PAREN_NSS = """\
void main()
{
    int x = GetGlobalNumber("key";  // missing closing paren
}
"""


class TestScriptFileModel(unittest.TestCase):
    """Tests for the ScriptFile data model."""

    def test_create_minimal_script(self):
        s = ScriptFile(name="test_script", source_code="void main() {}")
        self.assertEqual(s.name, "test_script")
        self.assertEqual(s.source_code, "void main() {}")

    def test_default_source_code_empty(self):
        s = ScriptFile(name="empty")
        self.assertEqual(s.source_code, "")

    def test_has_errors_false_initially(self):
        s = ScriptFile(name="clean")
        self.assertFalse(s.has_errors())

    def test_has_errors_true_when_set(self):
        s = ScriptFile(name="broken")
        s.errors = [CompilationError(line=1, column=0, message="syntax error", severity="error")]
        self.assertTrue(s.has_errors())

    def test_errors_list_initially_empty(self):
        s = ScriptFile(name="fresh")
        self.assertEqual(s.errors, [])

    def test_warnings_list_initially_empty(self):
        s = ScriptFile(name="fresh2")
        self.assertEqual(s.warnings, [])

    def test_save_to_disk(self):
        """ScriptFile can be written to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.nss"
            s = ScriptFile(name="test", source_code=VALID_NSS)
            s.file_path = path
            result = s.save_to_disk()
            self.assertTrue(result)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), VALID_NSS)

    def test_load_from_disk(self):
        """ScriptFile can load source from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "load_test.nss"
            path.write_text(VALID_NSS, encoding="utf-8")
            s = ScriptFile(name="load_test")
            s.file_path = path
            result = s.load_from_disk()
            self.assertTrue(result)
            self.assertEqual(s.source_code, VALID_NSS)

    def test_save_returns_false_no_path(self):
        s = ScriptFile(name="no_path")
        self.assertFalse(s.save_to_disk())

    def test_load_returns_false_missing_file(self):
        s = ScriptFile(name="missing")
        s.file_path = Path("/nonexistent/path/script.nss")
        self.assertFalse(s.load_from_disk())

    def test_to_dict(self):
        s = ScriptFile(name="dict_test", source_code="void main(){}")
        d = s.to_dict()
        self.assertIn("name", d)
        self.assertEqual(d["name"], "dict_test")

    def test_get_compiled_path(self):
        s = ScriptFile(name="myscript")
        s.file_path = Path("/tmp/myscript.nss")
        expected = Path("/tmp/myscript.ncs")
        self.assertEqual(s.get_compiled_path(), expected)

    def test_get_compiled_path_none_when_no_file(self):
        s = ScriptFile(name="nopath")
        self.assertIsNone(s.get_compiled_path())

    def test_get_referenced_variables(self):
        s = ScriptFile(name="vars", source_code=VALID_NSS)
        refs = s.get_referenced_variables()
        self.assertIn("K_SWG_MYQUEST", refs)

    def test_str_representation(self):
        s = ScriptFile(name="str_test")
        self.assertIn("str_test", str(s))


class TestScriptTemplates(unittest.TestCase):
    """Tests for the NSS template generators."""

    def test_void_main_template(self):
        src = make_void_main_template()
        self.assertIn("void main()", src)
        self.assertIn("{", src)
        self.assertIn("}", src)

    def test_void_main_brace_balance(self):
        src = make_void_main_template()
        self.assertEqual(src.count("{"), src.count("}"))

    def test_starting_conditional_template(self):
        src = make_starting_conditional_template()
        self.assertIn("StartingConditional", src)

    def test_quest_start_template(self):
        src = make_quest_start_template("K_SWG_TEST")
        self.assertIn("void main()", src)
        self.assertIn("K_SWG_TEST", src)

    def test_templates_are_strings(self):
        self.assertIsInstance(make_void_main_template(), str)
        self.assertIsInstance(make_starting_conditional_template(), str)
        self.assertIsInstance(make_quest_start_template("TEST"), str)

    def test_templates_non_empty(self):
        for src in [
            make_void_main_template(),
            make_starting_conditional_template(),
            make_quest_start_template("TEST"),
        ]:
            self.assertGreater(len(src), 10)

    def test_void_main_paren_balance(self):
        src = make_void_main_template()
        self.assertEqual(src.count("("), src.count(")"))


class TestCompilationError(unittest.TestCase):
    """Tests for the CompilationError model."""

    def test_create_error(self):
        e = CompilationError(line=5, column=0, message="Undeclared identifier", severity="error")
        self.assertEqual(e.line, 5)
        self.assertEqual(e.message, "Undeclared identifier")
        self.assertEqual(e.severity, "error")

    def test_create_warning(self):
        e = CompilationError(line=3, column=0, message="Unused variable", severity="warning")
        self.assertEqual(e.severity, "warning")

    def test_str_representation(self):
        e = CompilationError(line=10, column=0, message="Error message", severity="error")
        s = str(e)
        self.assertIn("10", s)
        self.assertIn("Error message", s)

    def test_default_severity_is_error(self):
        e = CompilationError(line=1, column=0, message="test")
        self.assertEqual(e.severity, "error")


class TestSyntaxCheck(unittest.TestCase):
    """
    Tests for brace/paren balance checks — mirrors the fallback logic
    in ScriptEditorWidget._syntax_check_only().
    """

    def _check(self, code: str) -> list:
        """Run the same balance checks as the editor's syntax fallback."""
        issues = []
        ob = code.count("{"); cb = code.count("}")
        op = code.count("("); cp = code.count(")")
        if ob != cb:
            issues.append(f"Brace mismatch: {ob}{{ vs {cb}}}")
        if op != cp:
            issues.append(f"Paren mismatch: {op}( vs {cp})")
        return issues

    def test_valid_code_no_issues(self):
        issues = self._check(VALID_NSS)
        self.assertEqual(issues, [])

    def test_unbalanced_brace_detected(self):
        issues = self._check(UNBALANCED_BRACE_NSS)
        self.assertTrue(any("Brace" in i for i in issues))

    def test_unbalanced_paren_detected(self):
        issues = self._check(UNBALANCED_PAREN_NSS)
        self.assertTrue(any("Paren" in i for i in issues))

    def test_empty_code_no_issues(self):
        issues = self._check("")
        self.assertEqual(issues, [])

    def test_single_function_no_issues(self):
        src = "void main() { int x = 1; }"
        issues = self._check(src)
        self.assertEqual(issues, [])

    def test_multi_function_no_issues(self):
        src = (
            "int helper(int n) { return n + 1; }\n"
            "void main() { int x = helper(1); }\n"
        )
        issues = self._check(src)
        self.assertEqual(issues, [])


class TestScriptGetReferencedVars(unittest.TestCase):
    """Tests for global variable extraction."""

    def test_extract_set_global_number(self):
        src = 'SetGlobalNumber("K_MYVAR", 1);'
        s = ScriptFile(name="test", source_code=src)
        refs = s.get_referenced_variables()
        self.assertIn("K_MYVAR", refs)

    def test_extract_get_global_boolean(self):
        src = 'if (GetGlobalBoolean("K_QUEST_ACTIVE")) {}'
        s = ScriptFile(name="test", source_code=src)
        refs = s.get_referenced_variables()
        self.assertIn("K_QUEST_ACTIVE", refs)

    def test_extract_multiple_vars(self):
        src = (
            'SetGlobalNumber("K_VAR1", 1);\n'
            'GetGlobalString("K_VAR2");\n'
        )
        s = ScriptFile(name="test", source_code=src)
        refs = s.get_referenced_variables()
        self.assertIn("K_VAR1", refs)
        self.assertIn("K_VAR2", refs)

    def test_no_vars_in_empty_script(self):
        s = ScriptFile(name="empty", source_code="void main() {}")
        self.assertEqual(s.get_referenced_variables(), [])


if __name__ == "__main__":
    unittest.main()
