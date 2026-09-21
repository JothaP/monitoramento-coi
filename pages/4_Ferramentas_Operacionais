import streamlit as st
from auth import verificar_autenticacao

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Ferramentas Operacionais - COI",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Oculta a navegação padrão do Streamlit
st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# TRAVA DE SEGURANÇA E CONTROLE DE SESSÃO
# ============================================================
if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("Ir para o Login"):
        st.switch_page("app.py")
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### 🛠️ Ferramentas Operacionais")
    st.caption(f"Usuário: **{st.session_state.get('usuario_logado', '')}**")
    st.caption(f"Perfil: **{st.session_state.get('perfil', '').upper()}**")
    
    st.divider()
    
    if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")

# ============================================================
# ÁREA PRINCIPAL
# ============================================================
st.title("🛠️ Ferramentas Operacionais")
st.caption("Módulo destinado a ferramentas auxiliares da operação.")

st.divider()

st.info("Este módulo está pronto para receber as ferramentas. Me diga quais funcionalidades você deseja implementar aqui.")
