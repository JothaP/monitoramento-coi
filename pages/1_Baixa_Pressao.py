import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
import os
import simplekml
from datetime import datetime, date, timedelta
from streamlit_autorefresh import st_autorefresh
import io
import uuid
from typing import Optional
import time
import plotly.express as px
from branca.element import Element
from html import escape
import unicodedata


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

from auth import verificar_autenticacao

if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# CONSTANTES
# ============================================================

LAT_BASE = -5.0892
LON_BASE = -42.8019

SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"

COLUNAS_PADRAO = [
    "ID",
    "Data",
    "Municipio",
    "Bairro",
    "Latitude",
    "Longitude",
    "Pressao_MCA",
    "Observacao",
    "Matricula"
]

COR_SEM_PRESSAO = "#FF5C60"
COR_BAIXA_PRESSAO = "#F8DC00"
COR_EM_ATENCAO = "#FF8FE1"
COR_ALTA_PRESSAO = "#A11FFF"


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_texto(valor):
    if pd.isna(valor):
        return ""

    valor = str(valor).strip()

    valor = unicodedata.normalize(
        "NFKD",
        valor
    ).encode(
        "ASCII",
        "ignore"
    ).decode(
        "ASCII"
    )

    return " ".join(valor.lower().split())


def converter_float(valor, padrao=0.0):

    if valor is None:
        return padrao

    if isinstance(valor, (int, float)):
        try:
            if pd.isna(valor):
                return padrao
        except Exception:
            pass

        return float(valor)

    texto = str(valor).strip()

    if not texto:
        return padrao

    texto = texto.replace("MCA", "")
    texto = texto.replace("mca", "")
    texto = texto.replace(" ", "")

    # Trata números no padrão brasileiro
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return padrao


def classificar_pressao(pressao):

    pressao = converter_float(pressao, 0)

    if pressao == 0:
        return "Sem Pressão"

    if pressao <= 5:
        return "Baixa Pressão"

    if pressao <= 15:
        return "Em Atenção"

    return "Alta Pressão"


def cor_classificacao(classificacao):

    mapa = {
        "Sem Pressão": COR_SEM_PRESSAO,
        "Baixa Pressão": COR_BAIXA_PRESSAO,
        "Em Atenção": COR_EM_ATENCAO,
        "Alta Pressão": COR_ALTA_PRESSAO
    }

    return mapa.get(
        classificacao,
        COR_BAIXA_PRESSAO
    )


def gerar_id():
    return str(uuid.uuid4())


def formatar_pressao(valor):

    try:
        valor = float(valor)
    except Exception:
        valor = 0

    return f"{valor:.2f}".replace(".", ",")


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google():

    try:

        credenciais_dict = st.secrets["gcp_json"]

        if isinstance(credenciais_dict, str):
            credenciais_dict = json.loads(
                credenciais_dict
            )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        credentials = Credentials.from_service_account_info(
            credenciais_dict,
            scopes=scopes
        )

        cliente = gspread.authorize(credentials)

        planilha = cliente.open_by_key(
            SPREADSHEET_ID
        )

        try:
            aba = planilha.worksheet(
                "baixa_pressao"
            )
        except Exception:
            aba = planilha.add_worksheet(
                title="baixa_pressao",
                rows=1000,
                cols=len(COLUNAS_PADRAO)
            )

            aba.append_row(
                COLUNAS_PADRAO
            )

        return aba

    except Exception as e:

        st.error(
            f"Erro ao conectar ao Google Sheets: {e}"
        )

        return None


worksheet = conectar_google()


# ============================================================
# GARANTIR ESTRUTURA DA PLANILHA
# ============================================================

def garantir_colunas():

    if worksheet is None:
        return

    try:

        valores = worksheet.get_all_values()

        if not valores:

            worksheet.append_row(
                COLUNAS_PADRAO
            )

            return

        cabecalho = valores[0]

        alterou = False

        for coluna in COLUNAS_PADRAO:

            if coluna not in cabecalho:

                cabecalho.append(
                    coluna
                )

                alterou = True

        if alterou:

            worksheet.update(
                "1:1",
                [cabecalho]
            )

    except Exception:
        pass


garantir_colunas()


# ============================================================
# CARREGAMENTO
# ============================================================

@st.cache_data(ttl=20)
def carregar_dados():

    if worksheet is None:
        return pd.DataFrame(
            columns=COLUNAS_PADRAO
        )

    try:

        valores = worksheet.get_all_values()

        if not valores:
            return pd.DataFrame(
                columns=COLUNAS_PADRAO
            )

        cabecalho = valores[0]

        dados = valores[1:]

        df = pd.DataFrame(
            dados,
            columns=cabecalho
        )

        for coluna in COLUNAS_PADRAO:

            if coluna not in df.columns:
                df[coluna] = ""

        df = df[
            COLUNAS_PADRAO
        ].copy()

        # ----------------------------------------------------
        # TEXTO
        # ----------------------------------------------------

        for coluna in [
            "ID",
            "Municipio",
            "Bairro",
            "Observacao",
            "Matricula"
        ]:

            df[coluna] = (
                df[coluna]
                .fillna("")
                .astype(str)
                .str.strip()
            )

        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        df["Data"] = pd.to_datetime(
            df["Data"],
            errors="coerce",
            dayfirst=True
        )

        # ----------------------------------------------------
        # COORDENADAS
        # ----------------------------------------------------

        df["Latitude"] = df[
            "Latitude"
        ].apply(
            lambda x: converter_float(
                x,
                None
            )
        )

        df["Longitude"] = df[
            "Longitude"
        ].apply(
            lambda x: converter_float(
                x,
                None
            )
        )

        df["Latitude"] = df[
            "Latitude"
        ].round(6)

        df["Longitude"] = df[
            "Longitude"
        ].round(6)

        # ----------------------------------------------------
        # PRESSÃO
        # ----------------------------------------------------

        df["Pressao_MCA"] = df[
            "Pressao_MCA"
        ].apply(
            lambda x: converter_float(
                x,
                0
            )
        )

        # ----------------------------------------------------
        # LIMPEZA
        # ----------------------------------------------------

        df = df[
            df["Bairro"].astype(str).str.strip() != ""
        ].copy()

        df["Classificacao"] = df[
            "Pressao_MCA"
        ].apply(
            classificar_pressao
        )

        return df.reset_index(
            drop=True
        )

    except Exception as e:

        st.error(
            f"Erro ao carregar dados: {e}"
        )

        return pd.DataFrame(
            columns=COLUNAS_PADRAO
        )


df = carregar_dados()


# ============================================================
# CRUD
# ============================================================

def invalidar_cache():

    try:
        carregar_dados.clear()
    except Exception:
        pass


def adicionar_ponto(
    data,
    municipio,
    bairro,
    latitude,
    longitude,
    pressao,
    observacao,
    matricula
):

    if worksheet is None:
        return False

    try:

        novo_id = gerar_id()

        linha = [
            novo_id,
            data.strftime("%d/%m/%Y")
            if isinstance(data, (date, datetime))
            else str(data),
            str(municipio).strip(),
            str(bairro).strip(),
            round(float(latitude), 6),
            round(float(longitude), 6),
            converter_float(pressao),
            str(observacao).strip(),
            str(matricula).strip()
        ]

        worksheet.append_row(
            linha,
            value_input_option="USER_ENTERED"
        )

        invalidar_cache()

        return True

    except Exception as e:

        st.error(
            f"Erro ao adicionar ponto: {e}"
        )

        return False


def adicionar_lote_seguro(df_lote):

    if worksheet is None:
        return False

    try:

        if df_lote.empty:
            return False

        linhas = []

        for _, row in df_lote.iterrows():

            data = row.get(
                "Data",
                datetime.now()
            )

            if pd.isna(data):
                data = datetime.now()

            if isinstance(data, pd.Timestamp):
                data = data.to_pydatetime()

            linha = [
                str(
                    row.get(
                        "ID",
                        gerar_id()
                    )
                ).strip()
                or gerar_id(),

                data.strftime("%d/%m/%Y"),

                str(
                    row.get(
                        "Municipio",
                        ""
                    )
                ).strip(),

                str(
                    row.get(
                        "Bairro",
                        ""
                    )
                ).strip(),

                round(
                    converter_float(
                        row.get("Latitude"),
                        0
                    ),
                    6
                ),

                round(
                    converter_float(
                        row.get("Longitude"),
                        0
                    ),
                    6
                ),

                converter_float(
                    row.get(
                        "Pressao_MCA",
                        0
                    )
                ),

                str(
                    row.get(
                        "Observacao",
                        ""
                    )
                ).strip(),

                str(
                    row.get(
                        "Matricula",
                        ""
                    )
                ).strip()
            ]

            linhas.append(
                linha
            )

        if linhas:

            worksheet.append_rows(
                linhas,
                value_input_option="USER_ENTERED"
            )

            invalidar_cache()

            return True

        return False

    except Exception as e:

        st.error(
            f"Erro ao inserir lote: {e}"
        )

        return False


def atualizar_ponto(
    id_ponto,
    data,
    municipio,
    bairro,
    latitude,
    longitude,
    pressao,
    observacao,
    matricula
):

    if worksheet is None:
        return False

    try:

        celula = worksheet.find(
            str(id_ponto)
        )

        if not celula:
            return False

        linha = [
            str(id_ponto),
            data.strftime("%d/%m/%Y")
            if isinstance(data, (date, datetime))
            else str(data),
            str(municipio).strip(),
            str(bairro).strip(),
            round(float(latitude), 6),
            round(float(longitude), 6),
            converter_float(pressao),
            str(observacao).strip(),
            str(matricula).strip()
        ]

        worksheet.update(
            f"A{celula.row}:I{celula.row}",
            [linha],
            value_input_option="USER_ENTERED"
        )

        invalidar_cache()

        return True

    except Exception as e:

        st.error(
            f"Erro ao atualizar ponto: {e}"
        )

        return False


def excluir_ponto(id_ponto):

    if worksheet is None:
        return False

    try:

        celula = worksheet.find(
            str(id_ponto)
        )

        if not celula:
            return False

        worksheet.delete_rows(
            celula.row
        )

        invalidar_cache()

        return True

    except Exception as e:

        st.error(
            f"Erro ao excluir ponto: {e}"
        )

        return False


# ============================================================
# EXPORTAÇÃO XLSX
# ============================================================

def exportar_xlsx(df_export):

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df_export.to_excel(
            writer,
            index=False,
            sheet_name="Baixa Pressão"
        )

    output.seek(0)

    return output


# ============================================================
# EXPORTAÇÃO KML
# ============================================================

def exportar_kml(df_export):

    kml = simplekml.Kml()

    for _, row in df_export.iterrows():

        lat = converter_float(
            row["Latitude"],
            None
        )

        lon = converter_float(
            row["Longitude"],
            None
        )

        if lat is None or lon is None:
            continue

        classificacao = classificar_pressao(
            row["Pressao_MCA"]
        )

        pnt = kml.newpoint(
            name=str(
                row["Bairro"]
            ),
            coords=[
                (lon, lat)
            ]
        )

        pnt.description = (
            f"Bairro: {row['Bairro']}<br>"
            f"Município: {row['Municipio']}<br>"
            f"Pressão: "
            f"{formatar_pressao(row['Pressao_MCA'])} MCA<br>"
            f"Classificação: {classificacao}<br>"
            f"Matrícula: {row['Matricula']}"
        )

    output = io.BytesIO(
        kml.kml().encode(
            "utf-8"
        )
    )

    return output


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 💧 Filtros"
    )

    st.markdown(
        "---"
    )

    if not df.empty:

        datas_validas = df[
            "Data"
        ].dropna()

        if not datas_validas.empty:

            data_min = (
                datas_validas
                .min()
                .date()
            )

            data_max = (
                datas_validas
                .max()
                .date()
            )

        else:

            data_min = date.today()
            data_max = date.today()

    else:

        data_min = date.today()
        data_max = date.today()

    intervalo_data = st.date_input(
        "Período",
        value=(
            data_min,
            data_max
        ),
        min_value=data_min,
        max_value=data_max
    )

    if len(intervalo_data) == 2:

        data_inicio = intervalo_data[0]
        data_fim = intervalo_data[1]

    else:

        data_inicio = data_min
        data_fim = data_max

    municipios = sorted(
        [
            x for x in df[
                "Municipio"
            ].dropna().unique()
            if str(x).strip()
        ]
    )

    municipio_selecionado = st.selectbox(
        "Município",
        ["Todos"] + municipios
    )

    df_bairro_filtro = df.copy()

    if municipio_selecionado != "Todos":

        df_bairro_filtro = df_bairro_filtro[
            df_bairro_filtro[
                "Municipio"
            ] == municipio_selecionado
        ]

    bairros = sorted(
        [
            x for x in df_bairro_filtro[
                "Bairro"
            ].dropna().unique()
            if str(x).strip()
        ]
    )

    bairro_selecionado = st.selectbox(
        "Bairro",
        ["Todos"] + bairros
    )

    matriculas = sorted(
        [
            x for x in df[
                "Matricula"
            ].dropna().unique()
            if str(x).strip()
        ]
    )

    matricula_selecionada = st.selectbox(
        "Matrícula",
        ["Todas"] + matriculas
    )

    faixa_pressao = st.slider(
        "Faixa de pressão (MCA)",
        min_value=0.0,
        max_value=100.0,
        value=(0.0, 100.0),
        step=0.5
    )

    st.markdown(
        "---"
    )

    st.markdown(
        "### 📍 Visualização"
    )

    tipo_mapa = st.selectbox(
        "Tipo de mapa",
        [
            "OSM",
            "Esri Satellite",
            "OpenTopoMap"
        ]
    )

    modo_visualizacao = st.radio(
        "Visualização",
        [
            "Por bairro",
            "Medições individuais"
        ]
    )

    exibir_rotulos = st.checkbox(
        "Exibir rótulos dos bairros",
        value=True
    )

    modo_adicionar = st.checkbox(
        "📍 Modo adicionar ponto",
        value=False
    )

    st.markdown(
        "---"
    )

    st.markdown(
        "### 🔄 Atualização"
    )

    intervalo_refresh = st.selectbox(
        "Atualização automática",
        [
            "Desativada",
            "30 segundos",
            "1 minuto",
            "5 minutos"
        ],
        index=0
    )

    if intervalo_refresh != "Desativada":

        mapa_intervalo = {
            "30 segundos": 30000,
            "1 minuto": 60000,
            "5 minutos": 300000
        }

        st_autorefresh(
            interval=mapa_intervalo[
                intervalo_refresh
            ],
            key="refresh_bp"
        )

    st.markdown(
        "---"
    )

    st.markdown(
        "### 📤 Dados"
    )

    arquivo_upload = st.file_uploader(
        "Importar XLSX ou CSV",
        type=[
            "xlsx",
            "csv"
        ]
    )

    if st.button(
        "⬇️ Baixar modelo"
    ):

        modelo = pd.DataFrame(
            columns=COLUNAS_PADRAO
        )

        buffer_modelo = io.BytesIO()

        with pd.ExcelWriter(
            buffer_modelo,
            engine="openpyxl"
        ) as writer:

            modelo.to_excel(
                writer,
                index=False
            )

        buffer_modelo.seek(0)

        st.download_button(
            "Baixar modelo XLSX",
            data=buffer_modelo,
            file_name="modelo_baixa_pressao.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

    if st.button(
        "🔄 Atualizar dados"
    ):

        invalidar_cache()
        st.rerun()

    if st.button(
        "🏠 Voltar ao menu"
    ):

        st.switch_page(
            "app.py"
        )


# ============================================================
# IMPORTAÇÃO
# ============================================================

if arquivo_upload is not None:

    try:

        if arquivo_upload.name.lower().endswith(
            ".csv"
        ):

            df_importado = pd.read_csv(
                arquivo_upload,
                sep=None,
                engine="python"
            )

        else:

            df_importado = pd.read_excel(
                arquivo_upload
            )

        st.sidebar.success(
            f"{len(df_importado)} registros carregados."
        )

        if st.sidebar.button(
            "Importar registros"
        ):

            colunas_faltantes = [
                c for c in COLUNAS_PADRAO
                if c not in df_importado.columns
            ]

            for coluna in colunas_faltantes:
                df_importado[coluna] = ""

            df_importado = df_importado[
                COLUNAS_PADRAO
            ]

            if adicionar_lote_seguro(
                df_importado
            ):

                st.success(
                    "Dados importados com sucesso."
                )

                st.rerun()

    except Exception as e:

        st.sidebar.error(
            f"Erro na importação: {e}"
        )


# ============================================================
# FILTRAGEM
# ============================================================

df_filtrado = df.copy()

if not df_filtrado.empty:

    df_filtrado = df_filtrado[
        df_filtrado["Data"].dt.date.between(
            data_inicio,
            data_fim
        )
    ]

    if municipio_selecionado != "Todos":

        df_filtrado = df_filtrado[
            df_filtrado[
                "Municipio"
            ] == municipio_selecionado
        ]

    if bairro_selecionado != "Todos":

        df_filtrado = df_filtrado[
            df_filtrado[
                "Bairro"
            ] == bairro_selecionado
        ]

    if matricula_selecionada != "Todas":

        df_filtrado = df_filtrado[
            df_filtrado[
                "Matricula"
            ] == matricula_selecionada
        ]

    df_filtrado = df_filtrado[
        df_filtrado[
            "Pressao_MCA"
        ].between(
            faixa_pressao[0],
            faixa_pressao[1]
        )
    ]


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "💧 Painel de Monitoramento de Baixa Pressão - COI"
)


# ============================================================
# MÉTRICAS
# ============================================================

total = len(
    df_filtrado
)

sem_pressao = len(
    df_filtrado[
        df_filtrado[
            "Pressao_MCA"
        ] == 0
    ]
)

baixa_pressao = len(
    df_filtrado[
        (
            df_filtrado[
                "Pressao_MCA"
            ] > 0
        )
        &
        (
            df_filtrado[
                "Pressao_MCA"
            ] <= 5
        )
    ]
)

em_atencao = len(
    df_filtrado[
        (
            df_filtrado[
                "Pressao_MCA"
            ] > 5
        )
        &
        (
            df_filtrado[
                "Pressao_MCA"
            ] <= 15
        )
    ]
)

alta_pressao = len(
    df_filtrado[
        df_filtrado[
            "Pressao_MCA"
        ] > 15
    ]
)


col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Total",
        total
    )

with col2:
    st.metric(
        "Sem Pressão",
        sem_pressao
    )

with col3:
    st.metric(
        "Baixa Pressão",
        baixa_pressao
    )

with col4:
    st.metric(
        "Em Atenção",
        em_atencao
    )

with col5:
    st.metric(
        "Alta Pressão",
        alta_pressao
    )


# ============================================================
# PIN SVG
# ============================================================

def gerar_pin_svg(
    cor: str,
    tamanho: str = "bairro"
) -> str:

    if tamanho == "individual":

        largura = 34
        altura = 39

    else:

        largura = 40
        altura = 45

    return f"""
    <svg
        class="bp-pin-svg"
        width="{largura}"
        height="{altura}"
        viewBox="0 0 40 45"
        xmlns="http://www.w3.org/2000/svg"
        style="
            position:absolute;
            left:50%;
            top:50%;
            transform:translate(-50%,-50%);
            overflow:visible;
            pointer-events:auto;
            z-index:2000;
        "
    >
        <path
            d="
                M20 43
                C18.5 40.8 5 26.2 5 16
                C5 7.72 11.72 1 20 1
                C28.28 1 35 7.72 35 16
                C35 26.2 21.5 40.8 20 43 Z
            "
            fill="{cor}"
            stroke="#ffffff"
            stroke-width="2"
            stroke-linejoin="round"
        />

        <circle
            cx="20"
            cy="16"
            r="5"
            fill="#ffffff"
        />
    </svg>
    """


# ============================================================
# CSS
# ============================================================

map_style_html = """

<style>

.leaflet-marker-icon {
    background: transparent !important;
    border: none !important;
    overflow: visible !important;
}

.bp-marker-wrapper {
    position: relative !important;
    overflow: visible !important;
    pointer-events: none !important;
}

.bp-pin-svg {
    pointer-events: auto !important;
    overflow: visible !important;
}

.bp-label-card {

    position: absolute !important;

    width: 158px;

    box-sizing: border-box;

    padding: 5px 8px;

    background: rgba(
        255,
        255,
        255,
        0.95
    );

    border: 1px solid rgba(
        80,
        80,
        80,
        0.30
    );

    border-left: 4px solid
        var(--bp-label-color, #777);

    border-radius: 6px;

    box-shadow:
        0 2px 7px
        rgba(0, 0, 0, 0.22);

    color: #222;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    font-size: 11px;

    line-height: 1.25;

    z-index: 900 !important;

    pointer-events: none !important;

    white-space: normal;

    transition:
        left 0.15s ease,
        top 0.15s ease,
        opacity 0.15s ease;

}

.bp-label-card-individual {
    width: 145px;
}

.bp-label-card-bairro {
    width: 158px;
}

.bp-label-title {
    font-weight: 700;
    margin-bottom: 2px;
}

.bp-label-data {
    font-weight: 500;
}

.leaflet-tooltip {
    display: none !important;
}

</style>

"""


# ============================================================
# MAPA
# ============================================================

if not df_filtrado.empty:

    coordenadas_validas = df_filtrado[
        df_filtrado["Latitude"].notna()
        &
        df_filtrado["Longitude"].notna()
        &
        (df_filtrado["Latitude"] != 0)
        &
        (df_filtrado["Longitude"] != 0)
    ]

else:

    coordenadas_validas = pd.DataFrame()


if not coordenadas_validas.empty:

    centro_lat = coordenadas_validas[
        "Latitude"
    ].mean()

    centro_lon = coordenadas_validas[
        "Longitude"
    ].mean()

    zoom_inicial = 13

else:

    centro_lat = LAT_BASE
    centro_lon = LON_BASE
    zoom_inicial = 12


m = folium.Map(
    location=[
        centro_lat,
        centro_lon
    ],
    zoom_start=zoom_inicial,
    control_scale=True,
    tiles=None
)


# ============================================================
# CAMADAS
# ============================================================

folium.TileLayer(
    "OpenStreetMap",
    name="OSM",
    control=True
).add_to(m)


folium.TileLayer(
    tiles=(
        "https://server.arcgisonline.com/"
        "ArcGIS/rest/services/"
        "World_Imagery/"
        "MapServer/tile/{z}/{y}/{x}"
    ),
    attr="Esri",
    name="Esri Satellite",
    control=True
).add_to(m)


folium.TileLayer(
    "OpenTopoMap",
    name="OpenTopoMap",
    control=True
).add_to(m)


# ============================================================
# MARCADORES
# ============================================================

if not df_filtrado.empty:

    if modo_visualizacao == "Medições individuais":

        # ----------------------------------------------------
        # MEDIÇÕES INDIVIDUAIS
        # ----------------------------------------------------

        for _, row in df_filtrado.iterrows():

            lat = converter_float(
                row["Latitude"],
                None
            )

            lon = converter_float(
                row["Longitude"],
                None
            )

            if lat is None or lon is None:
                continue

            if lat == 0 or lon == 0:
                continue

            pressao = converter_float(
                row["Pressao_MCA"],
                0
            )

            classificacao = classificar_pressao(
                pressao
            )

            cor = cor_classificacao(
                classificacao
            )

            bairro = str(
                row["Bairro"]
            )

            titulo = escape(
                bairro
            )

            label_html = ""

            if exibir_rotulos:

                label_html = f"""
                <div
                    class="
                        bp-label-card
                        bp-label-card-individual
                    "
                    data-bp-label="1"
                >
                    <div
                        class="bp-label-title"
                    >
                        {titulo}
                    </div>

                    <div
                        class="bp-label-data"
                    >
                        {formatar_pressao(pressao)}
                        MCA ·
                        {escape(classificacao)}
                    </div>
                </div>
                """

            pin_svg = gerar_pin_svg(
                cor,
                "individual"
            )

            marker_html = f"""
            <div
                class="
                    bp-marker-wrapper
                    bp-individual-marker-wrapper
                "
                data-bp-priority="1"
                style="
                    width:42px;
                    height:42px;
                    position:relative;
                    overflow:visible;
                "
            >

                {pin_svg}

                {label_html}

            </div>
            """

            popup_html = f"""
            <div style="
                min-width:230px;
                font-family:Arial;
            ">

                <b>📍 {escape(bairro)}</b>

                <hr>

                <b>Município:</b>
                {escape(str(row["Municipio"]))}
                <br>

                <b>Matrícula:</b>
                {escape(str(row["Matricula"]))}
                <br>

                <b>Pressão:</b>
                {formatar_pressao(pressao)}
                MCA
                <br>

                <b>Classificação:</b>
                {escape(classificacao)}
                <br>

                <b>Data:</b>
                {
                    row["Data"].strftime("%d/%m/%Y")
                    if pd.notna(row["Data"])
                    else ""
                }

                <br>

                <b>ID:</b>
                {escape(str(row["ID"]))}

                <br><br>

                <b>Observação:</b>
                <br>
                {escape(str(row["Observacao"]))}

            </div>
            """

            popup = folium.Popup(
                popup_html,
                max_width=350
            )

            tooltip = folium.Tooltip(
                (
                    f"{bairro} · "
                    f"{formatar_pressao(pressao)} MCA · "
                    f"{classificacao}"
                ),
                sticky=False
            )

            icon = folium.DivIcon(
                html=marker_html,
                icon_size=(
                    42,
                    42
                ),
                icon_anchor=(
                    21,
                    21
                ),
                class_name=(
                    "pressao-individual-marker"
                )
            )

            marker = folium.Marker(
                location=[
                    lat,
                    lon
                ],
                icon=icon,
                popup=popup,
                tooltip=tooltip
            )

            marker.add_to(m)

    else:

        # ----------------------------------------------------
        # AGRUPAMENTO POR BAIRRO
        # ----------------------------------------------------

        df_bairros = df_filtrado.copy()

        df_bairros = df_bairros[
            df_bairros["Latitude"].notna()
            &
            df_bairros["Longitude"].notna()
            &
            (df_bairros["Latitude"] != 0)
            &
            (df_bairros["Longitude"] != 0)
        ]

        agrupado = (
            df_bairros
            .groupby(
                [
                    "Municipio",
                    "Bairro"
                ],
                dropna=False
            )
        )

        for (
            municipio,
            bairro
        ), grupo in agrupado:

            if grupo.empty:
                continue

            lat = grupo[
                "Latitude"
            ].mean()

            lon = grupo[
                "Longitude"
            ].mean()

            quantidade = len(
                grupo
            )

            media_pressao = grupo[
                "Pressao_MCA"
            ].mean()

            minima = grupo[
                "Pressao_MCA"
            ].min()

            maxima = grupo[
                "Pressao_MCA"
            ].max()

            classificacao = classificar_pressao(
                media_pressao
            )

            cor = cor_classificacao(
                classificacao
            )

            bairro_texto = str(
                bairro
            )

            municipio_texto = str(
                municipio
            )

            label_html = ""

            if exibir_rotulos:

                label_html = f"""
                <div
                    class="
                        bp-label-card
                        bp-label-card-bairro
                    "
                    data-bp-label="1"
                >

                    <div
                        class="bp-label-title"
                    >
                        {escape(bairro_texto)}
                    </div>

                    <div
                        class="bp-label-data"
                    >
                        Média:
                        {formatar_pressao(media_pressao)}
                        MCA
                    </div>

                    <div
                        class="bp-label-data"
                    >
                        {quantidade}
                        medição(ões) ·
                        {escape(classificacao)}
                    </div>

                </div>
                """

            pin_svg = gerar_pin_svg(
                cor,
                "bairro"
            )

            marker_html = f"""
            <div
                class="
                    bp-marker-wrapper
                    bp-bairro-marker-wrapper
                "
                data-bp-priority="{quantidade}"
                style="
                    width:44px;
                    height:44px;
                    position:relative;
                    overflow:visible;
                "
            >

                {pin_svg}

                {label_html}

            </div>
            """

            detalhes = ""

            for _, medicao in grupo.iterrows():

                data_medicao = ""

                if pd.notna(
                    medicao["Data"]
                ):

                    data_medicao = (
                        medicao["Data"]
                        .strftime("%d/%m/%Y")
                    )

                detalhes += f"""
                <div
                    style="
                        padding:5px 0;
                        border-bottom:
                        1px solid #ddd;
                    "
                >
                    <b>{data_medicao}</b><br>

                    Pressão:
                    {
                        formatar_pressao(
                            medicao["Pressao_MCA"]
                        )
                    }
                    MCA<br>

                    Matrícula:
                    {
                        escape(
                            str(
                                medicao["Matricula"]
                            )
                        )
                    }

                    <br>

                    ID:
                    {
                        escape(
                            str(
                                medicao["ID"]
                            )
                        )
                    }
                </div>
                """

            popup_html = f"""
            <div style="
                min-width:280px;
                max-height:400px;
                overflow-y:auto;
                font-family:Arial;
            ">

                <h4 style="
                    margin:0 0 4px 0;
                ">
                    📍 {escape(bairro_texto)}
                </h4>

                <div>
                    <b>Município:</b>
                    {escape(municipio_texto)}
                </div>

                <hr>

                <b>Pressão média:</b>
                {formatar_pressao(media_pressao)}
                MCA

                <br>

                <b>Classificação:</b>
                {escape(classificacao)}

                <br>

                <b>Quantidade:</b>
                {quantidade}

                <br>

                <b>Mínima:</b>
                {formatar_pressao(minima)}
                MCA

                <br>

                <b>Máxima:</b>
                {formatar_pressao(maxima)}
                MCA

                <hr>

                <b>Detalhamento</b>

                {detalhes}

            </div>
            """

            popup = folium.Popup(
                popup_html,
                max_width=380
            )

            tooltip = folium.Tooltip(
                (
                    f"{bairro_texto} · "
                    f"Média: "
                    f"{formatar_pressao(media_pressao)} MCA · "
                    f"{quantidade} medição(ões)"
                ),
                sticky=False
            )

            icon = folium.DivIcon(
                html=marker_html,
                icon_size=(
                    44,
                    44
                ),
                icon_anchor=(
                    22,
                    22
                ),
                class_name=(
                    "pressao-bairro-marker"
                )
            )

            marker = folium.Marker(
                location=[
                    lat,
                    lon
                ],
                icon=icon,
                popup=popup,
                tooltip=tooltip
            )

            marker.add_to(m)


# ============================================================
# CONTROLE DE CAMADAS
# ============================================================

folium.LayerControl(
    collapsed=False
).add_to(m)


# ============================================================
# CSS
# ============================================================

m.get_root().html.add_child(
    Element(
        map_style_html
    )
)


# ============================================================
# JAVASCRIPT
# DESCONGESTIONAMENTO DOS RÓTULOS
# ============================================================

map_name = m.get_name()


declutter_js = r"""
(function() {

    const MAP_NAME_PLACEHOLDER = "__MAP_NAME__";

    const ESPACO_PIN = 14;
    const MARGEM_ROTULO = 5;
    const MARGEM_MAPA = 4;

    const POSICOES = [
        "top",
        "bottom",
        "right",
        "left",
        "top-right",
        "top-left",
        "bottom-right",
        "bottom-left"
    ];


    function obterMapa() {

        return window[
            MAP_NAME_PLACEHOLDER
        ];

    }


    function obterWrappers(map) {

        if (!map) {
            return [];
        }

        const container =
            map.getContainer();

        return Array.from(
            container.querySelectorAll(
                ".bp-marker-wrapper"
            )
        );

    }


    function obterPinCentro(wrapper) {

        const svg =
            wrapper.querySelector(
                ".bp-pin-svg"
            );

        if (!svg) {
            return null;
        }

        const rect =
            svg.getBoundingClientRect();

        return {
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
            centerX:
                rect.left +
                rect.width / 2,
            centerY:
                rect.top +
                rect.height / 2
        };

    }


    /*
     * Esta é a parte principal da correção.
     *
     * Não usamos somente a caixa do SVG.
     * Criamos uma área de segurança ao redor
     * do centro do marcador.
     *
     * Assim o rótulo jamais poderá atravessar
     * a região ocupada pelo pin.
     */
    function obterZonaProtegidaPin(wrapper) {

        const pin =
            obterPinCentro(wrapper);

        if (!pin) {
            return null;
        }

        return {
            left:
                pin.left -
                ESPACO_PIN,

            right:
                pin.right +
                ESPACO_PIN,

            top:
                pin.top -
                ESPACO_PIN,

            bottom:
                pin.bottom +
                ESPACO_PIN
        };

    }


    function caixasSeSobrepoem(
        a,
        b,
        margem
    ) {

        if (!a || !b) {
            return false;
        }

        const m =
            margem || 0;

        return !(
            a.right <
                b.left - m
            ||
            a.left >
                b.right + m
            ||
            a.bottom <
                b.top - m
            ||
            a.top >
                b.bottom + m
        );

    }


    function aplicarPosicao(
        label,
        pos
    ) {

        label.style.transform = "";

        switch (pos) {

            case "top":

                label.style.left =
                    "50%";

                label.style.top =
                    "-18px";

                label.style.transform =
                    "translate(-50%, -100%)";

                break;


            case "bottom":

                label.style.left =
                    "50%";

                label.style.top =
                    "62px";

                label.style.transform =
                    "translateX(-50%)";

                break;


            case "right":

                label.style.left =
                    "62px";

                label.style.top =
                    "50%";

                label.style.transform =
                    "translateY(-50%)";

                break;


            case "left":

                label.style.left =
                    "-18px";

                label.style.top =
                    "50%";

                label.style.transform =
                    "translate(-100%, -50%)";

                break;


            case "top-right":

                label.style.left =
                    "58px";

                label.style.top =
                    "-14px";

                label.style.transform =
                    "translateY(-100%)";

                break;


            case "top-left":

                label.style.left =
                    "-14px";

                label.style.top =
                    "-14px";

                label.style.transform =
                    "translate(-100%, -100%)";

                break;


            case "bottom-right":

                label.style.left =
                    "58px";

                label.style.top =
                    "58px";

                break;


            case "bottom-left":

                label.style.left =
                    "-14px";

                label.style.top =
                    "58px";

                label.style.transform =
                    "translateX(-100%)";

                break;

        }

    }


    function dentroDoMapa(
        rect,
        mapaRect
    ) {

        return (
            rect.left >=
                mapaRect.left -
                MARGEM_MAPA
            &&
            rect.right <=
                mapaRect.right +
                MARGEM_MAPA
            &&
            rect.top >=
                mapaRect.top -
                MARGEM_MAPA
            &&
            rect.bottom <=
                mapaRect.bottom +
                MARGEM_MAPA
        );

    }


    function prioridadeWrapper(
        wrapper
    ) {

        const prioridade =
            Number(
                wrapper.dataset.bpPriority
            );

        if (
            Number.isNaN(prioridade)
        ) {
            return 0;
        }

        return prioridade;

    }


    function ehIndividual(
        wrapper
    ) {

        return wrapper.classList.contains(
            "bp-individual-marker-wrapper"
        );

    }


    function recalcularRotulos() {

        const map =
            obterMapa();

        if (!map) {
            return;
        }

        const container =
            map.getContainer();

        if (!container) {
            return;
        }

        const mapaRect =
            container.getBoundingClientRect();

        const wrappers =
            obterWrappers(map);


        /*
         * Primeiro coletamos todos os pins.
         *
         * Isso é importante:
         * o algoritmo sabe onde todos os pins
         * estão antes de começar a posicionar
         * os rótulos.
         */
        const zonasPins =
            wrappers.map(
                wrapper => ({
                    wrapper: wrapper,
                    zona:
                        obterZonaProtegidaPin(
                            wrapper
                        )
                })
            );


        const candidatos = [];


        wrappers.forEach(
            wrapper => {

                const label =
                    wrapper.querySelector(
                        ".bp-label-card"
                    );

                if (!label) {
                    return;
                }

                label.style.display =
                    "block";

                label.style.visibility =
                    "hidden";

                label.style.opacity =
                    "0";


                /*
                 * Pega a cor do próprio pin.
                 */
                const path =
                    wrapper.querySelector(
                        ".bp-pin-svg path"
                    );

                if (path) {

                    const cor =
                        path.getAttribute(
                            "fill"
                        );

                    if (cor) {

                        label.style
                            .setProperty(
                                "--bp-label-color",
                                cor
                            );

                    }

                }


                candidatos.push({
                    wrapper: wrapper,
                    label: label,
                    prioridade:
                        prioridadeWrapper(
                            wrapper
                        ),
                    individual:
                        ehIndividual(
                            wrapper
                        )
                });

            }
        );


        /*
         * Individual primeiro.
         * Dentro de cada grupo, maior quantidade
         * recebe prioridade.
         */
        candidatos.sort(
            (a, b) => {

                if (
                    a.individual !==
                    b.individual
                ) {

                    return a.individual
                        ? -1
                        : 1;

                }

                return (
                    b.prioridade -
                    a.prioridade
                );

            }
        );


        const rotulosAceitos = [];


        candidatos.forEach(
            item => {

                const label =
                    item.label;

                const wrapper =
                    item.wrapper;

                let aceitou =
                    false;


                for (
                    let i = 0;
                    i < POSICOES.length;
                    i++
                ) {

                    const pos =
                        POSICOES[i];


                    aplicarPosicao(
                        label,
                        pos
                    );


                    /*
                     * Força o navegador a calcular
                     * a nova posição imediatamente.
                     */
                    const rect =
                        label.getBoundingClientRect();


                    /*
                     * 1. Não pode sair do mapa.
                     */
                    if (
                        !dentroDoMapa(
                            rect,
                            mapaRect
                        )
                    ) {
                        continue;
                    }


                    /*
                     * 2. Não pode bater em
                     * outro rótulo já aceito.
                     */
                    let colideRotulo =
                        false;

                    for (
                        let j = 0;
                        j <
                        rotulosAceitos.length;
                        j++
                    ) {

                        if (
                            caixasSeSobrepoem(
                                rect,
                                rotulosAceitos[j],
                                MARGEM_ROTULO
                            )
                        ) {

                            colideRotulo =
                                true;

                            break;

                        }

                    }

                    if (
                        colideRotulo
                    ) {
                        continue;
                    }


                    /*
                     * 3. NÃO PODE ocupar a área
                     * protegida de nenhum PIN.
                     *
                     * Aqui está a correção principal.
                     */
                    let colidePin =
                        false;


                    for (
                        let j = 0;
                        j <
                        zonasPins.length;
                        j++
                    ) {

                        const itemPin =
                            zonasPins[j];

                        if (
                            !itemPin.zona
                        ) {
                            continue;
                        }


                        /*
                         * O próprio pin também é
                         * considerado obstáculo.
                         *
                         * Isso impede que o rótulo
                         * nasça sobre o próprio pin.
                         */
                        if (
                            caixasSeSobrepoem(
                                rect,
                                itemPin.zona,
                                0
                            )
                        ) {

                            colidePin =
                                true;

                            break;

                        }

                    }


                    if (
                        colidePin
                    ) {
                        continue;
                    }


                    /*
                     * Encontramos uma posição
                     * realmente livre.
                     */
                    aceitou =
                        true;

                    label.style.visibility =
                        "visible";

                    label.style.opacity =
                        "1";

                    rotulosAceitos.push(
                        rect
                    );

                    break;

                }


                /*
                 * Se nenhuma das 8 posições
                 * for possível, simplesmente
                 * não mostramos o rótulo.
                 */
                if (!aceitou) {

                    label.style.display =
                        "none";

                    label.style.visibility =
                        "hidden";

                    label.style.opacity =
                        "0";

                }

            }
        );

    }


    let recalculoAgendado =
        false;


    function solicitarRecalculo() {

        if (
            recalculoAgendado
        ) {
            return;
        }

        recalculoAgendado =
            true;


        requestAnimationFrame(
            function() {

                recalculoAgendado =
                    false;

                recalcularRotulos();

            }
        );

    }


    function iniciar() {

        const map =
            obterMapa();

        if (!map) {

            setTimeout(
                iniciar,
                300
            );

            return;
        }


        map.on(
            "zoomend",
            solicitarRecalculo
        );

        map.on(
            "moveend",
            solicitarRecalculo
        );

        map.on(
            "resize",
            solicitarRecalculo
        );


        window.addEventListener(
            "resize",
            solicitarRecalculo
        );


        /*
         * Aguarda o Leaflet terminar
         * de renderizar os SVGs.
         */
        setTimeout(
            solicitarRecalculo,
            100
        );

        setTimeout(
            solicitarRecalculo,
            300
        );

        setTimeout(
            solicitarRecalculo,
            700
        );

        setTimeout(
            solicitarRecalculo,
            1200
        );

    }


    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            iniciar
        );

    } else {

        iniciar();

    }

})();
"""


declutter_js = (
    declutter_js
    .replace(
        "__MAP_NAME__",
        map_name
    )
)


m.get_root().html.add_child(
    Element(
        f"<script>{declutter_js}</script>"
    )
)


# ============================================================
# EXIBIÇÃO DO MAPA
# ============================================================

st_folium(
    m,
    width=None,
    height=720,
    returned_objects=[]
)


# ============================================================
# MODO ADICIONAR PONTO
# ============================================================

if modo_adicionar:

    st.markdown(
        "---"
    )

    st.subheader(
        "📍 Adicionar ponto"
    )

    st.info(
        "Preencha os dados abaixo para cadastrar "
        "uma nova medição."
    )

    col_a, col_b = st.columns(2)

    with col_a:

        nova_data = st.date_input(
            "Data",
            value=date.today()
        )

        novo_municipio = st.text_input(
            "Município"
        )

        novo_bairro = st.text_input(
            "Bairro"
        )

        nova_matricula = st.text_input(
            "Matrícula"
        )

    with col_b:

        nova_latitude = st.number_input(
            "Latitude",
            value=float(LAT_BASE),
            format="%.6f"
        )

        nova_longitude = st.number_input(
            "Longitude",
            value=float(LON_BASE),
            format="%.6f"
        )

        nova_pressao = st.number_input(
            "Pressão (MCA)",
            min_value=0.0,
            value=0.0,
            step=0.1
        )

        nova_observacao = st.text_area(
            "Observação"
        )

    if st.button(
        "💾 Salvar ponto",
        type="primary"
    ):

        if not novo_municipio.strip():

            st.error(
                "Informe o município."
            )

        elif not novo_bairro.strip():

            st.error(
                "Informe o bairro."
            )

        elif (
            nova_latitude == 0
            or
            nova_longitude == 0
        ):

            st.error(
                "Informe coordenadas válidas."
            )

        else:

            sucesso = adicionar_ponto(
                nova_data,
                novo_municipio,
                novo_bairro,
                nova_latitude,
                nova_longitude,
                nova_pressao,
                nova_observacao,
                nova_matricula
            )

            if sucesso:

                st.success(
                    "Ponto adicionado com sucesso."
                )

                time.sleep(
                    0.5
                )

                st.rerun()


# ============================================================
# TABELA DE DADOS
# ============================================================

with st.expander(
    "📋 Visualizar dados filtrados"
):

    if df_filtrado.empty:

        st.info(
            "Nenhum registro encontrado "
            "com os filtros selecionados."
        )

    else:

        colunas_exibicao = [
            "ID",
            "Data",
            "Municipio",
            "Bairro",
            "Latitude",
            "Longitude",
            "Pressao_MCA",
            "Classificacao",
            "Observacao",
            "Matricula"
        ]

        df_tabela = df_filtrado[
            colunas_exibicao
        ].copy()

        st.dataframe(
            df_tabela,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# EXPORTAÇÕES
# ============================================================

st.markdown(
    "---"
)

st.subheader(
    "📤 Exportar dados"
)

col_exp1, col_exp2 = st.columns(2)

with col_exp1:

    arquivo_xlsx = exportar_xlsx(
        df_filtrado
    )

    st.download_button(
        "⬇️ Exportar XLSX",
        data=arquivo_xlsx,
        file_name=(
            "monitoramento_baixa_pressao.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True
    )


with col_exp2:

    arquivo_kml = exportar_kml(
        df_filtrado
    )

    st.download_button(
        "🌎 Exportar KML",
        data=arquivo_kml,
        file_name=(
            "monitoramento_baixa_pressao.kml"
        ),
        mime="application/vnd.google-earth.kml+xml",
        use_container_width=True
    )
