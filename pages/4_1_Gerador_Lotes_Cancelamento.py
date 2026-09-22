# ============================================================
# GERADOR DE LOTES DE CANCELAMENTO — HUB OPERACIONAL
# PLATAFORMA COI
#
# PARTE 1/2
#
# Estrutura:
#   - Configuração
#   - Autenticação
#   - Funções auxiliares
#   - Mapa de zonas
#   - Persistência das bases
#   - Carregamento único dos arquivos
#   - HUB de operações
# ============================================================

import streamlit as st
import pandas as pd
import io
import re
import unicodedata
import hashlib

from datetime import datetime, time, timedelta

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Gerador de Lotes de Cancelamento - COI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .hub-card {
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 10px;
        }

        .status-ok {
            color: #16803c;
            font-weight: 600;
        }

        .status-empty {
            color: #888888;
            font-weight: 500;
        }

        .base-title {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 4px;
        }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():

    st.warning("Sessão não iniciada ou expirada.")

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# FUNÇÕES DE NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    if pd.isna(texto):
        return ""

    texto = str(texto)

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.upper().strip()

    texto = re.sub(r"\s+", " ", texto)

    return texto


def normalizar_coluna(coluna):

    return normalizar_texto(coluna)


# ============================================================
# NORMALIZAÇÃO DE CIDADE PARA EVENTOS
# ============================================================

def normalizar_cidade_evento(cidade):

    cidade = normalizar_texto(cidade)

    cidade = re.sub(
        r"^ZONA RURAL\s*-\s*",
        "",
        cidade
    )

    cidade = re.sub(
        r"^POVOADO\s+",
        "",
        cidade
    )

    cidade = re.sub(
        r"^POV\.?\s+",
        "",
        cidade
    )

    equivalencias = {

        "CURRAL NOVO DO PIAUI":
            "CURRAL NOVO PI",

        "SAO LOURENCO DO PIAUI":
            "SAO LOURENCO",

        "OLHO D AGUA DO PIAUI":
            "OLHO D'AGUA DO PIAUI",
    }

    return equivalencias.get(
        cidade,
        cidade
    )


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(proto):

    if pd.isna(proto):
        return "", "", None

    texto = str(proto).strip()

    match = re.search(
        r"(\d+)\s*/\s*(\d{4})",
        texto
    )

    if not match:
        return "", "", None

    numero_str = match.group(1)

    ano_str = match.group(2)

    numero_int = int(numero_str)

    return (
        numero_str,
        ano_str,
        numero_int
    )


# ============================================================
# CONVERSÃO ROBUSTA DE DATAS
# ============================================================

def converter_datas_robusto(serie):

    resultado = []

    for valor in serie:

        if pd.isna(valor):

            resultado.append(pd.NaT)

            continue

        if isinstance(
            valor,
            pd.Timestamp
        ):

            resultado.append(valor)

            continue

        if isinstance(
            valor,
            datetime
        ):

            resultado.append(
                pd.Timestamp(valor)
            )

            continue

        if isinstance(
            valor,
            time
        ):

            resultado.append(pd.NaT)

            continue

        # --------------------------------------------
        # Excel serial date
        # --------------------------------------------

        if isinstance(
            valor,
            (int, float)
        ):

            try:

                if 1 <= float(valor) <= 60000:

                    data = (
                        pd.Timestamp("1899-12-30")
                        + pd.to_timedelta(
                            float(valor),
                            unit="D"
                        )
                    )

                    resultado.append(data)

                    continue

            except Exception:

                pass

        texto = str(valor).strip()

        if not texto:

            resultado.append(pd.NaT)

            continue

        formatos = [

            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",

            "%d/%m/%Y",

            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",

            "%d-%m-%Y",

            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",

            "%Y-%m-%d",
        ]

        convertido = None

        for formato in formatos:

            try:

                convertido = pd.to_datetime(
                    texto,
                    format=formato
                )

                break

            except Exception:

                continue

        if convertido is not None:

            resultado.append(convertido)

            continue

        # --------------------------------------------
        # Último recurso
        # --------------------------------------------

        try:

            convertido = pd.to_datetime(
                texto,
                dayfirst=True,
                errors="coerce"
            )

        except Exception:

            convertido = pd.NaT

        resultado.append(convertido)

    return pd.Series(
        resultado,
        index=serie.index
    )


# ============================================================
# DATA/HORA DE EVENTO
# ============================================================

def parse_data_hora_evento(valor):

    if pd.isna(valor):

        return pd.NaT

    convertido = converter_datas_robusto(
        pd.Series([valor])
    ).iloc[0]

    return convertido


# ============================================================
# EVENTO ATINGE TODO O MUNICÍPIO?
# ============================================================

def evento_eh_todo_municipio(areas_texto):

    texto = normalizar_texto(
        areas_texto
    )

    padroes = [

        "TODO O MUNICIPIO",
        "TODA CIDADE",
        "TODO O POVOADO",
        "TODA A AREA",
        "TODO MUNICIPIO",
        "TODO O MUNICIPIO",
        "MUNICIPIO TODO",
        "CIDADE TODA",
    ]

    for padrao in padroes:

        if padrao in texto:

            return True

    return False


# ============================================================
# BAIRRO APARECE NAS ÁREAS DO EVENTO?
# ============================================================

def bairro_aparece_nas_areas_evento(
    bairro_os,
    areas_texto
):

    bairro = normalizar_texto(
        bairro_os
    )

    areas = normalizar_texto(
        areas_texto
    )

    if not bairro or not areas:

        return False

    if bairro in areas:

        return True

    # --------------------------------------------
    # Equivalências conhecidas
    # --------------------------------------------

    equivalencias = {

        "CENTRO": [
            "CENTRO"
        ],

        "SAO JOSE": [
            "SAO JOSE",
            "SAO JOSE II"
        ],

        "NOVA ESPERANCA": [
            "NOVA ESPERANCA",
            "NOVA ESPERANCA I",
            "NOVA ESPERANCA II"
        ],
    }

    if bairro in equivalencias:

        for equivalente in equivalencias[bairro]:

            if equivalente in areas:

                return True

    # --------------------------------------------
    # Comparação por tokens
    # --------------------------------------------

    tokens_bairro = set(
        bairro.split()
    )

    tokens_areas = set(
        areas.split()
    )

    if tokens_bairro:

        intersecao = (
            tokens_bairro
            & tokens_areas
        )

        percentual = (
            len(intersecao)
            / len(tokens_bairro)
        )

        if percentual >= 0.70:

            return True

    return False


# ============================================================
# LOCALIZAÇÃO DE COLUNAS — BACKLOG
# ============================================================

def localizar_coluna(df, tipo):

    colunas = {
        normalizar_coluna(c): c
        for c in df.columns
    }

    # --------------------------------------------
    # Protocolo
    # --------------------------------------------

    if tipo == "protocolo":

        procurada = normalizar_coluna(
            "COD. PROTOCOLO ORIGEM"
        )

        if procurada in colunas:

            return colunas[procurada]

        for normalizada, original in colunas.items():

            if (
                "PROTOCOLO" in normalizada
                and "ORIGEM" in normalizada
            ):

                return original

    # --------------------------------------------
    # Matrícula
    # --------------------------------------------

    if tipo == "matricula":

        procurada = "MATRICULA"

        if procurada in colunas:

            return colunas[procurada]

        for normalizada, original in colunas.items():

            if "MATRICULA" in normalizada:

                return original

    # --------------------------------------------
    # Cidade
    # --------------------------------------------

    if tipo == "cidade":

        procurada = "CIDADE"

        if procurada in colunas:

            return colunas[procurada]

    # --------------------------------------------
    # Bairro
    # --------------------------------------------

    if tipo == "bairro":

        procurada = "BAIRRO"

        if procurada in colunas:

            return colunas[procurada]

        for normalizada, original in colunas.items():

            if "BAIRRO" in normalizada:

                return original

    # --------------------------------------------
    # Data / SLA
    # --------------------------------------------

    if tipo == "data":

        procurada = "INICIO DO SLA"

        if procurada in colunas:

            return colunas[procurada]

        for normalizada, original in colunas.items():

            if normalizada.startswith(
                "INICIO DO SLA"
            ):

                return original

        for normalizada, original in colunas.items():

            if "INICIO DO SLA" in normalizada:

                return original

    return None


# ============================================================
# LOCALIZAÇÃO DE COLUNAS — EVENTOS
# ============================================================

def localizar_coluna_eventos(
    df,
    candidatos,
    obrigatoria=True
):

    colunas = {
        normalizar_coluna(c): c
        for c in df.columns
    }

    # Primeiro tenta correspondência exata

    for candidato in candidatos:

        chave = normalizar_coluna(
            candidato
        )

        if chave in colunas:

            return colunas[chave]

    # Depois tenta correspondência parcial

    for candidato in candidatos:

        chave = normalizar_coluna(
            candidato
        )

        for normalizada, original in colunas.items():

            if chave in normalizada:

                return original

    if obrigatoria:

        raise ValueError(
            "Não foi possível localizar a coluna "
            f"esperada: {candidatos}"
        )

    return None


# ============================================================
# LOCALIZAÇÃO DE COLUNA DE SERVIÇO
# ============================================================

def localizar_coluna_servico(df):

    candidatos = [

        "DESCRIPTION",
        "DESCRIPTION SERVICE",
        "SERVICE",
        "SERVICO",
        "TIPO",
        "TIPO OS",
        "TIPO DE OS",
        "MOTIVO",
    ]

    return localizar_coluna_eventos(
        df,
        candidatos,
        obrigatoria=True
    )


# ============================================================
# LOCALIZAÇÃO DE COLUNAS — LOTES
# ============================================================

def localizar_coluna_lote(
    df,
    candidatos,
    obrigatoria=True
):

    colunas = {
        normalizar_coluna(c): c
        for c in df.columns
    }

    for candidato in candidatos:

        chave = normalizar_coluna(
            candidato
        )

        if chave in colunas:

            return colunas[chave]

    for candidato in candidatos:

        chave = normalizar_coluna(
            candidato
        )

        for normalizada, original in colunas.items():

            if chave in normalizada:

                return original

    if obrigatoria:

        raise ValueError(
            "Não foi possível localizar a coluna "
            f"esperada: {candidatos}"
        )

    return None


# ============================================================
# LEITURA DE EXCEL
# ============================================================

def ler_excel_bytes(
    nome_arquivo,
    conteudo
):

    extensao = (
        nome_arquivo
        .lower()
        .split(".")[-1]
    )

    if extensao not in [
        "xlsx",
        "xlsm"
    ]:

        raise ValueError(
            f"O arquivo '{nome_arquivo}' "
            "não é um Excel válido. "
            "Use .xlsx ou .xlsm."
        )

    df = pd.read_excel(
        io.BytesIO(conteudo),
        engine="openpyxl"
    )

    # Normaliza espaços dos nomes das colunas

    df.columns = [

        re.sub(
            r"\s+",
            " ",
            str(col).strip()
        )

        for col in df.columns

    ]

    return df


# ============================================================
# REMOVER LINHAS TOTALMENTE VAZIAS
# ============================================================

def remover_linhas_vazias(df):

    if df is None:

        return df

    if df.empty:

        return df.copy()

    mascara_vazia = df.apply(
        lambda linha:
            all(
                pd.isna(valor)
                or str(valor).strip() == ""
                for valor in linha
            ),
        axis=1
    )

    return (
        df.loc[~mascara_vazia]
        .reset_index(drop=True)
    )


# ============================================================
# CONSOLIDAÇÃO DE DATAFRAMES
# ============================================================

def consolidar_lista_dfs(
    lista_dfs,
    mensagem_vazio="Nenhuma base foi carregada."
):

    validos = []

    for df in lista_dfs:

        if df is None:

            continue

        if df.empty:

            continue

        validos.append(
            df.copy()
        )

    if not validos:

        raise ValueError(
            mensagem_vazio
        )

    df = pd.concat(
        validos,
        ignore_index=True,
        sort=False
    )

    df = remover_linhas_vazias(
        df
    )

    if df.empty:

        raise ValueError(
            "Após remover linhas vazias, "
            "não restaram registros."
        )

    quantidade_duplicadas = (
        len(df)
        - len(
            df.drop_duplicates(
                keep="first"
            )
        )
    )

    # IMPORTANTE:
    # somente duplicações EXATAS

    df = df.drop_duplicates(
        keep="first"
    ).reset_index(drop=True)

    return (
        df,
        quantidade_duplicadas
    )


# ============================================================
# SALVAR LOTE EM EXCEL
# ============================================================

def salvar_lote_excel(
    df,
    nome_arquivo=None
):

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Lote"
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# MAPA DE ZONAS
#
# MANTER O MAPA ORIGINAL DO PROJETO AQUI.
#
# A estrutura abaixo permite que o restante do sistema
# continue funcionando mesmo que o mapa seja ampliado.
# ============================================================

MAPA_ZONAS = {

    "ACAUA": 229,
    "AGRICOLANDIA": 1,
    "AGUA BRANCA": 3,

    # --------------------------------------------------------
    # PRINCIPAIS MUNICÍPIOS
    # --------------------------------------------------------

    "TERESINA": 110,
    "PARNAIBA": 77,
    "FLORIANO": 41,
    "PICOS": 81,

    "CAMPO ALEGRE DO FIDALGO": 418,
    "CAMPO GRANDE DO PIAUI": 195,

    # --------------------------------------------------------
    # LOCALIDADES / POVOADOS
    # --------------------------------------------------------

    "POV SANTA TERESA": 158,
    "POV CALDEIRAOZINHO": 287,
    "POVOADO BURITIZINHO": 233,
    "POV COROA DE SAO REMIGIO": 277,
    "POVOADO PEDRA": 157,
    "POVOADO APARECIDA": 143,
    "POV BARRA DO LONGA": 124,
    "POV INGAZEIRA": 330,
    "POV SERRA DA SOLTA": 302,
    "POVOADO BARRA GRANDE": 239,
    "POVOADO SAO JOAQUIM": 210,
    "POVOADO TRANQUEIRA": 235,
    "POV MOCAMBINHO": 148,
    "POV BURITI DO CASTELO": 189,
    "POVOADO MANDACARU": 288,
    "POVOADO MATINHA": 183,
    "POV DAVID CALDAS": 119,
    "POV. LAGOA DE BAIXO": 331,

    # ========================================================
    # IMPORTANTE
    #
    # CAMPO MAIOR NÃO POSSUI ZONA DEFINIDA.
    #
    # Não adicionar automaticamente uma zona para ele.
    # ========================================================
}


MAPA_ZONAS_NORMALIZADO = {

    normalizar_texto(cidade): zona

    for cidade, zona
    in MAPA_ZONAS.items()

}


def obter_zona(cidade):

    cidade_normalizada = (
        normalizar_texto(cidade)
    )

    return MAPA_ZONAS_NORMALIZADO.get(
        cidade_normalizada
    )


# ============================================================
# OBTENÇÃO DE VALORES ÚNICOS
# ============================================================

def obter_valores_unicos(
    df,
    coluna
):

    if (
        df is None
        or df.empty
        or coluna not in df.columns
    ):

        return []

    valores = []

    vistos = set()

    for valor in df[coluna].dropna():

        texto = str(valor).strip()

        if not texto:

            continue

        normalizado = normalizar_texto(
            texto
        )

        if normalizado in [
            "",
            "NAN",
            "NONE",
            "NULL"
        ]:

            continue

        if normalizado in vistos:

            continue

        vistos.add(
            normalizado
        )

        valores.append(
            texto
        )

    return sorted(
        valores,
        key=normalizar_texto
    )


# ============================================================
# CONVERSÃO DE HORA
# ============================================================

def converter_hora(valor):

    if valor is None:

        raise ValueError(
            "Horário não informado."
        )

    texto = str(valor).strip()

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        texto
    )

    if not match:

        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Use HH:MM."
        )

    hora = int(
        match.group(1)
    )

    minuto = int(
        match.group(2)
    )

    if not 0 <= hora <= 23:

        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "A hora deve estar entre 00 e 23."
        )

    if not 0 <= minuto <= 59:

        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Os minutos devem estar entre 00 e 59."
        )

    return time(
        hour=hora,
        minute=minuto
    )


# ============================================================
# EXTRAÇÃO DE LISTA RÁPIDA
# ============================================================

def extrair_lista_os(texto_raw):

    if texto_raw is None:

        return []

    texto = str(
        texto_raw
    )

    partes = re.split(
        r"[,;\s]+",
        texto
    )

    resultado = []

    vistos = set()

    for parte in partes:

        parte = parte.strip()

        if not parte:

            continue

        chave = normalizar_texto(
            parte
        )

        if chave in vistos:

            continue

        vistos.add(
            chave
        )

        resultado.append(
            parte
        )

    return resultado


# ============================================================
# ASSINATURA DOS ARQUIVOS
#
# Essa é uma das partes MAIS IMPORTANTES da nova arquitetura.
#
# O Streamlit executa o script novamente sempre que o usuário
# interage com a tela.
#
# Portanto, não podemos simplesmente fazer:
#
#     ler_excel(...)
#
# toda vez que o script for executado.
#
# A assinatura identifica se o conjunto de arquivos realmente
# mudou.
# ============================================================

def assinatura_arquivo(arquivo):

    if arquivo is None:

        return None

    conteudo = arquivo.getvalue()

    return (
        arquivo.name,
        len(conteudo),
        hashlib.md5(
            conteudo
        ).hexdigest()
    )


def assinatura_arquivos(arquivos):

    if not arquivos:

        return ()

    assinaturas = []

    for arquivo in arquivos:

        conteudo = arquivo.getvalue()

        assinaturas.append(
            (
                arquivo.name,
                len(conteudo),
                hashlib.md5(
                    conteudo
                ).hexdigest()
            )
        )

    return tuple(
        sorted(
            assinaturas
        )
    )


# ============================================================
# LIMPAR APENAS O RESULTADO
#
# ATENÇÃO:
# Esta função NÃO apaga as bases carregadas.
# ============================================================

def limpar_resultado():

    st.session_state.df_resultado = None

    st.session_state.df_log = None

    st.session_state.nome_arquivo_resultado = None


# ============================================================
# SELECIONAR OPERAÇÃO
# ============================================================

def selecionar_operacao(
    nome_operacao
):

    operacao_anterior = (
        st.session_state.get(
            "operacao_ativa"
        )
    )

    if operacao_anterior != nome_operacao:

        limpar_resultado()

    st.session_state.operacao_ativa = (
        nome_operacao
    )


# ============================================================
# SESSION STATE
#
# As bases abaixo ficam disponíveis durante toda a sessão.
# ============================================================

defaults = {

    # --------------------------------------------------------
    # BASES PRINCIPAIS
    # --------------------------------------------------------

    "df_api": None,
    "df_the": None,

    # --------------------------------------------------------
    # BASE DE EVENTOS
    # --------------------------------------------------------

    "df_eventos": None,

    # --------------------------------------------------------
    # BASES DE SERVIÇOS
    # --------------------------------------------------------

    "df_servicos_api": None,
    "df_servicos_the": None,

    # --------------------------------------------------------
    # LOTES DE ACOMPANHAMENTO
    # --------------------------------------------------------

    "lista_lotes": [],

    # --------------------------------------------------------
    # RESULTADOS TRANSITÓRIOS
    # --------------------------------------------------------

    "df_resultado": None,
    "df_log": None,
    "nome_arquivo_resultado": None,

    # --------------------------------------------------------
    # ASSINATURAS DOS UPLOADS
    # --------------------------------------------------------

    "assinatura_api": (),
    "assinatura_the": (),
    "assinatura_eventos": None,
    "assinatura_serv_api": (),
    "assinatura_serv_the": (),
    "assinatura_lotes": (),

    # --------------------------------------------------------
    # HUB
    # --------------------------------------------------------

    "operacao_ativa": "FILTRAGEM",

    "modo_operacao": "API",
}


for key, valor_padrao in defaults.items():

    if key not in st.session_state:

        st.session_state[key] = (
            valor_padrao
        )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### 📦 Gerador de Lotes"
    )

    st.caption(
        f"Usuário: **"
        f"{st.session_state.get('usuario_logado', '')}"
        f"**"
    )

    st.divider()

    if st.button(
        "🏠 Voltar ao Menu de Ferramentas",
        use_container_width=True
    ):

        st.switch_page(
            "pages/4_Ferramentas_Operacionais.py"
        )

    if st.button(
        "🏠 Voltar ao Hub Principal",
        use_container_width=True
    ):

        st.switch_page(
            "app.py"
        )

    st.divider()

    st.caption(
        "As bases carregadas permanecem "
        "disponíveis durante a sessão."
    )


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "📦 Gerador de Lotes de Cancelamento"
)

st.caption(
    "Hub operacional para geração, "
    "cruzamento e acompanhamento de lotes."
)


# ============================================================
# SELEÇÃO API / THE
# ============================================================

st.subheader(
    "⚙️ Modo de operação"
)

modo = st.radio(
    "Selecione a base de operação",
    [
        "API",
        "THE"
    ],
    horizontal=True,
    key="modo_operacao"
)


# ============================================================
# SE MUDOU API/THE, LIMPA APENAS O RESULTADO
# ============================================================

modo_anterior = (
    st.session_state.get(
        "_modo_anterior"
    )
)

if modo_anterior is None:

    st.session_state._modo_anterior = modo

elif modo_anterior != modo:

    limpar_resultado()

    st.session_state._modo_anterior = modo


# ============================================================
# HUB — BOTÕES DAS FUNÇÕES
# ============================================================

st.divider()

st.subheader(
    "🧭 Operações disponíveis"
)

st.caption(
    "Escolha uma função. As bases carregadas "
    "acima permanecem disponíveis para todas "
    "as operações."
)


# ============================================================
# PRIMEIRA LINHA
# ============================================================

col1, col2, col3 = st.columns(3)


with col1:

    if st.button(
        "🔎 Filtragem / Cancelamento",
        use_container_width=True,
        key="btn_filtragem"
    ):

        selecionar_operacao(
            "FILTRAGEM"
        )


with col2:

    if st.button(
        "♻️ Cancelamento de Duplicidades",
        use_container_width=True,
        key="btn_duplicidades"
    ):

        selecionar_operacao(
            "DUPLICIDADES"
        )


with col3:

    if st.button(
        "🚱 Eventos de Falta de Água",
        use_container_width=True,
        key="btn_eventos"
    ):

        selecionar_operacao(
            "EVENTOS"
        )


# ============================================================
# SEGUNDA LINHA
# ============================================================

col4, col5, col6 = st.columns(3)


with col4:

    if st.button(
        "🛠️ Serviço em Aberto",
        use_container_width=True,
        key="btn_servicos"
    ):

        selecionar_operacao(
            "SERVICOS"
        )


with col5:

    if st.button(
        "📦 Acompanhamento de Lote",
        use_container_width=True,
        key="btn_acompanhamento"
    ):

        selecionar_operacao(
            "ACOMPANHAMENTO"
        )


with col6:

    if st.button(
        "⚡ Lista Rápida",
        use_container_width=True,
        key="btn_lista_rapida"
    ):

        selecionar_operacao(
            "LISTA_RAPIDA"
        )


# ============================================================
# OPERAÇÃO ATIVA
# ============================================================

operacao = (
    st.session_state.operacao_ativa
)


nomes_operacoes = {

    "FILTRAGEM":
        "🔎 Filtragem / Cancelamento",

    "DUPLICIDADES":
        "♻️ Cancelamento de Duplicidades",

    "EVENTOS":
        "🚱 Eventos de Falta de Água",

    "SERVICOS":
        "🛠️ Serviço em Aberto",

    "ACOMPANHAMENTO":
        "📦 Acompanhamento de Lote",

    "LISTA_RAPIDA":
        "⚡ Lista Rápida",
}


st.info(
    f"**Operação ativa:** "
    f"{nomes_operacoes.get(operacao, operacao)}"
)


# ============================================================
# CARREGAMENTO DAS BASES
# ============================================================

st.divider()

st.subheader(
    "📂 Carregamento de Bases"
)

st.caption(
    "Os arquivos são processados somente quando "
    "o conjunto de arquivos selecionado é alterado. "
    "Depois de carregados, eles ficam disponíveis "
    "para todas as operações desta sessão."
)


# ============================================================
# UPLOADERS
# ============================================================

with st.expander(
    "📂 Selecionar / atualizar arquivos",
    expanded=True
):

    col_up1, col_up2 = st.columns(2)


    # ========================================================
    # COLUNA 1
    # ========================================================

    with col_up1:

        st.markdown(
            "**📊 Backlogs**"
        )

        arquivos_api = st.file_uploader(
            "Backlog API",
            type=[
                "xlsx",
                "xlsm"
            ],
            accept_multiple_files=True,
            key="up_api"
        )

        arquivos_the = st.file_uploader(
            "Backlog THE",
            type=[
                "xlsx",
                "xlsm"
            ],
            accept_multiple_files=True,
            key="up_the"
        )


    # ========================================================
    # COLUNA 2
    # ========================================================

    with col_up2:

        st.markdown(
            "**📁 Bases auxiliares**"
        )

        arquivo_eventos = st.file_uploader(
            "Planilha de Eventos",
            type=[
                "xlsx",
                "xlsm"
            ],
            key="up_eventos"
        )

        arquivos_serv_api = st.file_uploader(
            "Serviços API",
            type=[
                "xlsx",
                "xlsm"
            ],
            accept_multiple_files=True,
            key="up_serv_api"
        )

        arquivos_serv_the = st.file_uploader(
            "Serviços THE",
            type=[
                "xlsx",
                "xlsm"
            ],
            accept_multiple_files=True,
            key="up_serv_the"
        )

        arquivos_lotes = st.file_uploader(
            "Arquivos de Lote — Acompanhamento",
            type=[
                "xlsx",
                "xlsm"
            ],
            accept_multiple_files=True,
            key="up_lotes"
        )


# ============================================================
# PROCESSAMENTO — BACKLOG API
#
# SOMENTE processa se a assinatura mudou.
# ============================================================

assinatura_atual_api = (
    assinatura_arquivos(
        arquivos_api
    )
)


if (
    assinatura_atual_api
    and assinatura_atual_api
    != st.session_state.assinatura_api
):

    dfs_api = []

    erros_api = []

    for arquivo in arquivos_api:

        try:

            conteudo = (
                arquivo.getvalue()
            )

            df = ler_excel_bytes(
                arquivo.name,
                conteudo
            )

            dfs_api.append(
                df
            )

        except Exception as erro:

            erros_api.append(
                f"{arquivo.name}: {erro}"
            )

    if dfs_api:

        try:

            df_consolidado, qtd_dup = (
                consolidar_lista_dfs(
                    dfs_api,
                    mensagem_vazio=(
                        "Nenhum registro válido "
                        "foi encontrado nos arquivos API."
                    )
                )
            )

            st.session_state.df_api = (
                df_consolidado
            )

            st.session_state.assinatura_api = (
                assinatura_atual_api
            )

            st.success(
                "Backlog API carregado: "
                f"{len(df_consolidado):,} registros."
                .replace(",", ".")
                +
                (
                    f" {qtd_dup:,} duplicações exatas "
                    "removidas."
                    .replace(",", ".")
                    if qtd_dup
                    else ""
                )
            )

        except Exception as erro:

            st.error(
                f"Erro ao consolidar o Backlog API: {erro}"
            )

    for erro in erros_api:

        st.error(
            f"Erro no arquivo API: {erro}"
        )


# ============================================================
# PROCESSAMENTO — BACKLOG THE
# ============================================================

assinatura_atual_the = (
    assinatura_arquivos(
        arquivos_the
    )
)


if (
    assinatura_atual_the
    and assinatura_atual_the
    != st.session_state.assinatura_the
):

    dfs_the = []

    erros_the = []

    for arquivo in arquivos_the:

        try:

            conteudo = (
                arquivo.getvalue()
            )

            df = ler_excel_bytes(
                arquivo.name,
                conteudo
            )

            dfs_the.append(
                df
            )

        except Exception as erro:

            erros_the.append(
                f"{arquivo.name}: {erro}"
            )

    if dfs_the:

        try:

            df_consolidado, qtd_dup = (
                consolidar_lista_dfs(
                    dfs_the,
                    mensagem_vazio=(
                        "Nenhum registro válido "
                        "foi encontrado nos arquivos THE."
                    )
                )
            )

            st.session_state.df_the = (
                df_consolidado
            )

            st.session_state.assinatura_the = (
                assinatura_atual_the
            )

            st.success(
                "Backlog THE carregado: "
                f"{len(df_consolidado):,} registros."
                .replace(",", ".")
                +
                (
                    f" {qtd_dup:,} duplicações exatas "
                    "removidas."
                    .replace(",", ".")
                    if qtd_dup
                    else ""
                )
            )

        except Exception as erro:

            st.error(
                f"Erro ao consolidar o Backlog THE: {erro}"
            )

    for erro in erros_the:

        st.error(
            f"Erro no arquivo THE: {erro}"
        )


# ============================================================
# PROCESSAMENTO — EVENTOS
# ============================================================

assinatura_atual_eventos = (
    assinatura_arquivo(
        arquivo_eventos
    )
)


if (
    assinatura_atual_eventos
    and assinatura_atual_eventos
    != st.session_state.assinatura_eventos
):

    try:

        conteudo = (
            arquivo_eventos.getvalue()
        )

        df_eventos = ler_excel_bytes(
            arquivo_eventos.name,
            conteudo
        )

        st.session_state.df_eventos = (
            df_eventos
        )

        st.session_state.assinatura_eventos = (
            assinatura_atual_eventos
        )

        st.success(
            "Base de Eventos carregada: "
            f"{len(df_eventos):,} registros."
            .replace(",", ".")
        )

    except Exception as erro:

        st.error(
            f"Erro ao carregar a base de Eventos: {erro}"
        )


# ============================================================
# PROCESSAMENTO — SERVIÇOS API
# ============================================================

assinatura_atual_serv_api = (
    assinatura_arquivos(
        arquivos_serv_api
    )
)


if (
    assinatura_atual_serv_api
    and assinatura_atual_serv_api
    != st.session_state.assinatura_serv_api
):

    dfs_serv_api = []

    erros_serv_api = []

    for arquivo in arquivos_serv_api:

        try:

            conteudo = (
                arquivo.getvalue()
            )

            df = ler_excel_bytes(
                arquivo.name,
                conteudo
            )

            dfs_serv_api.append(
                df
            )

        except Exception as erro:

            erros_serv_api.append(
                f"{arquivo.name}: {erro}"
            )

    if dfs_serv_api:

        try:

            df_consolidado, qtd_dup = (
                consolidar_lista_dfs(
                    dfs_serv_api,
                    mensagem_vazio=(
                        "Nenhum registro válido "
                        "foi encontrado nos Serviços API."
                    )
                )
            )

            st.session_state.df_servicos_api = (
                df_consolidado
            )

            st.session_state.assinatura_serv_api = (
                assinatura_atual_serv_api
            )

            st.success(
                "Serviços API carregados: "
                f"{len(df_consolidado):,} registros."
                .replace(",", ".")
            )

        except Exception as erro:

            st.error(
                f"Erro ao consolidar Serviços API: {erro}"
            )

    for erro in erros_serv_api:

        st.error(
            f"Erro no arquivo de Serviços API: {erro}"
        )


# ============================================================
# PROCESSAMENTO — SERVIÇOS THE
# ============================================================

assinatura_atual_serv_the = (
    assinatura_arquivos(
        arquivos_serv_the
    )
)


if (
    assinatura_atual_serv_the
    and assinatura_atual_serv_the
    != st.session_state.assinatura_serv_the
):

    dfs_serv_the = []

    erros_serv_the = []

    for arquivo in arquivos_serv_the:

        try:

            conteudo = (
                arquivo.getvalue()
            )

            df = ler_excel_bytes(
                arquivo.name,
                conteudo
            )

            dfs_serv_the.append(
                df
            )

        except Exception as erro:

            erros_serv_the.append(
                f"{arquivo.name}: {erro}"
            )

    if dfs_serv_the:

        try:

            df_consolidado, qtd_dup = (
                consolidar_lista_dfs(
                    dfs_serv_the,
                    mensagem_vazio=(
                        "Nenhum registro válido "
                        "foi encontrado nos Serviços THE."
                    )
                )
            )

            st.session_state.df_servicos_the = (
                df_consolidado
            )

            st.session_state.assinatura_serv_the = (
                assinatura_atual_serv_the
            )

            st.success(
                "Serviços THE carregados: "
                f"{len(df_consolidado):,} registros."
                .replace(",", ".")
            )

        except Exception as erro:

            st.error(
                f"Erro ao consolidar Serviços THE: {erro}"
            )

    for erro in erros_serv_the:

        st.error(
            f"Erro no arquivo de Serviços THE: {erro}"
        )


# ============================================================
# PROCESSAMENTO — LOTES DE ACOMPANHAMENTO
# ============================================================

assinatura_atual_lotes = (
    assinatura_arquivos(
        arquivos_lotes
    )
)


if (
    assinatura_atual_lotes
    and assinatura_atual_lotes
    != st.session_state.assinatura_lotes
):

    lista_lotes_nova = []

    erros_lotes = []

    for arquivo in arquivos_lotes:

        try:

            conteudo = (
                arquivo.getvalue()
            )

            df_lote = ler_excel_bytes(
                arquivo.name,
                conteudo
            )

            df_lote = remover_linhas_vazias(
                df_lote
            )

            if not df_lote.empty:

                lista_lotes_nova.append(
                    {
                        "nome": arquivo.name,
                        "df": df_lote
                    }
                )

        except Exception as erro:

            erros_lotes.append(
                f"{arquivo.name}: {erro}"
            )

    if lista_lotes_nova:

        st.session_state.lista_lotes = (
            lista_lotes_nova
        )

        st.session_state.assinatura_lotes = (
            assinatura_atual_lotes
        )

        st.success(
            "Lotes de acompanhamento carregados: "
            f"{len(lista_lotes_nova)} arquivo(s)."
        )

    for erro in erros_lotes:

        st.error(
            f"Erro no arquivo de lote: {erro}"
        )


# ============================================================
# STATUS DAS BASES
# ============================================================

st.divider()

st.subheader(
    "📊 Bases disponíveis na sessão"
)

st.caption(
    "Estas bases permanecem carregadas enquanto "
    "a sessão estiver ativa. Trocar de módulo ou "
    "de API/THE não exige novo upload."
)


status1, status2, status3 = st.columns(3)
status4, status5, status6 = st.columns(3)


# ============================================================
# API
# ============================================================

with status1:

    if (
        st.session_state.df_api is not None
        and not st.session_state.df_api.empty
    ):

        st.markdown(
            "🟢 **Backlog API**"
        )

        st.caption(
            f"{len(st.session_state.df_api):,} registros"
            .replace(",", ".")
        )

    else:

        st.markdown(
            "⚪ **Backlog API**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# THE
# ============================================================

with status2:

    if (
        st.session_state.df_the is not None
        and not st.session_state.df_the.empty
    ):

        st.markdown(
            "🟢 **Backlog THE**"
        )

        st.caption(
            f"{len(st.session_state.df_the):,} registros"
            .replace(",", ".")
        )

    else:

        st.markdown(
            "⚪ **Backlog THE**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# EVENTOS
# ============================================================

with status3:

    if (
        st.session_state.df_eventos is not None
        and not st.session_state.df_eventos.empty
    ):

        st.markdown(
            "🟢 **Eventos**"
        )

        st.caption(
            f"{len(st.session_state.df_eventos):,} registros"
            .replace(",", ".")
        )

    else:

        st.markdown(
            "⚪ **Eventos**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# SERVIÇOS API
# ============================================================

with status4:

    if (
        st.session_state.df_servicos_api is not None
        and not st.session_state.df_servicos_api.empty
    ):

        st.markdown(
            "🟢 **Serviços API**"
        )

        st.caption(
            f"{len(st.session_state.df_servicos_api):,} registros"
            .replace(",", ".")
        )

    else:

        st.markdown(
            "⚪ **Serviços API**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# SERVIÇOS THE
# ============================================================

with status5:

    if (
        st.session_state.df_servicos_the is not None
        and not st.session_state.df_servicos_the.empty
    ):

        st.markdown(
            "🟢 **Serviços THE**"
        )

        st.caption(
            f"{len(st.session_state.df_servicos_the):,} registros"
            .replace(",", ".")
        )

    else:

        st.markdown(
            "⚪ **Serviços THE**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# LOTES
# ============================================================

with status6:

    if st.session_state.lista_lotes:

        st.markdown(
            "🟢 **Lotes de acompanhamento**"
        )

        st.caption(
            f"{len(st.session_state.lista_lotes)} arquivo(s)"
        )

    else:

        st.markdown(
            "⚪ **Lotes de acompanhamento**"
        )

        st.caption(
            "Não carregado"
        )


# ============================================================
# DEFINIÇÃO DA BASE ATIVA
# ============================================================

if modo == "API":

    df_backlog = (
        st.session_state.df_api
    )

    df_servicos = (
        st.session_state.df_servicos_api
    )

else:

    df_backlog = (
        st.session_state.df_the
    )

    df_servicos = (
        st.session_state.df_servicos_the
    )


# ============================================================
# INFORMAÇÃO DA BASE ATIVA
# ============================================================

st.divider()

if df_backlog is not None:

    st.success(
        f"Base ativa: **{modo}** — "
        f"{len(df_backlog):,} registros."
        .replace(",", ".")
    )

else:

    st.warning(
        f"A base **{modo}** ainda não foi carregada."
    )

# ============================================================
# PREPARAÇÃO DOS DADOS DE EVENTOS
# ============================================================

def preparar_dados_eventos(
    df_eventos_bruto,
    df_os
):

    if (
        df_eventos_bruto is None
        or df_eventos_bruto.empty
    ):
        raise ValueError(
            "A base de Eventos está vazia."
        )

    if (
        df_os is None
        or df_os.empty
    ):
        raise ValueError(
            "A base de Backlog está vazia."
        )

    # --------------------------------------------------------
    # COLUNAS DO EVENTO
    # --------------------------------------------------------

    col_cidade_evento = localizar_coluna_eventos(
        df_eventos_bruto,
        [
            "CIDADE",
            "MUNICIPIO"
        ]
    )

    col_areas_evento = localizar_coluna_eventos(
        df_eventos_bruto,
        [
            "ÁREAS IMPACTADAS",
            "AREAS IMPACTADAS",
            "AREA IMPACTADA",
            "AREAS"
        ]
    )

    col_inicio_evento = localizar_coluna_eventos(
        df_eventos_bruto,
        [
            "INÍCIO",
            "INICIO",
            "DATA INÍCIO",
            "DATA INICIO"
        ]
    )

    col_fim_evento = localizar_coluna_eventos(
        df_eventos_bruto,
        [
            "PREV. TÉRMINO",
            "PREV. TERMINO",
            "PREVISÃO DE TÉRMINO",
            "PREVISAO DE TERMINO",
            "TÉRMINO",
            "TERMINO"
        ]
    )

    col_descricao_evento = localizar_coluna_eventos(
        df_eventos_bruto,
        [
            "DESCRIÇÃO DO SERVIÇO",
            "DESCRICAO DO SERVICO",
            "DESCRIÇÃO",
            "DESCRICAO",
            "SERVIÇO",
            "SERVICO"
        ],
        obrigatoria=False
    )

    # --------------------------------------------------------
    # COLUNAS DA OS
    # --------------------------------------------------------

    col_cidade_os = localizar_coluna(
        df_os,
        "cidade"
    )

    col_bairro_os = localizar_coluna(
        df_os,
        "bairro"
    )

    col_data_os = localizar_coluna(
        df_os,
        "data"
    )

    col_protocolo_os = localizar_coluna(
        df_os,
        "protocolo"
    )

    col_matricula_os = localizar_coluna(
        df_os,
        "matricula"
    )

    obrigatorias = {
        "Cidade": col_cidade_os,
        "Bairro": col_bairro_os,
        "Início do SLA": col_data_os,
        "Protocolo": col_protocolo_os,
        "Matrícula": col_matricula_os
    }

    faltantes = [
        nome
        for nome, coluna
        in obrigatorias.items()
        if coluna is None
    ]

    if faltantes:

        raise ValueError(
            "Não foi possível localizar no backlog "
            "as colunas: "
            + ", ".join(faltantes)
        )

    # --------------------------------------------------------
    # EVENTOS
    # --------------------------------------------------------

    eventos = df_eventos_bruto.copy()

    eventos["_CIDADE_NORMALIZADA"] = (
        eventos[col_cidade_evento]
        .apply(normalizar_cidade_evento)
    )

    eventos["_AREAS_NORMALIZADAS"] = (
        eventos[col_areas_evento]
        .fillna("")
        .astype(str)
        .apply(normalizar_texto)
    )

    eventos["_INICIO_EVENTO"] = (
        eventos[col_inicio_evento]
        .apply(parse_data_hora_evento)
    )

    eventos["_FIM_EVENTO"] = (
        eventos[col_fim_evento]
        .apply(parse_data_hora_evento)
    )

    # --------------------------------------------------------
    # REGRA:
    # PREVISÃO DE TÉRMINO + 3 HORAS
    # --------------------------------------------------------

    eventos["_FIM_EFETIVO"] = (
        eventos["_FIM_EVENTO"]
        + timedelta(hours=3)
    )

    eventos["_TODO_MUNICIPIO"] = (
        eventos["_AREAS_NORMALIZADAS"]
        .apply(evento_eh_todo_municipio)
    )

    if col_descricao_evento:

        eventos["_DESCRICAO"] = (
            eventos[col_descricao_evento]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    else:

        eventos["_DESCRICAO"] = ""

    eventos = eventos[
        eventos["_AREAS_NORMALIZADAS"] != ""
    ].copy()

    # --------------------------------------------------------
    # BACKLOG
    # --------------------------------------------------------

    os_base = df_os.copy()

    os_base["_CIDADE_NORMALIZADA"] = (
        os_base[col_cidade_os]
        .apply(normalizar_cidade_evento)
    )

    os_base["_BAIRRO_NORMALIZADO"] = (
        os_base[col_bairro_os]
        .fillna("")
        .astype(str)
        .apply(normalizar_texto)
    )

    os_base["_DATA_SLA"] = (
        converter_datas_robusto(
            os_base[col_data_os]
        )
    )

    protocolos = (
        os_base[col_protocolo_os]
        .apply(parse_protocolo)
    )

    os_base["_NUMERO_PROTOCOLO"] = (
        protocolos.apply(
            lambda x: x[2]
        )
    )

    os_base["_ANO_PROTOCOLO"] = (
        protocolos.apply(
            lambda x: x[1]
        )
    )

    colunas = {

        "cidade_evento":
            col_cidade_evento,

        "areas_evento":
            col_areas_evento,

        "inicio_evento":
            col_inicio_evento,

        "fim_evento":
            col_fim_evento,

        "descricao_evento":
            col_descricao_evento,

        "cidade_os":
            col_cidade_os,

        "bairro_os":
            col_bairro_os,

        "data_os":
            col_data_os,

        "protocolo_os":
            col_protocolo_os,

        "matricula_os":
            col_matricula_os,
    }

    return (
        eventos,
        os_base,
        colunas
    )


# ============================================================
# EVENTOS X BACKLOG
# ============================================================

def cruzar_eventos_com_backlog(
    df_eventos_bruto,
    df_backlog,
    modo="API"
):

    eventos, os_base, colunas = (
        preparar_dados_eventos(
            df_eventos_bruto,
            df_backlog
        )
    )

    resultado = []

    log = []

    # --------------------------------------------------------
    # LOOP NAS OS
    # --------------------------------------------------------

    for indice, os in os_base.iterrows():

        cidade = os["_CIDADE_NORMALIZADA"]

        bairro = os["_BAIRRO_NORMALIZADO"]

        data_os = os["_DATA_SLA"]

        numero = os["_NUMERO_PROTOCOLO"]

        ano = os["_ANO_PROTOCOLO"]

        matricula = os[
            colunas["matricula_os"]
        ]

        # ----------------------------------------------------
        # PROTOCOLO
        # ----------------------------------------------------

        if numero is None:

            log.append({
                "Tipo": "ERRO",
                "Motivo": "Protocolo inválido",
                "Matrícula": matricula,
                "Linha": indice + 2
            })

            continue

        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        if pd.isna(data_os):

            log.append({
                "Tipo": "ERRO",
                "Motivo": "Data do SLA inválida",
                "Matrícula": matricula,
                "Protocolo": (
                    f"{numero}/{ano}"
                )
            })

            continue

        # ----------------------------------------------------
        # EVENTOS DA MESMA CIDADE
        # ----------------------------------------------------

        candidatos = eventos[
            eventos["_CIDADE_NORMALIZADA"]
            == cidade
        ]

        if candidatos.empty:

            continue

        evento_encontrado = None

        for _, evento in candidatos.iterrows():

            inicio = evento["_INICIO_EVENTO"]

            fim = evento["_FIM_EFETIVO"]

            if pd.isna(inicio) or pd.isna(fim):

                log.append({
                    "Tipo": "ERRO",
                    "Motivo": (
                        "Período de evento inválido"
                    ),
                    "Cidade": cidade
                })

                continue

            # ------------------------------------------------
            # OS precisa estar dentro do intervalo
            # ------------------------------------------------

            if not (
                inicio <= data_os <= fim
            ):

                continue

            # ------------------------------------------------
            # TODO MUNICÍPIO
            # ------------------------------------------------

            if evento["_TODO_MUNICIPIO"]:

                evento_encontrado = evento

                break

            # ------------------------------------------------
            # BAIRRO
            # ------------------------------------------------

            if bairro_aparece_nas_areas_evento(
                bairro,
                evento["_AREAS_NORMALIZADAS"]
            ):

                evento_encontrado = evento

                break

        if evento_encontrado is None:

            continue

        # ----------------------------------------------------
        # ZONA
        # ----------------------------------------------------

        if modo == "THE":

            zona = 1

        else:

            zona = obter_zona(
                os[
                    colunas["cidade_os"]
                ]
            )

            if zona is None:

                log.append({
                    "Tipo": "ERRO",
                    "Motivo": (
                        "Cidade sem zona definida"
                    ),
                    "Cidade": (
                        os[
                            colunas["cidade_os"
                            ]
                        ]
                    ),
                    "Matrícula": matricula,
                    "Protocolo": (
                        f"{numero}/{ano}"
                    )
                })

                continue

        descricao = (
            evento_encontrado[
                "_DESCRICAO"
            ]
        )

        observacao = (
            "Abertura indevida - "
            "OS aberta durante evento "
            "de falta de água"
        )

        if descricao:

            observacao += (
                f" ({descricao})"
            )

        resultado.append({

            "Matricula": matricula,

            "Zona Ligacao": zona,

            "Numero Do Pedido": numero,

            "Ano Do Pedido": ano,

            "Tipo Encerramento":
                "Cancelamento",

            "Observações":
                observacao
        })

    df_resultado = pd.DataFrame(
        resultado,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações"
        ]
    )

    df_log = pd.DataFrame(
        log
    )

    return (
        df_resultado,
        df_log
    )


# ============================================================
# SERVIÇOS EM ABERTO
# ============================================================

def cruzar_falta_com_servicos(
    df_falta,
    df_servicos,
    modo="API"
):

    if (
        df_falta is None
        or df_falta.empty
    ):

        raise ValueError(
            "A base de backlog está vazia."
        )

    if (
        df_servicos is None
        or df_servicos.empty
    ):

        raise ValueError(
            "A base de Serviços está vazia."
        )

    # --------------------------------------------------------
    # COLUNAS BACKLOG
    # --------------------------------------------------------

    col_matricula = localizar_coluna(
        df_falta,
        "matricula"
    )

    col_protocolo = localizar_coluna(
        df_falta,
        "protocolo"
    )

    col_cidade = localizar_coluna(
        df_falta,
        "cidade"
    )

    if not col_matricula:

        raise ValueError(
            "Coluna MATRÍCULA não encontrada no backlog."
        )

    if not col_protocolo:

        raise ValueError(
            "Coluna de protocolo não encontrada no backlog."
        )

    if not col_cidade:

        raise ValueError(
            "Coluna CIDADE não encontrada no backlog."
        )

    # --------------------------------------------------------
    # COLUNAS SERVIÇO
    # --------------------------------------------------------

    col_matricula_servico = localizar_coluna(
        df_servicos,
        "matricula"
    )

    if not col_matricula_servico:

        raise ValueError(
            "Coluna MATRÍCULA não encontrada "
            "na base de Serviços."
        )

    col_servico = localizar_coluna_servico(
        df_servicos
    )

    col_protocolo_servico = (
        localizar_coluna(
            df_servicos,
            "protocolo"
        )
    )

    if not col_protocolo_servico:

        col_protocolo_servico = (
            localizar_coluna_eventos(
                df_servicos,
                [
                    "NUMERO DO PEDIDO",
                    "NUMERO PEDIDO",
                    "NÚMERO DO PEDIDO",
                    "OS",
                    "O.S.",
                    "PROTOCOLO"
                ],
                obrigatoria=False
            )
        )

    # --------------------------------------------------------
    # INDEXAÇÃO DOS SERVIÇOS
    # --------------------------------------------------------

    servicos_indexados = {}

    for _, servico in df_servicos.iterrows():

        matricula = normalizar_texto(
            servico[
                col_matricula_servico
            ]
        )

        if not matricula:

            continue

        if matricula not in servicos_indexados:

            servicos_indexados[
                matricula
            ] = []

        servicos_indexados[
            matricula
        ].append(
            servico
        )

    resultado = []

    log = []

    # --------------------------------------------------------
    # CRUZAMENTO
    # --------------------------------------------------------

    for indice, os in df_falta.iterrows():

        matricula_original = os[
            col_matricula
        ]

        matricula = normalizar_texto(
            matricula_original
        )

        if not matricula:

            continue

        servicos = servicos_indexados.get(
            matricula,
            []
        )

        if not servicos:

            continue

        numero, ano, numero_int = (
            parse_protocolo(
                os[
                    col_protocolo
                ]
            )
        )

        if numero_int is None:

            log.append({
                "Tipo": "ERRO",
                "Motivo": "Protocolo inválido",
                "Matrícula": matricula_original
            })

            continue

        if modo == "THE":

            zona = 1

        else:

            zona = obter_zona(
                os[col_cidade]
            )

            if zona is None:

                log.append({
                    "Tipo": "ERRO",
                    "Motivo": "Cidade sem zona definida",
                    "Cidade": os[col_cidade],
                    "Matrícula": matricula_original
                })

                continue

        # ----------------------------------------------------
        # PRIMEIRO SERVIÇO EM ABERTO
        # ----------------------------------------------------

        servico = servicos[0]

        descricao = str(
            servico[
                col_servico
            ]
        ).strip()

        protocolo_servico = ""

        if col_protocolo_servico:

            protocolo_servico = str(
                servico[
                    col_protocolo_servico
                ]
            ).strip()

        observacao = (
            "Cliente já possui serviço em aberto: "
            f"{descricao}"
        )

        if protocolo_servico:

            observacao += (
                f" - O.S. {protocolo_servico}"
            )

        resultado.append({

            "Matricula":
                matricula_original,

            "Zona Ligacao":
                zona,

            "Numero Do Pedido":
                numero_int,

            "Ano Do Pedido":
                ano,

            "Tipo Encerramento":
                "Cancelamento",

            "Observações":
                observacao
        })

    df_resultado = pd.DataFrame(
        resultado,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações"
        ]
    )

    df_log = pd.DataFrame(
        log
    )

    return (
        df_resultado,
        df_log
    )


# ============================================================
# CONSOLIDAR LOTES COM FONTE
# ============================================================

def consolidar_lotes_com_fonte(
    lista_lotes
):

    partes = []

    for item in lista_lotes:

        df = item.get(
            "df"
        )

        nome = item.get(
            "nome",
            "Lote"
        )

        if (
            df is None
            or df.empty
        ):

            continue

        parte = df.copy()

        parte["_FONTE_LOTE"] = nome

        partes.append(
            parte
        )

    if not partes:

        raise ValueError(
            "Nenhum lote válido foi carregado."
        )

    return pd.concat(
        partes,
        ignore_index=True,
        sort=False
    )


# ============================================================
# ACOMPANHAMENTO DE LOTE
# ============================================================

def cruzar_acompanhamento_lote(
    df_backlog,
    df_lotes_com_fonte,
    motivos_por_arquivo
):

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        raise ValueError(
            "A base de backlog está vazia."
        )

    if (
        df_lotes_com_fonte is None
        or df_lotes_com_fonte.empty
    ):

        raise ValueError(
            "A base de lotes está vazia."
        )

    # --------------------------------------------------------
    # COLUNAS BACKLOG
    # --------------------------------------------------------

    col_mat_backlog = localizar_coluna(
        df_backlog,
        "matricula"
    )

    col_prot_backlog = localizar_coluna(
        df_backlog,
        "protocolo"
    )

    col_bairro_backlog = localizar_coluna(
        df_backlog,
        "bairro"
    )

    if not col_mat_backlog:

        raise ValueError(
            "MATRÍCULA não encontrada no backlog."
        )

    if not col_prot_backlog:

        raise ValueError(
            "PROTOCOLO não encontrado no backlog."
        )

    # --------------------------------------------------------
    # COLUNAS DOS LOTES
    # --------------------------------------------------------

    col_mat_lote = localizar_coluna_lote(
        df_lotes_com_fonte,
        [
            "MATRICULA",
            "MATRÍCULA"
        ]
    )

    col_numero_lote = localizar_coluna_lote(
        df_lotes_com_fonte,
        [
            "NUMERO DO PEDIDO",
            "NÚMERO DO PEDIDO",
            "NUMERO PEDIDO",
            "NUMERO DA O.S. A SER CANCELADA"
        ]
    )

    col_ano_lote = localizar_coluna_lote(
        df_lotes_com_fonte,
        [
            "ANO DO PEDIDO",
            "ANO PEDIDO"
        ]
    )

    # --------------------------------------------------------
    # INDEXAR BACKLOG
    # --------------------------------------------------------

    indice_exato = {}

    indice_matricula = {}

    for idx, os in df_backlog.iterrows():

        matricula = normalizar_texto(
            os[col_mat_backlog]
        )

        numero, ano, numero_int = (
            parse_protocolo(
                os[col_prot_backlog]
            )
        )

        if not matricula:

            continue

        if numero_int is not None:

            chave = (
                matricula,
                numero_int,
                ano
            )

            indice_exato.setdefault(
                chave,
                []
            ).append(
                idx
            )

        indice_matricula.setdefault(
            matricula,
            []
        ).append(
            idx
        )

    resultado = []

    log = []

    # --------------------------------------------------------
    # CRUZAMENTO
    # --------------------------------------------------------

    for _, lote in df_lotes_com_fonte.iterrows():

        matricula = normalizar_texto(
            lote[col_mat_lote]
        )

        numero_texto = str(
            lote[col_numero_lote]
        ).strip()

        ano_texto = str(
            lote[col_ano_lote]
        ).strip()

        try:

            numero = int(
                float(
                    numero_texto
                )
            )

        except Exception:

            log.append({
                "Tipo": "ERRO",
                "Motivo": "Número da O.S. inválido",
                "Matrícula": matricula,
                "Arquivo": lote["_FONTE_LOTE"]
            })

            continue

        chave = (
            matricula,
            numero,
            ano_texto
        )

        candidatos = indice_exato.get(
            chave,
            []
        )

        # ----------------------------------------------------
        # FALLBACK POR MATRÍCULA
        # ----------------------------------------------------

        if not candidatos:

            candidatos_mat = (
                indice_matricula.get(
                    matricula,
                    []
                )
            )

            if len(candidatos_mat) == 1:

                candidatos = candidatos_mat

        if not candidatos:

            log.append({
                "Tipo": "NÃO ENCONTRADO",
                "Motivo": (
                    "O.S. não encontrada no backlog"
                ),
                "Matrícula": matricula,
                "Número": numero,
                "Ano": ano_texto,
                "Arquivo": lote["_FONTE_LOTE"]
            })

            continue

        idx_backlog = candidatos[0]

        os = df_backlog.loc[
            idx_backlog
        ]

        motivo = motivos_por_arquivo.get(
            lote["_FONTE_LOTE"],
            ""
        )

        resultado.append({

            "Matrícula":
                os[col_mat_backlog],

            "Número da O.S. a ser cancelada":
                numero,

            "Bairro":
                os[col_bairro_backlog]
                if col_bairro_backlog
                else "",

            "Motivo do cancelamento":
                motivo,

            "Arquivo Lote":
                lote["_FONTE_LOTE"]
        })

    df_resultado = pd.DataFrame(
        resultado,
        columns=[
            "Matrícula",
            "Número da O.S. a ser cancelada",
            "Bairro",
            "Motivo do cancelamento",
            "Arquivo Lote"
        ]
    )

    df_log = pd.DataFrame(
        log
    )

    return (
        df_resultado,
        df_log
    )


# ============================================================
# LISTA RÁPIDA
# ============================================================

def cruzar_lista_rapida(
    df_backlog,
    lista_os,
    observacao,
    modo_atual="API"
):

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        raise ValueError(
            "A base de backlog está vazia."
        )

    col_matricula = localizar_coluna(
        df_backlog,
        "matricula"
    )

    col_protocolo = localizar_coluna(
        df_backlog,
        "protocolo"
    )

    col_cidade = localizar_coluna(
        df_backlog,
        "cidade"
    )

    if not col_matricula:

        raise ValueError(
            "MATRÍCULA não encontrada."
        )

    if not col_protocolo:

        raise ValueError(
            "PROTOCOLO não encontrado."
        )

    if not col_cidade:

        raise ValueError(
            "CIDADE não encontrada."
        )

    # --------------------------------------------------------
    # ÍNDICES
    # --------------------------------------------------------

    indice_numero = {}

    indice_ano = {}

    for idx, os in df_backlog.iterrows():

        numero, ano, numero_int = (
            parse_protocolo(
                os[col_protocolo]
            )
        )

        if numero_int is None:

            continue

        indice_numero.setdefault(
            numero_int,
            []
        ).append(
            idx
        )

        indice_ano.setdefault(
            (
                numero_int,
                ano
            ),
            []
        ).append(
            idx
        )

    resultado = []

    log = []

    # --------------------------------------------------------
    # LISTA
    # --------------------------------------------------------

    for os_informada in lista_os:

        numero, ano, numero_int = (
            parse_protocolo(
                os_informada
            )
        )

        # ----------------------------------------------------
        # Caso seja somente o número
        # ----------------------------------------------------

        if numero_int is None:

            try:

                numero_int = int(
                    float(
                        str(
                            os_informada
                        ).strip()
                    )
                )

            except Exception:

                log.append({
                    "Tipo": "ERRO",
                    "Motivo": "O.S. inválida",
                    "Valor": os_informada
                })

                continue

            ano = ""

        # ----------------------------------------------------
        # Procurar
        # ----------------------------------------------------

        if ano:

            candidatos = indice_ano.get(
                (
                    numero_int,
                    ano
                ),
                []
            )

        else:

            candidatos = indice_numero.get(
                numero_int,
                []
            )

        if not candidatos:

            log.append({
                "Tipo": "NÃO ENCONTRADO",
                "Motivo": (
                    "O.S. não encontrada no backlog"
                ),
                "Valor": os_informada
            })

            continue

        # ----------------------------------------------------
        # Se houver mais de uma ocorrência sem ano
        # ----------------------------------------------------

        if len(candidatos) > 1 and not ano:

            log.append({
                "Tipo": "AMBÍGUO",
                "Motivo": (
                    "Mais de uma O.S. encontrada "
                    "com o mesmo número"
                ),
                "Valor": os_informada
            })

            continue

        idx = candidatos[0]

        os = df_backlog.loc[
            idx
        ]

        numero_final, ano_final, numero_int_final = (
            parse_protocolo(
                os[col_protocolo]
            )
        )

        if modo_atual == "THE":

            zona = 1

        else:

            zona = obter_zona(
                os[col_cidade]
            )

            if zona is None:

                log.append({
                    "Tipo": "ERRO",
                    "Motivo": (
                        "Cidade sem zona definida"
                    ),
                    "Cidade": os[col_cidade],
                    "Valor": os_informada
                })

                continue

        resultado.append({

            "Matricula":
                os[col_matricula],

            "Zona Ligacao":
                zona,

            "Numero Do Pedido":
                numero_int_final,

            "Ano Do Pedido":
                ano_final,

            "Tipo Encerramento":
                "Cancelamento",

            "Observações":
                observacao
        })

    df_resultado = pd.DataFrame(
        resultado,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações"
        ]
    )

    df_log = pd.DataFrame(
        log
    )

    return (
        df_resultado,
        df_log
    )


# ============================================================
# IDENTIFICAÇÃO DE DUPLICIDADES
# ============================================================

def identificar_duplicidades(
    df
):

    if (
        df is None
        or df.empty
    ):

        raise ValueError(
            "A base está vazia."
        )

    col_matricula = localizar_coluna(
        df,
        "matricula"
    )

    col_data = localizar_coluna(
        df,
        "data"
    )

    col_protocolo = localizar_coluna(
        df,
        "protocolo"
    )

    if not col_matricula:

        raise ValueError(
            "MATRÍCULA não encontrada."
        )

    if not col_data:

        raise ValueError(
            "INÍCIO DO SLA não encontrado."
        )

    if not col_protocolo:

        raise ValueError(
            "PROTOCOLO não encontrado."
        )

    trabalho = df.copy()

    trabalho["_MATRICULA_NORMALIZADA"] = (
        trabalho[col_matricula]
        .apply(normalizar_texto)
    )

    trabalho["_DATA_NORMALIZADA"] = (
        converter_datas_robusto(
            trabalho[col_data]
        )
    )

    trabalho["_ORDEM_ORIGINAL"] = (
        range(len(trabalho))
    )

    duplicadas = trabalho[
        trabalho["_MATRICULA_NORMALIZADA"]
        .duplicated(
            keep=False
        )
        &
        (
            trabalho["_MATRICULA_NORMALIZADA"]
            != ""
        )
    ].copy()

    if duplicadas.empty:

        return (
            duplicadas,
            trabalho.copy(),
            0,
            0,
            [],
            []
        )

    # --------------------------------------------------------
    # Ordenação
    #
    # Mantém a primeira ocorrência válida/mais antiga.
    # --------------------------------------------------------

    candidatos = duplicadas.sort_values(
        by=[
            "_MATRICULA_NORMALIZADA",
            "_DATA_NORMALIZADA",
            "_ORDEM_ORIGINAL"
        ],
        na_position="last"
    )

    indices_mantidos = (
        candidatos
        .groupby(
            "_MATRICULA_NORMALIZADA",
            sort=False
        )
        .head(1)
        .index
    )

    indices_duplicidades = (
        candidatos.index
        .difference(
            indices_mantidos
        )
    )

    df_duplicidades = (
        candidatos
        .loc[
            indices_duplicidades
        ]
        .copy()
    )

    df_mantidos = (
        candidatos
        .loc[
            indices_mantidos
        ]
        .copy()
    )

    # --------------------------------------------------------
    # Protocolos originais
    # --------------------------------------------------------

    protocolos_originais = []

    for _, linha in df_mantidos.iterrows():

        protocolos_originais.append(
            str(
                linha[col_protocolo]
            ).strip()
        )

    qtd_matriculas = (
        duplicadas[
            "_MATRICULA_NORMALIZADA"
        ]
        .nunique()
    )

    qtd_duplicidades = (
        len(
            df_duplicidades
        )
    )

    # --------------------------------------------------------
    # Remover colunas auxiliares
    # --------------------------------------------------------

    colunas_auxiliares = [
        "_MATRICULA_NORMALIZADA",
        "_DATA_NORMALIZADA",
        "_ORDEM_ORIGINAL"
    ]

    df_duplicidades = (
        df_duplicidades
        .drop(
            columns=colunas_auxiliares,
            errors="ignore"
        )
    )

    df_mantidos = (
        df_mantidos
        .drop(
            columns=colunas_auxiliares,
            errors="ignore"
        )
    )

    return (
        df_duplicidades,
        df_mantidos,
        qtd_matriculas,
        qtd_duplicidades,
        [],
        protocolos_originais
    )


# ============================================================
# GARANTIR FORMATO PADRÃO DE LOTE
# ============================================================

def preparar_lote_cancelamento(
    df
):

    colunas = [
        "Matricula",
        "Zona Ligacao",
        "Numero Do Pedido",
        "Ano Do Pedido",
        "Tipo Encerramento",
        "Observações"
    ]

    if df is None:

        return pd.DataFrame(
            columns=colunas
        )

    resultado = df.copy()

    for coluna in colunas:

        if coluna not in resultado.columns:

            resultado[coluna] = ""

    return resultado[
        colunas
    ].copy()


# ============================================================
# FILTRAGEM
# ============================================================

def executar_filtragem(
    df,
    cidade=None,
    bairro=None,
    ano=None,
    mes=None,
    dia=None,
    hora_inicial=None,
    hora_final=None
):

    if (
        df is None
        or df.empty
    ):

        raise ValueError(
            "A base de backlog está vazia."
        )

    resultado = df.copy()

    col_cidade = localizar_coluna(
        resultado,
        "cidade"
    )

    col_bairro = localizar_coluna(
        resultado,
        "bairro"
    )

    col_data = localizar_coluna(
        resultado,
        "data"
    )

    # --------------------------------------------------------
    # CIDADE
    # --------------------------------------------------------

    if cidade and cidade != "TODAS":

        if not col_cidade:

            raise ValueError(
                "A coluna CIDADE não foi encontrada."
            )

        resultado = resultado[
            resultado[col_cidade]
            .apply(normalizar_texto)
            ==
            normalizar_texto(cidade)
        ]

    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    if bairro and bairro != "TODOS":

        if not col_bairro:

            raise ValueError(
                "A coluna BAIRRO não foi encontrada."
            )

        resultado = resultado[
            resultado[col_bairro]
            .apply(normalizar_texto)
            ==
            normalizar_texto(bairro)
        ]

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    if (
        ano is not None
        or mes is not None
        or dia is not None
        or hora_inicial is not None
        or hora_final is not None
    ):

        if not col_data:

            raise ValueError(
                "A coluna INÍCIO DO SLA não foi encontrada."
            )

        resultado["_DATA_FILTRO"] = (
            converter_datas_robusto(
                resultado[col_data]
            )
        )

        if ano is not None:

            resultado = resultado[
                resultado["_DATA_FILTRO"]
                .dt.year
                ==
                int(ano)
            ]

        if mes is not None:

            resultado = resultado[
                resultado["_DATA_FILTRO"]
                .dt.month
                ==
                int(mes)
            ]

        if dia is not None:

            resultado = resultado[
                resultado["_DATA_FILTRO"]
                .dt.day
                ==
                int(dia)
            ]

        if hora_inicial is not None:

            resultado = resultado[
                resultado["_DATA_FILTRO"]
                .dt.time
                >=
                hora_inicial
            ]

        if hora_final is not None:

            resultado = resultado[
                resultado["_DATA_FILTRO"]
                .dt.time
                <=
                hora_final
            ]

        resultado = resultado.drop(
            columns=[
                "_DATA_FILTRO"
            ],
            errors="ignore"
        )

    return resultado.reset_index(
        drop=True
    )


# ============================================================
# INTERFACE — FILTRAGEM
# ============================================================

if operacao == "FILTRAGEM":

    st.divider()

    st.subheader(
        "🔎 Filtragem / Cancelamento"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    else:

        col_cidade = localizar_coluna(
            df_backlog,
            "cidade"
        )

        col_bairro = localizar_coluna(
            df_backlog,
            "bairro"
        )

        col_data = localizar_coluna(
            df_backlog,
            "data"
        )

        cidades = (
            ["TODAS"]
            +
            obter_valores_unicos(
                df_backlog,
                col_cidade
            )
            if col_cidade
            else ["TODAS"]
        )

        cidade_filtro = st.selectbox(
            "Cidade",
            cidades,
            key="filtro_cidade"
        )

        if (
            cidade_filtro != "TODAS"
            and col_bairro
        ):

            df_cidades = df_backlog[
                df_backlog[col_cidade]
                .apply(normalizar_texto)
                ==
                normalizar_texto(
                    cidade_filtro
                )
            ]

        else:

            df_cidades = df_backlog

        bairros = (
            ["TODOS"]
            +
            obter_valores_unicos(
                df_cidades,
                col_bairro
            )
            if col_bairro
            else ["TODOS"]
        )

        bairro_filtro = st.selectbox(
            "Bairro",
            bairros,
            key="filtro_bairro"
        )

        # ----------------------------------------------------
        # DATAS
        # ----------------------------------------------------

        ano_filtro = None
        mes_filtro = None
        dia_filtro = None
        hora_inicial_filtro = None
        hora_final_filtro = None

        if col_data:

            datas = converter_datas_robusto(
                df_backlog[col_data]
            )

            anos_disponiveis = sorted(
                datas.dropna()
                .dt.year
                .unique()
                .tolist()
            )

            usar_ano = st.checkbox(
                "Filtrar por Ano",
                key="usar_filtro_ano"
            )

            if usar_ano and anos_disponiveis:

                ano_filtro = st.selectbox(
                    "Ano",
                    anos_disponiveis,
                    key="filtro_ano"
                )

            usar_mes = st.checkbox(
                "Filtrar por Mês",
                key="usar_filtro_mes"
            )

            if usar_mes:

                mes_filtro = st.selectbox(
                    "Mês",
                    list(range(1, 13)),
                    key="filtro_mes"
                )

            usar_dia = st.checkbox(
                "Filtrar por Dia",
                key="usar_filtro_dia"
            )

            if usar_dia:

                dia_filtro = st.number_input(
                    "Dia",
                    min_value=1,
                    max_value=31,
                    value=1,
                    step=1,
                    key="filtro_dia"
                )

            usar_hora = st.checkbox(
                "Filtrar por horário",
                key="usar_filtro_hora"
            )

            if usar_hora:

                col_h1, col_h2 = st.columns(2)

                with col_h1:

                    hora_inicial_texto = st.text_input(
                        "Hora inicial",
                        value="00:00",
                        key="filtro_hora_inicial"
                    )

                with col_h2:

                    hora_final_texto = st.text_input(
                        "Hora final",
                        value="23:59",
                        key="filtro_hora_final"
                    )

                try:

                    hora_inicial_filtro = (
                        converter_hora(
                            hora_inicial_texto
                        )
                    )

                    hora_final_filtro = (
                        converter_hora(
                            hora_final_texto
                        )
                    )

                except ValueError as erro:

                    st.error(
                        str(erro)
                    )

        # ----------------------------------------------------
        # EXECUTAR FILTRO
        # ----------------------------------------------------

        if st.button(
            "🔎 Aplicar Filtros",
            type="primary",
            use_container_width=True,
            key="aplicar_filtros"
        ):

            try:

                df_filtrado = executar_filtragem(
                    df_backlog,
                    cidade=(
                        cidade_filtro
                        if cidade_filtro != "TODAS"
                        else None
                    ),
                    bairro=(
                        bairro_filtro
                        if bairro_filtro != "TODOS"
                        else None
                    ),
                    ano=ano_filtro,
                    mes=mes_filtro,
                    dia=dia_filtro,
                    hora_inicial=(
                        hora_inicial_filtro
                    ),
                    hora_final=(
                        hora_final_filtro
                    )
                )

                st.session_state.df_filtragem_preview = (
                    df_filtrado
                )

            except Exception as erro:

                st.error(
                    f"Erro ao aplicar filtros: {erro}"
                )

        # ----------------------------------------------------
        # PRÉVIA
        # ----------------------------------------------------

        df_preview = st.session_state.get(
            "df_filtragem_preview"
        )

        if (
            df_preview is not None
        ):

            st.divider()

            st.markdown(
                f"**Prévia:** "
                f"{len(df_preview):,} registro(s)"
                .replace(",", ".")
            )

            st.dataframe(
                df_preview,
                use_container_width=True,
                height=400
            )

            if not df_preview.empty:

                st.divider()

                st.markdown(
                    "### 📦 Gerar lote"
                )

                observacao_filtragem = st.text_input(
                    "Observação do cancelamento",
                    value="Cancelamento conforme filtragem."
                )

                if st.button(
                    "📦 Gerar Lote de Cancelamento",
                    type="primary",
                    use_container_width=True,
                    key="gerar_lote_filtragem"
                ):

                    limpar_resultado()

                    resultado = []

                    log = []

                    col_mat = localizar_coluna(
                        df_preview,
                        "matricula"
                    )

                    col_prot = localizar_coluna(
                        df_preview,
                        "protocolo"
                    )

                    col_cid = localizar_coluna(
                        df_preview,
                        "cidade"
                    )

                    if not col_mat or not col_prot:

                        st.error(
                            "A base filtrada não possui "
                            "MATRÍCULA ou PROTOCOLO."
                        )

                    else:

                        for _, linha in df_preview.iterrows():

                            numero, ano, numero_int = (
                                parse_protocolo(
                                    linha[col_prot]
                                )
                            )

                            if numero_int is None:

                                log.append({
                                    "Tipo": "ERRO",
                                    "Motivo": (
                                        "Protocolo inválido"
                                    ),
                                    "Matrícula":
                                        linha[col_mat]
                                })

                                continue

                            if modo == "THE":

                                zona = 1

                            else:

                                zona = obter_zona(
                                    linha[col_cid]
                                )

                                if zona is None:

                                    log.append({
                                        "Tipo": "ERRO",
                                        "Motivo":
                                            "Cidade sem zona definida",
                                        "Cidade":
                                            linha[col_cid],
                                        "Matrícula":
                                            linha[col_mat]
                                    })

                                    continue

                            resultado.append({

                                "Matricula":
                                    linha[col_mat],

                                "Zona Ligacao":
                                    zona,

                                "Numero Do Pedido":
                                    numero_int,

                                "Ano Do Pedido":
                                    ano,

                                "Tipo Encerramento":
                                    "Cancelamento",

                                "Observações":
                                    observacao_filtragem
                            })

                        st.session_state.df_resultado = (
                            pd.DataFrame(
                                resultado,
                                columns=[
                                    "Matricula",
                                    "Zona Ligacao",
                                    "Numero Do Pedido",
                                    "Ano Do Pedido",
                                    "Tipo Encerramento",
                                    "Observações"
                                ]
                            )
                        )

                        st.session_state.df_log = (
                            pd.DataFrame(
                                log
                            )
                        )

                        st.session_state.nome_arquivo_resultado = (
                            f"Lote_Cancelamento_Filtragem_"
                            f"{modo}_"
                            f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                        )

                        st.success(
                            "Lote gerado com sucesso."
                        )


# ============================================================
# INTERFACE — DUPLICIDADES
# ============================================================

elif operacao == "DUPLICIDADES":

    st.divider()

    st.subheader(
        "♻️ Cancelamento de Duplicidades"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    else:

        if st.button(
            "🔍 Identificar Duplicidades",
            type="primary",
            use_container_width=True,
            key="identificar_duplicidades"
        ):

            limpar_resultado()

            try:

                (
                    df_dup,
                    df_mantidos,
                    qtd_matriculas,
                    qtd_duplicidades,
                    _,
                    _
                ) = identificar_duplicidades(
                    df_backlog
                )

                st.session_state.df_duplicidades = (
                    df_dup
                )

                st.session_state.df_mantidos = (
                    df_mantidos
                )

                st.session_state.qtd_matriculas_dup = (
                    qtd_matriculas
                )

                st.session_state.qtd_duplicidades = (
                    qtd_duplicidades
                )

            except Exception as erro:

                st.error(
                    f"Erro ao identificar duplicidades: {erro}"
                )

        df_dup = st.session_state.get(
            "df_duplicidades"
        )

        if df_dup is not None:

            st.metric(
                "Matrículas com duplicidade",
                st.session_state.get(
                    "qtd_matriculas_dup",
                    0
                )
            )

            st.metric(
                "O.S. para cancelamento",
                st.session_state.get(
                    "qtd_duplicidades",
                    0
                )
            )

            if not df_dup.empty:

                st.dataframe(
                    df_dup,
                    use_container_width=True,
                    height=400
                )

                if st.button(
                    "📦 Gerar Lote de Duplicidades",
                    type="primary",
                    use_container_width=True,
                    key="gerar_lote_dup"
                ):

                    limpar_resultado()

                    col_mat = localizar_coluna(
                        df_dup,
                        "matricula"
                    )

                    col_prot = localizar_coluna(
                        df_dup,
                        "protocolo"
                    )

                    col_cid = localizar_coluna(
                        df_dup,
                        "cidade"
                    )

                    resultado = []

                    log = []

                    for _, linha in df_dup.iterrows():

                        numero, ano, numero_int = (
                            parse_protocolo(
                                linha[col_prot]
                            )
                        )

                        if numero_int is None:

                            log.append({
                                "Tipo": "ERRO",
                                "Motivo":
                                    "Protocolo inválido",
                                "Matrícula":
                                    linha[col_mat]
                            })

                            continue

                        if modo == "THE":

                            zona = 1

                        else:

                            zona = obter_zona(
                                linha[col_cid]
                            )

                            if zona is None:

                                log.append({
                                    "Tipo": "ERRO",
                                    "Motivo":
                                        "Cidade sem zona definida",
                                    "Cidade":
                                        linha[col_cid],
                                    "Matrícula":
                                        linha[col_mat]
                                })

                                continue

                        resultado.append({

                            "Matricula":
                                linha[col_mat],

                            "Zona Ligacao":
                                zona,

                            "Numero Do Pedido":
                                numero_int,

                            "Ano Do Pedido":
                                ano,

                            "Tipo Encerramento":
                                "Cancelamento",

                            "Observações":
                                "Duplicidade com O.S N. "
                                + str(
                                    linha[col_prot]
                                )
                        })

                    st.session_state.df_resultado = (
                        pd.DataFrame(
                            resultado,
                            columns=[
                                "Matricula",
                                "Zona Ligacao",
                                "Numero Do Pedido",
                                "Ano Do Pedido",
                                "Tipo Encerramento",
                                "Observações"
                            ]
                        )
                    )

                    st.session_state.df_log = (
                        pd.DataFrame(
                            log
                        )
                    )

                    st.session_state.nome_arquivo_resultado = (
                        f"Lote_Cancelamento_Duplicidades_"
                        f"{modo}_"
                        f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                    )

                    st.success(
                        "Lote de duplicidades gerado."
                    )

            else:

                st.success(
                    "Nenhuma duplicidade encontrada."
                )


# ============================================================
# INTERFACE — EVENTOS
# ============================================================

elif operacao == "EVENTOS":

    st.divider()

    st.subheader(
        "🚱 Eventos de Falta de Água"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    elif (
        st.session_state.df_eventos is None
        or st.session_state.df_eventos.empty
    ):

        st.warning(
            "Carregue a Planilha de Eventos."
        )

    else:

        st.write(
            "O sistema cruzará automaticamente "
            "as O.S. do backlog com os eventos "
            "de falta de água."
        )

        if st.button(
            "🚱 Cruzar Eventos com Backlog",
            type="primary",
            use_container_width=True,
            key="cruzar_eventos"
        ):

            limpar_resultado()

            try:

                (
                    resultado,
                    log
                ) = cruzar_eventos_com_backlog(
                    st.session_state.df_eventos,
                    df_backlog,
                    modo=modo
                )

                st.session_state.df_resultado = (
                    preparar_lote_cancelamento(
                        resultado
                    )
                )

                st.session_state.df_log = log

                st.session_state.nome_arquivo_resultado = (
                    f"Lote_Cancelamento_Eventos_"
                    f"{modo}_"
                    f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                )

                st.success(
                    f"Cruzamento concluído. "
                    f"{len(resultado):,} O.S. identificada(s)."
                    .replace(",", ".")
                )

            except Exception as erro:

                st.error(
                    f"Erro no cruzamento de eventos: {erro}"
                )


# ============================================================
# INTERFACE — SERVIÇOS
# ============================================================

elif operacao == "SERVICOS":

    st.divider()

    st.subheader(
        "🛠️ Serviço em Aberto"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    elif (
        df_servicos is None
        or df_servicos.empty
    ):

        st.warning(
            f"Carregue primeiro a base "
            f"de Serviços {modo}."
        )

    else:

        st.write(
            "O sistema verificará quais matrículas "
            "do backlog possuem serviço em aberto."
        )

        if st.button(
            "🛠️ Cruzar Serviços com Backlog",
            type="primary",
            use_container_width=True,
            key="cruzar_servicos"
        ):

            limpar_resultado()

            try:

                (
                    resultado,
                    log
                ) = cruzar_falta_com_servicos(
                    df_backlog,
                    df_servicos,
                    modo=modo
                )

                st.session_state.df_resultado = (
                    preparar_lote_cancelamento(
                        resultado
                    )
                )

                st.session_state.df_log = log

                st.session_state.nome_arquivo_resultado = (
                    f"Lote_Cancelamento_ServicoAberto_"
                    f"{modo}_"
                    f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                )

                st.success(
                    f"Cruzamento concluído. "
                    f"{len(resultado):,} O.S. identificada(s)."
                    .replace(",", ".")
                )

            except Exception as erro:

                st.error(
                    f"Erro no cruzamento de serviços: {erro}"
                )


# ============================================================
# INTERFACE — ACOMPANHAMENTO
# ============================================================

elif operacao == "ACOMPANHAMENTO":

    st.divider()

    st.subheader(
        "📦 Acompanhamento de Lote"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    elif not st.session_state.lista_lotes:

        st.warning(
            "Carregue pelo menos um arquivo "
            "de lote para acompanhamento."
        )

    else:

        st.markdown(
            "### Arquivos carregados"
        )

        for item in st.session_state.lista_lotes:

            st.write(
                f"📄 {item['nome']} — "
                f"{len(item['df']):,} registros"
                .replace(",", ".")
            )

        st.divider()

        motivos_por_arquivo = {}

        st.markdown(
            "### Motivo de cancelamento por lote"
        )

        for item in st.session_state.lista_lotes:

            nome = item["nome"]

            motivos_por_arquivo[nome] = (
                st.text_input(
                    f"Motivo — {nome}",
                    key=f"motivo_{nome}"
                )
            )

        if st.button(
            "📦 Gerar Acompanhamento",
            type="primary",
            use_container_width=True,
            key="gerar_acompanhamento"
        ):

            limpar_resultado()

            try:

                df_lotes = (
                    consolidar_lotes_com_fonte(
                        st.session_state.lista_lotes
                    )
                )

                (
                    resultado,
                    log
                ) = cruzar_acompanhamento_lote(
                    df_backlog,
                    df_lotes,
                    motivos_por_arquivo
                )

                st.session_state.df_resultado = (
                    resultado
                )

                st.session_state.df_log = log

                st.session_state.nome_arquivo_resultado = (
                    f"Acompanhamento_Lote_"
                    f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                )

                st.success(
                    f"Acompanhamento gerado. "
                    f"{len(resultado):,} registro(s)."
                    .replace(",", ".")
                )

            except Exception as erro:

                st.error(
                    f"Erro no acompanhamento: {erro}"
                )


# ============================================================
# INTERFACE — LISTA RÁPIDA
# ============================================================

elif operacao == "LISTA_RAPIDA":

    st.divider()

    st.subheader(
        "⚡ Lista Rápida"
    )

    if (
        df_backlog is None
        or df_backlog.empty
    ):

        st.warning(
            f"Carregue primeiro o Backlog {modo}."
        )

    else:

        st.markdown(
            "Digite as O.S. que deseja localizar."
        )

        texto_os = st.text_area(
            "Lista de O.S.",
            placeholder=(
                "Exemplos:\n"
                "12345\n"
                "12346\n"
                "12347/2026\n"
                "12348, 12349, 12350"
            ),
            height=180,
            key="lista_rapida_texto"
        )

        observacao_lista = st.text_input(
            "Observação do cancelamento",
            value="Cancelamento via lista rápida.",
            key="lista_rapida_observacao"
        )

        if st.button(
            "⚡ Localizar O.S. e Gerar Lote",
            type="primary",
            use_container_width=True,
            key="gerar_lista_rapida"
        ):

            limpar_resultado()

            lista_os = (
                extrair_lista_os(
                    texto_os
                )
            )

            if not lista_os:

                st.warning(
                    "Informe pelo menos uma O.S."
                )

            else:

                try:

                    (
                        resultado,
                        log
                    ) = cruzar_lista_rapida(
                        df_backlog,
                        lista_os,
                        observacao_lista,
                        modo_atual=modo
                    )

                    st.session_state.df_resultado = (
                        preparar_lote_cancelamento(
                            resultado
                        )
                    )

                    st.session_state.df_log = log

                    st.session_state.nome_arquivo_resultado = (
                        f"Lote_ListaRapida_"
                        f"{modo}_"
                        f"{datetime.now():%Y%m%d_%H%M%S}.xlsx"
                    )

                    st.success(
                        f"Processamento concluído. "
                        f"{len(resultado):,} O.S. encontrada(s)."
                        .replace(",", ".")
                    )

                except Exception as erro:

                    st.error(
                        f"Erro na Lista Rápida: {erro}"
                    )


# ============================================================
# RESULTADO GLOBAL
#
# Todos os módulos que geram lote chegam aqui.
# ============================================================

df_resultado_final = (
    st.session_state.get(
        "df_resultado"
    )
)


if (
    df_resultado_final is not None
    and not df_resultado_final.empty
):

    st.divider()

    st.subheader(
        "📄 Resultado da operação"
    )

    # --------------------------------------------------------
    # MÉTRICAS
    # --------------------------------------------------------

    met1, met2 = st.columns(2)

    with met1:

        st.metric(
            "Registros no lote",
            f"{len(df_resultado_final):,}"
            .replace(",", ".")
        )

    with met2:

        df_log_final = (
            st.session_state.get(
                "df_log"
            )
        )

        qtd_log = (
            len(df_log_final)
            if (
                df_log_final is not None
                and not df_log_final.empty
            )
            else 0
        )

        st.metric(
            "Registros no LOG",
            f"{qtd_log:,}"
            .replace(",", ".")
        )

    # --------------------------------------------------------
    # PRÉVIA DO RESULTADO
    # --------------------------------------------------------

    st.dataframe(
        df_resultado_final,
        use_container_width=True,
        height=450
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    excel_bytes = salvar_lote_excel(
        df_resultado_final
    )

    nome_download = (
        st.session_state.nome_arquivo_resultado
        or
        "lote_cancelamento.xlsx"
    )

    st.download_button(
        label="⬇️ Baixar Lote — Excel",
        data=excel_bytes,
        file_name=nome_download,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
        key="download_lote_final"
    )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    if (
        df_log_final is not None
        and not df_log_final.empty
    ):

        st.divider()

        with st.expander(
            "📋 Visualizar LOG da operação"
        ):

            st.dataframe(
                df_log_final,
                use_container_width=True,
                height=300
            )

            log_bytes = salvar_lote_excel(
                df_log_final
            )

            st.download_button(
                label="⬇️ Baixar LOG",
                data=log_bytes,
                file_name=(
                    "LOG_"
                    + nome_download
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="download_log_final"
            )

    # --------------------------------------------------------
    # NOVA OPERAÇÃO
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "🧹 Limpar resultado e iniciar nova operação",
        use_container_width=True,
        key="limpar_resultado_final"
    ):

        limpar_resultado()

        # Também limpa somente a prévia específica
        # da filtragem.

        if (
            "df_filtragem_preview"
            in st.session_state
        ):

            st.session_state.df_filtragem_preview = None

        st.rerun()


# ============================================================
# MENSAGEM QUANDO NÃO HÁ RESULTADO
# ============================================================

else:

    # Não mostrar esta mensagem para operações que ainda
    # estejam aguardando carregamento de bases.

    if operacao in [
        "FILTRAGEM",
        "DUPLICIDADES",
        "EVENTOS",
        "SERVICOS",
        "ACOMPANHAMENTO",
        "LISTA_RAPIDA"
    ]:

        st.divider()

        st.caption(
            "Nenhum resultado gerado nesta operação."
        )

st.divider()

st.caption(
    "Plataforma COI • Gerador de Lotes de Cancelamento"
)

st.caption(
    "As bases permanecem disponíveis enquanto "
    "a sessão do Streamlit estiver ativa. "
    "Os resultados gerados são independentes "
    "das bases carregadas."
)
