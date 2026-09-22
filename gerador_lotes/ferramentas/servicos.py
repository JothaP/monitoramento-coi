import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado


def render_servicos():
    st.title("🛠️ Análise de Serviços")

    st.caption(
        "Ferramenta para consulta, análise e tratamento das bases de serviços."
    )

    st.divider()

    # ============================================================
    # SELEÇÃO DA BASE
    # ============================================================

    bases_disponiveis = []

    if base_carregada("servicos_api"):
        bases_disponiveis.append("API")

    if base_carregada("servicos_the"):
        bases_disponiveis.append("THE")

    if not bases_disponiveis:

        st.warning(
            "Nenhuma base de Serviços está carregada no Hub do "
            "Gerador de Lotes."
        )

        st.info(
            "Volte ao Hub, carregue a base Serviços API ou Serviços THE "
            "e depois acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_servicos_sem_base",
        ):
            st.session_state.ferramenta_atual = None
            limpar_resultado()
            st.rerun()

        st.stop()

    modo_anterior = st.session_state.get(
        "servicos_modo_api_the",
        bases_disponiveis[0],
    )

    if modo_anterior not in bases_disponiveis:
        modo_anterior = bases_disponiveis[0]

    modo = st.radio(
        "Base de operação",
        bases_disponiveis,
        index=bases_disponiveis.index(modo_anterior),
        horizontal=True,
        key="servicos_modo_api_the",
    )

    nome_base = (
        "servicos_api"
        if modo == "API"
        else "servicos_the"
    )

    df = obter_base(nome_base)

    if df is None or df.empty:
        st.warning(
            f"A base Serviços {modo} não possui dados disponíveis."
        )
        st.stop()

    st.divider()

    # ============================================================
    # BASE SELECIONADA
    # ============================================================

    st.markdown("### 📊 Base selecionada")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Base",
            f"Serviços {modo}",
        )

    with col2:
        st.metric(
            "Registros",
            f"{len(df):,}".replace(",", "."),
        )

    with col3:
        st.metric(
            "Colunas",
            f"{len(df.columns):,}".replace(",", "."),
        )

    st.divider()

    # ============================================================
    # CONFIGURAÇÃO
    # ============================================================

    st.markdown("### ⚙️ Configuração da análise")

    st.info(
        "Os critérios e regras de análise dos serviços serão "
        "implementados na próxima etapa. Esta área está preparada "
        "para receber os filtros e parâmetros da ferramenta."
    )

    col_config_1, col_config_2 = st.columns(2)

    with col_config_1:

        st.multiselect(
            "Campos para análise",
            options=list(df.columns),
            default=[],
            key="servicos_campos_analise",
            help=(
                "Selecione os campos que serão utilizados "
                "posteriormente na análise."
            ),
        )

    with col_config_2:

        st.selectbox(
            "Tipo de análise",
            options=[
                "Análise de Serviços",
            ],
            key="servicos_tipo_analise",
        )

    st.divider()

    # ============================================================
    # ANÁLISE
    # ============================================================

    st.markdown("### 🔍 Análise")

    if st.button(
        "🔍 Analisar Serviços",
        type="primary",
        use_container_width=True,
        key="btn_analisar_servicos",
    ):
        st.session_state["servicos_analisado"] = True

    # ============================================================
    # RESULTADO
    # ============================================================

    if st.session_state.get("servicos_analisado", False):

        st.divider()

        st.markdown("### 📋 Resultado da análise")

        col_resultado_1, col_resultado_2, col_resultado_3 = st.columns(3)

        with col_resultado_1:
            st.metric(
                "Registros analisados",
                f"{len(df):,}".replace(",", "."),
            )

        with col_resultado_2:
            st.metric(
                "Serviços identificados",
                "—",
            )

        with col_resultado_3:
            st.metric(
                "Registros resultantes",
                "—",
            )

        st.markdown("#### Prévia dos registros")

        st.info(
            "A análise dos serviços será implementada na próxima "
            "etapa. Por enquanto, esta área apresenta somente "
            "a estrutura da ferramenta."
        )

        st.dataframe(
            df.head(100),
            use_container_width=True,
            hide_index=True,
        )

        # ========================================================
        # AÇÕES
        # ========================================================

        st.divider()

        st.markdown("### 📤 Ações")

        col_acao_1, col_acao_2 = st.columns(2)

        with col_acao_1:

            st.button(
                "📥 Exportar resultado",
                use_container_width=True,
                disabled=True,
                key="btn_exportar_servicos",
            )

        with col_acao_2:

            if st.button(
                "🗑️ Limpar análise",
                use_container_width=True,
                key="btn_limpar_servicos",
            ):
                st.session_state["servicos_analisado"] = False
                st.session_state["servicos_campos_analise"] = []
                st.rerun()

    # ============================================================
    # VOLTAR
    # ============================================================

    st.divider()

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_servicos",
    ):
        st.session_state.ferramenta_atual = None
        limpar_resultado()
        st.session_state["servicos_analisado"] = False
        st.rerun()
