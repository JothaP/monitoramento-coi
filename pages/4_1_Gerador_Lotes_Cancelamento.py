import streamlit as st

from auth import verificar_autenticacao

from gerador_lotes import (
    inicializar_estado,
    obter_base,
    base_carregada,
    limpar_base,
    limpar_bases,
)

from gerador_lotes.carregamento import processar_upload_multiplo

from gerador_lotes.ferramentas.filtragem import render_filtragem
from gerador_lotes.ferramentas.duplicidade import render_duplicidade


st.set_page_config(
    page_title="Gerador de Lotes - COI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


inicializar_estado()


ferramenta_atual = st.session_state.get("ferramenta_atual")


if ferramenta_atual == "filtragem":
    render_filtragem()
    st.stop()


if ferramenta_atual == "duplicidade":
    render_duplicidade()
    st.stop()


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
        "⬅️ Voltar às Ferramentas",
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


st.title("📦 Gerador de Lotes")

st.caption(
    "Hub central para carregamento e gerenciamento das bases "
    "utilizadas pelas ferramentas operacionais."
)

st.divider()


# ============================================================
# BASES
# ============================================================

st.markdown("## 🗂️ Bases de Dados")


bases = [
    (
        "api",
        "🔵 API",
        "Base principal de API.",
    ),
    (
        "the",
        "🟢 THE",
        "Base principal de THE.",
    ),
    (
        "servicos_api",
        "🔧 Serviços API",
        "Base de serviços relacionados à API.",
    ),
    (
        "servicos_the",
        "🔧 Serviços THE",
        "Base de serviços relacionados à THE.",
    ),
    (
        "eventos",
        "📋 Eventos",
        "Base de eventos operacionais.",
    ),
    (
        "lotes",
        "📦 Lotes",
        "Base de lotes.",
    ),
]


for nome_base, titulo_base, descricao_base in bases:

    st.markdown(f"### {titulo_base}")

    st.caption(descricao_base)

    versao = st.session_state.get(
        f"versao_upload_{nome_base}",
        0,
    )

    arquivos = st.file_uploader(
        f"Carregar arquivo(s) — {titulo_base}",
        type=["xlsx", "xlsm"],
        accept_multiple_files=True,
        key=f"upload_{nome_base}_{versao}",
    )

    if arquivos:

        try:

            processar_upload_multiplo(
                nome_base,
                arquivos,
            )

        except Exception as erro:

            st.error(
                f"Erro ao carregar a base {titulo_base}: {erro}"
            )

    if base_carregada(nome_base):

        df = obter_base(nome_base)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.success("Carregada")

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

        with col4:

            arquivos_carregados = st.session_state.get(
                f"arquivos_{nome_base}",
                [],
            )

            st.metric(
                "Arquivos",
                len(arquivos_carregados),
            )

        arquivos_carregados = st.session_state.get(
            f"arquivos_{nome_base}",
            [],
        )

        if arquivos_carregados:

            st.caption(
                "Arquivo(s): "
                + ", ".join(arquivos_carregados)
            )

        if st.button(
            f"Limpar {titulo_base}",
            key=f"limpar_{nome_base}",
        ):

            limpar_base(nome_base)

            st.rerun()

    else:

        st.info("Nenhum arquivo carregado.")

    st.divider()


# ============================================================
# FERRAMENTAS
# ============================================================

st.markdown("## 🛠️ Ferramentas")

st.caption(
    "As ferramentas utilizam as bases carregadas acima."
)


col1, col2, col3 = st.columns(3)


# ============================================================
# FILTRAGEM
# ============================================================

with col1:

    st.markdown("### 🔎 Filtragem")

    st.caption(
        "Filtragem e preparação de registros."
    )

    pode_filtrar = (
        base_carregada("api")
        or base_carregada("the")
    )

    if st.button(
        "Acessar Filtragem",
        type="primary",
        use_container_width=True,
        disabled=not pode_filtrar,
        key="btn_acessar_filtragem",
    ):

        st.session_state.ferramenta_atual = "filtragem"

        st.rerun()


# ============================================================
# DUPLICIDADE
# ============================================================

with col2:

    st.markdown("### ♻️ Duplicidade")

    st.caption(
        "Análise de registros duplicados."
    )

    pode_analisar_duplicidade = (
        base_carregada("api")
        or base_carregada("the")
    )

    if st.button(
        "Acessar Duplicidade",
        type="primary",
        use_container_width=True,
        disabled=not pode_analisar_duplicidade,
        key="btn_acessar_duplicidade",
    ):

        st.session_state.ferramenta_atual = "duplicidade"

        st.rerun()


# ============================================================
# SERVIÇOS
# ============================================================

with col3:

    st.markdown("### 🛠️ Serviços")

    st.caption(
        "Ferramenta em estruturação."
    )

    st.button(
        "Em breve",
        disabled=True,
        use_container_width=True,
        key="btn_servicos_breve",
    )


st.divider()


# ============================================================
# STATUS DAS BASES
# ============================================================

st.markdown("## 📊 Status das Bases")


status_colunas = st.columns(3)


for indice, (
    nome_base,
    titulo_base,
    _,
) in enumerate(bases):

    coluna = status_colunas[indice % 3]

    with coluna:

        if base_carregada(nome_base):

            df = obter_base(nome_base)

            st.success(
                f"{titulo_base}: "
                f"{len(df):,} registros".replace(",", ".")
            )

        else:

            st.warning(
                f"{titulo_base}: não carregada"
            )
