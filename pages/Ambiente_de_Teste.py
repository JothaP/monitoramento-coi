"""Área reservada ao desenvolvimento e homologação das próximas ferramentas COI."""
import streamlit as st
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from auth import verificar_autenticacao, tem_acesso_modulo

st.set_page_config(page_title="Ambiente de Teste | COI", page_icon="🧪", layout="wide", initial_sidebar_state="collapsed")
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Acesse o Hub Central para entrar.")
    st.stop()
if str(st.session_state.get("perfil", "")).strip().lower() != "admin" or not tem_acesso_modulo("teste"):
    st.error("Seu perfil não está autorizado a acessar o Ambiente de Teste.")
    st.stop()

if st.button("⬅️ Voltar ao Menu Principal", key="voltar_menu_principal_ambiente_teste"):
    st.switch_page("app.py")
st.title("🧪 Ambiente de Teste")
st.info("Nenhuma ferramenta em desenvolvimento no momento.")
