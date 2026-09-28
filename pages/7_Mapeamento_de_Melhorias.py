import io
import json
import math
import html
from datetime import date, datetime
from uuid import uuid4

import folium
import gspread
import pandas as pd
import streamlit as st

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium

from auth import verificar_autenticacao


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

verificar_autenticacao()

if not st.session_state.get("autenticado"):
    st.warning(
        "Você precisa estar autenticado para acessar este módulo."
    )

    if st.button("🏠 Voltar ao Menu Principal"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# CONFIGURAÇÃO DA PLANILHA
# ============================================================

# ATENÇÃO:
# Esta planilha é EXCLUSIVA do Módulo 7.
# Não utilizar o ID da planilha do Módulo 1.

SPREADSHEET_ID = st.secrets.get(
    "MAPEAMENTO_MELHORIAS_SPREADSHEET_ID",
    "",
)

REGISTRO_SHEET = "Registro"
HISTORICO_SHEET = "Historico"


# ============================================================
# ESTRUTURA DA ABA REGISTRO
# ============================================================

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


# ============================================================
# ESTRUTURA DA ABA HISTORICO
# ============================================================

HISTORICO_HEADERS = [
    "ID",
    "Matrícula",
    "N. O.S",
    "Data de Abertura",
    "Pressão",
    "Pontual",
]


REGISTROS_POR_PAGINA = 10


# ============================================================
# ESTILO
# ============================================================

st.markdown(
    """
    <style>

    .kpi-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px;
        padding: 15px 18px;
        min-height: 115px;
        background: rgba(128,128,128,0.04);
    }

    .kpi-title {
        font-size: 0.82rem;
        opacity: 0.70;
        margin-bottom: 7px;
    }

    .kpi-value {
        font-size: 1.35rem;
        font-weight: 700;
        line-height: 1.25;
    }

    .registro-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
    }

    .registro-label {
        font-size: 0.75rem;
        opacity: 0.65;
    }

    .registro-value {
        font-weight: 600;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# UTILITÁRIOS
# ============================================================

def texto(valor):
    if valor is None:
        return ""

    if isinstance(valor, float) and math.isnan(valor):
        return ""

    return str(valor).strip()


def escape(valor):
    return html.escape(texto(valor))


def gerar_id():
    return uuid4().hex[:12]


def converter_float(valor):
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        if isinstance(valor, float) and math.isnan(valor):
            return None

        return float(valor)

    valor = texto(valor)

    if not valor:
        return None

    valor = valor.replace(",", ".")

    try:
        return float(valor)
    except ValueError:
        return None


def coordenadas_validas(latitude, longitude):
    lat = converter_float(latitude)
    lon = converter_float(longitude)

    if lat is None or lon is None:
        return False

    return (
        -90 <= lat <= 90
        and -180 <= lon <= 180
    )


def formatar_data(valor):
    if not texto(valor):
        return "—"

    try:
        data = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(data):
            return texto(valor)

        return data.strftime("%d/%m/%Y")

    except Exception:
        return texto(valor)


def formatar_data_hora(valor):
    if not texto(valor):
        return "—"

    try:
        data = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(data):
            return texto(valor)

        return data.strftime(
            "%d/%m/%Y %H:%M"
        )

    except Exception:
        return texto(valor)


def valor_data(valor):
    if not texto(valor):
        return date.today()

    try:
        data = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(data):
            return date.today()

        return data.date()

    except Exception:
        return date.today()


def valor_datetime(valor):
    if not texto(valor):
        return datetime.now()

    try:
        data = pd.to_datetime(
            valor,
            errors="coerce",
        )

        if pd.isna(data):
            return datetime.now()

        return data.to_pydatetime()

    except Exception:
        return datetime.now()


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google_sheets(spreadsheet_id):

    if not spreadsheet_id:
        raise ValueError(
            "MAPEAMENTO_MELHORIAS_SPREADSHEET_ID "
            "não foi configurado nos secrets."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials_dict = json.loads(
        st.secrets["gcp_json"]
    )

    credentials = (
        Credentials.from_service_account_info(
            credentials_dict,
            scopes=scopes,
        )
    )

    gc = gspread.authorize(
        credentials
    )

    return gc.open_by_key(
        spreadsheet_id
    )


def garantir_cabecalho(
    worksheet,
    headers,
):
    valores = worksheet.get_all_values()

    if not valores:
        worksheet.append_row(
            headers,
            value_input_option="USER_ENTERED",
        )
        return

    atual = [
        texto(x)
        for x in valores[0]
    ]

    if atual != headers:
        worksheet.clear()

        worksheet.append_row(
            headers,
            value_input_option="USER_ENTERED",
        )


@st.cache_resource
def obter_planilhas():

    try:
        planilha = conectar_google_sheets(
            SPREADSHEET_ID
        )

        try:
            registro_ws = planilha.worksheet(
                REGISTRO_SHEET
            )
        except gspread.WorksheetNotFound:
            registro_ws = planilha.add_worksheet(
                title=REGISTRO_SHEET,
                rows=1000,
                cols=len(REGISTRO_HEADERS),
            )

        try:
            historico_ws = planilha.worksheet(
                HISTORICO_SHEET
            )
        except gspread.WorksheetNotFound:
            historico_ws = planilha.add_worksheet(
                title=HISTORICO_SHEET,
                rows=2000,
                cols=len(HISTORICO_HEADERS),
            )

        garantir_cabecalho(
            registro_ws,
            REGISTRO_HEADERS,
        )

        garantir_cabecalho(
            historico_ws,
            HISTORICO_HEADERS,
        )

        return (
            registro_ws,
            historico_ws,
        )

    except Exception as exc:

        st.error(
            "Não foi possível acessar a planilha "
            "**Mapeamento de Melhorias**."
        )

        st.exception(exc)

        st.info(
            "Verifique o compartilhamento da planilha "
            "com a conta de serviço e o valor de "
            "`MAPEAMENTO_MELHORIAS_SPREADSHEET_ID`."
        )

        st.stop()


def carregar_worksheet(
    worksheet,
    headers,
):

    registros = worksheet.get_all_records(
        default_blank=""
    )

    if not registros:
        return pd.DataFrame(
            columns=headers
        )

    df = pd.DataFrame(
        registros
    )

    for coluna in headers:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[headers].copy()


def carregar_dados():

    registro_ws, historico_ws = (
        obter_planilhas()
    )

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

def localizar_linha(
    worksheet,
    identificador,
):

    try:
        celula = worksheet.find(
            str(identificador)
        )

        if celula:
            return celula.row

    except Exception:
        pass

    return None


# ============================================================
# CRUD REGISTRO
# ============================================================

def registro_para_lista(
    dados,
):
    return [
        dados.get(
            coluna,
            "",
        )
        for coluna in REGISTRO_HEADERS
    ]


def adicionar_registro(
    dados,
):

    registro_ws, _ = (
        obter_planilhas()
    )

    registro_ws.append_row(
        registro_para_lista(
            dados
        ),
        value_input_option="USER_ENTERED",
    )


def atualizar_registro(
    registro_id,
    dados,
):

    registro_ws, _ = (
        obter_planilhas()
    )

    linha = localizar_linha(
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
            registro_para_lista(
                dados
            )
        ],
        value_input_option="USER_ENTERED",
    )


def excluir_registro(
    registro_id,
):

    registro_ws, _ = (
        obter_planilhas()
    )

    linha = localizar_linha(
        registro_ws,
        registro_id,
    )

    if linha is None:
        raise ValueError(
            "Registro não encontrado."
        )

    registro_ws.delete_rows(
        linha
    )


# ============================================================
# CRUD O.S.
# ============================================================

def os_para_lista(
    dados,
):
    return [
        dados.get(
            coluna,
            "",
        )
        for coluna in HISTORICO_HEADERS
    ]


def adicionar_os(
    dados,
):

    _, historico_ws = (
        obter_planilhas()
    )

    historico_ws.append_row(
        os_para_lista(
            dados
        ),
        value_input_option="USER_ENTERED",
    )


def atualizar_os(
    os_id,
    dados,
):

    _, historico_ws = (
        obter_planilhas()
    )

    linha = localizar_linha(
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
            os_para_lista(
                dados
            )
        ],
        value_input_option="USER_ENTERED",
    )


def excluir_os(
    os_id,
):

    _, historico_ws = (
        obter_planilhas()
    )

    linha = localizar_linha(
        historico_ws,
        os_id,
    )

    if linha is None:
        raise ValueError(
            "O.S. não encontrada."
        )

    historico_ws.delete_rows(
        linha
    )


# ============================================================
# CONSULTAS
# ============================================================

def historico_da_matricula(
    df,
    matricula,
):

    if df.empty:
        return df.copy()

    return df[
        df["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        texto(matricula).upper()
    ].copy()


def registro_da_matricula(
    df,
    matricula,
):

    if df.empty:
        return df.copy()

    return df[
        df["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        texto(matricula).upper()
    ].copy()


def matricula_possui_registro(
    df,
    matricula,
    ignorar_id=None,
):

    if df.empty:
        return False

    mascara = (
        df["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        texto(matricula).upper()
    )

    if ignorar_id is not None:
        mascara &= (
            df["ID"].astype(str)
            != str(ignorar_id)
        )

    return mascara.any()


def os_duplicada(
    df,
    matricula,
    numero_os,
    ignorar_id=None,
):

    if df.empty:
        return False

    mascara = (
        df["Matrícula"]
        .astype(str)
        .str.strip()
        .str.upper()
        ==
        texto(matricula).upper()
    ) & (
        df["N. O.S"]
        .astype(str)
        .str.strip()
        ==
        texto(numero_os)
    )

    if ignorar_id is not None:
        mascara &= (
            df["ID"].astype(str)
            != str(ignorar_id)
        )

    return mascara.any()


# ============================================================
# EXPORTAÇÃO
# ============================================================

def gerar_excel(
    df_registro,
    df_historico,
):

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

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
    registro,
    historico,
):

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        registro.to_excel(
            writer,
            sheet_name="Resumo",
            index=False,
        )

        historico.to_excel(
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

    # --------------------------------------------------------
    # DATA DE ABERTURA
    # --------------------------------------------------------

    if not historico.empty:

        historico["_data_abertura"] = (
            pd.to_datetime(
                historico["Data de Abertura"],
                errors="coerce",
            )
        )

        datas = (
            historico["_data_abertura"]
            .dropna()
        )

        if not datas.empty:

            data_min = datas.min().date()
            data_max = datas.max().date()

            periodo = st.sidebar.date_input(
                "Data de Abertura",
                value=(
                    data_min,
                    data_max,
                ),
                min_value=data_min,
                max_value=data_max,
            )

            if (
                isinstance(periodo, tuple)
                and len(periodo) == 2
            ):

                inicio, fim = periodo

                historico = historico[
                    (
                        historico[
                            "_data_abertura"
                        ].dt.date
                        >= inicio
                    )
                    &
                    (
                        historico[
                            "_data_abertura"
                        ].dt.date
                        <= fim
                    )
                ]

                matriculas = set(
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
                    .isin(matriculas)
                ]

    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    bairros = sorted(
        [
            x
            for x in (
                registro["Bairro"]
                .astype(str)
                .str.strip()
                .unique()
            )
            if x
        ]
    )

    bairro = st.sidebar.multiselect(
        "Bairro",
        bairros,
    )

    if bairro:
        registro = registro[
            registro["Bairro"]
            .astype(str)
            .str.strip()
            .isin(bairro)
        ]

    # --------------------------------------------------------
    # MATRÍCULA
    # --------------------------------------------------------

    matriculas = sorted(
        [
            x
            for x in (
                registro["Matrícula"]
                .astype(str)
                .str.strip()
                .unique()
            )
            if x
        ]
    )

    matricula = st.sidebar.multiselect(
        "Matrícula",
        matriculas,
    )

    if matricula:
        registro = registro[
            registro["Matrícula"]
            .astype(str)
            .str.strip()
            .isin(matricula)
        ]

    # --------------------------------------------------------
    # GRAU DE IMPACTO
    # --------------------------------------------------------

    impactos = sorted(
        [
            x
            for x in (
                registro["Grau de Impacto"]
                .astype(str)
                .str.strip()
                .unique()
            )
            if x
        ]
    )

    impacto = st.sidebar.multiselect(
        "Grau de Impacto",
        impactos,
    )

    if impacto:
        registro = registro[
            registro["Grau de Impacto"]
            .astype(str)
            .str.strip()
            .isin(impacto)
        ]

    # --------------------------------------------------------
    # RESOLVIDO
    # --------------------------------------------------------

    resolvidos = sorted(
        [
            x
            for x in (
                registro["Resolvido"]
                .astype(str)
                .str.strip()
                .unique()
            )
            if x
        ]
    )

    resolvido = st.sidebar.multiselect(
        "Resolvido",
        resolvidos,
    )

    if resolvido:
        registro = registro[
            registro["Resolvido"]
            .astype(str)
            .str.strip()
            .isin(resolvido)
        ]

    # --------------------------------------------------------
    # EXECUTADO
    # --------------------------------------------------------

    executados = sorted(
        [
            x
            for x in (
                registro["Executado?"]
                .astype(str)
                .str.strip()
                .unique()
            )
            if x
        ]
    )

    executado = st.sidebar.multiselect(
        "Executado",
        executados,
    )

    if executado:
        registro = registro[
            registro["Executado?"]
            .astype(str)
            .str.strip()
            .isin(executado)
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

        matriculas_busca = set()

        mascara_matricula = (
            registro["Matrícula"]
            .astype(str)
            .str.lower()
            .str.contains(
                termo,
                na=False,
                regex=False,
            )
        )

        mascara_endereco = (
            registro["Endereço"]
            .astype(str)
            .str.lower()
            .str.contains(
                termo,
                na=False,
                regex=False,
            )
        )

        matriculas_busca.update(
            registro.loc[
                mascara_matricula,
                "Matrícula",
            ].astype(str)
        )

        matriculas_busca.update(
            registro.loc[
                mascara_endereco,
                "Matrícula",
            ].astype(str)
        )

        if not historico.empty:

            mascara_os = (
                historico["N. O.S"]
                .astype(str)
                .str.lower()
                .str.contains(
                    termo,
                    na=False,
                    regex=False,
                )
            )

            matriculas_busca.update(
                historico.loc[
                    mascara_os,
                    "Matrícula",
                ].astype(str)
            )

        registro = registro[
            registro["Matrícula"]
            .astype(str)
            .isin(matriculas_busca)
        ]

    # --------------------------------------------------------
    # INTERSEÇÃO FINAL
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

    return (
        registro,
        historico,
    )


# ============================================================
# LIMPAR FILTROS
# ============================================================

def limpar_filtros():

    chaves = [
        "filtro_bairro",
        "filtro_matricula",
        "filtro_impacto",
        "filtro_resolvido",
        "filtro_executado",
        "filtro_busca",
    ]

    for chave in chaves:
        if chave in st.session_state:
            del st.session_state[chave]


# ============================================================
# ORDENAÇÃO
# ============================================================

def ordenar_registros(
    df_registro,
    df_historico,
):

    if df_registro.empty:
        return df_registro.copy()

    resultado = df_registro.copy()

    if df_historico.empty:

        resultado["_qtd_os"] = 0
        resultado["_ultima_data"] = pd.NaT
        resultado["_ultima_os"] = ""

    else:

        historico = df_historico.copy()

        historico["_data"] = pd.to_datetime(
            historico["Data de Abertura"],
            errors="coerce",
        )

        quantidade = (
            historico.groupby(
                "Matrícula"
            )
            .size()
            .rename("_qtd_os")
        )

        ultima = (
            historico
            .sort_values("_data")
            .groupby("Matrícula")
            .tail(1)
        )

        ultima = ultima[
            [
                "Matrícula",
                "_data",
                "N. O.S",
            ]
        ].rename(
            columns={
                "_data": "_ultima_data",
                "N. O.S": "_ultima_os",
            }
        )

        resultado = resultado.merge(
            quantidade,
            left_on="Matrícula",
            right_index=True,
            how="left",
        )

        resultado = resultado.merge(
            ultima,
            on="Matrícula",
            how="left",
        )

        resultado["_qtd_os"] = (
            resultado["_qtd_os"]
            .fillna(0)
            .astype(int)
        )

    return resultado.sort_values(
        by=[
            "_qtd_os",
            "_ultima_data",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )


# ============================================================
# KPIs
# ============================================================

def calcular_kpis(
    df_registro,
    df_historico,
):

    if df_historico.empty:
        return {
            "cliente": "—",
            "qtd_os": 0,
            "tempo_medio": "—",
            "media_pressao": "—",
        }

    historico = df_historico.copy()

    historico["_data"] = pd.to_datetime(
        historico["Data de Abertura"],
        errors="coerce",
    )

    contagem = (
        historico.groupby(
            "Matrícula"
        )
        .size()
        .reset_index(
            name="qtd_os"
        )
    )

    ultima = (
        historico
        .sort_values("_data")
        .groupby("Matrícula")
        .tail(1)
        [
            [
                "Matrícula",
                "_data",
            ]
        ]
        .rename(
            columns={
                "_data": "_ultima_data"
            }
        )
    )

    ranking = contagem.merge(
        ultima,
        on="Matrícula",
        how="left",
    )

    ranking = ranking.sort_values(
        by=[
            "qtd_os",
            "_ultima_data",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )

    cliente = texto(
        ranking.iloc[0]["Matrícula"]
    )

    qtd_os = int(
        ranking.iloc[0]["qtd_os"]
    )

    historico_cliente = (
        historico_da_matricula(
            historico,
            cliente,
        )
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

    datas = (
        historico_cliente["_data"]
        .dropna()
        .dt.date
        .tolist()
    )

    if len(datas) >= 2:

        diferencas = [
            (
                datas[i]
                - datas[i - 1]
            ).days
            for i in range(
                1,
                len(datas),
            )
        ]

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

    if pressoes.empty:
        media_pressao_texto = "—"
    else:
        media_pressao_texto = (
            f"{pressoes.mean():.2f} MCA"
        )

    return {
        "cliente": cliente,
        "qtd_os": qtd_os,
        "tempo_medio": tempo_medio_texto,
        "media_pressao": media_pressao_texto,
    }


def exibir_kpis(
    kpis,
):

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    cards = [
        (
            col1,
            "Cliente com mais registros",
            kpis["cliente"],
        ),
        (
            col2,
            "Quant. de O.S",
            str(kpis["qtd_os"]),
        ),
        (
            col3,
            "Tempo Médio de Reclamação",
            kpis["tempo_medio"],
        ),
        (
            col4,
            "Média de Pressão",
            kpis["media_pressao"],
        ),
    ]

    for coluna, titulo, valor in cards:

        with coluna:

            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">
                        {html.escape(titulo)}
                    </div>
                    <div class="kpi-value">
                        {html.escape(str(valor))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
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
        "OpenStreetMap",
        name="Mapa",
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
    ).add_to(mapa)

    folium.TileLayer(
        tiles=(
            "https://{s}.tile.opentopomap.org/"
            "{z}/{x}/{y}.png"
        ),
        attr="OpenTopoMap",
        name="Topográfico",
    ).add_to(mapa)

    bounds = []

    for _, registro in df_registro.iterrows():

        latitude = converter_float(
            registro["Latitude"]
        )

        longitude = converter_float(
            registro["Longitude"]
        )

        if not coordenadas_validas(
            latitude,
            longitude,
        ):
            continue

        matricula = texto(
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

            aux = historico_cliente.copy()

            aux["_data"] = pd.to_datetime(
                aux["Data de Abertura"],
                errors="coerce",
            )

            aux = aux.sort_values(
                "_data"
            )

            ultima_os = texto(
                aux.iloc[-1]["N. O.S"]
            )

        resolvido = texto(
            registro["Resolvido"]
        ).upper()

        if resolvido in [
            "SIM",
            "S",
        ]:
            cor = "green"

        elif resolvido in [
            "NAO",
            "NÃO",
            "N",
        ]:
            cor = "red"

        else:
            cor = "blue"

        popup = f"""
        <div style="width:320px">

            <h4>
                {escape(matricula)}
            </h4>

            <b>Endereço:</b>
            {escape(registro["Endereço"])}
            <br>

            <b>Bairro:</b>
            {escape(registro["Bairro"])}
            <br>

            <b>Grau de Impacto:</b>
            {escape(registro["Grau de Impacto"])}
            <br>

            <b>Resolvido:</b>
            {escape(registro["Resolvido"])}
            <br>

            <b>Qtd. de O.S.:</b>
            {qtd_os}
            <br>

            <b>Última O.S.:</b>
            {escape(ultima_os)}
            <br>

            <b>Data de Registro:</b>
            {escape(
                formatar_data(
                    registro["Data de Registro"]
                )
            )}
            <br>

            <b>Responsável:</b>
            {escape(
                registro["Responsável"]
            )}
            <br>

            <b>Parecer:</b>
            {escape(
                registro["Parecer"]
            )}
            <br>

            <b>Tratativa 1:</b>
            {escape(
                registro["Tratativa 1"]
            )}
            <br>

            <b>Retorno:</b>
            {escape(
                registro["Retorno"]
            )}

        </div>
        """

        folium.Marker(
            location=[
                latitude,
                longitude,
            ],
            tooltip=matricula,
            popup=folium.Popup(
                popup,
                max_width=360,
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
            mapa.fit_bounds(
                bounds
            )

    folium.LayerControl().add_to(
        mapa
    )

    return mapa


# ============================================================
# ESTADO DOS DIÁLOGOS
# ============================================================

if "dialogo_melhorias" not in st.session_state:
    st.session_state.dialogo_melhorias = None

if "pagina_mapeamento" not in st.session_state:
    st.session_state.pagina_mapeamento = 1


def abrir_dialogo(
    nome,
    **dados,
):

    st.session_state.dialogo_melhorias = nome

    for chave, valor in dados.items():
        st.session_state[
            f"dialogo_{chave}"
        ] = valor


def fechar_dialogo():

    st.session_state.dialogo_melhorias = None

    for chave in list(
        st.session_state.keys()
    ):

        if (
            str(chave).startswith(
                "dialogo_"
            )
            and chave != "dialogo_melhorias"
        ):

            del st.session_state[
                chave
            ]


# ============================================================
# DIÁLOGO — NOVO REGISTRO
# ============================================================

@st.dialog(
    "Adicionar melhoria",
    width="large",
)
def dialogo_novo_registro(
    df_registro,
    df_historico,
):

    st.subheader(
        "Cadastro da melhoria"
    )

    col1, col2 = st.columns(2)

    with col1:

        matricula = st.text_input(
            "Matrícula *",
            key="novo_matricula",
        )

        endereco = st.text_input(
            "Endereço *",
            key="novo_endereco",
        )

        bairro = st.text_input(
            "Bairro *",
            key="novo_bairro",
        )

    with col2:

        latitude = st.text_input(
            "Latitude *",
            key="novo_latitude",
        )

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

    tratativa_1 = st.text_area(
        "Tratativa 1",
        key="novo_tratativa_1",
    )

    col3, col4 = st.columns(2)

    with col3:

        executado = st.text_input(
            "Executado?",
            key="novo_executado",
        )

    with col4:

        retorno = st.text_area(
            "Retorno",
            key="novo_retorno",
        )

    responsavel = st.text_input(
        "Responsável",
        key="novo_responsavel",
    )

    col5, col6 = st.columns(2)

    with col5:

        grau_impacto = st.text_input(
            "Grau de Impacto",
            key="novo_grau_impacto",
        )

    with col6:

        resolvido = st.text_input(
            "Resolvido",
            key="novo_resolvido",
        )

    st.divider()

    st.subheader(
        "O.S. inicial"
    )

    matricula = texto(
        matricula
    )

    historico_existente = (
        historico_da_matricula(
            df_historico,
            matricula,
        )
        if matricula
        else pd.DataFrame()
    )

    existe_registro = (
        matricula_possui_registro(
            df_registro,
            matricula,
        )
        if matricula
        else False
    )

    if existe_registro:

        st.error(
            "Já existe um registro para esta matrícula."
        )

        return

    adicionar_os = True

    if not historico_existente.empty:

        st.info(
            "Esta matrícula já possui histórico de O.S."
        )

        adicionar_os = st.checkbox(
            "Adicionar uma nova O.S.",
            value=False,
            key="novo_adicionar_os",
        )

    numero_os = ""
    data_abertura = datetime.now()
    pressao = 0.0
    pontual = "SIM"

    if (
        historico_existente.empty
        or adicionar_os
    ):

        col7, col8 = st.columns(2)

        with col7:

            numero_os = st.text_input(
                "N. O.S *",
                placeholder="Digite a identificação da O.S.",
                key="novo_numero_os",
            )

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
                [
                    "SIM",
                    "NÃO",
                ],
                key="novo_pontual",
            )

    salvar = st.button(
        "💾 Salvar",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    if not matricula:
        st.error(
            "Informe a matrícula."
        )
        return

    if not endereco.strip():
        st.error(
            "Informe o endereço."
        )
        return

    if not bairro.strip():
        st.error(
            "Informe o bairro."
        )
        return

    if not coordenadas_validas(
        latitude,
        longitude,
    ):
        st.error(
            "Latitude e longitude são obrigatórias "
            "e devem ser válidas."
        )
        return

    if (
        historico_existente.empty
        or adicionar_os
    ):

        if not texto(numero_os):
            st.error(
                "Informe a N. O.S."
            )
            return

        if os_duplicada(
            df_historico,
            matricula,
            numero_os,
        ):
            st.error(
                "Esta O.S. já está cadastrada."
            )
            return

    registro_id = gerar_id()

    dados = {
        "ID": registro_id,
        "Matrícula": matricula,
        "Endereço": endereco.strip(),
        "Bairro": bairro.strip(),
        "Latitude": converter_float(
            latitude
        ),
        "Longitude": converter_float(
            longitude
        ),
        "Parecer": parecer,
        "Data de Registro": (
            data_registro.strftime(
                "%Y-%m-%d"
            )
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
            dados
        )

        if (
            historico_existente.empty
            or adicionar_os
        ):

            dados_os = {
                "ID": gerar_id(),
                "Matrícula": matricula,
                "N. O.S": texto(
                    numero_os
                ),
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

        fechar_dialogo()

        st.cache_data.clear()

        st.rerun()

    except Exception as exc:

        st.error(
            "Não foi possível salvar o registro."
        )

        st.exception(exc)


# ============================================================
# DIÁLOGO — EDITAR REGISTRO
# ============================================================

@st.dialog(
    "Editar melhoria",
    width="large",
)
def dialogo_editar_registro(
    registro,
    df_registro,
    df_historico,
):

    registro_id = texto(
        registro["ID"]
    )

    matricula_original = texto(
        registro["Matrícula"]
    )

    matricula = st.text_input(
        "Matrícula *",
        value=matricula_original,
        key=f"edit_matricula_{registro_id}",
    )

    endereco = st.text_input(
        "Endereço *",
        value=texto(
            registro["Endereço"]
        ),
        key=f"edit_endereco_{registro_id}",
    )

    bairro = st.text_input(
        "Bairro *",
        value=texto(
            registro["Bairro"]
        ),
        key=f"edit_bairro_{registro_id}",
    )

    col1, col2 = st.columns(2)

    with col1:

        latitude = st.text_input(
            "Latitude *",
            value=texto(
                registro["Latitude"]
            ),
            key=f"edit_latitude_{registro_id}",
        )

    with col2:

        longitude = st.text_input(
            "Longitude *",
            value=texto(
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
        value=texto(
            registro["Parecer"]
        ),
        key=f"edit_parecer_{registro_id}",
    )

    data_registro = st.date_input(
        "Data de Registro *",
        value=valor_data(
            registro["Data de Registro"]
        ),
        key=f"edit_data_registro_{registro_id}",
    )

    tratativa_1 = st.text_area(
        "Tratativa 1",
        value=texto(
            registro["Tratativa 1"]
        ),
        key=f"edit_tratativa_{registro_id}",
    )

    col3, col4 = st.columns(2)

    with col3:

        executado = st.text_input(
            "Executado?",
            value=texto(
                registro["Executado?"]
            ),
            key=f"edit_executado_{registro_id}",
        )

    with col4:

        retorno = st.text_area(
            "Retorno",
            value=texto(
                registro["Retorno"]
            ),
            key=f"edit_retorno_{registro_id}",
        )

    responsavel = st.text_input(
        "Responsável",
        value=texto(
            registro["Responsável"]
        ),
        key=f"edit_responsavel_{registro_id}",
    )

    col5, col6 = st.columns(2)

    with col5:

        grau_impacto = st.text_input(
            "Grau de Impacto",
            value=texto(
                registro["Grau de Impacto"]
            ),
            key=f"edit_impacto_{registro_id}",
        )

    with col6:

        resolvido = st.text_input(
            "Resolvido",
            value=texto(
                registro["Resolvido"]
            ),
            key=f"edit_resolvido_{registro_id}",
        )

    st.divider()

    st.subheader(
        "O.S. inicial"
    )

    st.caption(
        "A O.S. existente pode ser consultada e editada no histórico da matrícula."
    )

    st.divider()

    salvar = st.button(
        "💾 Salvar alterações",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    matricula = texto(
        matricula
    )

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
            "Já existe outro registro para esta matrícula."
        )
        return

    if not endereco.strip():
        st.error(
            "Informe o endereço."
        )
        return

    if not bairro.strip():
        st.error(
            "Informe o bairro."
        )
        return

    if not coordenadas_validas(
        latitude,
        longitude,
    ):
        st.error(
            "Latitude e longitude são obrigatórias "
            "e devem ser válidas."
        )
        return

    dados = {
        "ID": registro_id,
        "Matrícula": matricula,
        "Endereço": endereco.strip(),
        "Bairro": bairro.strip(),
        "Latitude": converter_float(
            latitude
        ),
        "Longitude": converter_float(
            longitude
        ),
        "Parecer": parecer,
        "Data de Registro": (
            data_registro.strftime(
                "%Y-%m-%d"
            )
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
            dados,
        )

        # Se a matrícula foi alterada,
        # atualiza também o histórico.
        if (
            matricula.upper()
            != matricula_original.upper()
        ):

            historico_antigo = (
                historico_da_matricula(
                    df_historico,
                    matricula_original,
                )
            )

            for _, linha in (
                historico_antigo.iterrows()
            ):

                os_id = texto(
                    linha["ID"]
                )

                dados_os = {
                    "ID": os_id,
                    "Matrícula": matricula,
                    "N. O.S": texto(
                        linha["N. O.S"]
                    ),
                    "Data de Abertura": texto(
                        linha["Data de Abertura"]
                    ),
                    "Pressão": texto(
                        linha["Pressão"]
                    ),
                    "Pontual": texto(
                        linha["Pontual"]
                    ),
                }

                atualizar_os(
                    os_id,
                    dados_os,
                )

        fechar_dialogo()

        st.cache_data.clear()

        st.rerun()

    except Exception as exc:

        st.error(
            "Não foi possível atualizar o registro."
        )

        st.exception(exc)


# ============================================================
# DIÁLOGO — MATRÍCULA
# ============================================================

@st.dialog(
    "Registro da Matrícula",
    width="large",
)
def dialogo_matricula(
    matricula,
    df_registro,
    df_historico,
):

    registro_df = (
        registro_da_matricula(
            df_registro,
            matricula,
        )
    )

    historico_df = (
        historico_da_matricula(
            df_historico,
            matricula,
        )
    )

    if registro_df.empty:

        st.warning(
            "Registro principal não encontrado."
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
                f"{texto(registro['Endereço'])}"
            )

            st.markdown(
                f"**Bairro:** "
                f"{texto(registro['Bairro'])}"
            )

            st.markdown(
                f"**Latitude:** "
                f"{texto(registro['Latitude'])}"
            )

            st.markdown(
                f"**Longitude:** "
                f"{texto(registro['Longitude'])}"
            )

            st.markdown(
                f"**Data de Registro:** "
                f"{formatar_data(registro['Data de Registro'])}"
            )

            st.markdown(
                f"**Responsável:** "
                f"{texto(registro['Responsável']) or '—'}"
            )

        with col2:

            st.markdown(
                f"**Grau de Impacto:** "
                f"{texto(registro['Grau de Impacto']) or '—'}"
            )

            st.markdown(
                f"**Resolvido:** "
                f"{texto(registro['Resolvido']) or '—'}"
            )

            st.markdown(
                f"**Executado?:** "
                f"{texto(registro['Executado?']) or '—'}"
            )

            st.markdown(
                f"**Parecer:** "
                f"{texto(registro['Parecer']) or '—'}"
            )

        st.markdown(
            f"**Tratativa 1:** "
            f"{texto(registro['Tratativa 1']) or '—'}"
        )

        st.markdown(
            f"**Retorno:** "
            f"{texto(registro['Retorno']) or '—'}"
        )

        st.divider()

        col_edit, col_delete = (
            st.columns(2)
        )

        with col_edit:

            if st.button(
                "✏️ Editar Registro",
                use_container_width=True,
            ):

                fechar_dialogo()

                abrir_dialogo(
                    "editar",
                    registro=registro.to_dict(),
                )

                st.rerun()

        with col_delete:

            if st.button(
                "🗑️ Excluir Registro",
                use_container_width=True,
            ):

                abrir_dialogo(
                    "confirmar_exclusao_registro",
                    registro=registro.to_dict(),
                )

                st.rerun()

    st.divider()

    st.subheader(
        f"Histórico de O.S. ({len(historico_df)})"
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

        for _, os_row in (
            historico_exibicao.iterrows()
        ):

            os_id = texto(
                os_row["ID"]
            )

            with st.container(
                border=True
            ):

                col1, col2, col3 = (
                    st.columns(
                        [2.5, 2.5, 1]
                    )
                )

                with col1:

                    st.markdown(
                        f"**N. O.S:** "
                        f"{texto(os_row['N. O.S'])}"
                    )

                    st.caption(
                        formatar_data_hora(
                            os_row[
                                "Data de Abertura"
                            ]
                        )
                    )

                with col2:

                    st.markdown(
                        f"**Pressão:** "
                        f"{texto(os_row['Pressão'])} MCA"
                    )

                    st.markdown(
                        f"**Pontual:** "
                        f"{texto(os_row['Pontual'])}"
                    )

                with col3:

                    if st.button(
                        "✏️",
                        key=f"editar_os_{os_id}",
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
                    ):

                        abrir_dialogo(
                            "confirmar_exclusao_os",
                            os_id=os_id,
                            matricula=matricula,
                        )

                        st.rerun()

    st.divider()

    col_add, col_download = (
        st.columns(2)
    )

    with col_add:

        if st.button(
            "＋ Adicionar Registro",
            type="primary",
            use_container_width=True,
        ):

            fechar_dialogo()

            abrir_dialogo(
                "nova_os",
                matricula=matricula,
            )

            st.rerun()

    with col_download:

        arquivo = gerar_excel_cliente(
            registro_df,
            historico_df,
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
        )


# ============================================================
# DIÁLOGO — NOVA O.S.
# ============================================================

@st.dialog(
    "Adicionar O.S.",
    width="medium",
)
def dialogo_nova_os(
    matricula,
    df_historico,
):

    st.write(
        f"**Matrícula:** {matricula}"
    )

    numero_os = st.text_input(
        "N. O.S *",
        placeholder="Digite a identificação da O.S.",
    )

    data_abertura = st.datetime_input(
        "Data de Abertura *",
        value=datetime.now(),
    )

    pressao = st.number_input(
        "Pressão (MCA) *",
        min_value=0.0,
        step=0.01,
        format="%.2f",
    )

    pontual = st.selectbox(
        "Pontual",
        [
            "SIM",
            "NÃO",
        ],
    )

    salvar = st.button(
        "💾 Salvar O.S.",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    if not texto(numero_os):

        st.error(
            "Informe a N. O.S."
        )

        return

    if os_duplicada(
        df_historico,
        matricula,
        numero_os,
    ):

        st.error(
            "Essa O.S. já está cadastrada."
        )

        return

    dados = {
        "ID": gerar_id(),
        "Matrícula": matricula,
        "N. O.S": texto(numero_os),
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
            dados
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

@st.dialog(
    "Editar O.S.",
    width="medium",
)
def dialogo_editar_os(
    os_id,
    matricula,
    df_historico,
):

    os_df = df_historico[
        df_historico["ID"]
        .astype(str)
        ==
        str(os_id)
    ]

    if os_df.empty:

        st.error(
            "O.S. não encontrada."
        )

        return

    os_atual = os_df.iloc[0]

    numero_os = st.text_input(
        "N. O.S *",
        value=texto(
            os_atual["N. O.S"]
        ),
        placeholder="Digite a identificação da O.S.",
    )

    data_abertura = st.datetime_input(
        "Data de Abertura *",
        value=valor_datetime(
            os_atual[
                "Data de Abertura"
            ]
        ),
    )

    pressao_atual = (
        converter_float(
            os_atual["Pressão"]
        )
    )

    if pressao_atual is None:
        pressao_atual = 0.0

    pressao = st.number_input(
        "Pressão (MCA) *",
        min_value=0.0,
        value=float(
            pressao_atual
        ),
        step=0.01,
        format="%.2f",
    )

    pontual_atual = texto(
        os_atual["Pontual"]
    )

    if pontual_atual not in [
        "SIM",
        "NÃO",
    ]:
        pontual_atual = "SIM"

    pontual = st.selectbox(
        "Pontual",
        [
            "SIM",
            "NÃO",
        ],
        index=[
            "SIM",
            "NÃO",
        ].index(
            pontual_atual
        ),
    )

    salvar = st.button(
        "💾 Salvar alterações",
        type="primary",
        use_container_width=True,
    )

    if not salvar:
        return

    if not texto(numero_os):

        st.error(
            "Informe a N. O.S."
        )

        return

    if os_duplicada(
        df_historico,
        matricula,
        numero_os,
        ignorar_id=os_id,
    ):

        st.error(
            "Essa O.S. já está cadastrada."
        )

        return

    dados = {
        "ID": os_id,
        "Matrícula": matricula,
        "N. O.S": texto(numero_os),
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
            dados,
        )

        fechar_dialogo()

        st.rerun()

    except Exception as exc:

        st.error(
            "Não foi possível atualizar a O.S."
        )

        st.exception(exc)


# ============================================================
# DIÁLOGO — CONFIRMAÇÃO REGISTRO
# ============================================================

@st.dialog(
    "Confirmar exclusão"
)
def dialogo_confirmar_exclusao_registro(
    registro,
):

    matricula = texto(
        registro["Matrícula"]
    )

    st.warning(
        f"Excluir o registro da matrícula "
        f"**{matricula}**?"
    )

    st.info(
        "O histórico de O.S. será preservado."
    )

    col1, col2 = (
        st.columns(2)
    )

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

            fechar_dialogo()

            st.rerun()

        except Exception as exc:

            st.error(
                "Não foi possível excluir o registro."
            )

            st.exception(exc)


# ============================================================
# DIÁLOGO — CONFIRMAÇÃO O.S.
# ============================================================

@st.dialog(
    "Confirmar exclusão da O.S."
)
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

    os_df = df_historico[
        df_historico["ID"]
        .astype(str)
        ==
        str(os_id)
    ]

    if os_df.empty:

        st.error(
            "O.S. não encontrada."
        )

        return

    numero_os = texto(
        os_df.iloc[0]["N. O.S"]
    )

    if len(historico_cliente) <= 1:

        st.warning(
            "Esta é a única O.S. da matrícula."
        )

        st.info(
            "A última O.S. não pode ser excluída."
        )

        if st.button(
            "Fechar",
            use_container_width=True,
        ):

            fechar_dialogo()
            st.rerun()

        return

    st.warning(
        f"Excluir a O.S. **{numero_os}**?"
    )

    col1, col2 = (
        st.columns(2)
    )

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

            excluir_os(
                os_id
            )

            fechar_dialogo()

            st.rerun()

        except Exception as exc:

            st.error(
                "Não foi possível excluir a O.S."
            )

            st.exception(exc)


# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================

(
    registro_ws,
    historico_ws,
    df_registro,
    df_historico,
) = carregar_dados()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🗺️ Mapeamento de Melhorias"
    )

    st.divider()

    if st.button(
        "＋ Adicionar melhoria",
        type="primary",
        use_container_width=True,
    ):

        fechar_dialogo()

        abrir_dialogo(
            "novo"
        )

        st.rerun()

    st.divider()

    st.markdown(
        "### Filtros"
    )


# ============================================================
# APLICA FILTROS
# ============================================================

df_registro_filtrado, df_historico_filtrado = (
    aplicar_filtros(
        df_registro,
        df_historico,
    )
)


# ============================================================
# LIMPAR FILTROS
# ============================================================

with st.sidebar:

    if st.button(
        "🧹 Limpar filtros",
        use_container_width=True,
    ):

        limpar_filtros()

        st.session_state[
            "pagina_mapeamento"
        ] = 1

        st.rerun()

    st.divider()

    arquivo_sidebar = gerar_excel(
        df_registro_filtrado,
        df_historico_filtrado,
    )

    st.download_button(
        "⬇️ Exportar filtrado",
        data=arquivo_sidebar,
        file_name=(
            "mapeamento_de_melhorias_filtrado.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

    st.divider()

    if st.button(
        "🏠 Voltar ao Menu Principal",
        use_container_width=True,
    ):

        st.switch_page(
            "app.py"
        )


# ============================================================
# CABEÇALHO
# ============================================================

st.title(
    "🗺️ Mapeamento de Melhorias"
)

st.caption(
    "Cadastro, acompanhamento e histórico das melhorias "
    "relacionadas às matrículas."
)


# ============================================================
# KPIs
# ============================================================

kpis = calcular_kpis(
    df_registro_filtrado,
    df_historico_filtrado,
)

exibir_kpis(
    kpis
)


# ============================================================
# MAPA
# ============================================================

st.markdown(
    "### Mapa"
)

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
# LISTA DE REGISTROS
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

    pagina = st.session_state.get(
        "pagina_mapeamento",
        1,
    )

    pagina = min(
        pagina,
        total_paginas,
    )

    col_prev, col_info, col_next = (
        st.columns(
            [1, 2, 1]
        )
    )

    with col_prev:

        if st.button(
            "← Anterior",
            disabled=pagina <= 1,
            use_container_width=True,
        ):

            st.session_state[
                "pagina_mapeamento"
            ] = max(
                1,
                pagina - 1,
            )

            st.rerun()

    with col_info:

        st.markdown(
            f"""
            <div style="
                text-align:center;
                padding-top:8px;
            ">
                Página {pagina} de {total_paginas}
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_next:

        if st.button(
            "Próxima →",
            disabled=pagina >= total_paginas,
            use_container_width=True,
        ):

            st.session_state[
                "pagina_mapeamento"
            ] = min(
                total_paginas,
                pagina + 1,
            )

            st.rerun()

    inicio = (
        pagina - 1
    ) * REGISTROS_POR_PAGINA

    fim = (
        inicio
        + REGISTROS_POR_PAGINA
    )

    pagina_df = df_lista.iloc[
        inicio:fim
    ]

    for _, registro in (
        pagina_df.iterrows()
    ):

        registro_id = texto(
            registro["ID"]
        )

        matricula = texto(
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

            ultima_os = texto(
                aux.iloc[-1]["N. O.S"]
            )

        with st.container(
            border=True
        ):

            col1, col2, col3, col4, col5 = (
                st.columns(
                    [
                        1.7,
                        2.7,
                        1.5,
                        1,
                        1.2,
                    ]
                )
            )

            with col1:

                if st.button(
                    matricula,
                    key=f"abrir_{registro_id}",
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
                    f"**{texto(registro['Endereço'])}**"
                )

                st.caption(
                    texto(
                        registro["Bairro"]
                    )
                )

            with col3:

                st.caption(
                    "Grau de Impacto"
                )

                st.write(
                    texto(
                        registro[
                            "Grau de Impacto"
                        ]
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

dialogo = st.session_state.get(
    "dialogo_melhorias"
)


if dialogo == "novo":

    dialogo_novo_registro(
        df_registro,
        df_historico,
    )


elif dialogo == "editar":

    registro = st.session_state.get(
        "dialogo_registro"
    )

    if registro:

        dialogo_editar_registro(
            registro,
            df_registro,
            df_historico,
        )


elif dialogo == "matricula":

    matricula = st.session_state.get(
        "dialogo_matricula"
    )

    if matricula:

        dialogo_matricula(
            matricula,
            df_registro,
            df_historico,
        )


elif dialogo == "nova_os":

    matricula = st.session_state.get(
        "dialogo_matricula"
    )

    if matricula:

        dialogo_nova_os(
            matricula,
            df_historico,
        )


elif dialogo == "editar_os":

    os_id = st.session_state.get(
        "dialogo_os_id"
    )

    matricula = st.session_state.get(
        "dialogo_matricula"
    )

    if os_id and matricula:

        dialogo_editar_os(
            os_id,
            matricula,
            df_historico,
        )


elif (
    dialogo
    == "confirmar_exclusao_registro"
):

    registro = st.session_state.get(
        "dialogo_registro"
    )

    if registro:

        dialogo_confirmar_exclusao_registro(
            registro
        )


elif (
    dialogo
    == "confirmar_exclusao_os"
):

    os_id = st.session_state.get(
        "dialogo_os_id"
    )

    matricula = st.session_state.get(
        "dialogo_matricula"
    )

    if os_id and matricula:

        dialogo_confirmar_exclusao_os(
            os_id,
            matricula,
            df_historico,
        )
