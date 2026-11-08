"""Browser checks on phone-sized touch viewports, with an isolated diary."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'dist' / 'mobile-qa'


@contextmanager
def server():
    with tempfile.TemporaryDirectory(prefix='meu-plano-mobile-') as temporary:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        password = secrets.token_urlsafe(24)
        env = {**os.environ, 'APP_PASSWORD': password, 'OPENAI_API_KEY': '',
               'APP_DB_PATH': str(Path(temporary) / 'diary.db')}
        with open(Path(temporary) / 'server.log', 'w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'app.py',
                '--server.address=127.0.0.1', f'--server.port={port}'], cwd=ROOT,
                env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                url = f'http://127.0.0.1:{port}'
                for _ in range(60):
                    if process.poll() is not None:
                        raise RuntimeError('Servidor encerrou antes do teste.')
                    try:
                        if urlopen(url + '/_stcore/health', timeout=1).status == 200:
                            break
                    except OSError:
                        time.sleep(.25)
                else:
                    raise RuntimeError('Servidor não iniciou.')
                yield url, password
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def inspect_page(page, name):
    page.locator('[data-testid="stMain"]').evaluate('(el) => el.scrollTop = 0')
    page.screenshot(path=str(OUTPUT / f'{name}.png'))
    layout=page.evaluate('''() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth,
      tabs: Array.from(document.querySelectorAll('[role=tab]')).map(x => ({text:x.textContent,rect:x.getBoundingClientRect().toJSON()}))})''')
    assert layout['documentWidth'] <= layout['width'], layout
    assert all(0 <= t['rect']['left'] and t['rect']['right'] <= layout['width'] and t['rect']['height'] >= 44 for t in layout['tabs']), layout
    print(json.dumps({'device': name, 'viewport': page.viewport_size, 'layout': layout}, ensure_ascii=False), flush=True)


def exercise(page, name):
    # Every operation below is driven through browser controls in a touch viewport.
    page.get_by_label('Relato da refeição', exact=True).fill('150 g de arroz, 2 ovos')
    page.get_by_role('button', name='Calcular alimentos do relato', exact=True).tap()
    expect(page.get_by_label('Alimento', exact=True)).to_have_count(2)
    quantity=page.get_by_label('Quantidade (g/ml)', exact=True).first
    quantity.fill('160')
    quantity.press('Tab')
    expect(page.get_by_text('Total estimado: 363 kcal', exact=False)).to_be_visible()
    page.get_by_role('button', name='💾 Salvar no diário', exact=True).tap()
    expect(page.get_by_text('Refeição salva no diário.', exact=True)).to_be_visible()
    page.get_by_role('tab', name='✅ Checklist', exact=True).tap()
    water=page.get_by_label('💧 Bebi água suficiente hoje', exact=True)
    if not water.is_checked():page.get_by_text('💧 Bebi água suficiente hoje', exact=True).tap()
    expect(water).to_be_checked()
    page.get_by_label('Observações (fome, disposição, dificuldades)', exact=True).fill(f'Teste {name}')
    page.get_by_role('button', name='Salvar checklist', exact=True).tap()
    expect(page.get_by_text('Checklist salvo!', exact=True)).to_be_visible()
    page.get_by_role('tab', name='📏 Evolução semanal', exact=True).tap()
    page.get_by_label('Peso (kg)', exact=True).fill('96.5')
    page.get_by_role('button', name='Salvar medidas', exact=True).tap()
    expect(page.get_by_text('Medidas salvas!', exact=True)).to_be_visible()
    page.get_by_role('tab', name='📊 Histórico e exportação', exact=True).tap()
    for label,filename in [('📄 Baixar meu PDF atualizado',f'{name}.pdf'),('💾 Baixar backup completo',f'{name}.db')]:
        with page.expect_download() as waiting:
            page.get_by_role('button', name=label, exact=True).tap()
        download=waiting.value
        download.save_as(str(OUTPUT / filename))
        assert (OUTPUT / filename).stat().st_size > 1000
    page.get_by_role('tab', name='🍽️ Refeições e áudio', exact=True).tap()
    page.get_by_role('button', name='Adicionar alimentos manualmente', exact=True).tap()
    page.get_by_label('Alimento', exact=True).fill(f'Iogurte {name}')
    page.get_by_label('Quantidade (g/ml)', exact=True).fill('170')
    page.get_by_label('Calorias por 100 g/ml', exact=True).fill('65')
    page.get_by_label('Calorias por 100 g/ml', exact=True).press('Tab')
    expect(page.get_by_text('Total estimado: 110 kcal', exact=False)).to_be_visible()
    page.screenshot(path=str(OUTPUT / f'{name}-form.png'))
    page.get_by_role('button', name='💾 Salvar no diário', exact=True).tap()
    expect(page.get_by_text('Refeição salva no diário.', exact=True)).to_be_visible()
    assert page.get_by_text('Traceback').count()==0
    print(f'{name}: refeições, edição, checklist, medidas, PDF e backup OK', flush=True)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with server() as (url, password), sync_playwright() as p:
        for name, engine, device in [('android', p.chromium, 'Pixel 7'), ('iphone', p.webkit, 'iPhone 13')]:
            browser = engine.launch(headless=True)
            try:
                context = browser.new_context(**p.devices[device], accept_downloads=True, locale='pt-BR')
                page = context.new_page()
                page.goto(url)
                page.get_by_label('Senha', exact=True).fill(password)
                page.get_by_role('button', name='Entrar', exact=True).tap()
                expect(page.get_by_role('button',name='Calcular alimentos do relato',exact=True)).to_be_visible(timeout=30000)
                expect(page.locator('[data-testid=stMetricValue]').first).to_contain_text('1.700',timeout=30000)
                inspect_page(page, name)
                try:
                    exercise(page, name)
                except Exception:
                    page.screenshot(path=str(OUTPUT / f'{name}-failure.png'))
                    raise
                context.close()
            finally:
                browser.close()


if __name__ == '__main__':
    main()
