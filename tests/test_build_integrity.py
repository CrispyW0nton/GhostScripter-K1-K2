from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_builder_bundles_runtime_knowledge_and_compiler_definitions():
    source = (ROOT / "build_tools" / "build.py").read_text(encoding="utf-8")
    assert "resources' / 'scripts'" in source
    assert "--collect-submodules=pykotor" not in source
    assert "pykotor.resource.formats.ncs.compilers" in source
    assert "mcp.server.streamable_http_manager" in source
    assert "ghostscripter.core.nwscript.compiler_defs" in source
    assert "ghostscripter.core.gff_codec" in source
    assert "ghostscripter.core.lip" in source
    assert "ghostscripter.core.ssf" in source
    assert "ghostscripter.core.services" in source
    assert "ghostscripter.ui.widgets.lip_editor_widget" in source
    assert "ghostscripter.mcp.tools_pkg.handlers_write" in source
    assert "resources' / 'tools'" not in source


def test_ci_onefile_build_does_not_delete_folder_build():
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )
    assert "--onefile --no-zip --no-clean" in workflow
