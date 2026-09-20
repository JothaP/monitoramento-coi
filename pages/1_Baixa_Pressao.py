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
import plotly.express as px

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Monitoramento de Baixa Pressão - COI",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# TRAVA DE SEGURANÇA E CONTROLE DE SESSÃO DO HUB
# ============================================================
if "autenticado" not in st.session_state or not st.session_state.autenticado:
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
COLUNAS_PADRAO = ["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"]

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
        return sh.worksheet("baixa_pressao")
    except Exception:
        return sh.sheet1

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"❌ Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# ============================================================
# FUNÇÕES DE DADOS
# ============================================================
def gerar_id() -> str:
    return str(uuid.uuid4())[:8].upper()

def normalizar_coluna(nome: str) -> str:
    nome = str(nome).strip().lower()
    mapeamento = {
        "id": "ID", "data": "Data", "municipio": "Municipio", "município": "Municipio",
        "bairro": "Bairro", "latitude": "Latitude", "lat": "Latitude", "longitude": "Longitude",
        "lon": "Longitude", "long": "Longitude", "pressao_mca": "Pressao_MCA", "pressão_mca": "Pressao_MCA",
        "pressao": "Pressao_MCA", "pressão": "Pressao_MCA", "mca": "Pressao_MCA",
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
    df["Municipio"] = df["Municipio"].astype(str).str.strip().replace({"": "Teresina", "nan": "Teresina", "None": "Teresina"})
    df["Bairro"] = df["Bairro"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df["Latitude"] = df["Latitude"].apply(lambda x: normalizar_coordenada(x, "lat"))
    df["Longitude"] = df["Longitude"].apply(lambda x: normalizar_coordenada(x, "lon"))
    df["Pressao_MCA"] = df["Pressao_MCA"].apply(lambda x: parse_float(x, 0.0) or 0.0)
    df = df[df["Bairro"].astype(str).str.strip() != ""]

    return df[COLUNAS_PADRAO].reset_index(drop=True)

def limpar_cache():
    carregar_dados.clear()

def adicionar_ponto(municipio: str, bairro: str, lat: float, lon: float, pressao: float, data_str: str):
    novo_id = gerar_id()
    worksheet.append_row([novo_id, data_str, municipio, bairro, lat, lon, pressao])
    limpar_cache()
    return novo_id

def atualizar_ponto(id_registro: str, municipio: str, bairro: str, lat: float, lon: float, pressao: float, data_str: str) -> bool:
    try:
        celula = worksheet.find(str(id_registro))
        if celula is None:
            return False
        linha = celula.row
        worksheet.update(f"A{linha}:G{linha}", [[str(id_registro), str(data_str), str(municipio), str(bairro), float(lat), float(lon), float(pressao)]])
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
if "id_editando" not in st.session_state:
    st.session_state.id_editando = None

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")
    st.divider()

    st.markdown("### 💧 COI - Monitoramento")
    st.caption("Baixa Pressão • Tempo Real")

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

    municipios_opts = ["Todos"] + sorted(df_data["Municipio"].dropna().unique().tolist()) if not df_data.empty else ["Todos"]
    mun_sel = st.selectbox("Município", municipios_opts, key="filtro_municipio")

    bairros_base = df_data[df_data["Municipio"] == mun_sel] if mun_sel != "Todos" and not df_data.empty else df_data
    bairros_opts = ["Todos"] + sorted(bairros_base["Bairro"].dropna().unique().tolist()) if not bairros_base.empty else ["Todos"]
    bairro_sel = st.selectbox("Bairro", bairros_opts, key="filtro_bairro")

    faixa_sel = st.selectbox(
        "Faixa de Pressão",
        ["Todas", "Críticos (0 MCA)", "Atenção (≤ 5 MCA)", "Normais (> 5 MCA)"],
        key="filtro_pressao"
    )

    st.divider()

    # FORMULÁRIO DE CADASTRO OU EDIÇÃO
    if st.session_state.id_editando:
        st.markdown("#### ✏️ Editar Ponto")
        df_edit_busca = df_all[df_all["ID"] == st.session_state.id_editando]
        if not df_edit_busca.empty:
            reg_edit = df_edit_busca.iloc[0]
            with st.form("form_edicao"):
                municipio	= st.text_input("Município *\t", value=str(reg_edit["Municipio"]))
                bairro_e = st.text_input("Bairro *", value=str(reg_edit["Bairro"]))
                c1, c2 = st.columns(2)
                with c1:
                    lat_e = st.number_input("Latitude *", format="%.6f", value=float(reg_edit["Latitude"] or LAT_BASE), step=0.000001)
                with c2:
                    lon_e = st.number_input("Longitude *", format="%.6f", value=float(reg_edit["Longitude"] or LON_BASE), step=0.000001)
                pressao_e = st.number_input("Pressão (MCA) *", format="%.2f", value=float(reg_edit["Pressao_MCA"] or 0.0), min_value=0.0, step=0.1)

                col_salvar, col_canc = st.columns(2)
                with col_salvar:
                    salvar_edicao = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True)
                with col_canc:
                    cancelar_edicao = st.form_submit_button("❌ Cancelar", use_container_width=True)

                if salvar_edicao:
                    if atualizar_ponto(st.session_state.id_editando, municipio	, bairro_e, lat_e, lon_e, pressao_e, reg_edit["Data"]):
                        st.success("Atualizado com sucesso!")
                        st.session_state.id_editando = None
                        st.rerun()
                if cancelar_edicao:
                    st.session_state.id_editando = None
                    st.rerun()
        else:
            st.session_state.id_editando = None
    else:
        st.markdown("#### ➕ Novo Ponto")
        if data_escolhida != hoje:
            st.warning("Cadastro manual disponível apenas para a **data de hoje**.")
        else:
            lat_default = st.session_state.clicked_lat if st.session_state.clicked_lat is not None else 0.0
            lon_default = st.session_state.clicked_lon if st.session_state.clicked_lon is not None else 0.0

            with st.form("form_novo_ponto", clear_on_submit=True):
                municipio	= st.text_input("Município *\t", value="Teresina")
                bairro = st.text_input("Bairro *", placeholder="Ex: Centro")

                c1, c2 = st.columns(2)
                with c1:
                    lat = st.number_input("Latitude *", format="%.6f", value=float(lat_default), step=0.000001)
                with c2:
                    lon = st.number_input("Longitude *", format="%.6f", value=float(lon_default), step=0.000001)

                pressao = st.number_input("Pressão (MCA) *", format="%.2f", value=0.00, min_value=0.0, step=0.1)
                enviado = st.form_submit_button("Cadastrar Ponto", type="primary", use_container_width=True)

                if enviado:
                    if not municipio	.strip() or not bairro.strip():
                        st.error("Município e Bairro são obrigatórios.")
                    elif lat == 0.0 and lon == 0.0:
                        st.error("Informe coordenadas válidas ou clique no mapa.")
                    else:
                        lat_n = normalizar_coordenada(lat, "lat")
                        lon_n = normalizar_coordenada(lon, "lon")
                        if lat_n is None or lon_n is None:
                            st.error("Coordenadas inválidas.")
                        else:
                            novo_id = adicionar_ponto(municipio	.strip(), bairro.strip(), lat_n, lon_n, pressao, data_para_str(hoje))
                            st.success(f"Ponto cadastrado! ID: {novo_id}")
                            st.session_state.clicked_lat = None
                            st.session_state.clicked_lon = None
                            st.rerun()

    st.divider()
    st.markdown("#### ⏱️ Atualização")
    intervalo = st.select_slider("Intervalo (segundos)", options=[0, 15, 30, 60, 120], value=30)
    if intervalo > 0:
        st_autorefresh(interval=intervalo * 1000, key="autorefresh")

# ============================================================
# ÁREA PRINCIPAL
# ============================================================
st.title("💧 Painel de Monitoramento de Baixa Pressão - COI")
st.caption(f"Visualizando: **{data_str_selecionada}**")

df = carregar_dados()
df_filtrado = df[df["Data"] == data_str_selecionada].copy() if not df.empty else df.copy()

if mun_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Municipio"] == mun_sel]
if bairro_sel != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Bairro"] == bairro_sel]

if faixa_sel == "Críticos (0 MCA)":
    df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] == 0]
elif faixa_sel == "Atenção (≤ 5 MCA)":
    df_filtrado = df_filtrado[(df_filtrado["Pressao_MCA"] > 0) & (df_filtrado["Pressao_MCA"] <= 5)]
elif faixa_sel == "Normais (> 5 MCA)":
    df_filtrado = df_filtrado[df_filtrado["Pressao_MCA"] > 5]

if not df_filtrado.empty:
    total = len(df_filtrado)
    criticos = len(df_filtrado[df_filtrado["Pressao_MCA"] == 0])
    atencao = len(df_filtrado[(df_filtrado["Pressao_MCA"] > 0) & (df_filtrado["Pressao_MCA"] <= 5)])
    normais = len(df_filtrado[df_filtrado["Pressao_MCA"] > 5])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de Ocorrências", total)
    k2.metric("Críticos (0 MCA)", criticos)
    k3.metric("Em Atenção (≤ 5 MCA)", atencao)
    k4.metric("Normais (> 5 MCA)", normais)
else:
    st.info("Nenhum ponto registrado para a data e filtros selecionados.")

st.divider()

# MAPA
st.subheader("🗺️ Mapa de Baixa Pressão")
c_map1, c_map2 = st.columns([1, 4])
with c_map1:
    mostrar_rotulos = st.checkbox("Exibir rótulos", value=False)
    if data_escolhida == hoje:
        st.session_state.modo_adicionar_mapa = st.checkbox(
            "📍 Modo adicionar ponto",
            value=st.session_state.modo_adicionar_mapa
        )

if not df_filtrado.empty and df_filtrado["Latitude"].notna().any():
    centro_lat = float(df_filtrado["Latitude"].mean())
    centro_lon = float(df_filtrado["Longitude"].mean())
    zoom = 13
else:
    centro_lat, centro_lon = LAT_BASE, LON_BASE
    zoom = 12

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles="OpenStreetMap")

if not df_filtrado.empty:
    validos = df_filtrado.dropna(subset=["Latitude", "Longitude"])
    for _, row in validos.iterrows():
        pressao = row["Pressao_MCA"]
        cor = "red" if pressao == 0 else ("orange" if pressao <= 5 else "blue")
        popup = f"<b>ID:</b> {row['ID']}<br><b>Bairro:</b> {row['Bairro']}<br><b>Pressão:</b> {pressao} MCA"
        
        marker_icon = folium.Icon(color=cor, icon="tint", prefix="fa")
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=folium.Popup(popup, max_width=250),
            tooltip=f"{row['Municipio']} - {row['Bairro']} ({pressao} MCA)",
            icon=marker_icon
        ).add_to(m)

        if mostrar_rotulos:
            texto_rotulo = f"{row['Bairro']} — {pressao} MCA"
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

map_data = st_folium(m, width="100%", height=520, returned_objects=["last_clicked"], key="mapa_principal")

if st.session_state.modo_adicionar_mapa and data_escolhida == hoje and map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    if clicked:
        st.session_state.clicked_lat = round(clicked["lat"], 6)
        st.session_state.clicked_lon = round(clicked["lng"], 6)
        st.success(f"📍 Coordenadas capturadas: {st.session_state.clicked_lat}, {st.session_state.clicked_lon}")
        st.rerun()

st.divider()

# TABELA
st.subheader("📋 Registro de Pontos")
if not df_filtrado.empty:
    df_show = df_filtrado[["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA"]].reset_index(drop=True)
    evento = st.dataframe(df_show, use_container_width=True, height=300, on_select="rerun", selection_mode="single-row", key="tabela_registros")
    
    linhas_selecionadas = evento.selection.rows if evento and evento.selection else []
    if linhas_selecionadas:
        idx = linhas_selecionadas[0]
        registro = df_show.iloc[idx]
        id_sel = str(registro["ID"])
        
        col_a, col_b, _ = st.columns([1, 1, 4])
        with col_a:
            if st.button("✏️ Editar", use_container_width=True):
                st.session_state.id_editando = id_sel
                st.rerun()
        with col_b:
            if st.button("🗑️ Excluir", use_container_width=True):
                if excluir_ponto(id_sel):
                    st.success("Excluído com sucesso.")
                    st.rerun()

# ============================================================
# ANALÍTICO: VARIAÇÃO DE PRESSÃO POR PERÍODO E BAIRRO
# ============================================================
st.divider()
st.subheader("📈 Análise de Tendência e Variação por Bairro")
st.markdown("Selecione um período e um bairro para acompanhar o histórico e a variação da pressão ao longo do tempo.")

if not df_all.empty:
    col_g1, col_g2, col_g3 = st.columns([2, 2, 2])
    
    with col_g1:
        data_inicio_padrao = hoje - timedelta(days=30)
        data_ini_analise = st.date_input("Data Inicial", value=data_inicio_padrao, format="DD/MM/YYYY", key="analise_ini")
    
    with col_g2:
        data_fim_analise = st.date_input("Data Final", value=hoje, format="DD/MM/YYYY", key="analise_fim")
        
    with col_g3:
        bairros_disponiveis = sorted(df_all["Bairro"].dropna().unique().tolist())
        bairro_analise = st.selectbox("Selecione o Bairro", bairros_disponiveis, key="analise_bairro")

    if data_ini_analise > data_fim_analise:
        st.error("A data inicial não pode ser maior que a data final.")
    else:
        df_tendencia = df_all[df_all["Bairro"] == bairro_analise].copy()
        
        if not df_tendencia.empty:
            df_tendencia["DataObj"] = pd.to_datetime(df_tendencia["Data"], format="%d/%m/%Y", errors="coerce")
            df_tendencia = df_tendencia.dropna(subset=["DataObj"])
            
            mask = (df_tendencia["DataObj"].dt.date >= data_ini_analise) & (df_tendencia["DataObj"].dt.date <= data_fim_analise)
            df_tendencia = df_tendencia.loc[mask].sort_values("DataObj")

            if not df_tendencia.empty:
                fig = px.line(
                    df_tendencia,
                    x="Data",
                    y="Pressao_MCA",
                    markers=True,
                    title=f"Evolução da Pressão (MCA) — {bairro_analise}",
                    labels={"Data": "Data do Registro", "Pressao_MCA": "Pressão (MCA)"},
                )
                
                fig.add_hline(y=5, line_dash="dash", line_color="orange", annotation_text="Limite de Atenção (5 MCA)", annotation_position="top left")
                fig.add_hline(y=0, line_dash="solid", line_color="red", annotation_text="Crítico (0 MCA)", annotation_position="bottom left")
                
                fig.update_traces(line_color="#0284c7", line_width=3, marker_size=8)
                fig.update_layout(xaxis_title="Data", yaxis_title="Pressão (MCA)", hovermode="x unified")
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"Nenhum registro encontrado para o bairro **{bairro_analise}** no período selecionado.")
        else:
            st.warning("Não há dados históricos suficientes para este bairro.")
else:
    st.info("Aguardando dados para gerar o gráfico de tendência.")
