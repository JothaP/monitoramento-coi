import streamlit as st


# ============================================================
# CHAVES DAS BASES
# ============================================================

BASES = [
    "api",
    "the",
    "eventos",
    "servicos_api",
    "servicos_the",
    "lotes",
]


# ============================================================
# INICIALIZAÇÃO DO ESTADO
# ============================================================

def inicializar_estado():

    # --------------------------------------------------------
    # Bases carregadas
    # --------------------------------------------------------
    for base in BASES:
        chave = f"base_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = None

    # --------------------------------------------------------
    # Nomes dos arquivos carregados
    # --------------------------------------------------------
    for base in BASES:
        chave = f"arquivos_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = []

    # --------------------------------------------------------
    # Assinaturas dos uploads
    # Usadas para não processar novamente arquivos
    # que já foram carregados.
    # --------------------------------------------------------
    for base in BASES:
        chave = f"assinatura_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = None

    # --------------------------------------------------------
    # Ferramenta atualmente selecionada
    # --------------------------------------------------------
    if "ferramenta_atual" not in st.session_state:
        st.session_state.ferramenta_atual = None

    # --------------------------------------------------------
    # Resultado da ferramenta
    # --------------------------------------------------------
    if "resultado" not in st.session_state:
        st.session_state.resultado = None

    if "log_resultado" not in st.session_state:
        st.session_state.log_resultado = []

    if "nome_resultado" not in st.session_state:
        st.session_state.nome_resultado = None


# ============================================================
# ACESSO ÀS BASES
# ============================================================

def obter_base(nome):

    chave = f"base_{nome}"

    return st.session_state.get(chave)


def definir_base(nome, dataframe, arquivos=None, assinatura=None):

    st.session_state[f"base_{nome}"] = dataframe

    if arquivos is not None:
        st.session_state[f"arquivos_{nome}"] = arquivos

    if assinatura is not None:
        st.session_state[f"assinatura_{nome}"] = assinatura


# ============================================================
# VERIFICAÇÃO
# ============================================================

def base_carregada(nome):

    df = obter_base(nome)

    return df is not None and not df.empty


# ============================================================
# LIMPAR RESULTADO
# ============================================================

def limpar_resultado():

    st.session_state.resultado = None
    st.session_state.log_resultado = []
    st.session_state.nome_resultado = None


# ============================================================
# LIMPAR TODAS AS BASES
# ============================================================

def limpar_bases():

    for base in BASES:

        st.session_state[f"base_{base}"] = None
        st.session_state[f"arquivos_{base}"] = []
        st.session_state[f"assinatura_{base}"] = None

    limpar_resultado()

    st.session_state.ferramenta_atual = None


# ============================================================
# VOLTAR AO HUB
# ============================================================

def voltar_ao_hub():

    st.session_state.ferramenta_atual = None
    limpar_resultado()