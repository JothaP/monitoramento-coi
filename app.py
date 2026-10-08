import streamlit as st

from auth import (
    fazer_login,
    verificar_autenticacao,
    fazer_logout,
    tem_acesso_modulo,
)


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Plataforma COI - Hub Central",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# OCULTAR NAVEGAÇÃO PADRÃO
# ============================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CREDENCIAIS
# ============================================================

SENHA_ADMIN = st.secrets.get(
    "SENHA_ADMIN",
)

SENHA_USUARIO = st.secrets.get(
    "SENHA_USUARIO",
)

SENHA_OPERADOR = st.secrets.get(
    "SENHA_OPERADOR",
)


# ============================================================
# VALIDAR CONFIGURAÇÃO DAS SENHAS
# ============================================================

if not SENHA_ADMIN:
    st.error(
        "A senha SENHA_ADMIN não está configurada nos Secrets."
    )
    st.stop()


if not SENHA_USUARIO:
    st.error(
        "A senha SENHA_USUARIO não está configurada nos Secrets."
    )
    st.stop()


if not SENHA_OPERADOR:
    st.error(
        "A senha SENHA_OPERADOR não está configurada nos Secrets."
    )
    st.stop()


# ============================================================
# ESTADO INICIAL
# ============================================================

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = ""

if "perfil" not in st.session_state:
    st.session_state.perfil = ""

if "modulos" not in st.session_state:
    st.session_state.modulos = []


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.get(
    "autenticado",
    False,
):

    st.title(
        "🔐 Acesso Restrito - Plataforma de Análises - COI"
    )

    st.markdown(
        "Por favor, insira a senha de acesso para continuar."
    )

    with st.form(
        "form_login"
    ):

        senha_digitada = st.text_input(
            "Senha de Acesso",
            type="password",
        )

        botao_login = st.form_submit_button(
            "Entrar",
            type="primary",
            use_container_width=True,
        )

        if botao_login:

            # =================================================
            # ADMIN
            # =================================================

            if (
                senha_digitada
                == SENHA_ADMIN
            ):

                sucesso = fazer_login(
                    usuario="admin",
                    perfil="admin",
                )

                if sucesso:

                    st.success(
                        "Login de Administrador realizado com sucesso!"
                    )

                    st.rerun()


            # =================================================
            # USUARIO
            # =================================================

            elif (
                senha_digitada
                == SENHA_USUARIO
            ):

                sucesso = fazer_login(
                    usuario="usuario",
                    perfil="usuario",
                )

                if sucesso:

                    st.success(
                        "Login de Usuário realizado com sucesso!"
                    )

                    st.rerun()


            # =================================================
            # OPERADOR
            # =================================================

            elif (
                senha_digitada
                == SENHA_OPERADOR
            ):

                sucesso = fazer_login(
                    usuario="operador",
                    perfil="operador",
                )

                if sucesso:

                    st.success(
                        "Login de Operador realizado com sucesso!"
                    )

                    st.rerun()


            # =================================================
            # SENHA INCORRETA
            # =================================================

            else:

                st.error(
                    "❌ Senha incorreta. Tente novamente."
                )

    st.stop()


# ============================================================
# VALIDAR SESSÃO
# ============================================================

if not verificar_autenticacao():

    st.session_state.autenticado = False

    st.session_state.usuario_logado = ""

    st.session_state.perfil = ""

    st.session_state.modulos = []

    st.rerun()


# ============================================================
# MODO ESCURO
# ============================================================

if "modo_escuro_hub" not in st.session_state:

    st.session_state.modo_escuro_hub = False


modo_escuro_hub = st.toggle(
    "🌙 Modo escuro",
    value=st.session_state.modo_escuro_hub,
    key="toggle_modo_escuro_hub",
)


st.session_state.modo_escuro_hub = (
    modo_escuro_hub
)


if modo_escuro_hub:

    st.markdown(
        """
        <style>

            .stApp {
                background-color: #0e1117;
                color: #fafafa;
            }

            .stApp p,
            .stApp label,
            .stApp h1,
            .stApp h2,
            .stApp h3,
            .stApp h4,
            .stApp h5,
            .stApp h6 {
                color: #f0f0f0 !important;
            }

            .stButton > button {
                background-color: #000000 !important;
                color: #ffffff !important;
                border: 1px solid #444c56 !important;
            }

            .stButton > button * {
                color: #ffffff !important;
            }

            .stButton > button:hover {
                background-color: #000000 !important;
                color: #ff0000 !important;
                border-color: #ff0000 !important;
            }

            .stButton > button:hover * {
                color: #ff0000 !important;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# INFORMAÇÕES DO USUÁRIO
# ============================================================

usuario_atual = st.session_state.get(
    "usuario_logado",
    "",
)

perfil_atual = st.session_state.get(
    "perfil",
    "",
).upper()


st.write(
    f"Bem-vindo(a)! Perfil conectado: "
    f"**{perfil_atual}**"
)

st.divider()

st.markdown(
    "### Selecione o módulo desejado:"
)

st.markdown("")


# ============================================================
# OBTENER PERMISSÕES
# ============================================================

modulo_1 = tem_acesso_modulo("1")
modulo_2 = tem_acesso_modulo("2")
modulo_3 = tem_acesso_modulo("3")
modulo_4 = tem_acesso_modulo("4")
modulo_5 = tem_acesso_modulo("5")
modulo_6 = tem_acesso_modulo("6")
modulo_7 = tem_acesso_modulo("7")


# ============================================================
# MÓDULOS
# ============================================================

# ------------------------------------------------------------
# PRIMEIRA LINHA
# ------------------------------------------------------------

col1, col2, col3 = st.columns(3)


# ============================================================
# MÓDULO 1
# ============================================================

with col1:

    if modulo_1:

        st.markdown("#### 💧 Módulo 1")
        st.markdown("**Baixa Pressão**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Baixa Pressão",
            type="primary",
            use_container_width=True,
            key="acessar_baixa_pressao",
        ):

            st.switch_page(
                "pages/1_Baixa_Pressao.py"
            )


# ============================================================
# MÓDULO 2
# ============================================================

with col2:

    if modulo_2:

        st.markdown("#### 🗺️ Módulo 2")
        st.markdown("**Mapeamento de Pressão**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Mapeamento",
            type="primary",
            use_container_width=True,
            key="acessar_mapeamento_pressao",
        ):

            st.switch_page(
                "pages/2_Mapeamento_Pressao.py"
            )


# ============================================================
# MÓDULO 3
# ============================================================

with col3:

    if modulo_3:

        st.markdown("#### 🚰 Módulo 3")
        st.markdown("**Farol Operacional**")
        st.caption(
            "Status: Em desenvolvimento"
        )

        if st.button(
            "Acessar Farol Operacional",
            use_container_width=True,
            key="acessar_farol_operacional",
        ):

            st.switch_page(
                "pages/3_Farol_Operacional.py"
            )


# ------------------------------------------------------------
# SEGUNDA LINHA
# ------------------------------------------------------------

st.markdown("")

col4, col5, col6 = st.columns(3)


# ============================================================
# MÓDULO 4
# ============================================================

with col4:

    if modulo_4:

        st.markdown("#### 🛠️ Módulo 4")
        st.markdown("**Ferramentas Operacionais**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Ferramentas",
            type="primary",
            use_container_width=True,
            key="acessar_ferramentas_operacionais",
        ):

            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )


# ============================================================
# MÓDULO 5
# ============================================================

with col5:

    if modulo_5:

        st.markdown("#### 📋 Módulo 5")
        st.markdown("**Cadastros e Consultas COI**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Cadastros e Consultas",
            type="primary",
            use_container_width=True,
            key="acessar_cadastros_consultas",
        ):

            st.switch_page(
                "pages/5_Cadastros_Consultas_COI.py"
            )


# ============================================================
# MÓDULO 6
# ============================================================

with col6:

    if modulo_6:

        st.markdown("#### 🔧 Módulo 6")
        st.markdown("**Ferramentas Adicionais**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Ferramentas Adicionais",
            type="primary",
            use_container_width=True,
            key="acessar_ferramentas_adicionais",
        ):

            st.switch_page(
                "pages/6_Ferramentas_Adicionais.py"
            )


# ------------------------------------------------------------
# TERCEIRA LINHA
# ------------------------------------------------------------

if modulo_7:

    st.markdown("")

    col7, col8, col9 = st.columns(3)

    with col7:

        st.markdown("#### 🗺️ Módulo 7")
        st.markdown("**Mapeamento de Melhorias**")
        st.caption("Status: Suspenso")

        if st.button(
            "Acessar Mapeamento de Melhorias",
            type="primary",
            use_container_width=True,
            key="acessar_mapeamento_melhorias",
        ):

            st.switch_page(
                "pages/7_Mapeamento_de_Melhorias.py"
            )


# ============================================================
# ENCERRAR SESSÃO
# ============================================================

st.markdown("")

st.divider()

if st.button(
    "Encerrar Sessão / Sair",
    key="encerrar_sessao",
):

    fazer_logout()

    st.success(
        "Sessão encerrada com sucesso!"
    )

    st.rerun()
