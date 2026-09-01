"""Local-only PlantUML rendering for Hermes WebUI."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

from api.config import STATE_DIR
from api.shares import _sanitize_svg_bytes
from api.subprocess_utils import windows_hide_flags

MAX_SOURCE_BYTES = 256 * 1024
MAX_SVG_BYTES = 4 * 1024 * 1024
RENDER_TIMEOUT_SECONDS = 20


class PlantUmlRenderError(ValueError):
    """A client-safe PlantUML rendering failure."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


def _plantuml_jar() -> Path:
    configured = os.environ.get("HERMES_WEBUI_PLANTUML_JAR", "").strip()
    candidate = Path(configured).expanduser() if configured else STATE_DIR / "plantuml" / "plantuml.jar"
    if not candidate.is_file():
        raise PlantUmlRenderError(
            "PlantUML is not installed locally. Install plantuml.jar or set HERMES_WEBUI_PLANTUML_JAR.",
            status=503,
        )
    return candidate


def render_svg_data_uri(source: object) -> str:
    """Render bounded PlantUML source locally and return a safe SVG data URI."""
    if not isinstance(source, str) or not source.strip():
        raise PlantUmlRenderError("PlantUML source is required.", status=400)
    raw = source.encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES:
        raise PlantUmlRenderError("PlantUML source is too large.", status=413)
    if "\x00" in source:
        raise PlantUmlRenderError("PlantUML source contains an invalid character.", status=400)

    java = shutil.which("java")
    if not java:
        raise PlantUmlRenderError("Java is required to render PlantUML locally.", status=503)

    try:
        completed = subprocess.run(
            [java, "-Djava.awt.headless=true", "-jar", str(_plantuml_jar()), "-tsvg", "-pipe"],
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RENDER_TIMEOUT_SECONDS,
            check=False,
            creationflags=windows_hide_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise PlantUmlRenderError("PlantUML rendering timed out.", status=504) from exc
    except OSError as exc:
        raise PlantUmlRenderError("PlantUML could not be started locally.", status=503) from exc

    svg = completed.stdout
    if completed.returncode != 0 or not svg.lstrip().startswith(b"<svg"):
        raise PlantUmlRenderError("PlantUML could not render this diagram.")
    if len(svg) > MAX_SVG_BYTES:
        raise PlantUmlRenderError("Rendered PlantUML diagram is too large.", status=413)

    safe_svg = _sanitize_svg_bytes(svg)
    return "data:image/svg+xml;base64," + base64.b64encode(safe_svg).decode("ascii")
