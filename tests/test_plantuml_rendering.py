"""Regression coverage for local PlantUML rendering in chat and workspace previews."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.plantuml import render_svg_data_uri

ROOT = Path(__file__).parent.parent
UI_JS = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
WORKSPACE_JS = (ROOT / "static" / "workspace.js").read_text(encoding="utf-8")
ROUTES_PY = (ROOT / "api" / "routes.py").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_plantuml_fences_become_hydratable_placeholders():
    assert "/^(plantuml|puml|uml)$/" in UI_JS
    assert 'class="plantuml-block"' in UI_JS
    assert "mermaid-block|plantuml-block|katex-block" in UI_JS
    assert "['pre-header','mermaid-block','plantuml-block','katex-block']" in UI_JS


def test_plantuml_hydrates_in_chat_and_workspace_previews():
    assert "function renderPlantUmlBlocks(container)" in UI_JS
    assert "api('/api/plantuml/render'" in UI_JS
    assert "renderPlantUmlBlocks(container);" in UI_JS
    assert "renderPlantUmlBlocks(target)" in WORKSPACE_JS


def test_plantuml_uses_a_local_post_endpoint_and_safe_image_surface():
    assert 'parsed.path == "/api/plantuml/render"' in ROUTES_PY
    assert "render_svg_data_uri(body.get(\"source\"))" in ROUTES_PY
    assert 'class="plantuml-rendered"' in UI_JS
    assert ".plantuml-rendered{display:inline-block;max-width:100%;height:auto;}" in STYLE_CSS


def test_local_plantuml_renderer_returns_svg_data_uri():
    completed = SimpleNamespace(returncode=0, stdout=b'<svg xmlns="http://www.w3.org/2000/svg"/>', stderr=b"")
    with (
        patch("api.plantuml._plantuml_jar", return_value=Path("plantuml.jar")),
        patch("api.plantuml.shutil.which", return_value="java"),
        patch("api.plantuml.subprocess.run", return_value=completed),
    ):
        rendered = render_svg_data_uri("@startuml\nAlice -> Bob: Hello\n@enduml\n")
    assert rendered.startswith("data:image/svg+xml;base64,")
