import streamlit as st
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

import extra_streamlit_components as stx


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TEMPO_SESSAO_HORAS = 8
COOKIE_NAME = "coi_auth_token"


# ============================================================
# CHAVE DE SEGURANÇA
# ============================================================

def obter_secret_key():
    """
    Obtém a chave secreta usada para assinar os cookies.

    A chave deve estar no Streamlit Secrets:
        COI_SECRET_KEY = "..."
    """

    chave = st.secrets.get("COI_SECRET_KEY")

    if not chave:
        raise RuntimeError(
            "A chave COI_SECRET_KEY não foi configurada "
            "nos Secrets do Streamlit."
        )

    return str(chave)


# ============================================================
# COOKIE MANAGER
# ============================================================

def get_manager():
    """
    Garante que o CookieManager seja criado apenas uma vez
    durante a sessão atual do Streamlit.
    """

    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager(
            key="coi_cookie_manager"
        )

    return st.session_state.cookie_manager


# ============================================================
# ASSINATURA
# ============================================================

def gerar_assinatura(conteudo: str) -> str:
    """
    Gera uma assinatura HMAC para impedir que o conteúdo
    do cookie seja alterado manualmente pelo navegador.
    """

    chave = obter_secret_key()

    return hmac.new(
        chave.encode("utf-8"),
        conteudo.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def criar_token(usuario: str, perfil: str) -> str:
    """
    Cria o conteúdo do cookie com validade de 8 horas.
    """

    agora = datetime.now(timezone.utc)
    expiracao = agora + timedelta(hours=TEMPO_SESSAO_HORAS)

    dados = {
        "usuario": usuario,
        "perfil": perfil,
        "expira_em": expiracao.isoformat(),
        "nonce": secrets.token_hex(16),
    }

    conteudo = json.dumps(
        dados,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assinatura = gerar_assinatura(conteudo)

    token = {
        "dados": conteudo,
        "assinatura": assinatura,
    }

    return json.dumps(
        token,
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ============================================================
# VALIDAÇÃO DO TOKEN
# ============================================================

def validar_token(token: str):
    """
    Valida a assinatura e a validade do cookie.

    Retorna os dados do usuário quando o token é válido.
    Retorna None quando o token é inválido ou expirado.
    """

    try:

        token_data = json.loads(token)

        conteudo = token_data.get("dados")
        assinatura_recebida = token_data.get("assinatura")

        if not conteudo or not assinatura_recebida:
            return None

        assinatura_correta = gerar_assinatura(conteudo)

        if not hmac.compare_digest(
            assinatura_recebida,
            assinatura_correta,
        ):
            return None

        dados = json.loads(conteudo)

        expira_em = datetime.fromisoformat(
            dados["expira_em"]
        )

        if expira_em.tzinfo is None:
            expira_em = expira_em.replace(
                tzinfo=timezone.utc
            )

        agora = datetime.now(timezone.utc)

        if agora >= expira_em:
            return None

        usuario = dados.get("usuario")
        perfil = dados.get("perfil")

        if not usuario or not perfil:
            return None

        return dados

    except Exception:
        return None


# ============================================================
# LOGIN
# ============================================================

def fazer_login(usuario: str, perfil: str):
    """
    Registra um novo login e inicia uma nova sessão de 8 horas.
    """

    cookie_manager = get_manager()

    token = criar_token(
        usuario=usuario,
        perfil=perfil,
    )

    expiracao_cookie = datetime.now(timezone.utc) + timedelta(
        hours=TEMPO_SESSAO_HORAS
    )

    cookie_manager.set(
        COOKIE_NAME,
        token,
        expires_at=expiracao_cookie,
    )

    st.session_state.autenticado = True
    st.session_state.usuario_logado = usuario
    st.session_state.perfil = perfil


# ============================================================
# VERIFICAÇÃO DA AUTENTICAÇÃO
# ============================================================

def verificar_autenticacao() -> bool:
    """
    Verifica a sessão atual.

    Primeiro verifica o session_state.
    Caso ele tenha sido perdido após um refresh,
    tenta reconstruir a sessão utilizando o cookie.
    """

    if st.session_state.get("autenticado") is True:

        return True

    cookie_manager = get_manager()

    try:
        cookie = cookie_manager.get(COOKIE_NAME)
    except Exception:
        return False

    if not cookie:
        return False

    dados = validar_token(cookie)

    if not dados:

        try:
            cookie_manager.delete(COOKIE_NAME)
        except Exception:
            pass

        return False

    st.session_state.autenticado = True
    st.session_state.usuario_logado = dados.get(
        "usuario",
        "",
    )
    st.session_state.perfil = dados.get(
        "perfil",
        "",
    )

    return True


# ============================================================
# LOGOUT
# ============================================================

def fazer_logout():
    """
    Encerra a sessão atual e remove o cookie de autenticação.
    """

    cookie_manager = get_manager()

    try:
        cookie_manager.delete(COOKIE_NAME)
    except Exception:
        pass

    keys_to_delete = [
        key
        for key in list(st.session_state.keys())
        if key != "cookie_manager"
    ]

    for key in keys_to_delete:
        del st.session_state[key]
