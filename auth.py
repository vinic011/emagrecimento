"""Single-owner access gate; no diary or database is loaded before login."""
import hashlib
import hmac
import threading
import time

import streamlit as st
from core import config


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
    session = st.session_state.get("owner_login", {})
    if session.get("fingerprint") == fingerprint and time.time() < session.get("expires", 0):
        if st.sidebar.button("Sair", key="logout"):
            st.session_state.clear()
            st.rerun()
        return
    # Expired sessions must not retain diary widgets or download links.
    st.session_state.pop("owner_login", None)
    st.title("🔒 Meu Plano")
    st.caption("Seu diário pessoal de alimentação e hábitos.")
    with st.form("login", clear_on_submit=True):
        supplied = st.text_input("Senha", type="password", max_chars=256)
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        guard = login_guard()
        with guard["lock"]:
            if time.monotonic() < guard["blocked_until"]:
                st.error("Muitas tentativas. Aguarde um minuto e tente novamente.")
            elif hmac.compare_digest(supplied.encode(), password.encode()):
                guard["failures"] = 0
                st.session_state.clear()
                st.session_state["owner_login"] = {"fingerprint": fingerprint, "expires": time.time() + 12 * 3600}
                st.rerun()
            else:
                guard["failures"] += 1
                if guard["failures"] >= 5:
                    guard["blocked_until"] = time.monotonic() + 60
                    guard["failures"] = 0
                st.error("Senha incorreta.")
    st.stop()
