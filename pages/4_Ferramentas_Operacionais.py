import streamlit as st

from auth import verificar_autenticacao


st.set_page_config(
    page_title="Ferramentas Operacionais - COI",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


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
        use_container_width=True,
    ):
        st.switch_page("app.py")


st.title("🛠️ Ferramentas Operacionais")
st.caption("Selecione a ferramenta desejada:")
st.divider()


col1, col2, col3 = st.columns(3)


with col1:
    st.markdown("#### 📦 Gerador de Lotes")
    st.markdown("**Cancelamento de O.S.**")
    st.caption("Status: Ativo")

    if st.button(
        "Acessar Gerador de Lotes",
        type="primary",
        use_container_width=True,
        key="btn_gerador_lotes",
    ):
        st.switch_page(
            "pages/4_1_Gerador_Lotes_Cancelamento.py"
        )


with col2:
    st.markdown("#### 📊 Gerador de Painel")
    st.markdown("**Painéis Operacionais**")

    if st.session_state.get("perfil") == "admin":

        st.caption("Status: Ativo (Admin)")

        if st.button(
            "Acessar Gerador de Painel",
            type="primary",
            use_container_width=True,
            key="btn_gerador_painel",
        ):
            st.switch_page(
                "pages/4_2_Gerador_de_Painel.py"
            )

    else:

        st.caption("Status: Restrito")

        st.button(
            "Acessar Gerador de Painel",
            disabled=True,
            use_container_width=True,
            key="btn_gerador_painel_bloqueado",
        )

        st.markdown(
            "<p style='font-size:12px; color:gray;'>"
            "🔒 Restrito a administradores"
            "</p>",
            unsafe_allow_html=True
        )


with col3:
    st.markdown("#### 🃏 Cards Operacionais")
    st.markdown("**Cards e Indicadores**")
    st.caption("Status: Em desenvolvimento")

    st.button(
        "Em breve",
        disabled=True,
        use_container_width=True,
        key="btn_cards_operacionais",
    )
