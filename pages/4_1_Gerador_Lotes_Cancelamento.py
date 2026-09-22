```python
# ============================================================
# MÓDULO 4.1 — FILTRAGEM / CANCELAMENTO
# PLATAFORMA COI — GERADOR DE LOTES
# ============================================================
#
# IMPORTANTE:
# As bases NÃO são carregadas neste módulo.
#
# O carregamento é realizado pelo HUB CENTRAL e mantido em:
#
#   st.session_state.df_api
#   st.session_state.df_the
#
# O modo operacional é mantido em:
#
#   st.session_state.modo_operacao
#
# ============================================================


# ============================================================
# IMPORTAÇÕES
# ============================================================

import io
import re
import unicodedata
from datetime import datetime, time

import pandas as pd
import streamlit as st

from auth import verificar_autenticacao

from gerador_lotes.estado import (
    inicializar_estado,
)

from gerador_lotes.exportacao import (
    dataframe_para_excel,
)


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Gerador de Lotes - Cancelamento",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# OCULTA NAVEGAÇÃO PADRÃO DO STREAMLIT
# ============================================================

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .block-container {
            padding-top: 1.5rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():

    st.warning(
        "Sessão não iniciada ou expirada."
    )

    if st.button(
        "Ir para o Login",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# ESTADO COMPARTILHADO
# ============================================================

inicializar_estado()


# ============================================================
# MAPA DE ZONAS
# ============================================================

MAPA_ZONAS = {

    "ACAUA": 229,
    "AGRICOLANDIA": 1,
    "AGUA BRANCA": 3,
    "ALAGOINHA": 129,
    "ALEGRETE DO PIAUI": 439,
    "ALTO LONGA": 2,
    "ALTOS": 4,
    "ALVORADA DO GURGUEIA": 414,
    "AMARANTE": 5,
    "ANGICAL DO PIAUI": 6,
    "ANISIO DE ABREU": 7,
    "ANTONIO ALMEIDA": 474,
    "AROAZES": 10,
    "AROEIRAS DO ITAIM": 415,
    "ARRAIAL": 9,
    "ASSUNCAO DO PIAUI": 422,
    "AVELINO LOPES": 11,
    "BAIXA GRANDE DO RIBEIRO": 125,
    "BARRA D ALCANTARA": 423,
    "BARRAS": 12,
    "BARREIRAS DO PIAUI": 13,
    "BARRO DURO": 14,
    "BATALHA": 15,
    "BELA VISTA DO PIAUI": 438,
    "BELEM DO PIAUI": 318,
    "BENEDITINOS": 19,
    "BERTOLINIA": 17,
    "BETANIA DO PIAUI": 441,
    "BOA HORA": 416,
    "BOCAINA": 16,
    "BOM JESUS": 20,
    "BOM PRINCIPIO DO PIAUI": 442,
    "BONFIM DO PIAUI": 179,
    "BOQUEIRAO DO PIAUI": 401,
    "BRASILEIRA": 121,
    "BREJO DO PIAUI": 160,
    "BURITI DOS LOPES": 18,
    "BURITI DOS MONTES": 443,
    "CABECEIRAS DO PIAUI": 127,
    "CAJAZEIRAS DO PIAUI": 444,
    "CAJUEIRO DA PRAIA": 206,
    "CALDEIRAO GRANDE DO PIAUI": 417,
    "CAMPINAS DO PIAUI": 22,
    "CAMPO ALEGRE DO FIDALGO": 418,
    "CAMPO GRANDE DO PIAUI": 195,
    "CAMPO LARGO DO PIAUI": 419,

    # CAMPO MAIOR NÃO POSSUI ZONA DEFINIDA

    "CANAVIEIRA": 138,
    "CANTO DO BURITI": 24,
    "CAPITAO DE CAMPOS": 21,
    "CAPITAO GERVASIO OLIVEIRA": 429,
    "CARACOL": 25,
    "CARAUBAS DO PIAUI": 402,
    "CARIDADE": 322,
    "CASTELO DO PIAUI": 27,
    "CAXINGO": 446,
    "COCAL": 28,
    "COCAL DE TELHA": 403,
    "COCAL DOS ALVES": 447,
    "COIVARAS": 448,
    "COLONIA DO GURGUEIA": 123,
    "COLONIA DO PIAUI": 162,
    "CONCEICAO DO CANINDE": 26,
    "CORONEL JOSE DIAS": 270,
    "CORRENTE": 29,
    "CRISTALANDIA": 30,
    "CRISTINO CASTRO": 31,
    "CURIMATA": 32,
    "CURRAIS": 449,
    "CURRAL NOVO PI": 268,
    "CURRALINHOS": 412,
    "DEMERVAL LOBAO": 33,
    "DIRCEU ARCOVERDE": 115,
    "DOM EXPEDITO LOPES": 34,
    "DOM INOCENCIO": 400,
    "DOMINGOS MOURAO": 70,
    "ELESBAO VELOSO": 36,
    "ELIZEU MARTINS": 35,
    "ESPERANTINA": 37,
    "FARTURA DO PIAUI": 329,
    "FLORES DO PIAUI": 39,
    "FLORESTA DO PIAUI": 450,
    "FLORIANO": 41,
    "FRANCINOPOLIS": 38,
    "FRANCISCO AIRES": 40,
    "FRANCISCO MACEDO": 404,
    "FRANCISCO SANTOS": 42,
    "FRONTEIRAS": 43,
    "GEMINIANO": 433,
    "GILBUES": 44,
    "GUADALUPE": 45,
    "GUARIBAS": 281,
    "HUGO NAPOLEAO": 46,
    "ILHA GRANDE": 149,
    "INHUMA": 47,
    "IPIRANGA": 49,
    "ISAIAS COELHO": 50,
    "ITAINOPOLIS": 51,
    "ITAUEIRA": 48,
    "JACOBINA DO PIAUI": 192,
    "JAICOS": 52,
    "JARDIM MULATO": 136,
    "JATOBA DO PIAUI": 452,
    "JERUMENHA": 54,
    "JOAO COSTA": 453,
    "JOAQUIM PIRES": 55,
    "JOCA MARQUES": 454,
    "JOSE DE FREITAS": 53,
    "JUAZEIRO DO PIAUI": 214,
    "JULIO BORGES": 203,
    "JUREMA": 209,
    "LAGOA ALEGRE": 120,
    "LAGOA DE SAO FRANCISCO": 424,
    "LAGOA DO BARRO DO PIAUI": 176,
    "LAGOA DO PIAUI": 455,
    "LAGOA DO SITIO": 425,
    "LAGOINHA DO PIAUI": 456,
    "LANDRI SALES": 435,
    "LUIS CORREIA": 57,
    "LUZILANDIA": 58,
    "MADEIRO": 457,
    "MANOEL EMIDIO": 59,
    "MARCOLANDIA": 406,
    "MARCOS PARENTE": 60,
    "MASSAPE DO PIAUI": 431,
    "MATIAS OLIMPIO": 61,
    "MIGUEL ALVES": 62,
    "MIGUEL LEAO": 459,
    "MILTON BRANDAO": 473,
    "MONSENHOR GIL": 65,
    "MONSENHOR HIPOLITO": 66,
    "MONTE ALEGRE": 64,
    "MORRO CABECA NO TEMPO": 434,
    "MORRO DO CHAPEU DO PIAUI": 405,
    "MURICI DOS PORTELAS": 320,
    "NAZARE DO PIAUI": 67,
    "NAZARIA": 131,
    "NOSSA SENHORA DE NAZARE": 420,
    "NOSSA SRA DOS REMEDIOS": 69,
    "NOVA SANTA RITA": 312,
    "NOVO ORIENTE DO PIAU": 68,
    "NOVO SANTO ANTONIO": 410,
    "OEIRAS": 71,
    "OLHO D'AGUA DO PIAUI": 461,
    "PADRE MARCOS": 72,
    "PAES LANDIM": 73,
    "PAJEU DO PIAUI": 462,
    "PALMEIRA DO PIAUI": 74,
    "PALMEIRAIS": 75,
    "PAQUETA": 187,
    "PARNAGUA": 76,
    "PARNAIBA": 77,
    "PASSAGEM FRANCA": 130,
    "PATOS DO PIAUI": 310,
    "PAU D ARCO DO PIAUI": 436,
    "PAULISTANA": 79,
    "PAVUSSU": 135,
    "PEDRO II": 80,
    "PEDRO LAURENTINO": 428,
    "PICOS": 81,
    "PIMENTEIRAS": 82,
    "PIO IX": 78,
    "PIRACURUCA": 83,
    "PIRIPIRI": 84,
    "PORTO": 85,
    "PORTO ALEGRE DO PIAUI": 426,
    "PRATA DO PIAUI": 86,
    "QUEIMADA NOVA": 465,
    "REDENCAO DO GURGUEIA": 466,
    "REGENERACAO": 89,
    "RIACHO FRIO": 146,
    "RIBEIRA DO PIAUI": 467,
    "RIBEIRO GONCALVES": 88,
    "RIO GRANDE DO PIAUI": 90,
    "SANTA CRUZ DO PIAUI": 93,
    "SANTA CRUZ DOS MILAGRES": 468,
    "SANTA FILOMENA": 94,
    "SANTA LUZ": 96,
    "SANTA ROSA DO PIAUI": 117,
    "SANTA TERESA": 158,
    "SANTANA DO PIAUI": 212,
    "SANTO ANTONIO DE LISBOA": 91,
    "SANTO ANTONIO D MILA": 122,
    "SANTO INACIO DO PIAUI": 102,
    "SAO BRAZ": 319,
    "SAO FELIX": 95,
    "SAO FRANCISCO DE ASSIS": 263,
    "SAO FRANCISCO DO PIAUI": 97,
    "SAO GONCALO DO GURGUEIA": 469,
    "SAO GONCALO DO PIAUI": 98,
    "SAO JOAO DA CANABRAVA": 116,
    "SAO JOAO DA FRONTEIRA": 408,
    "SAO JOAO DA SERRA": 99,
    "SAO JOAO DA VARJOTA": 411,
    "SAO JOAO DO ARRAIAL": 470,
    "SAO JOAO DO PIAUI": 104,
    "SAO JOSE DO DIVINO": 174,
    "SAO JOSE DO PEIXE": 103,
    "SAO JOSE DO PIAUI": 92,
    "SAO JULIAO": 100,
    "SAO LOURENCO": 269,
    "SAO LUIS DO PIAUI": 202,
    "SAO MIGUEL DA BAIXA GRANDE": 427,
    "SAO MIGUEL DO FIDALGO": 432,
    "SAO MIGUEL TAPUIO": 101,
    "SAO PEDRO": 105,
    "SAO RAIMUNDO NONATO": 106,
    "SEBASTIAO BARROS": 472,
    "SEBASTIAO LEAL": 126,
    "SIGEFREDO PACHECO": 409,
    "SIMOES": 107,
    "SIMPLICIO MENDES": 108,
    "SOCORRO DO PIAUI": 109,
    "SUSSUAPARA": 421,
    "TAMBORIL DO PIAUI": 437,
    "TANQUE DO PIAUI": 430,
    "TERESINA": 110,
    "UNIAO": 111,
    "URUCUI": 112,
    "VALENCA": 113,
    "VARZEA BRANCA": 193,
    "VARZEA GRANDE": 114,
    "VERA MENDES": 413,
    "VILA NOVA DO PIAUI": 196,
    "WALL FERRAZ": 309,

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
}


# ============================================================
# MAPA NORMALIZADO
# ============================================================

def normalizar_texto(texto):

    if pd.isna(texto):

        return ""

    texto = str(texto)

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = texto.upper().strip()

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto


MAPA_ZONAS_NORMALIZADO = {
    normalizar_texto(cidade): zona
    for cidade, zona in MAPA_ZONAS.items()
}


# ============================================================
# OBTÉM ZONA
# ============================================================

def obter_zona(cidade):

    cidade_normalizada = normalizar_texto(
        cidade
    )

    return MAPA_ZONAS_NORMALIZADO.get(
        cidade_normalizada
    )


# ============================================================
# LOCALIZA COLUNA
# ============================================================

def localizar_coluna(
    df,
    tipo,
):

    if df is None or df.empty:

        return None

    colunas = list(df.columns)

    normalizadas = {
        coluna: normalizar_texto(coluna)
        for coluna in colunas
    }


    # --------------------------------------------------------
    # PROTOCOLO
    # --------------------------------------------------------

    if tipo == "protocolo":

        for coluna, nome in normalizadas.items():

            if nome == "COD. PROTOCOLO ORIGEM":

                return coluna

        for coluna, nome in normalizadas.items():

            if (
                "PROTOCOLO" in nome
                and
                "ORIGEM" in nome
            ):

                return coluna


    # --------------------------------------------------------
    # MATRÍCULA
    # --------------------------------------------------------

    elif tipo == "matricula":

        for coluna, nome in normalizadas.items():

            if nome == "MATRICULA":

                return coluna

        for coluna, nome in normalizadas.items():

            if "MATRICULA" in nome:

                return coluna


    # --------------------------------------------------------
    # CIDADE
    # --------------------------------------------------------

    elif tipo == "cidade":

        for coluna, nome in normalizadas.items():

            if nome == "CIDADE":

                return coluna


    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    elif tipo == "bairro":

        for coluna, nome in normalizadas.items():

            if nome == "BAIRRO":

                return coluna

        for coluna, nome in normalizadas.items():

            if "BAIRRO" in nome:

                return coluna


    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    elif tipo == "data":

        for coluna, nome in normalizadas.items():

            if nome == "DATA":

                return coluna

        for coluna, nome in normalizadas.items():

            if nome.startswith("DATA "):

                return coluna

        for coluna, nome in normalizadas.items():

            if "DATA" in nome:

                return coluna

        # ----------------------------------------------------
        # Compatibilidade com "Início do SLA"
        # ----------------------------------------------------

        for coluna, nome in normalizadas.items():

            if (
                "INICIO DO SLA" in nome
                or
                "INICIO SLA" in nome
            ):

                return coluna


    return None


# ============================================================
# CONVERSÃO ROBUSTA DE DATAS
# ============================================================

def converter_datas_robusto(serie):

    if serie is None:

        return pd.Series(
            dtype="datetime64[ns]"
        )

    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]",
    )


    # ========================================================
    # DATETIME / TIMESTAMP
    # ========================================================

    mascara_datetime = serie.map(
        lambda valor:
        isinstance(
            valor,
            (datetime, pd.Timestamp),
        )
    )


    if mascara_datetime.any():

        resultado.loc[
            mascara_datetime
        ] = pd.to_datetime(
            serie.loc[mascara_datetime],
            errors="coerce",
        )


    # ========================================================
    # EXCEL SERIAL
    # ========================================================

    mascara_numerica = (
        ~mascara_datetime
        &
        serie.map(
            lambda valor:
            isinstance(
                valor,
                (int, float),
            )
            and not isinstance(
                valor,
                bool,
            )
        )
    )


    if mascara_numerica.any():

        valores_numericos = pd.to_numeric(
            serie.loc[mascara_numerica],
            errors="coerce",
        )

        resultado.loc[
            mascara_numerica
        ] = pd.to_datetime(
            valores_numericos,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )


    # ========================================================
    # STRINGS
    # ========================================================

    mascara_texto = (
        ~mascara_datetime
        &
        ~mascara_numerica
        &
        serie.notna()
    )


    if mascara_texto.any():

        textos = (
            serie.loc[mascara_texto]
            .astype(str)
            .str.strip()
        )


        # ----------------------------------------------------
        # dd/mm/yyyy HH:MM:SS
        # ----------------------------------------------------

        formatos = [
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]


        convertido = pd.Series(
            pd.NaT,
            index=textos.index,
            dtype="datetime64[ns]",
        )


        for formato in formatos:

            mascara_pendente = convertido.isna()

            if not mascara_pendente.any():
                break

            convertido.loc[
                mascara_pendente
            ] = pd.to_datetime(
                textos.loc[mascara_pendente],
                format=formato,
                errors="coerce",
            )


        # ----------------------------------------------------
        # Última tentativa para valores textuais não
        # reconhecidos pelos formatos explícitos.
        # ----------------------------------------------------

        mascara_pendente = convertido.isna()

        if mascara_pendente.any():

            convertido.loc[
                mascara_pendente
            ] = pd.to_datetime(
                textos.loc[mascara_pendente],
                errors="coerce",
                dayfirst=True,
            )


        resultado.loc[
            mascara_texto
        ] = convertido


    return resultado


# ============================================================
# CONVERSÃO DE HORA
# ============================================================

def converter_hora(valor):

    valor = str(valor).strip()

    correspondencia = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        valor,
    )

    if not correspondencia:

        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Use HH:MM."
        )


    hora = int(
        correspondencia.group(1)
    )

    minuto = int(
        correspondencia.group(2)
    )


    if not (
        0 <= hora <= 23
        and
        0 <= minuto <= 59
    ):

        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Use HH:MM."
        )


    return time(
        hora,
        minuto,
    )


# ============================================================
# PARSE DO PROTOCOLO
# ============================================================

def parse_protocolo(proto):

    if pd.isna(proto):

        return "", "", None

    texto = str(proto).strip()

    correspondencia = re.search(
        r"(\d+)\s*/\s*(\d{4})",
        texto,
    )

    if not correspondencia:

        return "", "", None


    numero = (
        correspondencia.group(1)
    )

    ano = (
        correspondencia.group(2)
    )

    numero_int = int(
        numero
    )


    return (
        numero,
        ano,
        numero_int,
    )


# ============================================================
# ESTADO ESPECÍFICO DA FERRAMENTA
# ============================================================

def inicializar_estado_filtragem():

    valores_padrao = {

        "filtro_cidades": [],
        "filtro_bairros": [],
        "filtro_anos": [],
        "filtro_meses": [],
        "filtro_dias": [],

        "hora_inicio": "00:00",
        "hora_fim": "23:59",

        "observacoes_filtragem": "",

        "filtragem_preview": None,
        "filtragem_etapas": [],
        "filtragem_total_inicial": 0,

        "filtragem_geracao_info": None,
    }


    for chave, valor in valores_padrao.items():

        if chave not in st.session_state:

            if isinstance(
                valor,
                list,
            ):

                st.session_state[chave] = (
                    valor.copy()
                )

            else:

                st.session_state[chave] = valor


# ============================================================
# OBTÉM MODO ATIVO
# ============================================================

def obter_modo_atual():

    modo = str(
        st.session_state.get(
            "modo_operacao",
            "API",
        )
    ).upper().strip()


    if modo not in (
        "API",
        "THE",
    ):

        modo = "API"


    return modo


# ============================================================
# OBTÉM BASE ATIVA
# ============================================================

def obter_backlog_filtragem(
    modo=None,
):

    if modo is None:

        modo = obter_modo_atual()


    modo = str(
        modo
    ).upper().strip()


    if modo == "THE":

        return st.session_state.get(
            "df_the"
        )


    return st.session_state.get(
        "df_api"
    )


# ============================================================
# COLUNAS DISPONÍVEIS
# ============================================================

def obter_colunas_filtragem(df):

    if df is None or df.empty:

        return {
            "cidade": None,
            "bairro": None,
            "data": None,
            "protocolo": None,
            "matricula": None,
        }


    return {

        "cidade": localizar_coluna(
            df,
            "cidade",
        ),

        "bairro": localizar_coluna(
            df,
            "bairro",
        ),

        "data": localizar_coluna(
            df,
            "data",
        ),

        "protocolo": localizar_coluna(
            df,
            "protocolo",
        ),

        "matricula": localizar_coluna(
            df,
            "matricula",
        ),
    }


# ============================================================
# VALORES ÚNICOS
# ============================================================

def obter_valores_unicos(
    df,
    coluna,
):

    if (
        df is None
        or df.empty
        or coluna is None
    ):

        return []


    valores = (
        df[coluna]
        .dropna()
        .astype(str)
        .str.strip()
    )


    valores = valores[
        ~valores.str.lower().isin(
            {
                "",
                "nan",
                "none",
                "null",
            }
        )
    ]


    resultado = {}


    for valor in valores:

        normalizado = normalizar_texto(
            valor
        )

        if not normalizado:
            continue

        if normalizado not in resultado:

            resultado[normalizado] = valor


    return sorted(
        resultado.values(),
        key=normalizar_texto,
    )


# ============================================================
# CIDADES
# ============================================================

def obter_cidades_filtragem(df):

    col_cidade = localizar_coluna(
        df,
        "cidade",
    )

    return obter_valores_unicos(
        df,
        col_cidade,
    )


# ============================================================
# BAIRROS
# ============================================================

def obter_bairros_filtragem(
    df,
    cidades_selecionadas=None,
):

    col_bairro = localizar_coluna(
        df,
        "bairro",
    )


    if col_bairro is None:

        return []


    base = df.copy()


    cidades_selecionadas = (
        cidades_selecionadas
        or []
    )


    if cidades_selecionadas:

        col_cidade = localizar_coluna(
            df,
            "cidade",
        )


        if col_cidade is not None:

            cidades_norm = {
                normalizar_texto(cidade)
                for cidade
                in cidades_selecionadas
            }


            mascara = (
                df[col_cidade]
                .map(normalizar_texto)
                .isin(cidades_norm)
            )


            base = df.loc[
                mascara
            ]


    return obter_valores_unicos(
        base,
        col_bairro,
    )


# ============================================================
# ANOS
# ============================================================

def obter_anos_filtragem(df):

    col_data = localizar_coluna(
        df,
        "data",
    )


    if col_data is None:

        return []


    datas = converter_datas_robusto(
        df[col_data]
    )


    anos = (
        datas
        .dropna()
        .dt.year
        .astype(int)
        .unique()
        .tolist()
    )


    anos.sort()

    return anos


# ============================================================
# MESES
# ============================================================

MESES_FILTRAGEM = {

    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def obter_meses_filtragem():

    return list(
        MESES_FILTRAGEM.keys()
    )


# ============================================================
# DIAS
# ============================================================

def obter_dias_filtragem():

    return list(
        range(
            1,
            32,
        )
    )


# ============================================================
# APLICA FILTROS
# ============================================================

def aplicar_filtros_filtragem(
    df_consolidado,
):

    if df_consolidado is None:

        raise ValueError(
            "Nenhum arquivo foi carregado."
        )


    if df_consolidado.empty:

        raise ValueError(
            "A base carregada está vazia."
        )


    df = (
        df_consolidado
        .copy()
    )


    total_inicial = len(
        df
    )


    col_cidade = localizar_coluna(
        df,
        "cidade",
    )

    col_bairro = localizar_coluna(
        df,
        "bairro",
    )

    col_data = localizar_coluna(
        df,
        "data",
    )


    etapas = []


    # ========================================================
    # CIDADE
    # ========================================================

    cidades_selecionadas = list(
        st.session_state.get(
            "filtro_cidades",
            [],
        )
    )


    if cidades_selecionadas:

        if col_cidade is None:

            raise ValueError(
                "A planilha não possui a coluna Cidade."
            )


        cidades_norm = {
            normalizar_texto(cidade)
            for cidade
            in cidades_selecionadas
        }


        mascara = (
            df[col_cidade]
            .map(normalizar_texto)
            .isin(cidades_norm)
        )


        df = df.loc[
            mascara
        ]


        etapas.append(
            (
                "Cidade",
                len(df),
            )
        )


    # ========================================================
    # BAIRRO
    # ========================================================

    bairros_selecionados = list(
        st.session_state.get(
            "filtro_bairros",
            [],
        )
    )


    if bairros_selecionados:

        if col_bairro is None:

            raise ValueError(
                "A planilha não possui a coluna Bairro."
            )


        bairros_norm = {
            normalizar_texto(bairro)
            for bairro
            in bairros_selecionados
        }


        mascara = (
            df[col_bairro]
            .map(normalizar_texto)
            .isin(bairros_norm)
        )


        df = df.loc[
            mascara
        ]


        etapas.append(
            (
                "Bairro",
                len(df),
            )
        )


    # ========================================================
    # DATA / HORÁRIO
    # ========================================================

    anos_selecionados = list(
        st.session_state.get(
            "filtro_anos",
            [],
        )
    )


    meses_selecionados = list(
        st.session_state.get(
            "filtro_meses",
            [],
        )
    )


    dias_selecionados = list(
        st.session_state.get(
            "filtro_dias",
            [],
        )
    )


    inicio = converter_hora(
        st.session_state.get(
            "hora_inicio",
            "00:00",
        )
    )


    fim = converter_hora(
        st.session_state.get(
            "hora_fim",
            "23:59",
        )
    )


    horario_restrito = not (
        inicio == time(0, 0)
        and
        fim == time(23, 59)
    )


    precisa_data = (
        bool(anos_selecionados)
        or
        bool(meses_selecionados)
        or
        bool(dias_selecionados)
        or
        horario_restrito
    )


    if precisa_data:

        if col_data is None:

            raise ValueError(
                "A planilha não possui uma coluna de data "
                "identificável. A ferramenta procura "
                "'DATA' ou 'Início do SLA'."
            )


        datas = converter_datas_robusto(
            df[col_data]
        )


        # ====================================================
        # ANO
        # ====================================================

        if anos_selecionados:

            anos = {
                int(ano)
                for ano
                in anos_selecionados
            }


            mascara = (
                datas.dt.year
                .isin(anos)
            )


            df = df.loc[
                mascara
            ]


            datas = converter_datas_robusto(
                df[col_data]
            )


            etapas.append(
                (
                    "Ano",
                    len(df),
                )
            )


        # ====================================================
        # MÊS
        # ====================================================

        if meses_selecionados:

            meses = {
                int(mes)
                for mes
                in meses_selecionados
            }


            mascara = (
                datas.dt.month
                .isin(meses)
            )


            df = df.loc[
                mascara
            ]


            datas = converter_datas_robusto(
                df[col_data]
            )


            etapas.append(
                (
                    "Mês",
                    len(df),
                )
            )


        # ====================================================
        # DIA
        # ====================================================

        if dias_selecionados:

            dias = {
                int(dia)
                for dia
                in dias_selecionados
            }


            mascara = (
                datas.dt.day
                .isin(dias)
            )


            df = df.loc[
                mascara
            ]


            datas = converter_datas_robusto(
                df[col_data]
            )


            etapas.append(
                (
                    "Dia",
                    len(df),
                )
            )


        # ====================================================
        # HORÁRIO
        # ====================================================

        if horario_restrito:

            inicio_segundos = (
                inicio.hour * 3600
                +
                inicio.minute * 60
            )


            fim_segundos = (
                fim.hour * 3600
                +
                fim.minute * 60
                +
                59
            )


            segundos = (
                datas.dt.hour * 3600
                +
                datas.dt.minute * 60
                +
                datas.dt.second
            )


            if inicio_segundos <= fim_segundos:

                mascara_horario = (
                    datas.notna()
                    &
                    (
                        segundos
                        >=
                        inicio_segundos
                    )
                    &
                    (
                        segundos
                        <=
                        fim_segundos
                    )
                )

            else:

                mascara_horario = (
                    datas.notna()
                    &
                    (
                        (
                            segundos
                            >=
                            inicio_segundos
                        )
                        |
                        (
                            segundos
                            <=
                            fim_segundos
                        )
                    )
                )


            df = df.loc[
                mascara_horario
            ]


            etapas.append(
                (
                    "Horário",
                    len(df),
                )
            )


    df_filtrado_atual = (
        df
        .reset_index(drop=True)
    )


    return (
        df_filtrado_atual,
        etapas,
        total_inicial,
    )


# ============================================================
# GERAÇÃO DO LOTE
# ============================================================

def gerar_lote_filtragem():

    modo = obter_modo_atual()


    df_consolidado = (
        obter_backlog_filtragem(
            modo
        )
    )


    if df_consolidado is None:

        raise ValueError(
            f"Nenhuma base do modo {modo} foi carregada."
        )


    if df_consolidado.empty:

        raise ValueError(
            f"A base {modo} está vazia."
        )


    # ========================================================
    # APLICA FILTROS
    # ========================================================

    (
        df_filtrado,
        etapas,
        total_inicial,
    ) = aplicar_filtros_filtragem(
        df_consolidado
    )


    st.session_state.filtragem_total_inicial = (
        total_inicial
    )

    st.session_state.filtragem_etapas = (
        etapas
    )

    st.session_state.filtragem_preview = (
        df_filtrado.copy()
    )


    if df_filtrado.empty:

        st.session_state.df_resultado = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

        raise ValueError(
            "Nenhuma O.S. foi encontrada "
            "com os filtros selecionados."
        )


    # ========================================================
    # LOCALIZA COLUNAS
    # ========================================================

    col_protocolo = localizar_coluna(
        df_filtrado,
        "protocolo",
    )

    col_matricula = localizar_coluna(
        df_filtrado,
        "matricula",
    )

    col_cidade = localizar_coluna(
        df_filtrado,
        "cidade",
    )


    if col_protocolo is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'COD. PROTOCOLO ORIGEM'."
        )


    if col_matricula is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'MATRICULA'."
        )


    if col_cidade is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'CIDADE'."
        )


    # ========================================================
    # OBSERVAÇÃO
    # ========================================================

    observacao = str(
        st.session_state.get(
            "observacoes_filtragem",
            "",
        )
    ).strip()


    cidades_sem_zona = []
    protocolos_invalidos = []

    resultados = []


    # ========================================================
    # PROCESSAMENTO
    # ========================================================

    for _, linha in df_filtrado.iterrows():

        matricula = linha[
            col_matricula
        ]

        cidade = linha[
            col_cidade
        ]

        protocolo = linha[
            col_protocolo
        ]


        # ----------------------------------------------------
        # PROTOCOLO
        # ----------------------------------------------------

        (
            numero_pedido,
            ano_pedido,
            numero_int,
        ) = parse_protocolo(
            protocolo
        )


        if numero_int is None:

            protocolos_invalidos.append(
                {
                    "Matrícula": matricula,
                    "Protocolo": protocolo,
                    "Cidade": cidade,
                    "Motivo": (
                        "Protocolo não está no formato "
                        "número/ano."
                    ),
                }
            )

            continue


        # ----------------------------------------------------
        # ZONA
        # ----------------------------------------------------

        if modo == "THE":

            zona = 1

        else:

            zona = obter_zona(
                cidade
            )


            if zona is None:

                cidades_sem_zona.append(
                    {
                        "Matrícula": matricula,
                        "Protocolo": protocolo,
                        "Cidade": cidade,
                        "Motivo": (
                            "Cidade não possui zona "
                            "definida no MAPA_ZONAS."
                        ),
                    }
                )

                continue


        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        resultados.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_int,
                "Ano Do Pedido": int(ano_pedido),
                "Tipo Encerramento": 1,
                "Observações": observacao,
            }
        )


    # ========================================================
    # DATAFRAME FINAL
    # ========================================================

    df_resultado = pd.DataFrame(
        resultados,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações",
        ],
    )


    if df_resultado.empty:

        st.session_state.df_resultado = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

        raise ValueError(
            "Nenhuma O.S. válida pôde ser convertida em lote."
        )


    # ========================================================
    # TIPOS NUMÉRICOS
    # ========================================================

    for coluna in [
        "Zona Ligacao",
        "Numero Do Pedido",
        "Ano Do Pedido",
        "Tipo Encerramento",
    ]:

        df_resultado[coluna] = (
            pd.to_numeric(
                df_resultado[coluna],
                errors="coerce",
            )
            .astype("Int64")
        )


    # ========================================================
    # LOG
    # ========================================================

    linhas_log = []


    for item in cidades_sem_zona:

        linhas_log.append(
            {
                "Tipo": "Cidade sem zona",
                "Matrícula": item["Matrícula"],
                "Protocolo": item["Protocolo"],
                "Cidade": item["Cidade"],
                "Motivo": item["Motivo"],
            }
        )


    for item in protocolos_invalidos:

        linhas_log.append(
            {
                "Tipo": "Protocolo inválido",
                "Matrícula": item["Matrícula"],
                "Protocolo": item["Protocolo"],
                "Cidade": item["Cidade"],
                "Motivo": item["Motivo"],
            }
        )


    if linhas_log:

        df_log = pd.DataFrame(
            linhas_log
        )

    else:

        df_log = pd.DataFrame(
            columns=[
                "Tipo",
                "Matrícula",
                "Protocolo",
                "Cidade",
                "Motivo",
            ]
        )


    # ========================================================
    # NOME DO ARQUIVO
    # ========================================================

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )


    nome_arquivo = (
        f"Lote_Cancelamento_"
        f"{modo}_"
        f"{timestamp}.xlsx"
    )


    # ========================================================
    # SALVA RESULTADO
    # ========================================================

    st.session_state.df_resultado = (
        df_resultado
    )

    st.session_state.df_log = (
        df_log
    )

    st.session_state.nome_arquivo_resultado = (
        nome_arquivo
    )


    st.session_state.filtragem_geracao_info = {

        "modo": modo,

        "total_inicial": total_inicial,

        "total_filtrado": len(
            df_filtrado
        ),

        "total_resultado": len(
            df_resultado
        ),

        "cidades_sem_zona": len(
            cidades_sem_zona
        ),

        "protocolos_invalidos": len(
            protocolos_invalidos
        ),

        "etapas": etapas,
    }


    return (
        df_resultado,
        df_log,
    )


# ============================================================
# LOG PARA EXCEL
# ============================================================

def log_para_excel_filtragem(
    df_log,
):

    if df_log is None:

        return None


    if df_log.empty:

        return None


    buffer = io.BytesIO()


    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        df_log.to_excel(
            writer,
            index=False,
            sheet_name="LOG",
        )


    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# LIMPA RESULTADO
# ============================================================

def limpar_resultado_filtragem():

    st.session_state.df_resultado = None

    st.session_state.df_log = None

    st.session_state.nome_arquivo_resultado = None

    st.session_state.filtragem_preview = None

    st.session_state.filtragem_etapas = []

    st.session_state.filtragem_total_inicial = 0

    st.session_state.filtragem_geracao_info = None


# ============================================================
# LIMPA FILTROS
# ============================================================

def limpar_filtros_filtragem():

    st.session_state.filtro_cidades = []
    st.session_state.filtro_bairros = []
    st.session_state.filtro_anos = []
    st.session_state.filtro_meses = []
    st.session_state.filtro_dias = []

    st.session_state.hora_inicio = "00:00"
    st.session_state.hora_fim = "23:59"

    st.session_state.observacoes_filtragem = ""

    st.session_state.filtragem_preview = None
    st.session_state.filtragem_etapas = []
    st.session_state.filtragem_total_inicial = 0
    st.session_state.filtragem_geracao_info = None

    for chave in [
        "ui_filtro_cidades",
        "ui_filtro_bairros",
        "ui_filtro_anos",
        "ui_filtro_meses",
        "ui_filtro_dias",
        "ui_hora_inicio",
        "ui_hora_fim",
        "ui_observacoes_filtragem",
    ]:

        st.session_state.pop(
            chave,
            None,
        )


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_filtragem_cancelamento():

    inicializar_estado_filtragem()


    # ========================================================
    # SIDEBAR
    # ========================================================

    with st.sidebar:

        st.markdown(
            "### 🛠️ Ferramentas Operacionais"
        )

        st.caption(
            "Usuário: **"
            f"{st.session_state.get('usuario_logado', '')}"
            "**"
        )

        st.caption(
            "Perfil: **"
            f"{st.session_state.get('perfil', '').upper()}"
            "**"
        )

        st.divider()


        if st.button(
            "🏠 Voltar ao Menu Principal",
            use_container_width=True,
        ):

            limpar_resultado_filtragem()

            st.switch_page(
                "app.py"
            )


        if st.button(
            "↩️ Voltar às Ferramentas",
            use_container_width=True,
        ):

            limpar_resultado_filtragem()

            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )


    # ========================================================
    # MODO ATIVO
    # ========================================================

    modo = obter_modo_atual()

    df = obter_backlog_filtragem(
        modo
    )


    # ========================================================
    # CABEÇALHO
    # ========================================================

    st.title(
        "📦 Gerador de Lotes — Cancelamento"
    )

    st.caption(
        "Filtre o backlog carregado no Hub Central "
        "e gere o lote de cancelamento."
    )


    # ========================================================
    # AVISO SOBRE ORIGEM DA BASE
    # ========================================================

    st.info(
        "ℹ️ As bases utilizadas por esta ferramenta "
        "são carregadas exclusivamente no **Hub Central**. "
        "Não é necessário realizar upload nesta página."
    )


    # ========================================================
    # BASE INEXISTENTE
    # ========================================================

    if df is None:

        st.warning(
            f"Nenhuma base **{modo}** foi carregada no Hub Central."
        )

        st.markdown(
            "Retorne ao Hub, carregue a base correspondente "
            "e depois abra novamente esta ferramenta."
        )

        if st.button(
            "🏠 Ir para o Hub Central",
            type="primary",
            use_container_width=True,
        ):

            st.switch_page(
                "app.py"
            )

        return


    # ========================================================
    # BASE VAZIA
    # ========================================================

    if df.empty:

        st.error(
            f"A base **{modo}** está vazia."
        )

        return


    # ========================================================
    # COLUNAS
    # ========================================================

    colunas = obter_colunas_filtragem(
        df
    )


    # ========================================================
    # RESUMO
    # ========================================================

    col1, col2, col3, col4 = st.columns(4)


    with col1:

        st.metric(
            "Modo ativo",
            modo,
        )


    with col2:

        st.metric(
            "Registros na base",
            f"{len(df):,}".replace(
                ",",
                ".",
            ),
        )


    with col3:

        st.metric(
            "Coluna Cidade",
            colunas["cidade"]
            or "Não encontrada",
        )


    with col4:

        st.metric(
            "Coluna temporal",
            colunas["data"]
            or "Não encontrada",
        )


    st.divider()


    # ========================================================
    # LOCALIZAÇÃO
    # ========================================================

    st.markdown(
        "### 📍 Localização"
    )


    cidades_disponiveis = (
        obter_cidades_filtragem(
            df
        )
    )


    cidades_atuais = (
        st.session_state.get(
            "filtro_cidades",
            [],
        )
    )


    cidades_validas = [
        cidade
        for cidade
        in cidades_atuais
        if cidade in cidades_disponiveis
    ]


    cidades_selecionadas = st.multiselect(
        "Cidade",
        options=cidades_disponiveis,
        default=cidades_validas,
        key="ui_filtro_cidades",
        help=(
            "Selecione uma ou mais cidades. "
            "Sem seleção, todas as cidades serão consideradas."
        ),
    )


    st.session_state.filtro_cidades = (
        cidades_selecionadas
    )


    # ========================================================
    # BAIRROS
    # ========================================================

    bairros_disponiveis = (
        obter_bairros_filtragem(
            df,
            cidades_selecionadas,
        )
    )


    bairros_atuais = (
        st.session_state.get(
            "filtro_bairros",
            [],
        )
    )


    bairros_validos = [
        bairro
        for bairro
        in bairros_atuais
        if bairro in bairros_disponiveis
    ]


    bairros_selecionados = st.multiselect(
        "Bairro",
        options=bairros_disponiveis,
        default=bairros_validos,
        key="ui_filtro_bairros",
        help=(
            "Selecione um ou mais bairros. "
            "Sem seleção, todos os bairros serão considerados."
        ),
    )


    st.session_state.filtro_bairros = (
        bairros_selecionados
    )


    st.divider()


    # ========================================================
    # DATA
    # ========================================================

    st.markdown(
        "### 📅 Data"
    )


    if colunas["data"] is None:

        st.warning(
            "A base não possui uma coluna identificável "
            "como DATA ou Início do SLA. "
            "Os filtros temporais ficarão indisponíveis."
        )

    else:

        anos_disponiveis = (
            obter_anos_filtragem(
                df
            )
        )


        anos_atuais = (
            st.session_state.get(
                "filtro_anos",
                [],
            )
        )


        anos_validos = [
            ano
            for ano
            in anos_atuais
            if ano in anos_disponiveis
        ]


        anos_selecionados = st.multiselect(
            "Ano",
            options=anos_disponiveis,
            default=anos_validos,
            key="ui_filtro_anos",
            help=(
                "Filtra pelo ano da coluna temporal identificada."
            ),
        )


        st.session_state.filtro_anos = (
            anos_selecionados
        )


        col_mes, col_dia = st.columns(2)


        with col_mes:

            meses_disponiveis = (
                obter_meses_filtragem()
            )


            meses_atuais = (
                st.session_state.get(
                    "filtro_meses",
                    [],
                )
            )


            meses_validos = [
                mes
                for mes
                in meses_atuais
                if mes in meses_disponiveis
            ]


            meses_selecionados = st.multiselect(
                "Mês",
                options=meses_disponiveis,
                default=meses_validos,
                format_func=lambda x:
                    f"{x:02d} — {MESES_FILTRAGEM[x]}",
                key="ui_filtro_meses",
                help=(
                    "Filtra pelo mês da coluna temporal."
                ),
            )


            st.session_state.filtro_meses = (
                meses_selecionados
            )


        with col_dia:

            dias_disponiveis = (
                obter_dias_filtragem()
            )


            dias_atuais = (
                st.session_state.get(
                    "filtro_dias",
                    [],
                )
            )


            dias_validos = [
                dia
                for dia
                in dias_atuais
                if dia in dias_disponiveis
            ]


            dias_selecionados = st.multiselect(
                "Dia",
                options=dias_disponiveis,
                default=dias_validos,
                key="ui_filtro_dias",
                help=(
                    "Filtra pelo dia da coluna temporal."
                ),
            )


            st.session_state.filtro_dias = (
                dias_selecionados
            )


        # ====================================================
        # HORÁRIO
        # ====================================================

        st.markdown(
            "#### ⏰ Horário"
        )


        col_hora1, col_hora2 = st.columns(2)


        with col_hora1:

            hora_inicio = st.text_input(
                "Hora inicial",
                value=st.session_state.get(
                    "hora_inicio",
                    "00:00",
                ),
                key="ui_hora_inicio",
                placeholder="HH:MM",
            )


            st.session_state.hora_inicio = (
                hora_inicio
            )


        with col_hora2:

            hora_fim = st.text_input(
                "Hora final",
                value=st.session_state.get(
                    "hora_fim",
                    "23:59",
                ),
                key="ui_hora_fim",
                placeholder="HH:MM",
            )


            st.session_state.hora_fim = (
                hora_fim
            )


        st.caption(
            "Use 00:00 → 23:59 para não restringir "
            "o horário. Também é permitido atravessar "
            "a meia-noite, por exemplo, 22:00 → 02:00."
        )


    st.divider()


    # ========================================================
    # OBSERVAÇÃO
    # ========================================================

    st.markdown(
        "### 📝 Observação do cancelamento"
    )


    observacao = st.text_area(
        "Observações",
        value=st.session_state.get(
            "observacoes_filtragem",
            "",
        ),
        key="ui_observacoes_filtragem",
        placeholder=(
            "Digite a observação que será gravada "
            "no lote de cancelamento."
        ),
        height=100,
    )


    st.session_state.observacoes_filtragem = (
        observacao
    )


    st.divider()


    # ========================================================
    # BOTÕES
    # ========================================================

    col_preview, col_generate, col_clear = st.columns(
        [1, 1, 1]
    )


    # ========================================================
    # PRÉVIA
    # ========================================================

    with col_preview:

        if st.button(
            "👁️ Prévia",
            key="btn_filtragem_preview",
            use_container_width=True,
        ):

            try:

                (
                    df_preview,
                    etapas,
                    total_inicial,
                ) = aplicar_filtros_filtragem(
                    df
                )


                st.session_state.filtragem_preview = (
                    df_preview.copy()
                )

                st.session_state.filtragem_etapas = (
                    etapas
                )

                st.session_state.filtragem_total_inicial = (
                    total_inicial
                )


                st.success(
                    "Prévia atualizada."
                )


            except Exception as erro:

                st.error(
                    str(erro)
                )


    # ========================================================
    # GERAR LOTE
    # ========================================================

    with col_generate:

        if st.button(
            "📦 Gerar lote",
            key="btn_filtragem_gerar",
            type="primary",
            use_container_width=True,
        ):

            try:

                gerar_lote_filtragem()

                st.success(
                    "✓ Lote gerado com sucesso."
                )


            except Exception as erro:

                st.error(
                    str(erro)
                )


    # ========================================================
    # LIMPAR
    # ========================================================

    with col_clear:

        if st.button(
            "🧹 Limpar resultado",
            key="btn_filtragem_limpar",
            use_container_width=True,
        ):

            limpar_resultado_filtragem()

            st.rerun()


    # ========================================================
    # PRÉVIA
    # ========================================================

    df_preview = (
        st.session_state.get(
            "filtragem_preview"
        )
    )


    if df_preview is not None:

        st.divider()


        st.markdown(
            "### 👁️ Prévia da filtragem"
        )


        total_inicial = (
            st.session_state.get(
                "filtragem_total_inicial",
                len(df),
            )
        )


        total_filtrado = len(
            df_preview
        )


        c1, c2, c3 = st.columns(3)


        with c1:

            st.metric(
                "Total inicial",
                f"{total_inicial:,}".replace(
                    ",",
                    ".",
                ),
            )


        with c2:

            st.metric(
                "Após filtros",
                f"{total_filtrado:,}".replace(
                    ",",
                    ".",
                ),
            )


        with c3:

            if total_inicial:

                percentual = (
                    total_filtrado
                    /
                    total_inicial
                    *
                    100
                )

                st.metric(
                    "Percentual restante",
                    f"{percentual:.2f}%",
                )

            else:

                st.metric(
                    "Percentual restante",
                    "0%",
                )


        # ====================================================
        # ETAPAS
        # ====================================================

        etapas = (
            st.session_state.get(
                "filtragem_etapas",
                [],
            )
        )


        if etapas:

            st.markdown(
                "#### Etapas do filtro"
            )


            dados_etapas = []

            anterior = total_inicial


            for nome, quantidade in etapas:

                dados_etapas.append(
                    {
                        "Filtro": nome,
                        "Registros após filtro": quantidade,
                        "Redução": (
                            anterior
                            -
                            quantidade
                        ),
                    }
                )

                anterior = quantidade


            st.dataframe(
                pd.DataFrame(
                    dados_etapas
                ),
                use_container_width=True,
                hide_index=True,
            )


        # ====================================================
        # REGISTROS
        # ====================================================

        st.markdown(
            "#### Registros encontrados"
        )


        st.dataframe(
            df_preview.head(100),
            use_container_width=True,
            hide_index=True,
        )


        if len(df_preview) > 100:

            st.caption(
                "Exibindo os primeiros 100 de "
                f"{len(df_preview):,} registros."
            )


    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    df_resultado = (
        st.session_state.get(
            "df_resultado"
        )
    )


    if df_resultado is not None:

        st.divider()


        st.markdown(
            "### ✅ Lote gerado"
        )


        info = (
            st.session_state.get(
                "filtragem_geracao_info",
                {},
            )
        )


        c1, c2, c3, c4 = st.columns(4)


        with c1:

            st.metric(
                "Base",
                info.get(
                    "modo",
                    modo,
                ),
            )


        with c2:

            st.metric(
                "Filtrados",
                f"{info.get('total_filtrado', 0):,}".replace(
                    ",",
                    ".",
                ),
            )


        with c3:

            st.metric(
                "Incluídos no lote",
                f"{info.get('total_resultado', 0):,}".replace(
                    ",",
                    ".",
                ),
            )


        with c4:

            df_log_atual = (
                st.session_state.get(
                    "df_log"
                )
            )


            qtd_log = (
                len(df_log_atual)
                if df_log_atual is not None
                else 0
            )


            st.metric(
                "Ocorrências no LOG",
                f"{qtd_log:,}".replace(
                    ",",
                    ".",
                ),
            )


        # ====================================================
        # AVISOS
        # ====================================================

        qtd_sem_zona = info.get(
            "cidades_sem_zona",
            0,
        )


        qtd_protocolos = info.get(
            "protocolos_invalidos",
            0,
        )


        if qtd_sem_zona:

            st.warning(
                f"{qtd_sem_zona} registro(s) "
                "não incluído(s) por cidade sem zona definida."
            )


        if qtd_protocolos:

            st.warning(
                f"{qtd_protocolos} registro(s) "
                "não incluído(s) por protocolo inválido."
            )


        # ====================================================
        # CONTEÚDO DO LOTE
        # ====================================================

        st.markdown(
            "#### Conteúdo do lote"
        )


        st.dataframe(
            df_resultado.head(100),
            use_container_width=True,
            hide_index=True,
        )


        if len(df_resultado) > 100:

            st.caption(
                "Exibindo os primeiros 100 de "
                f"{len(df_resultado):,} registros."
            )


        # ====================================================
        # DOWNLOAD DO LOTE
        # ====================================================

        nome_arquivo = (
            st.session_state.get(
                "nome_arquivo_resultado",
                "Lote_Cancelamento.xlsx",
            )
        )


        excel_bytes = dataframe_para_excel(
            df_resultado,
            nome_aba="Lote",
        )


        st.download_button(
            label="⬇️ Baixar lote de cancelamento",
            data=excel_bytes,
            file_name=nome_arquivo,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key="download_lote_filtragem",
            use_container_width=True,
        )


        # ====================================================
        # LOG
        # ====================================================

        df_log = (
            st.session_state.get(
                "df_log"
            )
        )


        if (
            df_log is not None
            and
            not df_log.empty
        ):

            st.markdown(
                "#### LOG de processamento"
            )


            st.dataframe(
                df_log,
                use_container_width=True,
                hide_index=True,
            )


            log_bytes = (
                log_para_excel_filtragem(
                    df_log
                )
            )


            timestamp_log = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )


            nome_log = (
                f"LOG_Lote_Cancelamento_"
                f"{modo}_"
                f"{timestamp_log}.xlsx"
            )


            st.download_button(
                label="⬇️ Baixar LOG",
                data=log_bytes,
                file_name=nome_log,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key="download_log_filtragem",
                use_container_width=True,
            )


        else:

            st.success(
                "✓ Nenhuma ocorrência foi registrada no LOG."
            )


# ============================================================
# EXECUÇÃO DA PÁGINA
# ============================================================

render_filtragem_cancelamento()
```
