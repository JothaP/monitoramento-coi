import streamlit as st

from auth import (
    fazer_login,
    verificar_autenticacao,
    fazer_logout,
)

from gerador_lotes import (
    inicializar_estado,
    obter_base,
    base_carregada,
    processar_upload_unico,
    definir_modo_operacao,
    obter_modo_operacao,
    ajustar_modo_operacao,
)


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Plataforma COI - Hub Central",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# OCULTAR NAVEGAÇÃO PADRÃO
# ============================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .base-card {
            padding: 18px;
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 10px;
            margin-bottom: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# CREDENCIAIS
# ============================================================

SENHA_ADMIN = st.secrets.get(
    "SENHA_ADMIN",
    "admin2026"
)

SENHA_USUARIO = st.secrets.get(
    "SENHA_USUARIO",
    "coi2026"
)


# ============================================================
# INICIALIZAÇÃO DO ESTADO CENTRAL
# ============================================================

inicializar_estado()


# ============================================================
# RESTAURAÇÃO DA SESSÃO
# ============================================================

verificar_autenticacao()


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.get("autenticado"):

    st.title("🔐 Acesso Restrito - Plataforma COI")

    st.markdown(
        "Por favor, insira a senha de acesso para continuar."
    )

    with st.form("form_login"):

        senha_digitada = st.text_input(
            "Senha de Acesso",
            type="password"
        )

        botao_login = st.form_submit_button(
            "Entrar",
            type="primary",
            use_container_width=True
        )

        if botao_login:

            if senha_digitada == SENHA_ADMIN:

                fazer_login(
                    usuario="admin",
                    perfil="admin"
                )

                st.success(
                    "Login de Administrador realizado com sucesso!"
                )

                st.rerun()

            elif senha_digitada == SENHA_USUARIO:

                fazer_login(
                    usuario="operador",
                    perfil="usuario"
                )

                st.success(
                    "Login de Usuário realizado com sucesso!"
                )

                st.rerun()

            else:

                st.error(
                    "❌ Senha incorreta. Tente novamente."
                )

    st.stop()


# ============================================================
# GARANTE MODO VÁLIDO
# ============================================================

ajustar_modo_operacao()


# ============================================================
# INFORMAÇÕES DO USUÁRIO
# ============================================================

perfil_atual = st.session_state.get(
    "perfil",
    "usuario"
)

usuario_atual = st.session_state.get(
    "usuario_logado",
    ""
)


# ============================================================
# CABEÇALHO
# ============================================================

st.title("🏢 Plataforma COI")

st.write(
    f"Bem-vindo(a)! "
    f"Usuário: **{usuario_atual}** | "
    f"Perfil: **{perfil_atual.upper()}**"
)

st.divider()


# ============================================================
# CENTRAL DE BASES
# ============================================================

st.header("📂 Central de Bases")

st.caption(
    "Carregue as bases uma única vez. "
    "Elas permanecerão disponíveis para os módulos "
    "durante toda a sessão."
)


col_api, col_the = st.columns(2)


# ============================================================
# BASE API
# ============================================================

with col_api:

    st.subheader("🔵 Base API")

    arquivo_api = st.file_uploader(
        "Carregar Base API",
        type=["xlsx", "xlsm"],
        key="upload_base_api"
    )

    if arquivo_api is not None:

        processar_upload_unico(
            nome_base="api",
            arquivo=arquivo_api
        )

    if base_carregada("api"):

        df_api = obter_base("api")

        arquivos_api = st.session_state.get(
            "arquivos_api",
            []
        )

        nome_api = (
            arquivos_api[0]
            if arquivos_api
            else "Arquivo carregado"
        )

        st.success(
            f"🟢 Base API carregada\n\n"
            f"**Arquivo:** {nome_api}\n\n"
            f"**Registros:** {len(df_api):,}\n\n"
            f"**Colunas:** {len(df_api.columns):,}"
        )

    else:

        st.info(
            "Nenhuma Base API carregada."
        )


# ============================================================
# BASE THE
# ============================================================

with col_the:

    st.subheader("🟢 Base THE")

    arquivo_the = st.file_uploader(
        "Carregar Base THE",
        type=["xlsx", "xlsm"],
        key="upload_base_the"
    )

    if arquivo_the is not None:

        processar_upload_unico(
            nome_base="the",
            arquivo=arquivo_the
        )

    if base_carregada("the"):

        df_the = obter_base("the")

        arquivos_the = st.session_state.get(
            "arquivos_the",
            []
        )

        nome_the = (
            arquivos_the[0]
            if arquivos_the
            else "Arquivo carregado"
        )

        st.success(
            f"🟢 Base THE carregada\n\n"
            f"**Arquivo:** {nome_the}\n\n"
            f"**Registros:** {len(df_the):,}\n\n"
            f"**Colunas:** {len(df_the.columns):,}"
        )

    else:

        st.info(
            "Nenhuma Base THE carregada."
        )


# ============================================================
# BASE OPERACIONAL ATIVA
# ============================================================

st.divider()

st.subheader("🎯 Base Operacional Ativa")


bases_disponiveis = []

if base_carregada("api"):
    bases_disponiveis.append("API")

if base_carregada("the"):
    bases_disponiveis.append("THE")


if bases_disponiveis:

    modo_atual = obter_modo_operacao()

    if modo_atual not in bases_disponiveis:

        modo_atual = bases_disponiveis[0]

        definir_modo_operacao(
            modo_atual
        )

    modo_selecionado = st.radio(
        "Selecione a base que será utilizada pelas ferramentas:",
        options=bases_disponiveis,
        index=bases_disponiveis.index(
            modo_atual
        ),
        horizontal=True,
        key="modo_base_operacional"
    )

    definir_modo_operacao(
        modo_selecionado
    )

    if modo_selecionado == "API":

        df_ativo = obter_base("api")

        arquivos_ativos = st.session_state.get(
            "arquivos_api",
            []
        )

    else:

        df_ativo = obter_base("the")

        arquivos_ativos = st.session_state.get(
            "arquivos_the",
            []
        )

    nome_ativo = (
        arquivos_ativos[0]
        if arquivos_ativos
        else "Arquivo carregado"
    )

    st.success(
        f"🎯 **Base ativa: {modo_selecionado}**  |  "
        f"**Arquivo:** {nome_ativo}  |  "
        f"**Registros:** {len(df_ativo):,}"
    )

else:

    st.warning(
        "Nenhuma base foi carregada. "
        "Carregue a Base API e/ou a Base THE."
    )


# ============================================================
# RESUMO
# ============================================================

with st.expander("📋 Resumo das bases carregadas"):

    if base_carregada("api"):

        st.write(
            f"🟢 **API:** "
            f"{len(obter_base('api')):,} registros"
        )

    else:

        st.write(
            "⚪ **API:** não carregada"
        )

    if base_carregada("the"):

        st.write(
            f"🟢 **THE:** "
            f"{len(obter_base('the')):,} registros"
        )

    else:

        st.write(
            "⚪ **THE:** não carregada"
        )

    modo = obter_modo_operacao()

    if modo:

        st.write(
            f"🎯 **Base operacional ativa:** {modo}"
        )

    else:

        st.write(
            "🎯 **Base operacional ativa:** nenhuma"
        )


# ============================================================
# MÓDULOS
# ============================================================

st.divider()

st.markdown(
    "### Selecione o módulo desejado:"
)

col1, col2, col3, col4 = st.columns(4)


# ============================================================
# MÓDULO 1
# ============================================================

with col1:

    st.markdown("#### 🗺️ Módulo 1")
    st.markdown("**Baixa Pressão**")
    st.caption("Status: Ativo para todos")

    if st.button(
        "Acessar Baixa Pressão",
        type="primary",
        use_container_width=True,
        key="btn_baixa_pressao"
    ):

        st.switch_page(
            "pages/1_Baixa_Pressao.py"
        )


# ============================================================
# MÓDULO 2
# ============================================================

with col2:

    st.markdown("#### 📊 Módulo 2")
    st.markdown("**Mapeamento de Pressão**")
    st.caption("Status: Ativo para todos")

    if st.button(
        "Acessar Mapeamento",
        type="primary",
        use_container_width=True,
        key="btn_mapeamento"
    ):

        st.switch_page(
            "pages/2_Mapeamento_Pressao.py"
        )


# ============================================================
# MÓDULO 3
# ============================================================

with col3:

    st.markdown("#### ⚙️ Módulo 3")
    st.markdown("**Vazão de Poços**")

    if st.session_state.perfil == "admin":

        st.caption(
            "Status: Em desenvolvimento (Admin)"
        )

        if st.button(
            "Acessar Vazão de Poços",
            use_container_width=True,
            key="btn_vazao_pocos"
        ):

            st.switch_page(
                "pages/3_Vazao_Pocos.py"
            )

    else:

        st.caption(
            "Status: Em desenvolvimento"
        )

        st.button(
            "Acessar Vazão de Poços",
            disabled=True,
            use_container_width=True,
            key="btn_vazao_pocos_bloqueado"
        )

        st.markdown(
            "<p style='font-size:12px; color:gray;'>"
            "🔒 Restrito a administradores"
            "</p>",
            unsafe_allow_html=True
        )


# ============================================================
# MÓDULO 4
# ============================================================

with col4:

    st.markdown("#### 🛠️ Módulo 4")
    st.markdown("**Ferramentas Operacionais**")

    if st.session_state.perfil == "admin":

        st.caption(
            "Status: Ativo (Admin)"
        )

        if st.button(
            "Acessar Ferramentas",
            type="primary",
            use_container_width=True,
            key="btn_ferramentas"
        ):

            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )

    else:

        st.caption(
            "Status: Em desenvolvimento"
        )

        st.button(
            "Acessar Ferramentas",
            disabled=True,
            use_container_width=True,
            key="btn_ferramentas_bloqueado"
        )

        st.markdown(
            "<p style='font-size:12px; color:gray;'>"
            "🔒 Restrito a administradores"
            "</p>",
            unsafe_allow_html=True
        )


# ============================================================
# LOGOUT
# ============================================================

st.divider()

if st.button(
    "🚪 Encerrar Sessão / Sair"
):

    fazer_logout()

    st.success(
        "Sessão encerrada com sucesso!"
    )

    st.rerun()
