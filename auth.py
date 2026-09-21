import streamlit as st
from datetime import datetime, timedelta
import json
import extra_streamlit_components as stx

# ============================================================
# CONFIGURAÇÕES
# ============================================================
TEMPO_SESSAO_HORAS = 8          # ← Altere aqui o tempo de expiração da sessão
COOKIE_NAME = "coi_auth_token"


def get_manager():
    return stx.CookieManager(key="coi_cookie_manager")


def fazer_login(usuario: str = "usuario"):
    """Chamado quando o login é bem-sucedido"""
    cookie_manager = get_manager()
    
    expiracao = datetime.now() + timedelta(hours=TEMPO_SESSAO_HORAS)
    
    dados = {
        "autenticado": True,
        "usuario": usuario,
        "expira_em": expiracao.isoformat()
    }
    
    # Grava o cookie (válido por 1 dia no navegador)
    cookie_manager.set(
        COOKIE_NAME,
        json.dumps(dados),
        expires_at=datetime.now() + timedelta(days=1)
    )
    
    st.session_state.autenticado = True
    st.session_state.usuario = usuario


def verificar_autenticacao() -> bool:
    """
    Deve ser chamada no INÍCIO de todas as páginas protegidas.
    Retorna True se a sessão for válida.
    """
    # Já está autenticado nesta execução?
    if st.session_state.get("autenticado") is True:
        return True
    
    cookie_manager = get_manager()
    cookie = cookie_manager.get(COOKIE_NAME)
    
    if not cookie:
        return False
    
    try:
        dados = json.loads(cookie)
        expira_em = datetime.fromisoformat(dados["expira_em"])
        
        if datetime.now() < expira_em:
            # Cookie ainda válido → restaura a sessão
            st.session_state.autenticado = True
            st.session_state.usuario = dados.get("usuario", "usuario")
            return True
        else:
            # Cookie expirado
            cookie_manager.delete(COOKIE_NAME)
            return False
            
    except Exception:
        cookie_manager.delete(COOKIE_NAME)
        return False


def fazer_logout():
    """Limpa a sessão e o cookie"""
    cookie_manager = get_manager()
    cookie_manager.delete(COOKIE_NAME)
    
    # Limpa todo o session_state
    for key in list(st.session_state.keys()):
        del st.session_state[key]
