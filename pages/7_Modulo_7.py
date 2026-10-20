import streamlit as st
from auth import verificar_autenticacao, tem_acesso_modulo

st.set_page_config(page_title="Módulo 7 | Plataforma COI", page_icon="🧩", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav'] {display:none;}</style>", unsafe_allow_html=True)

if not verificar_autenticacao():
    st.error("Sessão não autenticada. Entre pelo Hub Central.")
    st.stop()
if not tem_acesso_modulo("7"):
    st.error("Seu perfil não tem acesso ao Módulo 7.")
    st.stop()

st.title("🧩 Módulo 7")
st.caption("Plataforma COI — novo módulo operacional")
st.info("Módulo preparado para receber a próxima ferramenta. Nenhuma funcionalidade operacional foi ativada nesta página.")
if st.button("← Voltar ao Hub Central"):
    st.switch_page("app.py")
