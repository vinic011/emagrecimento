"""Integration tests: only scripts/check_postgres.py's disposable database."""
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import os
import sqlite3

import psycopg
import pytest
from streamlit.testing.v1 import AppTest

import core
from storage import read_frame, import_sqlite_backup, initialize_tables

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'integration-only-password-123456'


@pytest.fixture
def remote(monkeypatch, tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Execute scripts/check_postgres.py para usar PostgreSQL temporário.')
    parsed = urlsplit(url)
    assert parsed.hostname == '127.0.0.1' and parsed.path == '/meu_plano_test'
    with psycopg.connect(url, autocommit=True) as cleanup:
        cleanup.execute('DROP TABLE IF EXISTS daily_backups,meals,habits,measures,settings')
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setenv('APP_PASSWORD', PASSWORD)
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('APP_DB_PATH', str(tmp_path / 'must-not-exist.db'))
    with closing(core.connect(require_remote=True)) as connection:
        yield connection
    assert not (tmp_path / 'must-not-exist.db').exists()


def test_postgres_persists_on_new_connection_and_exports_sqlite(remote, tmp_path):
    core.save_meal(remote, '2026-11-08', 'Almoço', core.parse_local('150 g de arroz, 2 ovos'), "teste ' ? %")
    core.set_setting(remote, 'target', 1800)
    core.set_setting(remote, 'target', 1750)
    with closing(core.connect(require_remote=True)) as fresh:
        assert fresh.execute('SELECT COUNT(*) FROM meals').fetchone() == (2,)
        assert core.get_setting(fresh, 'target', '') == '1750'
        frame = read_frame('SELECT * FROM meals WHERE day=?', fresh, ('2026-11-08',))
        assert frame.kcal.sum() == 350
        payload = core.backup_bytes(fresh)
        core.daily_backup(fresh, payload)
    snapshot = tmp_path / 'backup.db'
    snapshot.write_bytes(payload)
    with closing(sqlite3.connect(snapshot)) as restored:
        assert restored.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert restored.execute('SELECT COUNT(*) FROM meals').fetchone() == (2,)
        assert restored.execute('SELECT source FROM meals LIMIT 1').fetchone() == ("teste ' ? %",)
    with closing(core.connect(require_remote=True)) as fresh:
        assert bytes(fresh.execute('SELECT payload FROM daily_backups').fetchone()[0]) == payload


def test_postgres_rolls_back_partial_transaction(remote):
    with pytest.raises(RuntimeError):
        with remote:
            remote.execute('INSERT INTO measures(day,weight) VALUES (?,?)', ('2026-11-08', 98))
            raise RuntimeError('simulated interruption')
    assert remote.execute('SELECT COUNT(*) FROM measures').fetchone() == (0,)


def test_import_backup_to_neon_preserves_ids_and_refuses_overwrite(remote, tmp_path):
    path = tmp_path / 'previous.db'
    with closing(sqlite3.connect(path)) as source:
        initialize_tables(source)
        source.execute("INSERT INTO meals(id,day,meal,food,grams,kcal,source,created) VALUES (27,'2026-11-08','Almoço','Arroz',150,195,'original','2026-11-08')")
        source.execute("INSERT INTO settings VALUES ('start','2026-11-08')")
        source.execute("INSERT INTO settings VALUES ('target','1750')")
        source.commit()
    import_sqlite_backup(remote, path)
    core.save_meal(remote, '2026-11-09', 'Jantar', core.parse_local('2 ovos'), '')
    assert remote.execute('SELECT id FROM meals ORDER BY id').fetchall() == [(27,), (28,)]
    assert core.get_setting(remote, 'target', '') == '1750'
    with pytest.raises(ValueError, match='destino já contém registros'):
        import_sqlite_backup(remote, path)
    assert remote.execute('SELECT COUNT(*) FROM meals').fetchone() == (2,)


def test_cloud_interface_save_update_delete_and_reconnect(remote):
    from auth import login_guard
    login_guard.clear()
    def button(at, label):
        return next(x for x in at.button if x.label == label)
    def login():
        at = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()
        at.text_input[0].set_value(PASSWORD)
        button(at, 'Entrar').click().run()
        assert not at.exception
        assert len(at.tabs) == 4
        return at
    at = login()
    at.text_area(key='food_description').set_value('2 ovos')
    button(at, 'Calcular alimentos do relato').click().run()
    button(at, '💾 Salvar no diário').click().run()
    assert not at.exception
    assert at.metric[1].value == '155 kcal'
    day = at.date_input(key='record_day').value.isoformat()
    at.checkbox(key=f'water_{day}').check()
    button(at, 'Salvar checklist').click().run()
    at.checkbox(key=f'fiber_{day}').check()
    button(at, 'Salvar checklist').click().run()
    at.number_input(key=f'weight_{day}').set_value(96.5)
    button(at, 'Salvar medidas').click().run()
    at.number_input(key=f'weight_{day}').set_value(96.)
    button(at, 'Salvar medidas').click().run()
    assert not at.exception
    assert remote.execute('SELECT water,fiber FROM habits WHERE day=?', (day,)).fetchone() == (1,1)
    assert remote.execute('SELECT weight FROM measures WHERE day=?', (day,)).fetchone() == (96.,)
    assert remote.execute('SELECT COUNT(*) FROM daily_backups').fetchone() == (1,)
    fresh = login()
    assert fresh.metric[1].value == '155 kcal'
    button(fresh, '🗑️').click().run()
    assert not fresh.exception
    assert remote.execute('SELECT COUNT(*) FROM meals').fetchone() == (0,)
