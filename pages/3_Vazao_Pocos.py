import io
import hashlib
import re
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
    "IDENTIFICACAO_ATIVO",
    "DATA_LEITURA",
    "VAZAO",
    "UNIDADE",
    "PRESSAO",
    "OBS",
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

    cliente = obter_cliente_google()

    return cliente.open_by_key(
        SPREADSHEET_ID
    )


@st.cache_resource(show_spinner=False)
def obter_aba(nome_aba):

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

    return (
        obter_aba(NOME_ABA_POCOS),
        obter_aba(NOME_ABA_LEITURAS),
    )


# ============================================================
# CACHE DOS DADOS
# ============================================================

@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_pocos():

    aba_pocos, _ = obter_abas()

    valores = aba_pocos.get_all_values()

    if not valores:

        return pd.DataFrame(
            columns=CABECALHO_POCOS
        )

    cabecalho = [
        str(coluna).strip()
        for coluna in valores[0]
    ]

    registros = valores[1:]

    df = pd.DataFrame(
        registros,
        columns=cabecalho,
    )

    for coluna in CABECALHO_POCOS:

        if coluna not in df.columns:

            df[coluna] = ""

    return df[
        CABECALHO_POCOS
    ].copy()


@st.cache_data(
    ttl=120,
    show_spinner=False,
)
def carregar_leituras():

    _, aba_leituras = obter_abas()

    valores = aba_leituras.get_all_values()

    if not valores:

        return pd.DataFrame(
            columns=CABECALHO_LEITURAS
        )

    cabecalho = [
        str(coluna).strip()
        for coluna in valores[0]
    ]

    registros = valores[1:]

    df = pd.DataFrame(
        registros,
        columns=cabecalho,
    )

    for coluna in CABECALHO_LEITURAS:

        if coluna not in df.columns:

            df[coluna] = ""

    return df[
        CABECALHO_LEITURAS
    ].copy()


def invalidar_cache_dados():

    carregar_pocos.clear()
    carregar_leituras.clear()


# ============================================================
# GARANTIA DOS CABEÇALHOS
# ============================================================

def garantir_cabecalhos():

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


def normalizar_cabecalho(valor):

    texto = normalizar_texto(valor)

    texto = (
        texto
        .replace(" ", "")
        .replace(".", "")
        .replace("_", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "")
    )

    return texto


def parse_float(valor, default=None):

    if valor is None or (
        isinstance(valor, float)
        and pd.isna(valor)
    ):

        return default

    if isinstance(valor, (int, float)):

        try:

            numero = float(valor)

            if pd.isna(numero):
                return default

            return numero

        except (ValueError, TypeError):

            return default

    try:

        texto = str(valor).strip()

        if not texto or texto.lower() in (
            "nan",
            "none",
            "nat",
        ):

            return default

        texto = texto.replace(" ", "")

        # Trata formatos brasileiros como 1.234,56
        if "," in texto:

            texto = (
                texto
                .replace(".", "")
                .replace(",", ".")
            )

        else:

            texto = texto.replace(",", ".")

        numero = float(texto)

        if pd.isna(numero):
            return default

        return numero

    except (ValueError, TypeError):

        return default


def normalizar_coordenada(
    valor,
    tipo="lat",
):

    num = parse_float(
        valor,
        default=None,
    )

    if num is None:

        return None

    if tipo == "lat" and not (
        -90.0 <= num <= 90.0
    ):

        return None

    if tipo == "lon" and not (
        -180.0 <= num <= 180.0
    ):

        return None

    if num == 0.0:

        return None

    return round(
        float(num),
        6,
    )


def novo_id(prefixo, valores):

    maior = 0

    if valores is not None:

        for valor in valores:

            texto = str(valor).strip()

            if texto.startswith(prefixo):

                parte = texto[
                    len(prefixo):
                ]

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

    df["LATITUDE"] = df[
        "LATITUDE"
    ].apply(
        lambda x: normalizar_coordenada(
            x,
            "lat",
        )
    )

    df["LONGITUDE"] = df[
        "LONGITUDE"
    ].apply(
        lambda x: normalizar_coordenada(
            x,
            "lon",
        )
    )

    return df


def preparar_leituras(df):

    df = df.copy()

    if df.empty:

        return df

    for coluna in [
        "ID_LEITURA",
        "ID_POCO",
        "IDENTIFICACAO_ATIVO",
        "VAZAO",
        "UNIDADE",
        "PRESSAO",
        "OBS",
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
    identificacao_ativo,
    data_leitura,
    vazao,
    unidade,
    pressao="",
    obs="",
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
            identificacao_ativo,
            data_formatada,
            vazao,
            unidade,
            pressao,
            obs,
        ],
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()

    return id_leitura


def atualizar_leitura(
    linha_planilha,
    id_leitura,
    id_poco,
    identificacao_ativo,
    data_leitura,
    vazao,
    unidade,
    pressao="",
    obs="",
):

    _, aba_leituras = obter_abas()

    data_formatada = pd.to_datetime(
        data_leitura
    ).strftime(
        "%d/%m/%Y"
    )

    aba_leituras.update(
        f"A{linha_planilha}:H{linha_planilha}",
        [[
            id_leitura,
            id_poco,
            identificacao_ativo,
            data_formatada,
            vazao,
            unidade,
            pressao,
            obs,
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
# DUPLICIDADE DE LEITURA
# ============================================================

def chave_leitura(
    identificacao_ativo,
    data_leitura,
):

    ativo = normalizar_texto(
        identificacao_ativo
    )

    data_convertida = converter_data(
        data_leitura
    )

    if not ativo or pd.isna(data_convertida):

        return None

    return (
        ativo,
        data_convertida.strftime(
            "%Y-%m-%d"
        ),
    )


def obter_chaves_leituras_existentes(
    df_leituras,
):

    chaves = set()

    if df_leituras.empty:

        return chaves

    for _, linha in df_leituras.iterrows():

        chave = chave_leitura(
            linha.get(
                "IDENTIFICACAO_ATIVO",
                "",
            ),
            linha.get(
                "DATA_LEITURA",
                "",
            ),
        )

        if chave:

            chaves.add(chave)

    return chaves


# ============================================================
# PROCESSAMENTO DO UPLOAD DE LEITURAS
# ============================================================

def processar_upload_leituras(
    arquivo,
    df_pocos_atual,
    df_leituras_atual,
):

    try:

        conteudo = arquivo.getvalue()

        df_upload = pd.read_excel(
            io.BytesIO(conteudo)
        )

    except Exception as erro:

        return {
            "sucesso": False,
            "erro": (
                f"Não foi possível ler o arquivo: {erro}"
            ),
        }

    if df_upload.empty:

        return {
            "sucesso": False,
            "erro": "A planilha enviada está vazia.",
        }

    mapa_cabecalhos = {}

    for coluna in df_upload.columns:

        mapa_cabecalhos[
            normalizar_cabecalho(coluna)
        ] = coluna

    cabecalhos_obrigatorios = {
        "MUNICIPIOS": "Municípios",
        "CODINFRA": "Cod.Infra",
        "DATA": "Data",
        "VAZAOM3H": "Vazão (m³/h)",
    }

    faltantes = []

    for chave, nome in cabecalhos_obrigatorios.items():

        if chave not in mapa_cabecalhos:

            faltantes.append(nome)

    if faltantes:

        return {
            "sucesso": False,
            "erro": (
                "A planilha não possui os cabeçalhos obrigatórios: "
                + ", ".join(faltantes)
            ),
        }

    coluna_municipio = mapa_cabecalhos[
        "MUNICIPIOS"
    ]

    coluna_cod_infra = mapa_cabecalhos[
        "CODINFRA"
    ]

    coluna_data = mapa_cabecalhos[
        "DATA"
    ]

    coluna_vazao = mapa_cabecalhos[
        "VAZAOM3H"
    ]

    coluna_pressao = mapa_cabecalhos.get(
        "PRESSAO"
    )

    coluna_obs = mapa_cabecalhos.get(
        "OBS"
    )

    # --------------------------------------------------------
    # Mapa Cod.Infra -> ID_POCO
    # --------------------------------------------------------

    mapa_ativos = {}

    if not df_pocos_atual.empty:

        for _, poco in df_pocos_atual.iterrows():

            ativo = normalizar_texto(
                poco.get(
                    "IDENTIFICACAO_ATIVO",
                    "",
                )
            )

            if ativo:

                mapa_ativos[
                    ativo
                ] = str(
                    poco[
                        "ID_POCO"
                    ]
                )

    chaves_existentes = (
        obter_chaves_leituras_existentes(
            df_leituras_atual
        )
    )

    chaves_arquivo = set()

    registros = []

    duplicadas = []

    invalidas = []

    ativos_nao_cadastrados = []

    for numero_linha, (_, linha) in enumerate(
        df_upload.iterrows(),
        start=2,
    ):

        identificacao_ativo = str(
            linha.get(
                coluna_cod_infra,
                ""
            )
        ).strip()

        data_leitura = converter_data(
            linha.get(
                coluna_data
            )
        )

        vazao = parse_float(
            linha.get(
                coluna_vazao
            ),
            default=None,
        )

        # ----------------------------------------------------
        # Vazão é obrigatória para uma leitura válida.
        # Linhas sem vazão NÃO são importadas.
        # ----------------------------------------------------

        if vazao is None:
            invalidas.append(
                {
                    "Linha": numero_linha,
                    "Motivo": (
                        "Vazão não informada. "
                        "A linha não representa uma leitura válida."
                    ),
                    "Cod.Infra": identificacao_ativo,
                    "Data": (
                        data_leitura.strftime("%d/%m/%Y")
                        if pd.notna(data_leitura)
                        else str(
                            linha.get(
                                coluna_data,
                                ""
                            )
                        ).strip()
                    ),
                    "Vazão": "",
                }
            )
            continue

        if vazao < 0:
            invalidas.append(
                {
                    "Linha": numero_linha,
                    "Motivo": "Vazão negativa.",
                    "Cod.Infra": identificacao_ativo,
                    "Data": (
                        data_leitura.strftime("%d/%m/%Y")
                        if pd.notna(data_leitura)
                        else str(
                            linha.get(
                                coluna_data,
                                ""
                            )
                        ).strip()
                    ),
                    "Vazão": vazao,
                }
            )
            continue

        pressao = ""

        if coluna_pressao:

            valor_pressao = linha.get(
                coluna_pressao
            )

            if pd.notna(valor_pressao):

                pressao = str(
                    valor_pressao
                ).strip()

        obs = ""

        if coluna_obs:

            valor_obs = linha.get(
                coluna_obs
            )

            if pd.notna(valor_obs):

                obs = str(
                    valor_obs
                ).strip()

        ativo_normalizado = normalizar_texto(
            identificacao_ativo
        )

        # ----------------------------------------------------
        # Validações
        # ----------------------------------------------------

        if not ativo_normalizado:

            invalidas.append(
                {
                    "Linha": numero_linha,
                    "Motivo": (
                        "Cod.Infra não informado."
                    ),
                    "Cod.Infra": "",
                }
            )

            continue

        if pd.isna(data_leitura):

            invalidas.append(
                {
                    "Linha": numero_linha,
                    "Motivo": (
                        "Data inválida ou não informada."
                    ),
                    "Cod.Infra": identificacao_ativo,
                }
            )

            continue

        if ativo_normalizado not in mapa_ativos:

            ativos_nao_cadastrados.append(
                {
                    "Linha": numero_linha,
                    "Cod.Infra": identificacao_ativo,
                }
            )

            continue

        chave = chave_leitura(
            identificacao_ativo,
            data_leitura,
        )

        if chave in chaves_existentes:

            duplicadas.append(
                {
                    "Linha": numero_linha,
                    "Cod.Infra": identificacao_ativo,
                    "Data": data_leitura.strftime(
                        "%d/%m/%Y"
                    ),
                    "Motivo": (
                        "Leitura já existente no Sheets."
                    ),
                }
            )

            continue

        if chave in chaves_arquivo:

            duplicadas.append(
                {
                    "Linha": numero_linha,
                    "Cod.Infra": identificacao_ativo,
                    "Data": data_leitura.strftime(
                        "%d/%m/%Y"
                    ),
                    "Motivo": (
                        "Leitura duplicada no arquivo."
                    ),
                }
            )

            continue

        chaves_arquivo.add(chave)

        id_poco = mapa_ativos[
            ativo_normalizado
        ]

        registros.append(
            {
                "ID_POCO": id_poco,
                "IDENTIFICACAO_ATIVO": identificacao_ativo,
                "DATA_LEITURA": data_leitura.strftime(
                    "%d/%m/%Y"
                ),
                "VAZAO": (
                    str(vazao).replace(".", ",")
                ),
                "UNIDADE": (
                    "m³/h — Metros cúbicos por hora"
                ),
                "PRESSAO": pressao,
                "OBS": obs,
            }
        )

    return {
        "sucesso": True,
        "registros": registros,
        "duplicadas": duplicadas,
        "invalidas": invalidas,
        "ativos_nao_cadastrados": ativos_nao_cadastrados,
    }


def gravar_leituras_upload(
    registros,
):

    if not registros:

        return 0

    _, aba_leituras = obter_abas()

    df_atual = carregar_leituras()

    ids = (
        df_atual["ID_LEITURA"].tolist()
        if not df_atual.empty
        else []
    )

    proximo_numero = 0

    for valor in ids:

        texto = str(
            valor
        ).strip()

        if texto.startswith("LEIT"):

            try:

                numero = int(
                    texto[4:]
                )

                proximo_numero = max(
                    proximo_numero,
                    numero,
                )

            except ValueError:

                pass

    linhas = []

    for registro in registros:

        proximo_numero += 1

        id_leitura = (
            f"LEIT{proximo_numero:05d}"
        )

        linhas.append(
            [
                id_leitura,
                registro["ID_POCO"],
                registro[
                    "IDENTIFICACAO_ATIVO"
                ],
                registro[
                    "DATA_LEITURA"
                ],
                registro[
                    "VAZAO"
                ],
                registro[
                    "UNIDADE"
                ],
                registro[
                    "PRESSAO"
                ],
                registro[
                    "OBS"
                ],
            ]
        )

    aba_leituras.append_rows(
        linhas,
        value_input_option="USER_ENTERED",
    )

    invalidar_cache_dados()

    return len(linhas)


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
# TÍTULO
# ============================================================

st.title("Vazão de Poços")

st.caption(
    "Cadastro de poços, leituras de vazão, mapa e histórico."
)


# ============================================================
# SESSION STATE
# ============================================================

hoje = date.today()

if "poco_modal_aberto" not in st.session_state:

    st.session_state.poco_modal_aberto = False


# ============================================================
# DIALOG — CADASTRAR NOVO POÇO
# ============================================================

@st.dialog("➕ Cadastrar novo poço")
def modal_novo_poco():

    with st.form(
        "form_novo_poco_modal",
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
            "Município *",
        )

        c1, c2 = st.columns(2)

        with c1:

            latitude = st.text_input(
                "Latitude *",
                placeholder="-5.089200",
            )

        with c2:

            longitude = st.text_input(
                "Longitude *",
                placeholder="-42.801900",
            )

        salvar_poco = st.form_submit_button(
            "Cadastrar poço",
            type="primary",
            width="stretch",
        )

        if salvar_poco:

            lat_n = normalizar_coordenada(
                latitude,
                "lat",
            )

            lon_n = normalizar_coordenada(
                longitude,
                "lon",
            )

            if not identificacao.strip():

                st.error(
                    "A identificação do ativo é obrigatória."
                )

            elif not municipio.strip():

                st.error(
                    "O município é obrigatório."
                )

            elif lat_n is None:

                st.error(
                    "Latitude inválida. Informe um valor entre -90 e 90."
                )

            elif lon_n is None:

                st.error(
                    "Longitude inválida. Informe um valor entre -180 e 180."
                )

            else:

                try:

                    id_criado = adicionar_poco(
                        identificacao=identificacao.strip(),
                        nome=nome.strip(),
                        municipio=municipio.strip(),
                        latitude=lat_n,
                        longitude=lon_n,
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
# DIALOG — EDITAR / EXCLUIR POÇO
# ============================================================

@st.dialog("✏️ Editar ou excluir poço")
def modal_editar_poco():

    df_atual = preparar_pocos(
        carregar_pocos()
    )

    if df_atual.empty:

        st.info(
            "Nenhum poço cadastrado."
        )

        return

    opcoes_edicao = {
        identificacao_exibicao(row): row
        for _, row in df_atual.iterrows()
    }

    selecionado = st.selectbox(
        "Selecione o poço",
        list(opcoes_edicao.keys()),
        key="modal_poco_edicao",
    )

    poco_atual = opcoes_edicao[
        selecionado
    ]

    linha_df = df_atual.index[
        df_atual[
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
        "form_edicao_poco_modal"
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

        latitude_atual = normalizar_coordenada(
            poco_atual["LATITUDE"],
            "lat",
        )

        longitude_atual = normalizar_coordenada(
            poco_atual["LONGITUDE"],
            "lon",
        )

        c1, c2 = st.columns(2)

        with c1:

            latitude_edit = st.text_input(
                "Latitude *",
                value=(
                    str(latitude_atual)
                    if latitude_atual is not None
                    else ""
                ),
            )

        with c2:

            longitude_edit = st.text_input(
                "Longitude *",
                value=(
                    str(longitude_atual)
                    if longitude_atual is not None
                    else ""
                ),
            )

        salvar_edicao = st.form_submit_button(
            "💾 Salvar alterações",
            type="primary",
            width="stretch",
        )

        if salvar_edicao:

            lat_n = normalizar_coordenada(
                latitude_edit,
                "lat",
            )

            lon_n = normalizar_coordenada(
                longitude_edit,
                "lon",
            )

            if not identificacao_edit.strip():

                st.error(
                    "A identificação do ativo é obrigatória."
                )

            elif not municipio_edit.strip():

                st.error(
                    "O município é obrigatório."
                )

            elif lat_n is None:

                st.error(
                    "Latitude inválida. Informe um valor entre -90 e 90."
                )

            elif lon_n is None:

                st.error(
                    "Longitude inválida. Informe um valor entre -180 e 180."
                )

            elif linha_planilha is None:

                st.error(
                    "Não foi possível localizar a linha do poço."
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
                        latitude=lat_n,
                        longitude=lon_n,
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
        key="confirmar_exclusao_poco_modal",
    )

    if st.button(
        "🗑️ Excluir poço",
        type="secondary",
        width="stretch",
        key="btn_excluir_poco_modal",
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
# DIALOG — REGISTRAR NOVA LEITURA
# ============================================================

@st.dialog("📋 Registrar nova leitura")
def modal_nova_leitura():

    df_atual = preparar_pocos(
        carregar_pocos()
    )

    if df_atual.empty:

        st.info(
            "Cadastre pelo menos um poço para registrar leituras."
        )

        return

    opcoes_leitura = {
        identificacao_exibicao(row): row
        for _, row in df_atual.iterrows()
    }

    with st.form(
        "form_nova_leitura_modal",
        clear_on_submit=True,
    ):

        poco_leitura = st.selectbox(
            "Poço",
            list(
                opcoes_leitura.keys()
            ),
        )

        poco_selecionado = opcoes_leitura[
            poco_leitura
        ]

        data_leitura = st.date_input(
            "Data da leitura",
            value=date.today(),
            format="DD/MM/YYYY",
        )

        vazao = st.number_input(
            "Vazão",
            min_value=0.0,
            format="%.4f",
        )

        unidade = st.selectbox(
            "Unidade",
            UNIDADES_VAZAO,
        )

        pressao = st.text_input(
            "Pressão",
            placeholder="Opcional",
        )

        obs = st.text_area(
            "Observação",
            placeholder="Opcional",
        )

        salvar_leitura = st.form_submit_button(
            "Registrar leitura",
            type="primary",
            width="stretch",
        )

        if salvar_leitura:

            chave_nova = chave_leitura(
                poco_selecionado[
                    "IDENTIFICACAO_ATIVO"
                ],
                data_leitura,
            )

            chaves_existentes = (
                obter_chaves_leituras_existentes(
                    df_leituras
                )
            )

            if chave_nova in chaves_existentes:

                st.error(
                    "Já existe uma leitura para este ativo nesta data."
                )

            else:

                try:

                    id_leitura = adicionar_leitura(
                        id_poco=str(
                            poco_selecionado[
                                "ID_POCO"
                            ]
                        ),
                        identificacao_ativo=str(
                            poco_selecionado[
                                "IDENTIFICACAO_ATIVO"
                            ]
                        ).strip(),
                        data_leitura=data_leitura,
                        vazao=vazao,
                        unidade=unidade,
                        pressao=pressao.strip(),
                        obs=obs.strip(),
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
# DIALOG — EDITAR / EXCLUIR LEITURA
# ============================================================

@st.dialog("✏️ Editar ou excluir leitura")
def modal_editar_leitura():

    df_leituras_atual = preparar_leituras(
        carregar_leituras()
    )

    df_pocos_atual = preparar_pocos(
        carregar_pocos()
    )

    if df_leituras_atual.empty:

        st.info(
            "Nenhuma leitura registrada."
        )

        return

    historico_opcoes = {}

    for _, leitura in df_leituras_atual.iterrows():

        poco = df_pocos_atual[
            df_pocos_atual[
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
        key="leitura_edicao_modal",
    )

    leitura_atual = historico_opcoes[
        leitura_selecionada
    ]

    linha_df = df_leituras_atual.index[
        df_leituras_atual[
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

    opcoes_pocos_edicao = {}

    for _, poco in df_pocos_atual.iterrows():

        opcoes_pocos_edicao[
            identificacao_exibicao(poco)
        ] = poco[
            "ID_POCO"
        ]

    poco_da_leitura = str(
        leitura_atual[
            "ID_POCO"
        ]
    )

    nome_poco_atual = None

    for nome, id_poco in opcoes_pocos_edicao.items():

        if str(id_poco) == poco_da_leitura:

            nome_poco_atual = nome

            break

    if nome_poco_atual is None:

        if opcoes_pocos_edicao:

            nome_poco_atual = list(
                opcoes_pocos_edicao.keys()
            )[0]

    data_atual = converter_data(
        leitura_atual[
            "DATA_LEITURA"
        ]
    )

    if pd.isna(data_atual):

        data_atual = date.today()

    else:

        data_atual = data_atual.date()

    identificacao_atual = str(
        leitura_atual.get(
            "IDENTIFICACAO_ATIVO",
            "",
        )
    )

    with st.form(
        "form_edicao_leitura_modal"
    ):

        poco_editado = st.selectbox(
            "Poço",
            list(
                opcoes_pocos_edicao.keys()
            ),
            index=(
                list(
                    opcoes_pocos_edicao.keys()
                ).index(
                    nome_poco_atual
                )
                if nome_poco_atual
                else 0
            ),
        )

        data_editada = st.date_input(
            "Data da leitura",
            value=data_atual,
            format="DD/MM/YYYY",
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

            unidade_atual = str(
                leitura_atual[
                    "UNIDADE"
                ]
            )

            unidade_editada = st.selectbox(
                "Unidade",
                UNIDADES_VAZAO,
                index=(
                    UNIDADES_VAZAO.index(
                        unidade_atual
                    )
                    if unidade_atual in UNIDADES_VAZAO
                    else 0
                ),
            )

        pressao_editada = st.text_input(
            "Pressão",
            value=str(
                leitura_atual.get(
                    "PRESSAO",
                    "",
                )
            ),
        )

        obs_editada = st.text_area(
            "Observação",
            value=str(
                leitura_atual.get(
                    "OBS",
                    "",
                )
            ),
        )

        salvar_leitura_editada = st.form_submit_button(
            "💾 Salvar alterações",
            type="primary",
            width="stretch",
        )

        if salvar_leitura_editada:

            poco_novo = df_pocos_atual[
                df_pocos_atual[
                    "ID_POCO"
                ].astype(str)
                == str(
                    opcoes_pocos_edicao[
                        poco_editado
                    ]
                )
            ]

            if poco_novo.empty:

                st.error(
                    "Poço selecionado não encontrado."
                )

            elif linha_leitura_planilha is None:

                st.error(
                    "Não foi possível localizar a leitura."
                )

            else:

                identificacao_nova = str(
                    poco_novo.iloc[0][
                        "IDENTIFICACAO_ATIVO"
                    ]
                ).strip()

                chave_nova = chave_leitura(
                    identificacao_nova,
                    data_editada,
                )

                chaves_existentes = (
                    obter_chaves_leituras_existentes(
                        df_leituras_atual
                    )
                )

                chave_atual = chave_leitura(
                    identificacao_atual,
                    leitura_atual[
                        "DATA_LEITURA"
                    ],
                )

                chaves_outros_registros = (
                    chaves_existentes
                    - {chave_atual}
                )

                if (
                    chave_nova
                    in chaves_outros_registros
                ):

                    st.error(
                        "Já existe outra leitura para este ativo nesta data."
                    )

                else:

                    try:

                        atualizar_leitura(
                            linha_planilha=linha_leitura_planilha,
                            id_leitura=str(
                                leitura_atual[
                                    "ID_LEITURA"
                                ]
                            ),
                            id_poco=str(
                                poco_novo.iloc[0][
                                    "ID_POCO"
                                ]
                            ),
                            identificacao_ativo=identificacao_nova,
                            data_leitura=data_editada,
                            vazao=vazao_editada,
                            unidade=unidade_editada,
                            pressao=pressao_editada.strip(),
                            obs=obs_editada.strip(),
                        )

                        st.success(
                            "Leitura atualizada com sucesso."
                        )

                        st.rerun()

                    except Exception as erro:

                        st.error(
                            f"Erro ao atualizar leitura: {erro}"
                        )

    st.divider()

    confirmar_exclusao_leitura = st.checkbox(
        "Confirmo que desejo excluir esta leitura.",
        key="confirmar_exclusao_leitura_modal",
    )

    if st.button(
        "🗑️ Excluir leitura",
        type="secondary",
        width="stretch",
        key="btn_excluir_leitura_modal",
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
# DIALOG — IMPORTAR LEITURAS
# ============================================================

@st.dialog("📥 Importar leituras")
def modal_importar_leituras():

    st.write(
        "Envie uma planilha Excel contendo as colunas de medição."
    )

    st.caption(
        "Colunas esperadas: Municípios, Descrição do ativo, "
        "Cod.Infra, Data, Vazão (m³/h), Pressão e Obs. "
        "Linhas sem vazão não serão importadas."
    )

    arquivo = st.file_uploader(
        "Planilha de leituras",
        type=[
            "xlsx",
            "xlsm",
        ],
        key="upload_leituras",
    )

    if arquivo is None:

        return

    resultado = processar_upload_leituras(
        arquivo=arquivo,
        df_pocos_atual=df_pocos,
        df_leituras_atual=df_leituras,
    )

    if not resultado["sucesso"]:

        st.error(
            resultado["erro"]
        )

        return

    registros = resultado[
        "registros"
    ]

    duplicadas = resultado[
        "duplicadas"
    ]

    invalidas = resultado[
        "invalidas"
    ]

    ativos_nao_cadastrados = resultado[
        "ativos_nao_cadastrados"
    ]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Novas leituras",
        len(registros),
    )

    col2.metric(
        "Duplicadas",
        len(duplicadas),
    )

    col3.metric(
        "Inválidas",
        len(invalidas),
    )

    col4.metric(
        "Ativos não cadastrados",
        len(ativos_nao_cadastrados),
    )

    if ativos_nao_cadastrados:

        st.warning(
            "Existem registros cujo Cod.Infra não "
            "foi encontrado no cadastro de poços."
        )

        st.dataframe(
            pd.DataFrame(
                ativos_nao_cadastrados
            ),
            width="stretch",
            hide_index=True,
        )

    if invalidas:

        st.warning(
            "Existem registros com dados inválidos."
        )

        st.dataframe(
            pd.DataFrame(
                invalidas
            ),
            width="stretch",
            hide_index=True,
        )

    if duplicadas:

        st.info(
            "As duplicidades não serão importadas."
        )

        st.dataframe(
            pd.DataFrame(
                duplicadas
            ),
            width="stretch",
            hide_index=True,
        )

    if registros:

        st.success(
            f"{len(registros)} nova(s) leitura(s) pronta(s) para importação."
        )

        st.subheader("Leituras válidas")

        st.dataframe(
            pd.DataFrame(registros)[
                [
                    "IDENTIFICACAO_ATIVO",
                    "DATA_LEITURA",
                    "VAZAO",
                    "UNIDADE",
                    "PRESSAO",
                    "OBS",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        confirmar = st.checkbox(
            "Confirmo a importação das novas leituras.",
            key="confirmar_importacao_leituras",
        )

        if st.button(
            "💾 Importar leituras",
            type="primary",
            width="stretch",
            key="btn_confirmar_importacao_leituras",
        ):

            if not confirmar:

                st.warning(
                    "Marque a confirmação antes de importar."
                )

            else:

                try:

                    quantidade = (
                        gravar_leituras_upload(
                            registros
                        )
                    )

                    st.success(
                        f"{quantidade} leitura(s) importada(s) com sucesso."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao importar leituras: {erro}"
                    )

    else:

        st.info(
            "Nenhuma nova leitura para importar."
        )


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Filtros")

data_inicio_padrao = hoje - timedelta(
    days=30
)

periodo = st.sidebar.date_input(
    "Período das leituras",
    value=(
        data_inicio_padrao,
        hoje,
    ),
    format="DD/MM/YYYY",
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
# AÇÕES — POPUPS
# ============================================================

st.sidebar.divider()

st.sidebar.markdown(
    "### ⚙️ Ações"
)

if st.sidebar.button(
    "➕ Cadastrar novo poço",
    type="primary",
    width="stretch",
):

    modal_novo_poco()


if st.sidebar.button(
    "✏️ Editar ou excluir poço",
    width="stretch",
):

    modal_editar_poco()


if st.sidebar.button(
    "📋 Registrar nova leitura",
    width="stretch",
):

    modal_nova_leitura()


if st.sidebar.button(
    "📥 Importar leituras",
    width="stretch",
):

    modal_importar_leituras()


if st.sidebar.button(
    "📝 Editar ou excluir leitura",
    width="stretch",
):

    modal_editar_leitura()


st.sidebar.divider()

if st.sidebar.button(
    "🏠 Voltar ao Menu Principal",
    width="stretch",
):

    st.switch_page("app.py")


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

pocos_filtro = df_pocos.copy()

if municipio_filtro != "Todos":

    pocos_filtro = pocos_filtro[
        pocos_filtro[
            "MUNICIPIO"
        ].astype(str).str.strip()
        == municipio_filtro
    ]

if poco_filtro != "Todos":

    pocos_filtro = pocos_filtro[
        pocos_filtro.apply(
            identificacao_exibicao,
            axis=1,
        )
        == poco_filtro
    ]


# ============================================================
# POÇOS EXIBIDOS NO MAPA
# ============================================================

if municipio_filtro != "Todos":

    pocos_mapa = pocos_filtro.copy()

else:

    pocos_mapa = pd.DataFrame(
        columns=df_pocos.columns
    )


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
    len(pocos_filtro),
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

if municipio_filtro != "Todos":

    coordenadas = pocos_mapa.copy()

    coordenadas["LATITUDE"] = coordenadas[
        "LATITUDE"
    ].apply(
        lambda x: normalizar_coordenada(
            x,
            "lat",
        )
    )

    coordenadas["LONGITUDE"] = coordenadas[
        "LONGITUDE"
    ].apply(
        lambda x: normalizar_coordenada(
            x,
            "lon",
        )
    )

    coordenadas = coordenadas.dropna(
        subset=[
            "LATITUDE",
            "LONGITUDE",
        ]
    ).copy()

else:

    coordenadas = pd.DataFrame(
        columns=pocos_mapa.columns
    )


# ============================================================
# CENTRO DO MAPA
# ============================================================

if not coordenadas.empty:

    centro_lat = float(
        coordenadas[
            "LATITUDE"
        ].mean()
    )

    centro_lon = float(
        coordenadas[
            "LONGITUDE"
        ].mean()
    )

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

if municipio_filtro != "Todos":

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
                float(
                    poco["LATITUDE"]
                ),
                float(
                    poco["LONGITUDE"]
                ),
            ],
            tooltip=nome_exibicao,
            popup=folium.Popup(
                popup_html,
                max_width=350,
            ),
        ).add_to(mapa)


# ============================================================
# AJUSTE AUTOMÁTICO DO ENQUADRAMENTO
# ============================================================

if (
    municipio_filtro != "Todos"
    and not coordenadas.empty
):

    mapa.fit_bounds(
        [
            [
                coordenadas[
                    "LATITUDE"
                ].min(),
                coordenadas[
                    "LONGITUDE"
                ].min(),
            ],
            [
                coordenadas[
                    "LATITUDE"
                ].max(),
                coordenadas[
                    "LONGITUDE"
                ].max(),
            ],
        ],
        padding=(30, 30),
    )


# ============================================================
# EXIBIÇÃO DO MAPA
# ============================================================

st_folium(
    mapa,
    width=None,
    height=600,
)


# ============================================================
# AVISO DE COORDENADAS INVÁLIDAS
# ============================================================

if (
    municipio_filtro != "Todos"
    and not pocos_mapa.empty
    and coordenadas.empty
):

    st.warning(
        "Os poços selecionados não possuem "
        "coordenadas válidas para exibição no mapa. "
        "Verifique Latitude e Longitude no cadastro."
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
        suffixes=("", "_POCO"),
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
        "PRESSAO",
        "OBS",
    ]

    colunas_historico = [
        coluna
        for coluna in colunas_historico
        if coluna in historico.columns
    ]

    st.dataframe(
        historico[
            colunas_historico
        ],
        width="stretch",
        hide_index=True,
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
        list(opcoes_grafico.keys()),
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
            width="stretch",
        )


# ============================================================
# INFORMAÇÃO SOBRE CACHE
# ============================================================

st.caption(
    "Dados sincronizados com Google Sheets. "
    "As leituras são mantidas em cache por até 120 segundos "
    "e o cache é atualizado imediatamente após alterações."
)
