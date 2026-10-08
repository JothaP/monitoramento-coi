import io
import os
import re
import math
import hashlib
import zipfile
import unicodedata
from datetime import datetime, date
import xml.etree.ElementTree as ET

import gspread
import pandas as pd
import streamlit as st
import folium
import plotly.express as px

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Farol Operacional",
    layout="wide",
    initial_sidebar_state="expanded",
)

verificar_autenticacao()

SPREADSHEET_ID = "1l0IcsO1GgPYcs8DPRPI6_lKdSCM9vWOypcrwIMJ96QY"

NOME_ABA_POCOS = "POCOS"
NOME_ABA_LOGGERS = "LOGGERS"
NOME_ABA_PONTOS = "PONTOS"
NOME_ABA_EVENTOS = "EVENTOS"

ARQUIVO_KMZ_PADRAO = "TERESINA.kmz"
RAIO_OPERACIONAL_PADRAO = 500
RAIO_CONCENTRACAO_PADRAO = 500

CABECALHO_POCOS = [
    "ID_POCO",
    "IDENTIFICACAO_ATIVO",
    "NOME_POCO",
    "MUNICIPIO",
    "LATITUDE",
    "LONGITUDE",
]

CABECALHO_LOGGERS = [
    "ID_LOGGER",
    "IDENTIFICACAO_ATIVO",
    "ENDERECO",
    "MUNICIPIO",
    "LATITUDE",
    "LONGITUDE",
]

CABECALHO_PONTOS = [
    "Empresa",
    "Dt. Emissão",
    "Nº da O.S",
    "Matrícula",
    "Cidade",
    "Bairro",
    "Serviço Executado",
    "Status OS",
    "Atendente",
    "Latitude",
    "Longitude",
]

CABECALHO_EVENTOS = [
    "Data",
    "Controlador",
    "Status",
    "Unidade",
    "Cidade",
    "Regional",
    "Código do Ativo",
    "Serviço",
    "Equipe",
    "Supervisor",
    "Líder",
    "Oracle Field",
    "SAP",
    "Protocolo",
    "Link de Localização",
    "Início",
    "Prev. Término",
    "Término Real",
