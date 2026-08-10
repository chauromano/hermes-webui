"""Regression coverage for shared user projects and legacy project consolidation."""
import json
import threading


def _configure_project_storage(monkeypatch, tmp_path):
    import api.config as config
    import api.models as models

    projects_file = tmp_path / "projects.json"
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    index_file = session_dir / "_index.json"
    monkeypatch.setattr(config, "PROJECTS_FILE", projects_file)
    monkeypatch.setattr(config, "SESSION_DIR", session_dir)
    monkeypatch.setattr(config, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(models, "PROJECTS_FILE", projects_file)
    monkeypatch.setattr(models, "SESSION_DIR", session_dir)
    monkeypatch.setattr(models, "SESSION_INDEX_FILE", index_file)
    monkeypatch.setattr(models, "_projects_migrated", False)
    monkeypatch.setattr(models, "_PROJECTS_MIGRATION_LOCK", threading.Lock())
    return projects_file, session_dir, index_file


def test_legacy_user_projects_become_shared_and_duplicate_names_merge(monkeypatch, tmp_path):
    import api.models as models

    projects_file, session_dir, index_file = _configure_project_storage(monkeypatch, tmp_path)
    projects_file.write_text(json.dumps([
        {"project_id": "work-default", "name": "work", "profile": "default", "created_at": 1},
        {"project_id": "work-architect", "name": "Work", "profile": "architect", "created_at": 2},
        {"project_id": "cron-architect", "name": "Cron Jobs", "profile": "architect", "created_at": 3},
    ]), encoding="utf-8")

    session = models.Session(session_id="architect-session", workspace=str(tmp_path), profile="architect", project_id="work-architect", messages=[{"role": "user", "content": "keep me"}])
    session.save(touch_updated_at=False)

    projects = models.load_projects()
    assert projects == [
        {"project_id": "work-default", "name": "work", "created_at": 1, "shared": True},
        {"project_id": "cron-architect", "name": "Cron Jobs", "profile": "architect", "created_at": 3},
    ]
    assert models.get_session("architect-session").project_id == "work-default"
    assert json.loads(index_file.read_text(encoding="utf-8"))[0]["project_id"] == "work-default"


def test_shared_project_is_available_to_every_profile():
    import api.models as models

    shared = {"project_id": "work", "name": "work", "shared": True}
    private = {"project_id": "cron", "name": "Cron Jobs", "profile": "architect"}
    assert models.project_is_available_to_profile(shared, "architect")
    assert models.project_is_available_to_profile(shared, "default")
    assert models.project_is_available_to_profile(private, "architect")
    assert not models.project_is_available_to_profile(private, "default")


def test_new_user_project_route_creates_shared_row():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "api" / "routes.py").read_text(encoding="utf-8")
    block = source[source.find('"/api/projects/create"'):source.find('"/api/projects/rename"')]
    assert '"shared": True' in block
    assert '"profile": _requested_profile' not in block
