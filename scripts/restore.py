"""Restore a downloaded backup to a NEW path, never overwrite a live diary."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def restore(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('Escolha um destino novo; o banco existente não será sobrescrito.')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as incoming:
        if incoming.execute('PRAGMA integrity_check').fetchone() != ('ok',):
            raise ValueError('Backup corrompido.')
        tables = {row[0] for row in incoming.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'meals', 'habits', 'measures', 'settings'} <= tables:
            raise ValueError('O arquivo não é um backup completo deste app.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids accidentally replacing another process's file.
        with destination.open('xb'):
            pass
        with closing(sqlite3.connect(destination)) as outgoing:
            incoming.backup(outgoing)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        restored = restore(args.backup, args.output)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'Falha ao restaurar: {error}\n')
    print(f'Backup restaurado em {restored}. Pare o app, configure APP_DB_PATH para esse arquivo e reinicie.')
