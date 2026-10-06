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
# PERMISSÕES POR PERFIL
# ============================================================
#
# ADMIN
# Acesso total aos módulos disponíveis.
#
# USUARIO
# Acesso aos módulos 1, 2, 4, 5 e 6.
#
# OPERADOR
# Acesso SOMENTE ao módulo 1.
#
# ============================================================

PERMISSOES_PERFIS = {

    "admin": [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    ],

    "usuario": [
        "1",
        "2",
        "4",
        "5",
        "6",
    ],

    "operador": [
        "1",
    ],
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

        st.session_state[
            "cookie_controller"
        ] = controller

    return controller


# ============================================================
# SECRET KEY
# ============================================================

def obter_secret_key():

    chave = st.secrets.get(
        "COI_SECRET_KEY"
    )

    if not chave:

        raise RuntimeError(
            "A chave COI_SECRET_KEY não foi "
            "configurada nos Secrets do Streamlit."
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
# OBTER MÓDULOS DO PERFIL
# ============================================================

def obter_modulos_perfil(perfil):

    perfil = str(
        perfil or ""
    ).lower().strip()

    return [
        str(modulo)
        for modulo in PERMISSOES_PERFIS.get(
            perfil,
            [],
        )
    ]


# ============================================================
# VERIFICAR ACESSO AO MÓDULO
# ============================================================

def tem_acesso_modulo(modulo):

    perfil = st.session_state.get(
        "perfil",
        "",
    )

    if not perfil:
        return False

    modulos = obter_modulos_perfil(
        perfil
    )

    return str(modulo) in modulos


# ============================================================
# OBTER MÓDULOS DO USUÁRIO LOGADO
# ============================================================

def obter_modulos_usuario():

    perfil = st.session_state.get(
        "perfil",
        "",
    )

    return obter_modulos_perfil(
        perfil
    )


# ============================================================
# CRIAR TOKEN
# ============================================================

def criar_token(
    usuario,
    perfil,
):

    agora = datetime.now(
        timezone.utc
    )

    expiracao = (
        agora
        + timedelta(
            hours=TEMPO_SESSAO_HORAS
        )
    )

    usuario = str(
        usuario
    )

    perfil = str(
        perfil
    ).lower().strip()

    modulos = obter_modulos_perfil(
        perfil
    )

    dados = {

        "usuario": usuario,

        "perfil": perfil,

        "modulos": modulos,

        "expira_em": expiracao.isoformat(),

        "nonce": secrets.token_hex(
            16
        ),
    }

    conteudo = json.dumps(
        dados,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
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
        separators=(
            ",",
            ":",
        ),
    )


# ============================================================
# VALIDAR TOKEN
# ============================================================

def validar_token(token):

    try:

        if not token:
            return None

        token_data = json.loads(
            token
        )

        conteudo = token_data.get(
            "dados"
        )

        assinatura_recebida = (
            token_data.get(
                "assinatura"
            )
        )

        if (
            not conteudo
            or not assinatura_recebida
        ):
            return None

        assinatura_correta = (
            gerar_assinatura(
                conteudo
            )
        )

        if not hmac.compare_digest(
            str(
                assinatura_recebida
            ),
            assinatura_correta,
        ):
            return None

        dados = json.loads(
            conteudo
        )

        # ----------------------------------------------------
        # VALIDAR EXPIRAÇÃO
        # ----------------------------------------------------

        expira_em = datetime.fromisoformat(
            dados["expira_em"]
        )

        if expira_em.tzinfo is None:

            expira_em = expira_em.replace(
                tzinfo=timezone.utc
            )

        if (
            datetime.now(
                timezone.utc
            )
            >= expira_em
        ):

            return None

        # ----------------------------------------------------
        # VALIDAR USUÁRIO
        # ----------------------------------------------------

        usuario = dados.get(
            "usuario"
        )

        if not usuario:

            return None

        # ----------------------------------------------------
        # VALIDAR PERFIL
        # ----------------------------------------------------

        perfil = dados.get(
            "perfil"
        )

        if not perfil:

            return None

        perfil = str(
            perfil
        ).lower().strip()

        # ----------------------------------------------------
        # IMPORTANTE:
        #
        # As permissões são recalculadas a partir do perfil
        # atual, em vez de confiar somente no cookie.
        # ----------------------------------------------------

        modulos = obter_modulos_perfil(
            perfil
        )

        # Perfil inexistente = sem acesso
        if perfil not in PERMISSOES_PERFIS:

            return None

        dados["perfil"] = perfil

        dados["modulos"] = modulos

        return dados

    except Exception:

        return None


# ============================================================
# FAZER LOGIN
# ============================================================

def fazer_login(
    usuario,
    perfil,
):

    usuario = str(
        usuario
    )

    perfil = str(
        perfil
    ).lower().strip()

    # --------------------------------------------------------
    # Não permite login com perfil inexistente
    # --------------------------------------------------------

    if perfil not in PERMISSOES_PERFIS:

        return False

    controller = get_controller()

    # --------------------------------------------------------
    # Criar token
    # --------------------------------------------------------

    token = criar_token(
        usuario,
        perfil,
    )

    # --------------------------------------------------------
    # Salvar cookie
    # --------------------------------------------------------

    controller.set(
        COOKIE_NAME,
        token,
        max_age=(
            TEMPO_SESSAO_HORAS
            * 60
            * 60
        ),
    )

    # --------------------------------------------------------
    # Salvar sessão
    # --------------------------------------------------------

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
    ] = obter_modulos_perfil(
        perfil
    )

    return True


# ============================================================
# OBTER COOKIE
# ============================================================

def obter_cookie():

    try:

        return get_controller().get(
            COOKIE_NAME
        )

    except Exception:

        return None


# ============================================================
# VERIFICAR AUTENTICAÇÃO
# ============================================================

def verificar_autenticacao():

    # --------------------------------------------------------
    # Se a sessão atual já está autenticada
    # --------------------------------------------------------

    if (
        st.session_state.get(
            "autenticado"
        )
        is True
    ):

        perfil = st.session_state.get(
            "perfil",
            "",
        )

        # Recalcular permissões
        st.session_state[
            "modulos"
        ] = obter_modulos_perfil(
            perfil
        )

        return True

    # --------------------------------------------------------
    # Tentar recuperar cookie
    # --------------------------------------------------------

    token = obter_cookie()

    if not token:

        return False

    # --------------------------------------------------------
    # Validar cookie
    # --------------------------------------------------------

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
    # Restaurar sessão
    # --------------------------------------------------------

    st.session_state[
        "autenticado"
    ] = True

    st.session_state[
        "usuario_logado"
    ] = dados[
        "usuario"
    ]

    st.session_state[
        "perfil"
    ] = dados[
        "perfil"
    ]

    st.session_state[
        "modulos"
    ] = dados.get(
        "modulos",
        [],
    )

    return True


# ============================================================
# LOGOUT
# ============================================================

def fazer_logout():

    # --------------------------------------------------------
    # Remover cookie
    # --------------------------------------------------------

    try:

        get_controller().remove(
            COOKIE_NAME
        )

    except Exception:

        pass

    # --------------------------------------------------------
    # Limpar sessão
    # --------------------------------------------------------

    for key in list(
        st.session_state.keys()
    ):

        del st.session_state[
            key
        ]
