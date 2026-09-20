import streamlit as st

# ============================================================
# CONFIGURAÇÃO DA PÁGINA (Com ocultação da navegação padrão)
# ============================================================
st.set_page_config(
    page_title="Plataforma COI - Hub Central",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Oculta a barra lateral automática de páginas do Streamlit
st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# CREDENCIAIS DO SECRETS
# ============================================================
SENHA_ADMIN = st.secrets.get("SENHA_ADMIN", "admin2026")
SENHA_USUARIO = st.secrets.get("SENHA_USUARIO", "coi2026")

# ============================================================
# CONTROLE DE SESSÃO
# ============================================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "perfil" not in st.session_state:
    st.session_state.perfil = ""
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = ""

# ============================================================
# TELA DE LOGIN
# ============================================================
if not st.session_state.autenticado:
    st.title("🔐 Acesso Restrito - Plataforma COI")
    st.markdown("Por favor, insira a senha de acesso para continuar.")

    with st.form("form_login"):
        senha_digitada = st.text_input("Senha de Acesso", type="password")
        botao_login = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if botao_login:
            if senha_digitada == SENHA_ADMIN:
                st.session_state.autenticado = True
                st.session_state.perfil = "admin"
                st.session_state.usuario_logado = "admin"
                st.success("Login de Administrador realizado com sucesso!")
                st.rerun()
            elif senha_digitada == SENHA_USUARIO:
                st.session_state.autenticado = True
                st.session_state.perfil = "usuario"
                st.session_state.usuario_logado = "operador"
                st.success("Login de Usuário realizado com sucesso!")
                st.rerun()
            else:
                st.error("❌ Senha incorreta. Tente novamente.")
    st.stop()

# ============================================================
# HUB CENTRAL (APÓS O LOGIN)
# ============================================================
perfil_atual = st.session_state.perfil.upper()
st.write(f"Bem-vindo(a)! Perfil conectado: **{perfil_atual}**")
st.divider()

st.markdown("### Selecione o módulo desejado:")
st.markdown("")

col1, col2, col3 = st.columns(3)

# MÓDULO 1 (Liberado para todos)
with col1:
    st.markdown("#### 🗺️ Módulo 1")
    st.markdown("**Baixa Pressão**")
    st.caption("Status: Ativo para todos")
    if st.button("Acessar Baixa Pressão", type="primary", use_container_width=True):
        st.switch_page("pages/1_Baixa_Pressao.py")

# MÓDULO 2 (Liberado para todos)
with col2:
    st.markdown("#### 📊 Módulo 2")
    st.markdown("**Mapeamento de Pressão**")
    st.caption("Status: Ativo para todos")
    if st.button("Acessar Mapeamento", type="primary", use_container_width=True):
        st.switch_page("pages/2_Mapeamento_Pressao.py")

# MÓDULO 3 (Restrito a Admin)
with col3:
    st.markdown("#### ⚙️ Módulo 3")
    st.markdown("**Vazão de Poços**")
    if st.session_state.perfil == "admin":
        st.caption("Status: Em desenvolvimento (Admin)")
        if st.button("Acessar Vazão de Poços", use_container_width=True):
            st.switch_page("pages/3_Vazao_Pocos.py")
    else:
        st.caption("Status: Em desenvolvimento")
        st.button("Acessar Vazão de Poços", disabled=True, use_container_width=True)
        st.markdown("<p style='font-size:12px; color:gray;'>🔒 Restrito a administradores</p>", unsafe_allow_html=True)

st.divider()

# Botão de Logout
if st.button("Encerrar Sessão / Sair"):
    st.session_state.autenticado = False
    st.session_state.perfil = ""
    st.session_state.usuario_logado = ""
    st.success("Sessão encerrada com sucesso!")
    st.rerun()
