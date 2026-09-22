import re
import unicodedata
from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from auth import verificar_autenticacao
from gerador_lotes.estado import (
    inicializar_estado,
    obter_base,
    base_carregada,
    limpar_base,
    limpar_bases,
    limpar_resultado,
)
from gerador_lotes.carregamento import processar_upload_multiplo
from gerador_lotes.exportacao import dataframe_para_excel


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Gerador de Lotes - COI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .base-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 8px;
        }

        .status-ok {
            color: #16803c;
            font-weight: 600;
        }

        .status-off {
            color: #777777;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
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
# ESTADO
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
# FUNÇÕES DE NORMALIZAÇÃO
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


def obter_zona(cidade):
    cidade_normalizada = normalizar_texto(cidade)

    if not cidade_normalizada:
        return None

    return MAPA_ZONAS_NORMALIZADO.get(
        cidade_normalizada
    )


# ============================================================
# LOCALIZAÇÃO DE COLUNAS
# ============================================================

def localizar_coluna(df, tipo):
    if df is None or df.empty:
        return None

    mapa = {
        normalizar_texto(coluna): coluna
        for coluna in df.columns
    }

    if tipo == "protocolo":
        nome_exato = "COD. PROTOCOLO ORIGEM"

        if nome_exato in mapa:
            return mapa[nome_exato]

        for normalizada, original in mapa.items():
            if (
                "PROTOCOLO" in normalizada
                and "ORIGEM" in normalizada
            ):
                return original

    elif tipo == "matricula":
        if "MATRICULA" in mapa:
            return mapa["MATRICULA"]

        for normalizada, original in mapa.items():
            if "MATRICULA" in normalizada:
                return original

    elif tipo == "cidade":
        if "CIDADE" in mapa:
            return mapa["CIDADE"]

    elif tipo == "bairro":
        if "BAIRRO" in mapa:
            return mapa["BAIRRO"]

        for normalizada, original in mapa.items():
            if "BAIRRO" in normalizada:
                return original

    elif tipo == "data":
        if "DATA" in mapa:
            return mapa["DATA"]

        for normalizada, original in mapa.items():
            if normalizada.startswith("DATA "):
                return original

        for normalizada, original in mapa.items():
            if "DATA" in normalizada:
                return original

        if "INICIO DO SLA" in mapa:
            return mapa["INICIO DO SLA"]

        if "INICIO SLA" in mapa:
            return mapa["INICIO SLA"]

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

    mascara_nao_nula = serie.notna()

    if not mascara_nao_nula.any():
        return resultado

    valores = serie.loc[mascara_nao_nula]

    # --------------------------------------------------------
    # Datas já reconhecidas como datetime
    # --------------------------------------------------------

    mascara_datetime = valores.apply(
        lambda valor: isinstance(
            valor,
            (datetime, pd.Timestamp),
        )
    )

    if mascara_datetime.any():
        resultado.loc[
            valores.index[mascara_datetime]
        ] = pd.to_datetime(
            valores.loc[mascara_datetime],
            errors="coerce",
        )

    # --------------------------------------------------------
    # Números / datas Excel
    # --------------------------------------------------------

    mascara_numerico = valores.apply(
        lambda valor: (
            isinstance(valor, (int, float))
            and not isinstance(valor, bool)
        )
    )

    if mascara_numerico.any():
        numeros = pd.to_numeric(
            valores.loc[mascara_numerico],
            errors="coerce",
        )

        convertidos = pd.to_datetime(
            numeros,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )

        resultado.loc[
            convertidos.index
        ] = convertidos

    # --------------------------------------------------------
    # Textos
    # --------------------------------------------------------

    mascara_texto = ~(
        mascara_datetime
        | mascara_numerico
    )

    if mascara_texto.any():
        textos = valores.loc[
            mascara_texto
        ].astype(str).str.strip()

        formatos = [
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]

        restante = textos.copy()

        for formato in formatos:
            if restante.empty:
                break

            convertidos = pd.to_datetime(
                restante,
                format=formato,
                errors="coerce",
            )

            mascara_convertido = convertidos.notna()

            if mascara_convertido.any():
                resultado.loc[
                    convertidos.index[
                        mascara_convertido
                    ]
                ] = convertidos.loc[
                    mascara_convertido
                ]

            restante = restante.loc[
                ~mascara_convertido
            ]

        # ----------------------------------------------------
        # Última tentativa
        # ----------------------------------------------------

        if not restante.empty:
            convertidos = pd.to_datetime(
                restante,
                errors="coerce",
                dayfirst=True,
            )

            resultado.loc[
                convertidos.index
            ] = convertidos

    return resultado


# ============================================================
# CONVERSÃO DE HORÁRIO
# ============================================================

def converter_hora(valor):
    if valor is None:
        return None

    valor = str(valor).strip()

    if not valor:
        return None

    if not re.fullmatch(
        r"\d{1,2}:\d{2}",
        valor,
    ):
        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Use HH:MM."
        )

    hora, minuto = map(
        int,
        valor.split(":"),
    )

    if hora < 0 or hora > 23:
        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "A hora deve estar entre 00 e 23."
        )

    if minuto < 0 or minuto > 59:
        raise ValueError(
            f"Horário inválido: '{valor}'. "
            "Os minutos devem estar entre 00 e 59."
        )

    return time(
        hour=hora,
        minute=minuto,
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
        texto,
    )

    if not match:
        return "", "", None

    numero_str = match.group(1)
    ano_str = match.group(2)

    try:
        numero_int = int(numero_str)
    except Exception:
        return "", "", None

    return (
        numero_str,
        ano_str,
        numero_int,
    )


# ============================================================
# VALORES ÚNICOS
# ============================================================

def obter_valores_unicos(df, coluna):
    if (
        df is None
        or coluna is None
        or coluna not in df.columns
    ):
        return []

    valores = df[coluna].dropna()

    resultado = {}
    for valor in valores:
        texto = str(valor).strip()

        if not texto:
            continue

        if texto.lower() in {
            "nan",
            "none",
            "null",
        }:
            continue

        chave = normalizar_texto(texto)

        if chave not in resultado:
            resultado[chave] = texto

    return [
        resultado[chave]
        for chave in sorted(resultado.keys())
    ]


# ============================================================
# FILTROS
# ============================================================

def obter_modo_atual():
    modo = st.session_state.get(
        "modo_operacao",
        "API",
    )

    if modo not in {"API", "THE"}:
        modo = "API"

    return modo


def obter_backlog_filtragem(modo):
    if modo == "THE":
        return obter_base("the")

    return obter_base("api")


def aplicar_filtros_filtragem(
    df,
    coluna_cidade,
    coluna_bairro,
    coluna_data,
    cidades,
    bairros,
    ano,
    meses,
    dias,
    hora_inicial,
    hora_final,
):
    if df is None or df.empty:
        return df

    resultado = df.copy()

    # --------------------------------------------------------
    # CIDADE
    # --------------------------------------------------------

    if cidades and coluna_cidade:
        cidades_normalizadas = {
            normalizar_texto(valor)
            for valor in cidades
        }

        resultado = resultado[
            resultado[coluna_cidade].apply(
                normalizar_texto
            ).isin(cidades_normalizadas)
        ]

    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    if bairros and coluna_bairro:
        bairros_normalizados = {
            normalizar_texto(valor)
            for valor in bairros
        }

        resultado = resultado[
            resultado[coluna_bairro].apply(
                normalizar_texto
            ).isin(bairros_normalizados)
        ]

    # --------------------------------------------------------
    # DATA / HORA
    # --------------------------------------------------------

    existe_filtro_temporal = (
        ano is not None
        or bool(meses)
        or bool(dias)
        or hora_inicial is not None
        or hora_final is not None
    )

    if existe_filtro_temporal:
        if not coluna_data:
            raise ValueError(
                "Não foi encontrada uma coluna de data "
                "para aplicar os filtros temporais."
            )

        datas = converter_datas_robusto(
            resultado[coluna_data]
        )

        if ano is not None:
            resultado = resultado[
                datas.dt.year == ano
            ]

            datas = datas.loc[
                resultado.index
            ]

        if meses:
            resultado = resultado[
                datas.dt.month.isin(meses)
            ]

            datas = datas.loc[
                resultado.index
            ]

        if dias:
            resultado = resultado[
                datas.dt.day.isin(dias)
            ]

            datas = datas.loc[
                resultado.index
            ]

        if (
            hora_inicial is not None
            or hora_final is not None
        ):
            horas = datas.dt.time

            if (
                hora_inicial is not None
                and hora_final is not None
            ):
                if hora_inicial <= hora_final:
                    mascara_hora = (
                        (horas >= hora_inicial)
                        & (horas <= hora_final)
                    )
                else:
                    mascara_hora = (
                        (horas >= hora_inicial)
                        | (horas <= hora_final)
                    )

            elif hora_inicial is not None:
                mascara_hora = (
                    horas >= hora_inicial
                )

            else:
                mascara_hora = (
                    horas <= hora_final
                )

            resultado = resultado[
                mascara_hora
            ]

    return resultado.reset_index(drop=True)


# ============================================================
# GERAÇÃO DO LOTE
# ============================================================

def gerar_lote_filtragem(
    df_filtrado,
    modo,
    coluna_protocolo,
    coluna_matricula,
    coluna_cidade,
):
    if df_filtrado is None or df_filtrado.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    registros = []
    logs = []

    for _, linha in df_filtrado.iterrows():

        protocolo_original = (
            linha.get(coluna_protocolo)
            if coluna_protocolo
            else None
        )

        matricula = (
            linha.get(coluna_matricula)
            if coluna_matricula
            else ""
        )

        cidade = (
            linha.get(coluna_cidade)
            if coluna_cidade
            else ""
        )

        cidade_texto = (
            ""
            if pd.isna(cidade)
            else str(cidade).strip()
        )

        numero_str, ano_str, numero_int = (
            parse_protocolo(
                protocolo_original
            )
        )

        if numero_int is None:
            logs.append(
                {
                    "Tipo": "ERRO",
                    "Matrícula": matricula,
                    "Protocolo": protocolo_original,
                    "Cidade": cidade_texto,
                    "Motivo": "Protocolo inválido ou não localizado.",
                }
            )

            continue

        if modo == "THE":
            zona = 1
        else:
            zona = obter_zona(cidade_texto)

            if zona is None:
                logs.append(
                    {
                        "Tipo": "ERRO",
                        "Matrícula": matricula,
                        "Protocolo": protocolo_original,
                        "Cidade": cidade_texto,
                        "Motivo": "Cidade sem zona definida.",
                    }
                )

                continue

        registros.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_int,
                "Ano Do Pedido": ano_str,
                "Tipo Encerramento": "CANCELAMENTO",
                "Observações": "",
            }
        )

    resultado = pd.DataFrame(
        registros,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações",
        ],
    )

    log = pd.DataFrame(
        logs,
        columns=[
            "Tipo",
            "Matrícula",
            "Protocolo",
            "Cidade",
            "Motivo",
        ],
    )

    return resultado, log


# ============================================================
# DEFINIÇÃO DAS BASES
# ============================================================

CONFIG_BASES = {
    "api": {
        "titulo": "🔵 API",
        "descricao": "Backlog de ordens API",
    },
    "the": {
        "titulo": "🟢 THE",
        "descricao": "Backlog de ordens THE",
    },
    "servicos_api": {
        "titulo": "🟣 Serviços API",
        "descricao": "Base de serviços API",
    },
    "servicos_the": {
        "titulo": "🟠 Serviços THE",
        "descricao": "Base de serviços THE",
    },
    "eventos": {
        "titulo": "🟡 Eventos",
        "descricao": "Base de eventos",
    },
    "lotes": {
        "titulo": "🔴 Lotes",
        "descricao": "Base de lotes",
    },
}


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("### 📦 Gerador de Lotes")

    st.caption(
        f"Usuário: **{st.session_state.get('usuario_logado', '')}**"
    )

    st.caption(
        f"Perfil: **{st.session_state.get('perfil', '').upper()}**"
    )

    st.divider()

    if st.button(
        "🛠️ Voltar às Ferramentas",
        use_container_width=True,
    ):
        st.switch_page(
            "pages/4_Ferramentas_Operacionais.py"
        )

    if st.button(
        "🏠 Menu Principal",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.divider()

    if st.button(
        "🗑️ Limpar todas as bases",
        use_container_width=True,
    ):
        limpar_bases()
        st.rerun()


# ============================================================
# CABEÇALHO
# ============================================================

st.title("📦 Gerador de Lotes")
st.caption(
    "Hub de carregamento das bases e geração de lotes operacionais."
)


# ============================================================
# CARREGAMENTO DAS BASES
# ============================================================

st.subheader("📥 Carregamento das Bases")

st.info(
    "As seis bases são carregadas neste Hub. "
    "Você pode enviar apenas um arquivo ou vários arquivos "
    "para cada base. A consolidação é automática."
)


bases_lista = list(CONFIG_BASES.keys())

for inicio in range(0, len(bases_lista), 2):
    linha_bases = bases_lista[
        inicio:inicio + 2
    ]

    colunas = st.columns(2)

    for coluna, nome_base in zip(
        colunas,
        linha_bases,
    ):
        config = CONFIG_BASES[nome_base]

        with coluna:
            st.markdown(
                f"#### {config['titulo']}"
            )

            st.caption(
                config["descricao"]
            )

            versao_upload = st.session_state.get(
                f"versao_upload_{nome_base}",
                0,
            )

            arquivos = st.file_uploader(
                "Selecione arquivo(s) Excel",
                type=["xlsx", "xlsm"],
                accept_multiple_files=True,
                key=(
                    f"upload_{nome_base}_"
                    f"{versao_upload}"
                ),
            )

            if arquivos:
                try:
                    processar_upload_multiplo(
                        nome_base,
                        arquivos,
                    )
                except Exception as erro:
                    st.error(
                        f"Erro ao carregar a base "
                        f"{config['titulo']}: {erro}"
                    )

            if base_carregada(nome_base):
                df_base = obter_base(nome_base)
                arquivos_base = st.session_state.get(
                    f"arquivos_{nome_base}",
                    [],
                )

                st.markdown(
                    '<span class="status-ok">● Base carregada</span>',
                    unsafe_allow_html=True,
                )

                metrica1, metrica2 = st.columns(2)

                with metrica1:
                    st.metric(
                        "Registros",
                        f"{len(df_base):,}".replace(
                            ",", "."
                        ),
                    )

                with metrica2:
                    st.metric(
                        "Colunas",
                        len(df_base.columns),
                    )

                if arquivos_base:
                    st.caption(
                        "Arquivo(s): "
                        + ", ".join(arquivos_base)
                    )

                if st.button(
                    "Limpar esta base",
                    key=f"limpar_base_{nome_base}",
                    use_container_width=True,
                ):
                    limpar_base(nome_base)
                    limpar_resultado()
                    st.rerun()

            else:
                st.markdown(
                    '<span class="status-off">● Não carregada</span>',
                    unsafe_allow_html=True,
                )


# ============================================================
# STATUS GERAL
# ============================================================

st.divider()

quantidade_bases = sum(
    base_carregada(base)
    for base in CONFIG_BASES
)

col_status1, col_status2 = st.columns(2)

with col_status1:
    st.metric(
        "Bases carregadas",
        f"{quantidade_bases} / 6",
    )

with col_status2:
    modo_status = obter_modo_atual()

    st.metric(
        "Modo de operação",
        modo_status,
    )


# ============================================================
# FILTRAGEM / CANCELAMENTO
# ============================================================

st.divider()

st.subheader("🔎 Filtragem / Cancelamento")

modo_anterior = st.session_state.get(
    "modo_operacao",
    "API",
)

modo = st.radio(
    "Base para operação",
    options=["API", "THE"],
    horizontal=True,
    key="modo_operacao",
)

if modo != modo_anterior:
    limpar_resultado()


df_backlog = obter_backlog_filtragem(modo)


if df_backlog is None or df_backlog.empty:
    st.warning(
        f"A base **{modo}** ainda não foi carregada. "
        "Carregue a base acima para utilizar a filtragem."
    )

    st.stop()


# ============================================================
# COLUNAS
# ============================================================

coluna_protocolo = localizar_coluna(
    df_backlog,
    "protocolo",
)

coluna_matricula = localizar_coluna(
    df_backlog,
    "matricula",
)

coluna_cidade = localizar_coluna(
    df_backlog,
    "cidade",
)

coluna_bairro = localizar_coluna(
    df_backlog,
    "bairro",
)

coluna_data = localizar_coluna(
    df_backlog,
    "data",
)


with st.expander(
    "🔍 Colunas identificadas",
    expanded=False,
):
    info_colunas = pd.DataFrame(
        {
            "Campo": [
                "Protocolo",
                "Matrícula",
                "Cidade",
                "Bairro",
                "Data",
            ],
            "Coluna encontrada": [
                coluna_protocolo or "Não encontrada",
                coluna_matricula or "Não encontrada",
                coluna_cidade or "Não encontrada",
                coluna_bairro or "Não encontrada",
                coluna_data or "Não encontrada",
            ],
        }
    )

    st.dataframe(
        info_colunas,
        hide_index=True,
        use_container_width=True,
    )


# ============================================================
# FILTROS DE CIDADE E BAIRRO
# ============================================================

cidades_disponiveis = (
    obter_valores_unicos(
        df_backlog,
        coluna_cidade,
    )
    if coluna_cidade
    else []
)

bairros_disponiveis = (
    obter_valores_unicos(
        df_backlog,
        coluna_bairro,
    )
    if coluna_bairro
    else []
)


col1, col2 = st.columns(2)

with col1:
    filtro_cidades = st.multiselect(
        "🏙️ Cidade",
        options=cidades_disponiveis,
        key="ui_filtro_cidades",
    )

with col2:
    filtro_bairros = st.multiselect(
        "🏘️ Bairro",
        options=bairros_disponiveis,
        key="ui_filtro_bairros",
    )


# ============================================================
# FILTROS TEMPORAIS
# ============================================================

anos_disponiveis = []
meses_disponiveis = []
dias_disponiveis = []

datas_backlog = None

if coluna_data:
    datas_backlog = converter_datas_robusto(
        df_backlog[coluna_data]
    )

    anos_disponiveis = sorted(
        datas_backlog.dropna()
        .dt.year
        .unique()
        .tolist()
    )

    meses_disponiveis = list(
        range(1, 13)
    )

    dias_disponiveis = list(
        range(1, 32)
    )


col3, col4, col5 = st.columns(3)

with col3:
    filtro_ano = st.selectbox(
        "📅 Ano",
        options=["Todos"] + anos_disponiveis,
        key="ui_filtro_ano",
    )

with col4:
    filtro_meses = st.multiselect(
        "🗓️ Mês",
        options=meses_disponiveis,
        key="ui_filtro_meses",
    )

with col5:
    filtro_dias = st.multiselect(
        "📆 Dia",
        options=dias_disponiveis,
        key="ui_filtro_dias",
    )


# ============================================================
# HORÁRIOS
# ============================================================

col6, col7 = st.columns(2)

with col6:
    hora_inicial_texto = st.text_input(
        "🕐 Hora Inicial",
        placeholder="HH:MM",
        key="ui_hora_inicial",
    )

with col7:
    hora_final_texto = st.text_input(
        "🕐 Hora Final",
        placeholder="HH:MM",
        key="ui_hora_final",
    )


hora_inicial = None
hora_final = None


try:
    if hora_inicial_texto.strip():
        hora_inicial = converter_hora(
            hora_inicial_texto
        )

    if hora_final_texto.strip():
        hora_final = converter_hora(
            hora_final_texto
        )

except ValueError as erro:
    st.error(str(erro))
    st.stop()


# ============================================================
# OBSERVAÇÃO
# ============================================================

observacao_filtro = st.text_input(
    "📝 Observação",
    placeholder="Filtro opcional por texto...",
    key="ui_filtro_observacao",
)


# ============================================================
# APLICAÇÃO DOS FILTROS
# ============================================================

filtro_ano_valor = (
    None
    if filtro_ano == "Todos"
    else filtro_ano
)

try:
    df_filtrado = aplicar_filtros_filtragem(
        df=df_backlog,
        coluna_cidade=coluna_cidade,
        coluna_bairro=coluna_bairro,
        coluna_data=coluna_data,
        cidades=filtro_cidades,
        bairros=filtro_bairros,
        ano=filtro_ano_valor,
        meses=filtro_meses,
        dias=filtro_dias,
        hora_inicial=hora_inicial,
        hora_final=hora_final,
    )

except ValueError as erro:
    st.error(str(erro))
    st.stop()


# ============================================================
# FILTRO DE OBSERVAÇÃO
# ============================================================

if (
    observacao_filtro
    and observacao_filtro.strip()
):
    termo = normalizar_texto(
        observacao_filtro
    )

    mascara_observacao = (
        df_filtrado.astype(str)
        .apply(
            lambda coluna: coluna.apply(
                lambda valor: termo
                in normalizar_texto(valor)
            )
        )
        .any(axis=1)
    )

    df_filtrado = df_filtrado[
        mascara_observacao
    ].reset_index(drop=True)


# ============================================================
# RESUMO DA FILTRAGEM
# ============================================================

st.divider()

resumo1, resumo2, resumo3 = st.columns(3)

with resumo1:
    st.metric(
        "Registros na base",
        f"{len(df_backlog):,}".replace(
            ",", "."
        ),
    )

with resumo2:
    st.metric(
        "Registros filtrados",
        f"{len(df_filtrado):,}".replace(
            ",", "."
        ),
    )

with resumo3:
    if len(df_backlog) > 0:
        percentual = (
            len(df_filtrado)
            / len(df_backlog)
            * 100
        )
    else:
        percentual = 0

    st.metric(
        "Percentual",
        f"{percentual:.1f}%",
    )


# ============================================================
# PRÉVIA
# ============================================================

st.subheader("👁️ Prévia")

quantidade_previa = min(
    100,
    len(df_filtrado),
)

if quantidade_previa > 0:
    st.caption(
        f"Exibindo os primeiros "
        f"{quantidade_previa} registros."
    )

    st.dataframe(
        df_filtrado.head(100),
        hide_index=True,
        use_container_width=True,
    )

else:
    st.info(
        "Nenhum registro encontrado com os filtros atuais."
    )


# ============================================================
# AÇÕES
# ============================================================

st.divider()

acao1, acao2 = st.columns(2)


with acao1:
    gerar = st.button(
        "📦 Gerar Lote de Cancelamento",
        type="primary",
        use_container_width=True,
        disabled=df_filtrado.empty,
    )


with acao2:
    limpar = st.button(
        "🧹 Limpar Resultado",
        use_container_width=True,
    )


if limpar:
    limpar_resultado()
    st.rerun()


# ============================================================
# GERAÇÃO
# ============================================================

if gerar:

    if not coluna_protocolo:
        st.error(
            "A coluna de protocolo não foi encontrada na base."
        )
        st.stop()

    if not coluna_matricula:
        st.error(
            "A coluna de matrícula não foi encontrada na base."
        )
        st.stop()

    if not coluna_cidade:
        st.error(
            "A coluna de cidade não foi encontrada na base."
        )
        st.stop()

    with st.spinner(
        "Gerando lote de cancelamento..."
    ):
        resultado, log = gerar_lote_filtragem(
            df_filtrado=df_filtrado,
            modo=modo,
            coluna_protocolo=coluna_protocolo,
            coluna_matricula=coluna_matricula,
            coluna_cidade=coluna_cidade,
        )

    st.session_state.df_resultado = resultado
    st.session_state.df_log = log

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    st.session_state.nome_arquivo_resultado = (
        f"Lote_Cancelamento_{modo}_"
        f"{timestamp}.xlsx"
    )

    st.rerun()


# ============================================================
# RESULTADO
# ============================================================

df_resultado = st.session_state.get(
    "df_resultado"
)

df_log = st.session_state.get(
    "df_log"
)

nome_arquivo_resultado = st.session_state.get(
    "nome_arquivo_resultado"
)


if df_resultado is not None:

    st.divider()

    st.subheader("📦 Lote Gerado")

    resultado_col1, resultado_col2 = st.columns(2)

    with resultado_col1:
        st.metric(
            "Registros gerados",
            f"{len(df_resultado):,}".replace(
                ",", "."
            ),
        )

    with resultado_col2:
        quantidade_erros = (
            len(df_log)
            if df_log is not None
            else 0
        )

        st.metric(
            "Ocorrências no LOG",
            f"{quantidade_erros:,}".replace(
                ",", "."
            ),
        )

    if df_resultado.empty:
        st.warning(
            "Nenhum lote foi gerado. "
            "Verifique o LOG abaixo."
        )

    else:
        st.dataframe(
            df_resultado,
            hide_index=True,
            use_container_width=True,
        )

        arquivo_resultado = dataframe_para_excel(
            df_resultado,
            nome_aba="Lote",
        )

        if arquivo_resultado:
            st.download_button(
                label="⬇️ Baixar Lote de Cancelamento",
                data=arquivo_resultado,
                file_name=nome_arquivo_resultado,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                type="primary",
                use_container_width=True,
            )


# ============================================================
# LOG
# ============================================================

if df_log is not None:

    st.divider()

    st.subheader("📋 LOG")

    if df_log.empty:
        st.success(
            "Nenhuma ocorrência foi registrada no LOG."
        )

    else:
        st.dataframe(
            df_log,
            hide_index=True,
            use_container_width=True,
        )

        arquivo_log = dataframe_para_excel(
            df_log,
            nome_aba="LOG",
        )

        if arquivo_log:
            timestamp_log = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            st.download_button(
                label="⬇️ Baixar LOG",
                data=arquivo_log,
                file_name=(
                    f"LOG_Cancelamento_{modo}_"
                    f"{timestamp_log}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
            )
