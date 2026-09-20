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
    initial_sidebar_state="expanded"
)

# Estilização CSS para otimizar espaço da barra lateral e ocultar menu padrão
st.markdown(
    """
    <style>
        /* Oculta navegação padrão automática do Streamlit */
        [data-testid="stSidebarNav"] {
            display: none !important;
        }
        
        /* Otimização de espaçamento interno da sidebar */
        [data-testid="stSidebar"] div.block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# CONFIGURAÇÃO DE CREDENCIAIS E CONEXÃO (GOOGLE SHEETS)
# ============================================================
@st.cache_resource
def conectar_gsheets():
    try:
        if "gcp_service_account" in st.secrets:
            secret_dict = dict(st.secrets["gcp_service_account"])
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(secret_dict, scopes=scope)
            client = gspread.authorize(creds)
            return client
    except Exception as e:
        st.error(f"Erro ao conectar com as credenciais do Streamlit: {e}")
    return None

@st.cache_data(ttl=60)
def carregar_dados():
    client = conectar_gsheets()
    if not client:
        return pd.DataFrame(columns=["Protocolo", "Data", "Município", "Bairro", "Status", "Lat", "Lon"])
    try:
        sheet = client.open("Nome_Da_Sua_Planilha").worksheet("Ocorrencias")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        return df
    except Exception as e:
        st.warning(f"Aviso ao carregar dados da planilha: {e}")
        return pd.DataFrame(columns=["Protocolo", "Data", "Município", "Bairro", "Status", "Lat", "Lon"])

df_ocorrencias = carregar_dados()

# ============================================================
# FUNÇÕES DE SUPORTE E EXPORTAÇÃO (KML)
# ============================================================
def gerar_kml(df):
    kml = simplekml.Kml()
    for _, row in df.iterrows():
        lat = row.get("Lat")
        lon = row.get("Lon")
        if pd.notnull(lat) and pd.notnull(lon):
            try:
                kml.newpoint(
                    name=str(row.get("Protocolo", "Ocorrência")),
                    description=f"Município: {row.get('Município', '')}\nBairro: {row.get('Bairro', '')}\nStatus: {row.get('Status', '')}",
                    coords=[(float(lon), float(lat))]
                )
            except (ValueError, TypeError):
                continue
    return kml.kml()

# ============================================================
# BARRA LATERAL (FILTROS E NAVEGAÇÃO)
# ============================================================
with st.sidebar:
    st.title("🎛️ Painel de Controle")
    st.markdown("---")
    
    st.subheader("Filtros de Análise")
    
    # Extração dinâmica e segura dos filtros
    municipios_disponiveis = sorted(df_ocorrencias["Município"].dropna().unique().tolist()) if not df_ocorrencias.empty and "Município" in df_ocorrencias.columns else ["Teresina", "Timon"]
    municipio_selecionado = st.selectbox(
        "Selecione o Município",
        options=["Selecione..."] + municipios_disponiveis
    )
    
    bairros_disponiveis = sorted(df_ocorrencias["Bairro"].dropna().unique().tolist()) if not df_ocorrencias.empty and "Bairro" in df_ocorrencias.columns else ["Centro", "Ininga", "Fátima"]
    bairro_selecionado = st.selectbox(
        "Selecione o Bairro", 
        options=["Selecione..."] + bairros_disponiveis
    )
    
    periodo_selecionado = st.selectbox(
        "Selecione o Período", 
        options=["Selecione...", "Últimos 7 dias", "Últimos 30 dias", "Personalizado"]
    )
    
    st.markdown("---")
    
    # Botão de Download do KML
    if not df_ocorrencias.empty:
        kml_data = gerar_kml(df_ocorrencias)
        st.download_button(
            label="📥 Baixar KML das Ocorrências",
            data=kml_data,
            file_name="ocorrencias_baixa_pressao.kml",
            mime="application/vnd.google-earth.kml+xml",
            use_container_width=True
        )
    
    # Espaçamento dinâmico para empurrar o botão de voltar para o final absoluto da barra lateral
    st.markdown("<br>" * 3, unsafe_allow_html=True)
    st.markdown("---")
    
    # Botão de voltar ao menu principal posicionado rigorosamente embaixo
    if st.button("⬅️ Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")

# ============================================================
# CORPO PRINCIPAL DO MÓDULO
# ============================================================
st.header("💧 Monitoramento de Baixa Pressão - COI")
st.markdown("Acompanhamento operacional de ocorrências, chamados e tendências temporais.")
st.markdown("---")

# Seção de Métricas Rápidas
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total de Ocorrências", len(df_ocorrencias) if not df_ocorrencias.empty else 0)
with col2:
    em_andamento = len(df_ocorrencias[df_ocorrencias.get("Status", pd.Series()) == "Em Andamento"]) if not df_ocorrencias.empty else 0
    st.metric("Em Andamento", em_andamento)
with col3:
    finalizadas = len(df_ocorrencias[df_ocorrencias.get("Status", pd.Series()) == "Finalizado"]) if not df_ocorrencias.empty else 0
    st.metric("Finalizadas", finalizadas)

st.markdown("---")

# ============================================================
# MAPA OPERACIONAL DE OCORRÊNCIAS
# ============================================================
st.subheader("Mapa Operacional de Ocorrências")

if not df_ocorrencias.empty and "Lat" in df_ocorrencias.columns and "Lon" in df_ocorrencias.columns:
    m = folium.Map(location=[-5.0892, -42.8019], zoom_start=13)
    for _, row in df_ocorrencias.dropna(subset=["Lat", "Lon"]).iterrows():
        try:
            folium.Marker(
                location=[float(row["Lat"]), float(row["Lon"])],
                popup=f"Protocolo: {row.get('Protocolo', 'N/A')}<br>Bairro: {row.get('Bairro', 'N/A')}<br>Status: {row.get('Status', 'N/A')}",
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(m)
        except (ValueError, TypeError):
            continue
    st_folium(m, width="100%", height=450)
else:
    st.info("Nenhuma coordenada geográfica disponível no momento para exibição no mapa.")

st.markdown("---")

# ============================================================
# ANÁLISE DE TENDÊNCIA TEMPORAL (CONDICIONAL)
# ============================================================
st.subheader("Análise de Tendência Temporal")

# O gráfico só é renderizado após a seleção estrita de Município, Bairro e Período
if (municipio_selecionado != "Selecione..." and 
    bairro_selecionado != "Selecione..." and 
    periodo_selecionado != "Selecione..."):
    
    # Filtragem dos dados para o gráfico com base nas seleções
    if not df_ocorrencias.empty and "Data" in df_ocorrencias.columns:
        df_filtrado = df_ocorrencias[
            (df_ocorrencias.get("Município", "") == municipio_selecionado) & 
            (df_ocorrencias.get("Bairro", "") == bairro_selecionado)
        ]
    else:
        df_filtrado = pd.DataFrame()
    
    if not df_filtrado.empty:
        fig = px.line(
            df_filtrado, 
            x="Data", 
            y="Ocorrências" if "Ocorrências" in df_filtrado.columns else df_filtrado.columns[0], 
            markers=True,
            title=f"Evolução Temporal - {bairro_selecionado} ({municipio_selecionado}) [{periodo_selecionado}]"
        )
        fig.update_layout(xaxis_title="Data", yaxis_title="Volume de Ocorrências")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    # Estado inicial limpo: sem dados prévios carregados na tela
    st.info("👆 Selecione o **Município**, o **Bairro** e o **Período** na barra lateral para carregar a análise de tendência.")
