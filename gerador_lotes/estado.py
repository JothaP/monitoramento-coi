import streamlit as st


# ============================================================
# BASES MANTIDAS DURANTE A SESSÃO
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
    """
    Inicializa todos os estados necessários para o HUB.

    As bases permanecem disponíveis durante toda a sessão
    do usuário e podem ser utilizadas por diferentes
    ferramentas da plataforma.
    """

    # --------------------------------------------------------
    # DATAFRAMES
    # --------------------------------------------------------

    for base in BASES:

        chave = f"df_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = None

    # --------------------------------------------------------
    # NOMES DOS ARQUIVOS
    # --------------------------------------------------------

    for base in BASES:

        chave = f"arquivos_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = []

    # --------------------------------------------------------
    # ASSINATURA DOS UPLOADS
    # --------------------------------------------------------

    for base in BASES:

        chave = f"assinatura_{base}"

        if chave not in st.session_state:
            st.session_state[chave] = None

    # --------------------------------------------------------
    # MODO OPERACIONAL
    #
    # API ou THE
    # --------------------------------------------------------

    if "modo_operacao" not in st.session_state:
        st.session_state.modo_operacao = None

    # --------------------------------------------------------
    # FERRAMENTA ATUAL
    # --------------------------------------------------------

    if "ferramenta_atual" not in st.session_state:
        st.session_state.ferramenta_atual = None

    # --------------------------------------------------------
    # RESULTADOS
    # --------------------------------------------------------

    if "df_resultado" not in st.session_state:
        st.session_state.df_resultado = None

    if "df_log" not in st.session_state:
        st.session_state.df_log = None

    if "nome_arquivo_resultado" not in st.session_state:
        st.session_state.nome_arquivo_resultado = None


# ============================================================
# ACESSAR BASE
# ============================================================

def obter_base(nome):

    return st.session_state.get(
        f"df_{nome}"
    )


# ============================================================
# VERIFICAR BASE
# ============================================================

def base_carregada(nome):

    df = obter_base(nome)

    return (
        df is not None
        and not df.empty
    )


# ============================================================
# DEFINIR BASE
# ============================================================

def definir_base(
    nome,
    dataframe,
    arquivos=None,
    assinatura=None
):

    st.session_state[f"df_{nome}"] = dataframe

    if arquivos is not None:

        st.session_state[
            f"arquivos_{nome}"
        ] = arquivos

    if assinatura is not None:

        st.session_state[
            f"assinatura_{nome}"
        ] = assinatura


# ============================================================
# DEFINIR MODO OPERACIONAL
# ============================================================

def definir_modo_operacao(modo):

    if modo not in ("API", "THE", None):

        raise ValueError(
            "Modo operacional inválido. "
            "Utilize 'API', 'THE' ou None."
        )

    st.session_state.modo_operacao = modo


# ============================================================
# OBTER MODO OPERACIONAL
# ============================================================

def obter_modo_operacao():

    return st.session_state.get(
        "modo_operacao"
    )


# ============================================================
# OBTER BASE OPERACIONAL ATIVA
# ============================================================

def obter_base_ativa():

    modo = obter_modo_operacao()

    if modo == "API":

        return obter_base("api")

    if modo == "THE":

        return obter_base("the")

    return None


# ============================================================
# VERIFICAR SE EXISTE BASE ATIVA
# ============================================================

def existe_base_ativa():

    df = obter_base_ativa()

    return (
        df is not None
        and not df.empty
    )


# ============================================================
# DEFINIR MODO AUTOMATICAMENTE
# ============================================================

def ajustar_modo_operacao():

    """
    Garante que o modo operacional sempre corresponda
    a uma base realmente carregada.

    Prioridade:
        1. mantém o modo atual se a base existir;
        2. API, se disponível;
        3. THE, se disponível;
        4. None.
    """

    modo_atual = obter_modo_operacao()

    if (
        modo_atual == "API"
        and base_carregada("api")
    ):
        return "API"

    if (
        modo_atual == "THE"
        and base_carregada("the")
    ):
        return "THE"

    if base_carregada("api"):

        st.session_state.modo_operacao = "API"

        return "API"

    if base_carregada("the"):

        st.session_state.modo_operacao = "THE"

        return "THE"

    st.session_state.modo_operacao = None

    return None


# ============================================================
# LIMPAR RESULTADO
# ============================================================

def limpar_resultado():

    st.session_state.df_resultado = None
    st.session_state.df_log = None
    st.session_state.nome_arquivo_resultado = None


# ============================================================
# LIMPAR UMA BASE
# ============================================================

def limpar_base(nome):

    if nome not in BASES:
        return

    st.session_state[
        f"df_{nome}"
    ] = None

    st.session_state[
        f"arquivos_{nome}"
    ] = []

    st.session_state[
        f"assinatura_{nome}"
    ] = None

    ajustar_modo_operacao()


# ============================================================
# LIMPAR TODAS AS BASES
# ============================================================

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

    limpar_resultado()

    st.session_state.ferramenta_atual = None
    st.session_state.modo_operacao = None


# ============================================================
# VOLTAR AO HUB
# ============================================================

def voltar_ao_hub():

    st.session_state.ferramenta_atual = None

    limpar_resultado()
