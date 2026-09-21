import streamlit as st

st.set_page_config(page_title="Vazão de Poços - COI", page_icon="⚙️", layout="wide")

# Verificação segura de sessão e perfil de administrador
from auth import verificar_autenticacao

if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("Ir para o Login"):
        st.switch_page("app.py")
    st.stop()

if st.sidebar.button("🏠 Voltar ao Menu Principal"):
    st.switch_page("app.py")

st.title("⚙️ Módulo 3 - Vazão de Poços (Em Desenvolvimento)")
st.info("Painel restrito para testes do administrador.")
