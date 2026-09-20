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

# Estilização para otimizar espaço da barra lateral e fixar o botão no rodapé
st.markdown(
    """
    <style>
        /* Oculta navegação padrão do Streamlit */
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
        # Tenta carregar dos secrets do Streamlit
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

# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================
@st.cache_data(ttl=60)
def carregar_dados():
    client = conectar_gsheets()
    if not client:
        # DataFrame de fallback vazio caso não haja conexão configurada ainda
        return pd.DataFrame(columns=["Protocolo", "Data", "Município", "Bairro", "Status", "Lat", "Lon"])
    
    try:
        # Substitua pelo nome ou ID da sua planilha real
        sheet = client.open("Nome_Da_Sua_Planilha").worksheet("Ocorrencias")
        dados = sheet.get_all_records()
        df = pd.DataFrame(dados)
        return df
    except Exception as e:
        st.warning(f"Não foi possível carregar os dados da planilha: {e}")
        return pd.DataFrame(columns=["Protocolo", "Data", "Município", "Bairro", "Status", "Lat", "Lon"])

df_ocorrencias = carregar_dados()

# ============================================================
# BARRA LATERAL (FILTROS E NAVEGAÇÃO)
# ============================================================
with st.sidebar:
    st.title("🎛️ Painel de Controle")
    st.markdown("---")
    
    st.subheader("Filtros de Análise")
    
    # Filtro de Município
    municipios_disponiveis = sorted(df_ocorrencias["Município"].dropna().unique().tolist()) if "Município" in df_ocorrencias.columns and not df_ocorrencias.empty else ["Teresina", "Timon"]
    municipio_selecionado = st.selectbox(
        "Selecione o Município",
        options=["Selecione..."] + municipios_disponiveis
    )
    
    # Filtro de Bairro dinâmico com base no município ou geral
    bairros_disponiveis = sorted(df_ocorrencias["Bairro"].dropna().unique().tolist()) if "Bairro" in df_ocorrencias.columns and not df_ocorrencias.empty else ["Centro", "Ininga", "Fátima"]
    bairro_selecionado = st.selectbox(
        "Selecione o Bairro", 
        options=["Selecione..."] + bairros_disponiveis
    )
    
    periodo_selecionado = st.selectbox(
        "Selecione o Período", 
        options=["Selecione...", "Últimos 7 dias", "Últimos 30 dias", "Personalizado"]
    )
    
    # Espaçamento dinâmico para empurrar o botão para o final
    st.markdown("<br>" * 4, unsafe_allow_html=True)
    st.markdown("---")
    
    # Botão de voltar ao menu principal rigorosamente embaixo
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
    st.metric("Total de Ocorrências", len(df_ocorrencias))
with col2:
    st.metric("Em Andamento", len(df_ocorrencias[df_ocorrencias.get("Status", "") == "Em Andamento"]) if not df_ocorrencias.empty else 0)
with col3:
    st.metric("Finalizadas", len(df_ocorrencias[df_ocorrencias.get("Status", "") == "Finalizado"]) if not df_ocorrencias.empty else 0)

st.markdown("---")

# ============================================================
# MAPA E VISUALIZAÇÃO ESPACIAL
# ============================================================
st.subheader("Mapa Operacional de Ocorrências")

if not df_ocorrencias.empty and "Lat" in df_ocorrencias.columns and "Lon" in df_ocorrencias.columns:
    # Criação do mapa centrado (ex: Teresina)
    m = folium.Map(location=[-5.0892, -42.8019], zoom_start=13)
    for _, row in df_ocorrencias.dropna(subset=["Lat", "Lon"]).iterrows():
        folium.Marker(
            location=[row["Lat"], row["Lon"]],
            popup=f"Protocolo: {row.get('Protocolo', 'N/A')}<br>Bairro: {row.get('Bairro', 'N/A')}",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
    st_folium(m, width="100%", height=400)
else:
    st.info("Nenhuma coordenada geográfica disponível para exibição no mapa.")

st.markdown("---")

# ============================================================
# ANÁLISE DE TENDÊNCIA TEMPORAL (CONDICIONAL)
# ============================================================
st.subheader("Análise de Tendência Temporal")

# O gráfico só aparece se Município, Bairro e Período forem rigorosamente selecionados
if (municipio_selecionado != "Selecione..." and 
    bairro_selecionado != "Selecione..." and 
    periodo_selecionado != "Selecione..."):
    
    # Simulação de filtragem para o gráfico
    if not df_ocorrencias.empty and "Data" in df_ocorrencias.columns:
        df_filtrado = df_ocorrencias[
            (df_ocorrencias.get("Município", "") == municipio_selecionado) & 
            (df_ocorrencias.get("Bairro", "") == bairro_selecionado)
        ]
    else:
        # DataFrame demonstrativo caso a planilha esteja vazia ou em testes
        df_filtrado = pd.DataFrame({
            "Data": pd.date_range(start="2026-09-01", periods=10),
            "Ocorrências": [2, 4, 1, 6, 3, 5, 8, 2, 4, 3]
        })
    
    if not df_filtrado.empty:
        fig = px.line(
            df_filtrado, 
            x="Data" if "Data" in df_filtrado.columns else df_filtrado.index, 
            y="Ocorrências" if "Ocorrências" in df_filtrado.columns else df_filtrado.columns[0], 
            markers=True,
            title=f"Evolução - {bairro_selecionado} ({municipio_selecionado}) [{periodo_selecionado}]"
        )
        fig.update_layout(xaxis_title="Data", yaxis_title="Volume de Ocorrências")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    # Estado inicial limpo: sem dados prévios carregados
    st.info("👆 Selecione o **Município**, o **Bairro** e o **Período** na barra lateral para carregar a análise de tendência.")
