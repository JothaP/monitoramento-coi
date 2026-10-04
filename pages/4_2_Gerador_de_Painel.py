import streamlit as st
import io
import re
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Relatório de Falta de Água - COI",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none;
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }

        .upload-box {
            border: 1px solid #D9E1EA;
            border-radius: 12px;
            padding: 14px 16px;
            background: #FFFFFF;
        }

        .module-title {
            font-size: 24px;
            font-weight: 700;
            color: #123B5D;
            margin-bottom: 4px;
        }

        .module-subtitle {
            color: #667085;
            font-size: 14px;
            margin-bottom: 18px;
        }

        div[data-testid="stDownloadButton"] button {
            width: 100%;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# MAPAS EXISTENTES
# ============================================================

ZONA_POR_BAIRRO = {
    # NORTE
    "ÁGUA MINERAL": "NORTE",
    "ALEGRE": "NORTE",
    "BUENOS AIRES": "NORTE",
    "CABRAL": "NORTE",
    "EMBRAPA": "NORTE",
    "MOCAMBINHO": "NORTE",
    "MORRO DA ESPERANÇA": "NORTE",
    "PARQUE BRASIL": "NORTE",
    "PRIMAVERA": "NORTE",
    "REAL COMPAGRE": "NORTE",
    "SANTA MARIA": "NORTE",
    "SANTO ANTÔNIO": "NORTE",
    "VALE QUEM TEM": "NORTE",

    # SUL
    "AREIAS": "SUL",
    "CATUMBI": "SUL",
    "CERÂMICA CIL": "SUL",
    "CRISTO REI": "SUL",
    "LOURIVAL PARENTE": "SUL",
    "MACAÚBA": "SUL",
    "MONTE CASTELO": "SUL",
    "MORADA NOVA": "SUL",
    "NOSSA SENHORA DAS GRAÇAS": "SUL",
    "PARQUE PIAUÍ": "SUL",
    "PROMORAR": "SUL",
    "SACARCA": "SUL",
    "SANTA LUZIA": "SUL",
    "TABULETA": "SUL",
    "TRÊS ANDARES": "SUL",

    # LESTE
    "ÁGUA BRANCA": "LESTE",
    "CAMPESTRE": "LESTE",
    "FÁTIMA": "LESTE",
    "FLORES": "LESTE",
    "HORTO": "LESTE",
    "ININGA": "LESTE",
    "JOCKEY": "LESTE",
    "JÓQUEI": "LESTE",
    "MORADA DO SOL": "LESTE",
    "NOSSA SENHORA DE FÁTIMA": "LESTE",
    "NOIVOS": "LESTE",
    "PLANALTO": "LESTE",
    "SAMAPI": "LESTE",
    "SÃO CRISTÓVÃO": "LESTE",
    "SÃO JOÃO": "LESTE",
    "URUGUAI": "LESTE",

    # SUDESTE
    "DIRCEU": "SUDESTE",
    "ITARARÉ": "SUDESTE",
    "RENASCENÇA": "SUDESTE",
    "REDONDA": "SUDESTE",
    "TODOS OS SANTOS": "SUDESTE",
    "USINA SANTANA": "SUDESTE",

    # CENTRO
    "CENTRO": "CENTRO",
    "ILHOTAS": "CENTRO",
    "MATINHA": "CENTRO",
    "MARQUÊS": "CENTRO",
    "MONTE CASTELO": "CENTRO",
}


BASE_POR_CIDADE = {
    "PAULISTANA": "PAULISTANA",
    "PICOS": "PICOS",
    "FLORIANO": "FLORIANO",
    "SÃO RAIMUNDO NONATO": "SAO RAIMUNDO NONATO",
    "SAO RAIMUNDO NONATO": "SAO RAIMUNDO NONATO",
    "BOM JESUS": "BOM JESUS",
    "OEIRAS": "OEIRAS",
    "PIRIPIRI": "PIRIPIRI",
    "PARNAÍBA": "PARNAIBA",
    "PARNAIBA": "PARNAIBA",
    "SÃO JOÃO DO PIAUÍ": "SAO JOAO DO PIAUI",
    "SAO JOAO DO PIAUI": "SAO JOAO DO PIAUI",
    "TERESINA": "MEIO NORTE",
}


MESES_PT = {
    1: "JAN",
    2: "FEV",
    3: "MAR",
    4: "ABR",
    5: "MAI",
    6: "JUN",
    7: "JUL",
    8: "AGO",
    9: "SET",
    10: "OUT",
    11: "NOV",
    12: "DEZ",
}


LOGOS = {
    "API": Path("assets/logos/logo_aguas_do_piaui.png"),
    "THE": Path("assets/logos/logo_aguas_de_teresina.png"),
    "TIM": Path("assets/logos/logo_aguas_de_timon.png"),
}


NOMES_EMPRESAS = {
    "API": "Águas do Piauí",
    "THE": "Águas de Teresina",
    "TIM": "Águas de Timon",
}


TITULOS = {
    "API": "Relatório de Falta de Água — Piauí",
    "THE": "Relatório de Falta de Água — Teresina",
    "TIM": "Relatório de Falta de Água — Timon",
}


# ============================================================
# CORES
# ============================================================

BRANCO = "#FFFFFF"
FUNDO = "#F4F7FA"

AZUL_ESCURO = "#123B5D"
AZUL = "#0077B6"
AZUL_MEDIO = "#2B8CC4"

CINZA = "#667085"
CINZA_CLARO = "#E8EDF2"

TURQUESA = "#00A6A6"

VERMELHO = "#D64545"
VERDE = "#208B4E"
AMARELO = "#E5B700"


# ============================================================
# FONTES
# ============================================================

def localizar_fontes():
    candidatos = [
        Path("BACKLOG_AEGEA/fontes"),
        Path("./BACKLOG_AEGEA/fontes"),
        Path("fontes"),
        Path("./fontes"),
    ]

    for pasta in candidatos:
        if pasta.exists():
            return pasta

    return None


FONTES_AEGEA = localizar_fontes()


def fonte(
    tamanho,
    negrito=False,
):
    arquivos = []

    if FONTES_AEGEA:
        arquivos.extend(
            [
                FONTES_AEGEA / "Aptos.ttf",
                FONTES_AEGEA / "Aptos-Bold.ttf",
                FONTES_AEGEA / "Arial.ttf",
                FONTES_AEGEA / "Arial-Bold.ttf",
                FONTES_AEGEA / "Montserrat-Regular.ttf",
                FONTES_AEGEA / "Montserrat-Bold.ttf",
            ]
        )

    if negrito:
        nomes = [
            "Arial-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        nomes = [
            "Arial.ttf",
            "DejaVuSans.ttf",
        ]

    arquivos.extend(
        Path("/usr/share/fonts/truetype/dejavu").glob(
            "DejaVuSans*.ttf"
        )
    )

    for arquivo in arquivos:
        if arquivo.exists():
            try:
                return ImageFont.truetype(
                    str(arquivo),
                    tamanho,
                )
            except Exception:
                pass

    for nome in nomes:
        try:
            return ImageFont.truetype(nome, tamanho)
        except Exception:
            pass

    return ImageFont.load_default()


# ============================================================
# UTILITÁRIOS
# ============================================================

def normalizar(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    substituicoes = {
        "Á": "A",
        "À": "A",
        "Ã": "A",
        "Â": "A",
        "Ä": "A",
        "É": "E",
        "È": "E",
        "Ê": "E",
        "Ë": "E",
        "Í": "I",
        "Ì": "I",
        "Î": "I",
        "Ï": "I",
        "Ó": "O",
        "Ò": "O",
        "Õ": "O",
        "Ô": "O",
        "Ö": "O",
        "Ú": "U",
        "Ù": "U",
        "Û": "U",
        "Ü": "U",
        "Ç": "C",
    }

    for antigo, novo in substituicoes.items():
        texto = texto.replace(antigo, novo)

    texto = re.sub(r"\s+", " ", texto)

    return texto


def normalizar_cidade(valor):
    return normalizar(valor)


def obter_zona(bairro):
    bairro_n = normalizar(bairro)

    for chave, zona in ZONA_POR_BAIRRO.items():
        if normalizar(chave) == bairro_n:
            return zona

    return "NÃO IDENTIFICADA"


def obter_base(cidade):
    cidade_n = normalizar_cidade(cidade)

    for chave, base in BASE_POR_CIDADE.items():
        if normalizar_cidade(chave) == cidade_n:
            return base

    return ""


def localizar_coluna(df, candidatos):
    mapa = {}

    for coluna in df.columns:
        chave = normalizar(coluna)
        chave = re.sub(r"[^A-Z0-9]", "", chave)
        mapa[chave] = coluna

    for candidato in candidatos:
        chave = normalizar(candidato)
        chave = re.sub(r"[^A-Z0-9]", "", chave)

        if chave in mapa:
            return mapa[chave]

    for coluna in df.columns:
        coluna_n = normalizar(coluna)
        coluna_n = re.sub(r"[^A-Z0-9]", "", coluna_n)

        for candidato in candidatos:
            candidato_n = normalizar(candidato)
            candidato_n = re.sub(r"[^A-Z0-9]", "", candidato_n)

            if candidato_n and candidato_n in coluna_n:
                return coluna

    return None


# ============================================================
# CONVERSÃO DA DATA DE ABERTURA
# ============================================================

def converter_abertura(valor):
    """
    A coluna considerada como abertura da O.S. é:
        Início do SLA

    Formato esperado:
        dd/mm/aaaa hh:mm

    Para o relatório, somente a data é considerada.
    """

    if pd.isna(valor):
        return pd.NaT

    # Se o Excel já entregou como Timestamp
    if isinstance(valor, pd.Timestamp):
        return valor.normalize()

    if isinstance(valor, datetime):
        return pd.Timestamp(valor).normalize()

    if isinstance(valor, date):
        return pd.Timestamp(valor).normalize()

    # Caso seja número serial do Excel
    if isinstance(valor, (int, float, np.integer, np.floating)):
        try:
            numero = float(valor)

            if 20000 < numero < 60000:
                data = (
                    pd.Timestamp("1899-12-30")
                    + pd.to_timedelta(numero, unit="D")
                )

                return data.normalize()
        except Exception:
            pass

    texto = str(valor).strip()

    if not texto:
        return pd.NaT

    # Formato principal:
    # dd/mm/aaaa hh:mm
    formatos = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for formato in formatos:
        try:
            data = pd.to_datetime(
                texto,
                format=formato,
                errors="raise",
            )

            return data.normalize()

        except Exception:
            pass

    # Última tentativa
    try:
        data = pd.to_datetime(
            texto,
            dayfirst=True,
            errors="coerce",
        )

        if not pd.isna(data):
            return data.normalize()

    except Exception:
        pass

    return pd.NaT


# ============================================================
# FORMATAÇÃO
# ============================================================

def formatar_numero(numero):
    try:
        return f"{int(numero):,}".replace(",", ".")
    except Exception:
        return "0"


def abreviar_texto(texto, limite):
    texto = str(texto)

    if len(texto) <= limite:
        return texto

    return texto[: limite - 3] + "..."


def texto_cabecalho_periodo(valor, modo):
    if modo == "Por dia":
        return valor.strftime("%d/%m")

    return f"{MESES_PT[valor.month]}/{str(valor.year)[2:]}"


# ============================================================
# LEITURA DE ARQUIVO
# ============================================================

def ler_planilha(arquivo):
    if arquivo is None:
        return None

    nome = arquivo.name.lower()

    try:
        arquivo.seek(0)

        if nome.endswith(".xlsx"):
            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="openpyxl",
            )

        elif nome.endswith(".xlsb"):
            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="pyxlsb",
            )

        elif nome.endswith(".xls"):
            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="xlrd",
            )

        else:
            st.error(
                "Formato não suportado. "
                "Use .xlsx, .xls ou .xlsb."
            )

            return None

    except Exception as erro:
        st.error(
            f"Não foi possível ler o arquivo: {erro}"
        )

        return None


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

def preparar_dados(df, modulo):

    if df is None or df.empty:
        return None, "A planilha está vazia."

    dados = df.copy()

    # --------------------------------------------------------
    # DATA DE ABERTURA
    # --------------------------------------------------------
    #
    # IMPORTANTE:
    # A coluna oficial é "Início do SLA".
    #
    # --------------------------------------------------------

    coluna_abertura = localizar_coluna(
        dados,
        [
            "Início do SLA",
        ],
    )

    if coluna_abertura is None:
        return (
            None,
            "Não foi encontrada a coluna 'Início do SLA'.",
        )

    # --------------------------------------------------------
    # PROTOCOLO
    # --------------------------------------------------------

    coluna_protocolo = localizar_coluna(
        dados,
        [
            "Cód. Protocolo Origem",
            "Cod. Protocolo Origem",
            "Código Protocolo Origem",
            "Codigo Protocolo Origem",
            "Protocolo",
            "Protocolo Origem",
            "OS",
            "O.S.",
        ],
    )

    # --------------------------------------------------------
    # CONVERSÃO DA DATA
    # --------------------------------------------------------

    dados["_ABERTURA"] = dados[
        coluna_abertura
    ].apply(
        converter_abertura
    )

    # --------------------------------------------------------
    # PROTOCOLO
    # --------------------------------------------------------

    if coluna_protocolo:

        dados["_PROTOCOLO"] = (
            dados[coluna_protocolo]
            .astype(str)
            .str.strip()
        )

        dados.loc[
            dados["_PROTOCOLO"].isin(
                [
                    "",
                    "NAN",
                    "NONE",
                    "NAT",
                ]
            ),
            "_PROTOCOLO",
        ] = np.nan

    else:

        dados["_PROTOCOLO"] = np.nan

    # --------------------------------------------------------
    # REMOVE REGISTROS SEM DATA
    # --------------------------------------------------------

    dados = dados.dropna(
        subset=["_ABERTURA"]
    ).copy()

    if dados.empty:
        return (
            None,
            "Nenhum registro possui data de abertura válida na coluna 'Início do SLA'.",
        )

    # --------------------------------------------------------
    # THE / TIM
    # --------------------------------------------------------

    if modulo in ["THE", "TIM"]:

        coluna_bairro = localizar_coluna(
            dados,
            [
                "Bairro",
                "BAIRRO",
                "Bairro do Cliente",
                "Bairro Cliente",
            ],
        )

        if coluna_bairro is None:
            return (
                None,
                "Não foi encontrada a coluna de Bairro.",
            )

        dados["_LOCAL"] = (
            dados[coluna_bairro]
            .fillna("NÃO INFORMADO")
            .astype(str)
            .str.strip()
        )

        dados["_LOCAL"] = dados[
            "_LOCAL"
        ].replace(
            {
                "": "NÃO INFORMADO",
                "nan": "NÃO INFORMADO",
                "NaN": "NÃO INFORMADO",
            }
        )

    # --------------------------------------------------------
    # API
    # --------------------------------------------------------

    elif modulo == "API":

        coluna_cidade = localizar_coluna(
            dados,
            [
                "Cidade",
                "Município",
                "Municipio",
                "Município Cliente",
                "Cidade Cliente",
            ],
        )

        if coluna_cidade is None:
            return (
                None,
                "Não foi encontrada a coluna de Cidade/Município.",
            )

        dados["_LOCAL"] = (
            dados[coluna_cidade]
            .fillna("NÃO INFORMADA")
            .astype(str)
            .str.strip()
        )

        dados["_LOCAL"] = dados[
            "_LOCAL"
        ].replace(
            {
                "": "NÃO INFORMADA",
                "nan": "NÃO INFORMADA",
                "NaN": "NÃO INFORMADA",
            }
        )

        dados["_BASE"] = dados[
            "_LOCAL"
        ].apply(
            obter_base
        )

    # --------------------------------------------------------
    # CAMPOS TEMPORAIS
    # --------------------------------------------------------

    # _ABERTURA já está normalizado para:
    # dd/mm/aaaa 00:00:00

    dados["_DATA"] = dados[
        "_ABERTURA"
    ].dt.normalize()

    dados["_MES_ORDEM"] = (
        dados["_ABERTURA"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    return dados, None


# ============================================================
# CONTAGEM
# ============================================================

def contar_os(series):

    protocolos = series[
        "_PROTOCOLO"
    ]

    validos = protocolos.dropna()

    if not validos.empty:
        return validos.nunique()

    return len(series)


def gerar_agregacao(
    df,
    modo,
):

    dados = df.copy()

    if modo == "Por dia":
        dados["_PERIODO"] = dados[
            "_DATA"
        ]
    else:
        dados["_PERIODO"] = dados[
            "_MES_ORDEM"
        ]

    grupos = []

    for periodo, bloco_periodo in dados.groupby(
        "_PERIODO",
        sort=True,
    ):

        grupos.append(
            {
                "PERIODO": periodo,
                "TOTAL": contar_os(
                    bloco_periodo
                ),
            }
        )

    if not grupos:
        return pd.DataFrame(
            columns=[
                "PERIODO",
                "TOTAL",
            ]
        )

    return pd.DataFrame(
        grupos
    )


def gerar_tabela_local_periodo(
    df,
    modo,
):

    dados = df.copy()

    if modo == "Por dia":
        dados["_PERIODO"] = dados[
            "_DATA"
        ]
    else:
        dados["_PERIODO"] = dados[
            "_MES_ORDEM"
        ]

    tabela = {}

    locais = sorted(
        dados["_LOCAL"]
        .dropna()
        .astype(str)
        .unique()
    )

    periodos = sorted(
        dados["_PERIODO"]
        .dropna()
        .unique()
    )

    for local in locais:

        linha = []

        for periodo in periodos:

            bloco = dados[
                (dados["_LOCAL"] == local)
                & (
                    dados["_PERIODO"]
                    == periodo
                )
            ]

            linha.append(
                contar_os(bloco)
            )

        tabela[local] = linha

    resultado = pd.DataFrame(
        tabela,
        index=periodos,
    ).T

    resultado.index.name = "LOCAL"

    return resultado


# ============================================================
# DESENHO
# ============================================================

def cor_intensidade(
    valor,
    maximo,
):

    if maximo <= 0 or valor <= 0:
        return "#F1F4F7"

    proporcao = valor / maximo

    if proporcao >= 0.75:
        return "#123B5D"

    if proporcao >= 0.50:
        return "#2B8CC4"

    if proporcao >= 0.25:
        return "#7BB8D8"

    return "#DCECF5"


def cor_texto_celula(
    valor,
    maximo,
):

    if (
        maximo > 0
        and valor / maximo >= 0.75
    ):
        return BRANCO

    return AZUL_ESCURO


def texto_centralizado(
    draw,
    box,
    texto,
    fonte_obj,
    fill,
):

    x1, y1, x2, y2 = box

    bbox = draw.textbbox(
        (0, 0),
        texto,
        font=fonte_obj,
    )

    largura = bbox[2] - bbox[0]
    altura = bbox[3] - bbox[1]

    x = (
        x1
        + ((x2 - x1) - largura) / 2
    )

    y = (
        y1
        + ((y2 - y1) - altura) / 2
        - 2
    )

    draw.text(
        (x, y),
        texto,
        font=fonte_obj,
        fill=fill,
    )


def desenhar_card(
    draw,
    x,
    y,
    largura,
    altura,
    titulo,
    valor,
):

    draw.rounded_rectangle(
        (
            x,
            y,
            x + largura,
            y + altura,
        ),
        radius=18,
        fill=BRANCO,
        outline=CINZA_CLARO,
        width=2,
    )

    draw.text(
        (
            x + 24,
            y + 20,
        ),
        titulo,
        font=fonte(
            17,
            True,
        ),
        fill=CINZA,
    )

    draw.text(
        (
            x + 24,
            y + 55,
        ),
        str(valor),
        font=fonte(
            30,
            True,
        ),
        fill=AZUL_ESCURO,
    )


def desenhar_barra(
    draw,
    x,
    y,
    largura,
    altura,
    valor,
    maximo,
):

    draw.rounded_rectangle(
        (
            x,
            y,
            x + largura,
            y + altura,
        ),
        radius=6,
        fill=CINZA_CLARO,
    )

    if maximo > 0:

        largura_valor = int(
            largura
            * (valor / maximo)
        )

        if largura_valor > 0:

            draw.rounded_rectangle(
                (
                    x,
                    y,
                    x + largura_valor,
                    y + altura,
                ),
                radius=6,
                fill=AZUL,
            )


def desenhar_logo(
    imagem,
    logo_path,
    x,
    y,
    max_width,
    max_height,
):

    if not logo_path.exists():
        return

    try:

        logo = Image.open(
            logo_path
        ).convert("RGBA")

        logo.thumbnail(
            (
                max_width,
                max_height,
            ),
            Image.Resampling.LANCZOS,
        )

        imagem.alpha_composite(
            logo,
            (
                x,
                y,
            ),
        )

    except Exception:
        pass


# ============================================================
# PAINEL PRINCIPAL
# ============================================================

def gerar_painel(
    df,
    modulo,
    modo,
    base=None,
):

    if df is None or df.empty:
        raise ValueError(
            "Não existem dados para gerar o painel."
        )

    dados = df.copy()

    # --------------------------------------------------------
    # FILTRO API
    # --------------------------------------------------------

    if modulo == "API" and base:

        dados = dados[
            dados["_BASE"] == base
        ].copy()

    if dados.empty:
        raise ValueError(
            "Não existem registros para o filtro selecionado."
        )

    # --------------------------------------------------------
    # AGREGADOS
    # --------------------------------------------------------

    tabela = gerar_tabela_local_periodo(
        dados,
        modo,
    )

    if tabela.empty:
        raise ValueError(
            "Não foi possível gerar a tabela."
        )

    tabela = tabela.sort_index()

    periodos = list(
        tabela.columns
    )

    locais = list(
        tabela.index
    )

    # --------------------------------------------------------
    # TOTAIS
    # --------------------------------------------------------

    tabela["_TOTAL"] = tabela[
        periodos
    ].sum(
        axis=1
    )

    total_geral = int(
        tabela["_TOTAL"].sum()
    )

    local_maior = (
        tabela["_TOTAL"].idxmax()
        if not tabela.empty
        else "-"
    )

    totais_periodo = tabela[
        periodos
    ].sum(
        axis=0
    )

    periodo_critico = (
        totais_periodo.idxmax()
        if not totais_periodo.empty
        else None
    )

    # --------------------------------------------------------
    # DIMENSÕES
    # --------------------------------------------------------

    margem = 70

    largura = 1800

    altura_cabecalho = 300
    altura_cards = 220
    altura_titulo_tabela = 110
    altura_linha = 62
    altura_grafico = 460
    altura_rodape = 100

    largura_local = 390
    largura_periodo = 105
    largura_total = 125

    largura_tabela = (
        largura_local
        + len(periodos)
        * largura_periodo
        + largura_total
    )

    largura = max(
        largura,
        largura_tabela
        + margem * 2,
    )

    altura_tabela = (
        altura_titulo_tabela
        + len(locais)
        * altura_linha
    )

    altura = (
        altura_cabecalho
        + altura_cards
        + 50
        + altura_tabela
        + 70
        + altura_grafico
        + altura_rodape
    )

    imagem = Image.new(
        "RGBA",
        (
            largura,
            altura,
        ),
        FUNDO,
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # --------------------------------------------------------
    # CABEÇALHO
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            largura,
            12,
        ),
        fill=AZUL_ESCURO,
    )

    titulo = TITULOS[
        modulo
    ]

    if modulo == "API":

        if base:

            subtitulo = (
                "Painel de Reclamações de "
                f"Falta de Água • {base}"
            )

        else:

            subtitulo = (
                "Painel de Reclamações "
                "de Falta de Água"
            )

    else:

        subtitulo = (
            "Painel de Reclamações de "
            f"Falta de Água • {modo}"
        )

    draw.text(
        (
            margem,
            55,
        ),
        titulo,
        font=fonte(
            40,
            True,
        ),
        fill=AZUL_ESCURO,
    )

    draw.text(
        (
            margem,
            112,
        ),
        subtitulo,
        font=fonte(22),
        fill=CINZA,
    )

    # --------------------------------------------------------
    # PERÍODO
    # --------------------------------------------------------

    data_min = dados[
        "_DATA"
    ].min()

    data_max = dados[
        "_DATA"
    ].max()

    if modo == "Por dia":

        periodo_texto = (
            f"Período: "
            f"{data_min.strftime('%d/%m/%Y')} "
            f"a "
            f"{data_max.strftime('%d/%m/%Y')}"
        )

    else:

        periodo_texto = (
            f"Período: "
            f"{MESES_PT[data_min.month]}/"
            f"{data_min.year} "
            f"a "
            f"{MESES_PT[data_max.month]}/"
            f"{data_max.year}"
        )

    draw.text(
        (
            margem,
            160,
        ),
        periodo_texto,
        font=fonte(18),
        fill=CINZA,
    )

    # --------------------------------------------------------
    # LOGO
    # --------------------------------------------------------

    desenhar_logo(
        imagem,
        LOGOS[modulo],
        largura - margem - 330,
        45,
        330,
        130,
    )

    # --------------------------------------------------------
    # CARDS
    # --------------------------------------------------------

    y_cards = altura_cabecalho

    espaco_card = 25

    largura_card = (
        largura
        - 2 * margem
        - 2 * espaco_card
    ) / 3

    desenhar_card(
        draw,
        margem,
        y_cards,
        largura_card,
        altura_cards,
        "TOTAL DE O.S. / RECLAMAÇÕES",
        formatar_numero(
            total_geral
        ),
    )

    desenhar_card(
        draw,
        margem
        + largura_card
        + espaco_card,
        y_cards,
        largura_card,
        altura_cards,
        "LOCAL COM MAIOR VOLUME",
        abreviar_texto(
            local_maior,
            24,
        ),
    )

    desenhar_card(
        draw,
        margem
        + (
            largura_card
            + espaco_card
        ) * 2,
        y_cards,
        largura_card,
        altura_cards,
        "PERÍODO CRÍTICO",
        (
            texto_cabecalho_periodo(
                periodo_critico,
                modo,
            )
            if periodo_critico is not None
            else "-"
        ),
    )

    # --------------------------------------------------------
    # TABELA
    # --------------------------------------------------------

    y_tabela = (
        y_cards
        + altura_cards
        + 50
    )

    draw.text(
        (
            margem,
            y_tabela,
        ),
        (
            "VOLUME POR BAIRRO"
            if modulo in ["THE", "TIM"]
            else "VOLUME POR CIDADE"
        ),
        font=fonte(
            27,
            True,
        ),
        fill=AZUL_ESCURO,
    )

    y_inicio = (
        y_tabela
        + altura_titulo_tabela
        - 20
    )

    x_inicio = margem

    # --------------------------------------------------------
    # CABEÇALHO DA TABELA
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            x_inicio,
            y_inicio,
            x_inicio + largura_tabela,
            y_inicio + altura_linha,
        ),
        radius=8,
        fill=AZUL_ESCURO,
    )

    draw.text(
        (
            x_inicio + 18,
            y_inicio + 17,
        ),
        (
            "BAIRRO"
            if modulo in ["THE", "TIM"]
            else "CIDADE"
        ),
        font=fonte(
            18,
            True,
        ),
        fill=BRANCO,
    )

    for indice, periodo in enumerate(
        periodos
    ):

        x = (
            x_inicio
            + largura_local
            + indice
            * largura_periodo
        )

        titulo_periodo = (
            texto_cabecalho_periodo(
                periodo,
                modo,
            )
        )

        texto_centralizado(
            draw,
            (
                x,
                y_inicio,
                x + largura_periodo,
                y_inicio + altura_linha,
            ),
            titulo_periodo,
            fonte(
                15,
                True,
            ),
            BRANCO,
        )

    x_total = (
        x_inicio
        + largura_local
        + len(periodos)
        * largura_periodo
    )

    texto_centralizado(
        draw,
        (
            x_total,
            y_inicio,
            x_total + largura_total,
            y_inicio + altura_linha,
        ),
        "TOTAL",
        fonte(
            16,
            True,
        ),
        BRANCO,
    )

    # --------------------------------------------------------
    # LINHAS
    # --------------------------------------------------------

    maximo = (
        int(
            tabela[
                periodos
            ].max().max()
        )
        if periodos
        else 0
    )

    for linha_idx, local in enumerate(
        locais
    ):

        y = (
            y_inicio
            + altura_linha
            + linha_idx
            * altura_linha
        )

        fill_linha = (
            BRANCO
            if linha_idx % 2 == 0
            else "#F8FAFC"
        )

        draw.rectangle(
            (
                x_inicio,
                y,
                x_inicio + largura_tabela,
                y + altura_linha,
            ),
            fill=fill_linha,
        )

        texto_local = abreviar_texto(
            local,
            35,
        )

        draw.text(
            (
                x_inicio + 18,
                y + 18,
            ),
            texto_local,
            font=fonte(
                16,
                True,
            ),
            fill=AZUL_ESCURO,
        )

        for indice, periodo in enumerate(
            periodos
        ):

            x = (
                x_inicio
                + largura_local
                + indice
                * largura_periodo
            )

            valor = int(
                tabela.loc[
                    local,
                    periodo,
                ]
            )

            cor = cor_intensidade(
                valor,
                maximo,
            )

            draw.rectangle(
                (
                    x + 2,
                    y + 2,
                    x + largura_periodo - 2,
                    y + altura_linha - 2,
                ),
                fill=cor,
            )

            texto_centralizado(
                draw,
                (
                    x,
                    y,
                    x + largura_periodo,
                    y + altura_linha,
                ),
                formatar_numero(
                    valor
                ),
                fonte(
                    15,
                    True,
                ),
                cor_texto_celula(
                    valor,
                    maximo,
                ),
            )

        total_local = int(
            tabela.loc[
                local,
                "_TOTAL",
            ]
        )

        texto_centralizado(
            draw,
            (
                x_total,
                y,
                x_total + largura_total,
                y + altura_linha,
            ),
            formatar_numero(
                total_local
            ),
            fonte(
                16,
                True,
            ),
            AZUL_ESCURO,
        )

    # --------------------------------------------------------
    # GRÁFICO
    # --------------------------------------------------------

    y_grafico = (
        y_inicio
        + altura_linha
        + len(locais)
        * altura_linha
        + 60
    )

    draw.text(
        (
            margem,
            y_grafico,
        ),
        "EVOLUÇÃO DO VOLUME",
        font=fonte(
            27,
            True,
        ),
        fill=AZUL_ESCURO,
    )

    grafico_y = (
        y_grafico + 70
    )

    grafico_h = (
        altura_grafico - 100
    )

    grafico_x = margem

    grafico_w = (
        largura - 2 * margem
    )

    draw.rounded_rectangle(
        (
            grafico_x,
            grafico_y,
            grafico_x + grafico_w,
            grafico_y + grafico_h,
        ),
        radius=14,
        fill=BRANCO,
        outline=CINZA_CLARO,
        width=2,
    )

    valores_grafico = [
        int(
            totais_periodo[p]
        )
        for p in periodos
    ]

    if valores_grafico:

        max_grafico = max(
            valores_grafico
        )

        if max_grafico <= 0:
            max_grafico = 1

        eixo_x = (
            grafico_x + 70
        )

        eixo_y = (
            grafico_y
            + grafico_h
            - 60
        )

        eixo_topo = (
            grafico_y + 40
        )

        eixo_direita = (
            grafico_x
            + grafico_w
            - 35
        )

        # Linhas horizontais
        for i in range(5):

            proporcao = i / 4

            yy = (
                eixo_y
                - (
                    eixo_y
                    - eixo_topo
                )
                * proporcao
            )

            draw.line(
                (
                    eixo_x,
                    yy,
                    eixo_direita,
                    yy,
                ),
                fill=CINZA_CLARO,
                width=2,
            )

            valor_eixo = int(
                max_grafico
                * proporcao
            )

            draw.text(
                (
                    grafico_x + 15,
                    yy - 10,
                ),
                formatar_numero(
                    valor_eixo
                ),
                font=fonte(13),
                fill=CINZA,
            )

        n = len(periodos)

        if n == 1:

            pontos = [
                (
                    (
                        eixo_x
                        + eixo_direita
                    ) // 2,
                    eixo_y
                    - (
                        valores_grafico[0]
                        / max_grafico
                    )
                    * (
                        eixo_y
                        - eixo_topo
                    ),
                )
            ]

        else:

            pontos = []

            for i, valor in enumerate(
                valores_grafico
            ):

                xx = (
                    eixo_x
                    + (
                        i
                        / (n - 1)
                    )
                    * (
                        eixo_direita
                        - eixo_x
                    )
                )

                yy = (
                    eixo_y
                    - (
                        valor
                        / max_grafico
                    )
                    * (
                        eixo_y
                        - eixo_topo
                    )
                )

                pontos.append(
                    (
                        int(xx),
                        int(yy),
                    )
                )

        if len(pontos) >= 2:

            draw.line(
                pontos,
                fill=AZUL,
                width=6,
            )

        for i, ponto in enumerate(
            pontos
        ):

            xx, yy = ponto

            draw.ellipse(
                (
                    xx - 8,
                    yy - 8,
                    xx + 8,
                    yy + 8,
                ),
                fill=AZUL,
            )

            valor = valores_grafico[
                i
            ]

            draw.text(
                (
                    xx - 20,
                    yy - 38,
                ),
                formatar_numero(
                    valor
                ),
                font=fonte(
                    14,
                    True,
                ),
                fill=AZUL_ESCURO,
            )

            if len(periodos) <= 20:

                texto_periodo = (
                    texto_cabecalho_periodo(
                        periodos[i],
                        modo,
                    )
                )

                bbox = draw.textbbox(
                    (0, 0),
                    texto_periodo,
                    font=fonte(
                        13,
                        True,
                    ),
                )

                largura_txt = (
                    bbox[2]
                    - bbox[0]
                )

                draw.text(
                    (
                        xx
                        - largura_txt / 2,
                        eixo_y + 15,
                    ),
                    texto_periodo,
                    font=fonte(
                        13,
                        True,
                    ),
                    fill=CINZA,
                )

    # --------------------------------------------------------
    # RODAPÉ
    # --------------------------------------------------------

    y_rodape = (
        altura
        - altura_rodape
        + 25
    )

    draw.line(
        (
            margem,
            y_rodape,
            largura - margem,
            y_rodape,
        ),
        fill=CINZA_CLARO,
        width=2,
    )

    empresa = NOMES_EMPRESAS[
        modulo
    ]

    draw.text(
        (
            margem,
            y_rodape + 25,
        ),
        (
            f"{empresa} • "
            "Controle Operacional Integrado — COI"
        ),
        font=fonte(16),
        fill=CINZA,
    )

    draw.text(
        (
            largura - margem - 250,
            y_rodape + 25,
        ),
        datetime.now().strftime(
            "Gerado em %d/%m/%Y %H:%M"
        ),
        font=fonte(15),
        fill=CINZA,
    )

    # --------------------------------------------------------
    # PNG
    # --------------------------------------------------------

    output = io.BytesIO()

    imagem_rgb = imagem.convert(
        "RGB"
    )

    imagem_rgb.save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)

    return output


# ============================================================
# INTERFACE
# ============================================================

st.markdown(
    '<div class="module-title">'
    'Relatório de Falta de Água - COI'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="module-subtitle">'
    "Carregue as bases operacionais e gere o "
    "relatório consolidado de reclamações."
    "</div>",
    unsafe_allow_html=True,
)


# ============================================================
# UPLOADS
# ============================================================

col_api, col_the, col_tim = st.columns(
    3,
    gap="medium",
)

with col_api:

    st.markdown("### API")

    arquivo_api = st.file_uploader(
        "Planilha API",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        key="upload_api",
    )

with col_the:

    st.markdown("### THE")

    arquivo_the = st.file_uploader(
        "Planilha THE",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        key="upload_the",
    )

with col_tim:

    st.markdown("### TIM")

    arquivo_tim = st.file_uploader(
        "Planilha TIM",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        key="upload_tim",
    )


st.divider()


# ============================================================
# SELEÇÃO DO MÓDULO
# ============================================================

st.markdown(
    "### Configuração do relatório"
)

col1, col2 = st.columns(
    [1, 1],
    gap="large",
)

with col1:

    modulo = st.radio(
        "Empresa / operação",
        [
            "API",
            "THE",
            "TIM",
        ],
        horizontal=True,
    )

with col2:

    modo = st.radio(
        "Apresentação temporal",
        [
            "Por dia",
            "Por mês",
        ],
        horizontal=True,
    )


# ============================================================
# API — SELEÇÃO DE BASE
# ============================================================

base_selecionada = None

if modulo == "API":

    st.markdown(
        "#### Base operacional"
    )

    bases_disponiveis = []

    if arquivo_api is not None:

        df_api_preview = ler_planilha(
            arquivo_api
        )

        if df_api_preview is not None:

            df_api_preview, erro_preview = (
                preparar_dados(
                    df_api_preview,
                    "API",
                )
            )

            if df_api_preview is not None:

                bases_disponiveis = sorted(
                    [
                        b
                        for b in df_api_preview[
                            "_BASE"
                        ]
                        .dropna()
                        .unique()
                        if b
                    ]
                )

    opcoes_base = [
        "Todas"
    ] + bases_disponiveis

    base_escolhida = st.selectbox(
        "Selecione a base",
        opcoes_base,
    )

    if base_escolhida != "Todas":
        base_selecionada = (
            base_escolhida
        )


st.divider()


# ============================================================
# ARQUIVO SELECIONADO
# ============================================================

arquivos = {
    "API": arquivo_api,
    "THE": arquivo_the,
    "TIM": arquivo_tim,
}

arquivo_selecionado = arquivos[
    modulo
]


if arquivo_selecionado is None:

    st.info(
        f"Carregue a planilha de {modulo} "
        "para gerar o relatório."
    )

    st.stop()


# ============================================================
# PREPARAÇÃO
# ============================================================

with st.spinner(
    f"Preparando os dados de {modulo}..."
):

    df_original = ler_planilha(
        arquivo_selecionado
    )

    if df_original is None:
        st.stop()

    df, erro = preparar_dados(
        df_original,
        modulo,
    )


if erro:

    st.error(
        erro
    )

    st.stop()


# ============================================================
# INFORMAÇÕES DA BASE
# ============================================================

data_min = df[
    "_DATA"
].min()

data_max = df[
    "_DATA"
].max()

total_registros = len(df)


if modulo == "API":

    cidades = df[
        "_LOCAL"
    ].nunique()

    bases = (
        df["_BASE"]
        .replace(
            "",
            np.nan,
        )
        .dropna()
        .nunique()
    )

    info1, info2, info3 = st.columns(
        3
    )

    with info1:

        st.metric(
            "Registros",
            formatar_numero(
                total_registros
            ),
        )

    with info2:

        st.metric(
            "Cidades",
            formatar_numero(
                cidades
            ),
        )

    with info3:

        st.metric(
            "Bases identificadas",
            formatar_numero(
                bases
            ),
        )

else:

    bairros = df[
        "_LOCAL"
    ].nunique()

    info1, info2, info3 = st.columns(
        3
    )

    with info1:

        st.metric(
            "Registros",
            formatar_numero(
                total_registros
            ),
        )

    with info2:

        st.metric(
            "Bairros",
            formatar_numero(
                bairros
            ),
        )

    with info3:

        st.metric(
            "Período",
            (
                f"{data_min.strftime('%d/%m/%Y')} "
                f"a "
                f"{data_max.strftime('%d/%m/%Y')}"
            ),
        )


# ============================================================
# BOTÃO DE GERAÇÃO
# ============================================================

st.markdown("")

gerar = st.button(
    "GERAR RELATÓRIO",
    type="primary",
    use_container_width=True,
)


# ============================================================
# GERAÇÃO
# ============================================================

if gerar:

    with st.spinner(
        "Gerando relatório..."
    ):

        try:

            imagem_bytes = gerar_painel(
                df=df,
                modulo=modulo,
                modo=modo,
                base=base_selecionada,
            )

            st.session_state[
                "relatorio_gerado"
            ] = imagem_bytes.getvalue()

            st.session_state[
                "relatorio_modulo"
            ] = modulo

            st.session_state[
                "relatorio_modo"
            ] = modo

            st.session_state[
                "relatorio_base"
            ] = base_selecionada

        except Exception as erro:

            st.error(
                f"Erro ao gerar o relatório: {erro}"
            )

            st.stop()


# ============================================================
# RESULTADO
# ============================================================

if (
    "relatorio_gerado"
    in st.session_state
):

    st.divider()

    st.markdown(
        "### Relatório gerado"
    )

    imagem_final = st.session_state[
        "relatorio_gerado"
    ]

    modulo_final = st.session_state[
        "relatorio_modulo"
    ]

    modo_final = st.session_state[
        "relatorio_modo"
    ]

    base_final = st.session_state[
        "relatorio_base"
    ]

    if base_final:

        nome_arquivo = (
            f"RELATORIO_FA_{modulo_final}_"
            f"{normalizar(base_final).replace(' ', '_')}_"
            f"{modo_final.replace(' ', '_')}.png"
        )

    else:

        nome_arquivo = (
            f"RELATORIO_FA_{modulo_final}_"
            f"{modo_final.replace(' ', '_')}.png"
        )

    st.image(
        imagem_final,
        use_container_width=True,
    )

    st.download_button(
        label="BAIXAR RELATÓRIO EM PNG",
        data=imagem_final,
        file_name=nome_arquivo,
        mime="image/png",
        use_container_width=True,
    )
