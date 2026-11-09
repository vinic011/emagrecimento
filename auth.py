"""Single-owner access gate; no diary or database is loaded before login."""
import hashlib
import hmac
import secrets
import threading
import time

import streamlit as st
import streamlit.components.v2 as components
from core import config

REMEMBER_SECONDS = 30 * 24 * 3600
COOKIE_NAME = 'meu_plano_login'

browser_login = components.component('meu_plano_browser_login', js="""
export default function({data, setStateValue}) {
    const secure = location.protocol === 'https:' ? '; Secure' : '';
    if (data.command !== null) {
        document.cookie = data.name + '=' + encodeURIComponent(data.command)
            + '; Path=/; SameSite=Lax; Max-Age=' + (data.command ? data.maxAge : 0) + secure;
    }
    const entry = document.cookie.split('; ').find(x => x.startsWith(data.name + '='));
    let token = '';
    try { token = entry ? decodeURIComponent(entry.slice(data.name.length + 1)) : ''; } catch (_) {}
    setStateValue('token', token);
}
""")


def remember_token(password, now=None):
    expires = int(time.time() if now is None else now) + REMEMBER_SECONDS
    payload = f'{expires}.{secrets.token_hex(16)}'
    signature = hmac.new(password.encode(), ('remember-v1:' + payload).encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def token_expiry(token, password, now=None):
    if not isinstance(token, str) or len(token) > 160:
        return 0
    try:
        expiry, nonce, signature = token.split('.')
        expires = int(expiry)
    except (ValueError, TypeError):
        return 0
    current = time.time() if now is None else now
    if not current < expires <= current + REMEMBER_SECONDS or len(nonce) != 32:
        return 0
    expected = hmac.new(password.encode(), f'remember-v1:{expiry}.{nonce}'.encode(), hashlib.sha256).hexdigest()
    return expires if hmac.compare_digest(signature.encode(), expected.encode()) else 0


@st.cache_resource
def login_guard():
    # Shared across browser sessions so reconnecting cannot bypass the cooldown.
    return {"lock": threading.Lock(), "failures": 0, "blocked_until": 0.0}


def require_login():
    password = config("APP_PASSWORD")
    if not isinstance(password, str) or not 16 <= len(password) <= 256:
        st.title("🔒 Meu Plano")
        st.error("Configure APP_PASSWORD com 16 a 256 caracteres para liberar o acesso.")
        st.stop()
    fingerprint = hashlib.sha256(password.encode()).hexdigest()
    command = st.session_state.get('login_cookie_command')
    browser = browser_login(key='login_cookie', data={'name': COOKIE_NAME, 'command': command,
        'maxAge': REMEMBER_SECONDS}, on_token_change=lambda: None)
    if command is not None and browser.token == command:
        st.session_state.pop('login_cookie_command', None)
    session = st.session_state.get("owner_login", {})
    if not session and command is None and not st.session_state.get('logged_out'):
        expires = token_expiry(browser.token, password)
        if expires:
            session = {'fingerprint': fingerprint, 'expires': expires}
            st.session_state['owner_login'] = session
    if session.get("fingerprint") == fingerprint and time.time() < session.get("expires", 0):
        if st.sidebar.button("Sair", key="logout"):
            st.session_state.clear()
            st.session_state['login_cookie_command'] = ''
            st.session_state['logged_out'] = True
            st.rerun()
        return
    # Expired sessions must not retain diary widgets or download links.
    st.session_state.pop("owner_login", None)
    st.title("🔒 Meu Plano")
    st.caption("Seu diário pessoal de alimentação e hábitos.")
    with st.form("login", clear_on_submit=True):
        supplied = st.text_input("Senha", type="password", max_chars=256)
        remember = st.checkbox('Manter conectado por 30 dias', value=True)
        st.caption('Desmarque se estiver usando um aparelho compartilhado.')
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        guard = login_guard()
        with guard["lock"]:
            if time.monotonic() < guard["blocked_until"]:
                st.error("Muitas tentativas. Aguarde um minuto e tente novamente.")
            elif hmac.compare_digest(supplied.encode(), password.encode()):
                guard["failures"] = 0
                st.session_state.clear()
                token = remember_token(password) if remember else ''
                st.session_state['login_cookie_command'] = token
                st.session_state["owner_login"] = {"fingerprint": fingerprint,
                    "expires": token_expiry(token, password) if remember else time.time() + 12 * 3600}
                st.rerun()
            else:
                guard["failures"] += 1
                if guard["failures"] >= 5:
                    guard["blocked_until"] = time.monotonic() + 60
                    guard["failures"] = 0
                st.error("Senha incorreta.")
    st.stop()
