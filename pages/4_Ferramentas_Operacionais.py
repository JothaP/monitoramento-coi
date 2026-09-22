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
# AUTENTICAÇÃO
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

    st.caption(
        f"Usuário: **{st.session_state.get('usuario_logado', '')}**"
    )

    st.caption(
        f"Perfil: **{st.session_state.get('perfil', '').upper()}**"
    )

    st.divider()

    if st.button(
        "🏠 Voltar ao Menu Principal",
        use_container_width=True
    ):
        st.switch_page("app.py")

# ============================================================
# CABEÇALHO
# ============================================================

st.title("🛠️ Ferramentas Operacionais")

st.caption(
    "Acesse as ferramentas operacionais disponíveis na Plataforma COI."
)

st.divider()

# ============================================================
# FERRAMENTAS
# ============================================================

col1, col2, col3 = st.columns(3)

# ============================================================
# GERADOR DE LOTES
# ============================================================

with col1:

    st.markdown("#### 📦 Gerador de Lotes")

    st.markdown("**Processamento e geração de lotes operacionais**")

    st.caption("Status: Ativo")

    if st.button(
        "Acessar Gerador de Lotes",
        type="primary",
        use_container_width=True,
        key="btn_gerador_lotes"
    ):
        st.switch_page(
            "pages/4_1_Gerador_Lotes.py"
        )

# ============================================================
# GERADOR DE PAINEL
# ============================================================

with col2:

    st.markdown("#### 📊 Gerador de Painel")

    st.markdown("**Painéis Operacionais**")

    st.caption("Status: Ativo")

    if st.button(
        "Acessar Gerador de Painel",
        type="primary",
        use_container_width=True,
        key="btn_gerador_painel"
    ):
        st.switch_page(
            "pages/4_2_Gerador_de_Painel.py"
        )

# ============================================================
# CARDS OPERACIONAIS
# ============================================================

with col3:

    st.markdown("#### 🃏 Cards Operacionais")

    st.markdown("**Cards e Indicadores**")

    st.caption("Status: Em desenvolvimento")

    st.button(
        "Em breve",
        disabled=True,
        use_container_width=True,
        key="btn_cards_operacionais"
    )
