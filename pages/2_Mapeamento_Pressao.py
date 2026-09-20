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

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Mapeamento de Pressão - COI",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS para ocultar navegação padrão
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
# TRAVA DE SEGURANÇA E CONTROLE DE SESSÃO
# ============================================================
if "autenticado" not in st.session_state or not st.session_state.autenticado:
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("Ir para o Login"):
        st.switch_page("app.py")
    st.stop()

# ============================================================
# CONTROLE DE ACESSO (ADMIN VS USUÁRIO COMUM)
# ============================================================
usuario_atual = st.session_state.get("usuario_logado", "")
perfil_atual = st.session_state.get("perfil", "")
eh_admin = (usuario_atual.lower() == "admin" or perfil_atual.lower() == "admin")

if not eh_admin:
    with st.sidebar:
        st.markdown("### 🗺️ COI - Mapeamento")
        st.caption("Em Desenvolvimento")
        st.divider()
        if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
            st.switch_page("app.py")

    st.title("🗺️ Mapeamento de Pressão - COI")
    st.info("🚧 Este módulo está atualmente em fase de desenvolvimento e validação.")
    st.stop()

# ============================================================
# CONSTANTES E ESTRUTURA DE COLUNAS DA SUA PLANILHA
# ============================================================
LAT_BASE = -5.0892
LON_BASE = -42.8019
SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"
COLUNAS_PADRAO = ["ID", "Data", "Pontos", "Latitude", "Longitude", "MCA", "Observacao"]

# ============================================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================================
@st.cache_resource
def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = json.loads(st.secrets["gcp_json"])
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet("mapeamento_pressao")
    except Exception:
        try:
            ws = sh.add_worksheet(title="mapeamento_pressao", rows="1000", cols="20")
        except Exception:
            ws = sh.sheet1
            
    try:
        dados_iniciais = ws.get_all_values()
        if not dados_iniciais or len(dados_iniciais) == 0:
            ws.append_row(["ID", "Data", "Pontos", "Latitude", "Longitude", "MCA", "Observação"])
    except Exception:
        pass
        
    return ws

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"❌ Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# ============================================================
# FUNÇÕES DE DADOS E EXPORTAÇÃO
# ============================================================
def gerar_id() -> str:
    return str(uuid.uuid4())[:8].upper()

def normalizar_coluna(nome: str) -> str:
    nome = str(nome).strip().lower()
    mapeamento = {
        "id": "ID", "data": "Data", "pontos": "Pontos", "ponto": "Pontos",
        "latitude": "Latitude", "lat": "Latitude", "longitude": "Longitude",
        "lon": "Longitude", "long": "Longitude", "mca": "MCA", "pressao": "MCA", "pressão": "MCA",
        "observacao": "Observacao", "observação": "Observacao", "obs": "Observacao"
    }
    return mapeamento.get(nome, nome.title())

def parse_float(valor, default=None):
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return default
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        texto = str(valor).strip()
        if not texto or texto.lower() in ("nan", "none", "nat", ""):
            return default
        texto = texto.replace(",", ".").replace(" ", "")
        return float(texto)
    except (ValueError, TypeError):
        return default

def normalizar_coordenada(valor, tipo: str = "lat") -> Optional[float]:
    num = parse_float(valor, default=None)
    if num is None:
        return None
    if tipo == "lat" and not (-90.0 <= num <= 90.0):
        return None
    if tipo == "lon" and not (-180.0 <= num <= 180.0):
        return None
    if num == 0.0:
        return None
    return round(float(num), 6)

@st.cache_data(ttl=5, show_spinner="Carregando dados...")
def carregar_dados() -> pd.DataFrame:
    try:
        valores = worksheet.get_all_values()
    except Exception as e:
        st.error(f"Erro ao ler planilha: {e}")
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    if not valores or len(valores) < 2:
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    cabecalhos_raw = valores[0]
    cabecalhos = [normalizar_coluna(c) for c in cabecalhos_raw]

    registros = []
    for linha in valores[1:]:
        if not any(str(c).strip() for c in linha):
            continue
        reg = {}
        for i, col in enumerate(cabecalhos):
            reg[col] = linha[i] if i < len(linha) else ""
        registros.append(reg)

    if not registros:
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    df = pd.DataFrame(registros)
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = ""

    def limpar_id(v):
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return gerar_id()
        return s

    df["ID"] = df["ID"].apply(limpar_id)
    df["Data"] = df["Data"].apply(normalizar_data)
    df["Pontos"] = df["Pontos"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df["Latitude"] = df["Latitude"].apply(lambda x: normalizar_coordenada(x, "lat"))
    df["Longitude"] = df["Longitude"].apply(lambda x: normalizar_coordenada(x, "lon"))
    df["MCA"] = df["MCA"].apply(lambda x: parse_float(x, 0.0) or 0.0)
    df["Observacao"] = df["Observacao"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df = df[df["Pontos"].astype(str).str.strip() != ""]

    return df[COLUNAS_PADRAO].reset_index(drop=True)

def limpar_cache():
    carregar_dados.clear()

def adicionar_ponto(pontos: str, lat: float, lon: float, mca: float, obs: str, data_str: str):
    novo_id = gerar_id()
    worksheet.append_row([novo_id, data_str, pontos, lat, lon, mca, obs])
    limpar_cache()
    return novo_id

def adicionar_lote_pontos(linhas_dados: list):
    if not linhas_dados:
        return 0
    worksheet.append_rows(linhas_dados)
    limpar_cache()
    return len(linhas_dados)

def atualizar_ponto(id_registro: str, pontos: str, lat: float, lon: float, mca: float, obs: str, data_str: str) -> bool:
    try:
        celula = worksheet.find(str(id_registro))
        if celula is None:
            return False
        linha = celula.row
        worksheet.update(f"A{linha}:G{linha}", [[str(id_registro), str(data_str), str(pontos), float(lat), float(lon), float(mca), str(obs)]])
        limpar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar: {e}")
        return False

def excluir_ponto(id_registro: str) -> bool:
    try:
        celula = worksheet.find(str(id_registro))
        if celula is None:
            return False
        worksheet.delete_rows(celula.row)
        limpar_cache()
        return True
    except Exception:
        return False

def data_para_str(d: date) -> str:
    return d.strftime("%d/%m/%Y")

def normalizar_data(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", "nat"):
        return ""
    formatos = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto

def gerar_kml(df):
    kml = simplekml.Kml()
    for _, row in df.iterrows():
        lat = row.get("Latitude")
        lon = row.get("Longitude")
        if pd.notnull(lat) and pd.notnull(lon):
            try:
                kml.newpoint(
                    name=str(row.get("ID", "Ponto")),
                    description=f"Ponto: {row.get('Pontos', '')}\nMCA: {row.get('MCA', '')}\nObservação: {row.get('Observacao', '')}",
                    coords=[(float(lon), float(lat))]
                )
            except (ValueError, TypeError):
                continue
    return kml.kml()

# ============================================================
# SESSION STATE
# ============================================================
hoje = date.today()

if "data_selecionada" not in st.session_state:
    st.session_state.data_selecionada = hoje
if "clicked_lat" not in st.session_state:
    st.session_state.clicked_lat = None
if "clicked_lon" not in st.session_state:
    st.session_state.clicked_lon = None
if "modo_adicionar_mapa" not in st.session_state:
    st.session_state.modo_adicionar_mapa = False

# ============================================================
# DIALOGS (POP-UPS DE CADASTRO E EDIÇÃO)
# ============================================================
@st.dialog("➕ Cadastrar Ponto de Pressão")
def modal_novo_ponto():
    lat_default = st.session_state.clicked_lat if st.session_state.clicked_lat is not None else 0.0
    lon_default = st.session_state.clicked_lon if st.session_state.clicked_lon is not None else 0.0

    with st.form("form_novo_ponto_modal", clear_on_submit=True):
        pontos = st.text_input("Pontos / Local *", placeholder="Ex: Ponto A-01")

        c1, c2 = st.columns(2)
        with c1:
            lat = st.number_input("Latitude *", format="%.6f", value=float(lat_default), step=0.000001)
        with c2:
            lon = st.number_input("Longitude *", format="%.6f", value=float(lon_default), step=0.000001)

        mca = st.number_input("MCA *", format="%.2f", value=0.00, min_value=0.0, step=0.1)
        obs = st.text_input("Observação", placeholder="Ex: Válvula regulada")
        enviado = st.form_submit_button("Cadastrar Ponto", type="primary", use_container_width=True)

        if enviado:
            if not pontos.strip():
                st.error("O campo 'Pontos' é obrigatório.")
            elif lat == 0.0 and lon == 0.0:
                st.error("Informe coordenadas válidas ou clique no mapa.")
            else:
                lat_n = normalizar_coordenada(lat, "lat")
                lon_n = normalizar_coordenada(lon, "lon")
                if lat_n is None or lon_n is None:
                    st.error("Coordenadas inválidas.")
                else:
                    novo_id = adicionar_ponto(pontos.strip(), lat_n, lon_n, mca, obs.strip(), data_para_str(hoje))
                    st.success(f"Ponto cadastrado! ID: {novo_id}")
                    st.session_state.clicked_lat = None
                    st.session_state.clicked_lon = None
                    st.rerun()

@st.dialog("✏️ Editar Ponto de Pressão")
def modal_editar_ponto(id_registro: str):
    df_all = carregar_dados()
    df_edit_busca = df_all[df_all["ID"] == id_registro]
    if not df_edit_busca.empty:
        reg_edit = df_edit_busca.iloc[0]
        with st.form("form_edicao_modal"):
            pontos_e = st.text_input("Pontos *", value=str(reg_edit["Pontos"]))
            c1, c2 = st.columns(2)
            with c1:
                lat_e = st.number_input("Latitude *", format="%.6f", value=float(reg_edit["Latitude"] or LAT_BASE), step=0.000001)
            with c2:
                lon_e = st.number_input("Longitude *", format="%.6f", value=float(reg_edit["Longitude"] or LON_BASE), step=0.000001)
            mca_e = st.number_input("MCA *", format="%.2f", value=float(reg_edit["MCA"] or 0.0), min_value=0.0, step=0.1)
            obs_e = st.text_input("Observação", value=str(reg_edit["Observacao"]))

            col_salvar, col_canc = st.columns(2)
            with col_salvar:
                salvar_edicao = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True)
            with col_canc:
                cancelar_edicao = st.form_submit_button("❌ Cancelar", use_container_width=True)

            if salvar_edicao:
                if atualizar_ponto(id_registro, pontos_e, lat_e, lon_e, mca_e, obs_e, reg_edit["Data"]):
                    st.success("Atualizado com sucesso!")
                    st.rerun()
            if cancelar_edicao:
                st.rerun()
    else:
        st.warning("Registro não encontrado.")

# ============================================================
# SIDEBAR (ADMIN)
# ============================================================
with st.sidebar:
    st.markdown("### 🗺️ COI - Mapeamento")
    st.caption("⚙️ Área de Testes (Admin)")

    st.markdown("#### 📅 Selecionar Data")
    data_escolhida = st.date_input(
        "Data",
        value=st.session_state.data_selecionada,
        format="DD/MM/YYYY",
        label_visibility="collapsed",
        key="calendario_principal"
    )
    st.session_state.data_selecionada = data_escolhida
    data_str_selecionada = data_para_str(data_escolhida)

    if data_escolhida == hoje:
        st.success("Exibindo dados de **hoje**")
    else:
        st.info(f"Exibindo dados de **{data_str_selecionada}**")

    st.divider()

    st.markdown("#### 🔍 Filtros")
    df_all = carregar_dados()
    df_data = df_all[df_all["Data"] == data_str_selecionada] if not df_all.empty else df_all

    pontos_opts = ["Todos"] + sorted(df_data["Pontos"].dropna().unique().tolist()) if not df_data.empty else ["Todos"]
    ponto_sel = st.selectbox("Ponto", pontos_opts, key="filtro_ponto")

    faixa_sel = st.selectbox(
        "Faixa de MCA",
        ["Todas", "Críticos (0 MCA)", "Atenção (≤ 5 MCA)", "Normais (> 5 MCA)"],
        key="filtro_mca"
    )

    st.divider()

    st.markdown("#### ➕ Ações e Dados")
    if data_escolhida == hoje:
        if st.button("Adicionar Novo Ponto", type="primary", use_container_width=True):
            modal_novo_ponto()
    else:
        st.warning("Cadastro manual disponível apenas para a **data de hoje**.")

    # UPLOAD EM LOTE (Evita erro 429 de cota do Google Sheets)
    arquivo_upload = st.file_uploader("📂 Enviar Planilha (XLSX/CSV)", type=["xlsx", "csv"], key="upload_mapeamento")
    if arquivo_upload is not None:
        try:
            if arquivo_upload.name.endswith('.csv'):
                df_up = pd.read_csv(arquivo_upload)
            else:
                df_up = pd.read_excel(arquivo_upload)
            
            lote_para_enviar = []
            data_atual_str = data_para_str(hoje)

            for _, row in df_up.iterrows():
                ponto_val = str(row.get("Pontos", row.get("Ponto", "")))
                lat_val = parse_float(row.get("Latitude", row.get("Lat")))
                lon_val = parse_float(row.get("Longitude", row.get("Lon")))
                mca_val = parse_float(row.get("MCA", row.get("Pressao", 0.0)), 0.0)
                obs_val = str(row.get("Observação", row.get("Observacao", "")))
                
                if ponto_val.strip() and lat_val and lon_val:
                    novo_id = gerar_id()
                    lote_para_enviar.append([novo_id, data_atual_str, ponto_val.strip(), lat_val, lon_val, mca_val, obs_val])

            if lote_para_enviar:
                adicionar_lote_pontos(lote_para_enviar)
                st.success(f"✅ {len(lote_para_enviar)} registros importados com sucesso em lote!")
                st.rerun()
            else:
                st.warning("⚠️ Nenhum registro válido encontrado com Pontos e Coordenadas.")
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {e}")

    st.divider()

    # EXPORTAÇÃO
    st.markdown("#### 📥 Exportar Dados")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not df_all.empty:
            df_all.to_excel(writer, index=False, sheet_name='Mapeamento_Pressao')
        else:
            pd.DataFrame(columns=COLUNAS_PADRAO).to_excel(writer, index=False, sheet_name='Mapeamento_Pressao')
    excel_data = output.getvalue()
    
    st.download_button(
        label="📊 Baixar em Excel (XLSX)",
        data=excel_data,
        file_name=f"mapeamento_pressao_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    kml_string = gerar_kml(df_all) if not df_all.empty else simplekml.Kml().kml()
    st.download_button(
        label="🗺️ Baixar Mapa (KML/KMZ)",
        data=kml_string,
        file_name=f"mapeamento_pressao_{datetime.now().strftime('%Y%m%d')}.kml",
        mime="application/vnd.google-earth.kml+xml",
        use_container_width=True
    )

    st.divider()
    st.markdown("#### ⏱️ Atualização")
    intervalo = st.select_slider("Intervalo (segundos)", options=[0, 15, 30, 60, 120], value=30)
    if intervalo > 0:
        st_autorefresh(interval=intervalo * 1000, key="autorefresh")

    st.markdown("<br>" * 2, unsafe_allow_html=True)
    st.divider()

    if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")

# ============================================================
# ÁREA PRINCIPAL (ADMIN)
# ============================================================
st.title("🗺️ Painel de Mapeamento de Pressão - COI")
st.warning("⚠️ Modo Admin (Testes do Módulo 2)")
st.caption(f"Visualizando: **{data_str_selecionada}**")

df = carregar_dados()
df_filtrado = df[df["Data"] == data_str_selecionada].copy() if not df.empty else df.copy()

if ponto_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Pontos"] == ponto_sel]

if faixa_sel == "Críticos (0 MCA)":
    df_filtrado = df_filtrado[df_filtrado["MCA"] == 0]
elif faixa_sel == "Atenção (≤ 5 MCA)":
    df_filtrado = df_filtrado[(df_filtrado["MCA"] > 0) & (df_filtrado["MCA"] <= 5)]
elif faixa_sel == "Normais (> 5 MCA)":
    df_filtrado = df_filtrado[df_filtrado["MCA"] > 5]

if not df_filtrado.empty:
    total = len(df_filtrado)
    criticos = len(df_filtrado[df_filtrado["MCA"] == 0])
    atencao = len(df_filtrado[(df_filtrado["MCA"] > 0) & (df_filtrado["MCA"] <= 5)])
    normais = len(df_filtrado[df_filtrado["MCA"] > 5])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de Ocorrências", total)
    k2.metric("Críticos (0 MCA)", criticos)
    k3.metric("Em Atenção (≤ 5 MCA)", atencao)
    k4.metric("Normais (> 5 MCA)", normais)
else:
    st.info("Nenhum ponto registrado para a data e filtros selecionados.")

st.divider()

# ============================================================
# MAPA COM SELETOR DE TIPO DE MAPA (ESTILO MY MAPS)
# ============================================================
st.subheader("🗺️ Mapa de Mapeamento de Pressão")

c_map1, c_map2, c_map3 = st.columns([2, 2, 2])
with c_map1:
    tipo_mapa = st.selectbox(
        "🗺️ Tipo de Mapa",
        options=[
            "Mapa Padrão (OpenStreetMap)",
            "Satélite (Esri World Imagery)",
            "Claro / Minimalista (CartoDB Positron)",
            "Escuro / Noturno (CartoDB Dark Matter)",
            "Terreno (Stamen Terrain)"
        ],
        key="seletor_tipo_mapa"
    )
with c_map2:
    mostrar_rotulos = st.checkbox("Exibir rótulos", value=False)
with c_map3:
    if data_escolhida == hoje:
        st.session_state.modo_adicionar_mapa = st.checkbox(
            "📍 Modo adicionar ponto",
            value=st.session_state.modo_adicionar_mapa
        )

if "Satélite" in tipo_mapa:
    tiles_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    attr = 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
elif "Claro" in tipo_mapa:
    tiles_url = 'CartoDB positron'
    attr = None
elif "Escuro" in tipo_mapa:
    tiles_url = 'CartoDB dark_matter'
    attr = None
elif "Terreno" in tipo_mapa:
    tiles_url = 'Stamen Terrain'
    attr = None
else:
    tiles_url = 'OpenStreetMap'
    attr = None

if not df_filtrado.empty and df_filtrado["Latitude"].notna().any():
    centro_lat = float(df_filtrado["Latitude"].mean())
    centro_lon = float(df_filtrado["Longitude"].mean())
    zoom = 13
else:
    centro_lat, centro_lon = LAT_BASE, LON_BASE
    zoom = 12

if attr:
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles=tiles_url, attr=attr)
else:
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles=tiles_url)

if not df_filtrado.empty:
    validos = df_filtrado.dropna(subset=["Latitude", "Longitude"])
    for _, row in validos.iterrows():
        mca = row["MCA"]
        cor = "red" if mca == 0 else ("orange" if mca <= 5 else "blue")
        popup = f"<b>Ponto:</b> {row['Pontos']}<br><b>MCA:</b> {mca}<br><b>Obs:</b> {row['Observacao']}"
        
        marker_icon = folium.Icon(color=cor, icon="map-pin", prefix="fa")
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=folium.Popup(popup, max_width=250),
            tooltip=f"{row['Pontos']} ({mca} MCA)",
            icon=marker_icon
        ).add_to(m)

        if mostrar_rotulos:
            texto_rotulo = f"{row['Pontos']} — {mca} MCA"
            folium.map.Marker(
                [row["Latitude"], row["Longitude"]],
                icon=folium.DivIcon(
                    icon_size=(200, 40),
                    icon_anchor=(-12, 18),
                    html=f'''
                    <div style="
                        font-family: sans-serif;
                        font-size: 11px;
                        font-weight: 600;
                        color: #1f2937;
                        background-color: rgba(255, 255, 255, 0.92);
                        padding: 4px 8px;
                        border-radius: 6px;
                        border: 1px solid #cbd5e1;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                        width: max-content;
                        white-space: nowrap;
                    ">
                        📍 {texto_rotulo}
                    </div>
                    '''
                )
            ).add_to(m)

map_data = st_folium(m, width="100%", height=520, returned_objects=["last_clicked"], key="mapa_principal_map")

if st.session_state.modo_adicionar_mapa and data_escolhida == hoje and map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    if clicked:
        st.session_state.clicked_lat = round(clicked["lat"], 6)
        st.session_state.clicked_lon = round(clicked["lng"], 6)
        modal_novo_ponto()

st.divider()

# ============================================================
# TABELA
# ============================================================
st.subheader("📋 Registro de Pontos Mapeados")
if not df_filtrado.empty:
    df_show = df_filtrado[["ID", "Data", "Pontos", "Latitude", "Longitude", "MCA", "Observacao"]].reset_index(drop=True)
    evento = st.dataframe(df_show, use_container_width=True, height=300, on_select="rerun", selection_mode="single-row", key="tabela_registros_map")
    
    linhas_selecionadas = evento.selection.rows if evento and evento.selection else []
    if linhas_selecionadas:
        idx = linhas_selecionadas[0]
        registro = df_show.iloc[idx]
        id_sel = str(registro["ID"])
        
        col_a, col_b, _ = st.columns([1, 1, 4])
        with col_a:
            if st.button("✏️ Editar", use_container_width=True):
                modal_editar_ponto(id_sel)
        with col_b:
            if st.button("🗑️ Excluir", use_container_width=True):
                if excluir_ponto(id_sel):
                    st.success("Excluído com sucesso.")
                    st.rerun()
else:
    st.info("Nenhum dado cadastrado ou filtrado para exibir na tabela.")
