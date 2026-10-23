import sqlite3
from contextlib import closing

import pytest
from api import agent_sessions


def seed(path, *, role_index=False, partial=False, collation='NOCASE'):
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
        CREATE TABLE sessions(id TEXT PRIMARY KEY, title TEXT, model TEXT,
          message_count INTEGER, started_at REAL, source TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT,
          role TEXT, content TEXT, timestamp REAL);
        CREATE INDEX idx_messages_session ON messages(session_id, timestamp);
        INSERT INTO sessions VALUES ('old', 'Old resumed', 'm', 99, 1, 'cli');
        INSERT INTO sessions VALUES ('new', 'New', 'm', 99, 3, 'cli');
        INSERT INTO messages VALUES (1, 'old', 'USER', 'payload', 2);
        INSERT INTO messages VALUES (2, 'old', 'assistant', 'payload', 10);
        INSERT INTO messages VALUES (3, 'new', 'user', 'payload', 4);
        INSERT INTO messages VALUES (4, 'new', 'tool', 'payload', 5);
        """)
        if role_index:
            where = " WHERE role = 'user'" if partial else ''
            db.execute(f"CREATE INDEX idx_messages_session_role ON messages(session_id, role COLLATE {collation}){where}")
        db.commit()


def listing_and_plan(path, monkeypatch):
    statements = []
    real_connect = sqlite3.connect
    def traced(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(agent_sessions.sqlite3, 'connect', traced)
    rows = agent_sessions.read_importable_agent_session_rows(path, limit=2)
    query = next(q for q in statements if 'FROM sessions s' in q)
    with closing(real_connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        plan = [r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + query)]
    return rows, plan


def test_history_counts_use_covering_indexes_without_reading_message_payloads(tmp_path, monkeypatch):
    path = tmp_path / 'state.db'
    seed(path, role_index=True)
    rows, plan = listing_and_plan(path, monkeypatch)
    assert [r['id'] for r in rows] == ['old', 'new']
    assert [r['actual_message_count'] for r in rows] == [2, 2]
    assert [r['actual_user_message_count'] for r in rows] == [1, 1]
    assert [r['last_activity'] for r in rows] == [10, 5]
    assert not any('LEFT-JOIN' in step for step in plan), plan
    assert any('COVERING INDEX idx_messages_session_role' in step for step in plan), plan
    assert not any('USING INDEX idx_messages' in step for step in plan), plan


@pytest.mark.parametrize(('partial', 'collation'), [(True, 'NOCASE'), (False, 'BINARY')])
def test_incompatible_role_index_keeps_correct_fallback(tmp_path, monkeypatch, partial, collation):
    path = tmp_path / 'state.db'
    seed(path, role_index=True, partial=partial, collation=collation)
    rows, plan = listing_and_plan(path, monkeypatch)
    assert [r['actual_user_message_count'] for r in rows] == [1, 1]
    assert [r['actual_message_count'] for r in rows] == [2, 2]
    assert any('LEFT-JOIN' in step for step in plan)


def test_shell_fingerprint_changes_for_local_build_without_release_version(tmp_path):
    from api.updates import _detect_webui_asset_version
    static = tmp_path / 'static'
    static.mkdir()
    asset = static / 'sessions.js'
    asset.write_text('old')
    first = _detect_webui_asset_version(tmp_path, 'unknown')
    assert first != 'unknown'
    assert first == _detect_webui_asset_version(tmp_path, 'unknown')
    asset.write_text('new')
    assert first != _detect_webui_asset_version(tmp_path, 'unknown')


def test_unknown_asset_urls_revalidate_instead_of_caching_for_one_year(tmp_path, monkeypatch):
    from api import config, routes
    from tests.test_static_asset_compression_and_cache import _serve
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'sessions.js').write_text('script')
    monkeypatch.setattr(config, 'get_static_root', lambda: static)
    monkeypatch.setattr(routes, '_STATIC_CACHE', {})
    handler = _serve(routes, '/static/sessions.js', query='v=unknown')
    assert handler.header('Cache-Control') == 'public, no-cache'


def test_all_profile_cache_validation_reuses_committed_context_fingerprints(tmp_path, monkeypatch):
    from api import models, routes
    from api import route_session_list_cache as cache
    active = tmp_path / 'active.db'
    child = tmp_path / 'child.db'
    context_stamp = (('child-home', 'child', ('commit', 'db', 'wal', 'shm')),)
    monkeypatch.setattr(models, '_all_profiles_cli_contexts', lambda: ([(tmp_path, child, 'child')], context_stamp))
    monkeypatch.setattr(routes, '_active_state_db_path', lambda: active)
    monkeypatch.setattr(cache, '_session_list_cache_streaming_freeze_marker', lambda: None)
    calls = []
    def fingerprint(path):
        calls.append(path)
        return 'active-commit'
    monkeypatch.setattr(routes, '_session_list_cache_state_db_fingerprint', fingerprint)
    key = cache._session_list_cache_key('default', True, False, False, False)
    stamp = cache._session_list_cache_source_stamp(key)
    assert stamp[6] == (('child-home', 'child', 'commit', 'db', 'wal'),)
    assert calls == [active]


def test_cache_lookup_reports_stale_reason_from_one_source_read(monkeypatch):
    from api import route_session_list_cache as cache
    key = cache._session_list_cache_key('default', False, False, False, False)
    calls = []
    def stamp(_key):
        calls.append(_key)
        return ('new',)
    monkeypatch.setattr(cache, '_session_list_cache_resolved_source_stamp', stamp)
    with cache._SESSIONS_CACHE_LOCK:
        cache._SESSIONS_CACHE[key] = (0.0, ('old',), {'sessions': []})
    try:
        payload, fresh, reason = cache._session_list_cache_get(key, allow_stale=True, with_reason=True)
        assert payload == {'sessions': []}
        assert not fresh
        assert reason == 'source'
        assert calls == [key]
    finally:
        cache._session_list_cache_clear()
