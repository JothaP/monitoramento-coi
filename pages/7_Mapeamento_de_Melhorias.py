import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
import simplekml
from datetime import datetime, date, time
from uuid import uuid4
from typing import Optional
import re
import html
import io
import math


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Mapeamento de Melhorias - COI",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

        [data-testid="stSidebarNav"] {
            display: none;
        }

        section[data-testid="stSidebar"] > div {
            padding-top: 1rem;
        }

        .bloco-titulo {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .linha-cabecalho {
            background: rgba(128, 128, 128, 0.10);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 5px;
            font-size: 12px;
            font-weight: 700;
        }

        .campo-lista {
            font-size: 13px;
            line-height: 1.25;
        }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid rgba(128,128,128,0.30);
        }

        .badge-neutro {
            background: rgba(128,128,128,0.10);
        }

        .badge-sim {
            background: rgba(0, 180, 80, 0.12);
        }

        .badge-nao {
            background: rgba(220, 60, 60, 0.12);
        }

        .resumo-popup {
            padding: 8px 0;
        }

        .resumo-popup strong {
            font-weight: 700;
        }

        .os-box {
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
        }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

from auth import verificar_autenticacao


verificar_autenticacao()


if not st.session_state.get("autenticado"):
    st.warning("⚠️ Usuário não autenticado.")

    if st.button("Voltar para o menu principal"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# CONSTANTES
# ============================================================

LAT_BASE = -5.0892
LON_BASE = -42.8019


# IMPORTANTE:
# Esta é uma planilha DIFERENTE da utilizada pelos demais módulos.
# O ID deve ser cadastrado nos secrets.
SPREADSHEET_ID = st.secrets.get(
    "MAPEAMENTO_MELHORIAS_SPREADSHEET_ID",
    "",
)


REGISTRO_COLUNAS = [
    "ID",
    "Matrícula",
    "Endereço",
    "Bairro",
    "Latitude",
    "Longitude",
    "Parecer",
    "Mapeamento executado? (link)",
    "Tratativa 1",
    "Executado?",
    "Retorno",
    "Tratativa 02",
    "Executado?2",
    "Retorno 02",
    "Grau de Impacto",
    "Resolvido",
]


HISTORICO_COLUNAS = [
    "ID",
    "Matrícula",
    "N. O.S",
    "Data de Abertura",
    "Pressão",
    "Pontual",
]


# ============================================================
# ESTADO DA INTERFACE
# ============================================================

ESTADOS_PADRAO = {
    "pagina_melhorias": 1,
    "dialogo_melhorias": None,
    "dialogo_matricula": None,
    "dialogo_id": None,
    "dialogo_os_id": None,
    "dialogo_os_matricula": None,
    "tipo_exclusao": None,
    "id_exclusao": None,
    "matricula_exclusao": None,
    "modo_escuro_melhorias": False,
}


for chave, valor in ESTADOS_PADRAO.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# ============================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================

def gerar_id():
    return uuid4().hex[:12].upper()


def texto(valor) -> str:
    if valor is None:
        return ""

    if isinstance(valor, float) and math.isnan(valor):
        return ""

    return str(valor).strip()


def normalizar_texto(valor) -> str:
    import unicodedata

    valor = texto(valor).upper()

    valor = unicodedata.normalize(
        "NFKD",
        valor,
    ).encode(
        "ASCII",
        "ignore",
    ).decode(
        "ASCII"
    )

    return valor


def valor_float(valor) -> Optional[float]:
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
    except Exception:
        return None


def coordenada_valida(lat, lon):
    lat = valor_float(lat)
    lon = valor_float(lon)

    if lat is None or lon is None:
        return False

    if lat < -90 or lat > 90:
        return False

    if lon < -180 or lon > 180:
        return False

    return True


def formatar_float(valor, casas=2):
    valor = valor_float(valor)

    if valor is None:
        return ""

    return f"{valor:.{casas}f}".replace(".", ",")


def formatar_data_hora(valor):
    if valor is None or texto(valor) == "":
        return ""

    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%d/%m/%Y %H:%M")

    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")

    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")

    valor = texto(valor)

    formatos = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]

    for formato in formatos:
        try:
            dt = datetime.strptime(
                valor,
                formato,
            )

            return dt.strftime(
                "%d/%m/%Y %H:%M"
            )

        except Exception:
            continue

    try:
        dt = pd.to_datetime(
            valor,
            dayfirst=True,
            errors="coerce",
        )

        if not pd.isna(dt):
            return dt.strftime(
                "%d/%m/%Y %H:%M"
            )

    except Exception:
        pass

    return valor


def converter_data_hora(valor):
    if valor is None:
        return pd.NaT

    if isinstance(valor, datetime):
        return valor

    try:
        return pd.to_datetime(
            valor,
            dayfirst=True,
            errors="coerce",
        )

    except Exception:
        return pd.NaT


def validar_os(numero_os):
    """
    Formato esperado:
    12345/2026-1

    Mantém o ano com 4 dígitos e permite um ou mais
    dígitos no último bloco.
    """

    numero_os = texto(numero_os)

    if not numero_os:
        return False

    padrao = r"^\d{5}/\d{4}-\d+$"

    return bool(
        re.fullmatch(
            padrao,
            numero_os,
        )
    )


def valor_badge(valor):
    valor_normalizado = normalizar_texto(valor)

    if valor_normalizado == "SIM":
        return "badge badge-sim"

    if valor_normalizado == "NAO":
        return "badge badge-nao"

    return "badge badge-neutro"


def limpar_filtros_paginacao():
    st.session_state.pagina_melhorias = 1


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource
def conectar_google_sheets(spreadsheet_id):
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

    return gc.open_by_key(
        spreadsheet_id
    )


def obter_worksheet(spreadsheet, nome, colunas):
    try:
        worksheet = spreadsheet.worksheet(nome)

    except gspread.WorksheetNotFound:

        worksheet = spreadsheet.add_worksheet(
            title=nome,
            rows=1000,
            cols=max(len(colunas), 20),
        )

        worksheet.append_row(
            colunas,
            value_input_option="USER_ENTERED",
        )

        return worksheet

    valores = worksheet.get_all_values()

    if not valores:
        worksheet.append_row(
            colunas,
            value_input_option="USER_ENTERED",
        )

        return worksheet

    cabecalho = [
        texto(x)
        for x in valores[0]
    ]

    if cabecalho != colunas:
        st.error(
            f"A aba **{nome}** possui cabeçalho diferente do esperado."
        )

        st.code(
            " | ".join(colunas)
        )

        st.stop()

    return worksheet


def obter_planilhas():
    if not SPREADSHEET_ID:
        st.error(
            "❌ O ID da planilha do Mapeamento de Melhorias não foi configurado."
        )

        st.info(
            "Adicione `MAPEAMENTO_MELHORIAS_SPREADSHEET_ID` "
            "aos secrets da aplicação."
        )

        st.stop()

    try:
        spreadsheet = conectar_google_sheets(
            SPREADSHEET_ID
        )

        ws_registro = obter_worksheet(
            spreadsheet,
            "Registro",
            REGISTRO_COLUNAS,
        )

        ws_historico = obter_worksheet(
            spreadsheet,
            "Historico",
            HISTORICO_COLUNAS,
        )

        return (
            spreadsheet,
            ws_registro,
            ws_historico,
        )

    except Exception as erro:
        st.error(
            "❌ Não foi possível acessar a planilha "
            "**Mapeamento de Melhorias**."
        )

        st.exception(erro)

        st.stop()


# ============================================================
# LEITURA DOS DADOS
# ============================================================

def carregar_worksheet(worksheet, colunas):
    valores = worksheet.get_all_values()

    if not valores:
        return pd.DataFrame(
            columns=colunas
        )

    cabecalho = valores[0]
    dados = valores[1:]

    if not dados:
        return pd.DataFrame(
            columns=colunas
        )

    quantidade = len(cabecalho)

    linhas = []

    for linha in dados:
        linha = list(linha)

        if len(linha) < quantidade:
            linha.extend(
                [""] * (
                    quantidade - len(linha)
                )
            )

        linhas.append(
            linha[:quantidade]
        )

    df = pd.DataFrame(
        linhas,
        columns=cabecalho,
    )

    for coluna in colunas:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[colunas]


def carregar_dados(ws_registro, ws_historico):
    df_registro = carregar_worksheet(
        ws_registro,
        REGISTRO_COLUNAS,
    )

    df_historico = carregar_worksheet(
        ws_historico,
        HISTORICO_COLUNAS,
    )

    if not df_registro.empty:
        df_registro["Latitude"] = (
            df_registro["Latitude"]
            .apply(valor_float)
        )

        df_registro["Longitude"] = (
            df_registro["Longitude"]
            .apply(valor_float)
        )

    if not df_historico.empty:
        df_historico["Pressão"] = (
            df_historico["Pressão"]
            .apply(valor_float)
        )

        df_historico["_DataObj"] = (
            df_historico["Data de Abertura"]
            .apply(converter_data_hora)
        )

    return (
        df_registro,
        df_historico,
    )


# ============================================================
# OPERAÇÕES DE GOOGLE SHEETS
# ============================================================

def encontrar_linha_por_id(worksheet, registro_id):
    try:
        celula = worksheet.find(
            str(registro_id)
        )

        return celula.row

    except Exception:
        return None


def adicionar_linha(worksheet, dados):
    worksheet.append_row(
        dados,
        value_input_option="USER_ENTERED",
    )


def atualizar_linha(
    worksheet,
    numero_linha,
    dados,
):
    ultima_coluna = (
        chr(
            ord("A") + len(dados) - 1
        )
    )

    worksheet.update(
        f"A{numero_linha}:{ultima_coluna}{numero_linha}",
        [dados],
        value_input_option="USER_ENTERED",
    )


def excluir_linha(
    worksheet,
    numero_linha,
):
    worksheet.delete_rows(
        numero_linha
    )


# ============================================================
# HISTÓRICO / RELACIONAMENTOS
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
        == texto(matricula)
    ].copy()


def quantidade_os(
    df_historico,
    matricula,
):
    return len(
        historico_da_matricula(
            df_historico,
            matricula,
        )
    )


def ultima_os(
    df_historico,
    matricula,
):
    df = historico_da_matricula(
        df_historico,
        matricula,
    )

    if df.empty:
        return pd.NaT

    df = df.sort_values(
        "_DataObj",
        ascending=False,
        na_position="last",
    )

    return df.iloc[0]["_DataObj"]


def tempo_medio_reclamacao(
    df_historico,
    matricula,
):
    df = historico_da_matricula(
        df_historico,
        matricula,
    )

    if len(df) < 2:
        return None

    datas = (
        pd.to_datetime(
            df["_DataObj"],
            errors="coerce",
        )
        .dropna()
        .dt.normalize()
        .sort_values()
    )

    if len(datas) < 2:
        return None

    diferencas = (
        datas.diff()
        .dropna()
        .dt.days
    )

    if diferencas.empty:
        return 0.0

    return float(
        diferencas.mean()
    )


def media_pressao(
    df_historico,
    matricula,
):
    df = historico_da_matricula(
        df_historico,
        matricula,
    )

    if df.empty:
        return None

    valores = pd.to_numeric(
        df["Pressão"],
        errors="coerce",
    ).dropna()

    if valores.empty:
        return None

    return float(
        valores.mean()
    )


# ============================================================
# FILTROS
# ============================================================

def obter_periodo_padrao(df_historico):
    if df_historico.empty:
        hoje = date.today()
        return hoje, hoje

    datas = pd.to_datetime(
        df_historico["_DataObj"],
        errors="coerce",
    ).dropna()

    if datas.empty:
        hoje = date.today()
        return hoje, hoje

    return (
        datas.min().date(),
        datas.max().date(),
    )


def aplicar_filtros(
    df_registro,
    df_historico,
    data_inicial,
    data_final,
    bairro,
    matricula,
    grau_impacto,
    resolvido,
    executado,
    busca,
):
    hist = df_historico.copy()
    reg = df_registro.copy()

    # --------------------------------------------------------
    # FILTRO DE DATA
    # --------------------------------------------------------

    if not hist.empty:
        datas = pd.to_datetime(
            hist["_DataObj"],
            errors="coerce",
        )

        hist = hist[
            datas.dt.date.between(
                data_inicial,
                data_final,
            )
        ]

    # Matrículas que possuem O.S. dentro do período.
    matriculas_periodo = set(
        hist["Matrícula"]
        .astype(str)
        .str.strip()
    ) if not hist.empty else set()

    reg = reg[
        reg["Matrícula"]
        .astype(str)
        .str.strip()
        .isin(matriculas_periodo)
    ].copy()

    # --------------------------------------------------------
    # BAIRRO
    # --------------------------------------------------------

    if bairro != "Todos":
        reg = reg[
            reg["Bairro"]
            .astype(str)
            .str.strip()
            == bairro
        ]

    # --------------------------------------------------------
    # MATRÍCULA
    # --------------------------------------------------------

    if matricula != "Todas":
        reg = reg[
            reg["Matrícula"]
            .astype(str)
            .str.strip()
            == matricula
        ]

    # --------------------------------------------------------
    # GRAU DE IMPACTO
    # --------------------------------------------------------

    if grau_impacto != "Todos":
        reg = reg[
            reg["Grau de Impacto"]
            .astype(str)
            .str.strip()
            == grau_impacto
        ]

    # --------------------------------------------------------
    # RESOLVIDO
    # --------------------------------------------------------

    if resolvido != "Todos":
        reg = reg[
            reg["Resolvido"]
            .astype(str)
            .str.strip()
            == resolvido
        ]

    # --------------------------------------------------------
    # EXECUTADO
    #
    # O filtro considera os dois campos:
    # Executado? e Executado?2
    # --------------------------------------------------------

    if executado != "Todos":
        mask_exec = (
            reg["Executado?"]
            .astype(str)
            .str.strip()
            == executado
        ) | (
            reg["Executado?2"]
            .astype(str)
            .str.strip()
            == executado
        )

        reg = reg[
            mask_exec
        ]

    # --------------------------------------------------------
    # BUSCA RÁPIDA
    #
    # Matrícula, endereço, bairro e O.S.
    # --------------------------------------------------------

    busca = texto(busca)

    if busca:
        termo = normalizar_texto(
            busca
        )

        matriculas_busca_os = set()

        if not hist.empty:
            for _, linha in hist.iterrows():
                if termo in normalizar_texto(
                    linha["N. O.S"]
                ):
                    matriculas_busca_os.add(
                        texto(linha["Matrícula"])
                    )

        def corresponde(linha):
            campos = [
                linha["Matrícula"],
                linha["Endereço"],
                linha["Bairro"],
            ]

            if any(
                termo in normalizar_texto(campo)
                for campo in campos
            ):
                return True

            if texto(
                linha["Matrícula"]
            ) in matriculas_busca_os:
                return True

            return False

        reg = reg[
            reg.apply(
                corresponde,
                axis=1,
            )
        ]

    matriculas_finais = set(
        reg["Matrícula"]
        .astype(str)
        .str.strip()
    )

    hist = hist[
        hist["Matrícula"]
        .astype(str)
        .str.strip()
        .isin(matriculas_finais)
    ].copy()

    return (
        reg,
        hist,
    )


# ============================================================
# RESUMO PARA LISTA
# ============================================================

def criar_resumo_lista(
    df_registro,
    df_historico,
):
    if df_registro.empty:
        return pd.DataFrame()

    linhas = []

    for _, registro in df_registro.iterrows():

        matricula = texto(
            registro["Matrícula"]
        )

        hist = historico_da_matricula(
            df_historico,
            matricula,
        )

        ultima_data = (
            hist["_DataObj"].max()
            if not hist.empty
            else pd.NaT
        )

        linhas.append(
            {
                "ID": texto(
                    registro["ID"]
                ),
                "Matrícula": matricula,
                "Endereço": texto(
                    registro["Endereço"]
                ),
                "Bairro": texto(
                    registro["Bairro"]
                ),
                "Grau de Impacto": texto(
                    registro["Grau de Impacto"]
                ),
                "Resolvido": texto(
                    registro["Resolvido"]
                ),
                "Qtd. O.S.": len(hist),
                "Última O.S.": ultima_data,
            }
        )

    df = pd.DataFrame(linhas)

    if df.empty:
        return df

    df = df.sort_values(
        by=[
            "Qtd. O.S.",
            "Última O.S.",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )

    return df


# ============================================================
# EXPORTAÇÃO
# ============================================================

def gerar_excel(
    df_registro,
    df_historico,
    nome_resumo="Registro",
):
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        registro = df_registro.copy()
        historico = df_historico.copy()

        if "_DataObj" in historico.columns:
            historico = historico.drop(
                columns=["_DataObj"]
            )

        registro.to_excel(
            writer,
            index=False,
            sheet_name=nome_resumo,
        )

        historico.to_excel(
            writer,
            index=False,
            sheet_name="Historico",
        )

    buffer.seek(0)

    return buffer.getvalue()


def gerar_excel_cliente(
    registro,
    historico,
):
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        resumo = pd.DataFrame(
            [
                {
                    "ID": texto(
                        registro["ID"]
                    ),
                    "Matrícula": texto(
                        registro["Matrícula"]
                    ),
                    "Endereço": texto(
                        registro["Endereço"]
                    ),
                    "Bairro": texto(
                        registro["Bairro"]
                    ),
                    "Latitude": registro["Latitude"],
                    "Longitude": registro["Longitude"],
                    "Parecer": texto(
                        registro["Parecer"]
                    ),
                    "Mapeamento executado? (link)": texto(
                        registro[
                            "Mapeamento executado? (link)"
                        ]
                    ),
                    "Tratativa 1": texto(
                        registro["Tratativa 1"]
                    ),
                    "Executado?": texto(
                        registro["Executado?"]
                    ),
                    "Retorno": texto(
                        registro["Retorno"]
                    ),
                    "Tratativa 02": texto(
                        registro["Tratativa 02"]
                    ),
                    "Executado?2": texto(
                        registro["Executado?2"]
                    ),
                    "Retorno 02": texto(
                        registro["Retorno 02"]
                    ),
                    "Grau de Impacto": texto(
                        registro["Grau de Impacto"]
                    ),
                    "Resolvido": texto(
                        registro["Resolvido"]
                    ),
                }
            ]
        )

        hist_export = historico.copy()

        if "_DataObj" in hist_export.columns:
            hist_export = hist_export.drop(
                columns=["_DataObj"]
            )

        resumo.to_excel(
            writer,
            index=False,
            sheet_name="Resumo",
        )

        hist_export.to_excel(
            writer,
            index=False,
            sheet_name="Histórico",
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# MAPA
# ============================================================

def criar_mapa(
    df_registro,
    df_historico,
    tipo_mapa,
):
    mapa = folium.Map(
        location=[
            LAT_BASE,
            LON_BASE,
        ],
        zoom_start=12,
        control_scale=True,
    )

    if tipo_mapa == "🛰️ Satélite":
        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/"
                "ArcGIS/rest/services/"
                "World_Imagery/"
                "MapServer/tile/{z}/{y}/{x}"
            ),
            attr="Esri",
            name="Satélite",
        ).add_to(mapa)

    elif tipo_mapa == "⛰️ Terreno":
        folium.TileLayer(
            tiles=(
                "https://{s}.tile.opentopomap.org/"
                "{z}/{x}/{y}.png"
            ),
            attr="OpenTopoMap",
            name="Terreno",
        ).add_to(mapa)

    else:
        folium.TileLayer(
            tiles=(
                "https://{s}.tile.openstreetmap.org/"
                "{z}/{x}/{y}.png"
            ),
            attr="OpenStreetMap",
            name="Mapa",
        ).add_to(mapa)

    if df_registro.empty:
        folium.LayerControl().add_to(
            mapa
        )

        return mapa

    pontos = []

    for _, registro in df_registro.iterrows():

        lat = valor_float(
            registro["Latitude"]
        )

        lon = valor_float(
            registro["Longitude"]
        )

        if not coordenada_valida(
            lat,
            lon,
        ):
            continue

        matricula = texto(
            registro["Matrícula"]
        )

        hist = historico_da_matricula(
            df_historico,
            matricula,
        )

        qtd = len(hist)

        ultima = (
            hist["_DataObj"].max()
            if not hist.empty
            else pd.NaT
        )

        ultima_formatada = (
            ultima.strftime(
                "%d/%m/%Y %H:%M"
            )
            if not pd.isna(ultima)
            else "Sem registro"
        )

        resolvido = texto(
            registro["Resolvido"]
        )

        resolvido_normalizado = normalizar_texto(
            resolvido
        )

        if resolvido_normalizado == "SIM":
            cor = "green"
        elif resolvido_normalizado == "NAO":
            cor = "red"
        else:
            cor = "blue"

        link_mapeamento = texto(
            registro[
                "Mapeamento executado? (link)"
            ]
        )

        link_html = ""

        if link_mapeamento:
            link_seguro = html.escape(
                link_mapeamento,
                quote=True,
            )

            link_html = (
                f'<br><a href="{link_seguro}" '
                'target="_blank">Abrir mapeamento</a>'
            )

        popup_html = f"""
        <div style="font-family:Arial; font-size:13px; width:280px;">
            <h4 style="margin-bottom:8px;">
                🛠️ {html.escape(matricula)}
            </h4>

            <b>Endereço:</b>
            {html.escape(texto(registro["Endereço"]))}<br>

            <b>Bairro:</b>
            {html.escape(texto(registro["Bairro"]))}<br>

            <b>Grau de Impacto:</b>
            {html.escape(texto(registro["Grau de Impacto"]))}<br>

            <b>Resolvido:</b>
            {html.escape(resolvido)}<br>

            <b>Quantidade de O.S.:</b>
            {qtd}<br>

            <b>O.S. mais recente:</b>
            {ultima_formatada}<br>

            <hr>

            <b>Parecer:</b><br>
            {html.escape(texto(registro["Parecer"]))}

            {link_html}

            <br><br>

            <b>Tratativa 1:</b><br>
            {html.escape(texto(registro["Tratativa 1"]))}

            <br><br>

            <b>Tratativa 02:</b><br>
            {html.escape(texto(registro["Tratativa 02"]))}
        </div>
        """

        popup = folium.Popup(
            popup_html,
            max_width=350,
        )

        tooltip = (
            f"{matricula} | "
            f"{texto(registro['Bairro'])}"
        )

        folium.Marker(
            location=[
                lat,
                lon,
            ],
            tooltip=tooltip,
            popup=popup,
            icon=folium.Icon(
                color=cor,
                icon="wrench",
                prefix="fa",
            ),
        ).add_to(mapa)

        pontos.append(
            (
                lat,
                lon,
            )
        )

    if pontos:
        lat_media = sum(
            ponto[0]
            for ponto in pontos
        ) / len(pontos)

        lon_media = sum(
            ponto[1]
            for ponto in pontos
        ) / len(pontos)

        mapa.location = [
            lat_media,
            lon_media,
        ]

        if len(pontos) == 1:
            mapa.zoom_start = 14
        elif len(pontos) > 1:
            mapa.fit_bounds(
                pontos,
                padding=(
                    20,
                    20,
                ),
            )

    folium.LayerControl().add_to(
        mapa
    )

    return mapa


# ============================================================
# SALVAR NOVO REGISTRO
# ============================================================

def salvar_novo_registro(
    ws_registro,
    ws_historico,
    dados_registro,
    dados_os=None,
):
    matricula = texto(
        dados_registro["Matrícula"]
    )

    if not matricula:
        return False, "Informe a matrícula."

    if not coordenada_valida(
        dados_registro["Latitude"],
        dados_registro["Longitude"],
    ):
        return (
            False,
            "Latitude e Longitude são obrigatórias e devem ser válidas.",
        )

    # Verifica matrícula já cadastrada.
    try:
        valores = ws_registro.get_all_values()

        if valores:
            cabecalho = valores[0]

            if "Matrícula" in cabecalho:
                indice = cabecalho.index(
                    "Matrícula"
                )

                for linha in valores[1:]:
                    if len(linha) > indice:
                        if texto(
                            linha[indice]
                        ) == matricula:
                            return (
                                False,
                                "Esta matrícula já possui cadastro.",
                            )

    except Exception as erro:
        return (
            False,
            f"Erro ao verificar matrícula: {erro}",
        )

    # Se não existe histórico para a matrícula,
    # uma O.S. inicial é obrigatória.
    if dados_os is None:
        return (
            False,
            "A matrícula precisa possuir pelo menos uma O.S.",
        )

    numero_os = texto(
        dados_os["N. O.S"]
    )

    if not validar_os(
        numero_os
    ):
        return (
            False,
            "N. O.S inválida. Use o padrão 12345/2026-1.",
        )

    data_abertura = (
        dados_os["Data de Abertura"]
    )

    if not data_abertura:
        return (
            False,
            "Informe a Data de Abertura da O.S.",
        )

    # Evita O.S. duplicada.
    try:
        valores_hist = ws_historico.get_all_values()

        if valores_hist:
            cab_hist = valores_hist[0]

            idx_mat = cab_hist.index(
                "Matrícula"
            )

            idx_os = cab_hist.index(
                "N. O.S"
            )

            for linha in valores_hist[1:]:
                if (
                    len(linha) > idx_os
                    and texto(linha[idx_mat])
                    == matricula
                    and texto(linha[idx_os])
                    == numero_os
                ):
                    return (
                        False,
                        "Esta O.S. já está cadastrada para esta matrícula.",
                    )

    except Exception:
        pass

    id_registro = gerar_id()

    linha_registro = [
        id_registro,
        matricula,
        texto(dados_registro["Endereço"]),
        texto(dados_registro["Bairro"]),
        valor_float(dados_registro["Latitude"]),
        valor_float(dados_registro["Longitude"]),
        texto(dados_registro["Parecer"]),
        texto(
            dados_registro[
                "Mapeamento executado? (link)"
            ]
        ),
        texto(dados_registro["Tratativa 1"]),
        texto(dados_registro["Executado?"]),
        texto(dados_registro["Retorno"]),
        texto(dados_registro["Tratativa 02"]),
        texto(dados_registro["Executado?2"]),
        texto(dados_registro["Retorno 02"]),
        texto(dados_registro["Grau de Impacto"]),
        texto(dados_registro["Resolvido"]),
    ]

    adicionar_linha(
        ws_registro,
        linha_registro,
    )

    linha_os = [
        gerar_id(),
        matricula,
        numero_os,
        formatar_data_hora(
            data_abertura
        ),
        valor_float(
            dados_os["Pressão"]
        ),
        texto(
            dados_os["Pontual"]
        ),
    ]

    adicionar_linha(
        ws_historico,
        linha_os,
    )

    return (
        True,
        "Registro cadastrado com sucesso.",
    )


# ============================================================
# ATUALIZAR REGISTRO
# ============================================================

def atualizar_registro(
    ws_registro,
    ws_historico,
    registro_id,
    dados,
):
    linha = encontrar_linha_por_id(
        ws_registro,
        registro_id,
    )

    if linha is None:
        return (
            False,
            "Registro não encontrado.",
        )

    nova_matricula = texto(
        dados["Matrícula"]
    )

    if not nova_matricula:
        return (
            False,
            "Informe a matrícula.",
        )

    if not coordenada_valida(
        dados["Latitude"],
        dados["Longitude"],
    ):
        return (
            False,
            "Latitude e Longitude são obrigatórias e válidas.",
        )

    # Matrícula atual
    valores = ws_registro.get_all_values()

    cabecalho = valores[0]

    indice_id = cabecalho.index("ID")
    indice_matricula = cabecalho.index(
        "Matrícula"
    )

    matricula_antiga = ""

    for registro in valores[1:]:
        if len(registro) > indice_id:
            if texto(
                registro[indice_id]
            ) == texto(registro_id):

                if len(registro) > indice_matricula:
                    matricula_antiga = texto(
                        registro[indice_matricula]
                    )

                break

    # Impede colisão com outra matrícula.
    if nova_matricula != matricula_antiga:
        for registro in valores[1:]:
            if len(registro) > indice_id:
                if (
                    texto(registro[indice_matricula])
                    == nova_matricula
                    and texto(registro[indice_id])
                    != texto(registro_id)
                ):
                    return (
                        False,
                        "A nova matrícula já possui outro cadastro.",
                    )

    linha_registro = [
        texto(registro_id),
        nova_matricula,
        texto(dados["Endereço"]),
        texto(dados["Bairro"]),
        valor_float(dados["Latitude"]),
        valor_float(dados["Longitude"]),
        texto(dados["Parecer"]),
        texto(
            dados[
                "Mapeamento executado? (link)"
            ]
        ),
        texto(dados["Tratativa 1"]),
        texto(dados["Executado?"]),
        texto(dados["Retorno"]),
        texto(dados["Tratativa 02"]),
        texto(dados["Executado?2"]),
        texto(dados["Retorno 02"]),
        texto(dados["Grau de Impacto"]),
        texto(dados["Resolvido"]),
    ]

    atualizar_linha(
        ws_registro,
        linha,
        linha_registro,
    )

    # Se a matrícula foi alterada, mantém o histórico vinculado.
    if (
        matricula_antiga
        and nova_matricula != matricula_antiga
    ):
        valores_hist = ws_historico.get_all_values()

        if valores_hist:
            cab_hist = valores_hist[0]

            idx_mat = cab_hist.index(
                "Matrícula"
            )

            for numero_linha, registro_hist in enumerate(
                valores_hist[1:],
                start=2,
            ):
                if len(registro_hist) > idx_mat:
                    if texto(
                        registro_hist[idx_mat]
                    ) == matricula_antiga:

                        ws_historico.update(
                            f"B{numero_linha}",
                            [[nova_matricula]],
                            value_input_option="USER_ENTERED",
                        )

    return (
        True,
        "Registro atualizado com sucesso.",
    )


# ============================================================
# EXCLUIR REGISTRO
# ============================================================

def excluir_registro(
    ws_registro,
    registro_id,
):
    linha = encontrar_linha_por_id(
        ws_registro,
        registro_id,
    )

    if linha is None:
        return (
            False,
            "Registro não encontrado.",
        )

    excluir_linha(
        ws_registro,
        linha,
    )

    # IMPORTANTE:
    # O histórico NÃO é excluído.
    return (
        True,
        "Cadastro excluído. O histórico foi preservado.",
    )


# ============================================================
# O.S. — ADICIONAR
# ============================================================

def adicionar_os(
    ws_historico,
    matricula,
    numero_os,
    data_abertura,
    pressao,
    pontual,
):
    matricula = texto(
        matricula
    )

    numero_os = texto(
        numero_os
    )

    if not matricula:
        return (
            False,
            "Matrícula não informada.",
        )

    if not validar_os(
        numero_os
    ):
        return (
            False,
            "N. O.S inválida. Use o padrão 12345/2026-1.",
        )

    if not data_abertura:
        return (
            False,
            "Informe a Data de Abertura.",
        )

    if texto(pontual) not in [
        "SIM",
        "NÃO",
    ]:
        return (
            False,
            "Informe se a O.S. é pontual.",
        )

    # Verifica duplicidade por matrícula + O.S.
    valores = ws_historico.get_all_values()

    if valores:
        cabecalho = valores[0]

        idx_mat = cabecalho.index(
            "Matrícula"
        )

        idx_os = cabecalho.index(
            "N. O.S"
        )

        for registro in valores[1:]:
            if (
                len(registro) > idx_os
                and texto(registro[idx_mat])
                == matricula
                and texto(registro[idx_os])
                == numero_os
            ):
                return (
                    False,
                    "Esta O.S. já existe para esta matrícula.",
                )

    linha = [
        gerar_id(),
        matricula,
        numero_os,
        formatar_data_hora(
            data_abertura
        ),
        valor_float(pressao),
        texto(pontual),
    ]

    adicionar_linha(
        ws_historico,
        linha,
    )

    return (
        True,
        "O.S. adicionada com sucesso.",
    )


# ============================================================
# O.S. — ATUALIZAR
# ============================================================

def atualizar_os(
    ws_historico,
    os_id,
    matricula,
    numero_os,
    data_abertura,
    pressao,
    pontual,
):
    linha = encontrar_linha_por_id(
        ws_historico,
        os_id,
    )

    if linha is None:
        return (
            False,
            "O.S. não encontrada.",
        )

    if not validar_os(
        numero_os
    ):
        return (
            False,
            "N. O.S inválida. Use o padrão 12345/2026-1.",
        )

    if not data_abertura:
        return (
            False,
            "Informe a Data de Abertura.",
        )

    if pontual not in [
        "SIM",
        "NÃO",
    ]:
        return (
            False,
            "Informe se a O.S. é pontual.",
        )

    valores = ws_historico.get_all_values()

    cabecalho = valores[0]

    idx_id = cabecalho.index("ID")
    idx_mat = cabecalho.index(
        "Matrícula"
    )
    idx_os = cabecalho.index(
        "N. O.S"
    )

    # Não permite duplicar outra O.S.
    for registro in valores[1:]:
        if len(registro) <= idx_os:
            continue

        if (
            texto(registro[idx_mat])
            == texto(matricula)
            and texto(registro[idx_os])
            == texto(numero_os)
            and texto(registro[idx_id])
            != texto(os_id)
        ):
            return (
                False,
                "Já existe outra O.S. com esse número para esta matrícula.",
            )

    dados = [
        texto(os_id),
        texto(matricula),
        texto(numero_os),
        formatar_data_hora(
            data_abertura
        ),
        valor_float(pressao),
        texto(pontual),
    ]

    atualizar_linha(
        ws_historico,
        linha,
        dados,
    )

    return (
        True,
        "O.S. atualizada com sucesso.",
    )


# ============================================================
# O.S. — EXCLUIR
# ============================================================

def excluir_os(
    ws_historico,
    os_id,
    matricula,
):
    valores = ws_historico.get_all_values()

    if not valores:
        return (
            False,
            "Histórico não encontrado.",
        )

    cabecalho = valores[0]

    idx_id = cabecalho.index(
        "ID"
    )

    idx_mat = cabecalho.index(
        "Matrícula"
    )

    indices_matricula = []

    linha_encontrada = None

    for numero_linha, registro in enumerate(
        valores[1:],
        start=2,
    ):
        if len(registro) <= idx_mat:
            continue

        if texto(
            registro[idx_mat]
        ) == texto(matricula):

            indices_matricula.append(
                numero_linha
            )

        if len(registro) > idx_id:
            if texto(
                registro[idx_id]
            ) == texto(os_id):

                linha_encontrada = (
                    numero_linha
                )

    if linha_encontrada is None:
        return (
            False,
            "O.S. não encontrada.",
        )

    # Não deixa a matrícula ficar sem O.S.
    if len(indices_matricula) <= 1:
        return (
            False,
            "Não é possível excluir a única O.S. da matrícula. "
            "Exclua o cadastro da matrícula se necessário.",
        )

    excluir_linha(
        ws_historico,
        linha_encontrada,
    )

    return (
        True,
        "O.S. excluída com sucesso.",
    )


# ============================================================
# DIÁLOGO — NOVO REGISTRO
# ============================================================

@st.dialog(
    "＋ Adicionar Registro",
    width="large",
)
def dialogo_novo_registro(
    ws_registro,
    ws_historico,
    df_historico,
):

    st.markdown(
        "### Identificação da matrícula"
    )

    col1, col2 = st.columns(2)

    with col1:
        matricula = st.text_input(
            "Matrícula *",
            key="novo_matricula",
        )

    with col2:
        bairro = st.text_input(
            "Bairro",
            key="novo_bairro",
        )

    endereco = st.text_input(
        "Endereço",
        key="novo_endereco",
    )

    st.markdown(
        "### 📍 Localização"
    )

    col1, col2 = st.columns(2)

    with col1:
        latitude = st.text_input(
            "Latitude *",
            placeholder="-5.089200",
            key="novo_latitude",
        )

    with col2:
        longitude = st.text_input(
            "Longitude *",
            placeholder="-42.801900",
            key="novo_longitude",
        )

    st.markdown(
        "### 🛠️ Mapeamento da melhoria"
    )

    parecer = st.text_area(
        "Parecer",
        key="novo_parecer",
        height=90,
    )

    link_mapeamento = st.text_input(
        "Mapeamento executado? (link)",
        placeholder="https://...",
        key="novo_link_mapeamento",
    )

    col1, col2 = st.columns(2)

    with col1:
        grau_impacto = st.text_input(
            "Grau de Impacto",
            key="novo_grau_impacto",
        )

    with col2:
        resolvido = st.text_input(
            "Resolvido",
            key="novo_resolvido",
        )

    st.markdown(
        "### 🔧 Tratativa 1"
    )

    tratativa1 = st.text_area(
        "Tratativa 1",
        key="novo_tratativa1",
        height=80,
    )

    executado1 = st.text_input(
        "Executado?",
        key="novo_executado1",
    )

    retorno1 = st.text_area(
        "Retorno",
        key="novo_retorno1",
        height=80,
    )

    st.markdown(
        "### 🔧 Tratativa 2"
    )

    tratativa2 = st.text_area(
        "Tratativa 02",
        key="novo_tratativa2",
        height=80,
    )

    executado2 = st.text_input(
        "Executado?2",
        key="novo_executado2",
    )

    retorno2 = st.text_area(
        "Retorno 02",
        key="novo_retorno2",
        height=80,
    )

    st.divider()

    st.markdown(
        "### 📋 O.S. inicial"
    )

    historico_existente = historico_da_matricula(
        df_historico,
        matricula,
    )

    if historico_existente.empty:

        st.info(
            "A matrícula precisa possuir pelo menos uma O.S. "
            "para ser cadastrada."
        )

        os_numero = st.text_input(
            "N. O.S *",
            placeholder="12345/2026-1",
            key="novo_os",
        )

        data_os = st.datetime_input(
            "Data de Abertura *",
            value=datetime.now(),
            key="novo_data_os",
        )

        col1, col2 = st.columns(2)

        with col1:
            pressao_os = st.number_input(
                "Pressão (MCA)",
                min_value=0.0,
                step=0.1,
                format="%.2f",
                key="novo_pressao_os",
            )

        with col2:
            pontual_os = st.selectbox(
                "Pontual",
                ["SIM", "NÃO"],
                key="novo_pontual_os",
            )

        dados_os = {
            "N. O.S": os_numero,
            "Data de Abertura": data_os,
            "Pressão": pressao_os,
            "Pontual": pontual_os,
        }

    else:
        st.success(
            "Esta matrícula já possui O.S. no histórico."
        )

        adicionar_nova_os = st.checkbox(
            "Adicionar uma nova O.S. neste cadastro",
            key="novo_adicionar_os_existente",
        )

        dados_os = None

        if adicionar_nova_os:

            os_numero = st.text_input(
                "N. O.S",
                placeholder="12345/2026-1",
                key="novo_os_existente",
            )

            data_os = st.datetime_input(
                "Data de Abertura",
                value=datetime.now(),
                key="novo_data_os_existente",
            )

            col1, col2 = st.columns(2)

            with col1:
                pressao_os = st.number_input(
                    "Pressão (MCA)",
                    min_value=0.0,
                    step=0.1,
                    format="%.2f",
                    key="novo_pressao_os_existente",
                )

            with col2:
                pontual_os = st.selectbox(
                    "Pontual",
                    ["SIM", "NÃO"],
                    key="novo_pontual_os_existente",
                )

            dados_os = {
                "N. O.S": os_numero,
                "Data de Abertura": data_os,
                "Pressão": pressao_os,
                "Pontual": pontual_os,
            }

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        cancelar = st.button(
            "Cancelar",
            use_container_width=True,
        )

    with col2:
        salvar = st.button(
            "Salvar Registro",
            type="primary",
            use_container_width=True,
        )

    if cancelar:
        st.session_state.dialogo_melhorias = None
        st.rerun()

    if salvar:

        dados = {
            "Matrícula": matricula,
            "Endereço": endereco,
            "Bairro": bairro,
            "Latitude": latitude,
            "Longitude": longitude,
            "Parecer": parecer,
            "Mapeamento executado? (link)": link_mapeamento,
            "Tratativa 1": tratativa1,
            "Executado?": executado1,
            "Retorno": retorno1,
            "Tratativa 02": tratativa2,
            "Executado?2": executado2,
            "Retorno 02": retorno2,
            "Grau de Impacto": grau_impacto,
            "Resolvido": resolvido,
        }

        # Se já existe histórico, não é obrigatório adicionar
        # outra O.S.
        if not historico_existente.empty:
            if dados_os is None:
                # cria apenas o cadastro
                id_registro = gerar_id()

                linha = [
                    id_registro,
                    matricula,
                    endereco,
                    bairro,
                    valor_float(latitude),
                    valor_float(longitude),
                    parecer,
                    link_mapeamento,
                    tratativa1,
                    executado1,
                    retorno1,
                    tratativa2,
                    executado2,
                    retorno2,
                    grau_impacto,
                    resolvido,
                ]

                # Verifica matrícula duplicada
                df_atual = carregar_worksheet(
                    ws_registro,
                    REGISTRO_COLUNAS,
                )

                if (
                    not df_atual.empty
                    and matricula in
                    df_atual["Matrícula"]
                    .astype(str)
                    .str.strip()
                    .tolist()
                ):
                    st.error(
                        "Esta matrícula já possui cadastro."
                    )
                    return

                if not coordenada_valida(
                    latitude,
                    longitude,
                ):
                    st.error(
                        "Latitude e Longitude são obrigatórias e válidas."
                    )
                    return

                adicionar_linha(
                    ws_registro,
                    linha,
                )

                st.success(
                    "Registro cadastrado com sucesso."
                )

                st.session_state.dialogo_melhorias = None
                st.rerun()

            else:
                sucesso, mensagem = adicionar_os(
                    ws_historico,
                    matricula,
                    dados_os["N. O.S"],
                    dados_os["Data de Abertura"],
                    dados_os["Pressão"],
                    dados_os["Pontual"],
                )

                if not sucesso:
                    st.error(mensagem)
                    return

                sucesso, mensagem = salvar_novo_registro(
                    ws_registro,
                    ws_historico,
                    dados,
                    None,
                )

                if not sucesso:
                    st.error(mensagem)
                    return

        else:
            sucesso, mensagem = salvar_novo_registro(
                ws_registro,
                ws_historico,
                dados,
                dados_os,
            )

            if not sucesso:
                st.error(mensagem)
                return

        st.success(
            "Registro cadastrado com sucesso."
        )

        st.session_state.dialogo_melhorias = None
        st.rerun()


# ============================================================
# DIÁLOGO — EDITAR REGISTRO
# ============================================================

@st.dialog(
    "✏️ Editar Registro",
    width="large",
)
def dialogo_editar_registro(
    ws_registro,
    ws_historico,
    df_registro,
    registro_id,
):

    encontrados = df_registro[
        df_registro["ID"]
        .astype(str)
        .str.strip()
        == texto(registro_id)
    ]

    if encontrados.empty:
        st.error(
            "Registro não encontrado."
        )
        return

    registro = encontrados.iloc[0]

    with st.form(
        f"form_editar_{registro_id}"
    ):

        st.markdown(
            "### Identificação"
        )

        col1, col2 = st.columns(2)

        with col1:
            matricula = st.text_input(
                "Matrícula *",
                value=texto(
                    registro["Matrícula"]
                ),
            )

        with col2:
            bairro = st.text_input(
                "Bairro",
                value=texto(
                    registro["Bairro"]
                ),
            )

        endereco = st.text_input(
            "Endereço",
            value=texto(
                registro["Endereço"]
            ),
        )

        st.markdown(
            "### 📍 Localização"
        )

        col1, col2 = st.columns(2)

        with col1:
            latitude = st.text_input(
                "Latitude *",
                value=texto(
                    registro["Latitude"]
                ),
            )

        with col2:
            longitude = st.text_input(
                "Longitude *",
                value=texto(
                    registro["Longitude"]
                ),
            )

        st.markdown(
            "### 🛠️ Mapeamento"
        )

        parecer = st.text_area(
            "Parecer",
            value=texto(
                registro["Parecer"]
            ),
            height=90,
        )

        link_mapeamento = st.text_input(
            "Mapeamento executado? (link)",
            value=texto(
                registro[
                    "Mapeamento executado? (link)"
                ]
            ),
        )

        col1, col2 = st.columns(2)

        with col1:
            grau_impacto = st.text_input(
                "Grau de Impacto",
                value=texto(
                    registro["Grau de Impacto"]
                ),
            )

        with col2:
            resolvido = st.text_input(
                "Resolvido",
                value=texto(
                    registro["Resolvido"]
                ),
            )

        st.markdown(
            "### 🔧 Tratativa 1"
        )

        tratativa1 = st.text_area(
            "Tratativa 1",
            value=texto(
                registro["Tratativa 1"]
            ),
            height=80,
        )

        executado1 = st.text_input(
            "Executado?",
            value=texto(
                registro["Executado?"]
            ),
        )

        retorno1 = st.text_area(
            "Retorno",
            value=texto(
                registro["Retorno"]
            ),
            height=80,
        )

        st.markdown(
            "### 🔧 Tratativa 2"
        )

        tratativa2 = st.text_area(
            "Tratativa 02",
            value=texto(
                registro["Tratativa 02"]
            ),
            height=80,
        )

        executado2 = st.text_input(
            "Executado?2",
            value=texto(
                registro["Executado?2"]
            ),
        )

        retorno2 = st.text_area(
            "Retorno 02",
            value=texto(
                registro["Retorno 02"]
            ),
            height=80,
        )

        st.divider()

        salvar = st.form_submit_button(
            "Salvar alterações",
            type="primary",
            use_container_width=True,
        )

    if salvar:

        dados = {
            "Matrícula": matricula,
            "Endereço": endereco,
            "Bairro": bairro,
            "Latitude": latitude,
            "Longitude": longitude,
            "Parecer": parecer,
            "Mapeamento executado? (link)": link_mapeamento,
            "Tratativa 1": tratativa1,
            "Executado?": executado1,
            "Retorno": retorno1,
            "Tratativa 02": tratativa2,
            "Executado?2": executado2,
            "Retorno 02": retorno2,
            "Grau de Impacto": grau_impacto,
            "Resolvido": resolvido,
        }

        sucesso, mensagem = atualizar_registro(
            ws_registro,
            ws_historico,
            registro_id,
            dados,
        )

        if sucesso:
            st.success(mensagem)
            st.session_state.dialogo_melhorias = None
            st.rerun()

        else:
            st.error(mensagem)


# ============================================================
# DIÁLOGO — MATRÍCULA
# ============================================================

@st.dialog(
    "📋 Registro da Matrícula",
    width="large",
)
def dialogo_matricula(
    df_registro,
    df_historico,
    matricula,
):

    registros = df_registro[
        df_registro["Matrícula"]
        .astype(str)
        .str.strip()
        == texto(matricula)
    ]

    historico = historico_da_matricula(
        df_historico,
        matricula,
    )

    if registros.empty:
        st.warning(
            "O cadastro principal desta matrícula não existe mais."
        )

        if not historico.empty:
            st.info(
                "O histórico permanece armazenado."
            )

            st.dataframe(
                historico[
                    [
                        "N. O.S",
                        "Data de Abertura",
                        "Pressão",
                        "Pontual",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

        return

    registro = registros.iloc[0]

    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    st.markdown(
        f"## Matrícula {texto(registro['Matrícula'])}"
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Quantidade de O.S.",
            len(historico),
        )

    with col2:
        ultima = ultima_os(
            df_historico,
            matricula,
        )

        st.metric(
            "O.S. mais recente",
            (
                ultima.strftime(
                    "%d/%m/%Y"
                )
                if not pd.isna(ultima)
                else "—"
            ),
        )

    with col3:
        pressao = media_pressao(
            df_historico,
            matricula,
        )

        st.metric(
            "Média de Pressão",
            (
                f"{pressao:.2f} MCA"
                if pressao is not None
                else "—"
            ),
        )

    with col4:
        tempo_medio = tempo_medio_reclamacao(
            df_historico,
            matricula,
        )

        st.metric(
            "Tempo Médio",
            (
                f"{tempo_medio:.1f} dias"
                if tempo_medio is not None
                else "—"
            ),
        )

    # --------------------------------------------------------
    # DADOS DO REGISTRO
    # --------------------------------------------------------

    st.divider()

    st.markdown(
        "### 🛠️ Dados do registro"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"**Endereço:** {texto(registro['Endereço'])}"
        )

        st.markdown(
            f"**Bairro:** {texto(registro['Bairro'])}"
        )

        st.markdown(
            f"**Latitude:** {texto(registro['Latitude'])}"
        )

        st.markdown(
            f"**Longitude:** {texto(registro['Longitude'])}"
        )

        st.markdown(
            f"**Grau de Impacto:** {texto(registro['Grau de Impacto'])}"
        )

        st.markdown(
            f"**Resolvido:** {texto(registro['Resolvido'])}"
        )

    with col2:
        st.markdown(
            f"**Parecer:** {texto(registro['Parecer'])}"
        )

        link = texto(
            registro[
                "Mapeamento executado? (link)"
            ]
        )

        if link:
            st.markdown(
                f"[🔗 Abrir mapeamento]({link})"
            )

    st.markdown(
        f"**Tratativa 1:** {texto(registro['Tratativa 1'])}"
    )

    st.markdown(
        f"**Executado?:** {texto(registro['Executado?'])}"
    )

    st.markdown(
        f"**Retorno:** {texto(registro['Retorno'])}"
    )

    st.markdown(
        f"**Tratativa 02:** {texto(registro['Tratativa 02'])}"
    )

    st.markdown(
        f"**Executado?2:** {texto(registro['Executado?2'])}"
    )

    st.markdown(
        f"**Retorno 02:** {texto(registro['Retorno 02'])}"
    )

    # --------------------------------------------------------
    # BOTÕES
    # --------------------------------------------------------

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(
            "＋ Adicionar Registro",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.dialogo_melhorias = "nova_os"
            st.session_state.dialogo_os_matricula = matricula
            st.rerun()

    with col2:
        if st.button(
            "✏️ Editar Registro",
            use_container_width=True,
        ):
            st.session_state.dialogo_melhorias = "editar"
            st.session_state.dialogo_id = texto(
                registro["ID"]
            )
            st.rerun()

    with col3:
        if st.button(
            "🗑️ Excluir Registro",
            use_container_width=True,
        ):
            st.session_state.tipo_exclusao = "registro"
            st.session_state.id_exclusao = texto(
                registro["ID"]
            )
            st.session_state.matricula_exclusao = matricula
            st.session_state.dialogo_melhorias = "confirmar_exclusao"
            st.rerun()

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    st.divider()

    st.markdown(
        "### 📋 Histórico de O.S."
    )

    if historico.empty:
        st.info(
            "Nenhuma O.S. encontrada."
        )

    else:

        historico = historico.sort_values(
            "_DataObj",
            ascending=False,
        )

        for _, os_registro in historico.iterrows():

            os_id = texto(
                os_registro["ID"]
            )

            with st.container(
                border=True
            ):

                c1, c2, c3, c4, c5, c6 = st.columns(
                    [
                        1.5,
                        1.8,
                        1.2,
                        1.2,
                        0.7,
                        0.7,
                    ]
                )

                with c1:
                    st.markdown(
                        f"**O.S.**  \n"
                        f"{texto(os_registro['N. O.S'])}"
                    )

                with c2:
                    data_formatada = formatar_data_hora(
                        os_registro[
                            "Data de Abertura"
                        ]
                    )

                    st.markdown(
                        f"**Abertura**  \n"
                        f"{data_formatada}"
                    )

                with c3:
                    st.markdown(
                        f"**Pressão**  \n"
                        f"{formatar_float(os_registro['Pressão'])} MCA"
                    )

                with c4:
                    st.markdown(
                        f"**Pontual**  \n"
                        f"{texto(os_registro['Pontual'])}"
                    )

                with c5:
                    if st.button(
                        "✏️",
                        key=f"editar_os_{os_id}",
                        help="Editar O.S.",
                    ):
                        st.session_state.dialogo_melhorias = "editar_os"
                        st.session_state.dialogo_os_id = os_id
                        st.session_state.dialogo_os_matricula = matricula
                        st.rerun()

                with c6:
                    if st.button(
                        "🗑️",
                        key=f"excluir_os_{os_id}",
                        help="Excluir O.S.",
                    ):
                        st.session_state.tipo_exclusao = "os"
                        st.session_state.id_exclusao = os_id
                        st.session_state.matricula_exclusao = matricula
                        st.session_state.dialogo_melhorias = "confirmar_exclusao"
                        st.rerun()

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    st.divider()

    excel_cliente = gerar_excel_cliente(
        registro,
        historico,
    )

    st.download_button(
        "⬇️ Baixar Registro do Cliente",
        data=excel_cliente,
        file_name=(
            f"Mapeamento_Melhorias_"
            f"{matricula}.xlsx"
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
    "＋ Adicionar Registro",
    width="medium",
)
def dialogo_nova_os(
    ws_historico,
    matricula,
):

    st.markdown(
        f"### Matrícula: {texto(matricula)}"
    )

    st.caption(
        "Cadastre uma nova O.S. no histórico desta matrícula."
    )

    with st.form(
        "form_nova_os"
    ):

        numero_os = st.text_input(
            "N. O.S *",
            placeholder="12345/2026-1",
        )

        data_abertura = st.datetime_input(
            "Data de Abertura *",
            value=datetime.now(),
        )

        pressao = st.number_input(
            "Pressão (MCA)",
            min_value=0.0,
            step=0.1,
            format="%.2f",
        )

        pontual = st.selectbox(
            "Pontual",
            ["SIM", "NÃO"],
        )

        salvar = st.form_submit_button(
            "Salvar O.S.",
            type="primary",
            use_container_width=True,
        )

    if salvar:

        sucesso, mensagem = adicionar_os(
            ws_historico,
            matricula,
            numero_os,
            data_abertura,
            pressao,
            pontual,
        )

        if sucesso:
            st.success(mensagem)

            st.session_state.dialogo_melhorias = "matricula"
            st.session_state.dialogo_matricula = matricula

            st.rerun()

        else:
            st.error(mensagem)


# ============================================================
# DIÁLOGO — EDITAR O.S.
# ============================================================

@st.dialog(
    "✏️ Editar O.S.",
    width="medium",
)
def dialogo_editar_os(
    ws_historico,
    df_historico,
    os_id,
    matricula,
):

    registros = df_historico[
        df_historico["ID"]
        .astype(str)
        .str.strip()
        == texto(os_id)
    ]

    if registros.empty:
        st.error(
            "O.S. não encontrada."
        )
        return

    os_registro = registros.iloc[0]

    data_inicial = converter_data_hora(
        os_registro[
            "Data de Abertura"
        ]
    )

    if pd.isna(data_inicial):
        data_inicial = datetime.now()

    with st.form(
        f"form_editar_os_{os_id}"
    ):

        numero_os = st.text_input(
            "N. O.S *",
            value=texto(
                os_registro["N. O.S"]
            ),
        )

        data_abertura = st.datetime_input(
            "Data de Abertura *",
            value=data_inicial.to_pydatetime()
            if hasattr(
                data_inicial,
                "to_pydatetime",
            )
            else data_inicial,
        )

        pressao = st.number_input(
            "Pressão (MCA)",
            min_value=0.0,
            step=0.1,
            format="%.2f",
            value=(
                valor_float(
                    os_registro["Pressão"]
                )
                or 0.0
            ),
        )

        pontual_atual = texto(
            os_registro["Pontual"]
        )

        if pontual_atual not in [
            "SIM",
            "NÃO",
        ]:
            pontual_atual = "SIM"

        pontual = st.selectbox(
            "Pontual",
            ["SIM", "NÃO"],
            index=[
                "SIM",
                "NÃO",
            ].index(
                pontual_atual
            ),
        )

        salvar = st.form_submit_button(
            "Salvar alterações",
            type="primary",
            use_container_width=True,
        )

    if salvar:

        sucesso, mensagem = atualizar_os(
            ws_historico,
            os_id,
            matricula,
            numero_os,
            data_abertura,
            pressao,
            pontual,
        )

        if sucesso:
            st.success(mensagem)

            st.session_state.dialogo_melhorias = "matricula"
            st.session_state.dialogo_matricula = matricula

            st.rerun()

        else:
            st.error(mensagem)


# ============================================================
# DIÁLOGO — CONFIRMAÇÃO DE EXCLUSÃO
# ============================================================

@st.dialog(
    "⚠️ Confirmar exclusão",
    width="small",
)
def dialogo_confirmar_exclusao(
    ws_registro,
    ws_historico,
):

    tipo = st.session_state.tipo_exclusao
    identificador = st.session_state.id_exclusao
    matricula = st.session_state.matricula_exclusao

    if tipo == "registro":

        st.warning(
            "Você está prestes a excluir o cadastro principal "
            f"da matrícula **{matricula}**."
        )

        st.info(
            "O histórico de O.S. será preservado."
        )

    elif tipo == "os":

        st.warning(
            "Você está prestes a excluir a O.S. "
            f"da matrícula **{matricula}**."
        )

        st.info(
            "Esta ação não poderá ser desfeita."
        )

    col1, col2 = st.columns(2)

    with col1:
        cancelar = st.button(
            "Cancelar",
            use_container_width=True,
        )

    with col2:
        confirmar = st.button(
            "Confirmar exclusão",
            type="primary",
            use_container_width=True,
        )

    if cancelar:
        st.session_state.dialogo_melhorias = (
            "matricula"
            if tipo == "os"
            else None
        )

        if tipo == "os":
            st.session_state.dialogo_matricula = matricula

        st.rerun()

    if confirmar:

        if tipo == "registro":
            sucesso, mensagem = excluir_registro(
                ws_registro,
                identificador,
            )

            if sucesso:
                st.success(mensagem)

                st.session_state.dialogo_melhorias = None
                st.rerun()

            else:
                st.error(mensagem)

        elif tipo == "os":

            sucesso, mensagem = excluir_os(
                ws_historico,
                identificador,
                matricula,
            )

            if sucesso:
                st.success(mensagem)

                st.session_state.dialogo_melhorias = "matricula"
                st.session_state.dialogo_matricula = matricula

                st.rerun()

            else:
                st.error(mensagem)


# ============================================================
# CONEXÃO E DADOS
# ============================================================

(
    spreadsheet,
    ws_registro,
    ws_historico,
) = obter_planilhas()


(
    df_registro,
    df_historico,
) = carregar_dados(
    ws_registro,
    ws_historico,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### 🛠️ COI - Mapeamento de Melhorias"
    )

    st.caption(
        "Gestão de matrículas, O.S. e tratativas."
    )

    st.divider()

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    st.markdown(
        "**📅 Período de O.S.**"
    )

    data_minima, data_maxima = (
        obter_periodo_padrao(
            df_historico
        )
    )

    data_inicial = st.date_input(
        "Data Inicial",
        value=data_minima,
        key="filtro_data_inicial_mm",
        on_change=limpar_filtros_paginacao,
    )

    data_final = st.date_input(
        "Data Final",
        value=data_maxima,
        key="filtro_data_final_mm",
        on_change=limpar_filtros_paginacao,
    )

    if data_inicial > data_final:
        st.error(
            "A Data Inicial não pode ser maior que a Data Final."
        )

    st.divider()

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    st.markdown(
        "**🔎 Filtros**"
    )

    bairros = sorted(
        [
            texto(x)
            for x in df_registro["Bairro"].dropna().unique()
            if texto(x)
        ]
    ) if not df_registro.empty else []

    matriculas = sorted(
        [
            texto(x)
            for x in df_registro["Matrícula"].dropna().unique()
            if texto(x)
        ]
    ) if not df_registro.empty else []

    impactos = sorted(
        [
            texto(x)
            for x in df_registro["Grau de Impacto"].dropna().unique()
            if texto(x)
        ]
    ) if not df_registro.empty else []

    resolvidos = sorted(
        [
            texto(x)
            for x in df_registro["Resolvido"].dropna().unique()
            if texto(x)
        ]
    ) if not df_registro.empty else []

    executados = sorted(
        list(
            {
                texto(x)
                for x in list(
                    df_registro["Executado?"]
                ) + list(
                    df_registro["Executado?2"]
                )
                if texto(x)
            }
        )
    ) if not df_registro.empty else []

    bairro = st.selectbox(
        "Bairro",
        ["Todos"] + bairros,
        key="filtro_bairro_mm",
        on_change=limpar_filtros_paginacao,
    )

    matricula = st.selectbox(
        "Matrícula",
        ["Todas"] + matriculas,
        key="filtro_matricula_mm",
        on_change=limpar_filtros_paginacao,
    )

    grau_impacto = st.selectbox(
        "Grau de Impacto",
        ["Todos"] + impactos,
        key="filtro_impacto_mm",
        on_change=limpar_filtros_paginacao,
    )

    resolvido = st.selectbox(
        "Resolvido",
        ["Todos"] + resolvidos,
        key="filtro_resolvido_mm",
        on_change=limpar_filtros_paginacao,
    )

    executado = st.selectbox(
        "Executado",
        ["Todos"] + executados,
        key="filtro_executado_mm",
        on_change=limpar_filtros_paginacao,
    )

    busca = st.text_input(
        "Busca rápida",
        placeholder="Matrícula, endereço ou O.S.",
        key="filtro_busca_mm",
        on_change=limpar_filtros_paginacao,
    )

    st.divider()

    # --------------------------------------------------------
    # AÇÕES
    # --------------------------------------------------------

    st.markdown(
        "**⚙️ Ações**"
    )

    if st.button(
        "＋ Adicionar Registro",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.dialogo_melhorias = "novo"
        st.rerun()

    # --------------------------------------------------------
    # EXPORTAÇÃO
    # --------------------------------------------------------

    st.markdown(
        ""
    )

    # Os dados filtrados são calculados antes do botão,
    # portanto o download respeita os filtros atuais.
    (
        df_registro_filtrado,
        df_historico_filtrado,
    ) = aplicar_filtros(
        df_registro,
        df_historico,
        data_inicial,
        data_final,
        bairro,
        matricula,
        grau_impacto,
        resolvido,
        executado,
        busca,
    )

    excel_filtrado = gerar_excel(
        df_registro_filtrado,
        df_historico_filtrado,
        nome_resumo="Registro",
    )

    st.download_button(
        "⬇️ Exportar filtrado",
        data=excel_filtrado,
        file_name=(
            "Mapeamento_Melhorias_"
            f"{date.today().strftime('%Y%m%d')}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

    st.divider()

    # --------------------------------------------------------
    # NAVEGAÇÃO
    # --------------------------------------------------------

    if st.button(
        "⬅️ Voltar ao Hub Central",
        use_container_width=True,
    ):
        st.switch_page(
            "app.py"
        )

    st.divider()

    # --------------------------------------------------------
    # MODO ESCURO
    # --------------------------------------------------------

    modo_escuro = st.toggle(
        "🌙 Modo escuro",
        value=st.session_state.modo_escuro_melhorias,
        key="toggle_modo_escuro_melhorias",
    )

    st.session_state.modo_escuro_melhorias = (
        modo_escuro
    )


# ============================================================
# MODO ESCURO
# ============================================================

if st.session_state.modo_escuro_melhorias:

    st.markdown(
        """
        <style>

            .stApp {
                background-color: #0e1117;
                color: #fafafa;
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

            .stButton > button {
                background-color: #000000 !important;
                color: #ffffff !important;
                border: 1px solid #444c56 !important;
            }

            .stButton > button:hover {
                background-color: #000000 !important;
                color: #ff0000 !important;
                border-color: #ff0000 !important;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# VALIDAÇÃO DO PERÍODO
# ============================================================

if data_inicial > data_final:
    st.stop()


# ============================================================
# FILTROS APLICADOS
# ============================================================

(
    df_registro_filtrado,
    df_historico_filtrado,
) = aplicar_filtros(
    df_registro,
    df_historico,
    data_inicial,
    data_final,
    bairro,
    matricula,
    grau_impacto,
    resolvido,
    executado,
    busca,
)


# ============================================================
# TÍTULO
# ============================================================

st.title(
    "🛠️ Mapeamento de Melhorias - COI"
)

st.caption(
    "Gestão de matrículas, mapeamentos, tratativas e histórico de O.S."
)

st.caption(
    f"Período considerado: "
    f"{data_inicial.strftime('%d/%m/%Y')} "
    f"a "
    f"{data_final.strftime('%d/%m/%Y')}"
)


# ============================================================
# KPIs
# ============================================================

resumo = criar_resumo_lista(
    df_registro_filtrado,
    df_historico_filtrado,
)


matricula_destaque = None
qtd_destaque = 0

if not df_historico_filtrado.empty:

    contagem = (
        df_historico_filtrado
        .groupby("Matrícula")
        .size()
        .reset_index(
            name="QtdOS"
        )
    )

    contagem["UltimaOS"] = (
        contagem["Matrícula"]
        .apply(
            lambda x: ultima_os(
                df_historico_filtrado,
                x,
            )
        )
    )

    contagem = contagem.sort_values(
        by=[
            "QtdOS",
            "UltimaOS",
            "Matrícula",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        na_position="last",
    )

    if not contagem.empty:
        matricula_destaque = texto(
            contagem.iloc[0]["Matrícula"]
        )

        qtd_destaque = int(
            contagem.iloc[0]["QtdOS"]
        )


if matricula_destaque:

    tempo_kpi = tempo_medio_reclamacao(
        df_historico_filtrado,
        matricula_destaque,
    )

    pressao_kpi = media_pressao(
        df_historico_filtrado,
        matricula_destaque,
    )

else:
    tempo_kpi = None
    pressao_kpi = None


kpi1, kpi2, kpi3, kpi4 = st.columns(4)


with kpi1:
    st.metric(
        "Cliente com mais registros",
        matricula_destaque
        if matricula_destaque
        else "—",
    )


with kpi2:
    st.metric(
        "Quant. de O.S",
        qtd_destaque,
    )


with kpi3:
    st.metric(
        "Tempo Médio de Reclamação",
        (
            f"{tempo_kpi:.1f} dias"
            if tempo_kpi is not None
            else "—"
        ),
    )


with kpi4:
    st.metric(
        "Média de Pressão",
        (
            f"{pressao_kpi:.2f} MCA"
            if pressao_kpi is not None
            else "—"
        ),
    )


# ============================================================
# MAPA
# ============================================================

st.divider()

st.subheader(
    "🗺️ Mapa de Melhorias"
)

col1, col2 = st.columns(
    [
        1,
        1,
    ]
)

with col1:
    tipo_mapa = st.selectbox(
        "Tipo de mapa",
        [
            "🗺️ Mapa",
            "🛰️ Satélite",
            "⛰️ Terreno",
        ],
        key="tipo_mapa_melhorias",
    )

with col2:
    st.caption(
        "Sem filtros, todos os registros com coordenadas são exibidos. "
        "Com filtros, o mapa acompanha o resultado filtrado."
    )


mapa = criar_mapa(
    df_registro_filtrado,
    df_historico_filtrado,
    tipo_mapa,
)


st_folium(
    mapa,
    width=None,
    height=600,
    returned_objects=[],
    key="mapa_mapeamento_melhorias",
)


# ============================================================
# LISTA DE REGISTROS
# ============================================================

st.divider()

st.subheader(
    "📋 Registros de Melhorias"
)

if resumo.empty:

    st.info(
        "Nenhum registro encontrado para os filtros selecionados."
    )

else:

    total_registros = len(
        resumo
    )

    registros_por_pagina = 10

    total_paginas = max(
        1,
        math.ceil(
            total_registros
            / registros_por_pagina
        ),
    )

    if (
        st.session_state.pagina_melhorias
        > total_paginas
    ):
        st.session_state.pagina_melhorias = (
            total_paginas
        )

    pagina_atual = (
        st.session_state.pagina_melhorias
    )

    inicio = (
        pagina_atual - 1
    ) * registros_por_pagina

    fim = (
        inicio
        + registros_por_pagina
    )

    pagina = resumo.iloc[
        inicio:fim
    ]

    # --------------------------------------------------------
    # CABEÇALHO
    # --------------------------------------------------------

    h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(
        [
            1.4,
            2.2,
            1.3,
            1.2,
            0.9,
            1.3,
            0.5,
            0.5,
        ]
    )

    with h1:
        st.markdown(
            "**Matrícula**"
        )

    with h2:
        st.markdown(
            "**Endereço**"
        )

    with h3:
        st.markdown(
            "**Bairro**"
        )

    with h4:
        st.markdown(
            "**Impacto**"
        )

    with h5:
        st.markdown(
            "**Resolvido**"
        )

    with h6:
        st.markdown(
            "**O.S. / Última**"
        )

    with h7:
        st.markdown(
            "**✏️**"
        )

    with h8:
        st.markdown(
            "**🗑️**"
        )

    st.divider()

    # --------------------------------------------------------
    # LINHAS
    # --------------------------------------------------------

    for _, linha in pagina.iterrows():

        registro_id = texto(
            linha["ID"]
        )

        matricula_linha = texto(
            linha["Matrícula"]
        )

        with st.container(
            border=True
        ):

            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(
                [
                    1.4,
                    2.2,
                    1.3,
                    1.2,
                    0.9,
                    1.3,
                    0.5,
                    0.5,
                ]
            )

            with c1:
                if st.button(
                    matricula_linha,
                    key=f"abrir_matricula_{registro_id}",
                    use_container_width=True,
                ):
                    st.session_state.dialogo_melhorias = "matricula"
                    st.session_state.dialogo_matricula = matricula_linha
                    st.rerun()

            with c2:
                st.markdown(
                    f"<div class='campo-lista'>"
                    f"{html.escape(texto(linha['Endereço']))}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with c3:
                st.markdown(
                    f"<div class='campo-lista'>"
                    f"{html.escape(texto(linha['Bairro']))}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            with c4:
                impacto = texto(
                    linha["Grau de Impacto"]
                )

                st.markdown(
                    f'<span class="{valor_badge(impacto)}">'
                    f"{html.escape(impacto or '—')}"
                    f"</span>",
                    unsafe_allow_html=True,
                )

            with c5:
                resolvido_linha = texto(
                    linha["Resolvido"]
                )

                st.markdown(
                    f'<span class="{valor_badge(resolvido_linha)}">'
                    f"{html.escape(resolvido_linha or '—')}"
                    f"</span>",
                    unsafe_allow_html=True,
                )

            with c6:

                qtd = int(
                    linha["Qtd. O.S."]
                )

                ultima = linha[
                    "Última O.S."
                ]

                ultima_txt = (
                    ultima.strftime(
                        "%d/%m/%Y"
                    )
                    if not pd.isna(ultima)
                    else "—"
                )

                st.markdown(
                    f"**{qtd} O.S.**  \n"
                    f"{ultima_txt}"
                )

            with c7:
                if st.button(
                    "✏️",
                    key=f"editar_registro_{registro_id}",
                    help="Editar registro",
                ):
                    st.session_state.dialogo_melhorias = "editar"
                    st.session_state.dialogo_id = registro_id
                    st.rerun()

            with c8:
                if st.button(
                    "🗑️",
                    key=f"excluir_registro_{registro_id}",
                    help="Excluir registro",
                ):
                    st.session_state.tipo_exclusao = "registro"
                    st.session_state.id_exclusao = registro_id
                    st.session_state.matricula_exclusao = matricula_linha
                    st.session_state.dialogo_melhorias = "confirmar_exclusao"
                    st.rerun()

    # --------------------------------------------------------
    # PAGINAÇÃO
    # --------------------------------------------------------

    st.markdown("")

    p1, p2, p3 = st.columns(
        [
            1,
            2,
            1,
        ]
    )

    with p1:
        if st.button(
            "⬅️ Anterior",
            disabled=(
                pagina_atual <= 1
            ),
            use_container_width=True,
        ):
            st.session_state.pagina_melhorias -= 1
            st.rerun()

    with p2:
        st.markdown(
            f"<div style='text-align:center; padding-top:8px;'>"
            f"Página <b>{pagina_atual}</b> de <b>{total_paginas}</b>"
            f" &nbsp; • &nbsp; {total_registros} registros"
            f"</div>",
            unsafe_allow_html=True,
        )

    with p3:
        if st.button(
            "Próxima ➡️",
            disabled=(
                pagina_atual >= total_paginas
            ),
            use_container_width=True,
        ):
            st.session_state.pagina_melhorias += 1
            st.rerun()


# ============================================================
# ROTEAMENTO DOS DIÁLOGOS
# ============================================================

dialogo_atual = (
    st.session_state.dialogo_melhorias
)


if dialogo_atual == "novo":

    dialogo_novo_registro(
        ws_registro,
        ws_historico,
        df_historico,
    )

elif dialogo_atual == "editar":

    dialogo_editar_registro(
        ws_registro,
        ws_historico,
        df_registro,
        st.session_state.dialogo_id,
    )

elif dialogo_atual == "matricula":

    dialogo_matricula(
        df_registro,
        df_historico,
        st.session_state.dialogo_matricula,
    )

elif dialogo_atual == "nova_os":

    dialogo_nova_os(
        ws_historico,
        st.session_state.dialogo_os_matricula,
    )

elif dialogo_atual == "editar_os":

    dialogo_editar_os(
        ws_historico,
        df_historico,
        st.session_state.dialogo_os_id,
        st.session_state.dialogo_os_matricula,
    )

elif dialogo_atual == "confirmar_exclusao":

    dialogo_confirmar_exclusao(
        ws_registro,
        ws_historico,
    )
