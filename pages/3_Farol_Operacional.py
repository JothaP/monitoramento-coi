import io
import json
import math
import os
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

import gspread
import pandas as pd
import streamlit as st
import folium
import plotly.express as px

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Farol Operacional",
    layout="wide",
    initial_sidebar_state="expanded",
)

verificar_autenticacao()

SPREADSHEET_ID = (
    "1l0IcsO1GgPYcs8DPRPI6_lKdSCM9vWOypcrwIMJ96QY"
)

NOME_ABA_POCOS = "POCOS"
NOME_ABA_LOGGERS = "LOGGERS"
NOME_ABA_PONTOS = "PONTOS"
NOME_ABA_EVENTOS = "EVENTOS"

ARQUIVO_KMZ_PADRAO = "TERESINA.kmz"

RAIO_OPERACIONAL_PADRAO = 500
RAIO_CONCENTRACAO_PADRAO = 500


# ============================================================
# ESTRUTURA DAS ABAS
# ============================================================

CABECALHO_POCOS = [
    "ID_POCO",
    "IDENTIFICACAO_ATIVO",
    "NOME_POCO",
    "MUNICIPIO",
    "LATITUDE",
    "LONGITUDE",
]

CABECALHO_LOGGERS = [
    "ID_LOGGER",
    "IDENTIFICACAO_ATIVO",
    "ENDERECO",
    "MUNICIPIO",
    "LATITUDE",
    "LONGITUDE",
]

CABECALHO_PONTOS = [
    "Empresa",
    "Dt. Emissão",
    "Nº da O.S",
    "Matrícula",
    "Cidade",
    "Bairro",
    "Atendente",
    "Latitude",
    "Longitude",
]

CABECALHO_EVENTOS = [
    "Data",
    "Controlador",
    "Status",
    "Unidade",
    "Cidade",
    "Regional",
    "Código do Ativo",
    "Serviço",
    "Início",
    "Prev. Término",
    "Término Real",
]


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource(show_spinner=False)
def obter_cliente_google():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        json.loads(st.secrets["gcp_json"]),
        scopes=scopes,
    )

    return gspread.authorize(credentials)


@st.cache_resource(show_spinner=False)
def obter_planilha():

    cliente = obter_cliente_google()

    return cliente.open_by_key(
        SPREADSHEET_ID
    )


def criar_aba(nome, cabecalho, linhas=3000):

    planilha = obter_planilha()

    aba = planilha.add_worksheet(
        title=nome,
        rows=linhas,
        cols=len(cabecalho),
    )

    aba.update(
        "A1",
        [cabecalho],
        value_input_option="USER_ENTERED",
    )

    return aba


@st.cache_resource(show_spinner=False)
def obter_aba(nome):

    planilha = obter_planilha()

    try:

        return planilha.worksheet(nome)

    except gspread.WorksheetNotFound:

        estruturas = {
            NOME_ABA_POCOS: CABECALHO_POCOS,
            NOME_ABA_LOGGERS: CABECALHO_LOGGERS,
            NOME_ABA_PONTOS: CABECALHO_PONTOS,
            NOME_ABA_EVENTOS: CABECALHO_EVENTOS,
        }

        if nome not in estruturas:
            raise

        return criar_aba(
            nome,
            estruturas[nome],
        )


@st.cache_resource(show_spinner=False)
def obter_abas():

    return (
        obter_aba(NOME_ABA_POCOS),
        obter_aba(NOME_ABA_LOGGERS),
        obter_aba(NOME_ABA_PONTOS),
        obter_aba(NOME_ABA_EVENTOS),
    )


def garantir_cabecalhos():

    estruturas = [
        (
            obter_aba(NOME_ABA_POCOS),
            CABECALHO_POCOS,
        ),
        (
            obter_aba(NOME_ABA_LOGGERS),
            CABECALHO_LOGGERS,
        ),
        (
            obter_aba(NOME_ABA_PONTOS),
            CABECALHO_PONTOS,
        ),
        (
            obter_aba(NOME_ABA_EVENTOS),
            CABECALHO_EVENTOS,
        ),
    ]

    for aba, cabecalho in estruturas:

        atual = aba.row_values(1)

        if atual != cabecalho:

            aba.update(
                "A1",
                [cabecalho],
                value_input_option="USER_ENTERED",
            )


# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================

def carregar_aba(aba, cabecalho):

    valores = aba.get_all_values()

    if not valores:

        return pd.DataFrame(
            columns=cabecalho
        )

    cabecalho_planilha = [
        str(x).strip()
        for x in valores[0]
    ]

    registros = valores[1:]

    if not cabecalho_planilha:

        return pd.DataFrame(
            columns=cabecalho
        )

    df = pd.DataFrame(
        registros,
        columns=cabecalho_planilha,
    )

    for coluna in cabecalho:

        if coluna not in df.columns:

            df[coluna] = ""

    return df[
        cabecalho
    ].copy()


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_pocos():

    return carregar_aba(
        obter_aba(NOME_ABA_POCOS),
        CABECALHO_POCOS,
    )


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_loggers():

    return carregar_aba(
        obter_aba(NOME_ABA_LOGGERS),
        CABECALHO_LOGGERS,
    )


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_pontos():

    return carregar_aba(
        obter_aba(NOME_ABA_PONTOS),
        CABECALHO_PONTOS,
    )


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_eventos():

    return carregar_aba(
        obter_aba(NOME_ABA_EVENTOS),
        CABECALHO_EVENTOS,
    )


def invalidar_cache():

    carregar_pocos.clear()
    carregar_loggers.clear()
    carregar_pontos.clear()
    carregar_eventos.clear()


# ============================================================
# UTILITÁRIOS
# ============================================================

def normalizar_texto(valor):

    if valor is None:

        return ""

    texto = str(valor)

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip().upper()


def normalizar_cabecalho(valor):

    texto = normalizar_texto(valor)

    return re.sub(
        r"[^A-Z0-9]",
        "",
        texto,
    )


def texto(valor):

    if valor is None:

        return ""

    try:

        if pd.isna(valor):

            return ""

    except Exception:

        pass

    return str(valor).strip()


def numero(valor):

    if valor is None:

        return None

    try:

        if pd.isna(valor):

            return None

    except Exception:

        pass

    if isinstance(
        valor,
        (int, float),
    ):

        return float(valor)

    valor = str(valor).strip()

    if not valor:

        return None

    valor = valor.replace(
        " ",
        "",
    )

    try:

        if "," in valor:

            valor = (
                valor
                .replace(".", "")
                .replace(",", ".")
            )

        return float(valor)

    except ValueError:

        return None


def coordenada_valida(
    latitude,
    longitude,
):

    lat = numero(latitude)
    lon = numero(longitude)

    if lat is None or lon is None:

        return False

    return (
        -90 <= lat <= 90
        and -180 <= lon <= 180
        and not (
            lat == 0
            and lon == 0
        )
    )


def converter_data(valor):

    if valor is None:

        return pd.NaT

    if str(valor).strip() == "":

        return pd.NaT

    return pd.to_datetime(
        valor,
        errors="coerce",
        dayfirst=True,
        format="mixed",
    )


def formatar_data(valor):

    convertido = converter_data(valor)

    if pd.isna(convertido):

        return ""

    return convertido.strftime(
        "%d/%m/%Y"
    )


def novo_id(
    prefixo,
    valores,
):

    maior = 0

    for valor in valores:

        valor = texto(valor)

        if valor.upper().startswith(
            prefixo.upper()
        ):

            try:

                numero_id = int(
                    valor[
                        len(prefixo):
                    ]
                )

                maior = max(
                    maior,
                    numero_id,
                )

            except ValueError:

                pass

    return (
        f"{prefixo}"
        f"{maior + 1:05d}"
    )


def distancia_metros(
    lat1,
    lon1,
    lat2,
    lon2,
):

    if not coordenada_valida(
        lat1,
        lon1,
    ):

        return None

    if not coordenada_valida(
        lat2,
        lon2,
    ):

        return None

    raio_terra = 6371000

    lat1 = math.radians(
        float(lat1)
    )

    lat2 = math.radians(
        float(lat2)
    )

    diferenca_lat = math.radians(
        float(lat2)
        - float(lat1)
    )

    diferenca_lon = math.radians(
        float(lon2)
        - float(lon1)
    )

    a = (
        math.sin(
            diferenca_lat / 2
        ) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(
            diferenca_lon / 2
        ) ** 2
    )

    return (
        2
        * raio_terra
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )
    )


# ============================================================
# PREPARAÇÃO DOS DATAFRAMES
# ============================================================

def preparar_pocos(df):

    df = df.copy()

    for coluna in CABECALHO_POCOS:

        if coluna not in df.columns:

            df[coluna] = ""

    for coluna in [
        "ID_POCO",
        "IDENTIFICACAO_ATIVO",
        "NOME_POCO",
        "MUNICIPIO",
    ]:

        df[coluna] = (
            df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["LATITUDE_NUM"] = df[
        "LATITUDE"
    ].apply(numero)

    df["LONGITUDE_NUM"] = df[
        "LONGITUDE"
    ].apply(numero)

    return df


def preparar_loggers(df):

    df = df.copy()

    for coluna in CABECALHO_LOGGERS:

        if coluna not in df.columns:

            df[coluna] = ""

    for coluna in [
        "ID_LOGGER",
        "IDENTIFICACAO_ATIVO",
        "ENDERECO",
        "MUNICIPIO",
    ]:

        df[coluna] = (
            df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["LATITUDE_NUM"] = df[
        "LATITUDE"
    ].apply(numero)

    df["LONGITUDE_NUM"] = df[
        "LONGITUDE"
    ].apply(numero)

    return df


def preparar_pontos(df):

    df = df.copy()

    for coluna in CABECALHO_PONTOS:

        if coluna not in df.columns:

            df[coluna] = ""

    for coluna in CABECALHO_PONTOS:

        df[coluna] = (
            df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["DATA_DT"] = df[
        "Dt. Emissão"
    ].apply(converter_data)

    df["LATITUDE_NUM"] = df[
        "Latitude"
    ].apply(numero)

    df["LONGITUDE_NUM"] = df[
        "Longitude"
    ].apply(numero)

    return df


def preparar_eventos(df):

    df = df.copy()

    for coluna in CABECALHO_EVENTOS:

        if coluna not in df.columns:

            df[coluna] = ""

    for coluna in CABECALHO_EVENTOS:

        df[coluna] = (
            df[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    for coluna, auxiliar in [
        ("Data", "DATA_DT"),
        ("Início", "INICIO_DT"),
        ("Prev. Término", "PREV_TERMINO_DT"),
        ("Término Real", "TERMINO_REAL_DT"),
    ]:

        df[auxiliar] = df[
            coluna
        ].apply(converter_data)

    return df


# ============================================================
# KMZ
# ============================================================

def localizar_kmz():

    candidatos = [
        os.path.join(
            os.path.dirname(
                os.path.abspath(__file__)
            ),
            ARQUIVO_KMZ_PADRAO,
        ),
        os.path.join(
            os.getcwd(),
            ARQUIVO_KMZ_PADRAO,
        ),
        ARQUIVO_KMZ_PADRAO,
    ]

    for caminho in candidatos:

        if os.path.exists(caminho):

            return caminho

    return None


@st.cache_data(
    show_spinner=False
)
def carregar_kmz(caminho):

    if not caminho:

        return []

    try:

        with zipfile.ZipFile(
            caminho,
            "r",
        ) as arquivo_zip:

            arquivos_kml = [
                nome
                for nome
                in arquivo_zip.namelist()
                if nome.lower().endswith(".kml")
            ]

            if not arquivos_kml:

                return []

            nome_kml = next(
                (
                    nome
                    for nome
                    in arquivos_kml
                    if nome.lower().endswith(
                        "doc.kml"
                    )
                ),
                arquivos_kml[0],
            )

            conteudo = arquivo_zip.read(
                nome_kml
            )

        raiz = ET.fromstring(
            conteudo
        )

        namespace = {
            "kml":
            "http://www.opengis.net/kml/2.2"
        }

        bairros = []

        for placemark in raiz.findall(
            ".//kml:Placemark",
            namespace,
        ):

            elemento_nome = placemark.find(
                "kml:name",
                namespace,
            )

            nome = (
                elemento_nome.text.strip()
                if elemento_nome is not None
                and elemento_nome.text
                else "Sem nome"
            )

            poligonos = placemark.findall(
                ".//kml:Polygon",
                namespace,
            )

            geometrias = []

            for poligono in poligonos:

                elemento_coordenadas = (
                    poligono.find(
                        ".//kml:outerBoundaryIs/"
                        "kml:LinearRing/"
                        "kml:coordinates",
                        namespace,
                    )
                )

                if (
                    elemento_coordenadas is None
                    or not elemento_coordenadas.text
                ):

                    continue

                coordenadas = []

                for item in (
                    elemento_coordenadas
                    .text
                    .strip()
                    .split()
                ):

                    partes = item.split(",")

                    if len(partes) < 2:

                        continue

                    try:

                        longitude = float(
                            partes[0]
                        )

                        latitude = float(
                            partes[1]
                        )

                        coordenadas.append(
                            [
                                latitude,
                                longitude,
                            ]
                        )

                    except ValueError:

                        continue

                if len(coordenadas) >= 3:

                    geometrias.append(
                        coordenadas
                    )

            if geometrias:

                bairros.append(
                    {
                        "nome": nome,
                        "normalizado":
                            normalizar_texto(
                                nome
                            ),
                        "poligonos":
                            geometrias,
                    }
                )

        return bairros

    except Exception:

        return []


def ponto_em_poligono(
    latitude,
    longitude,
    poligono,
):

    dentro = False

    quantidade = len(
        poligono
    )

    if quantidade < 3:

        return False

    j = quantidade - 1

    for i in range(
        quantidade
    ):

        lat_i, lon_i = poligono[i]
        lat_j, lon_j = poligono[j]

        intersecciona = (
            (lat_i > latitude)
            !=
            (lat_j > latitude)
        ) and (
            longitude
            <
            (
                (lon_j - lon_i)
                * (latitude - lat_i)
                /
                (
                    (lat_j - lat_i)
                    or 1e-15
                )
            )
            + lon_i
        )

        if intersecciona:

            dentro = not dentro

        j = i

    return dentro


def localizar_bairro(
    latitude,
    longitude,
    bairros,
):

    if not coordenada_valida(
        latitude,
        longitude,
    ):

        return ""

    for bairro in bairros:

        for poligono in bairro[
            "poligonos"
        ]:

            if ponto_em_poligono(
                float(latitude),
                float(longitude),
                poligono,
            ):

                return bairro[
                    "nome"
                ]

    return ""


def associar_bairros(
    df,
    bairros,
):

    df = df.copy()

    if df.empty:

        df["BAIRRO_KMZ"] = pd.Series(
            dtype="object"
        )

        return df

    df["BAIRRO_KMZ"] = [
        localizar_bairro(
            lat,
            lon,
            bairros,
        )
        for lat, lon
        in zip(
            df["LATITUDE_NUM"],
            df["LONGITUDE_NUM"],
        )
    ]

    return df


# ============================================================
# DISTÂNCIAS / RELACIONAMENTOS
# ============================================================

def pontos_proximos(
    latitude,
    longitude,
    df,
    raio,
):

    encontrados = []

    if df.empty:

        return encontrados

    for indice, linha in df.iterrows():

        lat = linha.get(
            "LATITUDE_NUM"
        )

        lon = linha.get(
            "LONGITUDE_NUM"
        )

        distancia = distancia_metros(
            latitude,
            longitude,
            lat,
            lon,
        )

        if (
            distancia is not None
            and distancia <= raio
        ):

            encontrados.append(
                {
                    "indice": indice,
                    "distancia": distancia,
                    "linha": linha,
                }
            )

    return sorted(
        encontrados,
        key=lambda item:
            item["distancia"],
    )


def obter_concentracoes(
    df,
    raio,
):

    if df.empty:

        return []

    pontos = []

    for indice, linha in df.iterrows():

        lat = linha[
            "LATITUDE_NUM"
        ]

        lon = linha[
            "LONGITUDE_NUM"
        ]

        if not coordenada_valida(
            lat,
            lon,
        ):

            continue

        pontos.append(
            {
                "indice": indice,
                "lat": float(lat),
                "lon": float(lon),
                "os": texto(
                    linha.get(
                        "Nº da O.S"
                    )
                ),
                "bairro": texto(
                    linha.get(
                        "BAIRRO_KMZ"
                    )
                ),
            }
        )

    concentracoes = []
    processados = set()

    for ponto in pontos:

        if ponto["indice"] in processados:

            continue

        grupo = []

        for outro in pontos:

            distancia = distancia_metros(
                ponto["lat"],
                ponto["lon"],
                outro["lat"],
                outro["lon"],
            )

            if (
                distancia is not None
                and distancia <= raio
            ):

                grupo.append(
                    outro
                )

        if len(grupo) < 2:

            continue

        indices = frozenset(
            item["indice"]
            for item in grupo
        )

        if indices in processados:

            continue

        processados.update(
            indices
        )

        concentracoes.append(
            {
                "latitude":
                    sum(
                        x["lat"]
                        for x in grupo
                    )
                    / len(grupo),
                "longitude":
                    sum(
                        x["lon"]
                        for x in grupo
                    )
                    / len(grupo),
                "quantidade":
                    len(grupo),
                "ordens": [
                    x["os"]
                    for x in grupo
                    if x["os"]
                ],
                "bairros": sorted(
                    {
                        x["bairro"]
                        for x in grupo
                        if x["bairro"]
                    }
                ),
            }
        )

    return concentracoes


# ============================================================
# IMPORTAÇÃO DE ARQUIVOS
# ============================================================

def ler_arquivo(
    arquivo,
):

    nome = arquivo.name.lower()

    conteudo = arquivo.getvalue()

    if nome.endswith(".csv"):

        for encoding in [
            "utf-8-sig",
            "utf-8",
            "latin1",
        ]:

            try:

                return pd.read_csv(
                    io.BytesIO(
                        conteudo
                    ),
                    encoding=encoding,
                    sep=None,
                    engine="python",
                )

            except Exception:

                continue

        raise ValueError(
            "Não foi possível ler o CSV."
        )

    return pd.read_excel(
        io.BytesIO(
            conteudo
        )
    )


def mapa_colunas(df):

    resultado = {}

    for coluna in df.columns:

        resultado[
            normalizar_cabecalho(
                coluna
            )
        ] = coluna

    return resultado


def preparar_importacao(
    df,
    cabecalho,
):

    mapa = mapa_colunas(df)

    resultado = pd.DataFrame()

    for coluna in cabecalho:

        chave = normalizar_cabecalho(
            coluna
        )

        if chave in mapa:

            resultado[coluna] = df[
                mapa[chave]
            ]

        else:

            resultado[coluna] = ""

    return resultado.fillna("")


def chave_ponto(
    linha,
):

    os_num = normalizar_texto(
        linha.get(
            "Nº da O.S",
            "",
        )
    )

    if os_num:

        return (
            "OS",
            os_num,
        )

    return (
        "PONTO",
        normalizar_texto(
            linha.get(
                "Matrícula",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Dt. Emissão",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Cidade",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Bairro",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Latitude",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Longitude",
                "",
            )
        ),
    )


def chave_evento(
    linha,
):

    return (
        normalizar_texto(
            linha.get(
                "Data",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Controlador",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Unidade",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Código do Ativo",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Serviço",
                "",
            )
        ),
        normalizar_texto(
            linha.get(
                "Início",
                "",
            )
        ),
    )


def importar_pontos(
    df_upload,
):

    df_atual = preparar_pontos(
        carregar_pontos()
    )

    existentes = {
        chave_ponto(linha)
        for _, linha
        in df_atual.iterrows()
    }

    novos = []

    for _, linha
    in df_upload.iterrows():

        chave = chave_ponto(
            linha
        )

        if chave in existentes:

            continue

        existentes.add(
            chave
        )

        novos.append(
            [
                texto(
                    linha.get(
                        coluna,
                        "",
                    )
                )
                for coluna
                in CABECALHO_PONTOS
            ]
        )

    if novos:

        obter_aba(
            NOME_ABA_PONTOS
        ).append_rows(
            novos,
            value_input_option="USER_ENTERED",
        )

        invalidar_cache()

    return len(novos)


def importar_eventos(
    df_upload,
):

    df_atual = preparar_eventos(
        carregar_eventos()
    )

    existentes = {
        chave_evento(linha)
        for _, linha
        in df_atual.iterrows()
    }

    novos = []

    for _, linha
    in df_upload.iterrows():

        chave = chave_evento(
            linha
        )

        if chave in existentes:

            continue

        existentes.add(
            chave
        )

        novos.append(
            [
                texto(
                    linha.get(
                        coluna,
                        "",
                    )
                )
                for coluna
                in CABECALHO_EVENTOS
            ]
        )

    if novos:

        obter_aba(
            NOME_ABA_EVENTOS
        ).append_rows(
            novos,
            value_input_option="USER_ENTERED",
        )

        invalidar_cache()

    return len(novos)


# ============================================================
# CADASTRO DE POÇOS
# ============================================================

def adicionar_poco(
    identificacao,
    nome,
    municipio,
    latitude,
    longitude,
):

    df = carregar_pocos()

    ids = (
        df["ID_POCO"].tolist()
        if not df.empty
        else []
    )

    id_poco = novo_id(
        "POCO",
        ids,
    )

    obter_aba(
        NOME_ABA_POCOS
    ).append_row(
        [
            id_poco,
            identificacao,
            nome,
            municipio,
            latitude,
            longitude,
        ],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache()

    return id_poco


# ============================================================
# CADASTRO DE LOGGER
# ============================================================

def adicionar_logger(
    identificacao,
    endereco,
    municipio,
    latitude,
    longitude,
):

    df = carregar_loggers()

    ids = (
        df["ID_LOGGER"].tolist()
        if not df.empty
        else []
    )

    id_logger = novo_id(
        "LOG",
        ids,
    )

    obter_aba(
        NOME_ABA_LOGGERS
    ).append_row(
        [
            id_logger,
            identificacao,
            endereco,
            municipio,
            latitude,
            longitude,
        ],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache()

    return id_logger


# ============================================================
# POPUP
# ============================================================

def popup_os(
    linha,
):

    return f"""
    <div style="min-width:280px">
        <b>O.S.:</b>
        {texto(linha.get("Nº da O.S"))}<br>

        <b>Matrícula:</b>
        {texto(linha.get("Matrícula"))}<br>

        <b>Cidade:</b>
        {texto(linha.get("Cidade"))}<br>

        <b>Bairro:</b>
        {texto(linha.get("Bairro_KMZ"))}<br>

        <b>Empresa:</b>
        {texto(linha.get("Empresa"))}<br>

        <b>Atendente:</b>
        {texto(linha.get("Atendente"))}<br>

        <b>Emissão:</b>
        {formatar_data(
            linha.get("Dt. Emissão")
        )}
    </div>
    """


def popup_poco(
    linha,
):

    return f"""
    <div style="min-width:260px">
        <b>Poço:</b>
        {texto(linha.get("NOME_POCO"))}<br>

        <b>Ativo:</b>
        {texto(linha.get("IDENTIFICACAO_ATIVO"))}<br>

        <b>Município:</b>
        {texto(linha.get("MUNICIPIO"))}
    </div>
    """


def popup_logger(
    linha,
):

    return f"""
    <div style="min-width:260px">
        <b>Logger:</b>
        {texto(linha.get("IDENTIFICACAO_ATIVO"))}<br>

        <b>Endereço:</b>
        {texto(linha.get("ENDERECO"))}<br>

        <b>Município:</b>
        {texto(linha.get("MUNICIPIO"))}
    </div>
    """


# ============================================================
# MAPA
# ============================================================

TIPOS_MAPA = {
    "OpenStreetMap": {
        "tiles": "OpenStreetMap",
        "attr": None,
    },
    "Imagem de satélite": {
        "tiles": (
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/"
            "{z}/{y}/{x}"
        ),
        "attr": "Esri",
    },
    "OpenTopoMap": {
        "tiles": (
            "https://{s}.tile.opentopomap.org/"
            "{z}/{x}/{y}.png"
        ),
        "attr": "OpenTopoMap",
    },
}


def adicionar_bairros(
    mapa,
    bairros,
    bairro_selecionado,
):

    camada = folium.FeatureGroup(
        name="Bairros",
        show=True,
    )

    filtro = (
        normalizar_texto(
            bairro_selecionado
        )
        if bairro_selecionado != "Todos"
        else None
    )

    for bairro in bairros:

        if (
            filtro
            and bairro["normalizado"]
            != filtro
        ):

            continue

        for poligono in bairro[
            "poligonos"
        ]:

            folium.Polygon(
                locations=poligono,
                color="#3388ff",
                weight=1,
                fill=True,
                fill_opacity=0.08,
                tooltip=bairro[
                    "nome"
                ],
            ).add_to(
                camada
            )

    camada.add_to(
        mapa
    )


# ============================================================
# CARREGAMENTO INICIAL
# ============================================================

try:

    garantir_cabecalhos()

    df_pocos = preparar_pocos(
        carregar_pocos()
    )

    df_loggers = preparar_loggers(
        carregar_loggers()
    )

    df_pontos = preparar_pontos(
        carregar_pontos()
    )

    df_eventos = preparar_eventos(
        carregar_eventos()
    )

except Exception as erro:

    st.error(
        f"Erro ao carregar os dados: {erro}"
    )

    st.stop()


# ============================================================
# KMZ
# ============================================================

caminho_kmz = localizar_kmz()

bairros = carregar_kmz(
    caminho_kmz
)


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "🚦 Farol Operacional"
)

st.caption(
    "Monitoramento integrado de O.S., eventos, "
    "bairros, poços e loggers."
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "Filtros"
)


municipios = sorted(
    {
        texto(valor)
        for valor
        in pd.concat(
            [
                df_pocos[
                    "MUNICIPIO"
                ],
                df_loggers[
                    "MUNICIPIO"
                ],
                df_pontos[
                    "Cidade"
                ],
                df_eventos[
                    "Cidade"
                ],
            ],
            ignore_index=True,
        )
        if texto(valor)
    },
    key=normalizar_texto,
)


municipio_filtro = st.sidebar.selectbox(
    "Município",
    [
        "Todos"
    ] + municipios,
)


# ============================================================
# DATA
# ============================================================

datas_pontos = df_pontos[
    "DATA_DT"
].dropna()

if datas_pontos.empty:

    data_inicio_padrao = date.today()
    data_fim_padrao = date.today()

else:

    data_inicio_padrao = (
        datas_pontos.min().date()
    )

    data_fim_padrao = (
        datas_pontos.max().date()
    )


periodo = st.sidebar.date_input(
    "Período das O.S.",
    value=(
        data_inicio_padrao,
        data_fim_padrao,
    ),
    format="DD/MM/YYYY",
)


if (
    isinstance(
        periodo,
        (tuple, list),
    )
    and len(periodo) == 2
):

    data_inicio = periodo[0]
    data_fim = periodo[1]

else:

    data_inicio = data_inicio_padrao
    data_fim = data_fim_padrao


# ============================================================
# BAIRRO
# ============================================================

bairros_filtro = sorted(
    {
        bairro["nome"]
        for bairro
        in bairros
    },
    key=normalizar_texto,
)


bairro_filtro = st.sidebar.selectbox(
    "Bairro",
    [
        "Todos"
    ] + bairros_filtro,
)


# ============================================================
# EVENTOS
# ============================================================

status_opcoes = sorted(
    {
        texto(valor)
        for valor
        in df_eventos[
            "Status"
        ]
        if texto(valor)
    },
    key=normalizar_texto,
)


status_filtro = st.sidebar.multiselect(
    "Status",
    status_opcoes,
)


controladores = sorted(
    {
        texto(valor)
        for valor
        in df_eventos[
            "Controlador"
        ]
        if texto(valor)
    },
    key=normalizar_texto,
)


controladores_filtro = st.sidebar.multiselect(
    "Controlador",
    controladores,
)


servicos = sorted(
    {
        texto(valor)
        for valor
        in df_eventos[
            "Serviço"
        ]
        if texto(valor)
    },
    key=normalizar_texto,
)


servicos_filtro = st.sidebar.multiselect(
    "Serviço",
    servicos,
)


# ============================================================
# RAIOS
# ============================================================

raio_operacional = st.sidebar.number_input(
    "Raio operacional (m)",
    min_value=50,
    max_value=5000,
    value=RAIO_OPERACIONAL_PADRAO,
    step=50,
)


raio_concentracao = st.sidebar.number_input(
    "Raio de concentração (m)",
    min_value=50,
    max_value=5000,
    value=RAIO_CONCENTRACAO_PADRAO,
    step=50,
)


tipo_mapa = st.sidebar.selectbox(
    "Mapa",
    list(
        TIPOS_MAPA.keys()
    ),
)


# ============================================================
# IMPORTAÇÃO
# ============================================================

st.sidebar.divider()

st.sidebar.subheader(
    "Importação"
)


arquivo_pontos = st.sidebar.file_uploader(
    "O.S. / PONTOS",
    type=[
        "xlsx",
        "xls",
        "csv",
    ],
    key="arquivo_pontos",
)


if arquivo_pontos is not None:

    if st.sidebar.button(
        "Importar PONTOS",
        type="primary",
        width="stretch",
    ):

        try:

            df_upload = ler_arquivo(
                arquivo_pontos
            )

            df_upload = preparar_importacao(
                df_upload,
                CABECALHO_PONTOS,
            )

            quantidade = importar_pontos(
                df_upload
            )

            st.sidebar.success(
                f"{quantidade} O.S. nova(s) importada(s)."
            )

            st.rerun()

        except Exception as erro:

            st.sidebar.error(
                f"Erro: {erro}"
            )


arquivo_eventos = st.sidebar.file_uploader(
    "EVENTOS",
    type=[
        "xlsx",
        "xls",
        "csv",
    ],
    key="arquivo_eventos",
)


if arquivo_eventos is not None:

    if st.sidebar.button(
        "Importar EVENTOS",
        type="primary",
        width="stretch",
    ):

        try:

            df_upload = ler_arquivo(
                arquivo_eventos
            )

            df_upload = preparar_importacao(
                df_upload,
                CABECALHO_EVENTOS,
            )

            quantidade = importar_eventos(
                df_upload
            )

            st.sidebar.success(
                f"{quantidade} evento(s) novo(s) importado(s)."
            )

            st.rerun()

        except Exception as erro:

            st.sidebar.error(
                f"Erro: {erro}"
            )


# ============================================================
# AÇÕES
# ============================================================

st.sidebar.divider()

if st.sidebar.button(
    "🔄 Atualizar dados",
    width="stretch",
):

    invalidar_cache()

    st.rerun()


if st.sidebar.button(
    "🏠 Voltar ao Menu Principal",
    width="stretch",
):

    st.switch_page(
        "app.py"
    )


# ============================================================
# FILTRO DE PONTOS
# ============================================================

pontos = df_pontos.copy()


if municipio_filtro != "Todos":

    pontos = pontos[
        pontos[
            "Cidade"
        ].apply(
            normalizar_texto
        )
        ==
        normalizar_texto(
            municipio_filtro
        )
    ]


if bairro_filtro != "Todos":

    pontos = pontos[
        pontos[
            "BAIRRO_KMZ"
        ].apply(
            normalizar_texto
        )
        ==
        normalizar_texto(
            bairro_filtro
        )
    ]


pontos = pontos[
    pontos[
        "DATA_DT"
    ].isna()
    |
    (
        (
            pontos[
                "DATA_DT"
            ].dt.date
            >= data_inicio
        )
        &
        (
            pontos[
                "DATA_DT"
            ].dt.date
            <= data_fim
        )
    )
]


# ============================================================
# FILTRO DE EVENTOS
# ============================================================

eventos = df_eventos.copy()


if municipio_filtro != "Todos":

    eventos = eventos[
        eventos[
            "Cidade"
        ].apply(
            normalizar_texto
        )
        ==
        normalizar_texto(
            municipio_filtro
        )
    ]


if status_filtro:

    status_normalizados = {
        normalizar_texto(valor)
        for valor
        in status_filtro
    }

    eventos = eventos[
        eventos[
            "Status"
        ].apply(
            normalizar_texto
        ).isin(
            status_normalizados
        )
    ]


if controladores_filtro:

    controladores_normalizados = {
        normalizar_texto(valor)
        for valor
        in controladores_filtro
    }

    eventos = eventos[
        eventos[
            "Controlador"
        ].apply(
            normalizar_texto
        ).isin(
            controladores_normalizados
        )
    ]


if servicos_filtro:

    servicos_normalizados = {
        normalizar_texto(valor)
        for valor
        in servicos_filtro
    }

    eventos = eventos[
        eventos[
            "Serviço"
        ].apply(
            normalizar_texto
        ).isin(
            servicos_normalizados
        )
    ]


eventos = eventos[
    eventos[
        "DATA_DT"
    ].isna()
    |
    (
        (
            eventos[
                "DATA_DT"
            ].dt.date
            >= data_inicio
        )
        &
        (
            eventos[
                "DATA_DT"
            ].dt.date
            <= data_fim
        )
    )
]


# ============================================================
# MÉTRICAS
# ============================================================

concentracoes = obter_concentracoes(
    pontos,
    raio_concentracao,
)


col1, col2, col3, col4, col5 = st.columns(
    5
)


col1.metric(
    "O.S.",
    len(pontos),
)


col2.metric(
    "Eventos",
    len(eventos),
)


col3.metric(
    "Bairros",
    pontos[
        "BAIRRO_KMZ"
    ].replace(
        "",
        pd.NA,
    ).nunique(),
)


col4.metric(
    "Concentrações",
    len(concentracoes),
)


col5.metric(
    "Poços",
    len(df_pocos),
)


# ============================================================
# MAPA
# ============================================================

st.subheader(
    "Mapa operacional"
)


coordenadas = pontos[
    pontos[
        "LATITUDE_NUM"
    ].notna()
    &
    pontos[
        "LONGITUDE_NUM"
    ].notna()
].copy()


if coordenadas.empty:

    centro_lat = -5.0892
    centro_lon = -42.8016

else:

    centro_lat = (
        coordenadas[
            "LATITUDE_NUM"
        ].mean()
    )

    centro_lon = (
        coordenadas[
            "LONGITUDE_NUM"
        ].mean()
    )


config_mapa = TIPOS_MAPA[
    tipo_mapa
]


mapa = folium.Map(
    location=[
        centro_lat,
        centro_lon,
    ],
    zoom_start=12,
    tiles=config_mapa[
        "tiles"
    ],
    attr=config_mapa[
        "attr"
    ],
)


# ============================================================
# BAIRROS
# ============================================================

if bairros:

    adicionar_bairros(
        mapa,
        bairros,
        bairro_filtro,
    )


# ============================================================
# O.S.
# ============================================================

camada_os = folium.FeatureGroup(
    name="O.S.",
    show=True,
)


for _, linha in pontos.iterrows():

    lat = linha[
        "LATITUDE_NUM"
    ]

    lon = linha[
        "LONGITUDE_NUM"
    ]

    if not coordenada_valida(
        lat,
        lon,
    ):

        continue

    folium.CircleMarker(
        location=[
            lat,
            lon,
        ],
        radius=6,
        weight=1,
        fill=True,
        fill_opacity=0.8,
        tooltip=(
            "O.S. "
            f"{texto(linha.get('Nº da O.S'))}"
            " — "
            f"{texto(linha.get('BAIRRO_KMZ'))}"
        ),
        popup=folium.Popup(
            popup_os(linha),
            max_width=380,
        ),
    ).add_to(
        camada_os
    )


camada_os.add_to(
    mapa
)


# ============================================================
# POÇOS
# ============================================================

camada_pocos = folium.FeatureGroup(
    name="Poços",
    show=True,
)


for _, linha in df_pocos.iterrows():

    lat = linha[
        "LATITUDE_NUM"
    ]

    lon = linha[
        "LONGITUDE_NUM"
    ]

    if not coordenada_valida(
        lat,
        lon,
    ):

        continue

    proximos = pontos_proximos(
        lat,
        lon,
        pontos,
        raio_operacional,
    )

    folium.Marker(
        location=[
            lat,
            lon,
        ],
        tooltip=texto(
            linha.get(
                "IDENTIFICACAO_ATIVO"
            )
        ),
        popup=folium.Popup(
            popup_poco(linha),
            max_width=350,
        ),
        icon=folium.Icon(
            color="blue",
            icon="tint",
            prefix="fa",
        ),
    ).add_to(
        camada_pocos
    )

    if proximos:

        folium.Circle(
            location=[
                lat,
                lon,
            ],
            radius=raio_operacional,
            color="#3388ff",
            weight=1,
            fill=False,
            opacity=0.45,
            tooltip=(
                f"{len(proximos)} O.S. "
                "no raio operacional"
            ),
        ).add_to(
            camada_pocos
        )


camada_pocos.add_to(
    mapa
)


# ============================================================
# LOGGERS
# ============================================================

camada_loggers = folium.FeatureGroup(
    name="Loggers",
    show=True,
)


for _, linha in df_loggers.iterrows():

    lat = linha[
        "LATITUDE_NUM"
    ]

    lon = linha[
        "LONGITUDE_NUM"
    ]

    if not coordenada_valida(
        lat,
        lon,
    ):

        continue

    proximos = pontos_proximos(
        lat,
        lon,
        pontos,
        raio_operacional,
    )

    folium.Marker(
        location=[
            lat,
            lon,
        ],
        tooltip=texto(
            linha.get(
                "IDENTIFICACAO_ATIVO"
            )
        ),
        popup=folium.Popup(
            popup_logger(linha),
            max_width=350,
        ),
        icon=folium.Icon(
            color="green",
            icon="signal",
            prefix="fa",
        ),
    ).add_to(
        camada_loggers
    )

    if proximos:

        folium.Circle(
            location=[
                lat,
                lon,
            ],
            radius=raio_operacional,
            color="#28a745",
            weight=1,
            fill=False,
            opacity=0.45,
        ).add_to(
            camada_loggers
        )


camada_loggers.add_to(
    mapa
)


# ============================================================
# CONCENTRAÇÕES
# ============================================================

camada_concentracoes = folium.FeatureGroup(
    name="Concentrações",
    show=True,
)


for grupo in concentracoes:

    bairros_grupo = ", ".join(
        grupo["bairros"]
    )

    ordens = ", ".join(
        grupo["ordens"][:15]
    )

    popup = f"""
    <div style="min-width:280px">
        <b>Concentração operacional</b><br><br>

        <b>O.S.:</b>
        {grupo["quantidade"]}<br>

        <b>Raio:</b>
        {raio_concentracao} m<br>

        <b>Bairros:</b>
        {bairros_grupo or "Não identificado"}<br>

        <b>Ordens:</b>
        {ordens}
    </div>
    """

    folium.CircleMarker(
        location=[
            grupo["latitude"],
            grupo["longitude"],
        ],
        radius=min(
            8 + grupo["quantidade"] * 2,
            24,
        ),
        color="#dc3545",
        fill=True,
        fill_opacity=0.8,
        tooltip=(
            "Concentração — "
            f"{grupo['quantidade']} O.S."
        ),
        popup=folium.Popup(
            popup,
            max_width=380,
        ),
    ).add_to(
        camada_concentracoes
    )


camada_concentracoes.add_to(
    mapa
)


# ============================================================
# ENQUADRAMENTO
# ============================================================

todas_coordenadas = []


for _, linha in pontos.iterrows():

    if coordenada_valida(
        linha["LATITUDE_NUM"],
        linha["LONGITUDE_NUM"],
    ):

        todas_coordenadas.append(
            [
                float(
                    linha[
                        "LATITUDE_NUM"
                    ]
                ),
                float(
                    linha[
                        "LONGITUDE_NUM"
                    ]
                ),
            ]
        )


for _, linha in df_pocos.iterrows():

    if coordenada_valida(
        linha["LATITUDE_NUM"],
        linha["LONGITUDE_NUM"],
    ):

        todas_coordenadas.append(
            [
                float(
                    linha[
                        "LATITUDE_NUM"
                    ]
                ),
                float(
                    linha[
                        "LONGITUDE_NUM"
                    ]
                ),
            ]
        )


for _, linha in df_loggers.iterrows():

    if coordenada_valida(
        linha["LATITUDE_NUM"],
        linha["LONGITUDE_NUM"],
    ):

        todas_coordenadas.append(
            [
                float(
                    linha[
                        "LATITUDE_NUM"
                    ]
                ),
                float(
                    linha[
                        "LONGITUDE_NUM"
                    ]
                ),
            ]
        )


if len(
    todas_coordenadas
) >= 2:

    mapa.fit_bounds(
        todas_coordenadas,
        padding=(
            30,
            30,
        ),
    )


folium.LayerControl(
    collapsed=False,
).add_to(
    mapa
)


st_folium(
    mapa,
    width=None,
    height=680,
)


# ============================================================
# ANÁLISE POR BAIRRO
# ============================================================

st.subheader(
    "Análise operacional"
)


if pontos.empty:

    st.info(
        "Nenhuma O.S. encontrada "
        "com os filtros atuais."
    )

else:

    ranking = (
        pontos.assign(
            Bairro=pontos[
                "BAIRRO_KMZ"
            ].replace(
                "",
                "Não identificado",
            )
        )
        .groupby(
            "Bairro"
        )
        .size()
        .reset_index(
            name="O.S."
        )
        .sort_values(
            "O.S.",
            ascending=False,
        )
    )

    col_a, col_b = st.columns(
        2
    )

    with col_a:

        st.markdown(
            "#### O.S. por bairro"
        )

        st.dataframe(
            ranking,
            width="stretch",
            hide_index=True,
        )

    with col_b:

        st.markdown(
            "#### Distribuição"
        )

        fig = px.bar(
            ranking.head(15),
            x="Bairro",
            y="O.S.",
            labels={
                "Bairro":
                    "Bairro",
                "O.S.":
                    "Quantidade de O.S.",
            },
        )

        fig.update_layout(
            xaxis_tickangle=-45,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=100,
            ),
        )

        st.plotly_chart(
            fig,
            width="stretch",
        )


# ============================================================
# EVENTOS
# ============================================================

st.subheader(
    "Eventos operacionais"
)


if eventos.empty:

    st.info(
        "Nenhum evento encontrado "
        "com os filtros atuais."
    )

else:

    eventos_exibicao = eventos[
        CABECALHO_EVENTOS
    ].copy()

    for coluna in [
        "Data",
        "Início",
        "Prev. Término",
        "Término Real",
    ]:

        eventos_exibicao[
            coluna
        ] = eventos_exibicao[
            coluna
        ].apply(
            formatar_data
        )

    eventos_exibicao = eventos_exibicao.sort_values(
        "Data",
        ascending=False,
    )

    st.dataframe(
        eventos_exibicao,
        width="stretch",
        hide_index=True,
    )


# ============================================================
# O.S.
# ============================================================

st.subheader(
    "O.S. encontradas"
)


if pontos.empty:

    st.info(
        "Nenhuma O.S. encontrada."
    )

else:

    pontos_exibicao = pontos[
        CABECALHO_PONTOS
    ].copy()

    pontos_exibicao[
        "Dt. Emissão"
    ] = pontos_exibicao[
        "Dt. Emissão"
    ].apply(
        formatar_data
    )

    st.dataframe(
        pontos_exibicao,
        width="stretch",
        hide_index=True,
    )


# ============================================================
# STATUS DO KMZ
# ============================================================

if not caminho_kmz:

    st.warning(
        "O arquivo TERESINA.kmz não foi encontrado. "
        "Coloque-o na mesma pasta do módulo "
        "3_Farol_Operacional.py."
    )

else:

    st.caption(
        f"Mapa de bairros carregado: "
        f"{len(bairros)} polígonos/áreas encontrados "
        f"em {ARQUIVO_KMZ_PADRAO}."
    )
