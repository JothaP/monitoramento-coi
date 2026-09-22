```python
import streamlit as st

from ..estado import (
    obter_base,
    base_carregada,
    limpar_resultado,
)
from .componentes import selecionar_modo_api_the


def render_duplicidade():
    # ============================================================
    # CABEÇALHO
    # ============================================================

    st.title("♻️ Análise de Duplicidade")
    st.caption(
        "Estrutura inicial da ferramenta para análise de registros duplicados."
    )

    st.divider()

    # ============================================================
    # SELEÇÃO DA BASE
    # ============================================================

    modo, df = selecionar_modo_api_the(
        key="duplicidade_modo_api_the",
        titulo="Base de operação",
        limpar_resultado_callback=limpar_resultado,
    )

    if modo is None or df is None:
        st.stop()

    # ============================================================
    # INFORMAÇÕES DA BASE
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
    # CONFIGURAÇÃO DA ANÁLISE
    # ============================================================

    st.markdown("### ⚙️ Configuração da análise")

    st.info(
        "A definição dos critérios de duplicidade será implementada "
        "posteriormente. Neste momento, esta área está preparada "
        "para a configuração da ferramenta."
    )

    col_config_1, col_config_2 = st.columns(2)

    with col_config_1:
        st.multiselect(
            "Campos para análise de duplicidade",
            options=list(df.columns),
            default=[],
            key="duplicidade_campos",
            help="Os critérios de comparação serão definidos posteriormente.",
        )

    with col_config_2:
        st.selectbox(
            "Tipo de análise",
            options=[
                "Análise de duplicidade",
            ],
            key="duplicidade_tipo_analise",
        )

    st.divider()

    # ============================================================
    # AÇÃO PRINCIPAL
    # ============================================================

    st.markdown("### 🔍 Análise")

    if st.button(
        "🔍 Analisar Duplicidades",
        type="primary",
        use_container_width=True,
        key="btn_analisar_duplicidades",
    ):
        st.session_state["duplicidade_analisada"] = True

    # ============================================================
    # RESULTADOS
    # ============================================================

    if st.session_state.get("duplicidade_analisada", False):

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
                "Possíveis duplicidades",
                "—",
            )

        with col_resultado_3:
            st.metric(
                "Registros únicos",
                "—",
            )

        st.markdown("#### Registros identificados")

        st.info(
            "A identificação e apresentação das duplicidades "
            "serão implementadas na próxima etapa."
        )

        st.dataframe(
            df.head(100),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # ========================================================
        # AÇÕES DO RESULTADO
        # ========================================================

        st.markdown("### 📤 Ações")

        col_acao_1, col_acao_2 = st.columns(2)

        with col_acao_1:
            st.button(
                "📥 Exportar resultado",
                use_container_width=True,
                disabled=True,
                key="btn_exportar_duplicidade",
            )

        with col_acao_2:
            if st.button(
                "🗑️ Limpar análise",
                use_container_width=True,
                key="btn_limpar_duplicidade",
            ):
                st.session_state["duplicidade_analisada"] = False
                st.session_state["duplicidade_campos"] = []
                st.rerun()

    st.divider()

    # ============================================================
    # VOLTAR
    # ============================================================

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_duplicidade",
    ):
        st.session_state.ferramenta_atual = None
        limpar_resultado()
        st.session_state["duplicidade_analisada"] = False
        st.rerun()
```
