import streamlit as st
import io
import re
import html
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

        # Para THE/TIM o local principal já é o bairro.
        dados["_BAIRRO"] = dados["_LOCAL"]

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

        # O modo API pode ser detalhado por cidade e, depois,
        # apresentar os bairros daquela cidade.
        coluna_bairro = localizar_coluna(
            dados,
            [
                "Bairro",
                "BAIRRO",
                "Bairro do Cliente",
                "Bairro Cliente",
            ],
        )

        if coluna_bairro is not None:
            dados["_BAIRRO"] = (
                dados[coluna_bairro]
                .fillna("NÃO INFORMADO")
                .astype(str)
                .str.strip()
            )
            dados["_BAIRRO"] = dados["_BAIRRO"].replace(
                {
                    "": "NÃO INFORMADO",
                    "nan": "NÃO INFORMADO",
                    "NaN": "NÃO INFORMADO",
                }
            )
        else:
            dados["_BAIRRO"] = "NÃO INFORMADO"

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
# TABELA DINÂMICA / RELATÓRIO
# ============================================================

def periodo_label(mes):
    return f"{MESES_PT[mes.month]}/{mes.year}"


def data_label(data):
    return f"{data.day:02d}/{MESES_PT[data.month]}"


def contar_bloco(dados):
    if dados is None or dados.empty:
        return 0
    if "_PROTOCOLO" in dados.columns:
        validos = dados["_PROTOCOLO"].dropna()
        if not validos.empty:
            return int(validos.nunique())
    return int(len(dados))


def meses_disponiveis(dados):
    if dados is None or dados.empty:
        return []
    return sorted(
        [pd.Timestamp(x) for x in dados["_MES_ORDEM"].dropna().unique()]
    )


def montar_colunas_relatorio(dados, meses, meses_expandidos):
    """Retorna [(mes, data_ou_none)] em ordem visual."""
    colunas = []
    for mes in meses:
        if mes in meses_expandidos:
            dias = sorted(
                dados.loc[
                    dados["_MES_ORDEM"] == mes,
                    "_DATA",
                ].dropna().unique()
            )
            for dia in dias:
                colunas.append((mes, dia))
        else:
            colunas.append((mes, None))
    return colunas


def gerar_matriz_relatorio(
    dados,
    locais,
    colunas,
):
    """Gera a matriz final e o total por linha."""
    matriz = pd.DataFrame(
        0,
        index=locais,
        columns=range(len(colunas)),
        dtype=int,
    )

    for idx, (mes, dia) in enumerate(colunas):
        bloco_mes = dados[dados["_MES_ORDEM"] == mes]
        if dia is not None:
            bloco_mes = bloco_mes[
                bloco_mes["_DATA"] == dia
            ]

        if bloco_mes.empty:
            continue

        contagens = (
            bloco_mes.groupby("_LOCAL", sort=False)
            .apply(contar_bloco)
        )
        for local, valor in contagens.items():
            if local in matriz.index:
                matriz.loc[local, idx] = int(valor)

    matriz["__TOTAL__"] = matriz.sum(axis=1).astype(int)
    return matriz


def construir_tabela_html(
    matriz,
    locais,
    colunas,
    modulo,
    filtro_base=None,
):
    """Tabela visual no padrão do modelo enviado pelo usuário."""
    partes = []
    partes.append('<div class="relatorio-scroll">')
    partes.append('<table class="relatorio-fa">')
    partes.append('<thead>')

    # Linha de agrupamento por mês.
    partes.append('<tr class="mes-header">')
    partes.append('<th rowspan="2" class="local-header">LOCAL</th>')

    i = 0
    while i < len(colunas):
        mes = colunas[i][0]
        j = i
        while j < len(colunas) and colunas[j][0] == mes:
            j += 1
        span = j - i
        label = periodo_label(mes)
        partes.append(
            f'<th colspan="{span}" class="mes-header-cell">'
            f'{html.escape(label)}'
            f'</th>'
        )
        i = j

    partes.append('<th rowspan="2" class="total-header">TOTAL</th>')
    partes.append('</tr>')

    # Linha das datas.
    partes.append('<tr class="data-header">')
    for mes, dia in colunas:
        label = data_label(dia) if dia is not None else periodo_label(mes)
        partes.append(
            f'<th class="data-header-cell">{html.escape(label)}</th>'
        )
    partes.append('</tr>')
    partes.append('</thead>')
    partes.append('<tbody>')

    maximo = int(matriz.drop(columns=["__TOTAL__"]).to_numpy().max()) if len(matriz) else 0

    for local in locais:
        partes.append('<tr>')
        partes.append(
            f'<td class="local-cell">{html.escape(str(local))}</td>'
        )
        for idx in range(len(colunas)):
            valor = int(matriz.loc[local, idx])
            classe = " valor" if valor else " vazio"
            partes.append(
                f'<td class="numero-cell{classe}">'
                f'{formatar_numero(valor) if valor else ""}'
                f'</td>'
            )
        total = int(matriz.loc[local, "__TOTAL__"])
        partes.append(
            f'<td class="total-cell">{formatar_numero(total)}</td>'
        )
        partes.append('</tr>')

    # Total geral.
    partes.append('<tr class="total-geral">')
    partes.append('<td class="local-cell total-label">TOTAL GERAL</td>')
    for idx in range(len(colunas)):
        valor = int(matriz[idx].sum())
        partes.append(
            f'<td class="numero-cell total-geral-cell">'
            f'{formatar_numero(valor) if valor else ""}'
            f'</td>'
        )
    total_geral = int(matriz["__TOTAL__"].sum())
    partes.append(
        f'<td class="total-cell total-geral-cell">'
        f'{formatar_numero(total_geral)}'
        f'</td>'
    )
    partes.append('</tr>')

    partes.append('</tbody>')
    partes.append('</table>')
    partes.append('</div>')
    return "".join(partes)


def gerar_png_relatorio(
    matriz,
    locais,
    colunas,
    modulo,
    base=None,
    status=None,
):
    """Gera PNG em alta densidade, mantendo a nitidez mesmo para tabelas extensas."""
    # Renderiza em 3x a densidade lógica. A tabela mantém as mesmas proporções,
    # mas textos e linhas possuem muito mais pixels para o PNG e para o WhatsApp.
    escala = 3

    largura_local = 235
    largura_coluna = 82
    largura_total = 92
    altura_linha = 30
    altura_header = 32
    altura_subheader = 30
    margem = 24

    largura = (
        margem * 2
        + largura_local
        + len(colunas) * largura_coluna
        + largura_total
    )
    altura = (
        margem * 2
        + 58
        + altura_header
        + altura_subheader
        + (len(locais) + 1) * altura_linha
    )

    imagem = Image.new(
        "RGB",
        (largura * escala, altura * escala),
        "white",
    )
    draw_base = ImageDraw.Draw(imagem)

    # Proxy para desenhar usando coordenadas lógicas, automaticamente
    # convertidas para a resolução final.
    class _DrawEscalado:
        def __init__(self, draw, fator):
            self._draw = draw
            self._fator = fator

        def _xy(self, xy):
            if isinstance(xy, tuple):
                return tuple(int(round(v * self._fator)) for v in xy)
            return xy

        def rectangle(self, xy, **kwargs):
            return self._draw.rectangle(self._xy(xy), **kwargs)

        def text(self, xy, text, **kwargs):
            return self._draw.text(self._xy(xy), text, **kwargs)

        def textbbox(self, xy, text, **kwargs):
            return self._draw.textbbox(self._xy(xy), text, **kwargs)

    draw = _DrawEscalado(draw_base, escala)

    f_titulo = fonte(22 * escala, True)
    f_pequena = fonte(12 * escala, False)
    f_header = fonte(12 * escala, True)
    f_local = fonte(11 * escala, False)
    f_num = fonte(10 * escala, False)
    f_total = fonte(10 * escala, True)

    titulo = TITULOS.get(modulo, "Relatório de Falta de Água")
    draw.text((margem, 8), titulo, font=f_titulo, fill=AZUL_ESCURO)

    info = []
    if base:
        info.append(f"Base: {base}")
    if status:
        info.append(f"Status: {status}")
    if info:
        draw.text((margem, 36), " | ".join(info), font=f_pequena, fill=CINZA)

    y0 = margem + 58
    x0 = margem

    # Cabeçalho de meses.
    draw.rectangle(
        (x0, y0, x0 + largura_local, y0 + altura_header + altura_subheader),
        fill=AZUL_ESCURO,
        outline="#B8C2CC",
    )
    draw.text(
        (x0 + 8, y0 + 22),
        "LOCAL",
        font=f_header,
        fill=BRANCO,
    )

    x = x0 + largura_local
    i = 0
    while i < len(colunas):
        mes = colunas[i][0]
        j = i
        while j < len(colunas) and colunas[j][0] == mes:
            j += 1
        w = (j - i) * largura_coluna
        draw.rectangle(
            (x, y0, x + w, y0 + altura_header),
            fill=AZUL_ESCURO,
            outline="#B8C2CC",
        )
        label = periodo_label(mes)
        bbox = draw.textbbox((0, 0), label, font=f_header)
        draw.text(
            (x + (w - (bbox[2] - bbox[0])) / 2, y0 + 8),
            label,
            font=f_header,
            fill=BRANCO,
        )
        x += w
        i = j

    draw.rectangle(
        (x, y0, x + largura_total, y0 + altura_header + altura_subheader),
        fill=AZUL_ESCURO,
        outline="#B8C2CC",
    )
    draw.text((x + 12, y0 + 22), "TOTAL", font=f_header, fill=BRANCO)

    # Subcabeçalho.
    x = x0 + largura_local
    for mes, dia in colunas:
        draw.rectangle(
            (x, y0 + altura_header, x + largura_coluna, y0 + altura_header + altura_subheader),
            fill="#E8EDF2",
            outline="#B8C2CC",
        )
        label = data_label(dia) if dia is not None else periodo_label(mes)
        bbox = draw.textbbox((0, 0), label, font=f_header)
        draw.text(
            (x + (largura_coluna - (bbox[2] - bbox[0])) / 2, y0 + altura_header + 7),
            label,
            font=f_header,
            fill=AZUL_ESCURO,
        )
        x += largura_coluna

    y = y0 + altura_header + altura_subheader
    maximo = int(matriz.drop(columns=["__TOTAL__"]).to_numpy().max()) if len(matriz) else 0

    for local in locais:
        draw.rectangle(
            (x0, y, x0 + largura_local, y + altura_linha),
            fill="white",
            outline="#C8CDD2",
        )
        texto = abreviar_texto(local, 31)
        draw.text((x0 + 7, y + 8), texto, font=f_local, fill=AZUL_ESCURO)

        x = x0 + largura_local
        for idx in range(len(colunas)):
            valor = int(matriz.loc[local, idx])
            draw.rectangle(
                (x, y, x + largura_coluna, y + altura_linha),
                fill="white",
                outline="#D3D8DD",
            )
            if valor:
                bbox = draw.textbbox((0, 0), formatar_numero(valor), font=f_num)
                draw.text(
                    (x + (largura_coluna - (bbox[2] - bbox[0])) / 2, y + 8),
                    formatar_numero(valor),
                    font=f_num,
                    fill=AZUL_ESCURO,
                )
            x += largura_coluna

        total = int(matriz.loc[local, "__TOTAL__"])
        draw.rectangle(
            (x, y, x + largura_total, y + altura_linha),
            fill="#E8EDF2",
            outline="#B8C2CC",
        )
        draw.text((x + 22, y + 8), formatar_numero(total), font=f_total, fill=AZUL_ESCURO)
        y += altura_linha

    # Total geral.
    draw.rectangle(
        (x0, y, x0 + largura_local, y + altura_linha),
        fill=AZUL_ESCURO,
        outline=AZUL_ESCURO,
    )
    draw.text((x0 + 7, y + 8), "TOTAL GERAL", font=f_total, fill=BRANCO)

    x = x0 + largura_local
    for idx in range(len(colunas)):
        valor = int(matriz[idx].sum())
        draw.rectangle(
            (x, y, x + largura_coluna, y + altura_linha),
            fill=AZUL_ESCURO,
            outline=AZUL_ESCURO,
        )
        if valor:
            bbox = draw.textbbox((0, 0), formatar_numero(valor), font=f_total)
            draw.text(
                (x + (largura_coluna - (bbox[2] - bbox[0])) / 2, y + 8),
                formatar_numero(valor),
                font=f_total,
                fill=BRANCO,
            )
        x += largura_coluna

    total_geral = int(matriz["__TOTAL__"].sum())
    draw.rectangle(
        (x, y, x + largura_total, y + altura_linha),
        fill=AZUL_ESCURO,
        outline=AZUL_ESCURO,
    )
    draw.text((x + 22, y + 8), formatar_numero(total_geral), font=f_total, fill=BRANCO)

    output = io.BytesIO()
    # PNG é lossless; o parâmetro de escala acima garante alta densidade de
    # pixels sem depender do tamanho final da tabela.
    imagem.save(output, format="PNG", optimize=True, compress_level=6)
    output.seek(0)
    return output


def aplicar_filtro_status(df, coluna_status, status):
    if not coluna_status or not status or status == "Todos":
        return df
    return df[
        df[coluna_status]
        .fillna("NÃO INFORMADO")
        .astype(str)
        .str.strip()
        .eq(status)
    ].copy()


def locais_com_os(dados, coluna_local="_LOCAL"):
    """Retorna apenas localidades que possuem pelo menos uma O.S."""
    if dados is None or dados.empty or coluna_local not in dados.columns:
        return []

    locais_validos = []
    for local, bloco in dados.groupby(coluna_local, sort=False, dropna=False):
        if contar_bloco(bloco) > 0:
            texto = str(local).strip()
            if texto:
                locais_validos.append(texto)

    return sorted(set(locais_validos), key=normalizar)


# ============================================================
# INTERFACE
# ============================================================

st.markdown(
    '<div class="module-title">Relatório de Falta de Água - COI</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="module-subtitle">Tabela operacional para acompanhamento das O.S. de Falta de Água.</div>',
    unsafe_allow_html=True,
)

col_api, col_the, col_tim = st.columns(3, gap="medium")

with col_api:
    st.markdown("### API")
    arquivos_api = st.file_uploader(
        "Planilha(s) API",
        type=["xlsx", "xls", "xlsb"],
        accept_multiple_files=True,
        key="upload_api",
    )

with col_the:
    st.markdown("### THE")
    arquivos_the = st.file_uploader(
        "Planilha(s) THE",
        type=["xlsx", "xls", "xlsb"],
        accept_multiple_files=True,
        key="upload_the",
    )

with col_tim:
    st.markdown("### TIM")
    arquivos_tim = st.file_uploader(
        "Planilha(s) TIM",
        type=["xlsx", "xls", "xlsb"],
        accept_multiple_files=True,
        key="upload_tim",
    )

st.divider()

st.markdown(
    """
    <style>
        .relatorio-scroll {
            width: 100%;
            overflow-x: auto;
            overflow-y: auto;
            max-height: 72vh;
            border: 1px solid #B8C2CC;
            background: white;
        }

        table.relatorio-fa {
            border-collapse: collapse;
            width: max-content;
            min-width: 100%;
            font-size: 12px;
            color: #123B5D;
            background: white;
        }

        table.relatorio-fa th,
        table.relatorio-fa td {
            border: 1px solid #C8CDD2;
            padding: 4px 7px;
            height: 25px;
            box-sizing: border-box;
            white-space: nowrap;
        }

        table.relatorio-fa .local-header,
        table.relatorio-fa .total-header,
        table.relatorio-fa .mes-header-cell {
            background: #123B5D;
            color: white;
            font-weight: 700;
            text-align: center;
            position: sticky;
            top: 0;
            z-index: 4;
        }

        table.relatorio-fa .local-header {
            left: 0;
            min-width: 210px;
            text-align: left;
            z-index: 6;
        }

        table.relatorio-fa .data-header-cell {
            background: #E8EDF2;
            color: #123B5D;
            font-weight: 700;
            text-align: center;
            position: sticky;
            top: 29px;
            z-index: 3;
        }

        table.relatorio-fa .local-cell {
            background: white;
            position: sticky;
            left: 0;
            z-index: 2;
            min-width: 210px;
            text-align: left;
            font-weight: 500;
        }

        table.relatorio-fa .numero-cell {
            min-width: 62px;
            text-align: center;
        }

        table.relatorio-fa .vazio {
            color: transparent;
        }

        table.relatorio-fa .total-cell {
            min-width: 78px;
            background: #E8EDF2;
            text-align: center;
            font-weight: 700;
        }

        table.relatorio-fa .total-geral td {
            background: #123B5D;
            color: white;
            font-weight: 700;
        }

        table.relatorio-fa .total-geral .local-cell {
            background: #123B5D;
            color: white;
        }

        table.relatorio-fa .total-geral-cell {
            background: #123B5D !important;
            color: white !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns([1, 1, 1], gap="large")
with col1:
    modulo = st.radio(
        "Empresa / operação",
        ["API", "THE", "TIM"],
        horizontal=True,
    )

arquivos = {
    "API": arquivos_api,
    "THE": arquivos_the,
    "TIM": arquivos_tim,
}

arquivos_selecionados = arquivos[modulo]

if not arquivos_selecionados:
    st.info(f"Carregue uma ou mais planilhas de {modulo} para gerar o relatório.")
    st.stop()

with st.spinner(f"Consolidando os dados de {modulo}..."):
    df_original = ler_planilhas_consolidadas(arquivos_selecionados)
    if df_original is None:
        st.stop()
    df, erro = preparar_dados(df_original, modulo)

if erro:
    st.error(erro)
    st.stop()

# Status da Atividade é opcional, mas acompanha o padrão do modelo enviado.
coluna_status = localizar_coluna(
    df,
    [
        "Status da Atividade",
        "Status Atividade",
        "Status",
    ],
)

status_selecionado = "Todos"
if coluna_status:
    status_valores = sorted(
        [
            str(v).strip()
            for v in df[coluna_status].dropna().unique()
            if str(v).strip()
        ],
        key=normalizar,
    )
    opcoes_status = ["Todos"] + status_valores
    padrao = opcoes_status.index("Pendente") if "Pendente" in opcoes_status else 0
    with col2:
        status_selecionado = st.selectbox(
            "Status da Atividade",
            opcoes_status,
            index=padrao,
        )

base_selecionada = None
cidade_selecionada = None

# Filtro aplicado apenas para o relatório.
dados = aplicar_filtro_status(df, coluna_status, status_selecionado)

if modulo == "API":
    # --------------------------------------------------------
    # BASE / FONTE DE DADOS
    # --------------------------------------------------------
    with col3:
        bases_disponiveis = sorted(
            [b for b in df["_BASE"].dropna().unique() if b],
            key=normalizar,
        )
        opcoes_base = ["Todas"] + bases_disponiveis
        base_escolhida = st.selectbox(
            "Base / fonte de dados",
            opcoes_base,
        )

    if base_escolhida != "Todas":
        base_selecionada = base_escolhida
        dados = dados[dados["_BASE"] == base_selecionada].copy()

    # --------------------------------------------------------
    # CIDADE
    # --------------------------------------------------------
    # A cidade só é selecionada depois da Base. Ao escolher uma
    # cidade, o relatório passa a mostrar os bairros daquela cidade.
    cidades_com_os = locais_com_os(dados, "_LOCAL")
    opcoes_cidade = ["Todas"] + cidades_com_os

    cidade_escolhida = st.selectbox(
        "Cidade",
        opcoes_cidade,
        key="cidade_api_relatorio",
    )

    if cidade_escolhida != "Todas":
        cidade_selecionada = cidade_escolhida
        dados = dados[
            dados["_LOCAL"].astype(str).str.strip().eq(cidade_selecionada)
        ].copy()
        # O nível de linha muda de Cidade para Bairro.
        dados["_LOCAL"] = dados["_BAIRRO"]

    # Só aparecem cidades que realmente possuem O.S.
    # (quando não foi escolhida uma cidade).
    locais = locais_com_os(dados, "_LOCAL")

else:
    # THE/TIM: somente bairros com pelo menos uma O.S.
    locais = locais_com_os(dados, "_LOCAL")

if not locais:
    st.warning("Não há localidades com O.S. para os filtros selecionados.")
    st.stop()

# Meses disponíveis na seleção.
dados_periodos = dados
meses = meses_disponiveis(dados_periodos)
if not meses:
    st.warning("Não foi encontrada nenhuma data válida para montar as colunas.")
    st.stop()

mes_atual = pd.Timestamp.today().to_period("M").to_timestamp()

# O mês atual inicia expandido. Os demais começam agrupados.
if "meses_expandidos_fa" not in st.session_state:
    st.session_state["meses_expandidos_fa"] = {mes_atual}

# Remove meses que não existem mais e mantém o mês atual expandido.
st.session_state["meses_expandidos_fa"] = {
    m for m in st.session_state["meses_expandidos_fa"] if m in meses
}
st.session_state["meses_expandidos_fa"].add(mes_atual if mes_atual in meses else meses[-1])

st.markdown("### Período")
st.caption("Use + para detalhar um mês em dias. O mês atual inicia detalhado automaticamente.")

# Botões de expansão/recolhimento.
controles = st.columns(min(max(len(meses), 1), 8))
for i, mes in enumerate(meses):
    with controles[i % len(controles)]:
        expandido = mes in st.session_state["meses_expandidos_fa"]
        simbolo = "−" if expandido else "+"
        if st.button(
            f"{simbolo} {periodo_label(mes)}",
            key=f"toggle_mes_{modulo}_{mes.strftime('%Y%m')}",
            use_container_width=True,
        ):
            if expandido and mes == mes_atual:
                # O mês atual permanece detalhado por padrão, mas pode ser recolhido.
                st.session_state["meses_expandidos_fa"].discard(mes)
            elif expandido:
                st.session_state["meses_expandidos_fa"].discard(mes)
            else:
                st.session_state["meses_expandidos_fa"].add(mes)
            st.rerun()

meses_expandidos = st.session_state["meses_expandidos_fa"]
colunas = montar_colunas_relatorio(dados_periodos, meses, meses_expandidos)
matriz = gerar_matriz_relatorio(dados, locais, colunas)

# Ordenação operacional: maior volume de O.S. primeiro.
# Isso vale para cidades no API e para bairros no THE/TIM;
# quando uma cidade é selecionada no API, vale para os bairros.
ordem_locais = (
    matriz["__TOTAL__"]
    .sort_values(ascending=False, kind="stable")
    .index
    .tolist()
)
matriz = matriz.reindex(ordem_locais)
locais = ordem_locais

st.markdown(
    construir_tabela_html(
        matriz,
        locais,
        colunas,
        modulo,
        base_selecionada,
    ),
    unsafe_allow_html=True,
)

# PNG da mesma estrutura da tabela.
if "png_relatorio_fa" not in st.session_state:
    st.session_state["png_relatorio_fa"] = None

if st.button("ATUALIZAR PNG", type="secondary", use_container_width=True):
    png = gerar_png_relatorio(
        matriz,
        locais,
        colunas,
        modulo,
        base=base_selecionada,
        status=status_selecionado if status_selecionado != "Todos" else None,
    )
    st.session_state["png_relatorio_fa"] = png.getvalue()

# Sempre atualiza a imagem para refletir a tabela atual sem exigir botão.
png_atual = gerar_png_relatorio(
    matriz,
    locais,
    colunas,
    modulo,
    base=base_selecionada,
    status=status_selecionado if status_selecionado != "Todos" else None,
)
st.session_state["png_relatorio_fa"] = png_atual.getvalue()

st.download_button(
    "BAIXAR TABELA EM PNG",
    data=st.session_state["png_relatorio_fa"],
    file_name=(
        f"RELATORIO_FA_{modulo}"
        + (f"_{normalizar(base_selecionada).replace(' ', '_')}" if base_selecionada else "")
        + (f"_{normalizar(cidade_selecionada).replace(' ', '_')}" if cidade_selecionada else "")
        + ".png"
    ),
    mime="image/png",
    use_container_width=True,
)

