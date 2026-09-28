import io
import json
import math
import re
import html
from datetime import date, datetime, time
from uuid import uuid4

import folium
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Mapeamento de Melhorias - COI",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

from auth import verificar_autenticacao


verificar_autenticacao()

if not st.session_state.get("autenticado"):
    st.warning("Você precisa estar autenticado para acessar este módulo.")

    if st.button("🏠 Voltar ao Menu Principal"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# CONFIGURAÇÃO DO GOOGLE SHEETS
# ============================================================

# IMPORTANTE:
# Esta é a planilha EXCLUSIVA do Módulo 7.
# NÃO utilizar o ID da planilha do Módulo 1.
SPREADSHEET_ID = st.secrets.get(
    "MAPEAMENTO_MELHORIAS_SPREADSHEET_ID",
    "",
)


REGISTRO_SHEET = "Registro"
HISTORICO_SHEET = "Historico"


REGISTRO_HEADERS = [
    "ID",
    "Matrícula",
    "Endereço",
    "Bairro",
    "Latitude",
    "Longitude",
    "Parecer",
    "Data de Registro",
    "Tratativa 1",
    "Executado?",
    "Retorno",
    "Responsável",
    "Grau de Impacto",
    "Resolvido",
]


HISTORICO_HEADERS = [
    "ID",
    "Matrícula",
    "N. O.S",
    "Data de Abertura",
    "Pressão",
    "Pontual",
]


# ============================================================
# CONSTANTES
# ============================================================

REGISTROS_POR_PAGINA = 10

OS_PATTERN = re.compile(
    r"^\d{5}/\d{4}-\d+$"
)


# ============================================================
# ESTILO
# ============================================================

st.markdown(
    """
    <style>
        .kpi-card {
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 12px;
            padding: 16px;
            min-height: 115px;
        }

        .kpi-title {
            font-size: 0.85rem;
            opacity: 0.75;
            margin-bottom: 8px;
        }

        .kpi-value {
            font-size: 1.55rem;
            font-weight: 700;
        }

        .registro-card {
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 10px;
        }

        .registro-titulo {
            font-size: 1.05rem;
            font-weight: 700;
        }

        .registro-subtitulo {
            opacity: 0.75;
            font-size: 0.88rem;
        }

        .campo-label {
            font-size: 0.78rem;
            opacity: 0.70;
        }

        .campo-valor {
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""

    if isinstance(valor, float) and math.isnan(valor):
        return ""

    return str(valor).strip()


def normalizar_sim_nao(valor):
    texto = normalizar_texto(valor).upper()

    if texto in ("SIM", "S", "YES", "TRUE", "1"):
        return "SIM"

    if texto in ("NÃO", "NAO", "N", "NO", "FALSE", "0"):
        return "NAO"

    return texto


def converter_float(valor):
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and math.isnan(valor):
            return None
        return float(valor)

    texto = normalizar_texto(valor)

    if not texto:
        return None

    texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def formatar_data(valor):
    if valor is None or normalizar_texto(valor) == "":
        return "—"

    try:
        data = pd.to_datetime(valor, errors="coerce")

        if pd.isna(data):
            return normalizar_texto(valor)

        return data.strftime("%d/%m/%Y")

    except Exception:
        return normalizar_texto(valor)


def formatar_data_hora(valor):
    if valor is None or normalizar_texto(valor) == "":
        return "—"

    try:
        data = pd.to_datetime(valor, errors="coerce")

        if pd.isna(data):
            return normalizar_texto(valor)

        return data.strftime("%d/%m/%Y %H:%M")

    except Exception:
        return normalizar_texto(valor)


def escapar(valor):
    return html.escape(normalizar_texto(valor))


def gerar_id():
    return uuid4().hex[:12]


def coordenada_valida(latitude, longitude):
    lat = converter_float(latitude)
    lon = converter_float(longitude)

    if lat is None or lon is None:
        return False

    return (
        -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def valor_data_para_widget(valor, padrao=None):
    if padrao is None:
        padrao = date.today()

    if valor is None or normalizar_texto(valor) == "":
        return padrao

    try:
        resultado = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(resultado):
            return padrao

        return resultado.date()

    except Exception:
        return padrao


def valor_datetime_para_widget(valor):
    if valor is None or normalizar_texto(valor) == "":
        return datetime.now()

    try:
        resultado = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(resultado):
            return datetime.now()

        return resultado.to_pydatetime()

    except Exception:
        return datetime.now()


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google_sheets(spreadsheet_id):
    if not spreadsheet_id:
        raise ValueError(
            "A configuração MAPEAMENTO_MELHORIAS_SPREADSHEET_ID "
            "não foi encontrada nos secrets."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials_dict = json.loads(
        st.secrets["gcp_json"]
    )

    credentials = Credentials.from_service_account_info(
        credentials_dict,
        scopes=scopes,
    )

    gc = gspread.authorize(credentials)

    return gc.open_by_key(spreadsheet_id)


def garantir_headers(worksheet, headers):
    valores = worksheet.get_all_values()

    if not valores:
        worksheet.append_row(
            headers,
            value_input_option="USER_ENTERED",
        )
        return

    primeira_linha = [
        normalizar_texto(x)
        for x in valores[0]
    ]

    if primeira_linha != headers:
        worksheet.clear()
        worksheet.append_row(
            headers,
            value_input_option="USER_ENTERED",
        )


@st.cache_resource
def obter_planilhas():
    try:
        spreadsheet = conectar_google_sheets(
            SPREADSHEET_ID
        )

        try:
            registro_ws = spreadsheet.worksheet(
                REGISTRO_SHEET
            )
        except gspread.WorksheetNotFound:
            registro_ws = spreadsheet.add_worksheet(
                title=REGISTRO_SHEET,
                rows=1000,
                cols=len(REGISTRO_HEADERS),
            )

        try:
            historico_ws = spreadsheet.worksheet(
                HISTORICO_SHEET
            )
        except gspread.WorksheetNotFound:
            historico_ws = spreadsheet.add_worksheet(
                title=HISTORICO_SHEET,
                rows=2000,
                cols=len(HISTORICO_HEADERS),
            )

        garantir_headers(
            registro_ws,
            REGISTRO_HEADERS,
        )

        garantir_headers(
            historico_ws,
            HISTORICO_HEADERS,
        )

        return registro_ws, historico_ws

    except Exception as exc:
        st.error(
            "Não foi possível acessar a planilha "
            "**Mapeamento de Melhorias**."
        )

        st.exception(exc)

        st.info(
            "Verifique se a planilha foi compartilhada "
            "com o e-mail da conta de serviço configurada "
            "em `gcp_json` e se "
            "`MAPEAMENTO_MELHORIAS_SPREADSHEET_ID` "
            "aponta para a planilha correta."
        )

        st.stop()


def carregar_worksheet(worksheet, headers):
    valores = worksheet.get_all_records(
        default_blank=""
    )

    if not valores:
        return pd.DataFrame(
            columns=headers
        )

    df = pd.DataFrame(valores)

    for coluna in headers:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[headers].copy()


def carregar_dados():
    registro_ws, historico_ws = obter_planilhas()

    df_registro = carregar_worksheet(
        registro_ws,
        REGISTRO_HEADERS,
    )

    df_historico = carregar_worksheet(
        historico_ws,
        HISTORICO_HEADERS,
    )

    return (
        registro_ws,
        historico_ws,
        df_registro,
        df_historico,
    )


# ============================================================
# LOCALIZAÇÃO DE LINHAS
# ============================================================

def localizar_linha_por_id(
    worksheet,
    registro_id,
):
    try:
        celula = worksheet.find(
            str(registro_id)
        )

        if celula:
            return celula.row

    except Exception:
        pass

    return None


def localizar_linha_os(
    worksheet,
    os_id,
):
    return localizar_linha_por_id(
        worksheet,
        os_id,
    )


# ============================================================
# CRUD — REGISTRO
# ============================================================

def registro_para_lista(dados):
    return [
        dados.get(coluna, "")
        for coluna in REGISTRO_HEADERS
    ]


def adicionar_registro(dados):
    registro_ws, _ = obter_planilhas()

    registro_ws.append_row(
        registro_para_lista(dados),
        value_input_option="USER_ENTERED",
    )


def atualizar_registro(
    registro_id,
    dados,
):
    registro_ws, _ = obter_planilhas()

    linha = localizar_linha_por_id(
        registro_ws,
        registro_id,
    )

    if linha is None:
        raise ValueError(
            "Registro não encontrado."
        )

    registro_ws.update(
        f"A{linha}:N{linha}",
        [
            registro_para_lista(dados)
        ],
        value_input_option="USER_ENTERED",
    )


def excluir_registro(
    registro_id,
):
    registro_ws, _ = obter_planilhas()

    linha = localizar_linha_por_id(
        registro_ws,
        registro_id,
    )

    if linha is None:
        raise ValueError(
            "Registro não encontrado."
        )

    registro_ws.delete_rows(linha)


# ============================================================
# CRUD — O.S.
# ============================================================

def os_para_lista(dados):
    return [
        dados.get(coluna, "")
        for coluna in HISTORICO_HEADERS
    ]


def adicionar_os(dados):
    _, historico_ws = obter_planilhas()

    historico_ws.append_row(
        os_para_lista(dados),
        value_input_option="USER_ENTERED",
    )


def atualizar_os(
    os_id,
    dados,
):
    _, historico_ws = obter_planilhas()

    linha = localizar_linha_os(
        historico_ws,
        os_id,
    )

    if linha is None:
        raise ValueError(
            "O.S. não encontrada."
        )

    historico_ws.update(
        f"A{linha}:F{linha}",
        [
            os_para_lista(dados)
        ],
        value_input_option="USER_ENTERED",
    )


def excluir_os(os_id):
    _, historico_ws = obter_planilhas()

    linha = localizar_linha_os(
        historico_ws,
        os_id,
    )

    if linha is None:
        raise ValueError(
            "O.S. não encontrada."
        )

    historico_ws.delete_rows(linha)


# ============================================================
# CONSULTAS
# ============================================================

def historico_da_matricula(
    df_historico,
    matricula,
):
    if df_historico.empty:
        return df_historico.copy()

    return df_historico[
        df_historico["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        normalizar_texto(matricula)
        .upper()
    ].copy()


def registro_da_matricula(
    df_registro,
    matricula,
):
    if df_registro.empty:
        return df_registro.copy()

    return df_registro[
        df_registro["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        normalizar_texto(matricula)
        .upper()
    ].copy()


def matricula_possui_registro(
    df_registro,
    matricula,
    ignorar_id=None,
):
    if df_registro.empty:
        return False

    mascara = (
        df_registro["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        normalizar_texto(matricula).upper()
    )

    if ignorar_id is not None:
        mascara &= (
            df_registro["ID"].astype(str)
            != str(ignorar_id)
        )

    return mascara.any()


# ============================================================
# VALIDAÇÃO DE O.S.
# ============================================================

def validar_os(numero_os):
    numero_os = normalizar_texto(
        numero_os
    )

    if not numero_os:
        return False

    return bool(
        OS_PATTERN.fullmatch(numero_os)
    )


def os_duplicada(
    df_historico,
    matricula,
    numero_os,
    ignorar_id=None,
):
    if df_historico.empty:
        return False

    mascara = (
        df_historico["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        normalizar_texto(matricula).upper()
    ) & (
        df_historico["N. O.S"]
        .astype(str)
        .str.strip()
        ==
        normalizar_texto(numero_os)
    )

    if ignorar_id is not None:
        mascara &= (
            df_historico["ID"].astype(str)
            != str(ignorar_id)
        )

    return mascara.any()


# ============================================================
# EXPORTAÇÃO
# ============================================================

def gerar_excel(
    df_registro,
    df_historico,
    incluir_registro=True,
):
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        if incluir_registro:
            df_registro.to_excel(
                writer,
                sheet_name="Registro",
                index=False,
            )

        df_historico.to_excel(
            writer,
            sheet_name="Historico",
            index=False,
        )

    buffer.seek(0)

    return buffer


def gerar_excel_cliente(
    registro_cliente,
    historico_cliente,
):
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        registro_cliente.to_excel(
            writer,
            sheet_name="Resumo",
            index=False,
        )

        historico_cliente.to_excel(
            writer,
            sheet_name="Histórico",
            index=False,
        )

    buffer.seek(0)

    return buffer


# ============================================================
# FILTROS
# ============================================================

def aplicar_filtros(
    df_registro,
    df_historico,
):
    registro = df_registro.copy()
    historico = df_historico.copy()

    if not historico.empty:
        historico["_data_abertura"] = pd.to_datetime(
            historico["Data de Abertura"],
            errors="coerce",
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    if not historico.empty:

        datas_validas = (
            historico["_data_abertura"]
            .dropna()
        )

        if not datas_validas.empty:
            data_min = datas_validas.min().date()
            data_max = datas_validas.max().date()

            filtro_data = st.sidebar.date_input(
                "Data de Abertura",
                value=(
                    data_min,
                    data_max,
                ),
                min_value=data_min,
                max_value=data_max,
            )

            if (
                isinstance(filtro_data, tuple)
                and len(filtro_data) == 2
            ):
                data_inicio, data_fim = filtro_data

                historico = historico[
                    (
                        historico["_data_abertura"]
                        .dt.date
                        >= data_inicio
                    )
                    &
                    (
                        historico["_data_abertura"]
                        .dt.date
                        <= data_fim
                    )
                ]

                matriculas_data = set(
                    historico["Matrícula"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                )

                registro = registro[
                    registro["Matrícula"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .isin(matriculas_data)
                ]

    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    bairros = sorted(
        [
            x
            for x in registro["Bairro"]
            .astype(str)
            .str.strip()
            .unique()
            if x
        ]
    )

    bairros_selecionados = st.sidebar.multiselect(
        "Bairro",
        options=bairros,
    )

    if bairros_selecionados:
        registro = registro[
            registro["Bairro"]
            .astype(str)
            .str.strip()
            .isin(bairros_selecionados)
        ]

    # --------------------------------------------------------
    # MATRÍCULA
    # --------------------------------------------------------

    matriculas = sorted(
        [
            x
            for x in registro["Matrícula"]
            .astype(str)
            .str.strip()
            .unique()
            if x
        ]
    )

    matriculas_selecionadas = st.sidebar.multiselect(
        "Matrícula",
        options=matriculas,
    )

    if matriculas_selecionadas:
        registro = registro[
            registro["Matrícula"]
            .astype(str)
            .str.strip()
            .isin(matriculas_selecionadas)
        ]

    # --------------------------------------------------------
    # GRAU DE IMPACTO
    # --------------------------------------------------------

    impactos = sorted(
        [
            x
            for x in registro["Grau de Impacto"]
            .astype(str)
            .str.strip()
            .unique()
            if x
        ]
    )

    impactos_selecionados = st.sidebar.multiselect(
        "Grau de Impacto",
        options=impactos,
    )

    if impactos_selecionados:
        registro = registro[
            registro["Grau de Impacto"]
            .astype(str)
            .str.strip()
            .isin(impactos_selecionados)
        ]

    # --------------------------------------------------------
    # RESOLVIDO
    # --------------------------------------------------------

    resolvidos = sorted(
        [
            x
            for x in registro["Resolvido"]
            .astype(str)
            .str.strip()
            .unique()
            if x
        ]
    )

    resolvidos_selecionados = st.sidebar.multiselect(
        "Resolvido",
        options=resolvidos,
    )

    if resolvidos_selecionados:
        registro = registro[
            registro["Resolvido"]
            .astype(str)
            .str.strip()
            .isin(resolvidos_selecionados)
        ]

    # --------------------------------------------------------
    # EXECUTADO
    # --------------------------------------------------------

    executados_1 = set(
        registro["Executado?"]
        .astype(str)
        .str.strip()
        .unique()
    )

    executados = sorted(
        [
            x
            for x in executados_1
            if x
        ]
    )

    executado_selecionado = st.sidebar.multiselect(
        "Executado",
        options=executados,
    )

    if executado_selecionado:
        mascara_exec = (
            registro["Executado?"]
            .astype(str)
            .str.strip()
            .isin(executado_selecionado)
        )

        registro = registro[
            mascara_exec
        ]

    # --------------------------------------------------------
    # BUSCA RÁPIDA
    # --------------------------------------------------------

    busca = st.sidebar.text_input(
        "🔎 Busca rápida",
        placeholder="Matrícula, endereço ou O.S.",
    )

    if busca.strip():

        termo = busca.strip().lower()

        matriculas_busca = set(
            registro[
                registro["Matrícula"]
                .astype(str)
                .str.lower()
                .str.contains(
                    termo,
                    na=False,
                    regex=False,
                )
            ]["Matrícula"]
            .astype(str)
        )

        enderecos_busca = set(
            registro[
                registro["Endereço"]
                .astype(str)
                .str.lower()
                .str.contains(
                    termo,
                    na=False,
                    regex=False,
                )
            ]["Matrícula"]
            .astype(str)
        )

        os_busca = set()

        if not historico.empty:
            os_busca = set(
                historico[
                    historico["N. O.S"]
                    .astype(str)
                    .str.lower()
                    .str.contains(
                        termo,
                        na=False,
                        regex=False,
                    )
                ]["Matrícula"]
                .astype(str)
            )

        matriculas_busca |= enderecos_busca
        matriculas_busca |= os_busca

        registro = registro[
            registro["Matrícula"]
            .astype(str)
            .isin(matriculas_busca)
        ]

    # --------------------------------------------------------
    # INTERSEÇÃO FINAL DO HISTÓRICO
    # --------------------------------------------------------

    if not registro.empty:
        matriculas_finais = set(
            registro["Matrícula"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        historico = historico[
            historico["Matrícula"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(matriculas_finais)
        ]

    if "_data_abertura" in historico.columns:
        historico = historico.drop(
            columns=["_data_abertura"]
        )

    return registro, historico


# ============================================================
# ORDENAÇÃO DOS REGISTROS
# ============================================================

def ordenar_registros(
    df_registro,
    df_historico,
):
    if df_registro.empty:
        return df_registro.copy()

    contagem = (
        df_historico
        .groupby("Matrícula")
        .size()
        .rename("_qtd_os")
    )

    ultima_os = (
        df_historico.copy()
    )

    if not ultima_os.empty:
        ultima_os["_data"] = pd.to_datetime(
            ultima_os["Data de Abertura"],
            errors="coerce",
        )

        ultima_os = (
            ultima_os
            .sort_values("_data")
            .groupby("Matrícula")
            .tail(1)
            [
                ["Matrícula", "N. O.S", "_data"]
            ]
            .rename(
                columns={
                    "N. O.S": "_ultima_os"
                }
            )
        )

    resultado = df_registro.copy()

    resultado = resultado.merge(
        contagem,
        left_on="Matrícula",
        right_index=True,
        how="left",
    )

    resultado["_qtd_os"] = (
        resultado["_qtd_os"]
        .fillna(0)
        .astype(int)
    )

    if not ultima_os.empty:
        resultado = resultado.merge(
            ultima_os[
                [
                    "Matrícula",
                    "_ultima_os",
                    "_data",
                ]
            ],
            on="Matrícula",
            how="left",
        )
    else:
        resultado["_ultima_os"] = ""
        resultado["_data"] = pd.NaT

    resultado = resultado.sort_values(
        by=[
            "_qtd_os",
            "_data",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )

    return resultado


# ============================================================
# KPI
# ============================================================

def calcular_kpis(
    df_registro,
    df_historico,
):
    if df_historico.empty:
        return None

    agrupado = (
        df_historico
        .groupby("Matrícula")
        .size()
        .reset_index(
            name="qtd_os"
        )
    )

    if agrupado.empty:
        return None

    historico_aux = df_historico.copy()

    historico_aux["_data"] = pd.to_datetime(
        historico_aux["Data de Abertura"],
        errors="coerce",
    )

    ultimas = (
        historico_aux
        .sort_values("_data")
        .groupby("Matrícula")
        .tail(1)
        [["Matrícula", "_data"]]
        .rename(
            columns={
                "_data": "ultima_data"
            }
        )
    )

    agrupado = agrupado.merge(
        ultimas,
        on="Matrícula",
        how="left",
    )

    agrupado = agrupado.sort_values(
        by=[
            "qtd_os",
            "ultima_data",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )

    cliente = agrupado.iloc[0][
        "Matrícula"
    ]

    qtd_os = int(
        agrupado.iloc[0]["qtd_os"]
    )

    historico_cliente = historico_aux[
        historico_aux["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        normalizar_texto(cliente).upper()
    ].copy()

    historico_cliente = (
        historico_cliente
        .sort_values("_data")
    )

    datas = (
        historico_cliente["_data"]
        .dropna()
        .dt.date
        .tolist()
    )

    if len(datas) >= 2:
        diferencas = []

        for i in range(1, len(datas)):
            diferencas.append(
                (
                    datas[i]
                    - datas[i - 1]
                ).days
            )

        tempo_medio = (
            sum(diferencas)
            / len(diferencas)
        )

        tempo_medio_texto = (
            f"{tempo_medio:.1f} dias"
        )
    else:
        tempo_medio_texto = "—"

    pressoes = pd.to_numeric(
        historico_cliente["Pressão"],
        errors="coerce",
    ).dropna()

    if not pressoes.empty:
        media_pressao = (
            pressoes.mean()
        )

        media_pressao_texto = (
            f"{media_pressao:.2f} MCA"
        )
    else:
        media_pressao_texto = "—"

    return {
        "cliente": cliente,
        "qtd_os": qtd_os,
        "tempo_medio": tempo_medio_texto,
        "media_pressao": media_pressao_texto,
    }


def mostrar_kpis(kpis):
    if not kpis:
        st.info(
            "Não há O.S. suficientes para calcular os indicadores "
            "com os filtros atuais."
        )
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Cliente com mais registros",
            kpis["cliente"],
        )

    with col2:
        st.metric(
            "Quant. de O.S",
            kpis["qtd_os"],
        )

    with col3:
        st.metric(
            "Tempo Médio de Reclamação",
            kpis["tempo_medio"],
        )

    with col4:
        st.metric(
            "Média de Pressão",
            kpis["media_pressao"],
        )


# ============================================================
# MAPA
# ============================================================

def construir_mapa(
    df_registro,
    df_historico,
):
    mapa = folium.Map(
        location=[
            -5.0892,
            -42.8019,
        ],
        zoom_start=12,
        tiles=None,
        control_scale=True,
    )

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Mapa",
        control=True,
    ).add_to(mapa)

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/"
            "World_Imagery/MapServer/"
            "tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Satélite",
        control=True,
    ).add_to(mapa)

    folium.TileLayer(
        tiles=(
            "https://{s}.tile.opentopomap.org/"
            "{z}/{x}/{y}.png"
        ),
        attr="OpenTopoMap",
        name="Topográfico",
        control=True,
    ).add_to(mapa)

    if df_registro.empty:
        folium.LayerControl().add_to(mapa)
        return mapa

    bounds = []

    for _, registro in df_registro.iterrows():

        latitude = converter_float(
            registro["Latitude"]
        )

        longitude = converter_float(
            registro["Longitude"]
        )

        if not coordenada_valida(
            latitude,
            longitude,
        ):
            continue

        matricula = normalizar_texto(
            registro["Matrícula"]
        )

        historico_cliente = (
            historico_da_matricula(
                df_historico,
                matricula,
            )
        )

        qtd_os = len(
            historico_cliente
        )

        ultima_os = "—"

        if not historico_cliente.empty:
            historico_cliente = (
                historico_cliente.copy()
            )

            historico_cliente["_data"] = (
                pd.to_datetime(
                    historico_cliente[
                        "Data de Abertura"
                    ],
                    errors="coerce",
                )
            )

            historico_cliente = (
                historico_cliente
                .sort_values("_data")
            )

            ultimo = (
                historico_cliente.iloc[-1]
            )

            ultima_os = normalizar_texto(
                ultimo["N. O.S"]
            )

        resolvido = normalizar_sim_nao(
            registro["Resolvido"]
        )

        if resolvido == "SIM":
            cor = "green"
        elif resolvido == "NAO":
            cor = "red"
        else:
            cor = "blue"

        popup_html = f"""
        <div style="width: 320px;">
            <h4 style="margin-bottom:8px;">
                {escapar(matricula)}
            </h4>

            <b>Endereço:</b>
            {escapar(registro["Endereço"])}<br>

            <b>Bairro:</b>
            {escapar(registro["Bairro"])}<br>

            <b>Grau de Impacto:</b>
            {escapar(registro["Grau de Impacto"])}<br>

            <b>Resolvido:</b>
            {escapar(registro["Resolvido"])}<br>

            <b>Qtd. de O.S.:</b>
            {qtd_os}<br>

            <b>Última O.S.:</b>
            {escapar(ultima_os)}<br>

            <b>Data de Registro:</b>
            {escapar(formatar_data(registro["Data de Registro"]))}<br>

            <b>Responsável:</b>
            {escapar(registro["Responsável"])}<br>

            <b>Parecer:</b>
            {escapar(registro["Parecer"])}<br>

            <b>Tratativa 1:</b>
            {escapar(registro["Tratativa 1"])}<br>

            <b>Retorno:</b>
            {escapar(registro["Retorno"])}
        </div>
        """

        folium.Marker(
            location=[
                latitude,
                longitude,
            ],
            tooltip=matricula,
            popup=folium.Popup(
                popup_html,
                max_width=350,
            ),
            icon=folium.Icon(
                color=cor,
                icon="wrench",
                prefix="fa",
            ),
        ).add_to(mapa)

        bounds.append(
            [
                latitude,
                longitude,
            ]
        )

    if bounds:
        if len(bounds) == 1:
            mapa.location = bounds[0]
            mapa.zoom_start = 15
        else:
            mapa.fit_bounds(bounds)

    folium.LayerControl().add_to(mapa)

    return mapa


# ============================================================
# DIÁLOGOS
# ============================================================

def abrir_dialogo(nome, **dados):
    st.session_state.dialogo_melhorias = nome

    for chave, valor in dados.items():
        st.session_state[
            f"dialogo_{chave}"
        ] = valor


def fechar_dialogo():
    st.session_state.dialogo_melhorias = None

    chaves = [
        chave
        for chave in st.session_state.keys()
        if str(chave).startswith(
            "dialogo_"
        )
    ]

    for chave in chaves:
        if chave != "dialogo_melhorias":
            try:
                del st.session_state[chave]
            except Exception:
                pass


# ============================================================
# DIÁLOGO — NOVO REGISTRO
# ============================================================

@st.dialog("Novo Registro", width="large")
def dialogo_novo_registro(
    df_registro,
    df_historico,
):

    st.subheader(
        "Cadastro da melhoria"
    )

    matricula = st.text_input(
        "Matrícula *",
        key="novo_matricula",
    ).strip()

    endereco = st.text_input(
        "Endereço *",
        key="novo_endereco",
    ).strip()

    bairro = st.text_input(
        "Bairro *",
        key="novo_bairro",
    ).strip()

    col1, col2 = st.columns(2)

    with col1:
        latitude = st.text_input(
            "Latitude *",
            key="novo_latitude",
        )

    with col2:
        longitude = st.text_input(
            "Longitude *",
            key="novo_longitude",
        )

    st.divider()

    st.subheader(
        "Mapeamento"
    )

    parecer = st.text_area(
        "Parecer",
        key="novo_parecer",
    )

    data_registro = st.date_input(
        "Data de Registro *",
        value=date.today(),
        key="novo_data_registro",
    )

    col3, col4 = st.columns(2)

    with col3:
        grau_impacto = st.text_input(
            "Grau de Impacto",
            key="novo_grau_impacto",
        )

    with col4:
        resolvido = st.text_input(
            "Resolvido",
            key="novo_resolvido",
        )

    st.divider()

    st.subheader(
        "Tratativa"
    )

    tratativa_1 = st.text_area(
        "Tratativa 1",
        key="novo_tratativa_1",
    )

    col5, col6 = st.columns(2)

    with col5:
        executado = st.text_input(
            "Executado?",
            key="novo_executado",
        )

    with col6:
        responsavel = st.text_input(
            "Responsável",
            key="novo_responsavel",
        )

    retorno = st.text_area(
        "Retorno",
        key="novo_retorno",
    )

    st.divider()

    historico_existente = (
        historico_da_matricula(
            df_historico,
            matricula,
        )
        if matricula
        else pd.DataFrame()
    )

    matricula_ja_tem_registro = (
        matricula_possui_registro(
            df_registro,
            matricula,
        )
        if matricula
        else False
    )

    if matricula_ja_tem_registro:
        st.warning(
            "Já existe um registro principal para esta matrícula."
        )

    st.subheader(
        "O.S. inicial"
    )

    adicionar_nova_os = True

    if not historico_existente.empty:
        st.info(
            "Esta matrícula já possui O.S. cadastrada. "
            "Você pode cadastrar o registro principal "
            "sem adicionar uma nova O.S., ou adicionar outra O.S."
        )

        adicionar_nova_os = st.checkbox(
            "Adicionar uma nova O.S.",
            value=False,
            key="novo_adicionar_os_existente",
        )

    numero_os = ""
    data_abertura = datetime.now()
    pressao = ""
    pontual = "SIM"

    if (
        historico_existente.empty
        or adicionar_nova_os
    ):
        col7, col8 = st.columns(2)

        with col7:
            numero_os = st.text_input(
                "N. O.S *",
                placeholder="12345/2026-1",
                key="novo_numero_os",
            ).strip()

        with col8:
            data_abertura = st.datetime_input(
                "Data de Abertura *",
                value=datetime.now(),
                key="novo_data_abertura",
            )

        col9, col10 = st.columns(2)

        with col9:
            pressao = st.number_input(
                "Pressão (MCA) *",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="novo_pressao",
            )

        with col10:
            pontual = st.selectbox(
                "Pontual",
                ["SIM", "NÃO"],
                key="novo_pontual",
            )

    salvar = st.button(
        "💾 Salvar Registro",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    # --------------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------------

    if not matricula:
        st.error(
            "Informe a matrícula."
        )
        return

    if matricula_ja_tem_registro:
        st.error(
            "Já existe um registro para esta matrícula."
        )
        return

    if not endereco:
        st.error(
            "Informe o endereço."
        )
        return

    if not bairro:
        st.error(
            "Informe o bairro."
        )
        return

    if not coordenada_valida(
        latitude,
        longitude,
    ):
        st.error(
            "Latitude e longitude são obrigatórias "
            "e devem possuir valores válidos."
        )
        return

    if not historico_existente.empty:
        if adicionar_nova_os:
            if not validar_os(numero_os):
                st.error(
                    "N. O.S. inválida. Use o formato "
                    "12345/2026-1."
                )
                return

            if os_duplicada(
                df_historico,
                matricula,
                numero_os,
            ):
                st.error(
                    "Essa O.S. já está cadastrada para a matrícula."
                )
                return
    else:
        if not validar_os(numero_os):
            st.error(
                "É obrigatório cadastrar uma O.S. "
                "para uma matrícula sem histórico."
            )
            return

        if os_duplicada(
            df_historico,
            matricula,
            numero_os,
        ):
            st.error(
                "Essa O.S. já está cadastrada para a matrícula."
            )
            return

    # --------------------------------------------------------
    # SALVA REGISTRO PRINCIPAL
    # --------------------------------------------------------

    registro_id = gerar_id()

    dados_registro = {
        "ID": registro_id,
        "Matrícula": matricula,
        "Endereço": endereco,
        "Bairro": bairro,
        "Latitude": converter_float(latitude),
        "Longitude": converter_float(longitude),
        "Parecer": parecer,
        "Data de Registro": data_registro.strftime(
            "%Y-%m-%d"
        ),
        "Tratativa 1": tratativa_1,
        "Executado?": executado,
        "Retorno": retorno,
        "Responsável": responsavel,
        "Grau de Impacto": grau_impacto,
        "Resolvido": resolvido,
    }

    try:
        adicionar_registro(
            dados_registro
        )

        if (
            historico_existente.empty
            or adicionar_nova_os
        ):
            dados_os = {
                "ID": gerar_id(),
                "Matrícula": matricula,
                "N. O.S": numero_os,
                "Data de Abertura": (
                    data_abertura.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ),
                "Pressão": pressao,
                "Pontual": pontual,
            }

            adicionar_os(
                dados_os
            )

        st.cache_data.clear()
        st.success(
            "Registro salvo com sucesso."
        )

        fechar_dialogo()
        st.rerun()

    except Exception as exc:
        st.error(
            "Não foi possível salvar o registro."
        )
        st.exception(exc)


# ============================================================
# DIÁLOGO — EDITAR REGISTRO
# ============================================================

@st.dialog("Editar Registro", width="large")
def dialogo_editar_registro(
    registro,
    df_registro,
    df_historico,
):

    registro_id = normalizar_texto(
        registro["ID"]
    )

    matricula_original = normalizar_texto(
        registro["Matrícula"]
    )

    st.subheader(
        "Dados do registro"
    )

    matricula = st.text_input(
        "Matrícula *",
        value=matricula_original,
        key=f"edit_matricula_{registro_id}",
    ).strip()

    endereco = st.text_input(
        "Endereço *",
        value=normalizar_texto(
            registro["Endereço"]
        ),
        key=f"edit_endereco_{registro_id}",
    ).strip()

    bairro = st.text_input(
        "Bairro *",
        value=normalizar_texto(
            registro["Bairro"]
        ),
        key=f"edit_bairro_{registro_id}",
    ).strip()

    col1, col2 = st.columns(2)

    with col1:
        latitude = st.text_input(
            "Latitude *",
            value=normalizar_texto(
                registro["Latitude"]
            ),
            key=f"edit_latitude_{registro_id}",
        )

    with col2:
        longitude = st.text_input(
            "Longitude *",
            value=normalizar_texto(
                registro["Longitude"]
            ),
            key=f"edit_longitude_{registro_id}",
        )

    st.divider()

    st.subheader(
        "Mapeamento"
    )

    parecer = st.text_area(
        "Parecer",
        value=normalizar_texto(
            registro["Parecer"]
        ),
        key=f"edit_parecer_{registro_id}",
    )

    data_registro = st.date_input(
        "Data de Registro *",
        value=valor_data_para_widget(
            registro["Data de Registro"]
        ),
        key=f"edit_data_registro_{registro_id}",
    )

    col3, col4 = st.columns(2)

    with col3:
        grau_impacto = st.text_input(
            "Grau de Impacto",
            value=normalizar_texto(
                registro["Grau de Impacto"]
            ),
            key=f"edit_grau_impacto_{registro_id}",
        )

    with col4:
        resolvido = st.text_input(
            "Resolvido",
            value=normalizar_texto(
                registro["Resolvido"]
            ),
            key=f"edit_resolvido_{registro_id}",
        )

    st.divider()

    st.subheader(
        "Tratativa"
    )

    tratativa_1 = st.text_area(
        "Tratativa 1",
        value=normalizar_texto(
            registro["Tratativa 1"]
        ),
        key=f"edit_tratativa_1_{registro_id}",
    )

    col5, col6 = st.columns(2)

    with col5:
        executado = st.text_input(
            "Executado?",
            value=normalizar_texto(
                registro["Executado?"]
            ),
            key=f"edit_executado_{registro_id}",
        )

    with col6:
        responsavel = st.text_input(
            "Responsável",
            value=normalizar_texto(
                registro["Responsável"]
            ),
            key=f"edit_responsavel_{registro_id}",
        )

    retorno = st.text_area(
        "Retorno",
        value=normalizar_texto(
            registro["Retorno"]
        ),
        key=f"edit_retorno_{registro_id}",
    )

    st.divider()

    salvar = st.button(
        "💾 Salvar Alterações",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    # --------------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------------

    if not matricula:
        st.error(
            "Informe a matrícula."
        )
        return

    if matricula_possui_registro(
        df_registro,
        matricula,
        ignorar_id=registro_id,
    ):
        st.error(
            "Já existe outro registro principal "
            "para esta matrícula."
        )
        return

    if not endereco:
        st.error(
            "Informe o endereço."
        )
        return

    if not bairro:
        st.error(
            "Informe o bairro."
        )
        return

    if not coordenada_valida(
        latitude,
        longitude,
    ):
        st.error(
            "Latitude e longitude são obrigatórias "
            "e devem possuir valores válidos."
        )
        return

    dados_registro = {
        "ID": registro_id,
        "Matrícula": matricula,
        "Endereço": endereco,
        "Bairro": bairro,
        "Latitude": converter_float(latitude),
        "Longitude": converter_float(longitude),
        "Parecer": parecer,
        "Data de Registro": data_registro.strftime(
            "%Y-%m-%d"
        ),
        "Tratativa 1": tratativa_1,
        "Executado?": executado,
        "Retorno": retorno,
        "Responsável": responsavel,
        "Grau de Impacto": grau_impacto,
        "Resolvido": resolvido,
    }

    try:
        atualizar_registro(
            registro_id,
            dados_registro,
        )

        # ----------------------------------------------------
        # MIGRA HISTÓRICO CASO A MATRÍCULA TENHA SIDO ALTERADA
        # ----------------------------------------------------

        if (
            matricula_original.upper()
            != matricula.upper()
        ):
            _, historico_ws = obter_planilhas()

            historico_original = (
                historico_da_matricula(
                    df_historico,
                    matricula_original,
                )
            )

            for _, linha in historico_original.iterrows():

                os_id = normalizar_texto(
                    linha["ID"]
                )

                linha_atualizada = {
                    "ID": os_id,
                    "Matrícula": matricula,
                    "N. O.S": normalizar_texto(
                        linha["N. O.S"]
                    ),
                    "Data de Abertura": normalizar_texto(
                        linha["Data de Abertura"]
                    ),
                    "Pressão": normalizar_texto(
                        linha["Pressão"]
                    ),
                    "Pontual": normalizar_texto(
                        linha["Pontual"]
                    ),
                }

                atualizar_os(
                    os_id,
                    linha_atualizada,
                )

        st.success(
            "Registro atualizado com sucesso."
        )

        fechar_dialogo()
        st.rerun()

    except Exception as exc:
        st.error(
            "Não foi possível atualizar o registro."
        )
        st.exception(exc)


# ============================================================
# DIÁLOGO — VISUALIZAR MATRÍCULA
# ============================================================

@st.dialog("Registro da Matrícula", width="large")
def dialogo_matricula(
    matricula,
    df_registro,
    df_historico,
):

    registro_df = registro_da_matricula(
        df_registro,
        matricula,
    )

    historico_df = historico_da_matricula(
        df_historico,
        matricula,
    )

    if registro_df.empty:
        st.warning(
            "O registro principal desta matrícula "
            "não está cadastrado."
        )
    else:
        registro = registro_df.iloc[0]

        st.subheader(
            f"Matrícula: {matricula}"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(
                f"**Endereço:** "
                f"{normalizar_texto(registro['Endereço'])}"
            )

            st.markdown(
                f"**Bairro:** "
                f"{normalizar_texto(registro['Bairro'])}"
            )

            st.markdown(
                f"**Latitude:** "
                f"{normalizar_texto(registro['Latitude'])}"
            )

            st.markdown(
                f"**Longitude:** "
                f"{normalizar_texto(registro['Longitude'])}"
            )

            st.markdown(
                f"**Data de Registro:** "
                f"{formatar_data(registro['Data de Registro'])}"
            )

            st.markdown(
                f"**Responsável:** "
                f"{normalizar_texto(registro['Responsável']) or '—'}"
            )

        with col2:
            st.markdown(
                f"**Grau de Impacto:** "
                f"{normalizar_texto(registro['Grau de Impacto']) or '—'}"
            )

            st.markdown(
                f"**Resolvido:** "
                f"{normalizar_texto(registro['Resolvido']) or '—'}"
            )

            st.markdown(
                f"**Executado?:** "
                f"{normalizar_texto(registro['Executado?']) or '—'}"
            )

            st.markdown(
                f"**Parecer:** "
                f"{normalizar_texto(registro['Parecer']) or '—'}"
            )

        st.markdown(
            f"**Tratativa 1:** "
            f"{normalizar_texto(registro['Tratativa 1']) or '—'}"
        )

        st.markdown(
            f"**Retorno:** "
            f"{normalizar_texto(registro['Retorno']) or '—'}"
        )

        st.divider()

        col_editar, col_excluir = st.columns(2)

        with col_editar:
            if st.button(
                "✏️ Editar Registro",
                use_container_width=True,
                key=f"popup_editar_{matricula}",
            ):
                fechar_dialogo()
                abrir_dialogo(
                    "editar",
                    registro=registro.to_dict(),
                )
                st.rerun()

        with col_excluir:
            if st.button(
                "🗑️ Excluir Registro",
                use_container_width=True,
                key=f"popup_excluir_{matricula}",
            ):
                abrir_dialogo(
                    "confirmar_exclusao_registro",
                    registro=registro.to_dict(),
                )
                st.rerun()

    st.divider()

    st.subheader(
        f"O.S. da Matrícula ({len(historico_df)})"
    )

    if historico_df.empty:
        st.info(
            "Nenhuma O.S. cadastrada."
        )
    else:
        historico_exibicao = (
            historico_df.copy()
        )

        historico_exibicao["_data"] = (
            pd.to_datetime(
                historico_exibicao[
                    "Data de Abertura"
                ],
                errors="coerce",
            )
        )

        historico_exibicao = (
            historico_exibicao
            .sort_values(
                "_data",
                ascending=False,
            )
        )

        for _, os_row in historico_exibicao.iterrows():

            os_id = normalizar_texto(
                os_row["ID"]
            )

            with st.container(
                border=True
            ):
                col_a, col_b, col_c = st.columns(
                    [2, 2, 1]
                )

                with col_a:
                    st.markdown(
                        f"**N. O.S:** "
                        f"{normalizar_texto(os_row['N. O.S'])}"
                    )

                    st.caption(
                        formatar_data_hora(
                            os_row[
                                "Data de Abertura"
                            ]
                        )
                    )

                with col_b:
                    st.markdown(
                        f"**Pressão:** "
                        f"{normalizar_texto(os_row['Pressão'])} MCA"
                    )

                    st.markdown(
                        f"**Pontual:** "
                        f"{normalizar_texto(os_row['Pontual'])}"
                    )

                with col_c:
                    if st.button(
                        "✏️",
                        key=f"editar_os_{os_id}",
                        help="Editar O.S.",
                    ):
                        fechar_dialogo()
                        abrir_dialogo(
                            "editar_os",
                            os_id=os_id,
                            matricula=matricula,
                        )
                        st.rerun()

                    if st.button(
                        "🗑️",
                        key=f"excluir_os_{os_id}",
                        help="Excluir O.S.",
                    ):
                        abrir_dialogo(
                            "confirmar_exclusao_os",
                            os_id=os_id,
                            matricula=matricula,
                        )
                        st.rerun()

    st.divider()

    col_add, col_download = st.columns(2)

    with col_add:
        if st.button(
            "＋ Adicionar Registro",
            type="primary",
            use_container_width=True,
            key=f"adicionar_os_{matricula}",
        ):
            fechar_dialogo()
            abrir_dialogo(
                "nova_os",
                matricula=matricula,
            )
            st.rerun()

    with col_download:
        registro_export = registro_df.copy()

        historico_export = historico_df.copy()

        arquivo = gerar_excel_cliente(
            registro_export,
            historico_export,
        )

        st.download_button(
            "⬇️ Baixar Excel",
            data=arquivo,
            file_name=(
                f"mapeamento_"
                f"{matricula.replace('/', '_')}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
            key=f"download_cliente_{matricula}",
        )


# ============================================================
# DIÁLOGO — NOVA O.S.
# ============================================================

@st.dialog("Adicionar O.S.", width="medium")
def dialogo_nova_os(
    matricula,
    df_historico,
):

    st.write(
        f"**Matrícula:** {matricula}"
    )

    numero_os = st.text_input(
        "N. O.S *",
        placeholder="12345/2026-1",
        key=f"nova_os_numero_{matricula}",
    ).strip()

    data_abertura = st.datetime_input(
        "Data de Abertura *",
        value=datetime.now(),
        key=f"nova_os_data_{matricula}",
    )

    pressao = st.number_input(
        "Pressão (MCA) *",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key=f"nova_os_pressao_{matricula}",
    )

    pontual = st.selectbox(
        "Pontual",
        ["SIM", "NÃO"],
        key=f"nova_os_pontual_{matricula}",
    )

    salvar = st.button(
        "💾 Salvar O.S.",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    if not validar_os(numero_os):
        st.error(
            "N. O.S. inválida. Use o formato "
            "12345/2026-1."
        )
        return

    if os_duplicada(
        df_historico,
        matricula,
        numero_os,
    ):
        st.error(
            "Essa O.S. já está cadastrada para esta matrícula."
        )
        return

    dados_os = {
        "ID": gerar_id(),
        "Matrícula": matricula,
        "N. O.S": numero_os,
        "Data de Abertura": (
            data_abertura.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
        "Pressão": pressao,
        "Pontual": pontual,
    }

    try:
        adicionar_os(
            dados_os
        )

        st.success(
            "O.S. adicionada com sucesso."
        )

        fechar_dialogo()
        st.rerun()

    except Exception as exc:
        st.error(
            "Não foi possível adicionar a O.S."
        )
        st.exception(exc)


# ============================================================
# DIÁLOGO — EDITAR O.S.
# ============================================================

@st.dialog("Editar O.S.", width="medium")
def dialogo_editar_os(
    os_id,
    matricula,
    df_historico,
):

    historico_os = df_historico[
        df_historico["ID"]
        .astype(str)
        ==
        str(os_id)
    ]

    if historico_os.empty:
        st.error(
            "O.S. não encontrada."
        )
        return

    os_atual = historico_os.iloc[0]

    numero_os = st.text_input(
        "N. O.S *",
        value=normalizar_texto(
            os_atual["N. O.S"]
        ),
        key=f"edit_os_numero_{os_id}",
    ).strip()

    data_abertura = st.datetime_input(
        "Data de Abertura *",
        value=valor_datetime_para_widget(
            os_atual["Data de Abertura"]
        ),
        key=f"edit_os_data_{os_id}",
    )

    pressao_atual = converter_float(
        os_atual["Pressão"]
    )

    if pressao_atual is None:
        pressao_atual = 0.0

    pressao = st.number_input(
        "Pressão (MCA) *",
        min_value=0.0,
        value=float(pressao_atual),
        step=0.01,
        format="%.2f",
        key=f"edit_os_pressao_{os_id}",
    )

    pontual_atual = normalizar_texto(
        os_atual["Pontual"]
    )

    if pontual_atual not in ["SIM", "NÃO"]:
        pontual_atual = "SIM"

    pontual = st.selectbox(
        "Pontual",
        ["SIM", "NÃO"],
        index=[
            "SIM",
            "NÃO",
        ].index(pontual_atual),
        key=f"edit_os_pontual_{os_id}",
    )

    salvar = st.button(
        "💾 Salvar Alterações",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    if not validar_os(numero_os):
        st.error(
            "N. O.S. inválida. Use o formato "
            "12345/2026-1."
        )
        return

    if os_duplicada(
        df_historico,
        matricula,
        numero_os,
        ignorar_id=os_id,
    ):
        st.error(
            "Essa O.S. já está cadastrada para esta matrícula."
        )
        return

    dados_os = {
        "ID": os_id,
        "Matrícula": matricula,
        "N. O.S": numero_os,
        "Data de Abertura": (
            data_abertura.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
        "Pressão": pressao,
        "Pontual": pontual,
    }

    try:
        atualizar_os(
            os_id,
            dados_os,
        )

        st.success(
            "O.S. atualizada com sucesso."
        )

        fechar_dialogo()
        st.rerun()

    except Exception as exc:
        st.error(
            "Não foi possível atualizar a O.S."
        )
        st.exception(exc)


# ============================================================
# DIÁLOGO — CONFIRMAR EXCLUSÃO DO REGISTRO
# ============================================================

@st.dialog("Confirmar exclusão")
def dialogo_confirmar_exclusao_registro(
    registro,
):

    matricula = normalizar_texto(
        registro["Matrícula"]
    )

    st.warning(
        f"Tem certeza que deseja excluir o registro "
        f"da matrícula **{matricula}**?"
    )

    st.info(
        "As O.S. e o histórico dessa matrícula "
        "serão mantidos."
    )

    col1, col2 = st.columns(2)

    with col1:
        confirmar = st.button(
            "🗑️ Excluir",
            type="primary",
            use_container_width=True,
        )

    with col2:
        cancelar = st.button(
            "Cancelar",
            use_container_width=True,
        )

    if cancelar:
        fechar_dialogo()
        st.rerun()

    if confirmar:
        try:
            excluir_registro(
                registro["ID"]
            )

            st.success(
                "Registro excluído. "
                "O histórico foi preservado."
            )

            fechar_dialogo()
            st.rerun()

        except Exception as exc:
            st.error(
                "Não foi possível excluir o registro."
            )
            st.exception(exc)


# ============================================================
# DIÁLOGO — CONFIRMAR EXCLUSÃO DA O.S.
# ============================================================

@st.dialog("Confirmar exclusão da O.S.")
def dialogo_confirmar_exclusao_os(
    os_id,
    matricula,
    df_historico,
):

    historico_cliente = (
        historico_da_matricula(
            df_historico,
            matricula,
        )
    )

    os_atual = df_historico[
        df_historico["ID"]
        .astype(str)
        ==
        str(os_id)
    ]

    if os_atual.empty:
        st.error(
            "O.S. não encontrada."
        )
        return

    numero_os = normalizar_texto(
        os_atual.iloc[0]["N. O.S"]
    )

    if len(historico_cliente) <= 1:
        st.warning(
            "Esta matrícula possui apenas uma O.S."
        )

        st.info(
            "A última O.S. não pode ser excluída, "
            "pois toda matrícula ativa deve permanecer "
            "com pelo menos uma O.S."
        )

        if st.button(
            "Fechar",
            use_container_width=True,
        ):
            fechar_dialogo()
            st.rerun()

        return

    st.warning(
        f"Tem certeza que deseja excluir a O.S. "
        f"**{numero_os}**?"
    )

    st.write(
        "Essa operação não poderá ser desfeita."
    )

    col1, col2 = st.columns(2)

    with col1:
        confirmar = st.button(
            "🗑️ Excluir O.S.",
            type="primary",
            use_container_width=True,
        )

    with col2:
        cancelar = st.button(
            "Cancelar",
            use_container_width=True,
        )

    if cancelar:
        fechar_dialogo()
        st.rerun()

    if confirmar:
        try:
            excluir_os(
                os_id
            )

            st.success(
                "O.S. excluída com sucesso."
            )

            fechar_dialogo()
            st.rerun()

        except Exception as exc:
            st.error(
                "Não foi possível excluir a O.S."
            )
            st.exception(exc)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🗺️ Mapeamento de Melhorias"
    )

    st.divider()

    if st.button(
        "＋ Novo Registro",
        type="primary",
        use_container_width=True,
    ):
        fechar_dialogo()
        abrir_dialogo("novo")
        st.rerun()

    if st.button(
        "🏠 Voltar ao Menu Principal",
        use_container_width=True,
    ):
        st.switch_page(
            "app.py"
        )

    st.divider()

    st.markdown(
        "### Filtros"
    )


# ============================================================
# CARREGAMENTO
# ============================================================

(
    registro_ws,
    historico_ws,
    df_registro,
    df_historico,
) = carregar_dados()


# ============================================================
# SIDEBAR — FILTROS
# ============================================================

df_registro_filtrado, df_historico_filtrado = (
    aplicar_filtros(
        df_registro,
        df_historico,
    )
)


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "🗺️ Mapeamento de Melhorias"
)

st.caption(
    "Cadastro, acompanhamento e histórico das melhorias "
    "relacionadas às matrículas."
)


# ============================================================
# EXPORTAÇÃO GLOBAL
# ============================================================

arquivo_exportacao = gerar_excel(
    df_registro_filtrado,
    df_historico_filtrado,
)

st.download_button(
    "⬇️ Exportar filtrado",
    data=arquivo_exportacao,
    file_name=(
        "mapeamento_de_melhorias_filtrado.xlsx"
    ),
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    use_container_width=False,
)


# ============================================================
# KPIs
# ============================================================

st.markdown("### Indicadores")

kpis = calcular_kpis(
    df_registro_filtrado,
    df_historico_filtrado,
)

mostrar_kpis(kpis)


# ============================================================
# MAPA
# ============================================================

st.markdown("### Mapa")

mapa = construir_mapa(
    df_registro_filtrado,
    df_historico_filtrado,
)

st_folium(
    mapa,
    width=None,
    height=520,
    returned_objects=[],
)


# ============================================================
# LISTA
# ============================================================

st.markdown(
    "### Registros"
)

df_lista = ordenar_registros(
    df_registro_filtrado,
    df_historico_filtrado,
)

if df_lista.empty:

    st.info(
        "Nenhum registro encontrado com os filtros atuais."
    )

else:

    total_registros = len(
        df_lista
    )

    total_paginas = max(
        1,
        math.ceil(
            total_registros
            / REGISTROS_POR_PAGINA
        ),
    )

    pagina_atual = st.session_state.get(
        "pagina_mapeamento",
        1,
    )

    if pagina_atual > total_paginas:
        pagina_atual = total_paginas

    col_prev, col_info, col_next = st.columns(
        [1, 2, 1]
    )

    with col_prev:
        if st.button(
            "← Anterior",
            disabled=pagina_atual <= 1,
            use_container_width=True,
        ):
            st.session_state[
                "pagina_mapeamento"
            ] = max(
                1,
                pagina_atual - 1,
            )
            st.rerun()

    with col_info:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px;'>"
            f"Página {pagina_atual} de {total_paginas}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_next:
        if st.button(
            "Próxima →",
            disabled=pagina_atual >= total_paginas,
            use_container_width=True,
        ):
            st.session_state[
                "pagina_mapeamento"
            ] = min(
                total_paginas,
                pagina_atual + 1,
            )
            st.rerun()

    inicio = (
        pagina_atual - 1
    ) * REGISTROS_POR_PAGINA

    fim = (
        inicio
        + REGISTROS_POR_PAGINA
    )

    pagina_df = df_lista.iloc[
        inicio:fim
    ]

    for _, registro in pagina_df.iterrows():

        matricula = normalizar_texto(
            registro["Matrícula"]
        )

        historico_cliente = (
            historico_da_matricula(
                df_historico_filtrado,
                matricula,
            )
        )

        qtd_os = len(
            historico_cliente
        )

        ultima_os = "—"

        if not historico_cliente.empty:

            aux = historico_cliente.copy()

            aux["_data"] = pd.to_datetime(
                aux["Data de Abertura"],
                errors="coerce",
            )

            aux = aux.sort_values(
                "_data"
            )

            ultima_os = normalizar_texto(
                aux.iloc[-1]["N. O.S"]
            )

        with st.container(
            border=True
        ):

            col1, col2, col3, col4, col5 = st.columns(
                [1.7, 2.5, 1.7, 1.1, 1.2]
            )

            with col1:
                if st.button(
                    matricula,
                    key=f"abrir_matricula_{registro['ID']}",
                    type="secondary",
                    use_container_width=True,
                ):
                    fechar_dialogo()
                    abrir_dialogo(
                        "matricula",
                        matricula=matricula,
                    )
                    st.rerun()

            with col2:
                st.markdown(
                    f"**{normalizar_texto(registro['Endereço'])}**"
                )

                st.caption(
                    normalizar_texto(
                        registro["Bairro"]
                    )
                )

            with col3:
                st.caption(
                    "Grau de Impacto"
                )

                st.write(
                    normalizar_texto(
                        registro["Grau de Impacto"]
                    )
                    or "—"
                )

            with col4:
                st.caption(
                    "O.S."
                )

                st.write(
                    qtd_os
                )

            with col5:
                st.caption(
                    "Última O.S."
                )

                st.write(
                    ultima_os
                )


# ============================================================
# ROTEAMENTO DOS DIÁLOGOS
# ============================================================

dialogo_atual = st.session_state.get(
    "dialogo_melhorias"
)


if dialogo_atual == "novo":

    dialogo_novo_registro(
        df_registro,
        df_historico,
    )

elif dialogo_atual == "editar":

    registro_dialogo = st.session_state.get(
        "dialogo_registro"
    )

    if registro_dialogo:
        dialogo_editar_registro(
            registro_dialogo,
            df_registro,
            df_historico,
        )

elif dialogo_atual == "matricula":

    matricula_dialogo = st.session_state.get(
        "dialogo_matricula"
    )

    if matricula_dialogo:
        dialogo_matricula(
            matricula_dialogo,
            df_registro,
            df_historico,
        )

elif dialogo_atual == "nova_os":

    matricula_dialogo = st.session_state.get(
        "dialogo_matricula"
    )

    if matricula_dialogo:
        dialogo_nova_os(
            matricula_dialogo,
            df_historico,
        )

elif dialogo_atual == "editar_os":

    os_id_dialogo = st.session_state.get(
        "dialogo_os_id"
    )

    matricula_dialogo = st.session_state.get(
        "dialogo_matricula"
    )

    if os_id_dialogo and matricula_dialogo:
        dialogo_editar_os(
            os_id_dialogo,
            matricula_dialogo,
            df_historico,
        )

elif (
    dialogo_atual
    == "confirmar_exclusao_registro"
):

    registro_dialogo = st.session_state.get(
        "dialogo_registro"
    )

    if registro_dialogo:
        dialogo_confirmar_exclusao_registro(
            registro_dialogo
        )

elif (
    dialogo_atual
    == "confirmar_exclusao_os"
):

    os_id_dialogo = st.session_state.get(
        "dialogo_os_id"
    )

    matricula_dialogo = st.session_state.get(
        "dialogo_matricula"
    )

    if os_id_dialogo and matricula_dialogo:
        dialogo_confirmar_exclusao_os(
            os_id_dialogo,
            matricula_dialogo,
            df_historico,
        )
