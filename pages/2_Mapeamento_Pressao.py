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
# CONSTANTES E ESTRUTURA DE COLUNAS
# ============================================================
LAT_BASE = -5.0892
LON_BASE = -42.8019
SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"
COLUNAS_PADRAO = ["Data", "Pontos", "Latitude", "Longitude", "MCA", "Observacao"]

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
            ws.append_row(["Data", "Pontos", "Latitude", "Longitude", "MCA", "Observação"])
    except Exception:
        pass
        
    return ws

try:
    worksheet = conectar_google_sheets()
except Exception as e:
    st.error(f"❌ Erro ao conectar com o Google Sheets: {e}")
    st.stop()

# ============================================================
# FUNÇÕES DE CONVERSÃO E TRATAMENTO DE DADOS
# ============================================================
def normalizar_coluna(nome: str) -> str:
    nome = str(nome).strip().lower()
    mapeamento = {
        "data": "Data",
        "pontos": "Pontos", "ponto": "Pontos",
        "latitude": "Latitude", "lat": "Latitude", 
        "longitude": "Longitude", "lon": "Longitude", "long": "Longitude",
        "mca": "MCA", "pressao": "MCA", "pressão": "MCA",
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

def normalizar_data(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", "nat", ""):
        return ""
    formatos = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto

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

    df["Data"] = df["Data"].apply(normalizar_data)
    df["Pontos"] = df["Pontos"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df["Latitude"] = df["Latitude"].apply(lambda x: normalizar_coordenada(x, "lat"))
    df["Longitude"] = df["Longitude"].apply(lambda x: normalizar_coordenada(x, "lon"))
    df["MCA"] = df["MCA"].apply(lambda x: parse_float(x, 0.0) or 0.0)
    df["Observacao"] = df["Observacao"].astype(str).str.strip().replace({"nan": "", "None": ""})
    df = df[df["Pontos"].astype(str).str.strip() != ""]

    return df[COLUNAS_PADRAO].reset_index(drop=True)

def limpar_cache():
    st.cache_data.clear()

def adicionar_ponto(data_str: str, pontos: str, lat: float, lon: float, mca: float, obs: str):
    worksheet.append_row([str(data_str), str(pontos), float(lat), float(lon), float(mca), str(obs)])
    time.sleep(0.3)
    limpar_cache()

def adicionar_lote_seguro(linhas_dados: list):
    if not linhas_dados:
        return 0
    
    df_atual = carregar_dados()
    chaves_existentes = set()
    if not df_atual.empty:
        for _, r in df_atual.iterrows():
            lat_f = f"{float(r['Latitude']):.6f}" if pd.notnull(r['Latitude']) else ""
            lon_f = f"{float(r['Longitude']):.6f}" if pd.notnull(r['Longitude']) else ""
            chave = (str(r["Data"]).strip(), str(r["Pontos"]).strip().lower(), lat_f, lon_f)
            chaves_existentes.add(chave)

    linhas_novas = []
    for linha in linhas_dados:
        d_val, p_val, lat_val, lon_val, mca_val, obs_val = linha
        lat_f = f"{float(lat_val):.6f}"
        lon_f = f"{float(lon_val):.6f}"
        chave_nova = (str(d_val).strip(), str(p_val).strip().lower(), lat_f, lon_f)
        
        if chave_nova not in chaves_existentes:
            linhas_novas.append(linha)
            chaves_existentes.add(chave_nova)

    if linhas_novas:
        dados_formatados = [[d, p, float(lat), float(lon), float(mca), obs] for d, p, lat, lon, mca, obs in linhas_novas]
        worksheet.append_rows(dados_formatados, value_input_option='USER_ENTERED')
        time.sleep(0.3)
        limpar_cache()
        return len(linhas_novas)
    return 0

def atualizar_ponto(linha_idx: int, data_str: str, pontos: str, lat: float, lon: float, mca: float, obs: str) -> bool:
    try:
        target_row = linha_idx + 2
        worksheet.update(f"A{target_row}:F{target_row}", [[str(data_str), str(pontos), float(lat), float(lon), float(mca), str(obs)]])
        time.sleep(0.3)
        limpar_cache()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar: {e}")
        return False

def excluir_ponto(linha_idx: int) -> bool:
    try:
        target_row = linha_idx + 2
        worksheet.delete_rows(target_row)
        time.sleep(0.3)
        limpar_cache()
        return True
    except Exception:
        return False

def data_para_str(d: date) -> str:
    return d.strftime("%d/%m/%Y")

def gerar_kml(df):
    kml = simplekml.Kml()
    for _, row in df.iterrows():
        lat = row.get("Latitude")
        lon = row.get("Longitude")
        if pd.notnull(lat) and pd.notnull(lon):
            try:
                kml.newpoint(
                    name=str(row.get("Pontos", "Ponto")),
                    description=f"Data: {row.get('Data', '')}\nPonto: {row.get('Pontos', '')}\nMCA: {row.get('MCA', '')}\nObservação: {row.get('Observacao', '')}",
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
if "dados_upload_pendentes" not in st.session_state:
    st.session_state.dados_upload_pendentes = None
if "nome_arquivo_pendente" not in st.session_state:
    st.session_state.nome_arquivo_pendente = None

# ============================================================
# DIALOGS (POP-UPS DE CADASTRO, EDIÇÃO E PRÉ-VISUALIZAÇÃO DE UPLOAD)
# ============================================================
@st.dialog("➕ Cadastrar Ponto de Pressão")
def modal_novo_ponto():
    lat_default = st.session_state.clicked_lat if st.session_state.clicked_lat is not None else 0.0
    lon_default = st.session_state.clicked_lon if st.session_state.clicked_lon is not None else 0.0

    with st.form("form_novo_ponto_modal", clear_on_submit=True):
        data_cadastro = st.date_input("Data do Registro", value=hoje, format="DD/MM/YYYY")
        pontos = st.text_input("Pontos / Local *", placeholder="Ex: Ponto A-01")

        c1, c2 = st.columns(2)
        with c1:
            lat = st.text_input("Latitude * (aceita vírgula ou ponto)", value=str(lat_default))
        with c2:
            lon = st.text_input("Longitude * (aceita vírgula ou ponto)", value=str(lon_default))

        mca = st.number_input("MCA *", format="%.2f", value=0.00, min_value=0.0, step=0.1)
        obs = st.text_input("Observação", placeholder="Ex: Válvula regulada")
        enviado = st.form_submit_button("Cadastrar Ponto", type="primary", use_container_width=True)

        if enviado:
            lat_n = normalizar_coordenada(lat, "lat")
            lon_n = normalizar_coordenada(lon, "lon")
            if not pontos.strip():
                st.error("O campo 'Pontos' é obrigatório.")
            elif lat_n is None or lon_n is None:
                st.error("Coordenadas inválidas. Verifique os valores de Latitude e Longitude.")
            else:
                adicionar_ponto(data_para_str(data_cadastro), pontos.strip(), lat_n, lon_n, mca, obs.strip())
                st.success("Ponto cadastrado com sucesso!")
                st.session_state.clicked_lat = None
                st.session_state.clicked_lon = None
                st.rerun()

@st.dialog("✏️ Editar Ponto de Pressão")
def modal_editar_ponto(idx_tabela: int):
    df_all = carregar_dados()
    if idx_tabela < len(df_all):
        reg_edit = df_all.iloc[idx_tabela]
        try:
            data_parsed = datetime.strptime(str(reg_edit["Data"]), "%d/%m/%Y").date()
        except ValueError:
            data_parsed = hoje

        with st.form("form_edicao_modal"):
            data_e = st.date_input("Data do Registro", value=data_parsed, format="DD/MM/YYYY")
            pontos_e = st.text_input("Pontos *", value=str(reg_edit["Pontos"]))
            c1, c2 = st.columns(2)
            with c1:
                lat_e = st.text_input("Latitude *", value=str(reg_edit["Latitude"] or LAT_BASE))
            with c2:
                lon_e = st.text_input("Longitude *", value=str(reg_edit["Longitude"] or LON_BASE))
            mca_e = st.number_input("MCA *", format="%.2f", value=float(reg_edit["MCA"] or 0.0), min_value=0.0, step=0.1)
            obs_e = st.text_input("Observação", value=str(reg_edit["Observacao"]))

            col_salvar, col_canc = st.columns(2)
            with col_salvar:
                salvar_edicao = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True)
            with col_canc:
                cancelar_edicao = st.form_submit_button("❌ Cancelar", use_container_width=True)

            if salvar_edicao:
                lat_n = normalizar_coordenada(lat_e, "lat")
                lon_n = normalizar_coordenada(lon_e, "lon")
                if lat_n is None or lon_n is None:
                    st.error("Coordenadas inválidas.")
                else:
                    if atualizar_ponto(idx_tabela, data_para_str(data_e), pontos_e, lat_n, lon_n, mca_e, obs_e):
                        st.success("Atualizado com sucesso!")
                        st.rerun()
            if cancelar_edicao:
                st.rerun()
    else:
        st.warning("Registro não encontrado.")

@st.dialog("📋 Pré-visualização da Planilha")
def modal_previa_upload():
    st.write(f"Arquivo carregado: **{st.session_state.nome_arquivo_pendente}**")
    df_preview = pd.DataFrame(st.session_state.dados_upload_pendentes, columns=["Data", "Pontos", "Latitude", "Longitude", "MCA", "Observacao"])
    st.dataframe(df_preview, use_container_width=True)
    st.info(f"Total de registros válidos prontos para envio: **{len(df_preview)}**")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("Confirmar e Enviar", type="primary", use_container_width=True):
            with st.spinner("Enviando registros com segurança para o Google Sheets..."):
                qtd_inserida = adicionar_lote_seguro(st.session_state.dados_upload_pendentes)
            
            st.session_state.dados_upload_pendentes = None
            st.session_state.nome_arquivo_pendente = None

            if qtd_inserida > 0:
                st.success(f"✅ {qtd_inserida} novos registros importados com sucesso!")
            else:
                st.info("ℹ️ Todos os registros da planilha já existiam no sistema. Nenhuma duplicação foi feita.")
            time.sleep(1)
            st.rerun()

    with col_btn2:
        if st.button("Cancelar", use_container_width=True):
            st.session_state.dados_upload_pendentes = None
            st.session_state.nome_arquivo_pendente = None
            st.rerun()

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
    if st.button("Adicionar Novo Ponto", type="primary", use_container_width=True):
        modal_novo_ponto()

    arquivo_upload = st.file_uploader("📂 Enviar Planilha (XLSX/CSV)", type=["xlsx", "csv"], key="upload_mapeamento")
    
    if arquivo_upload is not None:
        if st.session_state.nome_arquivo_pendente != arquivo_upload.name:
            try:
                if arquivo_upload.name.endswith('.csv'):
                    df_up = pd.read_csv(arquivo_upload)
                else:
                    df_up = pd.read_excel(arquivo_upload)
                
                lote_para_enviar = []
                for _, row in df_up.iterrows():
                    raw_data = row.get("Data", row.get("date", ""))
                    data_val = normalizar_data(raw_data)
                    if not data_val:
                        data_val = data_str_selecionada

                    ponto_val = str(row.get("Pontos", row.get("Ponto", "")))
                    lat_val = normalizar_coordenada(row.get("Latitude", row.get("Lat")), "lat")
                    lon_val = normalizar_coordenada(row.get("Longitude", row.get("Lon")), "lon")
                    mca_val = parse_float(row.get("MCA", row.get("Pressao", 0.0)), 0.0)
                    obs_val = str(row.get("Observação", row.get("Observacao", "")))
                    
                    if ponto_val.strip() and lat_val is not None and lon_val is not None:
                        lote_para_enviar.append([data_val, ponto_val.strip(), float(lat_val), float(lon_val), float(mca_val), obs_val])

                if lote_para_enviar:
                    st.session_state.dados_upload_pendentes = lote_para_enviar
                    st.session_state.nome_arquivo_pendente = arquivo_upload.name
                else:
                    st.warning("⚠️ Nenhum registro válido encontrado. Verifique se os nomes das colunas são: Data, Pontos, Latitude, Longitude, MCA, Observação.")
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {e}")

    if st.session_state.dados_upload_pendentes is not None:
        modal_previa_upload()

    st.divider()

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
    intervalo = st.select_slider("Intervalo (segundos)", options=[0, 15, 30, 60, 120], value=60)
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
st.caption(f"Visualizando dados da data: **{data_str_selecionada}**")

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
    st.info(f"Nenhum ponto registrado para a data {data_str_selecionada} com os filtros selecionados.")

st.divider()

# ============================================================
# MAPA COM SELETOR DE TIPO DE MAPA (APENAS OS 3 FUNCIONAIS)
# ============================================================
st.subheader("🗺️ Mapa de Mapeamento de Pressão")

c_map1, c_map2, c_map3 = st.columns([2, 2, 2])
with c_map1:
    tipo_mapa = st.selectbox(
        "🗺️ Tipo de Mapa",
        options=[
            "Mapa Padrão (OpenStreetMap)",
            "Satélite (Esri World Imagery)",
            "Terreno (OpenTopoMap)"
        ],
        key="seletor_tipo_mapa"
    )
with c_map2:
    mostrar_rotulos = st.checkbox("Exibir rótulos", value=False)
with c_map3:
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

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom, tiles=None)

if "Satélite" in tipo_mapa:
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        name='Satélite (Esri World Imagery)'
    ).add_to(m)
elif "Terreno" in tipo_mapa:
    folium.TileLayer('OpenTopoMap', name='Terreno (OpenTopoMap)').add_to(m)
else:
    folium.TileLayer('OpenStreetMap', name='Mapa Padrão (OpenStreetMap)').add_to(m)

if not df_filtrado.empty:
    validos = df_filtrado.dropna(subset=["Latitude", "Longitude"])
    for idx_v, row in validos.iterrows():
        mca = row["MCA"]
        cor = "red" if mca == 0 else ("orange" if mca <= 5 else "blue")
        popup = f"<b>Data:</b> {row['Data']}<br><b>Ponto:</b> {row['Pontos']}<br><b>MCA:</b> {mca}<br><b>Obs:</b> {row['Observacao']}"
        
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

if st.session_state.modo_adicionar_mapa and map_data and map_data.get("last_clicked"):
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
    df_show = df_filtrado[["Data", "Pontos", "Latitude", "Longitude", "MCA", "Observacao"]].reset_index(drop=True)
    evento = st.dataframe(df_show, use_container_width=True, height=300, on_select="rerun", selection_mode="single-row", key="tabela_registros_map")
    
    linhas_selecionadas = evento.selection.rows if evento and evento.selection else []
    if linhas_selecionadas:
        idx = linhas_selecionadas[0]
        col_a, col_b, _ = st.columns([1, 1, 4])
        with col_a:
            if st.button("✏️ Editar", use_container_width=True):
                modal_editar_ponto(idx)
        with col_b:
            if st.button("🗑️ Excluir", use_container_width=True):
                if excluir_ponto(idx):
                    st.success("Excluído com sucesso.")
                    st.rerun()
else:
    st.info(f"Nenhum ponto registrado para a data {data_str_selecionada} com os filtros selecionados.")
