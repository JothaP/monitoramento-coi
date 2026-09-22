import streamlit as st


BASES = [
    "api",
    "the",
    "servicos_api",
    "servicos_the",
    "eventos",
    "lotes",
]


def inicializar_estado():

    for base in BASES:

        if f"df_{base}" not in st.session_state:
            st.session_state[f"df_{base}"] = None

        if f"arquivos_{base}" not in st.session_state:
            st.session_state[f"arquivos_{base}"] = []

        if f"assinatura_{base}" not in st.session_state:
            st.session_state[f"assinatura_{base}"] = None

        if f"versao_upload_{base}" not in st.session_state:
            st.session_state[f"versao_upload_{base}"] = 0

    if "ferramenta_atual" not in st.session_state:
        st.session_state.ferramenta_atual = None

    if "df_resultado" not in st.session_state:
        st.session_state.df_resultado = None

    if "df_resultado_lote" not in st.session_state:
        st.session_state.df_resultado_lote = None

    if "df_log" not in st.session_state:
        st.session_state.df_log = None

    if "nome_arquivo_resultado" not in st.session_state:
        st.session_state.nome_arquivo_resultado = None


def obter_base(nome):
    return st.session_state.get(f"df_{nome}")


def base_carregada(nome):

    df = obter_base(nome)

    return (
        df is not None
        and not df.empty
    )


def definir_base(
    nome,
    dataframe,
    arquivos=None,
    assinatura=None,
):

    if nome not in BASES:
        raise ValueError(
            f"Base desconhecida: {nome}"
        )

    st.session_state[f"df_{nome}"] = dataframe

    if arquivos is not None:
        st.session_state[f"arquivos_{nome}"] = arquivos

    if assinatura is not None:
        st.session_state[f"assinatura_{nome}"] = assinatura


def limpar_base(nome):

    if nome not in BASES:
        return

    st.session_state[f"df_{nome}"] = None
    st.session_state[f"arquivos_{nome}"] = []
    st.session_state[f"assinatura_{nome}"] = None

    st.session_state[
        f"versao_upload_{nome}"
    ] += 1


def limpar_resultado():

    st.session_state.df_resultado = None
    st.session_state.df_resultado_lote = None
    st.session_state.df_log = None
    st.session_state.nome_arquivo_resultado = None


def limpar_bases():

    for base in BASES:

        st.session_state[
            f"df_{base}"
        ] = None

        st.session_state[
            f"arquivos_{base}"
        ] = []

        st.session_state[
            f"assinatura_{base}"
        ] = None

        st.session_state[
            f"versao_upload_{base}"
        ] += 1

    limpar_resultado()

    st.session_state.ferramenta_atual = None


def voltar_ao_hub():

    st.session_state.ferramenta_atual = None

    limpar_resultado()