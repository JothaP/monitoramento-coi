import re
import unicodedata

import pandas as pd
import streamlit as st

from ..estado import (
obter_base,
base_carregada,
limpar_resultado,
)
from ..exportacao import dataframe_para_excel
from ..zonas import obter_zona
from .componentes import selecionar_modo_api_the

TIPO_ENCERRAMENTO = 6

COLUNAS_LOTE = [
"Matricula",
"Zona Ligacao",
"Numero Do Pedido",
"Ano Do Pedido",
"Tipo Encerramento",
"Observações",
]

def normalizar_texto(valor):
if valor is None:
return ""

```
if pd.isna(valor):
    return ""

texto = str(valor).strip().upper()

texto = unicodedata.normalize(
    "NFKD",
    texto,
).encode(
    "ASCII",
    "ignore",
).decode(
    "ASCII"
)

texto = re.sub(r"\s+", " ", texto)

return texto.strip()
```

def encontrar_coluna(df, nomes):
if df is None or df.empty:
return None

```
mapa = {
    normalizar_texto(coluna): coluna
    for coluna in df.columns
}

for nome in nomes:
    chave = normalizar_texto(nome)

    if chave in mapa:
        return mapa[chave]

return None
```

def normalizar_numero(valor):
if valor is None or pd.isna(valor):
return None

```
texto = str(valor).strip()

if not texto:
    return None

texto = texto.replace(",", ".")

try:
    numero = float(texto)

    if numero.is_integer():
        return str(int(numero))

except (ValueError, TypeError):
    pass

numeros = re.findall(r"\d+", texto)

if not numeros:
    return None

return str(int("".join(numeros)))
```

def normalizar_ano(valor):
if valor is None or pd.isna(valor):
return None

```
texto = str(valor).strip()

if not texto:
    return None

match = re.search(r"(19|20)\d{2}", texto)

if match:
    return match.group(0)

try:
    numero = float(texto)

    if numero.is_integer():
        numero = int(numero)

        if 1900 <= numero <= 2100:
            return str(numero)

except (ValueError, TypeError):
    pass

return None
```

def parse_protocolo(valor):
texto = str(valor).strip()

```
if not texto:
    return None, None

texto = re.sub(r"\s+", "", texto)

match = re.fullmatch(
    r"(\d+)\s*/\s*(\d{4})",
    texto,
)

if match:
    return (
        str(int(match.group(1))),
        match.group(2),
    )

match = re.fullmatch(
    r"(\d+)",
    texto,
)

if match:
    return (
        str(int(match.group(1))),
        None,
    )

match = re.search(
    r"(\d+)\s*/\s*(\d{4})",
    texto,
)

if match:
    return (
        str(int(match.group(1))),
        match.group(2),
    )

match = re.search(
    r"\d+",
    texto,
)

if match:
    return (
        str(int(match.group(0))),
        None,
    )

return None, None
```

def extrair_protocolos(texto):
if not texto:
return []

```
partes = re.split(
    r"[\n,;]+",
    str(texto),
)

protocolos = []

for parte in partes:
    parte = parte.strip()

    if not parte:
        continue

    numero, ano = parse_protocolo(parte)

    if numero is None:
        protocolos.append(
            {
                "entrada": parte,
                "numero": None,
                "ano": None,
                "valido": False,
            }
        )
        continue

    protocolos.append(
        {
            "entrada": parte,
            "numero": numero,
            "ano": ano,
            "valido": True,
        }
    )

return protocolos
```

def preparar_backlog(df):
if df is None or df.empty:
return None, None

```
col_numero = encontrar_coluna(
    df,
    [
        "COD. PROTOCOLO ORIGEM",
        "COD PROTOCOLO ORIGEM",
        "CODIGO PROTOCOLO ORIGEM",
    ],
)

col_ano = encontrar_coluna(
    df,
    [
        "ANO",
        "ANO DO PEDIDO",
        "ANO PEDIDO",
    ],
)

col_matricula = encontrar_coluna(
    df,
    [
        "MATRICULA",
        "MATRÍCULA",
    ],
)

col_cidade = encontrar_coluna(
    df,
    [
        "CIDADE",
        "MUNICIPIO",
        "MUNICÍPIO",
    ],
)

if col_numero is None:
    return None, (
        "A base selecionada não possui a coluna "
        "'COD. PROTOCOLO ORIGEM'."
    )

if col_matricula is None:
    return None, (
        "A base selecionada não possui a coluna "
        "'MATRICULA'."
    )

if col_cidade is None:
    return None, (
        "A base selecionada não possui a coluna "
        "'CIDADE'."
    )

base = df.copy()

base["_numero_lista_rapida"] = base[
    col_numero
].apply(normalizar_numero)

if col_ano is not None:
    base["_ano_lista_rapida"] = base[
        col_ano
    ].apply(normalizar_ano)
else:
    base["_ano_lista_rapida"] = None

base["_matricula_lista_rapida"] = base[
    col_matricula
]

base["_cidade_lista_rapida"] = base[
    col_cidade
]

base = base[
    base["_numero_lista_rapida"].notna()
].copy()

return base, None
```

def cruzar_lista_com_backlog(
protocolos,
df_backlog,
modo,
observacoes,
):
base, erro = preparar_backlog(df_backlog)

```
if erro:
    return (
        pd.DataFrame(columns=COLUNAS_LOTE),
        [],
        [],
        erro,
    )

if base is None or base.empty:
    return (
        pd.DataFrame(columns=COLUNAS_LOTE),
        [],
        [],
        "A base selecionada não possui registros válidos.",
    )

resultado = []

encontrados = 0
nao_encontrados = []
entradas_invalidas = []

processados = set()

for item in protocolos:
    entrada = item["entrada"]
    numero = item["numero"]
    ano = item["ano"]

    if not item["valido"] or numero is None:
        entradas_invalidas.append(entrada)
        continue

    chave_entrada = (
        numero,
        ano,
    )

    if chave_entrada in processados:
        continue

    processados.add(chave_entrada)

    candidato = base[
        base["_numero_lista_rapida"] == numero
    ]

    if ano is not None:
        candidato_ano = candidato[
            candidato["_ano_lista_rapida"] == ano
        ]

        if not candidato_ano.empty:
            candidato = candidato_ano

    if candidato.empty:
        nao_encontrados.append(
            entrada
        )
        continue

    linha = candidato.iloc[0]

    cidade = linha[
        "_cidade_lista_rapida"
    ]

    if modo == "THE":
        zona = 1
    else:
        zona = obter_zona(cidade)

    if zona is None:
        nao_encontrados.append(
            f"{entrada} — cidade sem zona: {cidade}"
        )
        continue

    matricula = linha[
        "_matricula_lista_rapida"
    ]

    ano_final = linha[
        "_ano_lista_rapida"
    ]

    if ano_final is None:
        ano_final = ano

    resultado.append(
        {
            "Matricula": matricula,
            "Zona Ligacao": zona,
            "Numero Do Pedido": numero,
            "Ano Do Pedido": ano_final,
            "Tipo Encerramento": TIPO_ENCERRAMENTO,
            "Observações": observacoes,
        }
    )

    encontrados += 1

df_resultado = pd.DataFrame(
    resultado,
    columns=COLUNAS_LOTE,
)

return (
    df_resultado,
    nao_encontrados,
    entradas_invalidas,
    None,
)
```

def limpar_estado_lista_rapida():
chaves = [
"lista_rapida_resultado",
"lista_rapida_log",
"lista_rapida_nome_arquivo",
"lista_rapida_protocolos",
"lista_rapida_observacoes",
"lista_rapida_geracao_info",
]

```
for chave in chaves:
    if chave in st.session_state:
        st.session_state[chave] = None
```

def aplicar_estilo_lista_rapida():
st.markdown(
""" <style>
.lista-rapida-card {
border: 1px solid rgba(128, 128, 128, 0.25);
border-radius: 12px;
padding: 18px;
margin-bottom: 18px;
}

```
    .lista-rapida-titulo {
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .lista-rapida-subtitulo {
        color: #888;
        font-size: 0.9rem;
        margin-bottom: 12px;
    }

    .lista-rapida-metricas {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin: 12px 0 18px 0;
    }

    .lista-rapida-metrica {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 10px;
        padding: 10px 16px;
        min-width: 150px;
    }

    .lista-rapida-metrica-label {
        font-size: 0.8rem;
        opacity: 0.7;
    }

    .lista-rapida-metrica-valor {
        font-size: 1.35rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
```

def render_lista_rapida():
aplicar_estilo_lista_rapida()

```
st.markdown(
    "## 📋 Lista Rápida"
)

st.caption(
    "Geração de lote de cancelamento a partir de uma lista de O.S./protocolos."
)

if not base_carregada("api") and not base_carregada("the"):
    st.warning(
        "Nenhuma base de operação disponível. "
        "Carregue a base API e/ou THE no Hub."
    )

    if st.button(
        "⬅️ Voltar ao Gerador de Lotes",
        use_container_width=False,
    ):
        st.session_state["ferramenta_atual"] = None
        st.rerun()

    return

if "lista_rapida_resultado" not in st.session_state:
    st.session_state["lista_rapida_resultado"] = None

if "lista_rapida_log" not in st.session_state:
    st.session_state["lista_rapida_log"] = None

if "lista_rapida_nome_arquivo" not in st.session_state:
    st.session_state["lista_rapida_nome_arquivo"] = None

if "lista_rapida_protocolos" not in st.session_state:
    st.session_state["lista_rapida_protocolos"] = ""

if "lista_rapida_observacoes" not in st.session_state:
    st.session_state["lista_rapida_observacoes"] = ""

modo, df_backlog = selecionar_modo_api_the(
    key="lista_rapida_modo",
    titulo="Base de operação",
    limpar_resultado_callback=limpar_estado_lista_rapida,
)

if modo is None or df_backlog is None:
    return

st.markdown(
    '<div class="lista-rapida-card">',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="lista-rapida-titulo">📋 Lista de protocolos</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="lista-rapida-subtitulo">'
    "Informe uma O.S./protocolo por linha ou separe os registros por vírgula."
    "</div>",
    unsafe_allow_html=True,
)

protocolos_texto = st.text_area(
    "Protocolos / O.S.",
    height=230,
    placeholder=(
        "Exemplo:\n"
        "123456/2026\n"
        "123457/2026\n"
        "123458/2026"
    ),
    key="lista_rapida_protocolos",
    label_visibility="visible",
)

st.markdown(
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="lista-rapida-card">',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="lista-rapida-titulo">📝 Observações</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="lista-rapida-subtitulo">'
    "Texto definido livremente pelo usuário e aplicado ao lote gerado."
    "</div>",
    unsafe_allow_html=True,
)

observacoes = st.text_area(
    "Observações do lote",
    height=120,
    placeholder="Digite a observação que deverá constar no lote.",
    key="lista_rapida_observacoes",
    label_visibility="visible",
)

st.markdown(
    "</div>",
    unsafe_allow_html=True,
)

st.markdown("### 📦 Geração do lote")

if st.button(
    "⚙️ Gerar lote",
    type="primary",
    use_container_width=True,
):
    limpar_estado_lista_rapida()

    if not protocolos_texto.strip():
        st.warning(
            "Informe pelo menos uma O.S./protocolo."
        )
        st.stop()

    protocolos = extrair_protocolos(
        protocolos_texto
    )

    if not protocolos:
        st.warning(
            "Nenhum protocolo válido foi identificado."
        )
        st.stop()

    (
        df_resultado,
        nao_encontrados,
        entradas_invalidas,
        erro,
    ) = cruzar_lista_com_backlog(
        protocolos=protocolos,
        df_backlog=df_backlog,
        modo=modo,
        observacoes=observacoes,
    )

    if erro:
        st.error(erro)
        st.stop()

    st.session_state[
        "lista_rapida_resultado"
    ] = df_resultado

    st.session_state[
        "lista_rapida_log"
    ] = {
        "nao_encontrados": nao_encontrados,
        "entradas_invalidas": entradas_invalidas,
        "total_informado": len(protocolos),
        "total_gerado": len(df_resultado),
    }

    nome_base = (
        "API"
        if modo == "API"
        else "THE"
    )

    st.session_state[
        "lista_rapida_nome_arquivo"
    ] = f"Lista Rapida {nome_base}.xlsx"

    st.session_state[
        "lista_rapida_geracao_info"
    ] = {
        "modo": modo,
        "total_informado": len(protocolos),
        "total_gerado": len(df_resultado),
    }

    st.rerun()

df_resultado = st.session_state.get(
    "lista_rapida_resultado"
)

log = st.session_state.get(
    "lista_rapida_log"
)

if df_resultado is not None:
    st.markdown("---")

    st.markdown("### 📊 Prévia do lote")

    total_informado = (
        log.get("total_informado", 0)
        if log
        else 0
    )

    total_gerado = (
        len(df_resultado)
    )

    nao_encontrados = (
        log.get("nao_encontrados", [])
        if log
        else []
    )

    entradas_invalidas = (
        log.get("entradas_invalidas", [])
        if log
        else []
    )

    st.markdown(
        '<div class="lista-rapida-metricas">'
        f'<div class="lista-rapida-metrica">'
        '<div class="lista-rapida-metrica-label">'
        "Informados"
        "</div>"
        f'<div class="lista-rapida-metrica-valor">'
        f"{total_informado}"
        "</div>"
        "</div>"
        f'<div class="lista-rapida-metrica">'
        '<div class="lista-rapida-metrica-label">'
        "Gerados"
        "</div>"
        f'<div class="lista-rapida-metrica-valor">'
        f"{total_gerado}"
        "</div>"
        "</div>"
        f'<div class="lista-rapida-metrica">'
        '<div class="lista-rapida-metrica-label">'
        "Não encontrados"
        "</div>"
        f'<div class="lista-rapida-metrica-valor">'
        f"{len(nao_encontrados)}"
        "</div>"
        "</div>"
        f'<div class="lista-rapida-metrica">'
        '<div class="lista-rapida-metrica-label">'
        "Inválidos"
        "</div>"
        f'<div class="lista-rapida-metrica-valor">'
        f"{len(entradas_invalidas)}"
        "</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if entradas_invalidas:
        st.warning(
            "Entradas não reconhecidas como protocolo: "
            + ", ".join(
                str(item)
                for item in entradas_invalidas
            )
        )

    if nao_encontrados:
        st.warning(
            "O.S. não encontrada: "
            + ", ".join(
                str(item)
                for item in nao_encontrados
            )
        )

    if df_resultado.empty:
        st.error(
            "Nenhum registro da lista foi encontrado no backlog."
        )
    else:
        st.dataframe(
            df_resultado,
            use_container_width=True,
            hide_index=True,
        )

        arquivo = dataframe_para_excel(
            df_resultado,
            nome_aba="Lista Rápida",
        )

        if arquivo is not None:
            st.download_button(
                label="⬇️ Baixar lote",
                data=arquivo.getvalue(),
                file_name=st.session_state.get(
                    "lista_rapida_nome_arquivo",
                    "Lista Rapida.xlsx",
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "🧹 Limpar resultado",
            use_container_width=True,
        ):
            limpar_resultado()
            limpar_estado_lista_rapida()
            st.rerun()

    with col2:
        if st.button(
            "⬅️ Voltar",
            use_container_width=True,
        ):
            limpar_resultado()
            limpar_estado_lista_rapida()
            st.session_state[
                "ferramenta_atual"
            ] = None
            st.rerun()
else:
    st.markdown("---")

    if st.button(
        "⬅️ Voltar",
        use_container_width=False,
    ):
        st.session_state[
            "ferramenta_atual"
        ] = None
        st.rerun()
```
