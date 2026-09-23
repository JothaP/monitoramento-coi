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
COOKIE_MANAGER_KEY = "coi_cookie_manager"

# ============================================================

# CHAVE DE SEGURANÇA

# ============================================================

def obter_secret_key() -> str:
"""
Obtém a chave secreta utilizada para assinar os cookies.

```
A chave deve estar configurada nos Secrets do Streamlit:

    COI_SECRET_KEY = "sua_chave_secreta"

Essa chave NÃO deve ser colocada no código nem publicada
no GitHub.
"""

chave = st.secrets.get("COI_SECRET_KEY")

if not chave:
    raise RuntimeError(
        "A chave COI_SECRET_KEY não foi configurada "
        "nos Secrets do Streamlit."
    )

return str(chave)
```

# ============================================================

# COOKIE MANAGER

# ============================================================

def get_manager():
"""
Cria o CookieManager uma única vez durante a sessão
atual do Streamlit.
"""

```
if "cookie_manager" not in st.session_state:
    st.session_state["cookie_manager"] = stx.CookieManager(
        key=COOKIE_MANAGER_KEY
    )

return st.session_state["cookie_manager"]
```

# ============================================================

# ASSINATURA HMAC

# ============================================================

def gerar_assinatura(conteudo: str) -> str:
"""
Gera uma assinatura HMAC-SHA256 para o conteúdo do token.
"""

```
chave = obter_secret_key()

return hmac.new(
    chave.encode("utf-8"),
    conteudo.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
```

# ============================================================

# CRIAÇÃO DO TOKEN

# ============================================================

def criar_token(usuario: str, perfil: str) -> str:
"""
Cria um token de autenticação válido por 8 horas.
"""

```
agora = datetime.now(timezone.utc)

expiracao = agora + timedelta(
    hours=TEMPO_SESSAO_HORAS
)

dados = {
    "usuario": str(usuario),
    "perfil": str(perfil),
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
```

# ============================================================

# VALIDAÇÃO DO TOKEN

# ============================================================

def validar_token(token: str):
"""
Valida a assinatura e a validade do token.

```
Retorna os dados do usuário quando o token é válido.
Retorna None quando o token é inválido ou expirado.
"""

try:
    if not token:
        return None

    token_data = json.loads(token)

    if not isinstance(token_data, dict):
        return None

    conteudo = token_data.get("dados")
    assinatura_recebida = token_data.get("assinatura")

    if not conteudo or not assinatura_recebida:
        return None

    assinatura_correta = gerar_assinatura(conteudo)

    if not hmac.compare_digest(
        str(assinatura_recebida),
        assinatura_correta,
    ):
        return None

    dados = json.loads(conteudo)

    if not isinstance(dados, dict):
        return None

    expira_em_texto = dados.get("expira_em")

    if not expira_em_texto:
        return None

    expira_em = datetime.fromisoformat(
        expira_em_texto
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
```

# ============================================================

# LOGIN

# ============================================================

def fazer_login(usuario: str, perfil: str):
"""
Realiza o login e inicia uma nova sessão de 8 horas.
"""

```
cookie_manager = get_manager()

token = criar_token(
    usuario=usuario,
    perfil=perfil,
)

expiracao_cookie = (
    datetime.now(timezone.utc)
    + timedelta(hours=TEMPO_SESSAO_HORAS)
)

try:
    cookie_manager.set(
        COOKIE_NAME,
        token,
        expires_at=expiracao_cookie,
    )
except Exception:
    return False

st.session_state["autenticado"] = True
st.session_state["usuario_logado"] = usuario
st.session_state["perfil"] = perfil

st.session_state["login_realizado"] = True

return True
```

# ============================================================

# OBTENÇÃO DO COOKIE

# ============================================================

def obter_cookie_autenticacao():
"""
Recupera o cookie de autenticação do navegador.

```
Tenta primeiro obter todos os cookies e depois utiliza
get() como fallback.
"""

cookie_manager = get_manager()

try:
    cookies = cookie_manager.get_all()

    if isinstance(cookies, dict):
        token = cookies.get(COOKIE_NAME)

        if token:
            return token

except Exception:
    pass

try:
    token = cookie_manager.get(COOKIE_NAME)

    if token:
        return token

except Exception:
    pass

return None
```

# ============================================================

# VERIFICAÇÃO DA AUTENTICAÇÃO

# ============================================================

def verificar_autenticacao() -> bool:
"""
Verifica se existe uma sessão autenticada.

```
Primeiro verifica o session_state.

Caso o session_state tenha sido perdido, tenta recuperar
a sessão através do cookie persistente do navegador.

A sessão possui validade de 8 horas a partir do login.
"""

# --------------------------------------------------------
# Sessão atual
# --------------------------------------------------------

if st.session_state.get("autenticado") is True:
    return True

# --------------------------------------------------------
# Login recém-realizado
# --------------------------------------------------------

if st.session_state.get("login_realizado") is True:
    st.session_state["autenticado"] = True
    return True

# --------------------------------------------------------
# Recuperação pelo cookie
# --------------------------------------------------------

cookie = obter_cookie_autenticacao()

if not cookie:
    return False

# --------------------------------------------------------
# Validação
# --------------------------------------------------------

dados = validar_token(cookie)

if not dados:

    try:
        cookie_manager = get_manager()
        cookie_manager.delete(COOKIE_NAME)
    except Exception:
        pass

    return False

# --------------------------------------------------------
# Restauração da sessão
# --------------------------------------------------------

st.session_state["autenticado"] = True

st.session_state["usuario_logado"] = dados.get(
    "usuario",
    "",
)

st.session_state["perfil"] = dados.get(
    "perfil",
    "",
)

return True
```

# ============================================================

# LOGOUT

# ============================================================

def fazer_logout():
"""
Encerra a sessão atual.

```
Remove o cookie de autenticação e limpa o session_state.
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
```
