import streamlit as st

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Ferramentas Operacionais - COI",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ESTILO
# ============================================================

st.markdown(
    """
    <style>

        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .main-title {
            font-size: 30px;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 2px;
        }

        .main-subtitle {
            font-size: 15px;
            color: #64748B;
            margin-bottom: 20px;
        }

        .tool-card {
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 12px;
            padding: 22px;
            min-height: 230px;
        }

        .tool-title {
            font-size: 18px;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 6px;
        }

        .tool-description {
            font-size: 14px;
            color: #475569;
            min-height: 45px;
            margin-bottom: 14px;
        }

        .tool-status {
            font-size: 13px;
            color: #64748B;
            margin-bottom: 12px;
        }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():

    st.warning(
        "Sessão não iniciada ou expirada."
    )

    if st.button(
        "Ir para o Login",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### 🛠️ Ferramentas Operacionais"
    )

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


# ============================================================
# CABEÇALHO
# ============================================================

st.markdown(
    '<div class="main-title">'
    "Ferramentas Operacionais"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="main-subtitle">'
    "Selecione a ferramenta operacional desejada."
    "</div>",
    unsafe_allow_html=True,
)

st.divider()


# ============================================================
# FERRAMENTAS
# ============================================================

col1, col2, col3 = st.columns(3)


# ============================================================
# 4.1 — GERADOR DE LOTES
# ============================================================

with col1:

    st.markdown(
        """
        <div class="tool-card">
            <div class="tool-title">
                📦 Gerador de Lotes
            </div>

            <div class="tool-description">
                Geração de lotes para processos de
                cancelamento de Ordens de Serviço.
            </div>

            <div class="tool-status">
                Status: <strong>Ativo</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")

    if st.button(
        "Acessar Gerador de Lotes",
        type="primary",
        use_container_width=True,
        key="btn_gerador_lotes",
    ):
        st.switch_page(
            "pages/4_1_Gerador_Lotes_Cancelamento.py"
        )


# ============================================================
# 4.2 — GERADOR DE PAINEL
# ============================================================

with col2:

    st.markdown(
        """
        <div class="tool-card">
            <div class="tool-title">
                📊 Gerador de Painel
            </div>

            <div class="tool-description">
                Geração de painéis e análises operacionais
                a partir das bases disponibilizadas.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")

    if st.session_state.get("perfil") == "admin":

        st.caption(
            "Status: Ativo (Admin)"
        )

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

        st.caption(
            "Status: Restrito"
        )

        st.button(
            "Acessar Gerador de Painel",
            disabled=True,
            use_container_width=True,
            key="btn_gerador_painel_bloqueado",
        )

        st.markdown(
            """
            <p style="
                font-size:12px;
                color:gray;
                margin-top:4px;
            ">
                🔒 Restrito a administradores
            </p>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# 4.3 — CARDS OPERACIONAIS
# ============================================================

with col3:

    st.markdown(
        """
        <div class="tool-card">
            <div class="tool-title">
                🃏 Cards Operacionais
            </div>

            <div class="tool-description">
                Geração de cards e indicadores executivos
                para acompanhamento operacional.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("")

    if st.session_state.get("perfil") == "admin":

        st.caption(
            "Status: Em desenvolvimento (Admin)"
        )

        if st.button(
            "Acessar Cards Operacionais",
            type="primary",
            use_container_width=True,
            key="btn_cards_operacionais",
        ):
            st.switch_page(
                "pages/4_3_Cards_Operacionais.py"
            )

    else:

        st.caption(
            "Status: Em desenvolvimento"
        )

        st.button(
            "Acessar Cards Operacionais",
            disabled=True,
            use_container_width=True,
            key="btn_cards_operacionais_bloqueado",
        )

        st.markdown(
            """
            <p style="
                font-size:12px;
                color:gray;
                margin-top:4px;
            ">
                🔒 Restrito a administradores
            </p>
            """,
            unsafe_allow_html=True,
        )
