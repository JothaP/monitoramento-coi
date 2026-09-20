import streamlit as st

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Mapeamento de Pressão - COI",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS para ocultar navegação padrão
st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        [data-testid="stSidebar"] div.block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# TRAVA DE SEGURANÇA E CONTROLE DE SESSÃO
# ============================================================
if "autenticado" not in st.session_state or not st.session_state.autenticado:
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("Ir para o Login"):
        st.switch_page("app.py")
    st.stop()

# ============================================================
# CONTROLE DE ACESSO (ADMIN VS USUÁRIO COMUM)
# ============================================================
# Verificamos se o usuário atual é o administrador. 
# (Certifique-se de que a variável 'usuario_logado' ou 'perfil' é salva no st.session_state na sua tela de login)
usuario_atual = st.session_state.get("usuario_logado", "")
perfil_atual = st.session_state.get("perfil", "")

# Defina aqui quem é considerado admin (ex: pelo nome de usuário ou perfil)
eh_admin = (usuario_atual.lower() == "admin" or perfil_atual.lower() == "admin")

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### 🗺️ COI - Mapeamento")
    st.caption("Em Desenvolvimento")
    st.divider()
    if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")

# ============================================================
# CONTEÚDO DA TELA
# ============================================================
if not eh_admin:
    # --------------------------------------------------------
    # TELA PARA USUÁRIOS COMUNS (Em Desenvolvimento)
    # --------------------------------------------------------
    st.title("🗺️ Mapeamento de Pressão - COI")
    st.info("🚧 Este módulo está atualmente em fase de desenvolvimento e validação.")
    st.markdown("""
        Em breve, novas ferramentas de mapeamento de pressão estarão disponíveis por aqui. 
        Utilize o menu principal para acessar os módulos liberados.
    """)
else:
    # --------------------------------------------------------
    # TELA PARA O ADMINISTRADOR (Área de Testes / Painel Completo)
    # --------------------------------------------------------
    st.title("🗺️ Mapeamento de Pressão (Área do Admin - Testes)")
    st.warning("⚠️ Você está acessando este módulo em modo de testes (Admin).")
    
    # Aqui você pode colocar o código completo do Módulo 2 que enviamos antes 
    # para continuar desenvolvendo e testando enquanto os usuários veem o aviso acima!
    st.write("Insira o código funcional do painel aqui para testes exclusivos do administrador.")
