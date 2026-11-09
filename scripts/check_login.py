"""Verify persistent login in real browsers with an isolated database."""
from check_mobile import server
from playwright.sync_api import sync_playwright, expect


def main():
    with server() as (url, password), sync_playwright() as p:
        for engine in (p.chromium, p.webkit):
            browser = engine.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(url)
            page.get_by_label('Senha', exact=True).fill(password)
            page.get_by_role('button', name='Entrar', exact=True).click()
            expect(page.get_by_role('tab')).to_have_count(4)
            page.wait_for_function("document.cookie.includes('meu_plano_login=')")
            page.reload()
            expect(page.get_by_role('tab')).to_have_count(4)
            saved = context.storage_state()
            context.close()
            context = browser.new_context(storage_state=saved)
            page = context.new_page()
            page.goto(url)
            expect(page.get_by_role('tab')).to_have_count(4)
            page.get_by_role('button', name='Sair', exact=True).click()
            expect(page.get_by_label('Senha', exact=True)).to_be_visible()
            page.wait_for_function("!document.cookie.includes('meu_plano_login=')")
            page.reload()
            expect(page.get_by_label('Senha', exact=True)).to_be_visible()
            expect(page.get_by_role('tab')).to_have_count(0)
            page.get_by_label('Senha', exact=True).fill(password)
            page.get_by_text('Manter conectado por 30 dias', exact=True).click()
            expect(page.get_by_label('Manter conectado por 30 dias', exact=True)).not_to_be_checked()
            page.get_by_role('button', name='Entrar', exact=True).click()
            expect(page.get_by_role('tab')).to_have_count(4)
            page.reload()
            expect(page.get_by_label('Senha', exact=True)).to_be_visible()
            expect(page.get_by_role('tab')).to_have_count(0)
            context.close()
            browser.close()
            print(f'{engine.name}: recarregar, reabrir, sair e acesso sem lembrar OK', flush=True)


if __name__ == '__main__':
    main()
