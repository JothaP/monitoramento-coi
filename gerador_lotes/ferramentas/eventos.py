import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado


def render_eventos():
    st.title("📋 Análise de Eventos")

    st.caption(
        "Ferramenta para consulta, análise e tratamento da base de eventos."
    )

    st.divider()

    # ============================================================
    # VERIFICAÇÃO DA BASE
    # ============================================================

    if not base_carregada("eventos"):
        st.warning(
            "A base de Eventos ainda não foi carregada no Hub do "
            "Gerador de Lotes."
        )

        st.info(
            "Volte ao Hub, carregue a base de Eventos e depois "
            "acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_eventos_sem_base",
        ):
            st.session_state.ferramenta_atual = None
            limpar_resultado()
            st.rerun()

        st.stop()

    df = obter_base("eventos")

    # ============================================================
    # BASE SELECIONADA
    # ============================================================

    st.markdown("### 📊 Base de Eventos")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Base",
            "EVENTOS",
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
        "Os critérios e regras de análise dos eventos serão "
        "implementados na próxima etapa. Esta área está preparada "
        "para receber os filtros e parâmetros da ferramenta."
    )

    col_config_1, col_config_2 = st.columns(2)

    with col_config_1:

        st.multiselect(
            "Campos para análise",
            options=list(df.columns),
            default=[],
            key="eventos_campos_analise",
            help=(
                "Selecione os campos que serão utilizados "
                "posteriormente na análise."
            ),
        )

    with col_config_2:

        st.selectbox(
            "Tipo de análise",
            options=[
                "Análise de Eventos",
            ],
            key="eventos_tipo_analise",
        )

    st.divider()

    # ============================================================
    # ÁREA DE ANÁLISE
    # ============================================================

    st.markdown("### 🔍 Análise")

    if st.button(
        "🔍 Analisar Eventos",
        type="primary",
        use_container_width=True,
        key="btn_analisar_eventos",
    ):
        st.session_state["eventos_analisado"] = True

    # ============================================================
    # RESULTADO
    # ============================================================

    if st.session_state.get("eventos_analisado", False):

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
                "Eventos identificados",
                "—",
            )

        with col_resultado_3:
            st.metric(
                "Registros resultantes",
                "—",
            )

        st.markdown("#### Prévia dos registros")

        st.info(
            "A análise dos eventos será implementada na próxima "
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
                key="btn_exportar_eventos",
            )

        with col_acao_2:

            if st.button(
                "🗑️ Limpar análise",
                use_container_width=True,
                key="btn_limpar_eventos",
            ):
                st.session_state["eventos_analisado"] = False
                st.session_state["eventos_campos_analise"] = []
                st.rerun()

    # ============================================================
    # VOLTAR
    # ============================================================

    st.divider()

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_eventos",
    ):
        st.session_state.ferramenta_atual = None
        limpar_resultado()
        st.session_state["eventos_analisado"] = False
        st.rerun()
