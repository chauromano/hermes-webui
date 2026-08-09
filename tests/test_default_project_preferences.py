"""Regression coverage for profile-scoped default project assignment."""
from pathlib import Path

from api import config
from api import routes


ROOT = Path(__file__).resolve().parents[1]
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def test_default_project_preference_is_profile_scoped_and_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")

    config.save_settings(
        {
            "default_project_by_profile": {
                "default": "personal-project",
                "architect": "architecture-project",
            }
        }
    )

    assert config.default_project_id_for_profile("default") == "personal-project"
    assert config.default_project_id_for_profile("architect") == "architecture-project"
    assert config.default_project_id_for_profile("researcher") is None


def test_invalid_default_project_entries_are_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")

    saved = config.save_settings(
        {
            "default_project_by_profile": {
                "default": "personal-project",
                "bad\x00profile": "invalid",
                "researcher": "\x00invalid",
            }
        }
    )

    assert saved["default_project_by_profile"] == {"default": "personal-project"}


def test_session_default_uses_only_a_project_owned_by_its_profile(monkeypatch):
    monkeypatch.setattr(routes, "default_project_id_for_profile", lambda profile: "personal-project")
    monkeypatch.setattr(
        routes,
        "load_projects",
        lambda: [
            {"project_id": "personal-project", "profile": "default"},
            {"project_id": "other-profile-project", "profile": "architect"},
        ],
    )

    assert routes._default_project_for_new_session("default") == "personal-project"
    assert routes._default_project_for_new_session("architect") is None


def test_deleted_default_project_falls_back_to_unassigned(monkeypatch):
    monkeypatch.setattr(routes, "default_project_id_for_profile", lambda profile: "deleted-project")
    monkeypatch.setattr(routes, "load_projects", lambda: [])

    assert routes._default_project_for_new_session("default") is None


def test_default_project_settings_control_autosaves_and_lists_active_projects():
    assert 'id="settingsDefaultProject"' in INDEX_HTML
    assert "function _loadDefaultProjectPreference" in PANELS_JS
    assert "api('/api/projects')" in PANELS_JS
    assert "payload.default_project_id=defaultProjectSel.value||null" in PANELS_JS
    assert "await _loadDefaultProjectPreference(settings);" in PANELS_JS
