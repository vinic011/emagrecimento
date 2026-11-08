"""Run integration tests against an isolated local PostgreSQL cluster."""
from pathlib import Path
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    found = shutil.which('initdb')
    binaries = Path(found).parent if found else Path('/opt/homebrew/opt/postgresql@17/bin')
    if not (binaries / 'initdb').exists():
        raise SystemExit('Instale PostgreSQL e disponibilize initdb e pg_ctl no PATH.')
    with tempfile.TemporaryDirectory(prefix='meu-plano-pg-') as directory:
        temporary = Path(directory)
        data = temporary / 'data'
        password = secrets.token_hex(24)
        password_file = temporary / 'password'
        password_file.touch(mode=0o600)
        password_file.write_text(password)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        subprocess.run([str(binaries / 'initdb'), '-D', str(data), '-U', 'diary_test',
                        '--no-locale', '--encoding=UTF8', '--auth-local=trust',
                        '--auth-host=scram-sha-256', f'--pwfile={password_file}'],
                       check=True, capture_output=True)
        started = False
        try:
            subprocess.run([str(binaries / 'pg_ctl'), '-D', str(data), '-l', str(temporary / 'postgres.log'),
                            '-o', f'-h 127.0.0.1 -p {port} -k {directory}', '-w', 'start'],
                           check=True, capture_output=True)
            started = True
            import psycopg
            base = f'postgresql://diary_test:{password}@127.0.0.1:{port}/'
            with psycopg.connect(base + 'postgres', autocommit=True) as connection:
                connection.execute('CREATE DATABASE meu_plano_test')
            env = {**os.environ, 'TEST_DATABASE_URL': base + 'meu_plano_test',
                   'DATABASE_URL': '', 'OPENAI_API_KEY': ''}
            print('PostgreSQL temporário iniciado; executando testes de integração.', flush=True)
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_postgres.py'],
                                    cwd=ROOT, env=env)
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            if started:
                subprocess.run([str(binaries / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'],
                               check=True, capture_output=True)


if __name__ == '__main__':
    main()
