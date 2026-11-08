from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'test-only-password-123456'


def button(at, label):
    return next(x for x in at.button if x.label == label)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('APP_DB_PATH', str(tmp_path / 'diary.db'))
    monkeypatch.setenv('APP_PASSWORD', PASSWORD)
    monkeypatch.setenv('OPENAI_API_KEY', '')
    from auth import login_guard
    login_guard.clear()
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not at.exception
    return at


def login(at):
    at.text_input[0].set_value(PASSWORD)
    button(at, 'Entrar').click().run()
    assert not at.exception
    assert len(at.tabs) == 4
    return at


def test_login_gate_and_logout(app, monkeypatch):
    assert not app.tabs and not app.get('download_button')
    app.text_input[0].set_value('wrong')
    button(app, 'Entrar').click().run()
    assert app.error and not app.tabs
    login(app)
    button(app, 'Sair').click().run()
    assert not app.tabs and not app.get('download_button')
    monkeypatch.setenv('APP_PASSWORD', '')
    app.run()
    assert app.error and not app.tabs


def test_login_rate_limit_across_sessions(app):
    for _ in range(5):
        app.text_input[0].set_value('wrong')
        button(app, 'Entrar').click().run()
    other = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    other.text_input[0].set_value(PASSWORD)
    button(other, 'Entrar').click().run()
    assert not other.tabs
    assert 'Aguarde' in other.error[0].value


def test_record_delete_and_reload(app, monkeypatch):
    import os
    login(app)
    app.date_input(key='record_day').set_value(date(2026, 11, 8)).run()
    app.text_area(key='food_description').set_value('150 g de arroz, 2 ovos')
    button(app, 'Calcular alimentos do relato').click().run()
    assert not app.exception
    button(app, '💾 Salvar no diário').click().run()
    assert not app.exception
    assert app.metric[1].value == '350 kcal'
    with closing(sqlite3.connect(os.environ['APP_DB_PATH'])) as db:
        assert db.execute('SELECT COUNT(*) FROM meals').fetchone() == (2,)
    fresh = login(AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run())
    fresh.date_input(key='record_day').set_value(date(2026, 11, 8)).run()
    assert fresh.metric[1].value == '350 kcal'
    button(fresh, '🗑️').click().run()
    assert not fresh.exception
    assert fresh.metric[1].value == '155 kcal'


def test_habits_and_measurements_are_date_scoped(app):
    login(app)
    app.date_input(key='record_day').set_value(date(2026, 11, 8)).run()
    app.checkbox(key='water_2026-11-08').check()
    app.text_area(key='notes_2026-11-08').set_value('Domingo')
    button(app, 'Salvar checklist').click().run()
    app.number_input(key='weight_2026-11-08').set_value(96.5)
    button(app, 'Salvar medidas').click().run()
    assert not app.exception
    app.date_input(key='record_day').set_value(date(2026, 11, 9)).run()
    assert not app.checkbox(key='water_2026-11-09').value
    assert app.text_area(key='notes_2026-11-09').value == ''
    assert app.number_input(key='weight_2026-11-09').value == 98.0
    button(app, 'Salvar checklist').click().run()
    app.date_input(key='record_day').set_value(date(2026, 11, 8)).run()
    assert app.checkbox(key='water_2026-11-08').value
    assert app.text_area(key='notes_2026-11-08').value == 'Domingo'
    assert app.number_input(key='weight_2026-11-08').value == 96.5
    assert not app.exception


def test_draft_does_not_follow_meal_or_failed_calculation(app):
    login(app)
    app.text_area(key='food_description').set_value('2 ovos')
    button(app, 'Calcular alimentos do relato').click().run()
    assert 'draft' in app.session_state
    app.selectbox(key='meal').set_value('Jantar').run()
    assert 'draft' not in app.session_state
    assert app.text_area(key='food_description').value == ''
    app.text_area(key='food_description').set_value('2 ovos')
    button(app, 'Calcular alimentos do relato').click().run()
    app.text_area(key='food_description').set_value('não sei')
    button(app, 'Calcular alimentos do relato').click().run()
    assert 'draft' not in app.session_state


def test_audio_updates_an_already_existing_description(app, monkeypatch):
    import core
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    monkeypatch.setattr(core, 'transcribe', lambda audio: '2 ovos e 150 g de arroz')
    login(app)
    app.text_area(key='food_description').set_value('texto anterior').run()
    app.audio_input[0].set_value(('refeicao.wav', b'fake audio', 'audio/wav')).run()
    button(app, 'Transcrever áudio').click().run()
    assert not app.exception
    assert app.text_area(key='food_description').value == '2 ovos e 150 g de arroz'


def test_password_change_revokes_open_session(app, monkeypatch):
    login(app)
    monkeypatch.setenv('APP_PASSWORD', 'another-strong-password-456')
    app.run()
    assert not app.tabs and not app.get('download_button')


def test_manual_food_editor_and_save(app):
    login(app)
    button(app, 'Adicionar alimentos manualmente').click().run()
    assert button(app, '💾 Salvar no diário').disabled
    version = app.session_state['draft_version']
    app.text_input(key=f'food_{version}_0_name').set_value('Iogurte da marca X')
    app.number_input(key=f'food_{version}_0_grams').set_value(170.)
    app.number_input(key=f'food_{version}_0_kcal').set_value(65.)
    app.run()
    button(app, '💾 Salvar no diário').click().run()
    assert not app.exception
    assert app.metric[1].value == '110 kcal'


def test_food_fields_preserve_edits_when_adding_and_removing(app):
    login(app)
    app.text_area(key='food_description').set_value('150 g de arroz, 2 ovos')
    button(app, 'Calcular alimentos do relato').click().run()
    version = app.session_state['draft_version']
    app.number_input(key=f'food_{version}_0_grams').set_value(160.)
    button(app, '＋ Incluir outro alimento').click().run()
    version = app.session_state['draft_version']
    assert app.number_input(key=f'food_{version}_0_grams').value == 160.
    app.text_input(key=f'food_{version}_2_name').set_value('Iogurte')
    app.number_input(key=f'food_{version}_2_kcal').set_value(65.)
    button(app, 'Remover alimento 2').click().run()
    version = app.session_state['draft_version']
    assert app.text_input(key=f'food_{version}_1_name').value == 'Iogurte'
    button(app, '💾 Salvar no diário').click().run()
    assert not app.exception
    assert app.metric[1].value == '273 kcal'


def test_cloud_requires_remote_database_and_never_falls_back(app, monkeypatch, tmp_path):
    path = tmp_path / 'cloud-must-not-exist.db'
    monkeypatch.setenv('APP_DB_PATH', str(path))
    cloud = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()
    cloud.text_input[0].set_value(PASSWORD)
    button(cloud, 'Entrar').click().run()
    assert not cloud.exception and not cloud.tabs
    assert 'DATABASE_URL' in cloud.error[0].value
    assert not path.exists()


def test_unreachable_postgres_is_safe_and_never_falls_back(app, monkeypatch, tmp_path):
    path = tmp_path / 'fallback-must-not-exist.db'
    monkeypatch.setenv('APP_DB_PATH', str(path))
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:secret-must-not-leak@127.0.0.1:1/db')
    cloud = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=30).run()
    cloud.text_input[0].set_value(PASSWORD)
    button(cloud, 'Entrar').click().run()
    assert not cloud.exception and not cloud.tabs
    assert 'banco de dados' in cloud.error[0].value
    assert 'secret-must-not-leak' not in str(cloud)
    assert not path.exists()
