import streamlit as st

from ..estado import base_carregada, obter_base


def selecionar_modo_api_the(
    key="modo_api_the",
    titulo="Base de operação",
    limpar_resultado_callback=None,
):
    modos_disponiveis = []

    if base_carregada("api"):
        modos_disponiveis.append("API")

    if base_carregada("the"):
        modos_disponiveis.append("THE")

    if not modos_disponiveis:
        st.warning(
            "Nenhuma base API ou THE está carregada no Hub do Gerador de Lotes."
        )
        return None, None

    modo_atual = st.session_state.get(
        f"{key}_valor",
        modos_disponiveis[0],
    )

    if modo_atual not in modos_disponiveis:
        modo_atual = modos_disponiveis[0]

    indice = modos_disponiveis.index(modo_atual)

    modo = st.radio(
        titulo,
        modos_disponiveis,
        index=indice,
        horizontal=True,
        key=key,
    )

    if st.session_state.get(f"{key}_valor") != modo:

        st.session_state[f"{key}_valor"] = modo

        if limpar_resultado_callback:
            limpar_resultado_callback()

        st.rerun()

    nome_base = "api" if modo == "API" else "the"

    df = obter_base(nome_base)

    return modo, df