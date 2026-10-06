import streamlit as st

from auth import (
    fazer_login,
    verificar_autenticacao,
    fazer_logout,
    tem_acesso_modulo,
)


st.set_page_config(
    page_title="Plataforma COI - Hub Central",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# OCULTAR NAVEGAÇÃO PADRÃO DO STREAMLIT
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
    "admin2026",
)

SENHA_USUARIO = st.secrets.get(
    "SENHA_USUARIO",
    "coi2026",
)

SENHA_MODULO_1 = st.secrets.get(
    "SENHA_OPERADOR",
    "aegea2026",
)


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

if not st.session_state.get("autenticado"):

    st.title(
        "🔐 Acesso Restrito - Plataforma de Análises - COI"
    )

    st.markdown(
        "Por favor, insira a senha de acesso para continuar."
    )

    with st.form("form_login"):

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

            # ==================================================
            # ADMIN
            # ==================================================

            if senha_digitada == SENHA_ADMIN:

                fazer_login(
                    usuario="admin",
                    perfil="admin",
                )

                st.success(
                    "Login de Administrador realizado com sucesso!"
                )

                st.rerun()


            # ==================================================
            # OPERADOR
            # ==================================================

            elif senha_digitada == SENHA_USUARIO:

                fazer_login(
                    usuario="operador",
                    perfil="usuario",
                )

                st.success(
                    "Login de Usuário realizado com sucesso!"
                )

                st.rerun()


            # ==================================================
            # USUÁRIO SOMENTE MÓDULO 1
            # ==================================================

            elif (
                SENHA_MODULO_1
                and senha_digitada == SENHA_MODULO_1
            ):

                fazer_login(
                    usuario="usuario_modulo_1",
                    perfil="modulo_1",
                )

                st.success(
                    "Login realizado com sucesso!"
                )

                st.rerun()


            # ==================================================
            # SENHA INCORRETA
            # ==================================================

            else:

                st.error(
                    "❌ Senha incorreta. Tente novamente."
                )

    st.stop()


# ============================================================
# VALIDAR SESSÃO EXISTENTE
# ============================================================

if not verificar_autenticacao():

    st.session_state.autenticado = False
    st.rerun()


# ============================================================
# HUB CENTRAL
# ============================================================

if "modo_escuro_hub" not in st.session_state:
    st.session_state.modo_escuro_hub = False


modo_escuro_hub = st.toggle(
    "🌙 Modo escuro",
    value=st.session_state.modo_escuro_hub,
    key="toggle_modo_escuro_hub",
)


st.session_state.modo_escuro_hub = modo_escuro_hub


# ============================================================
# MODO ESCURO
# ============================================================

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
    f"Bem-vindo(a)! Perfil conectado: **{perfil_atual}**"
)

st.divider()

st.markdown(
    "### Selecione o módulo desejado:"
)

st.markdown("")


# ============================================================
# MÓDULOS DISPONÍVEIS
# ============================================================

modulo_1 = tem_acesso_modulo("1")
modulo_2 = tem_acesso_modulo("2")
modulo_3 = tem_acesso_modulo("3")
modulo_4 = tem_acesso_modulo("4")
modulo_5 = tem_acesso_modulo("5")
modulo_6 = tem_acesso_modulo("6")
modulo_7 = tem_acesso_modulo("7")


# ============================================================
# PRIMEIRA LINHA
# ============================================================

colunas = st.columns(3)

indice = 0


# ============================================================
# MÓDULO 1
# ============================================================

if modulo_1:

    with colunas[indice]:

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

    indice += 1


# ============================================================
# MÓDULO 2
# ============================================================

if modulo_2:

    with colunas[indice]:

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

    indice += 1


# ============================================================
# MÓDULO 3
# ============================================================

if modulo_3:

    with colunas[indice]:

        st.markdown("#### 🚰 Módulo 3")
        st.markdown("**Vazão de Poços**")
        st.caption("Status: Em desenvolvimento")

        if st.button(
            "Acessar Vazão de Poços",
            use_container_width=True,
            key="acessar_vazao_pocos",
        ):

            st.switch_page(
                "pages/3_Vazao_Pocos.py"
            )

    indice += 1


# ============================================================
# SEGUNDA LINHA
# ============================================================

st.markdown("")

colunas = st.columns(3)
indice = 0


# ============================================================
# MÓDULO 4
# ============================================================

if modulo_4:

    with colunas[indice]:

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

    indice += 1


# ============================================================
# MÓDULO 5
# ============================================================

if modulo_5:

    with colunas[indice]:

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

    indice += 1


# ============================================================
# MÓDULO 6
# ============================================================

if modulo_6:

    with colunas[indice]:

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

    indice += 1


# ============================================================
# TERCEIRA LINHA
# ============================================================

if modulo_7:

    st.markdown("")

    colunas = st.columns(3)
    indice = 0

    with colunas[0]:

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

if st.button(
    "Encerrar Sessão / Sair",
    key="encerrar_sessao",
):

    fazer_logout()

    st.success(
        "Sessão encerrada com sucesso!"
    )

    st.rerun()
