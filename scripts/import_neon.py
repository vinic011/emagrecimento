"""Import a complete SQLite backup into an empty Neon/PostgreSQL diary."""
from contextlib import closing
from getpass import getpass
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
import sqlite3
from core import config, today
from storage import open_postgres, import_sqlite_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup')
    args = parser.parse_args()
    url = config('DATABASE_URL') or getpass('Cole a DATABASE_URL do banco Neon vazio (entrada oculta): ')
    try:
        with closing(open_postgres(url, today().isoformat())) as connection:
            import_sqlite_backup(connection, args.backup)
    except (ValueError, OSError, sqlite3.Error):
        parser.exit(1, 'Importação recusada: confira o backup e use um banco de destino vazio. Nenhum registro existente foi substituído.\n')
    except psycopg.Error:
        parser.exit(1, 'Falha ao acessar o PostgreSQL. Confira a conexão e tente novamente; se a conexão caiu ao confirmar, confira o destino antes de repetir.\n')
    print('Backup importado. Configure a mesma DATABASE_URL nos Secrets do Streamlit.')


if __name__ == '__main__':
    main()
