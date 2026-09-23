import streamlit as st
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time

from streamlit_cookies_controller import CookieController

TEMPO_SESSAO_HORAS = 8
COOKIE_NAME = "coi_auth_token"

def get_controller():
if "cookie_controller" not in st.session_state:
st.session_state["cookie_controller"] = CookieController(
key="coi_auth_controller"
)

```
return st.session_state["cookie_controller"]
```

def obter_secret_key():
chave = st.secrets.get("COI_SECRET_KEY")

```
if not chave:
    raise RuntimeError(
        "A chave COI_SECRET_KEY não foi configurada nos Secrets do Streamlit."
    )

return str(chave)
```

def gerar_assinatura(conteudo):
chave = obter_secret_key()

```
return hmac.new(
    chave.encode("utf-8"),
    conteudo.encode("utf-8"),
    hashlib.sha256,
).hexdigest()
```

def criar_token(usuario, perfil):
agora = datetime.now(timezone.utc)

```
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

def validar_token(token):
try:
if not token:
return None

```
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

def fazer_login(usuario, perfil):
controller = get_controller()

```
token = criar_token(
    usuario=usuario,
    perfil=perfil,
)

controller.set(
    COOKIE_NAME,
    token,
    max_age=TEMPO_SESSAO_HORAS * 60 * 60,
)

st.session_state["autenticado"] = True
st.session_state["usuario_logado"] = usuario
st.session_state["perfil"] = perfil

return True
```

def obter_cookie():
controller = get_controller()

```
try:
    token = controller.get(COOKIE_NAME)

    if token:
        return token

except Exception:
    pass

return None
```

def verificar_autenticacao():
if st.session_state.get("autenticado") is True:
return True

```
token = obter_cookie()

if token:
    dados = validar_token(token)

    if dados:
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

    try:
        get_controller().remove(COOKIE_NAME)
    except Exception:
        pass

    return False

tentativas = st.session_state.get(
    "_auth_tentativas_cookie",
    0,
)

if tentativas < 3:
    st.session_state["_auth_tentativas_cookie"] = tentativas + 1

    time.sleep(0.5)

    st.rerun()

st.session_state["_auth_tentativas_cookie"] = 0

return False
```

def fazer_logout():
try:
get_controller().remove(COOKIE_NAME)
except Exception:
pass

```
keys_to_delete = [
    key
    for key in list(st.session_state.keys())
    if key != "cookie_controller"
]

for key in keys_to_delete:
    del st.session_state[key]
```
