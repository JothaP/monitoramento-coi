import streamlit as st
import gspread
import pandas as pd
import folium
import plotly.express as px

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium
from datetime import date, datetime, timedelta
from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Vazão de Poços - COI",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
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

if "modo_escuro_pocos" not in st.session_state:
    st.session_state.modo_escuro_pocos = False

if "mapa_tipo_pocos" not in st.session_state:
    st.session_state.mapa_tipo_pocos = "OpenStreetMap"

if "poço_selecionado_grafico" not in st.session_state:
    st.session_state.poço_selecionado_grafico = None


# ============================================================
# CSS
# ============================================================

if st.session_state.modo_escuro_pocos:
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #111827;
            color: #f3f4f6;
        }

        [data-testid="stSidebar"] {
            background-color: #1f2937;
        }

        [data-testid="stSidebar"] * {
            color: #f3f4f6 !important;
        }

        .stDataFrame {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# GOOGLE SHEETS
# ============================================================

SPREADSHEET_ID = st.secrets.get("SPREADSHEET_ID")

if not SPREADSHEET_ID:
    st.error("SPREADSHEET_ID não está configurado nos Secrets.")
    st.stop()


@st.cache_resource
def conectar_google_sheets():
    credenciais = Credentials.from_service_account_info(
        st.secrets["gcp_json"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(SPREADSHEET_ID)

    return planilha


try:
    planilha = conectar_google_sheets()
except Exception as e:
    st.error(f"Erro ao conectar ao Google Sheets: {e}")
    st.stop()


# ============================================================
# ABAS
# ============================================================

try:
    aba_pocos = planilha.worksheet("POCOS")
except gspread.WorksheetNotFound:
    aba_pocos = planilha.add_worksheet(
        title="POCOS",
        rows=1000,
        cols=20,
    )

try:
    aba_leituras = planilha.worksheet("LEITURAS_POCOS")
except gspread.WorksheetNotFound:
    aba_leituras = planilha.add_worksheet(
        title="LEITURAS_POCOS",
        rows=5000,
        cols=20,
    )


CABECALHO_POCOS = [
    "ID_POCO",
    "NOME",
    "MUNICIPIO",
    "LOCALIZACAO",
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


def garantir_cabecalho(aba, cabecalho):
    valores = aba.get_all_values()

    if not valores:
        aba.append_row(cabecalho)
        return

    primeira_linha = valores[0]

    if primeira_linha != cabecalho:
        aba.update(
            "A1",
            [cabecalho],
        )


garantir_cabecalho(aba_pocos, CABECALHO_POCOS)
garantir_cabecalho(aba_leituras, CABECALHO_LEITURAS)


# ============================================================
# LEITURA DOS DADOS
# ============================================================

@st.cache_data(ttl=10)
def carregar_pocos():
    dados = aba_pocos.get_all_records()

    if not dados:
        return pd.DataFrame(columns=CABECALHO_POCOS)

    df = pd.DataFrame(dados)

    for coluna in CABECALHO_POCOS:
        if coluna not in df.columns:
            df[coluna] = ""

    df = df[CABECALHO_POCOS]

    df["ID_POCO"] = df["ID_POCO"].astype(str).str.strip()
    df["NOME"] = df["NOME"].astype(str).str.strip()
    df["MUNICIPIO"] = df["MUNICIPIO"].astype(str).str.strip()
    df["LOCALIZACAO"] = df["LOCALIZACAO"].astype(str).str.strip()

    df["LATITUDE"] = pd.to_numeric(df["LATITUDE"], errors="coerce")
    df["LONGITUDE"] = pd.to_numeric(df["LONGITUDE"], errors="coerce")

    return df


@st.cache_data(ttl=10)
def carregar_leituras():
    dados = aba_leituras.get_all_records()

    if not dados:
        return pd.DataFrame(columns=CABECALHO_LEITURAS)

    df = pd.DataFrame(dados)

    for coluna in CABECALHO_LEITURAS:
        if coluna not in df.columns:
            df[coluna] = ""

    df = df[CABECALHO_LEITURAS]

    df["ID_LEITURA"] = df["ID_LEITURA"].astype(str).str.strip()
    df["ID_POCO"] = df["ID_POCO"].astype(str).str.strip()

    df["DATA_LEITURA"] = pd.to_datetime(
        df["DATA_LEITURA"],
        errors="coerce",
        dayfirst=True,
    )

    df["VAZAO"] = pd.to_numeric(
        df["VAZAO"],
        errors="coerce",
    )

    df["UNIDADE"] = df["UNIDADE"].astype(str).str.strip()

    return df


pocos = carregar_pocos()
leituras = carregar_leituras()


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

UNIDADES_VAZAO = [
    "L/s — Litros por segundo",
    "L/min — Litros por minuto",
    "L/h — Litros por hora",
    "m³/h — Metros cúbicos por hora",
    "m³/dia — Metros cúbicos por dia",
    "m³/s — Metros cúbicos por segundo",
]


def novo_id(prefixo, existentes):
    existentes = set(str(x) for x in existentes if str(x).strip())

    numero = 1

    while True:
        novo = f"{prefixo}{numero:05d}"

        if novo not in existentes:
            return novo

        numero += 1


def limpar_cache_dados():
    carregar_pocos.clear()
    carregar_leituras.clear()


def linha_por_id(df, coluna, valor):
    encontrados = df.index[df[coluna].astype(str) == str(valor)].tolist()

    if not encontrados:
        return None

    return encontrados[0]


def obter_ultima_leitura(
    poco_id,
    df_leituras,
    data_inicial=None,
    data_final=None,
):
    dados = df_leituras[
        df_leituras["ID_POCO"].astype(str) == str(poco_id)
    ].copy()

    dados = dados.dropna(subset=["DATA_LEITURA"])

    if data_inicial is not None:
        dados = dados[
            dados["DATA_LEITURA"].dt.date >= data_inicial
        ]

    if data_final is not None:
        dados = dados[
            dados["DATA_LEITURA"].dt.date <= data_final
        ]

    if dados.empty:
        return None

    dados = dados.sort_values(
        "DATA_LEITURA",
        ascending=False,
    )

    return dados.iloc[0]


def formatar_vazao(valor):
    if pd.isna(valor):
        return "—"

    return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def descricao_ultima_leitura(
    leitura,
    hoje=None,
):
    if leitura is None:
        return "Sem leitura registrada"

    data_leitura = leitura["DATA_LEITURA"]

    if pd.isna(data_leitura):
        return "Sem leitura registrada"

    if hoje is None:
        hoje = date.today()

    dias = (hoje - data_leitura.date()).days

    vazao = formatar_vazao(leitura["VAZAO"])
    unidade = leitura["UNIDADE"]

    return (
        f"Última vazão: {vazao} {unidade} | "
        f"Leitura: {data_leitura.strftime('%d/%m/%Y')} | "
        f"Há {max(dias, 0)} dias"
    )


# ============================================================
# DIÁLOGO — CADASTRAR POÇO
# ============================================================

@st.dialog("➕ Cadastrar Novo Poço")
def dialogo_novo_poco():

    st.subheader("Dados do poço")

    nome = st.text_input(
        "Nome / identificação do poço",
        key="novo_poco_nome",
    )

    municipio = st.text_input(
        "Município",
        key="novo_poco_municipio",
    )

    localizacao = st.text_input(
        "Localização",
        key="novo_poco_localizacao",
    )

    col1, col2 = st.columns(2)

    with col1:
        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=0.0,
            format="%.6f",
            key="novo_poco_latitude",
        )

    with col2:
        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=0.0,
            format="%.6f",
            key="novo_poco_longitude",
        )

    st.divider()

    if st.button(
        "💾 Salvar Poço",
        type="primary",
        use_container_width=True,
        key="salvar_novo_poco",
    ):
        if not nome.strip():
            st.error("Informe o nome ou identificação do poço.")
            return

        if latitude == 0 and longitude == 0:
            st.warning("Confira as coordenadas informadas.")

        novo_id_poco = novo_id(
            "POCO",
            pocos["ID_POCO"].tolist(),
        )

        aba_pocos.append_row(
            [
                novo_id_poco,
                nome.strip(),
                municipio.strip(),
                localizacao.strip(),
                latitude,
                longitude,
            ]
        )

        limpar_cache_dados()

        st.success("Poço cadastrado com sucesso.")
        st.rerun()


# ============================================================
# DIÁLOGO — EDITAR POÇO
# ============================================================

@st.dialog("✏️ Editar Poço")
def dialogo_editar_poco(poco_id):

    dados = carregar_pocos()

    idx = linha_por_id(
        dados,
        "ID_POCO",
        poco_id,
    )

    if idx is None:
        st.error("Poço não encontrado.")
        return

    poco = dados.loc[idx]

    st.caption(f"ID interno: {poco_id}")

    nome = st.text_input(
        "Nome / identificação",
        value=str(poco["NOME"]),
        key=f"editar_nome_{poco_id}",
    )

    municipio = st.text_input(
        "Município",
        value=str(poco["MUNICIPIO"]),
        key=f"editar_municipio_{poco_id}",
    )

    localizacao = st.text_input(
        "Localização",
        value=str(poco["LOCALIZACAO"]),
        key=f"editar_localizacao_{poco_id}",
    )

    col1, col2 = st.columns(2)

    with col1:
        latitude = st.number_input(
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
            value=float(poco["LATITUDE"]) if pd.notna(poco["LATITUDE"]) else 0.0,
            format="%.6f",
            key=f"editar_latitude_{poco_id}",
        )

    with col2:
        longitude = st.number_input(
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
            value=float(poco["LONGITUDE"]) if pd.notna(poco["LONGITUDE"]) else 0.0,
            format="%.6f",
            key=f"editar_longitude_{poco_id}",
        )

    if st.button(
        "💾 Salvar alterações",
        type="primary",
        use_container_width=True,
        key=f"salvar_edicao_poco_{poco_id}",
    ):
        linha_planilha = idx + 2

        aba_pocos.update(
            f"A{linha_planilha}:F{linha_planilha}",
            [[
                poco_id,
                nome.strip(),
                municipio.strip(),
                localizacao.strip(),
                latitude,
                longitude,
            ]],
        )

        limpar_cache_dados()

        st.success("Poço atualizado.")
        st.rerun()


# ============================================================
# DIÁLOGO — EXCLUIR POÇO
# ============================================================

@st.dialog("⚠️ Excluir Poço")
def dialogo_excluir_poco(poco_id):

    dados_pocos = carregar_pocos()
    dados_leituras = carregar_leituras()

    poco = dados_pocos[
        dados_pocos["ID_POCO"].astype(str) == str(poco_id)
    ]

    quantidade = len(
        dados_leituras[
            dados_leituras["ID_POCO"].astype(str) == str(poco_id)
        ]
    )

    nome = (
        poco.iloc[0]["NOME"]
        if not poco.empty
        else poco_id
    )

    st.warning(
        f"Você está tentando excluir o poço **{nome}**."
    )

    if quantidade > 0:
        st.error(
            f"Este poço possui {quantidade} leitura(s) vinculada(s)."
        )
        st.info(
            "A exclusão do cadastro não será realizada automaticamente. "
            "Confirme somente se esta exclusão foi intencional."
        )
    else:
        st.info(
            "Este poço não possui leituras vinculadas."
        )

    confirmar = st.checkbox(
        "Confirmo que desejo excluir este cadastro.",
        key=f"confirmar_exclusao_poco_{poco_id}",
    )

    if st.button(
        "🗑️ Confirmar exclusão",
        type="primary",
        disabled=not confirmar,
        use_container_width=True,
        key=f"confirmar_exclusao_poco_botao_{poco_id}",
    ):
        idx = linha_por_id(
            dados_pocos,
            "ID_POCO",
            poco_id,
        )

        if idx is None:
            st.error("Poço não encontrado.")
            return

        aba_pocos.delete_rows(idx + 2)

        limpar_cache_dados()

        st.success("Cadastro do poço excluído.")
        st.rerun()


# ============================================================
# DIÁLOGO — CADASTRAR LEITURA
# ============================================================

@st.dialog("➕ Registrar Leitura")
def dialogo_nova_leitura(poco_id=None):

    dados_pocos = carregar_pocos()

    if dados_pocos.empty:
        st.warning("Cadastre pelo menos um poço antes de registrar uma leitura.")
        return

    ids_pocos = dados_pocos["ID_POCO"].tolist()

    opcoes_pocos = {}

    for _, row in dados_pocos.iterrows():
        identificacao = (
            f"{row['NOME']} — "
            f"{row['MUNICIPIO']}"
            if row["MUNICIPIO"]
            else str(row["NOME"])
        )

        opcoes_pocos[
            identificacao
        ] = row["ID_POCO"]

    labels = list(opcoes_pocos.keys())

    indice_padrao = 0

    if poco_id in opcoes_pocos.values():
        indice_padrao = list(
            opcoes_pocos.values()
        ).index(poco_id)

    selecionado = st.selectbox(
        "Poço",
        labels,
        index=indice_padrao,
        key="nova_leitura_poco",
    )

    poco_escolhido = opcoes_pocos[selecionado]

    data_leitura = st.date_input(
        "Data da leitura",
        value=date.today(),
        key="nova_leitura_data",
    )

    vazao = st.number_input(
        "Vazão",
        min_value=0.0,
        value=0.0,
        format="%.3f",
        key="nova_leitura_vazao",
    )

    unidade = st.selectbox(
        "Unidade",
        UNIDADES_VAZAO,
        key="nova_leitura_unidade",
    )

    if st.button(
        "💾 Salvar leitura",
        type="primary",
        use_container_width=True,
        key="salvar_nova_leitura",
    ):
        if vazao < 0:
            st.error("A vazão não pode ser negativa.")
            return

        novo_id_leitura = novo_id(
            "LEIT",
            carregar_leituras()["ID_LEITURA"].tolist(),
        )

        aba_leituras.append_row(
            [
                novo_id_leitura,
                poco_escolhido,
                data_leitura.strftime("%d/%m/%Y"),
                vazao,
                unidade,
            ]
        )

        limpar_cache_dados()

        st.success("Leitura registrada.")
        st.rerun()


# ============================================================
# DIÁLOGO — EDITAR LEITURA
# ============================================================

@st.dialog("✏️ Editar Leitura")
def dialogo_editar_leitura(id_leitura):

    dados = carregar_leituras()

    idx = linha_por_id(
        dados,
        "ID_LEITURA",
        id_leitura,
    )

    if idx is None:
        st.error("Leitura não encontrada.")
        return

    leitura = dados.loc[idx]

    st.caption(f"ID da leitura: {id_leitura}")

    dados_pocos = carregar_pocos()

    mapa_pocos = {}

    for _, row in dados_pocos.iterrows():
        nome = str(row["NOME"]).strip()
        municipio = str(row["MUNICIPIO"]).strip()

        label = (
            f"{nome} — {municipio}"
            if municipio
            else nome
        )

        mapa_pocos[label] = row["ID_POCO"]

    valores_ids = list(mapa_pocos.values())

    try:
        indice_poco = valores_ids.index(
            str(leitura["ID_POCO"])
        )
    except ValueError:
        indice_poco = 0

    poco_label = st.selectbox(
        "Poço",
        list(mapa_pocos.keys()),
        index=indice_poco,
        key=f"editar_leitura_poco_{id_leitura}",
    )

    data_original = leitura["DATA_LEITURA"]

    if pd.isna(data_original):
        data_original = date.today()
    else:
        data_original = data_original.date()

    data_leitura = st.date_input(
        "Data da leitura",
        value=data_original,
        key=f"editar_leitura_data_{id_leitura}",
    )

    valor_original = (
        float(leitura["VAZAO"])
        if pd.notna(leitura["VAZAO"])
        else 0.0
    )

    vazao = st.number_input(
        "Vazão",
        min_value=0.0,
        value=valor_original,
        format="%.3f",
        key=f"editar_leitura_vazao_{id_leitura}",
    )

    unidade_original = str(leitura["UNIDADE"])

    if unidade_original not in UNIDADES_VAZAO:
        unidades = UNIDADES_VAZAO + [unidade_original]
    else:
        unidades = UNIDADES_VAZAO

    indice_unidade = (
        unidades.index(unidade_original)
        if unidade_original in unidades
        else 0
    )

    unidade = st.selectbox(
        "Unidade",
        unidades,
        index=indice_unidade,
        key=f"editar_leitura_unidade_{id_leitura}",
    )

    if st.button(
        "💾 Salvar alterações",
        type="primary",
        use_container_width=True,
        key=f"salvar_edicao_leitura_{id_leitura}",
    ):
        linha_planilha = idx + 2

        aba_leituras.update(
            f"A{linha_planilha}:E{linha_planilha}",
            [[
                id_leitura,
                mapa_pocos[poco_label],
                data_leitura.strftime("%d/%m/%Y"),
                vazao,
                unidade,
            ]],
        )

        limpar_cache_dados()

        st.success("Leitura atualizada.")
        st.rerun()


# ============================================================
# DIÁLOGO — EXCLUIR LEITURA
# ============================================================

@st.dialog("🗑️ Excluir Leitura")
def dialogo_excluir_leitura(id_leitura):

    dados = carregar_leituras()

    idx = linha_por_id(
        dados,
        "ID_LEITURA",
        id_leitura,
    )

    if idx is None:
        st.error("Leitura não encontrada.")
        return

    leitura = dados.loc[idx]

    st.warning(
        "Esta ação excluirá definitivamente a leitura selecionada."
    )

    st.write(
        f"**Data:** "
        f"{leitura['DATA_LEITURA'].strftime('%d/%m/%Y') if pd.notna(leitura['DATA_LEITURA']) else '—'}"
    )

    st.write(
        f"**Vazão:** "
        f"{formatar_vazao(leitura['VAZAO'])} "
        f"{leitura['UNIDADE']}"
    )

    confirmar = st.checkbox(
        "Confirmo a exclusão desta leitura.",
        key=f"confirmar_exclusao_leitura_{id_leitura}",
    )

    if st.button(
        "🗑️ Excluir leitura",
        type="primary",
        disabled=not confirmar,
        use_container_width=True,
        key=f"botao_excluir_leitura_{id_leitura}",
    ):
        aba_leituras.delete_rows(idx + 2)

        limpar_cache_dados()

        st.success("Leitura excluída.")
        st.rerun()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## ⚙️ Vazão de Poços")
    st.caption("Monitoramento e histórico de vazões")

    st.divider()

    st.markdown("### 📅 Período")

    hoje = date.today()

    data_inicial = st.date_input(
        "Data Inicial",
        value=hoje - timedelta(days=30),
        key="pocos_data_inicial",
    )

    data_final = st.date_input(
        "Data Final",
        value=hoje,
        key="pocos_data_final",
    )

    if data_inicial > data_final:
        st.error("A Data Inicial não pode ser maior que a Data Final.")

    st.divider()

    st.markdown("### 🔎 Filtros")

    municipios_disponiveis = sorted(
        [
            str(x).strip()
            for x in pocos["MUNICIPIO"].dropna().unique()
            if str(x).strip()
        ]
    )

    municipio_filtro = st.selectbox(
        "Município",
        ["Todos"] + municipios_disponiveis,
        key="pocos_filtro_municipio",
    )

    pocos_disponiveis = pocos.copy()

    if municipio_filtro != "Todos":
        pocos_disponiveis = pocos_disponiveis[
            pocos_disponiveis["MUNICIPIO"].astype(str)
            == municipio_filtro
        ]

    opcoes_pocos_filtro = ["Todos"]

    for _, row in pocos_disponiveis.iterrows():
        opcoes_pocos_filtro.append(
            f"{row['NOME']} [{row['ID_POCO']}]"
        )

    poco_filtro = st.selectbox(
        "Poço",
        opcoes_pocos_filtro,
        key="pocos_filtro_poco",
    )

    st.divider()

    st.markdown("### 🗺️ Mapa")

    mapa_tipo = st.selectbox(
        "Tipo de mapa",
        [
            "OpenStreetMap",
            "Esri World Imagery",
            "OpenTopoMap",
        ],
        key="mapa_tipo_pocos",
    )

    exibir_rotulos = st.checkbox(
        "Exibir rótulos",
        value=False,
        key="pocos_exibir_rotulos",
    )

    st.divider()

    st.markdown("### ➕ Ações")

    if st.button(
        "➕ Cadastrar Poço",
        use_container_width=True,
    ):
        dialogo_novo_poco()

    if st.button(
        "📏 Registrar Leitura",
        use_container_width=True,
    ):
        dialogo_nova_leitura()

    st.divider()

    modo_escuro = st.toggle(
        "🌙 Modo escuro",
        value=st.session_state.modo_escuro_pocos,
        key="toggle_modo_escuro_pocos",
    )

    if modo_escuro != st.session_state.modo_escuro_pocos:
        st.session_state.modo_escuro_pocos = modo_escuro
        st.rerun()

    st.divider()

    if st.button(
        "🏠 Voltar ao Menu Principal",
        use_container_width=True,
    ):
        st.switch_page("app.py")


# ============================================================
# VALIDAÇÃO DO PERÍODO
# ============================================================

if data_inicial > data_final:
    st.stop()


# ============================================================
# FILTRO DAS LEITURAS
# ============================================================

leituras_periodo = leituras.copy()

leituras_periodo = leituras_periodo.dropna(
    subset=["DATA_LEITURA"]
)

leituras_periodo = leituras_periodo[
    (
        leituras_periodo["DATA_LEITURA"].dt.date
        >= data_inicial
    )
    &
    (
        leituras_periodo["DATA_LEITURA"].dt.date
        <= data_final
    )
]


# Filtro de município
if municipio_filtro != "Todos":

    ids_municipio = set(
        pocos[
            pocos["MUNICIPIO"].astype(str)
            == municipio_filtro
        ]["ID_POCO"]
        .astype(str)
    )

    leituras_periodo = leituras_periodo[
        leituras_periodo["ID_POCO"].astype(str).isin(
            ids_municipio
        )
    ]


# Filtro de poço
if poco_filtro != "Todos":

    id_poco_filtro = poco_filtro.split("[")[-1].replace("]", "").strip()

    leituras_periodo = leituras_periodo[
        leituras_periodo["ID_POCO"].astype(str)
        == id_poco_filtro
    ]


# ============================================================
# TÍTULO
# ============================================================

st.title("⚙️ Vazão de Poços")

st.caption(
    f"Período analisado: "
    f"{data_inicial.strftime('%d/%m/%Y')} a "
    f"{data_final.strftime('%d/%m/%Y')}"
)


# ============================================================
# INDICADORES
# ============================================================

quantidade_pocos = len(pocos)

quantidade_leituras = len(leituras_periodo)

pocos_com_leitura = (
    leituras_periodo["ID_POCO"]
    .astype(str)
    .nunique()
    if not leituras_periodo.empty
    else 0
)

pocos_sem_leitura = max(
    quantidade_pocos - pocos_com_leitura,
    0,
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Poços cadastrados",
        quantidade_pocos,
    )

with col2:
    st.metric(
        "Leituras no período",
        quantidade_leituras,
    )

with col3:
    st.metric(
        "Poços com leitura",
        pocos_com_leitura,
    )

with col4:
    st.metric(
        "Poços sem leitura",
        pocos_sem_leitura,
    )


# ============================================================
# MAPA
# ============================================================

st.divider()

st.subheader("🗺️ Localização dos Poços")

pocos_mapa = pocos.copy()

if municipio_filtro != "Todos":
    pocos_mapa = pocos_mapa[
        pocos_mapa["MUNICIPIO"].astype(str)
        == municipio_filtro
    ]

if poco_filtro != "Todos":
    pocos_mapa = pocos_mapa[
        pocos_mapa["ID_POCO"].astype(str)
        == id_poco_filtro
    ]


coordenadas_validas = pocos.dropna(
    subset=["LATITUDE", "LONGITUDE"]
)

if coordenadas_validas.empty:

    centro_lat = -5.09
    centro_lon = -42.80
    zoom = 10

else:

    centro_lat = coordenadas_validas["LATITUDE"].mean()
    centro_lon = coordenadas_validas["LONGITUDE"].mean()
    zoom = 10


m = folium.Map(
    location=[centro_lat, centro_lon],
    zoom_start=zoom,
    control_scale=True,
    tiles=None,
)


if mapa_tipo == "OpenStreetMap":

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
    ).add_to(m)

elif mapa_tipo == "Esri World Imagery":

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Esri World Imagery",
    ).add_to(m)

else:

    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="OpenTopoMap",
        name="OpenTopoMap",
    ).add_to(m)


for _, poco in pocos_mapa.iterrows():

    latitude = poco["LATITUDE"]
    longitude = poco["LONGITUDE"]

    if pd.isna(latitude) or pd.isna(longitude):
        continue

    ultima = obter_ultima_leitura(
        poco["ID_POCO"],
        leituras,
        data_inicial,
        data_final,
    )

    if ultima is None:

        texto_leitura = "Sem leitura registrada no período."

    else:

        texto_leitura = descricao_ultima_leitura(
            ultima
        )

    popup_html = f"""
    <div style="min-width:260px;">
        <b>{poco['NOME']}</b><br>
        Município: {poco['MUNICIPIO']}<br>
        Localização: {poco['LOCALIZACAO']}<br>
        <hr>
        {texto_leitura}
    </div>
    """

    tooltip_text = (
        f"{poco['NOME']} — {texto_leitura}"
    )

    folium.Marker(
        location=[
            latitude,
            longitude,
        ],
        tooltip=tooltip_text,
        popup=folium.Popup(
            popup_html,
            max_width=350,
        ),
        icon=folium.Icon(
            icon="tint",
            prefix="fa",
        ),
    ).add_to(m)

    if exibir_rotulos:

        folium.Marker(
            location=[
                latitude,
                longitude,
            ],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    font-size: 12px;
                    font-weight: 600;
                    white-space: nowrap;
                    transform: translate(12px, -10px);
                ">
                    {poco['NOME']}
                </div>
                """
            ),
        ).add_to(m)


folium.LayerControl().add_to(m)


st_folium(
    m,
    width="100%",
    height=520,
)


# ============================================================
# CADASTRO DOS POÇOS
# ============================================================

st.divider()

st.subheader("📍 Cadastro dos Poços")

if pocos.empty:

    st.info("Nenhum poço cadastrado.")

else:

    tabela_pocos = pocos[
        [
            "ID_POCO",
            "NOME",
            "MUNICIPIO",
            "LOCALIZACAO",
            "LATITUDE",
            "LONGITUDE",
        ]
    ].copy()

    tabela_pocos.columns = [
        "ID",
        "Poço",
        "Município",
        "Localização",
        "Latitude",
        "Longitude",
    ]

    selecao_pocos = st.dataframe(
        tabela_pocos,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tabela_pocos",
    )

    linhas_selecionadas = (
        selecao_pocos.selection.rows
        if selecao_pocos
        else []
    )

    if linhas_selecionadas:

        indice = linhas_selecionadas[0]

        poco_selecionado = tabela_pocos.iloc[indice]["ID"]

        col_editar, col_excluir = st.columns(2)

        with col_editar:

            if st.button(
                "✏️ Editar Poço selecionado",
                use_container_width=True,
                key="editar_poco_selecionado",
            ):
                dialogo_editar_poco(
                    poco_selecionado
                )

        with col_excluir:

            if st.button(
                "🗑️ Excluir Poço selecionado",
                use_container_width=True,
                key="excluir_poco_selecionado",
            ):
                dialogo_excluir_poco(
                    poco_selecionado
                )


# ============================================================
# HISTÓRICO DE LEITURAS
# ============================================================

st.divider()

st.subheader("📋 Histórico de Leituras")

if leituras_periodo.empty:

    st.info(
        "Nenhuma leitura encontrada com os filtros selecionados."
    )

else:

    historico = leituras_periodo.merge(
        pocos[
            [
                "ID_POCO",
                "NOME",
                "MUNICIPIO",
            ]
        ],
        on="ID_POCO",
        how="left",
    )

    historico["DATA_LEITURA"] = historico[
        "DATA_LEITURA"
    ].dt.strftime("%d/%m/%Y")

    historico["VAZAO"] = historico[
        "VAZAO"
    ].map(formatar_vazao)

    historico = historico[
        [
            "ID_LEITURA",
            "ID_POCO",
            "NOME",
            "MUNICIPIO",
            "DATA_LEITURA",
            "VAZAO",
            "UNIDADE",
        ]
    ]

    historico.columns = [
        "ID Leitura",
        "ID Poço",
        "Poço",
        "Município",
        "Data da leitura",
        "Vazão",
        "Unidade",
    ]

    selecao_leituras = st.dataframe(
        historico,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tabela_historico_pocos",
    )

    linhas_leituras = (
        selecao_leituras.selection.rows
        if selecao_leituras
        else []
    )

    if linhas_leituras:

        indice = linhas_leituras[0]

        leitura_selecionada = historico.iloc[
            indice
        ]["ID Leitura"]

        col_editar, col_excluir = st.columns(2)

        with col_editar:

            if st.button(
                "✏️ Editar leitura selecionada",
                use_container_width=True,
                key="editar_leitura_selecionada",
            ):
                dialogo_editar_leitura(
                    leitura_selecionada
                )

        with col_excluir:

            if st.button(
                "🗑️ Excluir leitura selecionada",
                use_container_width=True,
                key="excluir_leitura_selecionada",
            ):
                dialogo_excluir_leitura(
                    leitura_selecionada
                )


# ============================================================
# GRÁFICO
# ============================================================

st.divider()

st.subheader("📈 Evolução da Vazão")

if pocos.empty:

    st.info("Cadastre um poço para visualizar a evolução.")

else:

    mapa_pocos_grafico = {}

    for _, row in pocos.iterrows():

        label = (
            f"{row['NOME']} — {row['MUNICIPIO']}"
            if row["MUNICIPIO"]
            else str(row["NOME"])
        )

        mapa_pocos_grafico[label] = row["ID_POCO"]

    labels_grafico = list(
        mapa_pocos_grafico.keys()
    )

    selecao_grafico = st.selectbox(
        "Selecione o poço",
        labels_grafico,
        key="selecao_grafico_pocos",
    )

    id_grafico = mapa_pocos_grafico[
        selecao_grafico
    ]

    dados_grafico = leituras[
        leituras["ID_POCO"].astype(str)
        == str(id_grafico)
    ].copy()

    dados_grafico = dados_grafico.dropna(
        subset=["DATA_LEITURA", "VAZAO"]
    )

    dados_grafico = dados_grafico[
        (
            dados_grafico["DATA_LEITURA"].dt.date
            >= data_inicial
        )
        &
        (
            dados_grafico["DATA_LEITURA"].dt.date
            <= data_final
        )
    ]

    dados_grafico = dados_grafico.sort_values(
        "DATA_LEITURA"
    )

    if dados_grafico.empty:

        st.info(
            "Não existem leituras desse poço no período selecionado."
        )

    else:

        fig = px.line(
            dados_grafico,
            x="DATA_LEITURA",
            y="VAZAO",
            markers=True,
            hover_data=[
                "UNIDADE",
            ],
            labels={
                "DATA_LEITURA": "Data da leitura",
                "VAZAO": "Vazão",
                "UNIDADE": "Unidade",
            },
            title=f"Evolução da vazão — {selecao_grafico}",
        )

        fig.update_layout(
            hovermode="x unified",
            xaxis_title="Data da leitura",
            yaxis_title="Vazão",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )
