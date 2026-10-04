import streamlit as st
import io
import re
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter


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
    'ACAUA': 'PAULISTANA',
    'AGRICOLANDIA': 'MEIO NORTE',
    'AGUA BRANCA': 'MEIO NORTE',
    'ALAGOINHA': 'PICOS',
    'ALAGOINHA DO PIAUI': 'PICOS',
    'ALEGRETE DO PIAUI': 'PICOS',
    'ALTO LONGA': 'MEIO NORTE',
    'ALTOS': 'MEIO NORTE',
    'ALVORADA DO GURGUEIA': 'FLORIANO',
    'AMARANTE': 'FLORIANO',
    'ANGICAL DO PIAUI': 'MEIO NORTE',
    'ANISIO DE ABREU': 'SAO RAIMUNDO NONATO',
    'AROAZES': 'MEIO NORTE',
    'AROEIRAS DO ITAIM': 'PICOS',
    'ARRAIAL': 'FLORIANO',
    'ASSUNCAO DO PIAUI': 'MEIO NORTE',
    'AVELINO LOPES': 'BOM JESUS',
    'BAIXA GRANDE DO RIBEIRO': 'FLORIANO',
    'BARRA D ALCANTARA': 'OEIRAS',
    'BARRAS': 'PIRIPIRI',
    'BARREIRAS DO PIAUI': 'BOM JESUS',
    'BARRO DURO': 'MEIO NORTE',
    'BATALHA': 'PIRIPIRI',
    'BELA VISTA DO PIAUI': 'SAO JOAO DO PIAUI',
    'BELEM DO PIAUI': 'PICOS',
    'BENEDITINOS': 'MEIO NORTE',
    'BERTOLINIA': 'FLORIANO',
    'BOA HORA': 'PIRIPIRI',
    'BOCAINA': 'PICOS',
    'BOM JESUS': 'BOM JESUS',
    'BOM PRINCIPIO DO PIAUI': 'PARNAIBA',
    'BONFIM DO PIAUI': 'SAO RAIMUNDO NONATO',
    'BOQUEIRAO DO PIAUI': 'PIRIPIRI',
    'BRASILEIRA': 'PIRIPIRI',
    'BREJO DO PIAUI': 'SAO JOAO DO PIAUI',
    'BURITI DOS LOPES': 'PARNAIBA',
    'BURITI DOS MONTES': 'MEIO NORTE',
    'CABECEIRAS  DO PIAUI': 'PIRIPIRI',
    'CAJAZEIRAS DO PIAUI': 'OEIRAS',
    'CAJUEIRO DA PRAIA': 'PARNAIBA',
    'CAMPINAS DO PIAUI': 'SAO JOAO DO PIAUI',
    'CAMPO ALEGRE DO FIDALGO': 'SAO JOAO DO PIAUI',
    'CAMPO GRANDE DO PIAUI': 'PICOS',
    'CAMPO LARGO DO PIAUI': 'PIRIPIRI',
    'CANAVIEIRA': 'FLORIANO',
    'CANTO DO BURITI': 'SAO JOAO DO PIAUI',
    'CAPITAO DE CAMPOS': 'PIRIPIRI',
    'CAPITAO GERVASIO OLIVEIRA': 'SAO JOAO DO PIAUI',
    'CARACOL': 'SAO RAIMUNDO NONATO',
    'CARAUBAS DO PIAUI': 'PARNAIBA',
    'CARIDADE': 'PAULISTANA',
    'CARIDADE DO PIAUI': 'PAULISTANA',
    'CASTELO DO PIAUI': 'MEIO NORTE',
    'COCAL': 'PARNAIBA',
    'COCAL DE TELHA': 'PIRIPIRI',
    'COCAL DOS ALVES': 'PARNAIBA',
    'COIVARAS': 'MEIO NORTE',
    'COLONIA DO GURGUEIA': 'BOM JESUS',
    'COLONIA DO PIAUI': 'OEIRAS',
    'CONCEICAO DO CANINDE': 'SAO JOAO DO PIAUI',
    'CORONEL JOSE DIAS': 'SAO RAIMUNDO NONATO',
    'CORRENTE': 'BOM JESUS',
    'CRISTALANDIA': 'BOM JESUS',
    'CRISTINO CASTRO': 'BOM JESUS',
    'CURIMATA': 'BOM JESUS',
    'CURRAIS': 'BOM JESUS',
    'CURRAL NOVO PI': 'PAULISTANA',
    'CURRALINHOS': 'MEIO NORTE',
    'DEMERVAL LOBAO': 'MEIO NORTE',
    'DIRCEU ARCOVERDE': 'SAO RAIMUNDO NONATO',
    'DOM EXPEDITO LOPES': 'PICOS',
    'DOM INOCENCIO': 'SAO RAIMUNDO NONATO',
    'DOMINGOS MOURAO': 'PIRIPIRI',
    'ELESBAO VELOSO': 'MEIO NORTE',
    'ELIZEU MARTINS': 'BOM JESUS',
    'ESPERANTINA': 'PIRIPIRI',
    'FARTURA DO PIAUI': 'SAO RAIMUNDO NONATO',
    'FLORES DO PIAUI': 'FLORIANO',
    'FLORESTA DO PIAUI': 'OEIRAS',
    'FLORIANO': 'FLORIANO',
    'FRANCINOPOLIS': 'OEIRAS',
    'FRANCISCO AYRES': 'FLORIANO',
    'FRANCISCO AIRES': 'FLORIANO',
    'FRANCISCO MACEDO': 'PICOS',
    'FRANCISCO SANTOS': 'PICOS',
    'FRONTEIRAS': 'PICOS',
    'GEMINIANO': 'PICOS',
    'GILBUES': 'BOM JESUS',
    'GUADALUPE': 'FLORIANO',
    'GUARIBAS': 'SAO RAIMUNDO NONATO',
    'HUGO NAPOLEAO': 'MEIO NORTE',
    'ILHA GRANDE': 'PARNAIBA',
    'INHUMA': 'OEIRAS',
    'IPIRANGA': 'OEIRAS',
    'ISAIAS COELHO': 'PAULISTANA',
    'ITAINOPOLIS': 'PICOS',
    'ITAUEIRA': 'FLORIANO',
    'JACOBINA DO PIAUI': 'PAULISTANA',
    'JAICOS': 'PICOS',
    'JARDIM MULATO': 'MEIO NORTE',
    'JATOBA DO PIAUI': 'MEIO NORTE',
    'JERUMENHA': 'FLORIANO',
    'JOAO COSTA': 'SAO RAIMUNDO NONATO',
    'JOAQUIM PIRES': 'PARNAIBA',
    'JOCA MARQUES': 'PARNAIBA',
    'JOSE DE FREITAS': 'MEIO NORTE',
    'JUAZEIRO DO PIAUI': 'MEIO NORTE',
    'JULIO BORGES': 'BOM JESUS',
    'JUREMA': 'SAO RAIMUNDO NONATO',
    'LAGOA ALEGRE': 'PIRIPIRI',
    'LAGOA DE SAO FRANCISCO': 'PIRIPIRI',
    'LAGOA DO BARRO DO PIAUI': 'SAO JOAO DO PIAUI',
    'LAGOA DO PIAUI': 'MEIO NORTE',
    'LAGOA DO SITIO': 'OEIRAS',
    'LAGOINHA DO PIAUI': 'MEIO NORTE',
    'LUIS CORREIA': 'PARNAIBA',
    'LUZILANDIA': 'PIRIPIRI',
    'MADEIRO': 'PIRIPIRI',
    'MANOEL EMIDIO': 'BOM JESUS',
    'MARCOS PARENTE': 'FLORIANO',
    'MASSAPE DO PIAUI': 'PAULISTANA',
    'MATIAS OLIMPIO': 'PARNAIBA',
    'MIGUEL ALVES': 'PIRIPIRI',
    'MIGUEL LEAO': 'MEIO NORTE',
    'MILTON BRANDAO': 'PIRIPIRI',
    'MONSENHOR GIL': 'MEIO NORTE',
    'MONSENHOR HIPOLITO': 'PICOS',
    'MONTE ALEGRE': 'BOM JESUS',
    'MORRO CABECA NO TEMPO': 'BOM JESUS',
    'MORRO DO CHAPEU DO PIAUI': 'SAO RAIMUNDO NONATO',
    'MURICI DOS PORTELAS': 'PARNAIBA',
    'NAZARE DO PIAUI': 'FLORIANO',
    'NAZARIA': 'MEIO NORTE',
    'NOSSA SENHORA DE NAZARE': 'MEIO NORTE',
    'NOSSA SRA DOS REMEDIOS': 'PARNAIBA',
    'NOVA SANTA RITA': 'SAO JOAO DO PIAUI',
    'NOVO ORIENTE DO PIAU': 'OEIRAS',
    'NOVO SANTO ANTONIO': 'MEIO NORTE',
    'OEIRAS': 'OEIRAS',
    "OLHO D'AGUA DO PIAUI": 'MEIO NORTE',
    'PADRE MARCOS': 'PICOS',
    'PAES LANDIM': 'SAO JOAO DO PIAUI',
    'PAJEU DO PIAUI': 'FLORIANO',
    'PALMEIRA DO PIAUI': 'BOM JESUS',
    'PALMEIRAIS': 'MEIO NORTE',
    'PAQUETA': 'PICOS',
    'PARNAGUA': 'BOM JESUS',
    'PARNAIBA': 'PARNAIBA',
    'PASSAGEM FRANCA': 'MEIO NORTE',
    'PATOS DO PIAUI': 'PAULISTANA',
    'PAU D ARCO DO PIAUI': 'MEIO NORTE',
    'PAULISTANA': 'PAULISTANA',
    'PAVUSSU': 'FLORIANO',
    'PEDRO II': 'PIRIPIRI',
    'PICOS': 'PICOS',
    'PIMENTEIRAS': 'OEIRAS',
    'PIO IX': 'PICOS',
    'PIRACURUCA': 'PARNAIBA',
    'PIRIPIRI': 'PIRIPIRI',
    'PORTO': 'PIRIPIRI',
    'PORTO ALEGRE DO PIAUI': 'FLORIANO',
    'PRATA DO PIAUI': 'MEIO NORTE',
    'QUEIMADA NOVA': 'SAO JOAO DO PIAUI',
    'REDENCAO DO GURGUEIA': 'BOM JESUS',
    'REGENERACAO': 'FLORIANO',
    'RIACHO FRIO': 'BOM JESUS',
    'RIBEIRA DO PIAUI': 'FLORIANO',
    'RIBEIRO GONCALVES': 'FLORIANO',
    'RIO GRANDE DO PIAUI': 'FLORIANO',
    'SANTA CRUZ DO PIAUI': 'OEIRAS',
    'SANTA CRUZ DOS MILAGRES': 'MEIO NORTE',
    'SANTA FILOMENA': 'BOM JESUS',
    'SANTA LUZ': 'BOM JESUS',
    'SANTA ROSA DO PIAUI': 'OEIRAS',
    'SANTA TERESA': 'MEIO NORTE',
    'SANTANA DO PIAUI': 'PICOS',
    'SANTO ANTONIO DE LISBOA': 'PICOS',
    'SANTO ANTONIO D MILA': 'MEIO NORTE',
    'SANTO INACIO DO PIAUI': 'SAO JOAO DO PIAUI',
    'SAO BRAZ': 'SAO RAIMUNDO NONATO',
    'SAO FELIX': 'MEIO NORTE',
    'SAO FRANCISCO DE ASSIS': 'SAO JOAO DO PIAUI',
    'SAO FRANCISCO DO PIAUI': 'OEIRAS',
    'SAO GONCALO DO GURGUEIA': 'BOM JESUS',
    'SAO GONCALO DO PIAUI': 'MEIO NORTE',
    'SAO JOAO DA CANABRAVA': 'PICOS',
    'SAO JOAO DA FRONTEIRA': 'PIRIPIRI',
    'SAO JOAO DA SERRA': 'MEIO NORTE',
    'SAO JOAO DA VARJOTA': 'OEIRAS',
    'SAO JOAO DO ARRAIAL': 'PIRIPIRI',
    'SAO JOAO DO PIAUI': 'SAO JOAO DO PIAUI',
    'SAO JOSE DO DIVINO': 'PARNAIBA',
    'SAO JOSE DO PEIXE': 'SAO JOAO DO PIAUI',
    'SAO JOSE DO PIAUI': 'OEIRAS',
    'SAO JOSE DA TENDA': 'SAO RAIMUNDO NONATO',
    'SAO JULIAO': 'PICOS',
    'SAO LOURENCO': 'SAO RAIMUNDO NONATO',
    'SAO LUIS DO PIAUI': 'PICOS',
    'SAO MIGUEL DA BAIXA GRANDE': 'MEIO NORTE',
    'SAO MIGUEL DO FIDALGO': 'SAO JOAO DO PIAUI',
    'SAO MIGUEL TAPUIO': 'MEIO NORTE',
    'SAO PEDRO': 'MEIO NORTE',
    'SAO RAIMUNDO NONATO': 'SAO RAIMUNDO NONATO',
    'SEBASTIAO BARROS': 'BOM JESUS',
    'SEBASTIAO LEAL': 'FLORIANO',
    'SIGEFREDO PACHECO': 'MEIO NORTE',
    'SIMOES': 'PAULISTANA',
    'SIMPLICIO MENDES': 'SAO JOAO DO PIAUI',
    'SOCORRO DO PIAUI': 'SAO JOAO DO PIAUI',
    'SUSSUAPARA': 'PICOS',
    'TAMBORIL DO PIAUI': 'SAO RAIMUNDO NONATO',
    'TANQUE DO PIAUI': 'OEIRAS',
    'TERESINA': 'MEIO NORTE',
    'UNIAO': 'MEIO NORTE',
    'URUCUI': 'FLORIANO',
    'VALENCA': 'OEIRAS',
    'VARZEA BRANCA': 'SAO RAIMUNDO NONATO',
    'VARZEA GRANDE': 'OEIRAS',
    'VERA MENDES': 'PAULISTANA',
    'VILA NOVA DO PIAUI': 'PICOS',
    'WALL FERRAZ': 'OEIRAS',
    'POV SANTA TERESA': 'MEIO NORTE',
    'POV CALDEIRAOZINHO': 'SAO RAIMUNDO NONATO',
    'POVOADO BURITIZINHO': 'MEIO NORTE',
    'POV COROA DE SAO REMIGIO': 'PARNAIBA',
    'POVOADO PEDRA': 'MEIO NORTE',
    'POVOADO APARECIDA': 'PICOS',
    'POV BARRA DO LONGA': 'PARNAIBA',
    'POV INGAZEIRA': 'PAULISTANA',
    'POV SERRA DA SOLTA': 'MEIO NORTE',
    'POVOADO BARRA GRANDE': 'PARNAIBA',
    'POVOADO SAO JOAQUIM': 'MEIO NORTE',
    'POVOADO TRANQUEIRA': 'MEIO NORTE',
    'POV MOCAMBINHO': 'PARNAIBA',
    'POV BURITI DO CASTELO': 'MEIO NORTE',
    'POVOADO MANDACARU': 'PICOS',
    'POVOADO MATINHA': 'MEIO NORTE',
    'POV DAVID CALDAS': 'MEIO NORTE',
    'POV. LAGOA DE BAIXO': 'SAO RAIMUNDO NONATO',
    'POVOADO RIACHO DOS NEGRO': 'MEIO NORTE',
    'POVOADO POCAO': 'PARNAIBA',
    'OLHO D AGUA DO PIAUI': 'MEIO NORTE',
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

            return ImageFont.truetype(
                nome,
                tamanho,
            )

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

        texto = texto.replace(
            antigo,
            novo,
        )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

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

    if not cidade_n:
        return ""

    for chave, base in BASE_POR_CIDADE.items():

        if normalizar_cidade(chave) == cidade_n:
            return base

    return ""


def cidades_da_base(base=None):
    """Retorna cidades do cadastro oficial; sem base, retorna todas."""

    base_n = normalizar(base) if base else ""

    cidades = []

    for cidade, base_cidade in BASE_POR_CIDADE.items():
        if not base_n or normalizar(base_cidade) == base_n:
            cidades.append(cidade)

    # Remove duplicidades após normalização e mantém ordem alfabética.
    unicas = {}
    for cidade in cidades:
        unicas.setdefault(normalizar(cidade), cidade)

    return sorted(unicas.values(), key=normalizar)


def localizar_coluna(df, candidatos):

    mapa = {}

    for coluna in df.columns:

        chave = normalizar(coluna)

        chave = re.sub(
            r"[^A-Z0-9]",
            "",
            chave,
        )

        mapa[chave] = coluna

    for candidato in candidatos:

        chave = normalizar(candidato)

        chave = re.sub(
            r"[^A-Z0-9]",
            "",
            chave,
        )

        if chave in mapa:
            return mapa[chave]

    for coluna in df.columns:

        coluna_n = normalizar(coluna)

        coluna_n = re.sub(
            r"[^A-Z0-9]",
            "",
            coluna_n,
        )

        for candidato in candidatos:

            candidato_n = normalizar(candidato)

            candidato_n = re.sub(
                r"[^A-Z0-9]",
                "",
                candidato_n,
            )

            if (
                candidato_n
                and candidato_n in coluna_n
            ):
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

    try:

        resultado = pd.to_datetime(
            texto,
            format="%d/%m/%Y %H:%M",
            errors="raise",
        )

        return resultado

    except Exception:
        pass

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

        return f"{int(numero):,}".replace(
            ",",
            ".",
        )

    except Exception:

        return "0"


def abreviar_texto(texto, limite):

    texto = str(texto)

    if len(texto) <= limite:
        return texto

    return texto[: limite - 3] + "..."


def texto_cabecalho_periodo(valor, modo):

    if modo == "Por dia":

        return valor.strftime(
            "%d/%m"
        )

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
# LEITURA E CONSOLIDAÇÃO
# ============================================================

def ler_planilhas_consolidadas(arquivos):

    if not arquivos:
        return None

    bases = []

    for arquivo in arquivos:

        df_arquivo = ler_planilha(
            arquivo
        )

        if (
            df_arquivo is not None
            and not df_arquivo.empty
        ):

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

        return (
            None,
            "A planilha está vazia.",
        )

    dados = df.copy()

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

    dados["_ABERTURA"] = dados[
        coluna_abertura
    ].apply(
        converter_abertura
    )

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

    dados = dados.dropna(
        subset=["_ABERTURA"]
    ).copy()

    if dados.empty:

        return (
            None,
            "Nenhum registro possui data válida na coluna 'Início do SLA'.",
        )

    # ========================================================
    # DATA REAL DA ABERTURA
    # ========================================================

    dados["_DATA"] = (
        dados["_ABERTURA"]
        .dt.normalize()
    )

    # ========================================================
    # MÊS DE REFERÊNCIA
    # ========================================================

    dados["_MES_ORDEM"] = (
        dados["_ABERTURA"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    # ========================================================
    # LOCAL
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

        dados["_LOCAL"] = (
            dados["_LOCAL"].replace(
                {
                    "": "NÃO INFORMADO",
                    "nan": "NÃO INFORMADO",
                    "NaN": "NÃO INFORMADO",
                }
            )
        )

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

        dados["_LOCAL"] = (
            dados["_LOCAL"].replace(
                {
                    "": "NÃO INFORMADA",
                    "nan": "NÃO INFORMADA",
                    "NaN": "NÃO INFORMADA",
                }
            )
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

    if series is None or series.empty:
        return 0

    protocolos = series[
        "_PROTOCOLO"
    ]

    validos = protocolos.dropna()

    if not validos.empty:

        return validos.nunique()

    return len(series)


# ============================================================
# PLANILHA API — MODELO INTERATIVO
# ============================================================

def _cabecalhos_unicos(colunas):
    """Garante cabeçalhos únicos e compatíveis com Tabelas do Excel."""

    usados = set()
    resultado = []

    for coluna in colunas:
        base = str(coluna).strip() or "COLUNA"
        nome = base
        contador = 2

        while nome in usados:
            nome = f"{base}_{contador}"
            contador += 1

        usados.add(nome)
        resultado.append(nome)

    return resultado


def gerar_planilha_api(
    df,
    base_inicial=None,
    modo="Por dia",
):
    """
    Gera um XLSX para o modo API com:
      - DADOS: tabela estruturada com os registros consolidados;
      - BASES_CIDADES: cadastro oficial Base x Cidade;
      - PAINEL_API: tabela dinâmica simulada por fórmulas, com
        segmentação por Base através de lista suspensa.

    A solução evita imagem estática. A planilha continua editável no Excel
    e a troca da Base atualiza a visão do painel.
    """

    if df is None or df.empty:
        raise ValueError("Não existem dados para gerar a planilha API.")

    dados = df.copy()

    if "_BASE" not in dados.columns or "_LOCAL" not in dados.columns:
        raise ValueError("Os dados API não possuem Base/Cidade preparados.")

    # ------------------------------------------------------------
    # CONTAGENS ÚNICAS — mesma regra do relatório atual
    # ------------------------------------------------------------
    dados["_DATA"] = pd.to_datetime(dados["_DATA"], errors="coerce").dt.normalize()
    dados["_MES_ORDEM"] = pd.to_datetime(dados["_MES_ORDEM"], errors="coerce").dt.to_period("M").dt.to_timestamp()

    chave_dia = pd.DataFrame({
        "base": dados["_BASE"].fillna("").astype(str),
        "cidade": dados["_LOCAL"].fillna("").astype(str),
        "data": dados["_DATA"],
        "protocolo": dados["_PROTOCOLO"],
    })
    chave_dia["tem_protocolo"] = chave_dia["protocolo"].notna()

    cont_dia = pd.Series(1, index=dados.index, dtype="int64")
    mask_proto = chave_dia["tem_protocolo"]
    cont_dia.loc[mask_proto] = ~chave_dia.loc[mask_proto].duplicated(
        subset=["base", "cidade", "data", "protocolo"],
        keep="first",
    )
    dados["_CONTAGEM_DIA"] = cont_dia.astype(int)

    chave_mes = pd.DataFrame({
        "base": dados["_BASE"].fillna("").astype(str),
        "cidade": dados["_LOCAL"].fillna("").astype(str),
        "mes": dados["_MES_ORDEM"],
        "protocolo": dados["_PROTOCOLO"],
    })
    chave_mes["tem_protocolo"] = chave_mes["protocolo"].notna()

    cont_mes = pd.Series(1, index=dados.index, dtype="int64")
    mask_proto_mes = chave_mes["tem_protocolo"]
    cont_mes.loc[mask_proto_mes] = ~chave_mes.loc[mask_proto_mes].duplicated(
        subset=["base", "cidade", "mes", "protocolo"],
        keep="first",
    )
    dados["_CONTAGEM_MES"] = cont_mes.astype(int)

    # ------------------------------------------------------------
    # EXCEL
    # ------------------------------------------------------------
    wb = Workbook()
    ws_painel = wb.active
    ws_painel.title = "PAINEL_API"
    ws_dados = wb.create_sheet("DADOS")
    ws_mapa = wb.create_sheet("BASES_CIDADES")

    # ------------------------------------------------------------
    # DADOS
    # ------------------------------------------------------------
    colunas_originais = [
        c for c in dados.columns
        if not str(c).startswith("_")
    ]

    colunas_saida = colunas_originais + [
        "COI_Data_Abertura",
        "COI_Data",
        "COI_Mes",
        "COI_Cidade",
        "COI_Base",
        "COI_Protocolo",
        "COI_Contagem_Dia",
        "COI_Contagem_Mes",
    ]
    colunas_saida = _cabecalhos_unicos(colunas_saida)

    ws_dados.append(colunas_saida)

    mapa_coluna_saida = dict(zip(
        [str(c) for c in colunas_originais],
        colunas_saida[:len(colunas_originais)],
    ))

    for idx in dados.index:
        linha = []

        for coluna in colunas_originais:
            valor = dados.at[idx, coluna]
            if pd.isna(valor):
                valor = None
            elif isinstance(valor, pd.Timestamp):
                valor = valor.to_pydatetime()
            linha.append(valor)

        linha.extend([
            dados.at[idx, "_ABERTURA"].to_pydatetime() if pd.notna(dados.at[idx, "_ABERTURA"]) else None,
            dados.at[idx, "_DATA"].to_pydatetime() if pd.notna(dados.at[idx, "_DATA"]) else None,
            dados.at[idx, "_MES_ORDEM"].to_pydatetime() if pd.notna(dados.at[idx, "_MES_ORDEM"]) else None,
            normalizar_cidade(dados.at[idx, "_LOCAL"]) if pd.notna(dados.at[idx, "_LOCAL"]) else "",
            str(dados.at[idx, "_BASE"]) if pd.notna(dados.at[idx, "_BASE"]) else "",
            str(dados.at[idx, "_PROTOCOLO"]) if pd.notna(dados.at[idx, "_PROTOCOLO"]) else "",
            int(dados.at[idx, "_CONTAGEM_DIA"]),
            int(dados.at[idx, "_CONTAGEM_MES"]),
        ])

        ws_dados.append(linha)

    header_fill = PatternFill("solid", fgColor="123B5D")
    header_font = Font(color="FFFFFF", bold=True)
    thin_gray = Side(style="thin", color="D9E2EC")

    for cell in ws_dados[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws_dados.freeze_panes = "A2"
    ws_dados.auto_filter.ref = ws_dados.dimensions

    # Formatação de datas
    nomes_data = {"COI_Data_Abertura", "COI_Data", "COI_Mes"}
    for cell in ws_dados[1]:
        if cell.value in nomes_data:
            col_idx = cell.column
            for row in range(2, ws_dados.max_row + 1):
                ws_dados.cell(row, col_idx).number_format = "dd/mm/yyyy"

    ref_dados = f"A1:{get_column_letter(ws_dados.max_column)}{ws_dados.max_row}"
    tabela_dados = Table(displayName="TabelaDadosAPI", ref=ref_dados)
    tabela_dados.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws_dados.add_table(tabela_dados)

    # Larguras razoáveis sem alterar a estrutura dos dados.
    for col_idx, cell in enumerate(ws_dados[1], start=1):
        valores = [str(ws_dados.cell(r, col_idx).value or "") for r in range(1, min(ws_dados.max_row, 150) + 1)]
        largura = min(max(max((len(v) for v in valores), default=10) + 2, 10), 38)
        ws_dados.column_dimensions[get_column_letter(col_idx)].width = largura

    # ------------------------------------------------------------
    # BASES_CIDADES
    # ------------------------------------------------------------
    ws_mapa.append(["BASE", "CIDADE"])
    for cell in ws_mapa[1]:
        cell.fill = header_fill
        cell.font = header_font

    pares = []
    for cidade, base in BASE_POR_CIDADE.items():
        pares.append((str(base), str(cidade)))
    pares.sort(key=lambda x: (normalizar(x[0]), normalizar(x[1])))

    for base, cidade in pares:
        ws_mapa.append([base, cidade])

    ws_mapa.freeze_panes = "A2"
    ref_mapa = f"A1:B{ws_mapa.max_row}"
    tabela_mapa = Table(displayName="TabelaBasesCidades", ref=ref_mapa)
    tabela_mapa.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws_mapa.add_table(tabela_mapa)
    ws_mapa.column_dimensions["A"].width = 28
    ws_mapa.column_dimensions["B"].width = 34

    # ------------------------------------------------------------
    # LISTA DE BASES PARA A SEGMENTAÇÃO
    # ------------------------------------------------------------
    ws_aux = wb.create_sheet("LISTAS")
    ws_aux.sheet_state = "hidden"
    bases = sorted(set(BASE_POR_CIDADE.values()), key=normalizar)
    ws_aux["A1"] = "Todas"
    for i, base in enumerate(bases, start=2):
        ws_aux.cell(i, 1, base)

    # ------------------------------------------------------------
    # PAINEL API
    # ------------------------------------------------------------
    ws_painel.sheet_view.showGridLines = False
    ws_painel["A1"] = "RELATÓRIO DE FALTA DE ÁGUA — API"
    ws_painel["A1"].font = Font(size=18, bold=True, color="123B5D")
    ws_painel.merge_cells("A1:H1")

    ws_painel["A3"] = "SEGMENTAÇÃO — BASE"
    ws_painel["A3"].font = Font(bold=True, color="123B5D")
    ws_painel["B3"] = base_inicial if base_inicial else "Todas"
    ws_painel["B3"].font = Font(bold=True)
    ws_painel["B3"].fill = PatternFill("solid", fgColor="EAF2F8")
    ws_painel["B3"].border = Border(bottom=Side(style="thin", color="123B5D"))

    dv_base = DataValidation(
        type="list",
        formula1=f"=LISTAS!$A$1:$A${len(bases) + 1}",
        allow_blank=False,
    )
    dv_base.error = "Selecione uma base válida."
    dv_base.errorTitle = "Base inválida"
    dv_base.prompt = "Escolha a base para atualizar o painel."
    dv_base.promptTitle = "Segmentação por Base"
    ws_painel.add_data_validation(dv_base)
    dv_base.add(ws_painel["B3"])

    ws_painel["D3"] = "MODO"
    ws_painel["D3"].font = Font(bold=True, color="123B5D")
    ws_painel["E3"] = modo
    ws_painel["E3"].font = Font(bold=True)

    ws_painel["A5"] = "Cidade"
    ws_painel["A5"].fill = header_fill
    ws_painel["A5"].font = header_font
    ws_painel["A5"].alignment = Alignment(horizontal="center")

    periodos = sorted(dados["_DATA"].dropna().unique()) if modo == "Por dia" else sorted(dados["_MES_ORDEM"].dropna().unique())
    if not periodos:
        raise ValueError("Não foram encontradas datas válidas para o painel API.")

    for j, periodo in enumerate(periodos, start=2):
        cell = ws_painel.cell(5, j)
        cell.value = pd.Timestamp(periodo).to_pydatetime()
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.number_format = "dd/mm/yyyy" if modo == "Por dia" else "mm/yyyy"

    col_total = 2 + len(periodos)
    ws_painel.cell(5, col_total, "Total")
    ws_painel.cell(5, col_total).fill = header_fill
    ws_painel.cell(5, col_total).font = header_font
    ws_painel.cell(5, col_total).alignment = Alignment(horizontal="center")

    # Todas as 242 cidades do cadastro aparecem; a fórmula decide quais
    # pertencem à Base selecionada e retorna 0 para cidades sem O.S.
    cidades = cidades_da_base(None)
    primeira_linha = 6

    for i, cidade in enumerate(cidades, start=primeira_linha):
        ws_painel.cell(i, 1, cidade)

        for j, periodo in enumerate(periodos, start=2):
            letra = get_column_letter(j)
            data_ref = f"{letra}$5"

            if modo == "Por dia":
                formula = (
                    f'=IF(COUNTIFS(TabelaBasesCidades[BASE],$B$3,'
                    f'TabelaBasesCidades[CIDADE],$A{i})=0,"",'
                    f'SUMIFS(TabelaDadosAPI[COI_Contagem_Dia],TabelaDadosAPI[COI_Base],$B$3,'
                    f'TabelaDadosAPI[COI_Cidade],$A{i},TabelaDadosAPI[COI_Data],{data_ref}))'
                )
            else:
                formula = (
                    f'=IF(COUNTIFS(TabelaBasesCidades[BASE],$B$3,'
                    f'TabelaBasesCidades[CIDADE],$A{i})=0,"",'
                    f'SUMIFS(TabelaDadosAPI[COI_Contagem_Mes],TabelaDadosAPI[COI_Base],$B$3,'
                    f'TabelaDadosAPI[COI_Cidade],$A{i},TabelaDadosAPI[COI_Mes],{data_ref}))'
                )

            ws_painel.cell(i, j, formula)
            ws_painel.cell(i, j).alignment = Alignment(horizontal="center")

        faixa = f"B{i}:{get_column_letter(col_total - 1)}{i}"
        ws_painel.cell(i, col_total, f'=IF(COUNT({faixa})=0,"",SUM({faixa}))')
        ws_painel.cell(i, col_total).alignment = Alignment(horizontal="center")

    ultima_linha = primeira_linha + len(cidades) - 1
    linha_total = ultima_linha + 1
    ws_painel.cell(linha_total, 1, "TOTAL")
    ws_painel.cell(linha_total, 1).font = Font(bold=True)

    for j in range(2, col_total + 1):
        letra = get_column_letter(j)
        ws_painel.cell(
            linha_total,
            j,
            f'=IF(COUNT({letra}{primeira_linha}:{letra}{ultima_linha})=0,"",SUM({letra}{primeira_linha}:{letra}{ultima_linha}))',
        )
        ws_painel.cell(linha_total, j).font = Font(bold=True)
        ws_painel.cell(linha_total, j).alignment = Alignment(horizontal="center")

    # Estilo do painel
    for row in ws_painel.iter_rows(min_row=5, max_row=linha_total, min_col=1, max_col=col_total):
        for cell in row:
            cell.border = Border(bottom=thin_gray)
            cell.alignment = Alignment(
                horizontal="center" if cell.column > 1 else "left",
                vertical="center",
            )

    for cell in ws_painel[linha_total]:
        cell.fill = PatternFill("solid", fgColor="EAF2F8")

    ws_painel.freeze_panes = "B6"
    ws_painel.column_dimensions["A"].width = 34
    for j in range(2, col_total + 1):
        ws_painel.column_dimensions[get_column_letter(j)].width = 12

    # Filtro na tabela visual do painel.
    ref_painel = f"A5:{get_column_letter(col_total)}{ultima_linha}"
    tabela_painel = Table(displayName="TabelaPainelAPI", ref=ref_painel)
    tabela_painel.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws_painel.add_table(tabela_painel)

    # Observação de uso.
    ws_painel.cell(linha_total + 2, 1, "Como usar:")
    ws_painel.cell(linha_total + 2, 1).font = Font(bold=True, color="123B5D")
    ws_painel.cell(
        linha_total + 3,
        1,
        "Altere a célula B3 para segmentar o painel por Base. As cidades vinculadas à Base permanecem no painel mesmo quando não possuem O.S.; nesses casos o valor é 0.",
    )
    ws_painel.merge_cells(start_row=linha_total + 3, start_column=1, end_row=linha_total + 4, end_column=min(col_total, 8))
    ws_painel.cell(linha_total + 3, 1).alignment = Alignment(wrap_text=True, vertical="top")

    # Cálculo automático ao abrir no Excel.
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = "auto"
    except Exception:
        pass

    # Painel primeiro, depois dados auxiliares.
    wb.active = 0

    saida = io.BytesIO()
    wb.save(saida)
    saida.seek(0)
    return saida


# ============================================================
# TABELA
# ============================================================

def gerar_tabela_local_periodo(
    df,
    modo,
    locais_forcados=None,
):

    dados = df.copy()

    # ========================================================
    # POR DATA
    # ========================================================
    #
    # Cada data com pelo menos uma O.S. em toda a base
    # vira uma coluna.
    #
    # Exemplo:
    #
    #             01/10   02/10   03/10
    # BAIRRO A       4       -       2
    # BAIRRO B       -       7       -
    #
    # O "-" será representado visualmente como espaço em branco.
    # ========================================================

    if modo == "Por dia":

        dados["_PERIODO"] = (
            dados["_DATA"]
            .dt.normalize()
        )

    # ========================================================
    # POR MÊS
    # ========================================================

    else:

        dados["_PERIODO"] = (
            dados["_DATA"]
            .dt.to_period("M")
            .dt.to_timestamp()
        )

    # ========================================================
    # LOCAIS
    # ========================================================

    if locais_forcados is not None:

        locais = sorted(
            [
                str(local)
                for local in locais_forcados
                if str(local).strip()
            ],
            key=normalizar,
        )

    else:

        locais = sorted(
            dados["_LOCAL"]
            .dropna()
            .astype(str)
            .unique(),
            key=normalizar,
        )

    # ========================================================
    # PERÍODOS
    # ========================================================
    #
    # IMPORTANTE:
    # Só entram datas/meses que possuem pelo menos uma O.S.
    # em qualquer local.
    # ========================================================

    periodos = sorted(
        dados["_PERIODO"]
        .dropna()
        .unique()
    )

    # ========================================================
    # CONTAGEM
    # ========================================================

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

            quantidade = contar_os(
                bloco
            )

            linha.append(
                quantidade
            )

        tabela[local] = linha

    resultado = pd.DataFrame(
        tabela,
        index=periodos,
    ).T

    resultado.index.name = "LOCAL"

    resultado = resultado.reindex(
        columns=periodos
    )

    # Garante valores numéricos
    resultado = resultado.fillna(0).astype(int)

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
    # FILTRO DE BASE — API
    # ========================================================

    if modulo == "API" and base:

        dados = dados[
            dados["_BASE"] == base
        ].copy()

    # ========================================================
    # LOCAIS ESPERADOS
    # ========================================================
    # API não deve depender da cidade possuir O.S. no arquivo para
    # aparecer no relatório. O cadastro oficial Base x Cidade define
    # quais cidades pertencem à base selecionada.
    #
    # Assim, ao selecionar uma base, TODAS as cidades daquela base
    # aparecem; as que não possuem O.S. no período ficam vazias/zeradas.
    # ========================================================

    locais_forcados = None

    if modulo == "API":

        if base:
            locais_forcados = cidades_da_base(base)
        else:
            locais_forcados = cidades_da_base(None)

    if dados.empty and not locais_forcados:

        raise ValueError(
            "Não existem registros para o filtro selecionado."
        )

    # ========================================================
    # GERA TABELA
    # ========================================================

    tabela = gerar_tabela_local_periodo(
        dados,
        modo,
        locais_forcados=locais_forcados,
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

    largura = 1500

    altura_cabecalho = 260

    altura_linha = 58

    largura_local = 390

    largura_periodo = 90

    largura_total = 110

    # Número de datas/meses por bloco
    periodos_por_bloco = 10

    blocos_periodos = [
        periodos[
            i:i + periodos_por_bloco
        ]
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
            + len(locais)
            * altura_linha
            + 45
        )

    altura_rodape = 90

    altura = (
        altura_cabecalho
        + altura_tabela_total
        + altura_rodape
    )

    # ========================================================
    # CANVAS
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
    # FAIXA SUPERIOR
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

    # ========================================================
    # TÍTULO
    # ========================================================

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
    # PERÍODO
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
        font=fonte(
            17
        ),
        fill=CINZA,
    )

    # ========================================================
    # TIPO DE VISUALIZAÇÃO
    # ========================================================

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
        font=fonte(
            16
        ),
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
    # POSIÇÃO INICIAL
    # ========================================================

    y_atual = altura_cabecalho

    # ========================================================
    # MÁXIMO GLOBAL
    # ========================================================

    if periodos:

        maximo = int(
            tabela[
                periodos
            ].max().max()
        )

    else:

        maximo = 0

    # ========================================================
    # BLOCOS
    # ========================================================

    for numero_bloco, bloco in enumerate(
        blocos_periodos
    ):

        # ====================================================
        # TÍTULO DO BLOCO
        # ====================================================

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

        # ====================================================
        # CABEÇALHO DA TABELA
        # ====================================================

        y_inicio = (
            y_atual + 45
        )

        largura_tabela = (
            largura_local
            + len(bloco)
            * largura_periodo
            + largura_total
        )

        x_inicio = margem

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

        # ====================================================
        # CABEÇALHO DOS PERÍODOS
        # ====================================================

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

        # ====================================================
        # COLUNA TOTAL
        # ====================================================

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

        # ====================================================
        # LINHAS
        # ====================================================

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

            # =================================================
            # NOME DO LOCAL
            # =================================================

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

            # =================================================
            # VALORES POR DATA/MÊS
            # =================================================

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

                # =============================================
                # CÉLULA
                # =============================================

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

                # =============================================
                # IMPORTANTE:
                #
                # Se valor == 0:
                #   não escreve nada.
                #
                # Assim a célula fica visualmente vazia.
                # =============================================

                if valor > 0:

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

            # =================================================
            # TOTAL DO LOCAL
            # =================================================

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

        # ====================================================
        # PRÓXIMO BLOCO
        # ====================================================

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
    # EXPORTAÇÃO
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
# LEITURA E CONSOLIDAÇÃO
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

# O cadastro oficial Base x Cidade possui 242 vínculos e é usado
# exclusivamente para determinar a abrangência de cada base API.
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

        cidades_base = cidades_da_base(
            base_selecionada
        )

        st.caption(
            f"{len(cidades_base)} cidade(s) vinculada(s) à base "
            f"{base_selecionada}. Todas serão consideradas no relatório."
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

            if modulo == "API":

                planilha_bytes = gerar_planilha_api(
                    df=df,
                    base_inicial=base_selecionada,
                    modo=modo,
                )

                st.session_state[
                    "relatorio_gerado_xlsx"
                ] = planilha_bytes.getvalue()

                st.session_state[
                    "relatorio_modulo"
                ] = modulo

                st.session_state[
                    "relatorio_modo"
                ] = modo

                st.session_state[
                    "relatorio_base"
                ] = base_selecionada

            else:

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

if "relatorio_modulo" in st.session_state:

    st.divider()

    st.markdown(
        "### Relatório gerado"
    )

    modulo_final = st.session_state[
        "relatorio_modulo"
    ]

    modo_final = st.session_state[
        "relatorio_modo"
    ]

    base_final = st.session_state[
        "relatorio_base"
    ]

    if modulo_final == "API" and "relatorio_gerado_xlsx" in st.session_state:

        planilha_final = st.session_state[
            "relatorio_gerado_xlsx"
        ]

        if base_final:
            nome_arquivo = (
                f"RELATORIO_FA_API_"
                f"{normalizar(base_final).replace(' ', '_')}_"
                f"{modo_final.replace(' ', '_')}.xlsx"
            )
        else:
            nome_arquivo = (
                f"RELATORIO_FA_API_"
                f"{modo_final.replace(' ', '_')}.xlsx"
            )

        st.success(
            "Planilha API pronta. Abra no Excel e use a célula "
            "'SEGMENTAÇÃO — BASE' para trocar a Base do painel."
        )

        st.download_button(
            label="BAIXAR PLANILHA API",
            data=planilha_final,
            file_name=nome_arquivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    elif "relatorio_gerado" in st.session_state:

        imagem_final = st.session_state[
            "relatorio_gerado"
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

