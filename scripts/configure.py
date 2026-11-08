"""Set a local password without putting it in shell history or console output."""
from getpass import getpass
import json
import os
from pathlib import Path

path = Path(__file__).resolve().parents[1] / '.streamlit' / 'secrets.toml'
if path.exists():
    raise SystemExit('secrets.toml já existe. Edite o arquivo para preservar sua configuração.')
password = getpass('Crie sua senha de acesso (16 a 256 caracteres): ')
if not 16 <= len(password) <= 256:
    raise SystemExit('Senha deve ter entre 16 e 256 caracteres.')
if getpass('Confirme sua senha: ') != password:
    raise SystemExit('As senhas não conferem.')
path.parent.mkdir(exist_ok=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as file:
    file.write('APP_PASSWORD = ' + json.dumps(password, ensure_ascii=False) + '\n')
print('Senha local configurada. Inicie com: .venv/bin/streamlit run app.py')
