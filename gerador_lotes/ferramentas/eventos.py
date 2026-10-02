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
# IDENTIDADE VISUAL
# ============================================================

def aplicar_modo_visual():
    st.markdown(
        """
        <style>
        .coi-card {
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 14px;
            border: 1px solid;
        }

        .coi-card h3,
        .coi-card h4 {
            margin-top: 0;
        }

        .coi-metric {
            border-radius: 10px;
            padding: 14px 16px;
            border: 1px solid;
        }

        .coi-metric-label {
            font-size: 0.82rem;
            margin-bottom: 4px;
        }

        .coi-metric-value {
            font-size: 1.45rem;
            font-weight: 700;
        }

        @media (prefers-color-scheme: light) {
            .coi-card {
                background: #ffffff;
                border-color: #d9dee7;
            }

            .coi-card h3,
            .coi-card h4 {
                color: #111827;
            }

            .coi-card p,
            .coi-card span {
                color: #374151;
            }

            .coi-metric {
                background: #ffffff;
                border-color: #d9dee7;
            }

            .coi-metric-label {
                color: #6b7280;
            }

            .coi-metric-value {
                color: #111827;
            }

            section[data-testid="stSidebar"] {
                background: #ffffff;
            }
        }

        @media (prefers-color-scheme: dark) {
            .coi-card {
                background: #161b22;
                border-color: #30363d;
            }

            .coi-card h3,
            .coi-card h4 {
                color: #f0f2f6;
            }

            .coi-card p,
            .coi-card span {
                color: #c9d1d9;
            }

            .coi-metric {
                background: #161b22;
                border-color: #30363d;
            }

            .coi-metric-label {
                color: #8b949e;
            }

            .coi-metric-value {
                color: #f0f2f6;
            }

            section[data-testid="stSidebar"] {
                background: #161b22;
            }
        }

        div.stButton > button {
            border-radius: 8px;
        }

        div[data-testid="stDataFrame"] {
            border-radius: 8px;
        }

        div[data-testid="stExpander"] {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# NORMALIZAÇÃO DE TEXTO
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


# ============================================================
# LOCALIZAÇÃO DE COLUNAS
# ============================================================

def encontrar_coluna(df: pd.DataFrame, *nomes):
    mapa = {
        normalizar_texto(coluna): coluna
        for coluna in df.columns
    }

    for nome in nomes:
        chave = normalizar_texto(nome)

        if chave in mapa:
            return mapa[chave]

    return None


# ============================================================
# DATA/HORA DOS EVENTOS
# ============================================================

def converter_datetime_evento(valor):
    """
    Converte datas/horas da base de Eventos.

    Formato principal:
        24/09/2026 10:30h
    """

    if valor is None:
        return pd.NaT

    try:
        if pd.isna(valor):
            return pd.NaT
    except Exception:
        pass

    if isinstance(valor, (pd.Timestamp, datetime)):
        return pd.Timestamp(valor)

    texto = str(valor).strip()

    if not texto:
        return pd.NaT

    texto = re.sub(
        r"(\d{1,2}:\d{2})h\b",
        r"\1",
        texto,
        flags=re.IGNORECASE,
    )

    resultado = pd.to_datetime(
        texto,
        format="%d/%m/%Y %H:%M",
        errors="coerce",
    )

    if not pd.isna(resultado):
        return resultado

    return pd.to_datetime(
        texto,
        errors="coerce",
        dayfirst=True,
    )


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(valor):
    if valor is None:
        return None, None

    try:
        if pd.isna(valor):
            return None, None
    except Exception:
        pass

    texto = str(valor).strip()

    padrao = re.search(
        r"(\d+)\s*/\s*(\d{4})(?:\s*-\s*\d+)?",
        texto,
    )

    if not padrao:
        return None, None

    try:
        return (
            int(padrao.group(1)),
            int(padrao.group(2)),
        )
    except (TypeError, ValueError):
        return None, None


# ============================================================
# MATRÍCULA
# ============================================================

def normalizar_matricula(valor):
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

    return re.sub(r"\D", "", texto)


# ============================================================
# TODO O MUNICÍPIO
# ============================================================

PADROES_TODO_MUNICIPIO = {
    "TODA A CIDADE",
    "TODA CIDADE",
    "TODO O MUNICIPIO",
    "TODO MUNICIPIO",
    "TODA A AREA",
    "TODA AREA",
    "TODA A REGIAO",
    "TODA REGIAO",
    "MUNICIPIO TODO",
    "CIDADE TODA",
    "AREA TODA",
    "REGIAO TODA",
    "TODAS AS AREAS",
    "TODAS AREAS",
}


def eh_todo_municipio(valor) -> bool:
    texto = normalizar_texto(valor)

    if not texto:
        return False

    return texto in PADROES_TODO_MUNICIPIO


# ============================================================
# ÁREAS / BAIRROS
# ============================================================

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


def tokenizar_area(valor):
    texto = normalizar_texto(valor)

    if not texto:
        return set()

    return {
        token
        for token in texto.split()
        if token
    }


def areas_evento_correspondem(area_evento, bairro_os) -> bool:

    if not area_evento or not bairro_os:
        return False

    bairro = normalizar_texto(bairro_os)

    if not bairro:
        return False

    texto_area_original = str(area_evento).strip()

    if not texto_area_original:
        return False

    # --------------------------------------------------------
    # MUNICÍPIO INTEIRO
    # --------------------------------------------------------

    if eh_todo_municipio(texto_area_original):
        return True

    # --------------------------------------------------------
    # SEPARAÇÃO DE MÚLTIPLAS ÁREAS
    # --------------------------------------------------------

    partes = re.split(
        r"[;,|\n]+|\s+E\s+",
        texto_area_original,
        flags=re.IGNORECASE,
    )

    areas = []

    for parte in partes:
        area = normalizar_texto(parte)

        if area:
            areas.append(area)

    if not areas:
        return False

    # --------------------------------------------------------
    # COMPARAÇÃO EXATA
    # --------------------------------------------------------

    for area in areas:

        if area == bairro:
            return True

    # --------------------------------------------------------
    # SINÔNIMOS EXPLÍCITOS
    # --------------------------------------------------------

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

        area_equivalente = any(
            area in equivalentes
            for area in areas
        )

        bairro_equivalente = bairro in equivalentes

        if area_equivalente and bairro_equivalente:
            return True

    return False


# ============================================================
# PREPARAÇÃO DOS EVENTOS
# ============================================================

def preparar_eventos(df_eventos: pd.DataFrame):

    avisos = []

    if df_eventos is None or df_eventos.empty:
        return (
            pd.DataFrame(),
            ["A base de Eventos está vazia."],
            {
                "total": 0,
                "validos": 0,
                "invalidos": 0,
            },
        )

    df = df_eventos.copy()

    coluna_cidade = encontrar_coluna(
        df,
        "Cidade",
    )

    coluna_area = encontrar_coluna(
        df,
        "Áreas Impactadas",
        "Areas Impactadas",
        "Área Impactada",
        "Area Impactada",
    )

    coluna_inicio = encontrar_coluna(
        df,
        "Início",
        "Inicio",
    )

    coluna_fim = encontrar_coluna(
        df,
        "Prev. Término",
        "Prev Término",
        "Prev. Termino",
        "Previsão de Término",
        "Previsao de Termino",
    )

    coluna_descricao = encontrar_coluna(
        df,
        "Descrição do Serviço",
        "Descricao do Servico",
        "Descrição",
        "Descricao",
    )

    faltantes = []

    if coluna_cidade is None:
        faltantes.append("Cidade")

    if coluna_area is None:
        faltantes.append("Áreas Impactadas")

    if coluna_inicio is None:
        faltantes.append("Início")

    if coluna_fim is None:
        faltantes.append("Prev. Término")

    if faltantes:
        return (
            pd.DataFrame(),
            [
                "Colunas obrigatórias ausentes na base de "
                "Eventos: "
                + ", ".join(faltantes)
                + "."
            ],
            {
                "total": len(df),
                "validos": 0,
                "invalidos": len(df),
            },
        )

    eventos = pd.DataFrame()

    eventos["cidade"] = df[coluna_cidade].apply(
        normalizar_texto
    )

    eventos["areas"] = df[coluna_area].apply(
        normalizar_texto
    )

    eventos["inicio"] = df[coluna_inicio].apply(
        converter_datetime_evento
    )

    eventos["fim_previsto"] = df[coluna_fim].apply(
        converter_datetime_evento
    )

    eventos["fim_efetivo"] = (
        eventos["fim_previsto"]
        + pd.Timedelta(hours=3)
    )

    if coluna_descricao is not None:
        eventos["descricao"] = (
            df[coluna_descricao]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        eventos["descricao"] = ""

    eventos["todo_municipio"] = eventos["areas"].apply(
        eh_todo_municipio
    )

    eventos["fim_anterior_inicio"] = (
        eventos["inicio"].notna()
        & eventos["fim_previsto"].notna()
        & (
            eventos["fim_previsto"]
            < eventos["inicio"]
        )
    )

    quantidade_inicio_invalido = int(
        eventos["inicio"].isna().sum()
    )

    quantidade_fim_invalido = int(
        eventos["fim_previsto"].isna().sum()
    )

    quantidade_fim_anterior = int(
        eventos["fim_anterior_inicio"].sum()
    )

    cidades_vazias = int(
        (eventos["cidade"] == "").sum()
    )

    if quantidade_inicio_invalido:
        avisos.append(
            f"{quantidade_inicio_invalido} evento(s) com "
            "Início inválido serão ignorados."
        )

    if quantidade_fim_invalido:
        avisos.append(
            f"{quantidade_fim_invalido} evento(s) com "
            "Prev. Término inválido serão ignorados."
        )

    if quantidade_fim_anterior:
        avisos.append(
            f"{quantidade_fim_anterior} evento(s) com fim "
            "anterior ao início serão ignorados."
        )

    if cidades_vazias:
        avisos.append(
            f"{cidades_vazias} evento(s) sem cidade serão "
            "ignorados."
        )

    eventos_validos = eventos[
        eventos["inicio"].notna()
        & eventos["fim_previsto"].notna()
        & ~eventos["fim_anterior_inicio"]
        & (eventos["cidade"] != "")
    ].copy()

    estatisticas = {
        "total": len(eventos),
        "validos": len(eventos_validos),
        "invalidos": (
            len(eventos)
            - len(eventos_validos)
        ),
    }

    return (
        eventos_validos,
        avisos,
        estatisticas,
    )


# ============================================================
# OBSERVAÇÃO
# ============================================================

def montar_observacao(descricao):

    descricao = (
        ""
        if descricao is None
        else str(descricao).strip()
    )

    descricao = re.sub(
        r"\s+",
        " ",
        descricao,
    )

    prefixo = (
        "Abertura indevida - OS aberta durante evento "
        "de falta de água"
    )

    if descricao:
        texto = f"{prefixo} ({descricao})"
    else:
        texto = prefixo

    return texto[:280]


# ============================================================
# CRUZAMENTO EVENTOS x BACKLOG
# ============================================================

def cruzar_eventos_com_backlog(df_eventos, df_backlog, modo=None):
    colunas_obrigatorias = [
        "CIDADE",
        "BAIRRO",
        "INÍCIO DO SLA",
        "COD. PROTOCOLO ORIGEM",
        "MATRICULA",
    ]

    faltantes = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in df_backlog.columns
    ]

    if faltantes:
        raise ValueError(
            "Colunas obrigatórias ausentes no backlog: "
            + ", ".join(faltantes)
        )

    df = df_backlog.copy()

    df["cidade_normalizada"] = (
        df["CIDADE"]
        .fillna("")
        .astype(str)
        .map(normalizar_texto)
    )

    df["bairro_normalizado"] = (
        df["BAIRRO"]
        .fillna("")
        .astype(str)
        .map(normalizar_texto)
    )

    df["inicio_sla"] = pd.to_datetime(
        df["INÍCIO DO SLA"],
        errors="coerce",
        dayfirst=True,
    )

    df["chave_os"] = list(
        zip(
            df["MATRICULA"].map(normalizar_matricula),
            df["COD. PROTOCOLO ORIGEM"].fillna("").astype(str),
        )
    )

    df = df[
        (df["cidade_normalizada"] != "")
        & df["inicio_sla"].notna()
    ].copy()

    resultado = []
    avisos = []

    for _, evento in df_eventos.iterrows():
        cidade = normalizar_texto(evento.get("cidade", ""))

        areas = str(evento.get("areas", "") or "").strip()

        inicio_evento = evento.get("inicio")
        fim_previsto = evento.get("fim_previsto")
        fim_efetivo = evento.get("fim_efetivo")
        descricao = str(evento.get("descricao", "") or "").strip()

        if (
            not cidade
            or pd.isna(inicio_evento)
            or pd.isna(fim_previsto)
            or pd.isna(fim_efetivo)
        ):
            continue

        # Evento que abrange todo o município
        if bool(evento.get("todo_municipio", False)):
            areas_evento = ["TODA A CIDADE"]
        else:
            partes = re.split(
                r"[;,|\n]+|\s+E\s+",
                areas,
            )

            areas_evento = [
                normalizar_texto(parte)
                for parte in partes
                if normalizar_texto(parte)
            ]

        for area_evento in areas_evento:

            candidatos = df[
                df["cidade_normalizada"] == cidade
            ].copy()

            candidatos = candidatos[
                (candidatos["inicio_sla"] >= inicio_evento)
                & (candidatos["inicio_sla"] <= fim_efetivo)
            ]

            chaves_os_evento = set()

            for _, os_row in candidatos.iterrows():

                if area_evento != "TODA A CIDADE":
                    if not areas_evento_correspondem(
                        area_evento,
                        os_row["bairro_normalizado"],
                    ):
                        continue

                chave_os = os_row["chave_os"]

                if chave_os in chaves_os_evento:
                    continue

                chaves_os_evento.add(chave_os)

            quantidade_os = len(chaves_os_evento)

            # Só gera a linha quando existir pelo menos 1 O.S.
            if quantidade_os > 0:
                resultado.append(
                    {
                        "Quant. de O.S": quantidade_os,
                        "Cidade": cidade,
                        "Bairro": area_evento,
                        "Ano": inicio_evento.year,
                        "Mês": inicio_evento.month,
                        "Dia": inicio_evento.day,
                        "Hora Inicial": inicio_evento.strftime("%H:%M"),
                        "Hora Final": fim_previsto.strftime("%H:%M"),
                        "Observação": montar_observacao(descricao),
                    }
                )

    df_resultado = pd.DataFrame(
        resultado,
        columns=COLUNAS_LOTE,
    )

    return (
        df_resultado,
        len(df),
        len(df_resultado),
        avisos,
    )
    # --------------------------------------------------------
    # AVISOS
    # --------------------------------------------------------

    if protocolos_invalidos:
        avisos.append(
            f"{protocolos_invalidos} O.S. com protocolo inválido "
            "foram ignoradas."
        )

    if inicio_sla_invalido:
        avisos.append(
            f"{inicio_sla_invalido} O.S. com INÍCIO DO SLA inválido "
            "foram ignoradas."
        )

    # --------------------------------------------------------
    # RESULTADO FINAL
    # --------------------------------------------------------

    resultado = pd.DataFrame(
        resultados,
        columns=COLUNAS_LOTE,
    )

    return (
        resultado,
        len(df),
        avisos,
        len(resultado),
    )


# ============================================================
# LIMPEZA EXCLUSIVA DA ANÁLISE DE EVENTOS
# ============================================================

def limpar_estado_eventos():
    """
    Limpa somente o resultado da ferramenta Eventos.

    Não remove:
        df_api
        df_the
        df_eventos
        demais bases compartilhadas
    """

    st.session_state["eventos_analisado"] = False
    st.session_state["eventos_resultado"] = None
    st.session_state["eventos_avisos"] = []
    st.session_state["eventos_estatisticas"] = {}


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_eventos():

    aplicar_modo_visual()

    # --------------------------------------------------------
    # ESTADO DA FERRAMENTA
    # --------------------------------------------------------

    if "eventos_analisado" not in st.session_state:
        st.session_state["eventos_analisado"] = False

    if "eventos_resultado" not in st.session_state:
        st.session_state["eventos_resultado"] = None

    if "eventos_avisos" not in st.session_state:
        st.session_state["eventos_avisos"] = []

    if "eventos_estatisticas" not in st.session_state:
        st.session_state["eventos_estatisticas"] = {}

    # --------------------------------------------------------
    # CABEÇALHO
    # --------------------------------------------------------

    st.title("📋 Análise de Eventos")

    st.caption(
        "Cancela O.S. de reclamação abertas durante eventos "
        "oficiais de falta de água."
    )

    st.divider()

    # --------------------------------------------------------
    # API / THE
    # --------------------------------------------------------

    modo, df_backlog = selecionar_modo_api_the(
        key="eventos_modo"
    )

    # --------------------------------------------------------
    # BACKLOG
    # --------------------------------------------------------

    if df_backlog is None or df_backlog.empty:

        st.warning(
            f"A base de backlog do modo {modo} ainda não foi "
            "carregada no Hub."
        )

        st.info(
            "Volte ao Hub, carregue a base correspondente e "
            "acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_eventos_sem_backlog",
        ):
            st.session_state["ferramenta_atual"] = None
            limpar_resultado()
            st.rerun()

        st.stop()

    # --------------------------------------------------------
    # EVENTOS
    # --------------------------------------------------------

    if not base_carregada("eventos"):

        st.warning(
            "A base de Eventos ainda não foi carregada no Hub."
        )

        st.info(
            "Volte ao Hub, carregue a planilha de Eventos e "
            "acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_eventos_sem_eventos",
        ):
            st.session_state["ferramenta_atual"] = None
            limpar_resultado()
            st.rerun()

        st.stop()

    df_eventos = obter_base("eventos")

    # --------------------------------------------------------
    # BASES
    # --------------------------------------------------------

    st.markdown("### 📊 Bases utilizadas")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""
            <div class="coi-metric">
                <div class="coi-metric-label">Modo</div>
                <div class="coi-metric-value">{modo}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="coi-metric">
                <div class="coi-metric-label">Backlog</div>
                <div class="coi-metric-value">
                    {len(df_backlog):,}
                </div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="coi-metric">
                <div class="coi-metric-label">Eventos</div>
                <div class="coi-metric-value">
                    {len(df_eventos):,}
                </div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    st.divider()

    # --------------------------------------------------------
    # REGRAS
    # --------------------------------------------------------

    with st.expander(
        "ℹ️ Regras aplicadas",
        expanded=False,
    ):
        st.markdown(
            """
            **Critérios para identificação das O.S.:**

            - A cidade da O.S. deve ser a mesma do evento.
            - O **INÍCIO DO SLA** da O.S. deve estar entre o
              início e o fim efetivo do evento.
            - O fim efetivo corresponde ao **Prev. Término + 3 horas**.
            - Eventos que abrangem todo o município têm correspondência
              automática.
            - Nos demais eventos, o bairro é comparado com as
              **Áreas Impactadas**.
            - A mesma O.S. é contabilizada uma única vez por área do evento.
            - A coluna **Data** não é utilizada.
            - O resultado é consolidado por evento e área impactada.
            """
        )

    # --------------------------------------------------------
    # ANÁLISE
    # --------------------------------------------------------

    st.markdown("### 🔍 Análise")

    if st.button(
        "🔍 Analisar Eventos",
        type="primary",
        use_container_width=True,
        key="btn_analisar_eventos",
    ):

        with st.spinner(
            "Preparando eventos e cruzando com o backlog..."
        ):

            (
                eventos_preparados,
                avisos_eventos,
                estatisticas_eventos,
            ) = preparar_eventos(
                df_eventos
            )

            (
                resultado,
                total_analisado,
                avisos_cruzamento,
                total_resultado,
            ) = cruzar_eventos_com_backlog(
                df_backlog=df_backlog,
                eventos=eventos_preparados,
                modo=modo,
            )

        st.session_state["eventos_analisado"] = True

        st.session_state["eventos_resultado"] = resultado

        st.session_state["eventos_avisos"] = (
            avisos_eventos
            + avisos_cruzamento
        )

        st.session_state["eventos_estatisticas"] = {
            "eventos_total": estatisticas_eventos["total"],
            "eventos_validos": estatisticas_eventos["validos"],
            "registros_analisados": total_analisado,
            "os_cancelamento": total_resultado,
            "modo": modo,
        }

        st.rerun()

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    if st.session_state.get(
        "eventos_analisado",
        False,
    ):

        resultado = st.session_state.get(
            "eventos_resultado"
        )

        estatisticas = st.session_state.get(
            "eventos_estatisticas",
            {},
        )

        avisos = st.session_state.get(
            "eventos_avisos",
            [],
        )

        modo_resultado = estatisticas.get(
            "modo",
            modo,
        )

        st.divider()

        st.markdown("### 📋 Resultado da análise")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown(
                f"""
                <div class="coi-metric">
                    <div class="coi-metric-label">
                        Eventos válidos
                    </div>
                    <div class="coi-metric-value">
                        {estatisticas.get("eventos_validos", 0):,}
                    </div>
                </div>
                """.replace(",", "."),
                unsafe_allow_html=True,
            )

        with col2:
            st.markdown(
                f"""
                <div class="coi-metric">
                    <div class="coi-metric-label">
                        O.S. analisadas
                    </div>
                    <div class="coi-metric-value">
                        {estatisticas.get("registros_analisados", 0):,}
                    </div>
                </div>
                """.replace(",", "."),
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(
                f"""
                <div class="coi-metric">
                    <div class="coi-metric-label">
                        Linhas geradas
                    </div>
                    <div class="coi-metric-value">
                        {estatisticas.get("os_cancelamento", 0):,}
                    </div>
                </div>
                """.replace(",", "."),
                unsafe_allow_html=True,
            )

        with col4:

            analisadas = estatisticas.get(
                "registros_analisados",
                0,
            )

            linhas = estatisticas.get(
                "os_cancelamento",
                0,
            )

            percentual = (
                linhas / analisadas * 100
                if analisadas
                else 0
            )

            st.markdown(
                f"""
                <div class="coi-metric">
                    <div class="coi-metric-label">
                        Percentual
                    </div>
                    <div class="coi-metric-value">
                        {percentual:.1f}%
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ----------------------------------------------------
        # AVISOS
        # ----------------------------------------------------

        if avisos:

            st.markdown("### ⚠️ Avisos")

            for aviso in avisos:
                st.warning(aviso)

        # ----------------------------------------------------
        # PRÉVIA
        # ----------------------------------------------------

        st.markdown("### 👁️ Prévia do lote")

        if resultado is None or resultado.empty:

            st.info(
                "Nenhum evento/área foi identificado para "
                "composição do resultado."
            )

        else:

            st.dataframe(
                resultado,
                use_container_width=True,
                hide_index=True,
            )

            st.divider()

            st.markdown("### 📤 Ações")

            arquivo = dataframe_para_excel(
                resultado,
                nome_aba="Eventos",
            )

            nome_arquivo = (
                NOME_ARQUIVO_THE
                if modo_resultado == "THE"
                else NOME_ARQUIVO_API
            )

            col_acao_1, col_acao_2 = st.columns(2)

            with col_acao_1:

                st.download_button(
                    "📥 Baixar lote",
                    data=arquivo if arquivo is not None else b"",
                    file_name=nome_arquivo,
                    mime=(
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                    key="btn_baixar_eventos",
                )

            with col_acao_2:

                if st.button(
                    "🗑️ Limpar análise",
                    use_container_width=True,
                    key="btn_limpar_eventos",
                ):
                    limpar_estado_eventos()
                    st.rerun()

    # --------------------------------------------------------
    # VOLTAR AO HUB
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_eventos",
    ):

        st.session_state["ferramenta_atual"] = None

        # Limpa somente resultados globais.
        # As bases permanecem intactas.
        limpar_resultado()

        # Limpa somente o estado específico de Eventos.
        limpar_estado_eventos()

        st.rerun()
