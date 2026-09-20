import streamlit as st

st.set_page_config(page_title="Mapeamento - COI", page_icon="📊", layout="wide")

# Trava de segurança por URL direta
if "perfil" not in st.session_state or st.session_state.perfil != "admin":
    st.error("⛔ Acesso negado. Este módulo está em desenvolvimento e restrito a administradores.")
    if st.button("🏠 Voltar ao Menu Principal"):
        st.switch_page("app.py")
    st.stop()

if st.sidebar.button("🏠 Voltar ao Menu Principal"):
    st.switch_page("app.py")

st.title("📊 Módulo 2 - Mapeamento (Em Desenvolvimento)")
st.info("Painel restrito para testes do administrador.")