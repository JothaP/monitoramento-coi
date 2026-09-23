import streamlit as st

from auth import verificar_autenticacao

from gerador_lotes import (
    inicializar_estado,
    base_carregada,
    obter_base,
    limpar_base,
    limpar_bases,
    processar_upload_multiplo,
)

from gerador_lotes.ferramentas import (
    render_filtragem,
    render_duplicidade,
    render_servicos,
    render_eventos,
    render_lotes,
    render_lista_rapida,
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Gerador de Lotes - COI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ESTILO
# ============================================================

st.markdown(
    """
    <style>

    /* Oculta navegação padrão */
    [data-testid="stSidebarNav"] {
        display: none !important;
    }

    /* Espaçamento geral */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Títulos */
    h1 {
        margin-bottom: 0.2rem;
    }

    h2, h3 {
        margin-top: 0.5rem;
    }

    /* Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }

    /* Texto pequeno */
    .card-status {
        font-size: 0.82rem;
        margin-top: -0.15rem;
        margin-bottom: 0.45rem;
    }

    .card-registros {
        font-size: 0.78rem;
        color: #6b7280;
        margin-bottom: 0.35rem;
    }

    /* Reduz espaço entre elementos */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.45rem;
    }

    /* Separador */
    hr {
        margin-top: 1.2rem;
        margin-bottom: 1.2rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")

    if st.button(
        "Ir para o Login",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# ESTADO
# ============================================================

inicializar_estado()


# ============================================================
# CONFIGURAÇÃO DAS BASES
# ============================================================

BASES_CONFIG = [
    {
        "nome": "API",
        "chave": "api",
        "icone": "🔵",
        "descricao": "Base principal de API.",
    },
    {
        "nome": "THE",
        "chave": "the",
        "icone": "🟢",
        "descricao": "Base principal de THE.",
    },
    {
        "nome": "Serviços API",
        "chave": "servicos_api",
        "icone": "🔵",
        "descricao": "Serviços vinculados à API.",
    },
    {
        "nome": "Serviços THE",
        "chave": "servicos_the",
        "icone": "🟢",
        "descricao": "Serviços vinculados ao THE.",
    },
    {
        "nome": "Eventos",
        "chave": "eventos",
        "icone": "📋",
        "descricao": "Base de eventos operacionais.",
    },
    {
        "nome": "Lotes",
        "chave": "lotes",
        "icone": "📦",
        "descricao": "Base de lotes operacionais.",
    },
]


# ============================================================
# CONFIGURAÇÃO DAS FERRAMENTAS
# ============================================================

FERRAMENTAS = [
    {
        "nome": "Filtragem",
        "icone": "🔎",
        "descricao": "Filtragem e geração de lotes de cancelamento.",
        "funcao": render_filtragem,
    },
    {
        "nome": "Duplicidade",
        "icone": "♻️",
        "descricao": "Análise de registros duplicados.",
        "funcao": render_duplicidade,
    },
    {
        "nome": "Serviços",
        "icone": "🛠️",
        "descricao": "Análise e tratamento de serviços.",
        "funcao": render_servicos,
    },
    {
        "nome": "Eventos",
        "icone": "📋",
        "descricao": "Consulta e análise de eventos.",
        "funcao": render_eventos,
    },
    {
        "nome": "Lotes",
        "icone": "📦",
        "descricao": "Consulta e análise de lotes.",
        "funcao": render_lotes,
    },
    {
        "nome": "Lista Rápida",
        "icone": "⚡",
        "descricao": "Operações rápidas sobre as bases.",
        "funcao": render_lista_rapida,
    },
]


# ============================================================
# ROTEAMENTO DAS FERRAMENTAS
# ============================================================

ferramenta_atual = st.session_state.get("ferramenta_atual")

if ferramenta_atual == "filtragem":
    render_filtragem()
    st.stop()

if ferramenta_atual == "duplicidade":
    render_duplicidade()
    st.stop()

if ferramenta_atual == "servicos":
    render_servicos()
    st.stop()

if ferramenta_atual == "eventos":
    render_eventos()
    st.stop()

if ferramenta_atual == "lotes":
    render_lotes()
    st.stop()

if ferramenta_atual == "lista_rapida":
    render_lista_rapida()
    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("### 📦 Gerador de Lotes")

    st.caption(
        f"Usuário: **{st.session_state.get('usuario_logado', '')}**"
    )

    st.caption(
        f"Perfil: **{st.session_state.get('perfil', '').upper()}**"
    )

    st.divider()

    if st.button(
        "🛠️ Ferramentas Operacionais",
        use_container_width=True,
    ):
        st.switch_page("pages/4_Ferramentas_Operacionais.py")

    if st.button(
        "🏠 Menu Principal",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.divider()

    if st.button(
        "🗑️ Limpar todas as bases",
        use_container_width=True,
    ):
        limpar_bases()
        st.rerun()


# ============================================================
# CABEÇALHO
# ============================================================

st.title("📦 Gerador de Lotes")

st.caption(
    "Gerencie as bases operacionais e acesse as ferramentas do módulo."
)


# ============================================================
# RESUMO
# ============================================================

total_bases_carregadas = sum(
    1 for base in BASES_CONFIG
    if base_carregada(base["chave"])
)

st.markdown(
    f"**Bases carregadas:** {total_bases_carregadas} de {len(BASES_CONFIG)}"
)


# ============================================================
# BASES DE DADOS
# ============================================================

st.markdown("### 📁 Bases de Dados")

colunas_bases = st.columns(3)

for indice, base in enumerate(BASES_CONFIG):

    coluna = colunas_bases[indice % 3]

    chave = base["chave"]
    carregada = base_carregada(chave)
    df = obter_base(chave)

    with coluna:

        with st.container(border=True):

            # ------------------------------------------------
            # TÍTULO
            # ------------------------------------------------

            st.markdown(
                f"#### {base['icone']} {base['nome']}"
            )

            st.caption(base["descricao"])

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            if carregada:

                quantidade = len(df)

                st.markdown(
                    '<div class="card-status">🟢 <strong>Carregada</strong></div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div class="card-registros">'
                    f'{quantidade:,}'.replace(",", ".")
                    + " registros"
                    "</div>",
                    unsafe_allow_html=True,
                )

            else:

                st.markdown(
                    '<div class="card-status">⚪ <strong>Não carregada</strong></div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    '<div class="card-registros">&nbsp;</div>',
                    unsafe_allow_html=True,
                )

            # ------------------------------------------------
            # UPLOAD
            # ------------------------------------------------

            versao = st.session_state.get(
                f"versao_upload_{chave}",
                0,
            )

            arquivos = st.file_uploader(
                "Upload",
                type=["xlsx", "xlsm"],
                accept_multiple_files=True,
                key=f"upload_{chave}_{versao}",
                label_visibility="collapsed",
                help=(
                    f"Carregar arquivo(s) da base {base['nome']}. "
                    "Formatos aceitos: XLSX e XLSM."
                ),
            )

            if arquivos:

                processado = processar_upload_multiplo(
                    chave,
                    arquivos,
                )

                if processado:
                    st.rerun()

            # ------------------------------------------------
            # ARQUIVOS / LIMPAR
            # ------------------------------------------------

            arquivos_carregados = st.session_state.get(
                f"arquivos_{chave}",
                [],
            )

            if arquivos_carregados:

                st.caption(
                    f"📎 {len(arquivos_carregados)} arquivo(s)"
                )

                if st.button(
                    "Limpar",
                    key=f"limpar_base_{chave}",
                    use_container_width=True,
                ):
                    limpar_base(chave)
                    st.rerun()


# ============================================================
# FERRAMENTAS
# ============================================================

st.markdown("### 🛠️ Ferramentas Operacionais")

st.caption(
    "Selecione uma ferramenta para iniciar a operação."
)

colunas_ferramentas = st.columns(3)

for indice, ferramenta in enumerate(FERRAMENTAS):

    coluna = colunas_ferramentas[indice % 3]

    with coluna:

        with st.container(border=True):

            st.markdown(
                f"#### {ferramenta['icone']} {ferramenta['nome']}"
            )

            st.caption(ferramenta["descricao"])

            chave_ferramenta = (
                ferramenta["nome"]
                .lower()
                .replace(" ", "_")
            )

            if st.button(
                "Acessar",
                key=f"btn_ferramenta_{chave_ferramenta}",
                type="primary",
                use_container_width=True,
            ):

                mapa_ferramentas = {
                    "Filtragem": "filtragem",
                    "Duplicidade": "duplicidade",
                    "Serviços": "servicos",
                    "Eventos": "eventos",
                    "Lotes": "lotes",
                    "Lista Rápida": "lista_rapida",
                }

                st.session_state.ferramenta_atual = (
                    mapa_ferramentas[ferramenta["nome"]]
                )

                st.rerun()
