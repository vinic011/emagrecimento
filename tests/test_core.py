from contextlib import closing
from datetime import date, timedelta
from io import BytesIO
import sqlite3
from types import SimpleNamespace

import pandas as pd
from pypdf import PdfReader
import pytest
import core


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_DB_PATH', str(tmp_path / 'nested' / 'diary.db'))
    with closing(core.connect()) as connection:
        yield connection


@pytest.mark.parametrize('text,expected', [
    ('2 ovos', [('ovo', 100)]),
    ('150g arroz,100g feijão', [('arroz', 150), ('feijao', 100)]),
    ('150 g de arroz, 2 ovos, 100 gramas de feijão', [('arroz', 150), ('ovo', 100), ('feijao', 100)]),
    ('60 gramas de pão integral e 40 gramas de peito de peru e 200 ml de café sem açúcar', [('pao integral', 60), ('peito de peru', 40), ('cafe sem acucar', 200)]),
    ('0,5 kg de frango; 30,5 g de queijo minas', [('frango', 500), ('queijo minas', 30.5)]),
    ('100 g de maçã; 150 g de peito de frango', [('maca', 100), ('frango grelhado', 150)]),
    ('100 g de desconhecido', []),
])
def test_local_parser(text, expected):
    result = core.parse_local(text)
    assert [(x['food'], x['grams']) for x in result] == expected


@pytest.mark.parametrize('field,value', [('grams', -1), ('grams', 0), ('grams', float('nan')), ('grams', float('inf')), ('kcal100', -1), ('kcal100', 1001), ('food', ''), ('food', None)])
def test_invalid_records_are_atomic(database, field, value):
    good = {'food': 'Arroz', 'grams': 100, 'kcal100': 130}
    with pytest.raises(ValueError):
        core.save_meal(database, '2026-11-08', 'Almoço', [good, {**good, field: value}], '')
    assert database.execute('SELECT COUNT(*) FROM meals').fetchone()[0] == 0


def test_persistence_and_backup(database, tmp_path):
    core.save_meal(database, '2026-11-08', 'Almoço', core.parse_local('150 g de arroz'), 'relato')
    core.set_setting(database, 'start', '2026-11-08')
    backup = tmp_path / 'restored.db'
    backup.write_bytes(core.backup_bytes(database))
    with closing(sqlite3.connect(backup)) as restored:
        assert restored.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert restored.execute('SELECT kcal FROM meals').fetchone() == (195.0,)
        assert core.get_setting(restored, 'start', '') == '2026-11-08'
    with closing(core.connect()) as reopened:
        assert reopened.execute('SELECT COUNT(*) FROM meals').fetchone() == (1,)
        assert core.get_setting(reopened, 'start', '') == '2026-11-08'


def test_daily_backup_and_restore(database, tmp_path):
    from scripts.restore import restore
    core.save_meal(database, '2026-11-08', 'Jantar', core.parse_local('2 ovos'), '')
    core.daily_backup(database)
    source = core.db_path().parent / 'backups' / f'meu_plano_{core.today().isoformat()}.db'
    output = restore(source, tmp_path / 'restored.db')
    with closing(sqlite3.connect(output)) as restored:
        assert restored.execute('SELECT kcal FROM meals').fetchone() == (155.0,)
    with pytest.raises(ValueError):
        restore(source, output)
    core.save_meal(database, '2026-11-09', 'Almoço', core.parse_local('150 g de arroz'), '')
    core.daily_backup(database)
    with closing(sqlite3.connect(source)) as snapshot:
        assert snapshot.execute('SELECT COUNT(*) FROM meals').fetchone() == (2,)


def test_old_database_migration(tmp_path, monkeypatch):
    path = tmp_path / 'old.db'
    monkeypatch.setenv('APP_DB_PATH', str(path))
    with closing(sqlite3.connect(path)) as old:
        old.execute('CREATE TABLE habits (day TEXT PRIMARY KEY, water INTEGER, sleep INTEGER, bike INTEGER, bike_minutes INTEGER, notes TEXT)')
        old.execute("INSERT INTO habits VALUES ('2026-11-08',1,1,1,60,'original')")
        old.commit()
    with closing(core.connect()) as migrated:
        assert migrated.execute('SELECT notes,fiber FROM habits').fetchone() == ('original', 0)


def test_pdf_has_all_sixty_days_and_non_saturday_measurements(database):
    core.save_meal(database, '2026-11-08', 'Almoço', [{'food': '<b>Arroz & feijão</b>', 'grams': 150, 'kcal100': 130}], '')
    database.executemany('INSERT INTO measures VALUES (?,?,?,?,?)', [('2026-11-08', 98, 100, 105, 'Domingo & teste'), ('2026-11-14', 97, 99, 104, 'Sabado')])
    database.execute("INSERT INTO habits(day,water,fiber,notes) VALUES ('2026-11-08',1,1,'Teste < & >')")
    frames = [pd.read_sql_query(f'SELECT * FROM {table}', database) for table in ('meals', 'habits', 'measures')]
    result = core.make_pdf(date(2026, 11, 8), 1700, *frames)
    pdf = PdfReader(BytesIO(result))
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    for offset in range(60):
        assert (date(2026, 11, 8) + timedelta(days=offset)).strftime('%d/%m/%Y') in text
    assert 'Domingo & teste' in text
    assert 'Sabado' in text
    assert '<b>Arroz & feijão</b>' in text
    # No text may overflow the printable page horizontally.
    for page in pdf.pages:
        def check_position(text, cm, tm, font, size):
            if text.strip():
                assert 0 <= cm[4] + tm[4] <= float(page.mediabox.width)
        page.extract_text(visitor_text=check_position)


def test_csv_neutralizes_formulas():
    result = core.export_csv(pd.DataFrame({'food': ['=HYPERLINK("evil")', '+cmd', 'Arroz'], 'kcal': [1, 2, 3]})).decode('utf-8-sig')
    assert "'=HYPERLINK" in result and "'+cmd" in result


def test_transcription_contract(monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='2 ovos')
    monkeypatch.setattr(core, 'ai_client', lambda: SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create))))
    monkeypatch.setenv('OPENAI_TRANSCRIPTION_MODEL', 'gpt-transcribe')
    assert core.transcribe(BytesIO(b'fake audio')) == '2 ovos'
    assert calls[0]['extra_body'] == {'languages': ['pt']}
    with pytest.raises(ValueError):
        core.transcribe(BytesIO())


def test_ai_rejects_invalid_numbers(monkeypatch):
    message = SimpleNamespace(content='{"items":[{"food":"arroz","grams":-150,"kcal_per_100g":130}]}')
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=message)]))))
    monkeypatch.setattr(core, 'ai_client', lambda: client)
    with pytest.raises(ValueError):
        core.parse_ai('arroz')
