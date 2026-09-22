import streamlit as st

from auth import verificar_autenticacao

from gerador_lotes.estado import (
    inicializar_estado,
    obter_base,
    base_carregada,
    limpar_base,
    limpar_bases,
    limpar_resultado,
)

from gerador_lotes.carregamento import (
    processar_upload_multiplo,
)

from gerador_lotes.ferramentas.filtragem import (
    render_filtragem,
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


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():

    st.warning(
        "Sessão não iniciada ou expirada."
    )

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# ESTADO
# ============================================================

inicializar_estado()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### 📦 Gerador de Lotes"
    )

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
        key="hub_voltar_ferramentas",
    ):

        st.session_state.ferramenta_atual = None

        st.switch_page(
            "pages/4_Ferramentas_Operacionais.py"
        )

    if st.button(
        "🏠 Menu Principal",
        use_container_width=True,
        key="hub_menu_principal",
    ):

        st.session_state.ferramenta_atual = None

        st.switch_page("app.py")

    st.divider()

    if st.button(
        "🧹 Limpar todas as bases",
        use_container_width=True,
        key="hub_limpar_todas",
    ):

        limpar_bases()

        st.rerun()


# ============================================================
# ROTEAMENTO INTERNO DAS FERRAMENTAS
# ============================================================

if (
    st.session_state.get("ferramenta_atual")
    == "filtragem"
):

    render_filtragem()

    st.stop()


# ============================================================
# HUB
# ============================================================

st.title(
    "📦 Gerador de Lotes"
)

st.caption(
    "Hub central para carregamento e gerenciamento das bases operacionais."
)

st.divider()


# ============================================================
# BASES
# ============================================================

st.subheader(
    "📂 Bases Operacionais"
)

st.caption(
    "Carregue aqui as bases que ficarão disponíveis para as ferramentas."
)


BASES_UI = [
    (
        "api",
        "🔵 API",
        "Base API",
    ),
    (
        "the",
        "🟢 THE",
        "Base THE",
    ),
    (
        "servicos_api",
        "🔧 Serviços API",
        "Base de Serviços API",
    ),
    (
        "servicos_the",
        "🔧 Serviços THE",
        "Base de Serviços THE",
    ),
    (
        "eventos",
        "📋 Eventos",
        "Base de Eventos",
    ),
    (
        "lotes",
        "📦 Lotes",
        "Base de Lotes",
    ),
]


for inicio in range(
    0,
    len(BASES_UI),
    2,
):

    colunas = st.columns(2)

    for deslocamento, coluna in enumerate(
        colunas
    ):

        indice = inicio + deslocamento

        if indice >= len(BASES_UI):
            continue

        nome_base, titulo, descricao = (
            BASES_UI[indice]
        )

        with coluna:

            st.markdown(
                f"### {titulo}"
            )

            st.caption(
                descricao
            )

            versao = st.session_state.get(
                f"versao_upload_{nome_base}",
                0,
            )

            arquivos = st.file_uploader(
                "Selecione arquivo(s) Excel",
                type=[
                    "xlsx",
                    "xlsm",
                ],
                accept_multiple_files=True,
                key=(
                    f"upload_{nome_base}_{versao}"
                ),
                help=(
                    "Pode enviar um ou vários arquivos. "
                    "O nome do arquivo não precisa seguir um padrão."
                ),
            )

            if arquivos:

                try:

                    processado = (
                        processar_upload_multiplo(
                            nome_base,
                            arquivos,
                        )
                    )

                    if processado:

                        st.success(
                            f"{len(arquivos)} arquivo(s) carregado(s) com sucesso."
                        )

                except Exception as erro:

                    st.error(
                        f"Erro ao carregar {titulo}: {erro}"
                    )

            if base_carregada(nome_base):

                df = obter_base(
                    nome_base
                )

                nomes = st.session_state.get(
                    f"arquivos_{nome_base}",
                    [],
                )

                st.success(
                    "✅ Base carregada — "
                    + f"{len(df):,} registros".replace(
                        ",",
                        ".",
                    )
                )

                st.caption(
                    f"Colunas: {len(df.columns)}"
                )

                if nomes:

                    st.caption(
                        "Arquivo(s): "
                        + ", ".join(nomes)
                    )

                if st.button(
                    "🗑️ Limpar esta base",
                    use_container_width=True,
                    key=(
                        f"limpar_{nome_base}"
                    ),
                ):

                    limpar_base(
                        nome_base
                    )

                    limpar_resultado()

                    st.rerun()

            else:

                st.info(
                    "Nenhum arquivo carregado."
                )


# ============================================================
# STATUS
# ============================================================

st.divider()

st.subheader(
    "📊 Status das Bases"
)

colunas_status = st.columns(6)

for coluna, (
    nome_base,
    titulo,
    _,
) in zip(
    colunas_status,
    BASES_UI,
):

    with coluna:

        if base_carregada(nome_base):

            df = obter_base(
                nome_base
            )

            st.metric(
                titulo,
                f"{len(df):,}".replace(
                    ",",
                    ".",
                ),
            )

        else:

            st.metric(
                titulo,
                "—",
            )


# ============================================================
# FERRAMENTAS
# ============================================================

st.divider()

st.subheader(
    "🛠️ Ferramentas"
)

st.caption(
    "As ferramentas utilizam as bases carregadas acima. A seleção API/THE é feita dentro de cada ferramenta."
)


col1, col2, col3 = st.columns(3)


# ============================================================
# FILTRAGEM / CANCELAMENTO
# ============================================================

with col1:

    st.markdown(
        "### 🔎 Filtragem / Cancelamento"
    )

    st.caption(
        "Filtragem das bases API/THE e geração de lotes de cancelamento."
    )

    pode_acessar = (
        base_carregada("api")
        or base_carregada("the")
    )

    if st.button(
        "Acessar Filtragem",
        type="primary",
        use_container_width=True,
        disabled=not pode_acessar,
        key="hub_acessar_filtragem",
    ):

        st.session_state.ferramenta_atual = (
            "filtragem"
        )

        limpar_resultado()

        st.rerun()

    if not pode_acessar:

        st.caption(
            "🔒 Carregue API ou THE para habilitar."
        )


# ============================================================
# SERVIÇOS
# ============================================================

with col2:

    st.markdown(
        "### 🔧 Serviços"
    )

    st.caption(
        "Ferramentas relacionadas às bases de serviços."
    )

    st.button(
        "Em desenvolvimento",
        disabled=True,
        use_container_width=True,
        key="hub_servicos",
    )


# ============================================================
# EVENTOS / LOTES
# ============================================================

with col3:

    st.markdown(
        "### 📋 Eventos / Lotes"
    )

    st.caption(
        "Ferramentas para processamento de eventos e lotes."
    )

    st.button(
        "Em desenvolvimento",
        disabled=True,
        use_container_width=True,
        key="hub_eventos_lotes",
    )
