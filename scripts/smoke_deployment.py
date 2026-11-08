"""Smoke test the built Docker image using a disposable volume and random login.

Run after: docker build -t meu-plano-audit:local .
Only containers/volume created by this script are removed.
"""
import os
import secrets
import subprocess
import time
import uuid
from textwrap import dedent

image = 'meu-plano-audit:local'
suffix = uuid.uuid4().hex[:12]
container = f'meu-plano-test-{suffix}'
volume = f'meu-plano-test-data-{suffix}'
environment = {**os.environ, 'APP_PASSWORD': secrets.token_urlsafe(32)}


def docker(*args, check=True):
    return subprocess.run(['docker', *args], env=environment, check=check,
                          text=True, capture_output=True)


def execute(code):
    result = docker('exec', container, 'python', '-c', dedent(code))
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)


def start():
    docker('run', '-d', '--name', container, '--mount',
           f'type=volume,source={volume},target=/data', '-e', 'APP_PASSWORD', image)
    for _ in range(40):
        result = docker('exec', container, 'python', '-c',
                        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=2).status==200",
                        check=False)
        if result.returncode == 0:
            print('HTTP health: OK', flush=True)
            return
        time.sleep(.5)
    raise RuntimeError('O servidor não ficou saudável.')


def main():
    try:
        start()
        execute("""
    import os
    from streamlit.testing.v1 import AppTest
    from core import connect, save_meal, parse_local, daily_backup
    at=AppTest.from_file('/app/app.py',default_timeout=40).run()
    assert not at.exception and not at.tabs
    at.text_input[0].set_value(os.environ['APP_PASSWORD'])
    next(x for x in at.button if x.label=='Entrar').click().run()
    assert not at.exception and len(at.tabs)==4
    with connect() as c:
        save_meal(c,'2026-11-08','Almoço',parse_local('150 g de arroz'),'smoke-test')
        daily_backup(c)
    print('Linux: login, interface, gravação e backup OK')
    """)
        docker('restart', container)
        execute("""
    from core import connect
    with connect() as c:
        assert c.execute('SELECT kcal FROM meals').fetchone()==(195.0,)
        assert c.execute('PRAGMA integrity_check').fetchone()==('ok',)
    print('Reinício: registros preservados')
    """)
        docker('rm', '-f', container)
        start()
        execute("""
    import sqlite3
    from core import connect, db_path, today
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM meals').fetchone()==(1,)
    snapshot=db_path().parent/'backups'/f'meu_plano_{today().isoformat()}.db'
    with sqlite3.connect(snapshot) as c:
        assert c.execute('SELECT kcal FROM meals').fetchone()==(195.0,)
    print('Novo contêiner: diário e backup preservados no volume')
    """)
    except subprocess.CalledProcessError as error:
        # No secret is included in the command line or intentionally emitted.
        raise SystemExit(error.stderr[-3000:]) from None
    finally:
        docker('rm', '-f', container, check=False)
        docker('volume', 'rm', volume, check=False)


if __name__ == "__main__":
    main()
