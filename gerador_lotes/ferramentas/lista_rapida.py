import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado


def render_lista_rapida():
    st.title("⚡ Lista Rápida")

    st.caption(
        "Ferramenta para geração rápida de listas a partir das bases "
        "carregadas no Hub."
    )

    st.divider()

    # ============================================================
    # SELEÇÃO DA BASE
    # ============================================================

    bases_disponiveis = []

    if base_carregada("api"):
        bases_disponiveis.append("API")

    if base_carregada("the"):
        bases_disponiveis.append("THE")

    if not bases_disponiveis:
        st.warning(
            "Nenhuma base API ou THE está carregada no Hub do "
            "Gerador de Lotes."
        )

        st.info(
            "Volte ao Hub, carregue uma base API ou THE e depois "
            "acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lista_rapida_sem_base",
        ):
            st.session_state.ferramenta_atual = None
            limpar_resultado()
            st.rerun()

        st.stop()

    modo_anterior = st.session_state.get(
        "lista_rapida_modo_api_the",
        bases_disponiveis[0],
    )

    if modo_anterior not in bases_disponiveis:
        modo_anterior = bases_disponiveis[0]

    modo = st.radio(
        "Base de operação",
        bases_disponiveis,
        index=bases_disponiveis.index(modo_anterior),
        horizontal=True,
        key="lista_rapida_modo_api_the",
    )

    nome_base = "api" if modo == "API" else "the"

    df = obter_base(nome_base)

    if df is None or df.empty:
        st.warning(
            f"A base {modo} não possui dados disponíveis."
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
            modo,
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

    st.markdown("### ⚙️ Configuração da lista")

    st.info(
        "Os critérios e campos da Lista Rápida serão definidos "
        "na próxima etapa. Esta área está preparada para receber "
        "a configuração da ferramenta."
    )

    col_config_1, col_config_2 = st.columns(2)

    with col_config_1:

        st.multiselect(
            "Campos para composição da lista",
            options=list(df.columns),
            default=[],
            key="lista_rapida_campos",
            help=(
                "Selecione os campos que serão utilizados "
                "posteriormente na composição da lista."
            ),
        )

    with col_config_2:

        st.selectbox(
            "Tipo de lista",
            options=[
                "Lista Rápida",
            ],
            key="lista_rapida_tipo",
        )

    st.divider()

    # ============================================================
    # GERAÇÃO
    # ============================================================

    st.markdown("### ⚡ Gerar lista")

    if st.button(
        "⚡ Gerar Lista Rápida",
        type="primary",
        use_container_width=True,
        key="btn_gerar_lista_rapida",
    ):
        st.session_state["lista_rapida_gerada"] = True

    # ============================================================
    # RESULTADO
    # ============================================================

    if st.session_state.get("lista_rapida_gerada", False):

        st.divider()

        st.markdown("### 📋 Resultado")

        col_resultado_1, col_resultado_2, col_resultado_3 = st.columns(3)

        with col_resultado_1:
            st.metric(
                "Registros analisados",
                f"{len(df):,}".replace(",", "."),
            )

        with col_resultado_2:
            st.metric(
                "Itens na lista",
                "—",
            )

        with col_resultado_3:
            st.metric(
                "Registros resultantes",
                "—",
            )

        st.markdown("#### Prévia da lista")

        st.info(
            "A lógica de geração da Lista Rápida será implementada "
            "na próxima etapa. Por enquanto, esta área apresenta "
            "somente a estrutura da ferramenta."
        )

        st.dataframe(
            df.head(100),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # ========================================================
        # AÇÕES
        # ========================================================

        st.markdown("### 📤 Ações")

        col_acao_1, col_acao_2 = st.columns(2)

        with col_acao_1:

            st.button(
                "📥 Exportar lista",
                use_container_width=True,
                disabled=True,
                key="btn_exportar_lista_rapida",
            )

        with col_acao_2:

            if st.button(
                "🗑️ Limpar lista",
                use_container_width=True,
                key="btn_limpar_lista_rapida",
            ):
                st.session_state["lista_rapida_gerada"] = False
                st.session_state["lista_rapida_campos"] = []
                st.rerun()

    # ============================================================
    # VOLTAR
    # ============================================================

    st.divider()

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_lista_rapida",
    ):
        st.session_state.ferramenta_atual = None
        limpar_resultado()
        st.session_state["lista_rapida_gerada"] = False
        st.rerun()
