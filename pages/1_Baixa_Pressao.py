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
        
        /* Espaçamento elegante para elementos da barra lateral */
        .sidebar-content {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ============================================================
# BARRA LATERAL (FILTROS E NAVEGAÇÃO)
# ============================================================
with st.sidebar:
    st.title("🎛️ Painel de Controle")
    st.markdown("---")
    
    # Exemplo de Filtros
    st.subheader("Filtros de Análise")
    
    # Listas de exemplo (substitua pelas suas fontes de dados reais do app)
    lista_bairros = ["Centro", "Ininga", "Fátima", "São Cristóvão", "Morada do Sol"]
    
    bairro_selecionado = st.selectbox(
        "Selecione o Bairro", 
        options=["Selecione..."] + lista_bairros
    )
    
    periodo_selecionado = st.selectbox(
        "Selecione o Período", 
        options=["Selecione...", "Últimos 7 dias", "Últimos 30 dias", "Personalizado"]
    )
    
    # Espaçador flexível para empurrar o botão para o final da barra lateral
    st.markdown("<br>" * 6, unsafe_allow_html=True)
    st.markdown("---")
    
    # Botão de voltar ao menu principal posicionado rigorosamente embaixo
    if st.button("⬅️ Voltar ao Menu Principal", use_container_width=True):
        st.switch_page("app.py")  # Ajuste para o arquivo principal do seu menu se necessário

# ============================================================
# CORPO PRINCIPAL DO MÓDULO
# ============================================================
st.header("💧 Monitoramento de Baixa Pressão - COI")
st.markdown("Acompanhamento operacional de ocorrências e tendências por região.")

# Exemplo de dados fictícios para demonstração do gráfico
df_exemplo = pd.DataFrame({
    "Data": pd.date_range(start="2026-09-01", periods=10),
    "Ocorrências": [5, 8, 3, 12, 7, 6, 9, 4, 2, 5],
    "Bairro": ["Ininga"] * 10
})

st.markdown("---")
st.subheader("Análise de Tendência Temporal")

# Lógica para exibir o gráfico somente se ambos os filtros estiverem preenchidos
if bairro_selecionado != "Selecione..." and periodo_selecionado != "Selecione...":
    # Filtragem baseada na seleção (exemplo simplificado)
    df_filtrado = df_exemplo[df_exemplo["Bairro"] == bairro_selecionado]
    
    if not df_filtrado.empty:
        fig = px.line(
            df_filtrado, 
            x="Data", 
            y="Ocorrências", 
            markers=True,
            title=f"Evolução de Ocorrências - {bairro_selecionado} ({periodo_selecionado})"
        )
        fig.update_layout(xaxis_title="Data", yaxis_title="Número de Ocorrências")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
else:
    # Estado inicial: sem dados prévios carregados
    st.info("👆 Selecione um **Bairro** e um **Período** na barra lateral para carregar a análise de tendência.")
