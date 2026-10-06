import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado
from ..exportacao import dataframe_para_excel
from ..zonas import obter_zona
from .componentes import selecionar_modo_api_the


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_ARQUIVO_API = "Eventos API.xlsx"
NOME_ARQUIVO_THE = "Eventos THE.xlsx"

TIPO_ENCERRAMENTO = 6

COLUNAS_LOTE = [
    "Quant. de O.S",
    "Cidade",
    "Bairro",
    "Ano",
    "Mês",
    "Dia",
    "Hora Inicial",
    "Hora Final",
    "Observação",
]


# ============================================================
# VISUAL
# ============================================================

def aplicar_modo_visual():
    st.markdown(
        """
        <style>
        .bloco-regra {
            background-color: rgba(128,128,128,0.08);
            border-radius: 8px;
            padding: 12px 16px;
            margin: 8px 0 16px 0;
        }

        .titulo-secao {
            font-size: 1.15rem;
            font-weight: 600;
            margin-top: 10px;
            margin-bottom: 8px;
        }

        .resultado-ok {
            padding: 10px 14px;
            border-radius: 8px;
            background-color: rgba(0, 180, 80, 0.10);
            margin-bottom: 10px;
        }

        .resultado-vazio {
            padding: 10px 14px;
            border-radius: 8px;
            background-color: rgba(255, 170, 0, 0.10);
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(valor) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(r"[^A-Z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def normalizar_nome_coluna(valor) -> str:
    return normalizar_texto(valor)


def encontrar_coluna(df: pd.DataFrame, possibilidades):
    mapa = {
        normalizar_nome_coluna(coluna): coluna
        for coluna in df.columns
    }

    for possibilidade in possibilidades:
        chave = normalizar_nome_coluna(possibilidade)

        if chave in mapa:
            return mapa[chave]

    return None


# ============================================================
# DATAS
# ============================================================

def parse_data_hora(valor):
    if valor is None:
        return pd.NaT

    if isinstance(valor, pd.Timestamp):
        return valor

    if isinstance(valor, datetime):
        return pd.Timestamp(valor)

    try:
        if pd.isna(valor):
            return pd.NaT
    except Exception:
        pass

    texto = str(valor).strip()

    if not texto:
        return pd.NaT

    texto = re.sub(
        r"(\d{1,2}:\d{2})\s*h$",
        r"\1",
        texto,
        flags=re.IGNORECASE,
    )

    try:
        return pd.to_datetime(
            texto,
            format="%d/%m/%Y %H:%M",
            errors="coerce",
        )
    except Exception:
        pass

    try:
        return pd.to_datetime(
            texto,
            dayfirst=True,
            errors="coerce",
        )
    except Exception:
        return pd.NaT


def parse_coluna_data(serie: pd.Series) -> pd.Series:
    return serie.apply(parse_data_hora)


# ============================================================
# PROTOCOLO / MATRÍCULA
# ============================================================

def parse_protocolo(valor) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def normalizar_matricula(valor) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    texto = re.sub(r"\D", "", texto)

    return texto


# ============================================================
# ÁREAS
# ============================================================

PADROES_MUNICIPIO_INTEIRO = {
    "TODA A CIDADE",
    "TODOS OS BAIRROS",
    "MUNICIPIO INTEIRO",
    "MUNICIPIO TODO",
    "CIDADE INTEIRA",
    "TODA CIDADE",
    "TODOS BAIRROS",
}


def normalizar_nome_area_com_qualificadores(valor):
    texto = normalizar_texto(valor)

    if not texto:
        return ""

    qualificadores = {
        "PARCIAL",
        "PARCIALMENTE",
        "TOTAL",
        "INTEGRAL",
        "PARTE",
    }

    tokens = texto.split()

    while tokens and tokens[-1] in qualificadores:
        tokens.pop()

    return " ".join(tokens).strip()


def tokenizar_area(valor):
    texto = normalizar_nome_area_com_qualificadores(valor)

    if not texto:
        return set()

    return {
        token
        for token in texto.split()
        if token
    }


def separar_areas_impactadas(valor):
    if valor is None:
        return []

    try:
        if pd.isna(valor):
            return []
    except Exception:
        pass

    texto_original = str(valor).strip()

    if not texto_original:
        return []

    texto_normalizado = normalizar_texto(texto_original)

    if texto_normalizado in PADROES_MUNICIPIO_INTEIRO:
        return [texto_normalizado]

    texto = texto_original

    texto = re.sub(r"[;|/\\&]+", ",", texto)
    texto = re.sub(
        r"\s+\bE\b\s+",
        ",",
        texto,
        flags=re.IGNORECASE,
    )
    texto = texto.replace("\n", ",")

    partes = [
        parte.strip()
        for parte in texto.split(",")
        if parte.strip()
    ]

    resultado = []

    for parte in partes:
        normalizado = normalizar_texto(parte)

        if normalizado:
            resultado.append(normalizado)

    return resultado


SINONIMOS_AREAS = {
    "CENTRO": {
        "CENTRO",
    },
    "SAO JOSE": {
        "SAO JOSE",
        "SAO JOSE I",
        "SAO JOSE II",
    },
}


def areas_evento_correspondem(area_evento, bairro_os) -> bool:
    if not area_evento or not bairro_os:
        return False

    area = normalizar_nome_area_com_qualificadores(area_evento)
    bairro = normalizar_nome_area_com_qualificadores(bairro_os)

    if not area or not bairro:
        return False

    if area == bairro:
        return True

    for grupo, sinonimos in SINONIMOS_AREAS.items():

        grupo_normalizado = normalizar_texto(grupo)

        equivalentes = {
            grupo_normalizado,
            *{
                normalizar_texto(sinonimo)
                for sinonimo in sinonimos
                if normalizar_texto(sinonimo)
            },
        }

        if area in equivalentes and bairro in equivalentes:
            return True

    tokens_area = tokenizar_area(area)
    tokens_bairro = tokenizar_area(bairro)

    if tokens_area and tokens_bairro:
        if tokens_area == tokens_bairro:
            return True

    return False


# ============================================================
# IDENTIFICAÇÃO DE MUNICÍPIO INTEIRO
# ============================================================

def evento_afeta_municipio_inteiro(areas):
    if not areas:
        return False

    for area in areas:
        normalizado = normalizar_texto(area)

        if normalizado in PADROES_MUNICIPIO_INTEIRO:
            return True

    return False


# ============================================================
# PREPARAÇÃO DOS EVENTOS
# ============================================================

def preparar_eventos(df_eventos: pd.DataFrame):
    df = df_eventos.copy()

    coluna_cidade = encontrar_coluna(
        df,
        [
            "Cidade",
            "Município",
            "Municipio",
        ],
    )

    coluna_area = encontrar_coluna(
        df,
        [
            "Áreas Impactadas",
            "Areas Impactadas",
            "Área Impactada",
            "Area Impactada",
        ],
    )

    coluna_inicio = encontrar_coluna(
        df,
        [
            "Início",
            "Inicio",
            "Início do Evento",
            "Inicio do Evento",
            "Data de Início",
            "Data Inicio",
        ],
    )

    coluna_termino_real = encontrar_coluna(
        df,
        [
            "Término Real",
            "Termino Real",
            "Término real",
            "Termino real",
            "Data de Término Real",
            "Data Termino Real",
            "Finalização",
            "Finalizacao",
        ],
    )

    coluna_previsao_termino = encontrar_coluna(
        df,
        [
            "Previsão de Término",
            "Previsao de Termino",
            "Previsão Término",
            "Previsao Termino",
            "Prev. Término",
            "Prev Término",
            "Previsão de termino",
            "Previsao de termino",
        ],
    )

    coluna_descricao = encontrar_coluna(
        df,
        [
            "Descrição",
            "Descricao",
            "Descrição do Evento",
            "Descricao do Evento",
        ],
    )

    colunas_obrigatorias = {
        "Cidade": coluna_cidade,
        "Áreas Impactadas": coluna_area,
        "Início": coluna_inicio,
    }

    faltantes = [
        nome
        for nome, coluna in colunas_obrigatorias.items()
        if coluna is None
    ]

    if faltantes:
        raise ValueError(
            "Não foi possível localizar as seguintes colunas "
            f"obrigatórias no arquivo de eventos: {', '.join(faltantes)}"
        )

    if (
        coluna_termino_real is None
        and coluna_previsao_termino is None
    ):
        raise ValueError(
            "Não foi encontrada nenhuma coluna de término do evento. "
            "É necessário possuir 'Término Real' ou "
            "'Previsão de Término'."
        )

    # --------------------------------------------------------
    # Cidade
    # --------------------------------------------------------

    df["cidade"] = df[coluna_cidade].apply(
        normalizar_texto
    )

    # --------------------------------------------------------
    # Áreas
    # --------------------------------------------------------

    df["areas_original"] = df[coluna_area].apply(
        lambda valor: (
            ""
            if pd.isna(valor)
            else str(valor).strip()
        )
    )

    df["areas_lista"] = df["areas_original"].apply(
        separar_areas_impactadas
    )

    df["areas"] = df["areas_lista"].apply(
        lambda lista: ", ".join(lista)
    )

    # --------------------------------------------------------
    # Início do evento
    # --------------------------------------------------------

    df["inicio"] = parse_coluna_data(
        df[coluna_inicio]
    )

    # Início da janela = início do evento - 1 hora
    df["inicio_janela"] = (
        df["inicio"]
        - pd.Timedelta(hours=1)
    )

    # --------------------------------------------------------
    # Término Real
    # --------------------------------------------------------

    if coluna_termino_real is not None:
        df["termino_real"] = parse_coluna_data(
            df[coluna_termino_real]
        )
    else:
        df["termino_real"] = pd.NaT

    # --------------------------------------------------------
    # Previsão de Término
    # --------------------------------------------------------

    if coluna_previsao_termino is not None:
        df["previsao_termino"] = parse_coluna_data(
            df[coluna_previsao_termino]
        )
    else:
        df["previsao_termino"] = pd.NaT

    # --------------------------------------------------------
    # Término de referência
    #
    # Prioridade:
    # 1. Término Real
    # 2. Previsão de Término
    #
    # combine_first também trata corretamente casos em que
    # a coluna existe, mas o registro específico está vazio.
    # --------------------------------------------------------

    df["termino_referencia"] = (
        df["termino_real"].combine_first(
            df["previsao_termino"]
        )
    )

    # --------------------------------------------------------
    # Fim efetivo = término de referência + 3 horas
    # --------------------------------------------------------

    df["fim_efetivo"] = (
        df["termino_referencia"]
        + pd.Timedelta(hours=3)
    )

    # --------------------------------------------------------
    # Descrição
    # --------------------------------------------------------

    if coluna_descricao is not None:
        df["descricao"] = df[coluna_descricao].apply(
            lambda valor: (
                ""
                if pd.isna(valor)
                else str(valor).strip()
            )
        )
    else:
        df["descricao"] = ""

    # --------------------------------------------------------
    # Validação
    # --------------------------------------------------------

    df = df[
        df["cidade"].ne("")
        & df["inicio"].notna()
        & df["termino_referencia"].notna()
    ].copy()

    return df


# ============================================================
# CRUZAMENTO EVENTO x BACKLOG
# ============================================================

def cruzar_eventos_com_backlog(
    df_eventos: pd.DataFrame,
    df_backlog: pd.DataFrame,
):
    df_os = df_backlog.copy()

    # --------------------------------------------------------
    # Localização das colunas
    # --------------------------------------------------------

    coluna_cidade = encontrar_coluna(
        df_os,
        [
            "CIDADE",
            "Cidade",
            "Município",
            "Municipio",
        ],
    )

    coluna_bairro = encontrar_coluna(
        df_os,
        [
            "BAIRRO",
            "Bairro",
        ],
    )

    coluna_inicio_sla = encontrar_coluna(
        df_os,
        [
            "INÍCIO DO SLA",
            "INICIO DO SLA",
            "Início do SLA",
            "Inicio do SLA",
        ],
    )

    coluna_protocolo = encontrar_coluna(
        df_os,
        [
            "COD. PROTOCOLO ORIGEM",
            "COD PROTOCOLO ORIGEM",
            "Código do Protocolo Origem",
            "Codigo do Protocolo Origem",
        ],
    )

    coluna_matricula = encontrar_coluna(
        df_os,
        [
            "MATRICULA",
            "Matrícula",
            "Matricula",
        ],
    )

    if coluna_cidade is None:
        raise ValueError(
            "Não foi encontrada a coluna de cidade no backlog de O.S."
        )

    if coluna_bairro is None:
        raise ValueError(
            "Não foi encontrada a coluna de bairro no backlog de O.S."
        )

    if coluna_inicio_sla is None:
        raise ValueError(
            "Não foi encontrada a coluna 'Início do SLA' no backlog."
        )

    if coluna_protocolo is None:
        raise ValueError(
            "Não foi encontrada a coluna de protocolo no backlog."
        )

    if coluna_matricula is None:
        raise ValueError(
            "Não foi encontrada a coluna de matrícula no backlog."
        )

    # --------------------------------------------------------
    # Normalização do backlog
    # --------------------------------------------------------

    df_os["cidade_normalizada"] = df_os[
        coluna_cidade
    ].apply(normalizar_texto)

    df_os["bairro_normalizado"] = df_os[
        coluna_bairro
    ].apply(normalizar_texto)

    df_os["inicio_sla"] = parse_coluna_data(
        df_os[coluna_inicio_sla]
    )

    df_os["matricula_normalizada"] = df_os[
        coluna_matricula
    ].apply(normalizar_matricula)

    df_os["protocolo_normalizado"] = df_os[
        coluna_protocolo
    ].apply(parse_protocolo)

    df_os["chave_os"] = (
        df_os["matricula_normalizada"]
        + "|"
        + df_os["protocolo_normalizado"]
    )

    df_os = df_os[
        df_os["cidade_normalizada"].ne("")
        & df_os["inicio_sla"].notna()
    ].copy()

    resultados = []

    # ========================================================
    # PROCESSA CADA EVENTO
    # ========================================================

    for indice_evento, evento in df_eventos.iterrows():

        cidade_evento = normalizar_texto(
            evento["cidade"]
        )

        inicio_janela = evento["inicio_janela"]
        fim_efetivo = evento["fim_efetivo"]

        areas_evento = evento["areas_lista"]

        if not cidade_evento:
            continue

        if pd.isna(inicio_janela):
            continue

        if pd.isna(fim_efetivo):
            continue

        # ----------------------------------------------------
        # Filtra cidade
        # ----------------------------------------------------

        candidatos = df_os[
            df_os["cidade_normalizada"]
            == cidade_evento
        ].copy()

        if candidatos.empty:
            continue

        # ----------------------------------------------------
        # Filtra período
        #
        # Início do evento - 1h
        #
        # até
        #
        # Término Real + 3h
        #
        # ou Previsão de Término + 3h
        # ----------------------------------------------------

        candidatos = candidatos[
            (candidatos["inicio_sla"] >= inicio_janela)
            & (
                candidatos["inicio_sla"]
                <= fim_efetivo
            )
        ].copy()

        if candidatos.empty:
            continue

        # ----------------------------------------------------
        # Município inteiro
        # ----------------------------------------------------

        municipio_inteiro = (
            evento_afeta_municipio_inteiro(
                areas_evento
            )
        )

        # ----------------------------------------------------
        # Cruzamento por área
        # ----------------------------------------------------

        if municipio_inteiro:

            candidatos_filtrados = candidatos.copy()

        else:

            if not areas_evento:
                continue

            mascara_area = candidatos[
                "bairro_normalizado"
            ].apply(
                lambda bairro: any(
                    areas_evento_correspondem(
                        area_evento,
                        bairro,
                    )
                    for area_evento in areas_evento
                )
            )

            candidatos_filtrados = candidatos[
                mascara_area
            ].copy()

        if candidatos_filtrados.empty:
            continue

        # ----------------------------------------------------
        # Evita contar a mesma O.S. duas vezes
        # ----------------------------------------------------

        candidatos_filtrados = (
            candidatos_filtrados
            .drop_duplicates(
                subset=["chave_os"]
            )
            .copy()
        )

        quantidade = len(
            candidatos_filtrados
        )

        if quantidade <= 0:
            continue

        # ----------------------------------------------------
        # Informações para o lote
        # ----------------------------------------------------

        inicio_evento = evento["inicio"]
        termino_referencia = (
            evento["termino_referencia"]
        )

        if pd.isna(inicio_evento):
            continue

        if pd.isna(termino_referencia):
            continue

        cidade_original = evento["cidade"]

        # ----------------------------------------------------
        # Município inteiro
        # ----------------------------------------------------

        if municipio_inteiro:

            resultados.append(
                {
                    "Quant. de O.S": quantidade,
                    "Cidade": cidade_original,
                    "Bairro": "TODOS OS BAIRROS",
                    "Ano": inicio_evento.year,
                    "Mês": inicio_evento.month,
                    "Dia": inicio_evento.day,
                    "Hora Inicial": inicio_evento.strftime(
                        "%H:%M"
                    ),
                    "Hora Final": termino_referencia.strftime(
                        "%H:%M"
                    ),
                    "Observação": (
                        f"Evento: "
                        f"{evento['areas_original']} | "
                        f"Janela: "
                        f"{inicio_janela.strftime('%d/%m/%Y %H:%M')} "
                        f"até "
                        f"{fim_efetivo.strftime('%d/%m/%Y %H:%M')}"
                    ),
                }
            )

        # ----------------------------------------------------
        # Áreas específicas
        # ----------------------------------------------------

        else:

            for area_evento in areas_evento:

                mascara_area = candidatos_filtrados[
                    "bairro_normalizado"
                ].apply(
                    lambda bairro: (
                        areas_evento_correspondem(
                            area_evento,
                            bairro,
                        )
                    )
                )

                quantidade_area = int(
                    mascara_area.sum()
                )

                if quantidade_area <= 0:
                    continue

                resultados.append(
                    {
                        "Quant. de O.S": quantidade_area,
                        "Cidade": cidade_original,
                        "Bairro": (
                            normalizar_nome_area_com_qualificadores(
                                area_evento
                            )
                        ),
                        "Ano": inicio_evento.year,
                        "Mês": inicio_evento.month,
                        "Dia": inicio_evento.day,
                        "Hora Inicial": inicio_evento.strftime(
                            "%H:%M"
                        ),
                        "Hora Final": termino_referencia.strftime(
                            "%H:%M"
                        ),
                        "Observação": (
                            f"Evento: "
                            f"{evento['areas_original']} | "
                            f"Janela: "
                            f"{inicio_janela.strftime('%d/%m/%Y %H:%M')} "
                            f"até "
                            f"{fim_efetivo.strftime('%d/%m/%Y %H:%M')}"
                        ),
                    }
                )

    if not resultados:
        return pd.DataFrame(
            columns=COLUNAS_LOTE
        )

    resultado = pd.DataFrame(
        resultados
    )

    resultado = resultado[
        [
            coluna
            for coluna in COLUNAS_LOTE
            if coluna in resultado.columns
        ]
    ]

    return resultado


# ============================================================
# CARREGAMENTO DOS EVENTOS
# ============================================================

def carregar_arquivo_eventos(
    nome_arquivo,
):
    """
    A base de eventos é armazenada em df_eventos.

    O estado.py exige que obter_base() receba o nome
    da base, portanto utilizamos explicitamente:
        obter_base("eventos")
    """

    base = obter_base("eventos")

    if base is None:
        raise ValueError(
            "Não foi possível localizar a base de eventos carregada."
        )

    if isinstance(base, pd.DataFrame):
        return base.copy()

    if isinstance(base, dict):

        if nome_arquivo in base:
            valor = base[nome_arquivo]

            if isinstance(valor, pd.DataFrame):
                return valor.copy()

        nome_normalizado = normalizar_texto(
            nome_arquivo
        )

        for chave, valor in base.items():

            if (
                normalizar_texto(chave)
                == nome_normalizado
            ):
                if isinstance(valor, pd.DataFrame):
                    return valor.copy()

    raise ValueError(
        f"Não foi possível localizar o arquivo "
        f"'{nome_arquivo}'."
    )


# ============================================================
# CARREGAMENTO DO BACKLOG
# ============================================================

def carregar_backlog(modo):
    """
    O backlog utilizado no cruzamento depende do modo:

        API -> base 'api'
        THE -> base 'the'
    """

    modo_normalizado = normalizar_texto(
        modo
    )

    if modo_normalizado == "API":
        nome_base = "api"

    elif modo_normalizado == "THE":
        nome_base = "the"

    else:
        raise ValueError(
            f"Modo inválido para carregamento do backlog: {modo}"
        )

    base = obter_base(nome_base)

    if base is None:
        raise ValueError(
            f"A base '{nome_base}' não está carregada."
        )

    # Caso a base seja diretamente um DataFrame
    if isinstance(base, pd.DataFrame):
        return base.copy()

    # Caso a base contenha vários DataFrames
    if isinstance(base, dict):

        palavras_prioridade = [
            "OS",
            "BACKLOG",
            "ORDENS",
            "ORDEM",
        ]

        # Primeiro tenta encontrar uma chave relacionada
        # ao backlog/O.S.
        for chave, valor in base.items():

            if not isinstance(
                valor,
                pd.DataFrame,
            ):
                continue

            chave_normalizada = normalizar_texto(
                chave
            )

            if any(
                palavra in chave_normalizada
                for palavra in palavras_prioridade
            ):
                return valor.copy()

        # Fallback: primeiro DataFrame disponível
        for valor in base.values():

            if isinstance(
                valor,
                pd.DataFrame,
            ):
                return valor.copy()

    raise ValueError(
        f"Não foi encontrada uma base de O.S. "
        f"válida na base '{nome_base}'."
    )


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_eventos():
    aplicar_modo_visual()

    st.title("Análise de Eventos")

    st.markdown(
        """
        Utilize este módulo para identificar O.S. de Falta de Água
        abertas dentro da janela de impacto dos eventos cadastrados.
        """
    )

    # --------------------------------------------------------
    # Modo API / THE
    # --------------------------------------------------------

    modo = selecionar_modo_api_the()

    if modo is None:
        st.info(
            "Selecione um modo para continuar."
        )
        return

    # --------------------------------------------------------
    # Arquivo de eventos
    # --------------------------------------------------------

    nome_arquivo_eventos = (
        NOME_ARQUIVO_API
        if normalizar_texto(modo) == "API"
        else NOME_ARQUIVO_THE
    )

    st.markdown(
        '<div class="titulo-secao">Arquivo de eventos</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        f"Fonte selecionada: {nome_arquivo_eventos}"
    )

    try:

        df_eventos_bruto = (
            carregar_arquivo_eventos(
                nome_arquivo_eventos
            )
        )

    except Exception as erro:

        st.error(
            f"Não foi possível carregar os eventos: {erro}"
        )

        return

    # --------------------------------------------------------
    # Preparação dos eventos
    # --------------------------------------------------------

    try:

        df_eventos = preparar_eventos(
            df_eventos_bruto
        )

    except Exception as erro:

        st.error(
            f"Erro ao preparar os eventos: {erro}"
        )

        return

    if df_eventos.empty:

        st.warning(
            "Nenhum evento válido foi encontrado."
        )

        return

    # --------------------------------------------------------
    # Regras
    # --------------------------------------------------------

    with st.expander(
        "Regras aplicadas",
        expanded=False,
    ):

        st.markdown(
            """
            **Janela para considerar uma O.S.:**

            - Abertura da O.S. a partir de **1 hora antes do início do evento**.
            - O limite final considera primeiro o **Término Real**.
            - Se o **Término Real** não estiver disponível, é utilizada a **Previsão de Término**.
            - Após o término de referência são acrescentadas **3 horas**, correspondentes ao período esperado de normalização do abastecimento.
            - O município e o bairro/área impactada também precisam corresponder.
            - Qualificadores como **PARCIAL** são desconsiderados na comparação do nome da área.
            """
        )

    # --------------------------------------------------------
    # Backlog
    # --------------------------------------------------------

    st.markdown(
        '<div class="titulo-secao">Backlog de O.S.</div>',
        unsafe_allow_html=True,
    )

    try:

        df_backlog = carregar_backlog(
            modo
        )

        if df_backlog is None:
            st.warning(
                "Não foi encontrada uma base de O.S. carregada."
            )
            return

    except Exception as erro:

        st.error(
            f"Erro ao localizar o backlog de O.S.: {erro}"
        )

        return

    st.caption(
        f"{len(df_backlog):,} registros disponíveis para análise."
        .replace(",", ".")
    )

    # --------------------------------------------------------
    # Botão
    # --------------------------------------------------------

    if st.button(
        "Gerar análise de eventos",
        type="primary",
        use_container_width=True,
    ):

        with st.spinner(
            "Cruzando eventos com o backlog de O.S..."
        ):

            try:

                resultado = (
                    cruzar_eventos_com_backlog(
                        df_eventos,
                        df_backlog,
                    )
                )

            except Exception as erro:

                st.error(
                    f"Erro durante o cruzamento: {erro}"
                )

                return

        st.session_state[
            "resultado_eventos"
        ] = resultado

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

    resultado = st.session_state.get(
        "resultado_eventos"
    )

    if resultado is None:
        return

    st.markdown(
        '<div class="titulo-secao">Resultado</div>',
        unsafe_allow_html=True,
    )

    if resultado.empty:

        st.markdown(
            """
            <div class="resultado-vazio">
                Nenhuma O.S. foi encontrada dentro das regras
                de período e área dos eventos.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------
        # Retorno mesmo quando não há resultado
        # ----------------------------------------------------

        if st.button(
            "↩️ Voltar para o Gerador de Lotes",
            use_container_width=True,
            key="voltar_gerador_lotes_vazio",
        ):

            limpar_resultado()

            if "resultado_eventos" in st.session_state:
                del st.session_state[
                    "resultado_eventos"
                ]

            st.session_state[
                "ferramenta_atual"
            ] = None

            st.switch_page(
                "pages/4_1_Gerador_Lotes_Cancelamento.py"
            )

        return

    quantidade_total = int(
        resultado["Quant. de O.S"].sum()
    )

    quantidade_linhas = len(
        resultado
    )

    st.markdown(
        f"""
        <div class="resultado-ok">
            <strong>{quantidade_total}</strong> O.S. identificadas
            em <strong>{quantidade_linhas}</strong> agrupamentos.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # Tabela
    # --------------------------------------------------------

    st.dataframe(
        resultado,
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # Exportação
    # --------------------------------------------------------

    st.markdown(
        '<div class="titulo-secao">Exportação</div>',
        unsafe_allow_html=True,
    )

    try:

        arquivo_excel = dataframe_para_excel(
            resultado
        )

        st.download_button(
            label="Baixar resultado em Excel",
            data=arquivo_excel,
            file_name="Lote_Eventos.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    except Exception as erro:

        st.warning(
            f"Não foi possível preparar o Excel: {erro}"
        )

    # --------------------------------------------------------
    # Ações
    # --------------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "Limpar resultado",
            use_container_width=True,
            key="limpar_resultado_eventos",
        ):

            limpar_resultado()

            if "resultado_eventos" in st.session_state:
                del st.session_state[
                    "resultado_eventos"
                ]

            st.rerun()

    with col2:

        if st.button(
            "↩️ Voltar para o Gerador de Lotes",
            use_container_width=True,
            key="voltar_gerador_lotes",
        ):

            limpar_resultado()

            if "resultado_eventos" in st.session_state:
                del st.session_state[
                    "resultado_eventos"
                ]

            # Muito importante:
            # limpa a ferramenta atual antes de retornar.
            # Caso contrário, ao abrir novamente a página
            # ela poderia entrar diretamente em "eventos".
            st.session_state[
                "ferramenta_atual"
            ] = None

            st.switch_page(
                "pages/4_1_Gerador_Lotes_Cancelamento.py"
            )
