import streamlit as st
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from streamlit_cookies_controller import CookieController


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TEMPO_SESSAO_HORAS = 8
COOKIE_NAME = "coi_auth_token"


# ============================================================
# USUÁRIOS E PERMISSÕES
# ============================================================
#
# IMPORTANTE:
# Esta estrutura define APENAS as permissões.
#
# A validação da senha pode continuar sendo feita
# pelo sistema de login que você já possui.
#
# Basta ajustar os nomes dos usuários abaixo.
#

PERMISSOES_USUARIOS = {

    # --------------------------------------------------------
    # ADMINISTRADOR
    # --------------------------------------------------------
    "usuario_admin": {
        "perfil": "admin",
        "modulos": ["1", "2", "3", "4", "5", "6", "7", "8"]
    },

    # --------------------------------------------------------
    # USUÁRIO ATUAL
    # --------------------------------------------------------
    "usuario_2": {
        "perfil": "usuario",
        "modulos": ["1", "2", "3", "4", "5", "6", "7", "8"]
    },

    # --------------------------------------------------------
    # NOVO USUÁRIO
    # ACESSO SOMENTE AO MÓDULO 1
    # --------------------------------------------------------
    "usuario_3": {
        "perfil": "operador",
        "modulos": ["1"]
    },
}


# ============================================================
# COOKIE CONTROLLER
# ============================================================

def get_controller():

    controller = st.session_state.get(
        "cookie_controller"
    )

    if controller is None:

        controller = CookieController(
            key="coi_auth_controller"
        )

        st.session_state["cookie_controller"] = controller

    return controller


# ============================================================
# SECRET KEY
# ============================================================

def obter_secret_key():

    chave = st.secrets.get("COI_SECRET_KEY")

    if not chave:

        raise RuntimeError(
            "A chave COI_SECRET_KEY não foi configurada "
            "nos Secrets do Streamlit."
        )

    return str(chave)


# ============================================================
# ASSINATURA HMAC
# ============================================================

def gerar_assinatura(conteudo):

    chave = obter_secret_key()

    return hmac.new(
        chave.encode("utf-8"),
        conteudo.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ============================================================
# PERMISSÕES
# ============================================================

def obter_permissoes_usuario(usuario):

    usuario = str(usuario)

    dados = PERMISSOES_USUARIOS.get(usuario)

    if not dados:

        return {
            "perfil": "usuario",
            "modulos": []
        }

    return {
        "perfil": dados.get("perfil", "usuario"),
        "modulos": [
            str(modulo)
            for modulo in dados.get("modulos", [])
        ]
    }


def usuario_tem_acesso(usuario, modulo):

    permissoes = obter_permissoes_usuario(usuario)

    return str(modulo) in permissoes["modulos"]


def tem_acesso_modulo(modulo):

    usuario = st.session_state.get(
        "usuario_logado"
    )

    if not usuario:
        return False

    return usuario_tem_acesso(
        usuario,
        modulo
    )


def obter_modulos_usuario():

    usuario = st.session_state.get(
        "usuario_logado"
    )

    if not usuario:
        return []

    return obter_permissoes_usuario(
        usuario
    )["modulos"]


# ============================================================
# CRIAÇÃO DO TOKEN
# ============================================================

def criar_token(usuario, perfil=None):

    agora = datetime.now(timezone.utc)

    expiracao = (
        agora
        + timedelta(hours=TEMPO_SESSAO_HORAS)
    )

    permissoes = obter_permissoes_usuario(
        usuario
    )

    # Se perfil não foi informado,
    # utiliza o perfil cadastrado.
    if perfil is None:
        perfil = permissoes["perfil"]

    dados = {

        "usuario": str(usuario),

        "perfil": str(perfil),

        "modulos": permissoes["modulos"],

        "expira_em": expiracao.isoformat(),

        "nonce": secrets.token_hex(16),
    }

    conteudo = json.dumps(
        dados,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assinatura = gerar_assinatura(
        conteudo
    )

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

def validar_token(token):

    try:

        if not token:
            return None

        token_data = json.loads(token)

        conteudo = token_data.get(
            "dados"
        )

        assinatura_recebida = (
            token_data.get("assinatura")
        )

        if (
            not conteudo
            or not assinatura_recebida
        ):
            return None

        assinatura_correta = gerar_assinatura(
            conteudo
        )

        if not hmac.compare_digest(
            str(assinatura_recebida),
            assinatura_correta,
        ):
            return None

        dados = json.loads(
            conteudo
        )

        expira_em = datetime.fromisoformat(
            dados["expira_em"]
        )

        if expira_em.tzinfo is None:

            expira_em = expira_em.replace(
                tzinfo=timezone.utc
            )

        if datetime.now(timezone.utc) >= expira_em:

            return None

        if not dados.get("usuario"):

            return None

        # ----------------------------------------------------
        # Recupera as permissões atuais do usuário.
        #
        # Isso é proposital.
        #
        # Assim, se você alterar a permissão do usuário
        # no código, ela não fica presa ao token antigo.
        # ----------------------------------------------------

        usuario = str(
            dados["usuario"]
        )

        permissoes = obter_permissoes_usuario(
            usuario
        )

        dados["perfil"] = permissoes[
            "perfil"
        ]

        dados["modulos"] = permissoes[
            "modulos"
        ]

        return dados

    except Exception:

        return None


# ============================================================
# LOGIN
# ============================================================

def fazer_login(usuario, perfil=None):

    controller = get_controller()

    usuario = str(usuario)

    permissoes = obter_permissoes_usuario(
        usuario
    )

    if perfil is None:

        perfil = permissoes["perfil"]

    token = criar_token(
        usuario,
        perfil
    )

    controller.set(

        COOKIE_NAME,

        token,

        max_age=(
            TEMPO_SESSAO_HORAS
            * 60
            * 60
        ),
    )

    st.session_state[
        "autenticado"
    ] = True

    st.session_state[
        "usuario_logado"
    ] = usuario

    st.session_state[
        "perfil"
    ] = perfil

    st.session_state[
        "modulos"
    ] = permissoes["modulos"]

    return True


# ============================================================
# COOKIE
# ============================================================

def obter_cookie():

    try:

        return get_controller().get(
            COOKIE_NAME
        )

    except Exception:

        return None


# ============================================================
# AUTENTICAÇÃO
# ============================================================

def verificar_autenticacao():

    # --------------------------------------------------------
    # Sessão já autenticada
    # --------------------------------------------------------

    if st.session_state.get(
        "autenticado"
    ) is True:

        usuario = st.session_state.get(
            "usuario_logado"
        )

        if usuario:

            permissoes = (
                obter_permissoes_usuario(
                    usuario
                )
            )

            st.session_state[
                "perfil"
            ] = permissoes["perfil"]

            st.session_state[
                "modulos"
            ] = permissoes["modulos"]

        return True

    # --------------------------------------------------------
    # Recupera cookie
    # --------------------------------------------------------

    token = obter_cookie()

    if not token:

        return False

    dados = validar_token(
        token
    )

    if not dados:

        try:

            get_controller().remove(
                COOKIE_NAME
            )

        except Exception:

            pass

        return False

    # --------------------------------------------------------
    # Restaura sessão
    # --------------------------------------------------------

    st.session_state[
        "autenticado"
    ] = True

    st.session_state[
        "usuario_logado"
    ] = dados["usuario"]

    st.session_state[
        "perfil"
    ] = dados["perfil"]

    st.session_state[
        "modulos"
    ] = dados.get(
        "modulos",
        []
    )

    return True


# ============================================================
# LOGOUT
# ============================================================

def fazer_logout():

    try:

        get_controller().remove(
            COOKIE_NAME
        )

    except Exception:

        pass

    for key in list(
        st.session_state.keys()
    ):

        del st.session_state[key]
