import streamlit as st


# ============================================================
# BASES COMPARTILHADAS DA PLATAFORMA
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
    Inicializa todas as bases compartilhadas da sessão.

    As bases permanecem disponíveis durante toda a sessão
    do usuário e não são apagadas ao trocar de ferramenta.
    """

    for base in BASES:

        chave_df = f"df_{base}"
        chave_arquivos = f"arquivos_{base}"

        if chave_df not in st.session_state:
            st.session_state[chave_df] = None

        if chave_arquivos not in st.session_state:
            st.session_state[chave_arquivos] = []

    # Assinaturas dos uploads.
    if "assinaturas_upload" not in st.session_state:
        st.session_state["assinaturas_upload"] = {}

    # Ferramenta atualmente aberta.
    if "ferramenta_atual" not in st.session_state:
        st.session_state["ferramenta_atual"] = None


# ============================================================
# ACESSO ÀS BASES
# ============================================================

def obter_base(nome_base):
    """
    Retorna o DataFrame da base solicitada.
    """

    inicializar_estado()

    nome_base = str(nome_base).strip().lower()

    if nome_base not in BASES:
        raise ValueError(
            f"Base inválida: {nome_base}. "
            f"Bases disponíveis: {', '.join(BASES)}."
        )

    return st.session_state.get(f"df_{nome_base}")


def base_carregada(nome_base):
    """
    Verifica se uma base existe e possui registros.
    """

    df = obter_base(nome_base)

    return df is not None and not df.empty


# ============================================================
# DEFINIÇÃO DAS BASES
# ============================================================

def definir_base(nome_base, df, arquivos=None):
    """
    Armazena uma base no estado compartilhado da sessão.

    Esta função NÃO interfere nas demais bases.
    """

    inicializar_estado()

    nome_base = str(nome_base).strip().lower()

    if nome_base not in BASES:
        raise ValueError(
            f"Base inválida: {nome_base}. "
            f"Bases disponíveis: {', '.join(BASES)}."
        )

    st.session_state[f"df_{nome_base}"] = df

    if arquivos is not None:
        st.session_state[f"arquivos_{nome_base}"] = arquivos


# ============================================================
# LIMPEZA DE RESULTADOS
# ============================================================

def limpar_resultado():
    """
    Limpa somente resultados temporários das ferramentas.

    IMPORTANTE:
    Esta função NÃO remove nenhuma base carregada.

    As bases df_api, df_the, df_eventos, servicos_api,
    servicos_the e lotes permanecem disponíveis.
    """

    chaves_resultado = [
        "df_resultado",
        "df_log",
        "nome_arquivo_resultado",
        "resultado",
        "log_resultado",
    ]

    for chave in chaves_resultado:
        if chave in st.session_state:
            st.session_state[chave] = None

    # Estados específicos do Gerador de Lotes
    chaves_lotes = [
        "lote_gerado",
        "lote_resultado",
        "lote_log",
        "lote_nome_arquivo",
    ]

    for chave in chaves_lotes:
        if chave in st.session_state:
            st.session_state[chave] = None


# ============================================================
# LIMPEZA COMPLETA DAS BASES
# ============================================================

def limpar_bases():
    """
    Remove explicitamente todas as bases carregadas.

    Esta função deve ser chamada SOMENTE quando o usuário
    realmente desejar encerrar/limpar os dados da sessão.
    """

    inicializar_estado()

    for base in BASES:
        st.session_state[f"df_{base}"] = None
        st.session_state[f"arquivos_{base}"] = []

    st.session_state["assinaturas_upload"] = {}


# ============================================================
# RETORNO AO HUB
# ============================================================

def voltar_ao_hub():
    """
    Retorna ao Hub Central sem apagar as bases carregadas.
    """

    inicializar_estado()

    st.session_state["ferramenta_atual"] = None
