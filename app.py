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
            # CONSULTA (identificador interno: operador)
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
                        "Login de Consulta realizado com sucesso!"
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
# VISUAL DE BOTÕES DESABILITADOS (INCLUSIVE NO MODO ESCURO)
# ============================================================

st.markdown(
    """
    <style>
        .stButton > button:disabled,
        .stButton > button:disabled:hover {
            opacity: 0.45 !important;
            cursor: not-allowed !important;
            background-color: #71717a !important;
            color: #ffffff !important;
            border-color: #71717a !important;
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

# O identificador interno continua sendo "operador" para preservar o
# auth.py, as permissões existentes e a senha SENHA_OPERADOR no Secrets.
# Somente a identificação apresentada ao usuário passa a ser "CONSULTA".
perfil_interno = str(st.session_state.get("perfil", "")).strip().lower()
perfil_consulta = perfil_interno == "operador"
perfil_atual = "CONSULTA" if perfil_consulta else perfil_interno.upper()


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
ambiente_teste = tem_acesso_modulo("teste")


# ============================================================
# MÓDULOS
# ============================================================
# Perfil CONSULTA: todos os cartões ficam visíveis em suas posições;
# apenas os botões autorizados permanecem habilitados.
# Outros perfis mantêm sua exibição atual.


# ------------------------------------------------------------
# PRIMEIRA LINHA
# ------------------------------------------------------------

col1, col2, col3 = st.columns(3)


# ============================================================
# MÓDULO 1
# ============================================================

with col1:

    if modulo_1 or perfil_consulta:

        st.markdown("#### 💧 Módulo 1")
        st.markdown("**Baixa Pressão**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Baixa Pressão",
            type="primary",
            use_container_width=True,
            key="acessar_baixa_pressao",
            disabled=not modulo_1,
        ):

            st.switch_page(
                "pages/1_Baixa_Pressao.py"
            )


# ============================================================
# MÓDULO 2
# ============================================================

with col2:

    if modulo_2 or perfil_consulta:

        st.markdown("#### 🗺️ Módulo 2")
        st.markdown("**Mapeamento de Pressão**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Mapeamento",
            type="primary",
            use_container_width=True,
            key="acessar_mapeamento_pressao",
            disabled=not modulo_2,
        ):

            st.switch_page(
                "pages/2_Mapeamento_Pressao.py"
            )


# ============================================================
# MÓDULO 3
# ============================================================

with col3:

    if modulo_3 or perfil_consulta:

        st.markdown("#### 🚰 Módulo 3")
        st.markdown("**Farol Operacional**")
        st.caption(
            "Status: Ativo"
        )

        if st.button(
            "Acessar Farol Operacional",
            type="primary",
            use_container_width=True,
            key="acessar_farol_operacional",
            disabled=not modulo_3,
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

    if modulo_4 or perfil_consulta:

        st.markdown("#### 🛠️ Módulo 4")
        st.markdown("**Ferramentas Operacionais**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Ferramentas",
            type="primary",
            use_container_width=True,
            key="acessar_ferramentas_operacionais",
            disabled=not modulo_4,
        ):

            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )


# ============================================================
# MÓDULO 5
# ============================================================

with col5:

    if modulo_5 or perfil_consulta:

        st.markdown("#### 📋 Módulo 5")
        st.markdown("**Cadastros e Consultas COI**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Cadastros e Consultas",
            type="primary",
            use_container_width=True,
            key="acessar_cadastros_consultas",
            disabled=not modulo_5,
        ):

            st.switch_page(
                "pages/5_Cadastros_Consultas_COI.py"
            )


# ============================================================
# MÓDULO 6
# ============================================================

with col6:

    if modulo_6 or perfil_consulta:

        st.markdown("#### 🔧 Módulo 6")
        st.markdown("**Ferramentas Adicionais**")
        st.caption("Status: Ativo")

        if st.button(
            "Acessar Ferramentas Adicionais",
            type="primary",
            use_container_width=True,
            key="acessar_ferramentas_adicionais",
            disabled=not modulo_6,
        ):

            st.switch_page(
                "pages/6_Ferramentas_Adicionais.py"
            )


# ------------------------------------------------------------
# TERCEIRA LINHA
# ------------------------------------------------------------

# A terceira linha permanece visível para todos os perfis autenticados.
# Os cartões não mudam de posição quando algum módulo está oculto.
st.markdown("")
col7, col8, col9 = st.columns(3)

# ============================================================
# MÓDULO 7 — POSIÇÃO 7 (ESQUERDA)
# ============================================================

if modulo_7 or perfil_consulta:
    with col7:
        st.markdown("#### 📊 Módulo 7")
        st.markdown("**Relatórios Integrados**")
        st.caption("Concentrações e baixa pressão")
        if st.button(
            "Acessar Relatórios Integrados",
            type="primary",
            use_container_width=True,
            key="acessar_relatorios_integrados",
            disabled=not modulo_7,
        ):
            st.switch_page("pages/7_Relatorios_Integrados.py")

# ============================================================
# MÓDULO 8 — POSIÇÃO 8 (CENTRO)
# ============================================================

# Acesso liberado a todos os perfis autenticados: admin, usuario e operador.
# A própria página também valida a autenticação, inclusive no acesso direto.
with col8:
    st.markdown("#### 🔍 Módulo 8")
    st.markdown("**Consulta Operacional**")
    st.caption("Status: Ativo")
    if st.button(
        "Acessar Consulta Operacional",
        type="primary",
        use_container_width=True,
        key="acessar_consulta_operacional",
    ):
        st.switch_page("pages/8_Consulta_Operacional.py")

# ============================================================
# AMBIENTE DE TESTE — POSIÇÃO 9 (DIREITA)
# ============================================================

# Mantém a permissão de acesso de auth.py e exibe o cartão bloqueado para CONSULTA.
if ambiente_teste or perfil_consulta:
    with col9:
        st.markdown("#### 🧪 Ambiente de Teste")
        st.markdown("**Ferramentas em desenvolvimento**")
        st.caption("Acesso exclusivo do administrador")
        if st.button(
            "Acessar Ambiente de Teste",
            type="primary",
            use_container_width=True,
            key="acessar_ambiente_teste",
            disabled=not ambiente_teste,
        ):
            st.switch_page("pages/Ambiente_de_Teste.py")


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
