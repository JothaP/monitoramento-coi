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
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        [data-testid="stSidebar"] div.block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# TRAVA DE SEGURANÇA E CONTROLE DE SESSÃO DO HUB
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

SPREADSHEET_ID = (
    "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"
)

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


# ============================================================
# CLASSIFICAÇÃO E PALETA DE CORES DA PRESSÃO
# ============================================================
COR_SEM_PRESSAO = "#FF5C60"
COR_BAIXA_PRESSAO = "#F8DC00"
COR_EM_ATENCAO = "#FF8FE1"
COR_ALTA_PRESSAO = "#A11FFF"


def classificar_pressao(pressao):

    try:

        valor = float(pressao)

    except (TypeError, ValueError):

        valor = 0.0

    if valor == 0:

        return "Sem Pressão", COR_SEM_PRESSAO

    elif valor <= 5:

        return "Baixa Pressão", COR_BAIXA_PRESSAO

    elif valor <= 15:

        return "Em Atenção", COR_EM_ATENCAO

    else:

        return "Alta Pressão", COR_ALTA_PRESSAO


# ============================================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================================
@st.cache_resource
def conectar_google_sheets():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials_dict = json.loads(
        st.secrets["gcp_json"]
    )

    credentials = Credentials.from_service_account_info(
        credentials_dict,
        scopes=scopes
    )

    gc = gspread.authorize(credentials)

    sh = gc.open_by_key(
        SPREADSHEET_ID
    )

    try:

        ws = sh.worksheet(
            "baixa_pressao"
        )

    except Exception:

        try:

            ws = sh.add_worksheet(
                title="baixa_pressao",
                rows="1000",
                cols="20"
            )

        except Exception:

            ws = sh.sheet1

    try:

        dados_iniciais = ws.get_all_values()

        if not dados_iniciais or len(dados_iniciais) == 0:

            ws.append_row([
                "ID",
                "Data",
                "Municipio",
                "Bairro",
                "Latitude",
                "Longitude",
                "Pressao_MCA",
                "Observacao",
                "Matricula"
            ])

        else:

            cabecalho_atual = [
                str(c).strip()
                for c in dados_iniciais[0]
            ]

            # Garante a coluna Observacao
            if (
                len(cabecalho_atual) >= 7
                and "Observacao" not in cabecalho_atual
                and "Observação" not in cabecalho_atual
            ):

                ws.update(
                    "H1",
                    [["Observacao"]]
                )

            # Garante a coluna Matricula na coluna I.
            # Compatibilidade com instalações antigas
            # que ainda possuem somente 8 colunas.
            if (
                "Matricula" not in cabecalho_atual
                and "Matrícula" not in cabecalho_atual
            ):

                ws.update(
                    "I1",
                    [["Matricula"]]
                )

    except Exception:

        pass

    return ws


try:

    worksheet = conectar_google_sheets()

except Exception as e:

    st.error(
        f"❌ Erro ao conectar com o Google Sheets: {e}"
    )

    st.stop()


# ============================================================
# FUNÇÕES DE DADOS E EXPORTAÇÃO
# ============================================================
def gerar_id() -> str:

    return str(
        uuid.uuid4()
    )[:8].upper()


def normalizar_coluna(nome: str) -> str:

    nome = str(
        nome
    ).strip().lower()

    mapeamento = {

        "id": "ID",

        "data": "Data",

        "municipio": "Municipio",
        "município": "Municipio",

        "bairro": "Bairro",

        "latitude": "Latitude",
        "lat": "Latitude",

        "longitude": "Longitude",
        "lon": "Longitude",
        "long": "Longitude",

        "pressao_mca": "Pressao_MCA",
        "pressão_mca": "Pressao_MCA",
        "pressao": "Pressao_MCA",
        "pressão": "Pressao_MCA",
        "mca": "Pressao_MCA",

        "observacao": "Observacao",
        "observação": "Observacao",
        "obs": "Observacao",

        "matricula": "Matricula",
        "matrícula": "Matricula",
        "matrícula ": "Matricula",
        "mat": "Matricula"
    }

    return mapeamento.get(
        nome,
        nome.title()
    )


def normalizar_texto_local(
    valor,
    padrao=""
) -> str:

    if valor is None:

        return padrao

    texto = str(
        valor
    ).strip()

    if not texto or texto.lower() in (
        "nan",
        "none",
        "nat"
    ):

        return padrao

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return texto.upper().strip()


def parse_float(
    valor,
    default=None
):

    if valor is None or (
        isinstance(valor, float)
        and pd.isna(valor)
    ):

        return default

    if isinstance(
        valor,
        (int, float)
    ):

        return float(valor)

    try:

        texto = str(
            valor
        ).strip()

        if not texto or texto.lower() in (
            "nan",
            "none",
            "nat",
            ""
        ):

            return default

        texto = (
            texto
            .replace(",", ".")
            .replace(" ", "")
        )

        return float(texto)

    except (
        ValueError,
        TypeError
    ):

        return default


def normalizar_coordenada(
    valor,
    tipo: str = "lat"
) -> Optional[float]:

    num = parse_float(
        valor,
        default=None
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
        6
    )


def normalizar_data(valor) -> str:

    if valor is None or (
        isinstance(valor, float)
        and pd.isna(valor)
    ):

        return ""

    if isinstance(
        valor,
        (datetime, date)
    ):

        return valor.strftime(
            "%d/%m/%Y"
        )

    texto = str(
        valor
    ).strip()

    if not texto or texto.lower() in (
        "nan",
        "none",
        "nat",
        ""
    ):

        return ""

    formatos = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d"
    ]

    for fmt in formatos:

        try:

            return datetime.strptime(
                texto,
                fmt
            ).strftime(
                "%d/%m/%Y"
            )

        except ValueError:

            continue

    return texto


def carregar_dados() -> pd.DataFrame:

    try:

        valores = worksheet.get_all_values()

    except Exception as e:

        st.error(
            f"Erro ao ler planilha: {e}"
        )

        return pd.DataFrame(
            columns=COLUNAS_PADRAO
        )

    if not valores or len(valores) < 2:

        return pd.DataFrame(
            columns=COLUNAS_PADRAO
        )

    cabecalhos_raw = valores[0]

    cabecalhos = [
        normalizar_coluna(c)
        for c in cabecalhos_raw
    ]

    registros = []

    for linha in valores[1:]:

        if not any(
            str(c).strip()
            for c in linha
        ):

            continue

        reg = {}

        for i, col in enumerate(
            cabecalhos
        ):

            reg[col] = (
                linha[i]
                if i < len(linha)
                else ""
            )

        registros.append(reg)

    if not registros:

        return pd.DataFrame(
            columns=COLUNAS_PADRAO
        )

    df = pd.DataFrame(
        registros
    )

    for col in COLUNAS_PADRAO:

        if col not in df.columns:

            df[col] = ""

    def limpar_id(v):

        s = str(v).strip()

        if not s or s.lower() in (
            "nan",
            "none",
            ""
        ):

            return gerar_id()

        return s

    df["ID"] = df["ID"].apply(
        limpar_id
    )

    df["Data"] = df["Data"].apply(
        normalizar_data
    )

    # ========================================================
    # NORMALIZAÇÃO DE MUNICÍPIO
    # ========================================================
    df["Municipio"] = df["Municipio"].apply(
        lambda x:
        normalizar_texto_local(
            x,
            padrao="TERESINA"
        )
    )

    # ========================================================
    # NORMALIZAÇÃO DE BAIRRO
    # ========================================================
    df["Bairro"] = df["Bairro"].apply(
        lambda x:
        normalizar_texto_local(
            x,
            padrao=""
        )
    )

    df["Latitude"] = df[
        "Latitude"
    ].apply(
        lambda x:
        normalizar_coordenada(
            x,
            "lat"
        )
    )

    df["Longitude"] = df[
        "Longitude"
    ].apply(
        lambda x:
        normalizar_coordenada(
            x,
            "lon"
        )
    )

    df["Pressao_MCA"] = df[
        "Pressao_MCA"
    ].apply(
        lambda x:
        parse_float(
            x,
            0.0
        ) or 0.0
    )

    df["Observacao"] = (
        df["Observacao"]
        .astype(str)
        .str.strip()
        .replace({
            "nan": "",
            "None": ""
        })
    )

    # ========================================================
    # MATRÍCULA
    # ========================================================
    df["Matricula"] = (
        df["Matricula"]
        .astype(str)
        .str.strip()
        .replace({
            "nan": "",
            "None": ""
        })
    )

    df = df[
        df["Bairro"]
        .astype(str)
        .str.strip()
        != ""
    ]

    return df[
        COLUNAS_PADRAO
    ].reset_index(
        drop=True
    )


def limpar_cache():

    st.cache_data.clear()


def adicionar_ponto(
    municipio: str,
    matricula: str,
    bairro: str,
    lat: float,
    lon: float,
    pressao: float,
    data_str: str,
    observacao: str
):

    novo_id = gerar_id()

    municipio_normalizado = normalizar_texto_local(
        municipio,
        padrao="TERESINA"
    )

    bairro_normalizado = normalizar_texto_local(
        bairro,
        padrao=""
    )

    matricula_normalizada = str(
        matricula or ""
    ).strip()

    worksheet.append_row([
        str(novo_id),
        str(data_str),
        municipio_normalizado,
        bairro_normalizado,
        float(lat),
        float(lon),
        float(pressao),
        str(observacao),
        matricula_normalizada
    ])

    time.sleep(0.3)

    limpar_cache()

    return novo_id


def adicionar_lote_seguro(
    linhas_dados: list
):

    if not linhas_dados:

        return 0

    df_atual = carregar_dados()

    chaves_existentes = set()

    if not df_atual.empty:

        for _, r in df_atual.iterrows():

            lat_f = (
                f"{float(r['Latitude']):.6f}"
                if pd.notnull(
                    r["Latitude"]
                )
                else ""
            )

            lon_f = (
                f"{float(r['Longitude']):.6f}"
                if pd.notnull(
                    r["Longitude"]
                )
                else ""
            )

            # Matrícula permanece fora da chave
            # de duplicidade.
            chave = (
                str(r["Data"]).strip(),
                str(
                    r["Municipio"]
                ).strip().lower(),
                str(
                    r["Bairro"]
                ).strip().lower(),
                lat_f,
                lon_f
            )

            chaves_existentes.add(
                chave
            )

    linhas_novas = []

    for linha in linhas_dados:

        (
            id_v,
            d_val,
            mun_val,
            bair_val,
            lat_val,
            lon_val,
            pres_val,
            obs_val,
            mat_val
        ) = linha

        lat_f = (
            f"{float(lat_val):.6f}"
        )

        lon_f = (
            f"{float(lon_val):.6f}"
        )

        chave_nova = (
            str(d_val).strip(),
            str(
                mun_val
            ).strip().lower(),
            str(
                bair_val
            ).strip().lower(),
            lat_f,
            lon_f
        )

        if chave_nova not in chaves_existentes:

            linhas_novas.append(
                linha
            )

            chaves_existentes.add(
                chave_nova
            )

    if linhas_novas:

        dados_formatados = [

            [
                str(i),
                str(d),
                normalizar_texto_local(
                    mun,
                    padrao="TERESINA"
                ),
                normalizar_texto_local(
                    b,
                    padrao=""
                ),
                float(lat),
                float(lon),
                float(p),
                str(o),
                str(mat).strip()
            ]

            for (
                i,
                d,
                mun,
                b,
                lat,
                lon,
                p,
                o,
                mat
            ) in linhas_novas
        ]

        worksheet.append_rows(
            dados_formatados,
            value_input_option="USER_ENTERED"
        )

        time.sleep(0.3)

        limpar_cache()

        return len(
            linhas_novas
        )

    return 0


def atualizar_ponto(
    id_registro: str,
    municipio: str,
    matricula: str,
    bairro: str,
    lat: float,
    lon: float,
    pressao: float,
    data_str: str,
    observacao: str
) -> bool:

    try:

        celula = worksheet.find(
            str(id_registro)
        )

        if celula is None:

            return False

        linha = celula.row

        worksheet.update(
            f"A{linha}:I{linha}",
            [[
                str(id_registro),
                str(data_str),
                normalizar_texto_local(
                    municipio,
                    padrao="TERESINA"
                ),
                normalizar_texto_local(
                    bairro,
                    padrao=""
                ),
                float(lat),
                float(lon),
                float(pressao),
                str(observacao),
                str(matricula).strip()
            ]]
        )

        time.sleep(0.3)

        limpar_cache()

        return True

    except Exception as e:

        st.error(
            f"Erro ao atualizar: {e}"
        )

        return False


def excluir_ponto(
    id_registro: str
) -> bool:

    try:

        celula = worksheet.find(
            str(id_registro)
        )

        if celula is None:

            return False

        worksheet.delete_rows(
            celula.row
        )

        time.sleep(0.3)

        limpar_cache()

        return True

    except Exception:

        return False


def data_para_str(
    d: date
) -> str:

    return d.strftime(
        "%d/%m/%Y"
    )


def gerar_kml(df):

    kml = simplekml.Kml()

    for _, row in df.iterrows():

        lat = row.get(
            "Latitude"
        )

        lon = row.get(
            "Longitude"
        )

        if pd.notnull(lat) and pd.notnull(lon):

            try:

                obs_text = (
                    f"\nObservação: "
                    f"{row.get('Observacao', '')}"
                    if str(
                        row.get(
                            "Observacao",
                            ""
                        )
                    ).strip()
                    else ""
                )

                matricula_text = (
                    f"\nMatrícula: "
                    f"{row.get('Matricula', '')}"
                    if str(
                        row.get(
                            "Matricula",
                            ""
                        )
                    ).strip()
                    else ""
                )

                kml.newpoint(
                    name=str(
                        row.get(
                            "ID",
                            "Ponto"
                        )
                    ),
                    description=(
                        f"Município: "
                        f"{row.get('Municipio', '')}\n"
                        f"Bairro: "
                        f"{row.get('Bairro', '')}\n"
                        f"Matrícula: "
                        f"{row.get('Matricula', '')}\n"
                        f"Pressão: "
                        f"{row.get('Pressao_MCA', '')} MCA"
                        f"{obs_text}"
                    ),
                    coords=[
                        (
                            float(lon),
                            float(lat)
                        )
                    ]
                )

            except (
                ValueError,
                TypeError
            ):

                continue

    return kml.kml()


# ============================================================
# SESSION STATE
# ============================================================
hoje = date.today()

if "data_inicial_selecionada" not in st.session_state:

    st.session_state.data_inicial_selecionada = hoje

if "data_final_selecionada" not in st.session_state:

    st.session_state.data_final_selecionada = hoje

if "clicked_lat" not in st.session_state:

    st.session_state.clicked_lat = None

if "clicked_lon" not in st.session_state:

    st.session_state.clicked_lon = None

if "modo_adicionar_mapa" not in st.session_state:

    st.session_state.modo_adicionar_mapa = False

if "dados_upload_pendentes_bp" not in st.session_state:

    st.session_state.dados_upload_pendentes_bp = None

if "nome_arquivo_pendente_bp" not in st.session_state:

    st.session_state.nome_arquivo_pendente_bp = None

if "file_uploader_key_bp" not in st.session_state:

    st.session_state.file_uploader_key_bp = 0


# ============================================================
# DIALOGS
# ============================================================
@st.dialog("➕ Cadastrar Novo Ponto")
def modal_novo_ponto():

    lat_default = (
        st.session_state.clicked_lat
        if st.session_state.clicked_lat is not None
        else LAT_BASE
    )

    lon_default = (
        st.session_state.clicked_lon
        if st.session_state.clicked_lon is not None
        else LON_BASE
    )

    with st.form(
        "form_novo_ponto_modal",
        clear_on_submit=True
    ):

        data_cadastro = st.date_input(
            "Data do Registro",
            value=st.session_state.data_final_selecionada,
            format="DD/MM/YYYY"
        )

        municipio = st.text_input(
            "Município *",
            value="Teresina"
        )

        matricula = st.text_input(
            "Matrícula",
            placeholder="Ex: 123456789"
        )

        bairro = st.text_input(
            "Bairro *",
            placeholder="Ex: Centro"
        )

        c1, c2 = st.columns(2)

        with c1:

            lat = st.text_input(
                "Latitude * (aceita vírgula ou ponto)",
                value=str(lat_default)
            )

        with c2:

            lon = st.text_input(
                "Longitude * (aceita vírgula ou ponto)",
                value=str(lon_default)
            )

        pressao = st.number_input(
            "Pressão (MCA) *",
            format="%.2f",
            value=0.00,
            min_value=0.0,
            step=0.1
        )

        observacao = st.text_input(
            "Observação",
            placeholder="Ex: Válvula fechada"
        )

        enviado = st.form_submit_button(
            "Cadastrar Ponto",
            type="primary",
            use_container_width=True
        )

        if enviado:

            lat_n = normalizar_coordenada(
                lat,
                "lat"
            )

            lon_n = normalizar_coordenada(
                lon,
                "lon"
            )

            if not municipio.strip() or not bairro.strip():

                st.error(
                    "Município e Bairro são obrigatórios."
                )

            elif lat_n is None or lon_n is None:

                st.error(
                    "Coordenadas inválidas. "
                    "Verifique os valores de Latitude e Longitude."
                )

            else:

                novo_id = adicionar_ponto(
                    normalizar_texto_local(
                        municipio,
                        padrao="TERESINA"
                    ),
                    matricula.strip(),
                    normalizar_texto_local(
                        bairro,
                        padrao=""
                    ),
                    lat_n,
                    lon_n,
                    pressao,
                    data_para_str(
                        data_cadastro
                    ),
                    observacao.strip()
                )

                st.success(
                    f"Ponto cadastrado com sucesso! ID: {novo_id}"
                )

                st.session_state.clicked_lat = None
                st.session_state.clicked_lon = None

                st.rerun()


@st.dialog("✏️ Editar Ponto")
def modal_editar_ponto(
    id_registro: str
):

    df_all = carregar_dados()

    df_edit_busca = df_all[
        df_all["ID"] == id_registro
    ]

    if not df_edit_busca.empty:

        reg_edit = df_edit_busca.iloc[0]

        try:

            data_parsed = datetime.strptime(
                str(reg_edit["Data"]),
                "%d/%m/%Y"
            ).date()

        except ValueError:

            data_parsed = hoje

        with st.form(
            "form_edicao_modal"
        ):

            data_e = st.date_input(
                "Data do Registro",
                value=data_parsed,
                format="DD/MM/YYYY"
            )

            municipio_e = st.text_input(
                "Município *",
                value=str(
                    reg_edit["Municipio"]
                )
            )

            matricula_e = st.text_input(
                "Matrícula",
                value=str(
                    reg_edit["Matricula"]
                )
            )

            bairro_e = st.text_input(
                "Bairro *",
                value=str(
                    reg_edit["Bairro"]
                )
            )

            c1, c2 = st.columns(2)

            with c1:

                lat_e = st.text_input(
                    "Latitude *",
                    value=str(
                        reg_edit["Latitude"]
                        or LAT_BASE
                    )
                )

            with c2:

                lon_e = st.text_input(
                    "Longitude *",
                    value=str(
                        reg_edit["Longitude"]
                        or LON_BASE
                    )
                )

            pressao_e = st.number_input(
                "Pressão (MCA) *",
                format="%.2f",
                value=float(
                    reg_edit["Pressao_MCA"]
                    or 0.0
                ),
                min_value=0.0,
                step=0.1
            )

            observacao_e = st.text_input(
                "Observação",
                value=str(
                    reg_edit["Observacao"]
                )
            )

            col_salvar, col_canc = st.columns(2)

            with col_salvar:

                salvar_edicao = st.form_submit_button(
                    "💾 Salvar",
                    type="primary",
                    use_container_width=True
                )

            with col_canc:

                cancelar_edicao = st.form_submit_button(
                    "❌ Cancelar",
                    use_container_width=True
                )

            if salvar_edicao:

                lat_n = normalizar_coordenada(
                    lat_e,
                    "lat"
                )

                lon_n = normalizar_coordenada(
                    lon_e,
                    "lon"
                )

                if (
                    not municipio_e.strip()
                    or not bairro_e.strip()
                ):

                    st.error(
                        "Município e Bairro são obrigatórios."
                    )

                elif lat_n is None or lon_n is None:

                    st.error(
                        "Coordenadas inválidas."
                    )

                else:

                    if atualizar_ponto(
                        id_registro,
                        normalizar_texto_local(
                            municipio_e,
                            padrao="TERESINA"
                        ),
                        matricula_e.strip(),
                        normalizar_texto_local(
                            bairro_e,
                            padrao=""
                        ),
                        lat_n,
                        lon_n,
                        pressao_e,
                        data_para_str(
                            data_e
                        ),
                        observacao_e.strip()
                    ):

                        st.success(
                            "Atualizado com sucesso!"
                        )

                        st.rerun()

            if cancelar_edicao:

                st.rerun()

    else:

        st.warning(
            "Registro não encontrado."
        )


@st.dialog("📋 Pré-visualização da Planilha")
def modal_previa_upload():

    st.write(
        f"Arquivo carregado: "
        f"**{st.session_state.nome_arquivo_pendente_bp}**"
    )

    df_preview = pd.DataFrame(
        st.session_state.dados_upload_pendentes_bp,
        columns=[
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
    )

    st.dataframe(
        df_preview[
            [
                "Data",
                "Municipio",
                "Matricula",
                "Bairro",
                "Latitude",
                "Longitude",
                "Pressao_MCA",
                "Observacao"
            ]
        ],
        use_container_width=True
    )

    st.info(
        f"Total de registros válidos prontos para envio: "
        f"**{len(df_preview)}**"
    )

    col_btn1, col_btn2 = st.columns(2)

    with col_btn1:

        if st.button(
            "Confirmar e Enviar",
            type="primary",
            use_container_width=True
        ):

            with st.spinner(
                "Enviando registros com segurança para o Google Sheets..."
            ):

                qtd_inserida = adicionar_lote_seguro(
                    st.session_state.dados_upload_pendentes_bp
                )

            st.session_state.dados_upload_pendentes_bp = None
            st.session_state.nome_arquivo_pendente_bp = None
            st.session_state.file_uploader_key_bp += 1

            if qtd_inserida > 0:

                st.success(
                    f"✅ {qtd_inserida} novos registros importados com sucesso!"
                )

            else:

                st.info(
                    "ℹ️ Todos os registros da planilha já existiam "
                    "no sistema. Nenhuma duplicação foi feita."
                )

            time.sleep(1)

            st.rerun()

    with col_btn2:

        if st.button(
            "Cancelar",
            use_container_width=True
        ):

            st.session_state.dados_upload_pendentes_bp = None
            st.session_state.nome_arquivo_pendente_bp = None
            st.session_state.file_uploader_key_bp += 1

            st.rerun()


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:

    st.markdown(
        "### 💧 COI - Monitoramento"
    )

    st.caption(
        "Baixa Pressão • Tempo Real"
    )

    st.markdown(
        "#### 📅 Selecionar Período"
    )

    c_data_ini, c_data_fim = st.columns(2)

    with c_data_ini:

        data_inicial = st.date_input(
            "Data inicial",
            value=st.session_state.data_inicial_selecionada,
            format="DD/MM/YYYY",
            key="calendario_data_inicial"
        )

    with c_data_fim:

        data_final = st.date_input(
            "Data final",
            value=st.session_state.data_final_selecionada,
            format="DD/MM/YYYY",
            key="calendario_data_final"
        )

    st.session_state.data_inicial_selecionada = data_inicial
    st.session_state.data_final_selecionada = data_final

    if data_inicial > data_final:

        st.error(
            "A data inicial não pode ser maior que a data final."
        )

        periodo_valido = False

    else:

        periodo_valido = True

        if data_inicial == data_final:

            st.success(
                f"Exibindo dados de "
                f"**{data_para_str(data_inicial)}**"
            )

        else:

            st.info(
                f"Exibindo dados de "
                f"**{data_para_str(data_inicial)}** "
                f"a **{data_para_str(data_final)}**"
            )

    st.divider()

    st.markdown(
        "#### 🔍 Filtros"
    )

    df_all = carregar_dados()

    if not df_all.empty and periodo_valido:

        df_all["DataObjFiltro"] = pd.to_datetime(
            df_all["Data"],
            format="%d/%m/%Y",
            errors="coerce"
        )

        df_data = df_all[
            (
                df_all["DataObjFiltro"].dt.date
                >= data_inicial
            )
            &
            (
                df_all["DataObjFiltro"].dt.date
                <= data_final
            )
        ].copy()

    else:

        df_data = (
            df_all.copy()
            if not df_all.empty
            else df_all
        )

    municipios_opts = (
        ["Todos"]
        +
        sorted(
            df_data["Municipio"]
            .dropna()
            .unique()
            .tolist()
        )
        if not df_data.empty
        else ["Todos"]
    )

    mun_sel = st.selectbox(
        "Município",
        municipios_opts,
        key="filtro_municipio"
    )

    bairros_base = (
        df_data[
            df_data["Municipio"] == mun_sel
        ]
        if (
            mun_sel != "Todos"
            and not df_data.empty
        )
        else df_data
    )

    bairros_opts = (
        ["Todos"]
        +
        sorted(
            bairros_base["Bairro"]
            .dropna()
            .unique()
            .tolist()
        )
        if not bairros_base.empty
        else ["Todos"]
    )

    bairro_sel = st.selectbox(
        "Bairro",
        bairros_opts,
        key="filtro_bairro"
    )

    # ========================================================
    # FILTRO DE MATRÍCULA
    # ========================================================
    matriculas_base = (
        df_data[
            (
                df_data["Municipio"] == mun_sel
            )
            &
            (
                df_data["Bairro"] == bairro_sel
            )
        ]
        if (
            mun_sel != "Todos"
            and bairro_sel != "Todos"
            and not df_data.empty
        )
        else (
            df_data[
                df_data["Municipio"] == mun_sel
            ]
            if (
                mun_sel != "Todos"
                and not df_data.empty
            )
            else df_data
        )
    )

    matriculas_opts = (
        ["Todas"]
        +
        sorted(
            [
                str(x).strip()
                for x in matriculas_base["Matricula"]
                .dropna()
                .unique()
                if str(x).strip()
                and str(x).strip().lower()
                not in ("nan", "none")
            ]
        )
        if not matriculas_base.empty
        else ["Todas"]
    )

    matricula_sel = st.selectbox(
        "Matrícula",
        matriculas_opts,
        key="filtro_matricula"
    )

    faixa_sel = st.selectbox(
        "Faixa de Pressão",
        [
            "Todas",
            "Sem Pressão (0 MCA)",
            "Baixa Pressão (> 0 e ≤ 5 MCA)",
            "Em Atenção (> 5 e ≤ 10 MCA)",
            "Alta Pressão (> 15 MCA)"
        ],
        key="filtro_pressao"
    )

    st.divider()

    st.markdown(
        "#### ➕ Ações e Dados"
    )

    if st.button(
        "Adicionar Novo Ponto",
        type="primary",
        use_container_width=True
    ):

        modal_novo_ponto()

    arquivo_upload = st.file_uploader(
        "📂 Enviar Planilha (XLSX/CSV)",
        type=[
            "xlsx",
            "csv"
        ],
        key=(
            f"upload_baixa_pressao_"
            f"{st.session_state.file_uploader_key_bp}"
        )
    )

    # ========================================================
    # MODELO XLSX
    # ========================================================
    df_modelo = pd.DataFrame(
        [{
            "Data": datetime.now().strftime(
                "%d/%m/%Y"
            ),
            "Municipio": "TERESINA",
            "Bairro": "CENTRO",
            "Latitude": -5.0892,
            "Longitude": -42.8019,
            "Pressao_MCA": 2.5,
            "Observacao": "EXEMPLO DE OBSERVAÇÃO",
            "Matricula": "123456789"
        }],
        columns=COLUNAS_PADRAO[1:]
    )

    output_modelo = io.BytesIO()

    with pd.ExcelWriter(
        output_modelo,
        engine="openpyxl"
    ) as writer:

        df_modelo.to_excel(
            writer,
            index=False,
            sheet_name="Modelo"
        )

    st.download_button(
        label="📥 Baixar Planilha Modelo",
        data=output_modelo.getvalue(),
        file_name=(
            "modelo_importacao_"
            "baixa_pressao.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True
    )

    # ========================================================
    # UPLOAD
    # ========================================================
    if arquivo_upload is not None:

        if (
            st.session_state.nome_arquivo_pendente_bp
            != arquivo_upload.name
        ):

            try:

                if arquivo_upload.name.endswith(
                    ".csv"
                ):

                    df_up = pd.read_csv(
                        arquivo_upload
                    )

                else:

                    df_up = pd.read_excel(
                        arquivo_upload
                    )

                # Normaliza os nomes das colunas.
                # Aceita Matricula, Matrícula, MATRICULA, etc.
                df_up.columns = [
                    normalizar_coluna(c)
                    for c in df_up.columns
                ]

                lote_para_enviar = []

                for _, row in df_up.iterrows():

                    raw_data = row.get(
                        "Data",
                        row.get(
                            "date",
                            ""
                        )
                    )

                    data_val = normalizar_data(
                        raw_data
                    )

                    if not data_val:

                        data_val = data_para_str(
                            st.session_state
                            .data_final_selecionada
                        )

                    muni = normalizar_texto_local(
                        row.get(
                            "Municipio",
                            "TERESINA"
                        ),
                        padrao="TERESINA"
                    )

                    bair = normalizar_texto_local(
                        row.get(
                            "Bairro",
                            ""
                        ),
                        padrao=""
                    )

                    matricula_val = str(
                        row.get(
                            "Matricula",
                            ""
                        )
                    ).strip()

                    if matricula_val.lower() in (
                        "nan",
                        "none"
                    ):

                        matricula_val = ""

                    lat_val = normalizar_coordenada(
                        row.get(
                            "Latitude",
                            row.get("Lat")
                        ),
                        "lat"
                    )

                    lon_val = normalizar_coordenada(
                        row.get(
                            "Longitude",
                            row.get("Lon")
                        ),
                        "lon"
                    )

                    pres_val = parse_float(
                        row.get(
                            "Pressao_MCA",
                            0.0
                        ),
                        0.0
                    )

                    obs_val = str(
                        row.get(
                            "Observacao",
                            ""
                        )
                    ).strip()

                    if obs_val.lower() in (
                        "nan",
                        "none"
                    ):

                        obs_val = ""

                    if (
                        bair
                        and lat_val is not None
                        and lon_val is not None
                    ):

                        lote_para_enviar.append([
                            gerar_id(),
                            data_val,
                            muni,
                            bair,
                            float(lat_val),
                            float(lon_val),
                            float(pres_val),
                            obs_val,
                            matricula_val
                        ])

                if lote_para_enviar:

                    st.session_state.dados_upload_pendentes_bp = (
                        lote_para_enviar
                    )

                    st.session_state.nome_arquivo_pendente_bp = (
                        arquivo_upload.name
                    )

                else:

                    st.warning(
                        "⚠️ Nenhum registro válido encontrado. "
                        "Verifique se os nomes das colunas são: "
                        "Data, Municipio, Matricula, Bairro, Latitude, "
                        "Longitude, Pressao_MCA, Observacao."
                    )

            except Exception as e:

                st.error(
                    f"❌ Erro ao processar arquivo: {e}"
                )

    if (
        st.session_state.dados_upload_pendentes_bp
        is not None
    ):

        modal_previa_upload()

    st.divider()

    st.markdown(
        "#### 📥 Exportar Dados"
    )

    if not df_all.empty:

        output = io.BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            df_all.to_excel(
                writer,
                index=False,
                sheet_name="Baixa_Pressao"
            )

        excel_data = output.getvalue()

        st.download_button(
            label="📊 Baixar em Excel (XLSX)",
            data=excel_data,
            file_name=(
                f"baixa_pressao_"
                f"{datetime.now().strftime('%Y%m%d')}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True
        )

        kml_string = gerar_kml(
            df_all
        )

        st.download_button(
            label="🗺️ Baixar Mapa (KML/KMZ)",
            data=kml_string,
            file_name=(
                f"baixa_pressao_"
                f"{datetime.now().strftime('%Y%m%d')}.kml"
            ),
            mime="application/vnd.google-earth.kml+xml",
            use_container_width=True
        )

    st.divider()

    st.markdown(
        "#### ⏱️ Atualização"
    )

    intervalo = st.select_slider(
        "Intervalo (segundos)",
        options=[
            0,
            15,
            30,
            60,
            120
        ],
        value=30
    )

    if intervalo > 0:

        st_autorefresh(
            interval=intervalo * 1000,
            key="autorefresh"
        )

    st.markdown(
        "<br>" * 2,
        unsafe_allow_html=True
    )

    st.divider()

    if st.button(
        "🏠 Voltar ao Menu Principal",
        use_container_width=True
    ):

        st.switch_page(
            "app.py"
        )

    st.divider()

    if "modo_escuro_bp" not in st.session_state:

        st.session_state.modo_escuro_bp = False

    modo_escuro_bp = st.toggle(
        "🌙 Modo escuro",
        value=st.session_state.modo_escuro_bp,
        key="toggle_modo_escuro_bp",
    )

    st.session_state.modo_escuro_bp = (
        modo_escuro_bp
    )

    if modo_escuro_bp:

        st.markdown(
            """
            <style>
                .stApp {
                    background-color: #0e1117;
                    color: #fafafa;
                }

                [data-testid="stSidebar"] {
                    background-color: #161b22;
                }

                .stApp p,
                .stApp label,
                .stApp h1,
                .stApp h2,
                .stApp h3,
                .stApp h4,
                .stApp h5,
                .stApp h6 {
                    color: #f0f0f0 !important;
                }

                [data-testid="stMetric"],
                [data-testid="stExpander"],
                div[data-testid="stDataFrame"] {
                    background-color: #161b22;
                }

                input,
                textarea,
                [data-baseweb="select"] > div {
                    background-color: #21262d !important;
                    color: #f0f0f0 !important;
                }

                [data-baseweb="select"] * {
                    color: #f0f0f0 !important;
                }

                .stButton > button,
                .stDownloadButton > button {
                    background-color: #000000 !important;
                    color: #ffffff !important;
                    border: 1px solid #444c56 !important;
                }

                .stButton > button *,
                .stDownloadButton > button * {
                    color: #ffffff !important;
                }

                .stButton > button:hover,
                .stDownloadButton > button:hover {
                    background-color: #000000 !important;
                    color: #ff0000 !important;
                    border-color: #ff0000 !important;
                }

                .stButton > button:hover *,
                .stDownloadButton > button:hover * {
                    color: #ff0000 !important;
                }

                [data-testid="stDataFrame"] {
                    color: #f0f0f0;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# ÁREA PRINCIPAL
# ============================================================
st.title(
    "💧 Painel de Monitoramento de Baixa Pressão - COI"
)

if periodo_valido:

    if data_inicial == data_final:

        st.caption(
            f"Visualizando: "
            f"**{data_para_str(data_inicial)}**"
        )

    else:

        st.caption(
            f"Visualizando de "
            f"**{data_para_str(data_inicial)}** "
            f"a **{data_para_str(data_final)}**"
        )

df = carregar_dados()


# ============================================================
# FILTRO PRINCIPAL POR INTERVALO
# ============================================================
if not df.empty and periodo_valido:

    df["DataObjFiltro"] = pd.to_datetime(
        df["Data"],
        format="%d/%m/%Y",
        errors="coerce"
    )

    df_filtrado = df[
        (
            df["DataObjFiltro"].dt.date
            >= data_inicial
        )
        &
        (
            df["DataObjFiltro"].dt.date
            <= data_final
        )
    ].copy()

else:

    df_filtrado = (
        df.copy()
        if not df.empty
        else df.copy()
    )


if mun_sel != "Todos":

    df_filtrado = df_filtrado[
        df_filtrado["Municipio"] == mun_sel
    ]


if bairro_sel != "Todos":

    df_filtrado = df_filtrado[
        df_filtrado["Bairro"] == bairro_sel
    ]


# ============================================================
# FILTRO PRINCIPAL POR MATRÍCULA
# ============================================================
if matricula_sel != "Todas":

    df_filtrado = df_filtrado[
        df_filtrado["Matricula"]
        .astype(str)
        .str.strip()
        == matricula_sel
    ]


if faixa_sel == "Sem Pressão (0 MCA)":

    df_filtrado = df_filtrado[
        df_filtrado["Pressao_MCA"] == 0
    ]

elif faixa_sel == "Baixa Pressão (> 0 e ≤ 5 MCA)":

    df_filtrado = df_filtrado[
        (
            df_filtrado["Pressao_MCA"] > 0
        )
        &
        (
            df_filtrado["Pressao_MCA"] <= 5
        )
    ]

elif faixa_sel == "Em Atenção (> 5 e ≤ 10 MCA)":

    # ========================================================
    # IMPORTANTE:
    # O texto apresentado ao usuário permanece ≤ 10 MCA,
    # mas a regra operacional continua sendo ≤ 15 MCA.
    # ========================================================
    df_filtrado = df_filtrado[
        (
            df_filtrado["Pressao_MCA"] > 5
        )
        &
        (
            df_filtrado["Pressao_MCA"] <= 15
        )
    ]

elif faixa_sel == "Alta Pressão (> 15 MCA)":

    df_filtrado = df_filtrado[
        df_filtrado["Pressao_MCA"] > 15
    ]


# ============================================================
# MÉTRICAS
# ============================================================
if not df_filtrado.empty:

    total = len(
        df_filtrado
    )

    sem_pressao = len(
        df_filtrado[
            df_filtrado["Pressao_MCA"] == 0
        ]
    )

    baixa_pressao = len(
        df_filtrado[
            (
                df_filtrado["Pressao_MCA"] > 0
            )
            &
            (
                df_filtrado["Pressao_MCA"] <= 5
            )
        ]
    )

    em_atencao = len(
        df_filtrado[
            (
                df_filtrado["Pressao_MCA"] > 5
            )
            &
            (
                df_filtrado["Pressao_MCA"] <= 15
            )
        ]
    )

    alta_pressao = len(
        df_filtrado[
            df_filtrado["Pressao_MCA"] > 15
        ]
    )

    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric(
        "Total de Ocorrências",
        total
    )

    k2.metric(
        "Sem Pressão (0 MCA)",
        sem_pressao
    )

    k3.metric(
        "Baixa Pressão (≤ 5 MCA)",
        baixa_pressao
    )

    k4.metric(
        "Em Atenção (> 5 e ≤ 10 MCA)",
        em_atencao
    )

    k5.metric(
        "Alta Pressão (> 15 MCA)",
        alta_pressao
    )

else:

    if periodo_valido:

        st.info(
            "Nenhum ponto registrado no período "
            "e filtros selecionados."
        )


st.divider()


# ============================================================
# MAPA
# ============================================================
st.subheader(
    "🗺️ Mapa de Baixa Pressão"
)

c_map1, c_map2, c_map3, c_map4 = st.columns(
    [2, 2.2, 2, 2]
)


with c_map1:

    tipo_mapa = st.selectbox(
        "🗺️ Tipo de Mapa",
        options=[
            "Mapa Padrão (OpenStreetMap)",
            "Satélite (Esri World Imagery)",
            "Terreno (OpenTopoMap)"
        ],
        key="seletor_tipo_mapa_bp"
    )


with c_map2:

    modo_visualizacao = st.selectbox(
        "📊 Visualização",
        options=[
            "Por bairro",
            "Medições individuais"
        ],
        key="modo_visualizacao_mapa_bp",
        help=(
            "Por bairro mostra uma visão gerencial consolidada. "
            "Medições individuais mostra cada ponto registrado."
        )
    )


with c_map3:

    st.checkbox(
        "Exibir rótulos dos bairros",
        value=True,
        key="mostrar_rotulos_bp",
        help=(
            "Mostra informações junto aos pins. "
            "No modo por bairro mostra pressão média e quantidade. "
            "No modo individual mostra a medição daquele ponto."
        )
    )

    mostrar_rotulos = st.session_state.mostrar_rotulos_bp


with c_map4:

    st.session_state.modo_adicionar_mapa = st.checkbox(
        "📍 Modo adicionar ponto",
        value=st.session_state.modo_adicionar_mapa
    )


if (
    not df_filtrado.empty
    and df_filtrado["Latitude"].notna().any()
):

    centro_lat = float(
        df_filtrado["Latitude"].mean()
    )

    centro_lon = float(
        df_filtrado["Longitude"].mean()
    )

    zoom = 13

else:

    centro_lat = LAT_BASE
    centro_lon = LON_BASE
    zoom = 12


m = folium.Map(
    location=[
        centro_lat,
        centro_lon
    ],
    zoom_start=zoom,
    tiles=None,
    control_scale=True
)


if "Satélite" in tipo_mapa:

    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/"
            "ArcGIS/rest/services/World_Imagery/"
            "MapServer/tile/{z}/{y}/{x}"
        ),
        attr=(
            "Esri &mdash; Source: Esri, i-cubed, USDA, "
            "USGS, AEX, GeoEye, Getmapping, Aerogrid, "
            "IGN, IGP, UPR-EGP, and the GIS User Community"
        ),
        name="Satélite (Esri World Imagery)"
    ).add_to(m)

elif "Terreno" in tipo_mapa:

    folium.TileLayer(
        "OpenTopoMap",
        name="Terreno (OpenTopoMap)"
    ).add_to(m)

else:

    folium.TileLayer(
        "OpenStreetMap",
        name="Mapa Padrão (OpenStreetMap)"
    ).add_to(m)


# ============================================================
# FUNÇÕES VISUAIS DOS PINS
# ============================================================
def gerar_pin_svg(
    cor: str,
    tamanho: str = "bairro"
) -> str:

    """
    Gera um pin SVG independente do CSS de rotação.

    Isso evita problemas de renderização do pin
    dentro do DivIcon do Folium.
    """

    if tamanho == "individual":

        largura = 34
        altura = 39

        escala = 0.88

    else:

        largura = 40
        altura = 45

        escala = 1.0

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
            bottom:0;
            transform:translateX(-50%);
            overflow:visible;
            pointer-events:auto;
            z-index:1100;
        "
    >

        <path
            d="
                M20 43
                C18.5 40.8 5 26.2 5 16
                C5 7.72 11.72 1 20 1
                C28.28 1 35 7.72 35 16
                C35 26.2 21.5 40.8 20 43
                Z
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
# VISUALIZAÇÃO DOS MARCADORES
# ============================================================
if not df_filtrado.empty:

    validos = df_filtrado.dropna(
        subset=[
            "Latitude",
            "Longitude"
        ]
    ).copy()

    if not validos.empty:

        validos["Municipio"] = (
            validos["Municipio"]
            .fillna("MUNICIPIO NAO INFORMADO")
            .astype(str)
            .str.strip()
        )

        validos["Bairro"] = (
            validos["Bairro"]
            .fillna("BAIRRO NAO INFORMADO")
            .astype(str)
            .str.strip()
        )

        validos["Matricula"] = (
            validos["Matricula"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        validos["Pressao_MCA"] = pd.to_numeric(
            validos["Pressao_MCA"],
            errors="coerce"
        ).fillna(0.0)

        # ====================================================
        # MEDIÇÕES INDIVIDUAIS
        # ====================================================
        if modo_visualizacao == "Medições individuais":

            for _, registro in validos.iterrows():

                pressao = float(
                    registro["Pressao_MCA"]
                )

                classificacao, cor = classificar_pressao(
                    pressao
                )

                pressao_formatada = (
                    f"{pressao:.2f}"
                    .replace(".", ",")
                )

                bairro = str(
                    registro["Bairro"]
                )

                municipio = str(
                    registro["Municipio"]
                )

                matricula = str(
                    registro.get(
                        "Matricula",
                        ""
                    )
                ).strip()

                data_registro = str(
                    registro["Data"]
                )

                observacao = str(
                    registro.get(
                        "Observacao",
                        ""
                    )
                )

                observacao_html = ""

                if (
                    observacao
                    and observacao.lower() != "nan"
                ):

                    observacao_html = f"""
                    <div style="
                        margin-top:9px;
                        font-size:11px;
                        color:#475569;
                    ">
                        <b>Observação:</b> {escape(observacao)}
                    </div>
                    """

                popup_individual = f"""
                <div style="
                    width:250px;
                    font-family:Arial,sans-serif;
                    color:#111827;
                ">

                    <div style="
                        font-size:16px;
                        font-weight:800;
                        margin-bottom:2px;
                    ">
                        {escape(bairro)}
                    </div>

                    <div style="
                        font-size:11px;
                        color:#6b7280;
                        margin-bottom:8px;
                    ">
                        {escape(municipio)}
                    </div>

                    <div style="
                        font-size:11px;
                        color:#475569;
                        margin-bottom:10px;
                    ">
                        <b>Matrícula:</b>
                        {escape(matricula) if matricula else "Não informada"}
                    </div>

                    <div style="
                        background:#f8fafc;
                        border-radius:8px;
                        padding:9px;
                        border-left:4px solid {cor};
                        margin-bottom:10px;
                    ">

                        <div style="
                            font-size:10px;
                            color:#64748b;
                        ">
                            PRESSÃO MEDIDA
                        </div>

                        <div style="
                            font-size:20px;
                            font-weight:800;
                        ">
                            {pressao_formatada} MCA
                        </div>

                    </div>

                    <div style="
                        font-size:11px;
                        color:#475569;
                        line-height:1.55;
                    ">
                        <b>Classificação:</b> {classificacao}<br>
                        <b>Data:</b> {escape(data_registro)}<br>
                        <b>ID:</b> {escape(str(registro['ID']))}
                    </div>

                    {observacao_html}

                </div>
                """

                # --------------------------------------------
                # RÓTULO INDIVIDUAL
                # Matrícula NÃO entra aqui.
                # --------------------------------------------
                if mostrar_rotulos:

                    marker_html = f"""
                    <div
                        class="bp-marker-wrapper bp-individual-marker-wrapper"
                        data-bp-priority="1"
                        style="
                            position:relative;
                            width:42px;
                            height:70px;
                            overflow:visible;
                            font-family:Arial,sans-serif;
                            pointer-events:auto;
                        "
                    >

                        {gerar_pin_svg(
                            cor,
                            "individual"
                        )}

                        <div
                            class="bp-label-card bp-label-card-individual"
                            data-bp-default="top"
                        >

                            <div class="bp-label-title">
                                {escape(bairro)}
                            </div>

                            <div class="bp-label-data">

                                <span class="bp-label-pressure">
                                    {pressao_formatada} MCA
                                </span>

                                <span class="bp-label-separator"></span>

                                <span>
                                    {escape(classificacao)}
                                </span>

                            </div>

                        </div>

                    </div>
                    """

                else:

                    marker_html = f"""
                    <div
                        class="bp-marker-wrapper bp-individual-marker-wrapper"
                        data-bp-priority="1"
                        style="
                            position:relative;
                            width:42px;
                            height:70px;
                            overflow:visible;
                            font-family:Arial,sans-serif;
                            pointer-events:auto;
                        "
                    >

                        {gerar_pin_svg(
                            cor,
                            "individual"
                        )}

                    </div>
                    """

                folium.map.Marker(
                    location=[
                        float(registro["Latitude"]),
                        float(registro["Longitude"])
                    ],
                    icon=folium.DivIcon(
                        html=marker_html,
                        icon_size=(
                            42,
                            70
                        ),
                        icon_anchor=(
                            21,
                            70
                        ),
                        class_name=(
                            "pressao-individual-marker"
                        )
                    ),
                    popup=folium.Popup(
                        popup_individual,
                        max_width=290
                    ),
                    tooltip=(
                        f"{bairro} | "
                        f"{pressao_formatada} MCA | "
                        f"{classificacao}"
                    )
                ).add_to(m)

        # ====================================================
        # POR BAIRRO
        # ====================================================
        else:

            grupos_bairro = validos.groupby(
                [
                    "Municipio",
                    "Bairro"
                ],
                dropna=False,
                sort=True
            )

            for (
                municipio,
                bairro
            ), grupo in grupos_bairro:

                quantidade = int(
                    len(grupo)
                )

                media = float(
                    grupo["Pressao_MCA"].mean()
                )

                lat_bairro = float(
                    grupo["Latitude"].mean()
                )

                lon_bairro = float(
                    grupo["Longitude"].mean()
                )

                classificacao, cor = classificar_pressao(
                    media
                )

                media_formatada = (
                    f"{media:.2f}"
                    .replace(".", ",")
                )

                texto_medicoes = (
                    "medição"
                    if quantidade == 1
                    else "medições"
                )

                pressao_min = float(
                    grupo["Pressao_MCA"].min()
                )

                pressao_max = float(
                    grupo["Pressao_MCA"].max()
                )

                min_formatado = (
                    f"{pressao_min:.2f}"
                    .replace(".", ",")
                )

                max_formatado = (
                    f"{pressao_max:.2f}"
                    .replace(".", ",")
                )

                bairro_html = escape(
                    str(bairro)
                )

                municipio_html = escape(
                    str(municipio)
                )

                # =================================================
                # DETALHES DAS MEDIÇÕES
                # =================================================
                linhas_medicoes = []

                for _, registro in grupo.sort_values(
                    by=[
                        "Data",
                        "ID"
                    ],
                    ascending=[
                        False,
                        True
                    ]
                ).iterrows():

                    pressao_reg = float(
                        registro["Pressao_MCA"]
                    )

                    pressao_reg_formatada = (
                        f"{pressao_reg:.2f}"
                        .replace(".", ",")
                    )

                    matricula_reg = str(
                        registro.get(
                            "Matricula",
                            ""
                        )
                    ).strip()

                    matricula_html = ""

                    if matricula_reg:

                        matricula_html = f"""
                        <div style="
                            color:#6b7280;
                            margin-top:2px;
                        ">
                            Matrícula:
                            {escape(matricula_reg)}
                        </div>
                        """

                    linhas_medicoes.append(
                        f"""
                        <div style="
                            padding:7px 0;
                            border-bottom:1px solid #e5e7eb;
                            font-size:11px;
                        ">

                            <div style="
                                font-weight:700;
                                color:#111827;
                            ">
                                {escape(str(registro['Data']))} ·
                                {pressao_reg_formatada} MCA
                            </div>

                            <div style="
                                color:#6b7280;
                                margin-top:2px;
                            ">
                                ID: {escape(str(registro['ID']))}
                            </div>

                            {matricula_html}

                        </div>
                        """
                    )

                detalhes_medicoes = "".join(
                    linhas_medicoes[:12]
                )

                if quantidade > 12:

                    detalhes_medicoes += (
                        f"""
                        <div style="
                            margin-top:7px;
                            color:#6b7280;
                            font-size:10px;
                            text-align:center;
                        ">
                            + {quantidade - 12}
                            medições adicionais
                        </div>
                        """
                    )

                popup = f"""
                <div style="
                    width:280px;
                    font-family:Arial,sans-serif;
                    color:#111827;
                ">

                    <div style="
                        font-size:17px;
                        font-weight:800;
                        margin-bottom:2px;
                    ">
                        {bairro_html}
                    </div>

                    <div style="
                        font-size:11px;
                        color:#6b7280;
                        margin-bottom:12px;
                    ">
                        {municipio_html}
                    </div>

                    <div style="
                        display:flex;
                        gap:6px;
                        margin-bottom:10px;
                    ">

                        <div style="
                            flex:1;
                            background:#f8fafc;
                            border-radius:8px;
                            padding:8px;
                            border-left:4px solid {cor};
                        ">

                            <div style="
                                font-size:10px;
                                color:#64748b;
                            ">
                                MÉDIA
                            </div>

                            <div style="
                                font-size:18px;
                                font-weight:800;
                            ">
                                {media_formatada} MCA
                            </div>

                        </div>

                        <div style="
                            width:92px;
                            background:#f8fafc;
                            border-radius:8px;
                            padding:8px;
                        ">

                            <div style="
                                font-size:10px;
                                color:#64748b;
                            ">
                                MEDIÇÕES
                            </div>

                            <div style="
                                font-size:18px;
                                font-weight:800;
                            ">
                                {quantidade}
                            </div>

                        </div>

                    </div>

                    <div style="
                        font-size:11px;
                        color:#475569;
                        margin-bottom:8px;
                    ">
                        Faixa: <b>{classificacao}</b><br>
                        Mínima: <b>{min_formatado} MCA</b> ·
                        Máxima: <b>{max_formatado} MCA</b>
                    </div>

                    <div style="
                        max-height:220px;
                        overflow-y:auto;
                        border-top:1px solid #e5e7eb;
                    ">
                        {detalhes_medicoes}
                    </div>

                </div>
                """

                # =================================================
                # MARCADOR DO BAIRRO
                # =================================================
                if mostrar_rotulos:

                    marker_html = f"""
                    <div
                        class="bp-marker-wrapper bp-bairro-marker-wrapper"
                        data-bp-priority="{quantidade}"
                        style="
                            position:relative;
                            width:44px;
                            height:75px;
                            overflow:visible;
                            font-family:Arial,sans-serif;
                            pointer-events:auto;
                        "
                    >

                        {gerar_pin_svg(
                            cor,
                            "bairro"
                        )}

                        <div
                            class="bp-label-card bp-label-card-bairro"
                            data-bp-default="top"
                        >

                            <div class="bp-label-title">
                                {bairro_html}
                            </div>

                            <div class="bp-label-data">

                                <span class="bp-label-pressure">
                                    {media_formatada} MCA
                                </span>

                                <span class="bp-label-separator"></span>

                                <span>
                                    {quantidade}
                                    {texto_medicoes}
                                </span>

                            </div>

                        </div>

                    </div>
                    """

                else:

                    marker_html = f"""
                    <div
                        class="bp-marker-wrapper bp-bairro-marker-wrapper"
                        data-bp-priority="{quantidade}"
                        style="
                            position:relative;
                            width:44px;
                            height:75px;
                            overflow:visible;
                            font-family:Arial,sans-serif;
                            pointer-events:auto;
                        "
                    >

                        {gerar_pin_svg(
                            cor,
                            "bairro"
                        )}

                    </div>
                    """

                folium.map.Marker(
                    location=[
                        lat_bairro,
                        lon_bairro
                    ],
                    icon=folium.DivIcon(
                        html=marker_html,
                        icon_size=(
                            44,
                            75
                        ),
                        icon_anchor=(
                            22,
                            75
                        ),
                        class_name=(
                            "pressao-bairro-marker"
                        )
                    ),
                    popup=folium.Popup(
                        popup,
                        max_width=320
                    ),
                    tooltip=(
                        f"{bairro} | "
                        f"{media_formatada} MCA | "
                        f"{quantidade} {texto_medicoes}"
                    )
                ).add_to(m)


# ============================================================
# ESTILO DOS PINS E RÓTULOS
# ============================================================
map_style_html = """
<style>

    .leaflet-marker-icon.pressao-bairro-marker,
    .leaflet-marker-icon.pressao-individual-marker {

        background: transparent !important;

        border: 0 !important;

        overflow: visible !important;

        padding: 0 !important;

        margin: 0 !important;
    }


    .pressao-bairro-marker .bp-marker-wrapper,
    .pressao-individual-marker .bp-marker-wrapper {

        position: relative !important;

        overflow: visible !important;

        pointer-events: auto !important;

        font-family: Arial, sans-serif;
    }


    .bp-pin-svg {

        display: block !important;

        visibility: visible !important;

        opacity: 1 !important;

        overflow: visible !important;

        pointer-events: auto !important;
    }


    .pressao-bairro-marker .bp-pin-svg,
    .pressao-individual-marker .bp-pin-svg {

        z-index: 1100 !important;
    }


    .bp-label-card {

        position: absolute;

        width: 158px;

        box-sizing: border-box;

        padding: 5px 8px;

        background: rgba(255, 255, 255, 0.97);

        border: 1px solid #d7dee8;

        border-left: 3px solid var(--bp-color, #64748b);

        border-radius: 6px;

        box-shadow:
            0 2px 8px rgba(15, 23, 42, 0.20);

        color: #111827;

        font-family: Arial, sans-serif;

        display: block;

        opacity: 1;

        visibility: visible;

        z-index: 1000;

        pointer-events: none;

        line-height: 1.1;

        white-space: normal;

        transition:
            left 0.12s ease,
            top 0.12s ease,
            transform 0.12s ease;

        overflow: hidden;
    }


    .bp-marker-wrapper {

        --bp-color: #64748b;
    }


    .bp-label-title {

        font-size: 11px;

        font-weight: 800;

        line-height: 1.15;

        white-space: nowrap;

        overflow: hidden;

        text-overflow: ellipsis;

        color: #111827;
    }


    .bp-label-data {

        display: flex;

        align-items: center;

        gap: 6px;

        margin-top: 4px;

        font-size: 9px;

        line-height: 1.1;

        color: #475569;

        white-space: nowrap;
    }


    .bp-label-pressure {

        font-weight: 800;

        color: #111827;
    }


    .bp-label-separator {

        display: inline-block;

        width: 1px;

        height: 10px;

        background: #cbd5e1;

        flex: 0 0 auto;
    }


    .bp-label-card-individual {

        width: 145px;

        padding: 5px 7px;
    }


    .bp-label-card-individual .bp-label-title {

        font-size: 10px;
    }


    .bp-label-card-individual .bp-label-data {

        font-size: 8.5px;

        gap: 5px;
    }


    .bp-label-card-bairro {

        width: 158px;
    }


    .pressao-bairro-marker .leaflet-tooltip,
    .pressao-individual-marker .leaflet-tooltip {

        display: none !important;
    }

</style>
"""

m.get_root().html.add_child(
    Element(map_style_html)
)


# ============================================================
# DESCONGESTIONAMENTO DINÂMICO DOS RÓTULOS
# ============================================================
map_name = m.get_name()

declutter_js = """
<script>
(function() {

    function iniciarDeclutter() {

        if (typeof MAP_NAME_PLACEHOLDER === "undefined") {

            setTimeout(
                iniciarDeclutter,
                150
            );

            return;
        }


        var map = MAP_NAME_PLACEHOLDER;


        function caixasSeSobrepoem(
            a,
            b,
            margem
        ) {

            return !(
                a.right + margem < b.left ||
                a.left - margem > b.right ||
                a.bottom + margem < b.top ||
                a.top - margem > b.bottom
            );
        }


        function estaDentroDoMapa(
            caixa,
            areaMapa,
            margem
        ) {

            return !(
                caixa.left < areaMapa.left + margem ||
                caixa.right > areaMapa.right - margem ||
                caixa.top < areaMapa.top + margem ||
                caixa.bottom > areaMapa.bottom - margem
            );
        }


        function aplicarPosicao(
            rotulo,
            posicao
        ) {

            rotulo.style.left = "";
            rotulo.style.top = "";
            rotulo.style.transform = "";


            if (posicao === "top") {

                rotulo.style.left = "50%";
                rotulo.style.top = "-12px";
                rotulo.style.transform =
                    "translate(-50%, -100%)";

            }

            else if (posicao === "bottom") {

                rotulo.style.left = "50%";
                rotulo.style.top = "78px";
                rotulo.style.transform =
                    "translate(-50%, 0)";

            }

            else if (posicao === "right") {

                rotulo.style.left = "52px";
                rotulo.style.top = "32px";
                rotulo.style.transform =
                    "translate(0, -50%)";

            }

            else if (posicao === "left") {

                rotulo.style.left = "-12px";
                rotulo.style.top = "32px";
                rotulo.style.transform =
                    "translate(-100%, -50%)";

            }

            else if (posicao === "top-right") {

                rotulo.style.left = "48px";
                rotulo.style.top = "-8px";
                rotulo.style.transform =
                    "translate(0, -100%)";

            }

            else if (posicao === "top-left") {

                rotulo.style.left = "-8px";
                rotulo.style.top = "-8px";
                rotulo.style.transform =
                    "translate(-100%, -100%)";

            }

            else if (posicao === "bottom-right") {

                rotulo.style.left = "48px";
                rotulo.style.top = "78px";
                rotulo.style.transform =
                    "translate(0, 0)";

            }

            else if (posicao === "bottom-left") {

                rotulo.style.left = "-8px";
                rotulo.style.top = "78px";
                rotulo.style.transform =
                    "translate(-100%, 0)";

            }
        }


        function recalcularRotulos() {

            var container = map.getContainer();

            if (!container) {

                return;
            }


            var areaMapa =
                container.getBoundingClientRect();


            var marcadores =
                container.querySelectorAll(
                    ".pressao-bairro-marker .bp-marker-wrapper, " +
                    ".pressao-individual-marker .bp-marker-wrapper"
                );


            if (!marcadores.length) {

                return;
            }


            var candidatos = [];


            marcadores.forEach(
                function(wrapper) {

                    var rotulo =
                        wrapper.querySelector(
                            ".bp-label-card"
                        );


                    if (!rotulo) {

                        return;
                    }


                    var svg =
                        wrapper.querySelector(
                            ".bp-pin-svg"
                        );


                    if (svg) {

                        var path =
                            svg.querySelector(
                                "path"
                            );

                        if (path) {

                            var corPin =
                                path.getAttribute(
                                    "fill"
                                );

                            if (corPin) {

                                wrapper.style.setProperty(
                                    "--bp-color",
                                    corPin
                                );
                            }
                        }
                    }


                    rotulo.style.display =
                        "block";

                    rotulo.style.visibility =
                        "hidden";


                    aplicarPosicao(
                        rotulo,
                        "top"
                    );


                    var prioridade =
                        parseInt(
                            wrapper.getAttribute(
                                "data-bp-priority"
                            ) || "0",
                            10
                        );


                    if (isNaN(prioridade)) {

                        prioridade = 0;
                    }


                    var individual =
                        wrapper.classList.contains(
                            "bp-individual-marker-wrapper"
                        );


                    candidatos.push({

                        wrapper: wrapper,

                        rotulo: rotulo,

                        prioridade: prioridade,

                        individual: individual,

                        ordem: candidatos.length

                    });

                }
            );


            candidatos.sort(
                function(a, b) {

                    if (
                        a.individual
                        !==
                        b.individual
                    ) {

                        return a.individual
                            ? 1
                            : -1;
                    }


                    if (
                        b.prioridade
                        !==
                        a.prioridade
                    ) {

                        return (
                            b.prioridade
                            -
                            a.prioridade
                        );
                    }


                    return (
                        a.ordem
                        -
                        b.ordem
                    );

                }
            );


            var posicoes = [

                "top",

                "bottom",

                "right",

                "left",

                "top-right",

                "top-left",

                "bottom-right",

                "bottom-left"

            ];


            var aceitos = [];


            var margem = 8;


            var margemMapa = 4;


            candidatos.forEach(
                function(item) {

                    var encontrouPosicao = false;

                    // Caixa do pin (ou do wrapper) — o rótulo nunca pode sobrepor o próprio pin
                    var pinEl = item.wrapper.querySelector(".bp-pin-svg") || item.wrapper;
                    var caixaPin = pinEl.getBoundingClientRect();


                    for (
                        var p = 0;
                        p < posicoes.length;
                        p++
                    ) {

                        var posicao =
                            posicoes[p];


                        aplicarPosicao(
                            item.rotulo,
                            posicao
                        );


                        var caixa =
                            item.rotulo
                            .getBoundingClientRect();


                        if (
                            !estaDentroDoMapa(
                                caixa,
                                areaMapa,
                                margemMapa
                            )
                        ) {

                            continue;
                        }


                        // Não permite sobreposição com o próprio pin
                        if (
                            caixasSeSobrepoem(
                                caixa,
                                caixaPin,
                                4
                            )
                        ) {

                            continue;
                        }


                        var conflito = false;


                        for (
                            var i = 0;
                            i < aceitos.length;
                            i++
                        ) {

                            if (
                                caixasSeSobrepoem(
                                    caixa,
                                    aceitos[i],
                                    margem
                                )
                            ) {

                                conflito = true;

                                break;
                            }
                        }


                        if (!conflito) {

                            item.rotulo.style.visibility =
                                "visible";

                            aceitos.push(
                                caixa
                            );

                            encontrouPosicao = true;

                            break;
                        }

                    }


                    if (!encontrouPosicao) {

                        item.rotulo.style.visibility =
                            "hidden";

                    }

                }
            );
        }


        var agendamento = null;


        function agendarRecalculo() {

            if (agendamento) {

                clearTimeout(
                    agendamento
                );
            }


            agendamento = setTimeout(
                function() {

                    recalcularRotulos();


                    requestAnimationFrame(
                        function() {

                            recalcularRotulos();

                        }
                    );


                    agendamento = null;

                },
                80
            );
        }


        map.on(
            "zoomend",
            agendarRecalculo
        );


        map.on(
            "moveend",
            agendarRecalculo
        );


        map.on(
            "resize",
            agendarRecalculo
        );


        window.addEventListener(
            "resize",
            agendarRecalculo
        );


        setTimeout(
            recalcularRotulos,
            100
        );


        setTimeout(
            recalcularRotulos,
            250
        );


        setTimeout(
            recalcularRotulos,
            500
        );


        setTimeout(
            recalcularRotulos,
            900
        );

    }


    iniciarDeclutter();

})();
</script>
"""

declutter_js = declutter_js.replace(
    "MAP_NAME_PLACEHOLDER",
    map_name
)

m.get_root().html.add_child(
    Element(declutter_js)
)


# ============================================================
# LEGENDA DAS CORES
# ============================================================
legend_html = f"""
<div style="
    position: fixed;
    bottom: 24px;
    left: 24px;
    z-index: 9999;
    background-color: rgba(255, 255, 255, 0.94);
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 7px 9px;
    box-shadow: 0 2px 7px rgba(0, 0, 0, 0.16);
    font-family: Arial, sans-serif;
    font-size: 10px;
    line-height: 1.35;
    width: 176px;
    color: #1f2937;
">

    <div style="
        font-weight: 700;
        margin-bottom: 4px;
        color: #111827;
    ">
        Pressão
    </div>

    <div style="
        white-space: nowrap;
    ">
        <span style="
            display:inline-block;
            width:9px;
            height:9px;
            border-radius:50%;
            background:{COR_SEM_PRESSAO};
            margin-right:5px;
            vertical-align:middle;
        "></span>

        Sem Pressão (0 MCA)
    </div>

    <div style="
        white-space: nowrap;
    ">
        <span style="
            display:inline-block;
            width:9px;
            height:9px;
            border-radius:50%;
            background:{COR_BAIXA_PRESSAO};
            margin-right:5px;
            vertical-align:middle;
        "></span>

        Baixa Pressão (&gt; 0 e ≤ 5 MCA)
    </div>

    <div style="
        white-space: nowrap;
    ">
        <span style="
            display:inline-block;
            width:9px;
            height:9px;
            border-radius:50%;
            background:{COR_EM_ATENCAO};
            margin-right:5px;
            vertical-align:middle;
        "></span>

        Em Atenção (&gt; 5 e ≤ 10 MCA)
    </div>

    <div style="
        white-space: nowrap;
    ">
        <span style="
            display:inline-block;
            width:9px;
            height:9px;
            border-radius:50%;
            background:{COR_ALTA_PRESSAO};
            margin-right:5px;
            vertical-align:middle;
        "></span>

        Alta Pressão (&gt; 15 MCA)
    </div>

</div>
"""

m.get_root().html.add_child(
    Element(legend_html)
)


# ============================================================
# RENDERIZAÇÃO DO MAPA
# ============================================================
map_data = st_folium(
    m,
    width="100%",
    height=520,
    returned_objects=[
        "last_clicked"
    ],
    key="mapa_principal"
)


if (
    st.session_state.modo_adicionar_mapa
    and map_data
    and map_data.get(
        "last_clicked"
    )
):

    clicked = map_data[
        "last_clicked"
    ]

    if clicked:

        st.session_state.clicked_lat = round(
            clicked["lat"],
            6
        )

        st.session_state.clicked_lon = round(
            clicked["lng"],
            6
        )

        modal_novo_ponto()


st.divider()


# ============================================================
# TABELA
# ============================================================
st.subheader(
    "📋 Registro de Pontos"
)

if not df_filtrado.empty:

    df_show = df_filtrado[
        [
            "ID",
            "Data",
            "Municipio",
            "Matricula",
            "Bairro",
            "Latitude",
            "Longitude",
            "Pressao_MCA",
            "Observacao"
        ]
    ].reset_index(
        drop=True
    )

    evento = st.dataframe(
        df_show,
        use_container_width=True,
        height=300,
        on_select="rerun",
        selection_mode="single-row",
        key="tabela_registros"
    )

    linhas_selecionadas = (
        evento.selection.rows
        if evento and evento.selection
        else []
    )

    if linhas_selecionadas:

        idx = linhas_selecionadas[0]

        registro = df_show.iloc[
            idx
        ]

        id_sel = str(
            registro["ID"]
        )

        col_a, col_b, _ = st.columns(
            [1, 1, 4]
        )

        with col_a:

            if st.button(
                "✏️ Editar",
                use_container_width=True
            ):

                modal_editar_ponto(
                    id_sel
                )

        with col_b:

            if st.button(
                "🗑️ Excluir",
                use_container_width=True
            ):

                if excluir_ponto(
                    id_sel
                ):

                    st.success(
                        "Excluído com sucesso."
                    )

                    st.rerun()


# ============================================================
# ANALÍTICO
# ============================================================
st.divider()

st.subheader(
    "📈 Análise de Tendência e Variação por Bairro"
)

st.markdown(
    "Selecione um período e um bairro para acompanhar "
    "o histórico e a variação da pressão ao longo do tempo."
)

if not df_all.empty:

    col_g1, col_g2, col_g3 = st.columns(
        [2, 2, 2]
    )

    with col_g1:

        data_inicio_padrao = (
            hoje - timedelta(
                days=30
            )
        )

        data_ini_analise = st.date_input(
            "Data Inicial",
            value=data_inicio_padrao,
            format="DD/MM/YYYY",
            key="analise_ini"
        )

    with col_g2:

        data_fim_analise = st.date_input(
            "Data Final",
            value=hoje,
            format="DD/MM/YYYY",
            key="analise_fim"
        )

    with col_g3:

        bairros_disponiveis = sorted(
            df_all["Bairro"]
            .dropna()
            .unique()
            .tolist()
        )

        bairro_analise = st.selectbox(
            "Selecione o Bairro",
            options=[
                "Selecione..."
            ]
            +
            bairros_disponiveis,
            key="analise_bairro"
        )

    if bairro_analise != "Selecione...":

        if data_ini_analise > data_fim_analise:

            st.error(
                "A data inicial não pode ser maior "
                "que a data final."
            )

        else:

            df_tendencia = df_all[
                df_all["Bairro"]
                == bairro_analise
            ].copy()

            if not df_tendencia.empty:

                df_tendencia["DataObj"] = pd.to_datetime(
                    df_tendencia["Data"],
                    format="%d/%m/%Y",
                    errors="coerce"
                )

                df_tendencia = (
                    df_tendencia
                    .dropna(
                        subset=["DataObj"]
                    )
                )

                mask = (
                    (
                        df_tendencia[
                            "DataObj"
                        ].dt.date
                        >= data_ini_analise
                    )
                    &
                    (
                        df_tendencia[
                            "DataObj"
                        ].dt.date
                        <= data_fim_analise
                    )
                )

                df_tendencia = (
                    df_tendencia
                    .loc[mask]
                    .sort_values(
                        "DataObj"
                    )
                )

                if not df_tendencia.empty:

                    fig = px.line(
                        df_tendencia,
                        x="Data",
                        y="Pressao_MCA",
                        markers=True,
                        title=(
                            f"Evolução da Pressão (MCA) "
                            f"— {bairro_analise}"
                        ),
                        labels={
                            "Data": "Data do Registro",
                            "Pressao_MCA": "Pressão (MCA)"
                        },
                    )

                    fig.add_hline(
                        y=5,
                        line_dash="dash",
                        line_color=COR_BAIXA_PRESSAO,
                        annotation_text=(
                            "Limite: "
                            "Baixa Pressão (5 MCA)"
                        ),
                        annotation_position="top left"
                    )

                    fig.add_hline(
                        y=15,
                        line_dash="dash",
                        line_color=COR_ALTA_PRESSAO,
                        annotation_text=(
                            "Limite: "
                            "Alta Pressão (15 MCA)"
                        ),
                        annotation_position="top left"
                    )

                    fig.add_hline(
                        y=0,
                        line_dash="solid",
                        line_color=COR_SEM_PRESSAO,
                        annotation_text=(
                            "Sem Pressão (0 MCA)"
                        ),
                        annotation_position="bottom left"
                    )

                    fig.update_traces(
                        line_color="#0284c7",
                        line_width=3,
                        marker_size=8
                    )

                    fig.update_layout(
                        xaxis_title="Data",
                        yaxis_title="Pressão (MCA)",
                        hovermode="x unified"
                    )

                    st.plotly_chart(
                        fig,
                        use_container_width=True
                    )

                else:

                    st.info(
                        f"Nenhum registro encontrado "
                        f"para o bairro "
                        f"**{bairro_analise}** "
                        f"no período selecionado."
                    )

            else:

                st.warning(
                    "Não há dados históricos suficientes "
                    "para este bairro."
                )

    else:

        st.info(
            "👆 Selecione um **Bairro** acima para "
            "carregar a análise de tendência temporal."
        )

else:

    st.info(
        "Aguardando dados para gerar "
        "o gráfico de tendência."
    )
