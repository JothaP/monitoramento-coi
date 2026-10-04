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

VERMELHO = "#D64545"


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


def fonte(tamanho, negrito=False):
    arquivos = []

    if FONTES_AEGEA:
        if negrito:
            arquivos.extend(
                [
                    FONTES_AEGEA / "Aptos-Bold.ttf",
                    FONTES_AEGEA / "Arial-Bold.ttf",
                    FONTES_AEGEA / "Montserrat-Bold.ttf",
                ]
            )
        else:
            arquivos.extend(
                [
                    FONTES_AEGEA / "Aptos.ttf",
                    FONTES_AEGEA / "Arial.ttf",
                    FONTES_AEGEA / "Montserrat-Regular.ttf",
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
            candidato_n = re.sub(
                r"[^A-Z0-9]",
                "",
                candidato_n,
            )

            if candidato_n and candidato_n in coluna_n:
                return coluna

    return None


# ============================================================
# CONVERSÃO DA DATA
# ============================================================

def converter_abertura(valor):

    if pd.isna(valor):
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, datetime):
        return pd.Timestamp(valor)

    if isinstance(valor, date):
        return pd.Timestamp(valor)

    texto = str(valor).strip()

    if not texto:
        return pd.NaT

    # --------------------------------------------------------
    # FORMATO PRINCIPAL:
    # dd/mm/aaaa hh:mm
    # --------------------------------------------------------

    try:

        resultado = pd.to_datetime(
            texto,
            format="%d/%m/%Y %H:%M",
            errors="raise",
        )

        return resultado

    except Exception:
        pass

    # --------------------------------------------------------
    # OUTROS FORMATOS
    # --------------------------------------------------------

    formatos = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%y",
    ]

    for formato in formatos:

        try:

            return pd.to_datetime(
                texto,
                format=formato,
                errors="raise",
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # EXCEL SERIAL
    # --------------------------------------------------------

    if re.fullmatch(
        r"\d+(\.\d+)?",
        texto,
    ):

        try:

            numero = float(texto)

            if 20000 < numero < 60000:

                return (
                    pd.Timestamp("1899-12-30")
                    + pd.to_timedelta(
                        numero,
                        unit="D",
                    )
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # MÊS/ANO
    # --------------------------------------------------------

    meses = {
        "JAN": 1,
        "FEV": 2,
        "MAR": 3,
        "ABR": 4,
        "MAI": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SET": 9,
        "OUT": 10,
        "NOV": 11,
        "DEZ": 12,
    }

    texto_n = normalizar(texto)

    match = re.match(
        r"([A-Z]{3,})[/\-](\d{4})",
        texto_n,
    )

    if match:

        mes_texto = match.group(1)[:3]
        ano = int(match.group(2))

        if mes_texto in meses:

            return pd.Timestamp(
                year=ano,
                month=meses[mes_texto],
                day=1,
            )

    return pd.to_datetime(
        texto,
        errors="coerce",
        dayfirst=True,
    )


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

    return (
        f"{MESES_PT[valor.month]}/"
        f"{str(valor.year)[2:]}"
    )


# ============================================================
# LEITURA DA PLANILHA
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
# LEITURA E CONSOLIDAÇÃO DE MÚLTIPLAS PLANILHAS
# ============================================================

def ler_planilhas_consolidadas(arquivos):

    if not arquivos:
        return None

    bases = []

    for arquivo in arquivos:

        df_arquivo = ler_planilha(
            arquivo
        )

        if df_arquivo is not None and not df_arquivo.empty:

            bases.append(
                df_arquivo
            )

    if not bases:
        return None

    try:

        df_consolidado = pd.concat(
            bases,
            ignore_index=True,
            sort=False,
        )

        return df_consolidado

    except Exception as erro:

        st.error(
            f"Não foi possível consolidar os arquivos: {erro}"
        )

        return None


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

def preparar_dados(df, modulo):

    if df is None or df.empty:

        return None, "A planilha está vazia."

    dados = df.copy()

    # ========================================================
    # DATA DE ABERTURA
    # ========================================================
    # IMPORTANTE:
    # A coluna oficial utilizada é "Início do SLA".
    # O horário será ignorado posteriormente.
    # ========================================================

    coluna_abertura = localizar_coluna(
        dados,
        [
            "Início do SLA",
            "Inicio do SLA",
        ],
    )

    if coluna_abertura is None:

        return (
            None,
            "Não foi encontrada a coluna 'Início do SLA'.",
        )

    # ========================================================
    # PROTOCOLO
    # ========================================================

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

    # ========================================================
    # CONVERTER DATA
    # ========================================================

    dados["_ABERTURA"] = dados[
        coluna_abertura
    ].apply(
        converter_abertura
    )

    # ========================================================
    # PROTOCOLO
    # ========================================================

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

    # ========================================================
    # REMOVER DATAS INVÁLIDAS
    # ========================================================

    dados = dados.dropna(
        subset=["_ABERTURA"]
    ).copy()

    if dados.empty:

        return (
            None,
            "Nenhum registro possui data válida na coluna 'Início do SLA'.",
        )

    # ========================================================
    # DATA — SOMENTE DIA
    # ========================================================

    dados["_DATA"] = dados[
        "_ABERTURA"
    ].dt.normalize()

    dados["_MES_ORDEM"] = (
        dados["_ABERTURA"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    # ========================================================
    # THE / TIM
    # ========================================================

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

    # ========================================================
    # API
    # ========================================================

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


# ============================================================
# TABELA
# ============================================================

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

    tabela = {}

    for local in locais:

        linha = []

        for periodo in periodos:

            bloco = dados[
                (dados["_LOCAL"] == local)
                &
                (
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
# PAINEL
# ============================================================

def gerar_painel(
    df,
    modulo,
    modo,
    base=None,
):

    if df is None or df.empty:

        raise ValueError(
            "Não existem dados para gerar o relatório."
        )

    dados = df.copy()

    # ========================================================
    # FILTRO API
    # ========================================================

    if modulo == "API" and base:

        dados = dados[
            dados["_BASE"] == base
        ].copy()

    if dados.empty:

        raise ValueError(
            "Não existem registros para o filtro selecionado."
        )

    # ========================================================
    # TABELA
    # ========================================================

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

    # ========================================================
    # DIMENSÕES
    # ========================================================

    margem = 60

    # Mantém o relatório vertical.
    largura = 1500

    altura_cabecalho = 260

    altura_linha = 58

    # Ajuste da tabela para aproveitar melhor
    # a largura disponível.
    largura_local = 390

    largura_periodo = 90

    largura_total = 110

    # ========================================================
    # QUANTIDADE DE COLUNAS
    # ========================================================

    # Os períodos são divididos em blocos verticais.
    # Isso evita que muitos dias/meses façam a tabela
    # ultrapassar os limites da imagem.

    periodos_por_bloco = 10

    blocos_periodos = [
        periodos[i:i + periodos_por_bloco]
        for i in range(
            0,
            len(periodos),
            periodos_por_bloco,
        )
    ]

    if not blocos_periodos:
        blocos_periodos = [[]]

    altura_tabela_total = 0

    for bloco in blocos_periodos:

        altura_tabela_total += (
            45
            + altura_linha
            + len(locais) * altura_linha
            + 45
        )

    altura_rodape = 90

    altura = (
        altura_cabecalho
        + altura_tabela_total
        + altura_rodape
    )

    # ========================================================
    # IMAGEM
    # ========================================================

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

    # ========================================================
    # CABEÇALHO
    # ========================================================

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
                "Reclamações de Falta de Água "
                f"• Base: {base}"
            )

        else:

            subtitulo = (
                "Reclamações de Falta de Água "
                "• Todas as bases"
            )

    else:

        subtitulo = (
            "Reclamações de Falta de Água"
        )

    draw.text(
        (
            margem,
            50,
        ),
        titulo,
        font=fonte(
            38,
            True,
        ),
        fill=AZUL_ESCURO,
    )

    draw.text(
        (
            margem,
            108,
        ),
        subtitulo,
        font=fonte(
            21,
        ),
        fill=CINZA,
    )

    # ========================================================
    # INFORMAÇÃO TEMPORAL
    # ========================================================

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
            155,
        ),
        periodo_texto,
        font=fonte(17),
        fill=CINZA,
    )

    draw.text(
        (
            margem,
            190,
        ),
        (
            "Visualização: "
            + modo
            + " • "
            + (
                "Bairros"
                if modulo in ["THE", "TIM"]
                else "Cidades"
            )
        ),
        font=fonte(16),
        fill=CINZA,
    )

    # ========================================================
    # LOGO
    # ========================================================

    desenhar_logo(
        imagem,
        LOGOS[modulo],
        largura - margem - 280,
        45,
        280,
        120,
    )

    # ========================================================
    # ÁREA DAS TABELAS
    # ========================================================

    y_atual = altura_cabecalho

    maximo = int(
        tabela[
            periodos
        ].max().max()
    ) if periodos else 0

    for numero_bloco, bloco in enumerate(
        blocos_periodos
    ):

        # ----------------------------------------------------
        # TÍTULO DO BLOCO
        # ----------------------------------------------------

        if modo == "Por dia":

            titulo_bloco = (
                "VOLUME POR "
                + (
                    "BAIRRO"
                    if modulo in ["THE", "TIM"]
                    else "CIDADE"
                )
                + " — "
                + (
                    f"{bloco[0].strftime('%d/%m')}"
                    if len(bloco) == 1
                    else
                    f"{bloco[0].strftime('%d/%m')} "
                    f"a "
                    f"{bloco[-1].strftime('%d/%m')}"
                )
            )

        else:

            titulo_bloco = (
                "VOLUME POR "
                + (
                    "BAIRRO"
                    if modulo in ["THE", "TIM"]
                    else "CIDADE"
                )
                + " — "
                + (
                    texto_cabecalho_periodo(
                        bloco[0],
                        modo,
                    )
                    if len(bloco) == 1
                    else
                    f"{texto_cabecalho_periodo(bloco[0], modo)} "
                    f"a "
                    f"{texto_cabecalho_periodo(bloco[-1], modo)}"
                )
            )

        draw.text(
            (
                margem,
                y_atual,
            ),
            titulo_bloco,
            font=fonte(
                24,
                True,
            ),
            fill=AZUL_ESCURO,
        )

        y_inicio = (
            y_atual + 45
        )

        # ----------------------------------------------------
        # LARGURA DO BLOCO
        # ----------------------------------------------------

        largura_tabela = (
            largura_local
            + len(bloco)
            * largura_periodo
            + largura_total
        )

        x_inicio = margem

        # ----------------------------------------------------
        # CABEÇALHO
        # ----------------------------------------------------

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

        nome_local = (
            "BAIRRO"
            if modulo in ["THE", "TIM"]
            else "CIDADE"
        )

        draw.text(
            (
                x_inicio + 18,
                y_inicio + 17,
            ),
            nome_local,
            font=fonte(
                17,
                True,
            ),
            fill=BRANCO,
        )

        for indice, periodo in enumerate(
            bloco
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
                    14,
                    True,
                ),
                BRANCO,
            )

        x_total = (
            x_inicio
            + largura_local
            + len(bloco)
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
                15,
                True,
            ),
            BRANCO,
        )

        # ----------------------------------------------------
        # LINHAS
        # ----------------------------------------------------

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

            # -----------------------------------------------
            # LOCAL
            # -----------------------------------------------

            texto_local = abreviar_texto(
                local,
                38,
            )

            draw.text(
                (
                    x_inicio + 18,
                    y + 17,
                ),
                texto_local,
                font=fonte(
                    15,
                    True,
                ),
                fill=AZUL_ESCURO,
            )

            # -----------------------------------------------
            # PERÍODOS
            # -----------------------------------------------

            for indice, periodo in enumerate(
                bloco
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
                        x
                        + largura_periodo
                        - 2,
                        y
                        + altura_linha
                        - 2,
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
                        14,
                        True,
                    ),
                    cor_texto_celula(
                        valor,
                        maximo,
                    ),
                )

            # -----------------------------------------------
            # TOTAL DO LOCAL
            # -----------------------------------------------

            total_local = int(
                tabela.loc[
                    local,
                    periodos,
                ].sum()
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
                    15,
                    True,
                ),
                AZUL_ESCURO,
            )

        # ----------------------------------------------------
        # SEPARAÇÃO ENTRE BLOCOS
        # ----------------------------------------------------

        y_atual = (
            y_inicio
            + altura_linha
            + len(locais)
            * altura_linha
            + 45
        )

    # ========================================================
    # RODAPÉ
    # ========================================================

    y_rodape = (
        altura
        - altura_rodape
        + 20
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
        font=fonte(
            15,
        ),
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
        font=fonte(
            14,
        ),
        fill=CINZA,
    )

    # ========================================================
    # PNG
    # ========================================================

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
    "Relatório de Falta de Água - COI"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="module-subtitle">'
    "Geração de relatório consolidado de reclamações de Falta de Água."
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

    arquivos_api = st.file_uploader(
        "Planilha(s) API",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_api",
    )


with col_the:

    st.markdown("### THE")

    arquivos_the = st.file_uploader(
        "Planilha(s) THE",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_the",
    )


with col_tim:

    st.markdown("### TIM")

    arquivos_tim = st.file_uploader(
        "Planilha(s) TIM",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_tim",
    )


st.divider()


# ============================================================
# CONFIGURAÇÃO
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
# ARQUIVOS
# ============================================================

arquivos = {
    "API": arquivos_api,
    "THE": arquivos_the,
    "TIM": arquivos_tim,
}

arquivos_selecionados = arquivos[
    modulo
]


# ============================================================
# LEITURA E CONSOLIDAÇÃO DOS ARQUIVOS
# ============================================================

if not arquivos_selecionados:

    st.info(
        f"Carregue uma ou mais planilhas de {modulo} "
        "para gerar o relatório."
    )

    st.stop()


with st.spinner(
    f"Consolidando os dados de {modulo}..."
):

    df_original = ler_planilhas_consolidadas(
        arquivos_selecionados
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
# API — BASE
# ============================================================

base_selecionada = None

if modulo == "API":

    st.markdown(
        "#### Base operacional"
    )

    bases_disponiveis = sorted(
        [
            b
            for b in df["_BASE"]
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
# BOTÃO
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
            f"RELATORIO_FA_"
            f"{modulo_final}_"
            f"{normalizar(base_final).replace(' ', '_')}_"
            f"{modo_final.replace(' ', '_')}.png"
        )

    else:

        nome_arquivo = (
            f"RELATORIO_FA_"
            f"{modulo_final}_"
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
