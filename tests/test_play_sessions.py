from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.database import Database
from boardgamecompanion.plays import PlayError, PlayLog


@pytest.fixture
def log(tmp_path: Path) -> PlayLog:
    database = Database(tmp_path / 'sessions.sqlite3')
    database.initialize()
    now = datetime.now(UTC).isoformat()
    with database.transaction() as c:
        for game_id, title in ((1, 'Tricky Treats'), (2, 'Synthetic Coop')):
            c.execute('INSERT INTO board_games(id,bgg_id,title,created_at,updated_at) VALUES(?,?,?,?,?)',
                      (game_id, game_id, title, now, now))
        c.execute("INSERT INTO board_game_enrichments(board_game_id,source,external_id,metadata_json,next_refresh_at,created_at,updated_at) "
                  "VALUES(1,'bgg','1',?, '2099-01-01',?,?)",
                  ('{"alternate_titles":["Notte da brivido"]}', now, now))
    return PlayLog(database)


def payload(**changes):
    return {
        'request_id': 'a' * 32, 'played_on': '2026-11-15', 'play_mode': 'competitive',
        'duration_minutes': 60, 'players': [{'name': 'Anna'}, {'name': 'Luca'}],
        'location': 'Casa', 'rounds': [
            {'winner_indices': [0], 'scores': ['20', '10']},
            {'winner_indices': [1]}, {'winner_indices': [0, 1]},
        ], **changes,
    }


def test_session_records_distinct_results_and_counts_time_once(log):
    old = log.create(1, {'played_on': '2026-11-14', 'duration_minutes': 30, 'notes': 'Storico'})
    result = log.create_session(1, payload(completed_game=True))
    items = result['items']
    assert len(items) == 3
    assert [p['session_round'] for p in items] == [1, 2, 3]
    assert [p['completed_game'] for p in items] == [False, False, True]
    assert all(p['duration_minutes'] is None and p['session']['duration_minutes'] == 60 for p in items)
    assert [[p['winner'] for p in play['players']] for play in items] == [[True, False], [False, True], [True, True]]
    assert items[0]['players'][0]['score'] == '20'
    assert all(p['player_count'] == 2 and p['title'] == 'Notte da brivido' for p in items)
    summary = log.summary()
    assert summary['plays'] == 4 and summary['minutes'] == 90
    assert summary['games_played'][0]['minutes'] == 90
    assert {p['name']: p['wins'] for p in summary['players']} == {'Anna': 2, 'Luca': 2}
    assert log.list(q='notte da brivido')['total'] == 4
    assert log.get(old['id']) == old


def test_session_retry_is_idempotent_and_rejects_changed_content(log):
    first = log.create_session(1, payload())
    assert log.create_session(1, payload()) == first
    assert log.list()['total'] == 3
    with pytest.raises(PlayError):
        log.create_session(1, payload(duration_minutes=90))
    with pytest.raises(PlayError):
        log.create_session(2, payload())
    assert log.list()['total'] == 3


@pytest.mark.parametrize('changes', [
    {'rounds': [{'winner_indices': []}]},
    {'rounds': [{'winner_indices': [0]}, {'winner_indices': [10]}]},
    {'rounds': [{'winner_indices': [0]}, {'winner_indices': [0, 0]}]},
    {'rounds': [{'winner_indices': [0]}, {'winner_indices': [True]}]},
    {'rounds': [{'scores': ['1']}, {}]},
    {'rounds': [{'outcome': 'won'}, {}]},
    {'play_mode': 'cooperative'},
    {'play_mode': None}, {'duration_minutes': 0}, {'request_id': 'invalid'},
    {'player_count': 1},
])
def test_session_rejects_invalid_data_without_partial_records(log, changes):
    with pytest.raises(PlayError):
        log.create_session(1, payload(**changes))
    assert log.list()['total'] == 0
    with log.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM play_sessions').fetchone()[0] == 0


def test_cooperative_results_apply_to_every_participant(log):
    result = log.create_session(2, payload(play_mode='cooperative', rounds=[{'outcome': 'won'}, {'outcome': 'lost'}]))
    assert [p['outcome'] for p in result['items']] == ['won', 'lost']
    assert all(not p['winner'] for item in result['items'] for p in item['players'])
    assert all(p['wins'] == 1 and p['plays'] == 2 for p in log.summary()['players'])
    assert log.summary()['minutes'] == 60


def test_edit_and_delete_session_round_keep_shared_duration_consistent(log):
    plays = log.create_session(1, payload())['items']
    log.update(plays[1]['id'], {'session_duration_minutes': 75, 'notes': 'Seconda partita'})
    assert log.get(plays[0]['id'])['session']['duration_minutes'] == 75
    assert log.summary()['minutes'] == 75
    with pytest.raises(PlayError):
        log.update(plays[0]['id'], {'duration_minutes': 25})
    log.delete(plays[0]['id'])
    assert log.summary()['plays'] == 2 and log.summary()['minutes'] == 75
    for play in plays[1:]:
        log.delete(play['id'])
    assert log.summary()['minutes'] == 0


def test_migration_preserves_historical_play_columns(log):
    old = log.create(1, {'played_on': '2026-11-15', 'duration_minutes': 60, 'outcome': 'won',
                         'players': [{'name': 'Anna', 'winner': True}], 'player_count': 4, 'notes': 'Storico'})
    with log.database.transaction() as c:
        c.execute('DROP INDEX idx_game_plays_session')
        c.execute('ALTER TABLE game_plays DROP COLUMN session_round')
        c.execute('ALTER TABLE game_plays DROP COLUMN session_id')
        c.execute('DROP TABLE play_sessions')
        c.execute('DELETE FROM schema_migrations WHERE version=29')
        before = tuple(c.execute('SELECT * FROM game_plays').fetchone())
    log.database.initialize()
    log.database.initialize()
    with log.database.connect() as c:
        after = tuple(c.execute('SELECT * FROM game_plays').fetchone())
        assert after[:-2] == before and after[-2:] == (None, None)
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert log.get(old['id']) == old
    assert log.summary()['minutes'] == 60


def test_session_api(log, monkeypatch):
    from boardgamecompanion.main import app
    from boardgamecompanion.routers import plays as router
    monkeypatch.setattr(router, 'get_database', lambda: log.database)
    client = TestClient(app)
    data = payload()
    response = client.post('/api/games/1/play-sessions', json=data)
    assert response.status_code == 201
    assert client.post('/api/games/1/play-sessions', json=data).json() == response.json()
    assert client.get('/api/plays/summary').json()['minutes'] == 60
    invalid = deepcopy(data)
    invalid['rounds'] = [{}]
    assert client.post('/api/games/1/play-sessions', json=invalid).status_code == 422


def test_cursor_crosses_a_session_and_day_without_gaps(log):
    for _ in range(9):
        log.create(1, {"played_on": "2026-11-14"})
    session = log.create_session(1, payload())
    for _ in range(199):
        log.create(1, {"played_on": "2026-11-15"})
    first = log.list(limit=200, player=None, q="notte")
    cursor = first["next"]
    assert first["items"][-1]["session_round"] == 3
    log.create(1, {"played_on": "2026-11-16"})
    second = log.list(limit=200, q="notte", before=(cursor["played_on"], cursor["id"]))
    combined = first["items"] + second["items"]
    assert len(combined) == len({item["id"] for item in combined}) == 211
    assert [item["session_round"] for item in combined if item["session"]] == [3, 2, 1]
    assert {item["id"] for item in combined if item["session"]} == {item["id"] for item in session["items"]}
    assert "next" not in second
