import streamlit as st
from datetime import datetime, timedelta
import json
import extra_streamlit_components as stx

# ============================================================
# CONFIGURAÇÕES
# ============================================================
TEMPO_SESSAO_HORAS = 8          # ← Tempo de duração da sessão
COOKIE_NAME = "coi_auth_token"


def get_manager():
    return stx.CookieManager(key="coi_cookie_manager")


def fazer_login(usuario: str, perfil: str):
    """Chamado quando o login é bem-sucedido"""
    cookie_manager = get_manager()
    
    expiracao = datetime.now() + timedelta(hours=TEMPO_SESSAO_HORAS)
    
    dados = {
        "autenticado": True,
        "usuario": usuario,
        "perfil": perfil,
        "expira_em": expiracao.isoformat()
    }
    
    cookie_manager.set(
        COOKIE_NAME,
        json.dumps(dados),
        expires_at=datetime.now() + timedelta(days=1)
    )
    
    st.session_state.autenticado = True
    st.session_state.usuario_logado = usuario
    st.session_state.perfil = perfil


def verificar_autenticacao() -> bool:
    """
    Restaura a sessão se o cookie ainda for válido.
    """
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
            st.session_state.autenticado = True
            st.session_state.usuario_logado = dados.get("usuario", "")
            st.session_state.perfil = dados.get("perfil", "")
            return True
        else:
            cookie_manager.delete(COOKIE_NAME)
            return False
            
    except Exception:
        cookie_manager.delete(COOKIE_NAME)
        return False


def fazer_logout():
    """Limpa a sessão e o cookie"""
    cookie_manager = get_manager()
    cookie_manager.delete(COOKIE_NAME)
    
    for key in list(st.session_state.keys()):
        del st.session_state[key]
