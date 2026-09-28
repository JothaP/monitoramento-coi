import io
import hashlib
import json
import unicodedata
from datetime import datetime, date, timedelta

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
import folium

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÕES
# ============================================================

st.set_page_config(
    page_title="Vazão de Poços",
    layout="wide",
    initial_sidebar_state="expanded",
)

verificar_autenticacao()


SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"

NOME_ABA_POCOS = "POCOS"
NOME_ABA_LEITURAS = "LEITURAS_POCOS"

CABECALHO_POCOS = [
    "ID_POCO",
    "IDENTIFICACAO_ATIVO",
    "NOME_POCO",
    "MUNICIPIO",
    "LATITUDE",
    "LONGITUDE",
]

CABECALHO_LEITURAS = [
    "ID_LEITURA",
    "ID_POCO",
    "DATA_LEITURA",
    "VAZAO",
    "UNIDADE",
]

UNIDADES_VAZAO = [
    "L/s — Litros por segundo",
    "L/min — Litros por minuto",
    "L/h — Litros por hora",
    "m³/h — Metros cúbicos por hora",
    "m³/dia — Metros cúbicos por dia",
    "m³/s — Metros cúbicos por segundo",
]


# ============================================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================================

@st.cache_resource(show_spinner=False)
def obter_cliente_google():
    """
    Cria o cliente gspread uma única vez por processo do Streamlit.

    Usa a mesma autenticação já utilizada pelos demais módulos
    da Plataforma COI.
    """
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

    return gspread.authorize(credentials)


@st.cache_resource(show_spinner=False)
def obter_planilha():
    """
    Abre a planilha uma única vez.

    Isso evita que cada rerun execute novamente open_by_key().
    """
    cliente = obter_cliente_google()

    return cliente.open_by_key(
        SPREADSHEET_ID
    )


@st.cache_resource(show_spinner=False)
def obter_aba(nome_aba):
    """
    Mantém a referência da worksheet em cache.

    A chamada worksheet() deixa de acontecer a cada rerun.
    """
    planilha = obter_planilha()

    try:
        return planilha.worksheet(
            nome_aba
        )

    except gspread.WorksheetNotFound:

        if nome_aba == NOME_ABA_POCOS:

            aba = planilha.add_worksheet(
                title=nome_aba,
                rows=1000,
                cols=len(CABECALHO_POCOS),
            )

            aba.update(
                "A1",
                [CABECALHO_POCOS],
            )

            return aba

        if nome_aba == NOME_ABA_LEITURAS:

            aba = planilha.add_worksheet(
                title=nome_aba,
                rows=2000,
                cols=len(CABECALHO_LEITURAS),
            )

            aba.update(
                "A1",
                [CABECALHO_LEITURAS],
            )

            return aba

        raise


@st.cache_resource(show_spinner=False)
def obter_abas():
    """
    Obtém as duas abas uma única vez.
    """
    return (
        obter_aba(NOME_ABA_POCOS),
        obter_aba(NOME_ABA_LEITURAS),
    )


# ============================================================
# CACHE DOS DADOS
# ============================================================

@st.cache_data(
    ttl=30,
    show_spinner=False,
)
def carregar_pocos():
    """
    Faz somente uma leitura da aba POCOS a cada 30 segundos,
    salvo quando o cache é invalidado explicitamente após
    uma operação de escrita.
    """
    aba_pocos, _ = obter_abas()

    registros = aba_pocos.get_all_records()

    if not registros:
        return pd.DataFrame(
            columns=CABECALHO_POCOS
        )

    df = pd.DataFrame(registros)

    for coluna in CABECALHO_POCOS:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[
        CABECALHO_POCOS
    ].copy()


@st.cache_data(
    ttl=30,
    show_spinner=False,
)
def carregar_leituras():
    """
    Faz somente uma leitura da aba LEITURAS_POCOS
    a cada 30 segundos.
    """
    _, aba_leituras = obter_abas()

    registros = aba_leituras.get_all_records()

    if not registros:
        return pd.DataFrame(
            columns=CABECALHO_LEITURAS
        )

    df = pd.DataFrame(registros)

    for coluna in CABECALHO_LEITURAS:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[
        CABECALHO_LEITURAS
    ].copy()


def invalidar_cache_dados():
    """
    Deve ser chamado somente depois de escrever
    na planilha.
    """
    carregar_pocos.clear()
    carregar_leituras.clear()


# ============================================================
# GARANTIA DOS CABEÇALHOS
# ============================================================

def garantir_cabecalhos():
    """
    Verifica os cabeçalhos somente quando necessário.

    Não é chamada a cada rerun normal.
    """
    aba_pocos, aba_leituras = obter_abas()

    cab_pocos = aba_pocos.row_values(1)

    if cab_pocos != CABECALHO_POCOS:
        aba_pocos.update(
            "A1",
            [CABECALHO_POCOS],
        )

    cab_leituras = aba_leituras.row_values(1)

    if cab_leituras != CABECALHO_LEITURAS:
        aba_leituras.update(
            "A1",
            [CABECALHO_LEITURAS],
        )


# ============================================================
# UTILITÁRIOS
# ============================================================

def normalizar_texto(valor):
    texto = "" if valor is None else str(valor)

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    ).encode(
        "ascii",
        "ignore",
    ).decode(
        "ascii"
    )

    return texto.strip().upper()


def normalizar_numero(valor):
    try:
        if valor is None or str(valor).strip() == "":
            return None

        texto = str(valor).strip()

        # Aceita números armazenados com vírgula decimal.
        texto = texto.replace(",", ".")

        return float(texto)

    except (ValueError, TypeError):
        return None


def novo_id(prefixo, valores):
    """
    Gera IDs internos sequenciais.

    Exemplo:
    POCO00001
    LEIT00001
    """
    maior = 0

    if valores is not None:

        for valor in valores:

            texto = str(valor).strip()

            if texto.startswith(prefixo):

                parte = texto[len(prefixo):]

                try:
                    numero = int(parte)
                    maior = max(
                        maior,
                        numero,
                    )

                except ValueError:
                    pass

    return f"{prefixo}{maior + 1:05d}"


def identificacao_exibicao(row):
    identificacao = str(
        row.get(
            "IDENTIFICACAO_ATIVO",
            "",
        )
    ).strip()

    nome = str(
        row.get(
            "NOME_POCO",
            "",
        )
    ).strip()

    if nome and identificacao:
        return f"{nome} — {identificacao}"

    if nome:
        return nome

    if identificacao:
        return identificacao

    return str(
        row.get(
            "ID_POCO",
            "",
        )
    )


def converter_data(valor):
    if valor is None or str(valor).strip() == "":
        return pd.NaT

    return pd.to_datetime(
        valor,
        errors="coerce",
        dayfirst=True,
    )


def formatar_data(valor):
    data_convertida = converter_data(valor)

    if pd.isna(data_convertida):
        return ""

    return data_convertida.strftime(
        "%d/%m/%Y"
    )


def dias_desde_leitura(data_leitura):
    data_convertida = converter_data(
        data_leitura
    )

    if pd.isna(data_convertida):
        return None

    return (
        pd.Timestamp.today().normalize()
        - data_convertida.normalize()
    ).days


# ============================================================
# PREPARAÇÃO DOS DATAFRAMES
# ============================================================

def preparar_pocos(df):
    df = df.copy()

    if df.empty:
        return df

    for coluna in [
        "ID_POCO",
        "IDENTIFICACAO_ATIVO",
        "NOME_POCO",
        "MUNICIPIO",
    ]:
        if coluna in df.columns:
            df[coluna] = (
                df[coluna]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    # ========================================================
    # CORREÇÃO DAS COORDENADAS
    # ========================================================
    # Os dados podem estar no Google Sheets como:
    # - número;
    # - texto com ponto decimal;
    # - texto com vírgula decimal.
    #
    # pd.to_numeric() sozinho descarta valores como
    # "-5,0892". Por isso usamos normalizar_numero().
    # ========================================================

    df["LATITUDE"] = df[
        "LATITUDE"
    ].apply(normalizar_numero)

    df["LONGITUDE"] = df[
        "LONGITUDE"
    ].apply(normalizar_numero)

    return df


def preparar_leituras(df):
    df = df.copy()

    if df.empty:
        return df

    for coluna in [
        "ID_LEITURA",
        "ID_POCO",
        "VAZAO",
        "UNIDADE",
    ]:
        if coluna in df.columns:
            df[coluna] = (
                df[coluna]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    df["DATA_LEITURA_DT"] = pd.to_datetime(
        df["DATA_LEITURA"],
        errors="coerce",
        dayfirst=True,
    )

    df["VAZAO_NUM"] = pd.to_numeric(
        df["VAZAO"]
        .astype(str)
        .str.replace(
            ",",
            ".",
            regex=False,
        ),
        errors="coerce",
    )

    return df


# ============================================================
# OPERAÇÕES DE ESCRITA
# ============================================================

def adicionar_poco(
    identificacao,
    nome,
    municipio,
    latitude,
    longitude,
):
    aba_pocos, _ = obter_abas()

    df = carregar_pocos()

    ids = (
        df["ID_POCO"].tolist()
        if not df.empty
        else []
    )

    id_poco = novo_id(
        "POCO",
        ids,
    )

    aba_pocos.append_row(
        [
            id_poco,
            identificacao,
            nome,
            municipio,
            latitude,
            longitude,
        ],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()

    return id_poco


def atualizar_poco(
    linha_planilha,
    id_poco,
    identificacao,
    nome,
    municipio,
    latitude,
    longitude,
):
    aba_pocos, _ = obter_abas()

    valores = [
        id_poco,
        identificacao,
        nome,
        municipio,
        latitude,
        longitude,
    ]

    aba_pocos.update(
        f"A{linha_planilha}:F{linha_planilha}",
        [valores],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()


def excluir_poco(linha_planilha):
    aba_pocos, _ = obter_abas()

    aba_pocos.delete_rows(
        linha_planilha
    )

    invalidar_cache_dados()


def adicionar_leitura(
    id_poco,
    data_leitura,
    vazao,
    unidade,
):
    _, aba_leituras = obter_abas()

    df = carregar_leituras()

    ids = (
        df["ID_LEITURA"].tolist()
        if not df.empty
        else []
    )

    id_leitura = novo_id(
        "LEIT",
        ids,
    )

    data_formatada = pd.to_datetime(
        data_leitura
    ).strftime(
        "%d/%m/%Y"
    )

    aba_leituras.append_row(
        [
            id_leitura,
            id_poco,
            data_formatada,
            vazao,
            unidade,
        ],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()

    return id_leitura


def atualizar_leitura(
    linha_planilha,
    id_leitura,
    id_poco,
    data_leitura,
    vazao,
    unidade,
):
    _, aba_leituras = obter_abas()

    data_formatada = pd.to_datetime(
        data_leitura
    ).strftime(
        "%d/%m/%Y"
    )

    aba_leituras.update(
        f"A{linha_planilha}:E{linha_planilha}",
        [[
            id_leitura,
            id_poco,
            data_formatada,
            vazao,
            unidade,
        ]],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()


def excluir_leitura(linha_planilha):
    _, aba_leituras = obter_abas()

    aba_leituras.delete_rows(
        linha_planilha
    )

    invalidar_cache_dados()


# ============================================================
# CARREGAMENTO INICIAL
# ============================================================

try:
    aba_pocos, aba_leituras = obter_abas()

except Exception as erro:
    st.error(
        f"Não foi possível acessar o Google Sheets: {erro}"
    )
    st.stop()


# ============================================================
# TÍTULO
# ============================================================

st.title("Vazão de Poços")

st.caption(
    "Cadastro de poços, leituras de vazão, mapa e histórico."
)


# ============================================================
# DADOS
# ============================================================

try:
    df_pocos = preparar_pocos(
        carregar_pocos()
    )

    df_leituras = preparar_leituras(
        carregar_leituras()
    )

except Exception as erro:
    st.error(
        f"Erro ao carregar os dados: {erro}"
    )
    st.stop()


# ============================================================
# GARANTIR CABEÇALHOS
# ============================================================

if (
    df_pocos.empty
    and df_leituras.empty
):
    try:
        garantir_cabecalhos()
    except Exception:
        pass


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Filtros")

hoje = date.today()
data_inicio_padrao = hoje - timedelta(
    days=30
)

periodo = st.sidebar.date_input(
    "Período das leituras",
    value=(
        data_inicio_padrao,
        hoje,
    ),
)

if (
    isinstance(periodo, tuple)
    and len(periodo) == 2
):
    data_inicio, data_fim = periodo
else:
    data_inicio = data_inicio_padrao
    data_fim = hoje


municipios = []

if not df_pocos.empty:

    municipios = sorted(
        [
            x
            for x in df_pocos[
                "MUNICIPIO"
            ]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            if x
        ],
        key=normalizar_texto,
    )


municipio_filtro = st.sidebar.selectbox(
    "Município",
    ["Todos"] + municipios,
)


pocos_disponiveis = df_pocos.copy()

if (
    municipio_filtro != "Todos"
    and not pocos_disponiveis.empty
):

    pocos_disponiveis = pocos_disponiveis[
        pocos_disponiveis[
            "MUNICIPIO"
        ].astype(str).str.strip()
        == municipio_filtro
    ]


opcoes_pocos = ["Todos"]

if not pocos_disponiveis.empty:

    opcoes_pocos += [
        identificacao_exibicao(row)
        for _, row
        in pocos_disponiveis.iterrows()
    ]


poco_filtro = st.sidebar.selectbox(
    "Poço",
    opcoes_pocos,
)


# ============================================================
# LEITURAS DO PERÍODO
# ============================================================

leituras_periodo = df_leituras.copy()

if not leituras_periodo.empty:

    leituras_periodo = leituras_periodo[
        leituras_periodo[
            "DATA_LEITURA_DT"
        ].notna()
    ]

    leituras_periodo = leituras_periodo[
        (
            leituras_periodo[
                "DATA_LEITURA_DT"
            ].dt.date
            >= data_inicio
        )
        & (
            leituras_periodo[
                "DATA_LEITURA_DT"
            ].dt.date
            <= data_fim
        )
    ]


# ============================================================
# FILTRO DE POÇOS
# ============================================================

pocos_mapa = df_pocos.copy()

if municipio_filtro != "Todos":

    pocos_mapa = pocos_mapa[
        pocos_mapa[
            "MUNICIPIO"
        ].astype(str).str.strip()
        == municipio_filtro
    ]


if poco_filtro != "Todos":

    pocos_mapa = pocos_mapa[
        pocos_mapa.apply(
            identificacao_exibicao,
            axis=1,
        )
        == poco_filtro
    ]


# ============================================================
# ÚLTIMA LEITURA DE CADA POÇO NO PERÍODO
# ============================================================

ultimas_leituras = {}

if not leituras_periodo.empty:

    ordenadas = leituras_periodo.sort_values(
        "DATA_LEITURA_DT"
    )

    for id_poco, grupo in ordenadas.groupby(
        "ID_POCO"
    ):

        ultimas_leituras[
            str(id_poco)
        ] = grupo.iloc[-1]


# ============================================================
# MÉTRICAS
# ============================================================

col1, col2, col3 = st.columns(3)

col1.metric(
    "Poços cadastrados",
    len(df_pocos),
)

col2.metric(
    "Poços no filtro",
    len(pocos_mapa),
)

col3.metric(
    "Leituras no período",
    len(leituras_periodo),
)


# ============================================================
# MAPA
# ============================================================

st.subheader("Mapa dos poços")

TIPOS_MAPA = {
    "OpenStreetMap": {
        "tiles": "OpenStreetMap",
        "attr": None,
    },
    "Esri World Imagery": {
        "tiles": (
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/"
            "{z}/{y}/{x}"
        ),
        "attr": "Esri",
    },
    "OpenTopoMap": {
        "tiles": (
            "https://{s}.tile.opentopomap.org/"
            "{z}/{x}/{y}.png"
        ),
        "attr": "OpenTopoMap",
    },
}

tipo_mapa = st.selectbox(
    "Mapa",
    list(TIPOS_MAPA.keys()),
)

# ============================================================
# COORDENADAS DOS POÇOS
# ============================================================

coordenadas = pocos_mapa[
    pocos_mapa["LATITUDE"].notna()
    & pocos_mapa["LONGITUDE"].notna()
].copy()

# Mantém somente coordenadas dentro dos limites geográficos.
coordenadas = coordenadas[
    coordenadas["LATITUDE"].between(
        -90,
        90,
    )
    & coordenadas["LONGITUDE"].between(
        -180,
        180,
    )
].copy()


if not coordenadas.empty:

    centro_lat = coordenadas[
        "LATITUDE"
    ].mean()

    centro_lon = coordenadas[
        "LONGITUDE"
    ].mean()

elif not df_pocos.empty:

    coordenadas_todas = df_pocos[
        df_pocos["LATITUDE"].notna()
        & df_pocos["LONGITUDE"].notna()
    ].copy()

    coordenadas_todas = coordenadas_todas[
        coordenadas_todas[
            "LATITUDE"
        ].between(-90, 90)
        & coordenadas_todas[
            "LONGITUDE"
        ].between(-180, 180)
    ]

    if not coordenadas_todas.empty:

        centro_lat = coordenadas_todas[
            "LATITUDE"
        ].mean()

        centro_lon = coordenadas_todas[
            "LONGITUDE"
        ].mean()

    else:

        centro_lat = -5.0892
        centro_lon = -42.8016

else:

    centro_lat = -5.0892
    centro_lon = -42.8016


config_mapa = TIPOS_MAPA[
    tipo_mapa
]

mapa = folium.Map(
    location=[
        centro_lat,
        centro_lon,
    ],
    zoom_start=7,
    tiles=config_mapa["tiles"],
    attr=config_mapa["attr"],
)


# ============================================================
# MARCADORES
# ============================================================

for _, poco in coordenadas.iterrows():

    id_poco = str(
        poco["ID_POCO"]
    )

    leitura = ultimas_leituras.get(
        id_poco
    )

    nome_exibicao = identificacao_exibicao(
        poco
    )

    if leitura is None:

        status = "Sem leitura no período"

        detalhe_leitura = (
            "Sem leitura registrada no período."
        )

    else:

        vazao = leitura["VAZAO"]
        unidade = leitura["UNIDADE"]

        data_leitura = (
            leitura["DATA_LEITURA_DT"]
        )

        dias = dias_desde_leitura(
            data_leitura
        )

        status = (
            f"{vazao} {unidade}"
        )

        detalhe_leitura = (
            f"<b>Última leitura:</b> "
            f"{data_leitura.strftime('%d/%m/%Y')}<br>"
            f"<b>Vazão:</b> "
            f"{vazao} {unidade}<br>"
            f"<b>Dias desde a leitura:</b> "
            f"{dias}"
        )

    popup_html = f"""
    <div style="min-width:250px">
        <b>{nome_exibicao}</b><br><br>

        <b>Município:</b>
        {poco["MUNICIPIO"]}<br>

        <b>ID interno:</b>
        {id_poco}<br><br>

        <b>Latitude:</b>
        {poco["LATITUDE"]}<br>

        <b>Longitude:</b>
        {poco["LONGITUDE"]}<br><br>

        <b>Status:</b>
        {status}<br><br>

        {detalhe_leitura}
    </div>
    """

    folium.Marker(
        location=[
            float(poco["LATITUDE"]),
            float(poco["LONGITUDE"]),
        ],
        tooltip=nome_exibicao,
        popup=folium.Popup(
            popup_html,
            max_width=350,
        ),
    ).add_to(mapa)


# Ajusta o mapa automaticamente aos poços
# quando houver pelo menos um ponto válido.
if not coordenadas.empty:

    mapa.fit_bounds(
        [
            [
                coordenadas["LATITUDE"].min(),
                coordenadas["LONGITUDE"].min(),
            ],
            [
                coordenadas["LATITUDE"].max(),
                coordenadas["LONGITUDE"].max(),
            ],
        ],
        padding=(30, 30),
    )


st_folium(
    mapa,
    width=None,
    height=600,
)


# ============================================================
# AVISO DE COORDENADAS INVÁLIDAS
# ============================================================

if (
    not pocos_mapa.empty
    and coordenadas.empty
):

    st.warning(
        "Os poços selecionados não possuem "
        "coordenadas válidas para exibição no mapa. "
        "Verifique Latitude e Longitude no cadastro."
    )


# ============================================================
# CADASTRO DE POÇOS
# ============================================================

st.subheader("Cadastro de poços")

with st.expander(
    "Cadastrar novo poço",
    expanded=False,
):

    with st.form(
        "form_novo_poco",
        clear_on_submit=True,
    ):

        identificacao = st.text_input(
            "Identificação do ativo *",
            placeholder="Ex.: PL-API-PCO0001",
        )

        nome = st.text_input(
            "Nome do poço",
            placeholder="Opcional",
        )

        municipio = st.text_input(
            "Município *"
        )

        col_lat, col_lon = st.columns(2)

        with col_lat:

            latitude = st.number_input(
                "Latitude *",
                format="%.7f",
                value=0.0,
            )

        with col_lon:

            longitude = st.number_input(
                "Longitude *",
                format="%.7f",
                value=0.0,
            )

        salvar_poco = st.form_submit_button(
            "Cadastrar poço"
        )

    if salvar_poco:

        if not identificacao.strip():

            st.error(
                "A identificação do ativo é obrigatória."
            )

        elif not municipio.strip():

            st.error(
                "O município é obrigatório."
            )

        elif latitude == 0.0:

            st.error(
                "Informe uma latitude válida."
            )

        elif longitude == 0.0:

            st.error(
                "Informe uma longitude válida."
            )

        else:

            try:

                id_criado = adicionar_poco(
                    identificacao=identificacao.strip(),
                    nome=nome.strip(),
                    municipio=municipio.strip(),
                    latitude=latitude,
                    longitude=longitude,
                )

                st.success(
                    f"Poço cadastrado com ID {id_criado}."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao cadastrar poço: {erro}"
                )


# ============================================================
# EDIÇÃO / EXCLUSÃO DE POÇOS
# ============================================================

if not df_pocos.empty:

    with st.expander(
        "Editar ou excluir poço",
        expanded=False,
    ):

        opcoes_edicao = {
            identificacao_exibicao(row): row
            for _, row in df_pocos.iterrows()
        }

        selecionado = st.selectbox(
            "Selecione o poço",
            list(opcoes_edicao.keys()),
            key="poco_edicao",
        )

        poco_atual = opcoes_edicao[
            selecionado
        ]

        linha_df = df_pocos.index[
            df_pocos[
                "ID_POCO"
            ].astype(str)
            == str(
                poco_atual[
                    "ID_POCO"
                ]
            )
        ]

        if len(linha_df) > 0:

            indice_df = linha_df[0]
            linha_planilha = indice_df + 2

        else:

            linha_planilha = None

        with st.form(
            "form_edicao_poco"
        ):

            identificacao_edit = st.text_input(
                "Identificação do ativo *",
                value=str(
                    poco_atual[
                        "IDENTIFICACAO_ATIVO"
                    ]
                ),
            )

            nome_edit = st.text_input(
                "Nome do poço",
                value=str(
                    poco_atual[
                        "NOME_POCO"
                    ]
                ),
            )

            municipio_edit = st.text_input(
                "Município *",
                value=str(
                    poco_atual[
                        "MUNICIPIO"
                    ]
                ),
            )

            col_lat, col_lon = st.columns(2)

            with col_lat:

                latitude_edit = st.number_input(
                    "Latitude *",
                    value=float(
                        poco_atual[
                            "LATITUDE"
                        ]
                    ),
                    format="%.7f",
                )

            with col_lon:

                longitude_edit = st.number_input(
                    "Longitude *",
                    value=float(
                        poco_atual[
                            "LONGITUDE"
                        ]
                    ),
                    format="%.7f",
                )

            salvar_edicao = st.form_submit_button(
                "Salvar alterações"
            )

        if salvar_edicao:

            if not identificacao_edit.strip():

                st.error(
                    "A identificação do ativo é obrigatória."
                )

            elif not municipio_edit.strip():

                st.error(
                    "O município é obrigatório."
                )

            else:

                try:

                    atualizar_poco(
                        linha_planilha=linha_planilha,
                        id_poco=str(
                            poco_atual[
                                "ID_POCO"
                            ]
                        ),
                        identificacao=identificacao_edit.strip(),
                        nome=nome_edit.strip(),
                        municipio=municipio_edit.strip(),
                        latitude=latitude_edit,
                        longitude=longitude_edit,
                    )

                    st.success(
                        "Poço atualizado com sucesso."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao atualizar poço: {erro}"
                    )

        leituras_vinculadas = (
            df_leituras[
                df_leituras[
                    "ID_POCO"
                ].astype(str)
                == str(
                    poco_atual[
                        "ID_POCO"
                    ]
                )
            ]
            if not df_leituras.empty
            else pd.DataFrame()
        )

        st.divider()

        if not leituras_vinculadas.empty:

            st.warning(
                f"Este poço possui "
                f"{len(leituras_vinculadas)} "
                f"leitura(s) vinculada(s)."
            )

        confirmar_exclusao = st.checkbox(
            "Confirmo que desejo excluir este poço.",
            key="confirmar_exclusao_poco",
        )

        if st.button(
            "Excluir poço",
            type="secondary",
            key="btn_excluir_poco",
        ):

            if not confirmar_exclusao:

                st.warning(
                    "Marque a confirmação antes de excluir."
                )

            elif linha_planilha is None:

                st.error(
                    "Não foi possível localizar a linha do poço."
                )

            else:

                try:

                    excluir_poco(
                        linha_planilha
                    )

                    st.success(
                        "Poço excluído."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao excluir poço: {erro}"
                    )


# ============================================================
# REGISTRO DE LEITURAS
# ============================================================

st.subheader("Leituras de vazão")

if df_pocos.empty:

    st.info(
        "Cadastre pelo menos um poço para registrar leituras."
    )

else:

    with st.expander(
        "Registrar nova leitura",
        expanded=False,
    ):

        opcoes_leitura = {
            identificacao_exibicao(row): row[
                "ID_POCO"
            ]
            for _, row in df_pocos.iterrows()
        }

        with st.form(
            "form_nova_leitura",
            clear_on_submit=True,
        ):

            poco_leitura = st.selectbox(
                "Poço",
                list(
                    opcoes_leitura.keys()
                ),
            )

            data_leitura = st.date_input(
                "Data da leitura",
                value=date.today(),
            )

            col_vazao, col_unidade = st.columns(2)

            with col_vazao:

                vazao = st.number_input(
                    "Vazão",
                    min_value=0.0,
                    format="%.4f",
                )

            with col_unidade:

                unidade = st.selectbox(
                    "Unidade",
                    UNIDADES_VAZAO,
                )

            salvar_leitura = st.form_submit_button(
                "Registrar leitura"
            )

        if salvar_leitura:

            try:

                id_leitura = adicionar_leitura(
                    id_poco=opcoes_leitura[
                        poco_leitura
                    ],
                    data_leitura=data_leitura,
                    vazao=vazao,
                    unidade=unidade,
                )

                st.success(
                    f"Leitura registrada com ID {id_leitura}."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao registrar leitura: {erro}"
                )


# ============================================================
# HISTÓRICO
# ============================================================

st.subheader("Histórico de leituras")

if df_leituras.empty:

    st.info(
        "Nenhuma leitura registrada."
    )

else:

    historico = df_leituras.merge(
        df_pocos[
            [
                "ID_POCO",
                "IDENTIFICACAO_ATIVO",
                "NOME_POCO",
                "MUNICIPIO",
            ]
        ],
        on="ID_POCO",
        how="left",
    )

    historico["POÇO"] = historico.apply(
        identificacao_exibicao,
        axis=1,
    )

    historico["DATA"] = historico[
        "DATA_LEITURA_DT"
    ].dt.strftime(
        "%d/%m/%Y"
    )

    historico = historico.sort_values(
        "DATA_LEITURA_DT",
        ascending=False,
    )

    colunas_historico = [
        "ID_LEITURA",
        "ID_POCO",
        "POÇO",
        "IDENTIFICACAO_ATIVO",
        "NOME_POCO",
        "MUNICIPIO",
        "DATA",
        "VAZAO",
        "UNIDADE",
    ]

    st.dataframe(
        historico[
            colunas_historico
        ],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# EDITAR / EXCLUIR LEITURAS
# ============================================================

if not df_leituras.empty:

    with st.expander(
        "Editar ou excluir leitura",
        expanded=False,
    ):

        historico_opcoes = {}

        for _, leitura in df_leituras.iterrows():

            poco = df_pocos[
                df_pocos[
                    "ID_POCO"
                ].astype(str)
                == str(
                    leitura[
                        "ID_POCO"
                    ]
                )
            ]

            if not poco.empty:

                nome_poco = identificacao_exibicao(
                    poco.iloc[0]
                )

            else:

                nome_poco = str(
                    leitura[
                        "ID_POCO"
                    ]
                )

            data_texto = formatar_data(
                leitura[
                    "DATA_LEITURA"
                ]
            )

            chave = (
                f"{nome_poco} — "
                f"{data_texto} — "
                f"{leitura['VAZAO']} "
                f"{leitura['UNIDADE']} "
                f"— {leitura['ID_LEITURA']}"
            )

            historico_opcoes[
                chave
            ] = leitura

        leitura_selecionada = st.selectbox(
            "Selecione a leitura",
            list(
                historico_opcoes.keys()
            ),
            key="leitura_edicao",
        )

        leitura_atual = historico_opcoes[
            leitura_selecionada
        ]

        linha_df = df_leituras.index[
            df_leituras[
                "ID_LEITURA"
            ].astype(str)
            == str(
                leitura_atual[
                    "ID_LEITURA"
                ]
            )
        ]

        if len(linha_df) > 0:

            linha_leitura_planilha = (
                linha_df[0] + 2
            )

        else:

            linha_leitura_planilha = None

        poco_da_leitura = str(
            leitura_atual[
                "ID_POCO"
            ]
        )

        opcoes_pocos_edicao = {}

        for _, poco in df_pocos.iterrows():

            opcoes_pocos_edicao[
                identificacao_exibicao(poco)
            ] = poco[
                "ID_POCO"
            ]

        nome_poco_atual = None

        for nome, id_poco in opcoes_pocos_edicao.items():

            if str(id_poco) == poco_da_leitura:

                nome_poco_atual = nome

                break

        if nome_poco_atual is None:

            nome_poco_atual = list(
                opcoes_pocos_edicao.keys()
            )[0]

        with st.form(
            "form_edicao_leitura"
        ):

            poco_editado = st.selectbox(
                "Poço",
                list(
                    opcoes_pocos_edicao.keys()
                ),
                index=list(
                    opcoes_pocos_edicao.keys()
                ).index(
                    nome_poco_atual
                ),
            )

            data_editada = st.date_input(
                "Data da leitura",
                value=converter_data(
                    leitura_atual[
                        "DATA_LEITURA"
                    ]
                ).date(),
            )

            col_vazao, col_unidade = st.columns(2)

            with col_vazao:

                vazao_editada = st.number_input(
                    "Vazão",
                    min_value=0.0,
                    value=float(
                        leitura_atual[
                            "VAZAO_NUM"
                        ]
                        if pd.notna(
                            leitura_atual[
                                "VAZAO_NUM"
                            ]
                        )
                        else 0.0
                    ),
                    format="%.4f",
                )

            with col_unidade:

                unidade_editada = st.selectbox(
                    "Unidade",
                    UNIDADES_VAZAO,
                    index=(
                        UNIDADES_VAZAO.index(
                            leitura_atual[
                                "UNIDADE"
                            ]
                        )
                        if leitura_atual[
                            "UNIDADE"
                        ] in UNIDADES_VAZAO
                        else 0
                    ),
                )

            salvar_leitura_editada = st.form_submit_button(
                "Salvar alterações"
            )

        if salvar_leitura_editada:

            try:

                atualizar_leitura(
                    linha_planilha=linha_leitura_planilha,
                    id_leitura=str(
                        leitura_atual[
                            "ID_LEITURA"
                        ]
                    ),
                    id_poco=opcoes_pocos_edicao[
                        poco_editado
                    ],
                    data_leitura=data_editada,
                    vazao=vazao_editada,
                    unidade=unidade_editada,
                )

                st.success(
                    "Leitura atualizada com sucesso."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao atualizar leitura: {erro}"
                )

        confirmar_exclusao_leitura = st.checkbox(
            "Confirmo que desejo excluir esta leitura.",
            key="confirmar_exclusao_leitura",
        )

        if st.button(
            "Excluir leitura",
            type="secondary",
            key="btn_excluir_leitura",
        ):

            if not confirmar_exclusao_leitura:

                st.warning(
                    "Marque a confirmação antes de excluir."
                )

            elif linha_leitura_planilha is None:

                st.error(
                    "Não foi possível localizar a leitura."
                )

            else:

                try:

                    excluir_leitura(
                        linha_leitura_planilha
                    )

                    st.success(
                        "Leitura excluída."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao excluir leitura: {erro}"
                    )


# ============================================================
# GRÁFICO
# ============================================================

st.subheader("Evolução da vazão")

if df_pocos.empty:

    st.info(
        "Cadastre um poço para visualizar o gráfico."
    )

else:

    opcoes_grafico = {
        identificacao_exibicao(row): row[
            "ID_POCO"
        ]
        for _, row in df_pocos.iterrows()
    }

    poco_grafico = st.selectbox(
        "Poço para o gráfico",
        list(
            opcoes_grafico.keys()
        ),
        key="poco_grafico",
    )

    id_poco_grafico = opcoes_grafico[
        poco_grafico
    ]

    dados_grafico = df_leituras[
        df_leituras[
            "ID_POCO"
        ].astype(str)
        == str(
            id_poco_grafico
        )
    ].copy()

    if dados_grafico.empty:

        st.info(
            "Este poço ainda não possui leituras."
        )

    else:

        dados_grafico = dados_grafico.sort_values(
            "DATA_LEITURA_DT"
        )

        fig = px.line(
            dados_grafico,
            x="DATA_LEITURA_DT",
            y="VAZAO_NUM",
            markers=True,
            labels={
                "DATA_LEITURA_DT": "Data",
                "VAZAO_NUM": "Vazão",
            },
            title=poco_grafico,
        )

        fig.update_layout(
            hovermode="x unified"
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# INFORMAÇÃO SOBRE CACHE
# ============================================================

st.caption(
    "Dados sincronizados com Google Sheets. "
    "As leituras são mantidas em cache por até 30 segundos "
    "e o cache é atualizado imediatamente após alterações."
)
