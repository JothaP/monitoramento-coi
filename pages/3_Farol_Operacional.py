import io
import csv
import json
import os
import re
import math
import hashlib
import zipfile
import sqlite3
import threading
import tempfile
import time as tempo_execucao
import shutil
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from html import escape as html_escape
from zoneinfo import ZoneInfo
import unicodedata
from datetime import datetime, date, time as horario
import xml.etree.ElementTree as ET

import gspread
import pandas as pd
import numpy as np
import streamlit as st
import folium
import plotly.express as px
from shapely import wkb
from shapely.ops import transform as transformar_geometria
from pyproj import CRS, Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.graphics.shapes import Drawing, Circle, String, Rect, PolyLine
from reportlab.pdfbase.ttfonts import TTFont

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium
from branca.element import Element

from auth import verificar_autenticacao, tem_acesso_modulo


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Farol Operacional - Módulo 3",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not verificar_autenticacao() or not tem_acesso_modulo("3"):
    st.error("Acesso negado ao Farol Operacional. Entre pelo Hub Central com um perfil autorizado.")
    st.stop()

PERFIL_FAROL = str(st.session_state.get("perfil", "")).strip().lower()
PODE_EDITAR_FAROL = PERFIL_FAROL in {"admin", "usuario"}

def exigir_edicao_farol():
    """Bloqueia mutações mesmo quando funções são chamadas sem seus botões."""
    if not PODE_EDITAR_FAROL:
        raise PermissionError("Seu perfil permite apenas consultar o Farol Operacional.")

SPREADSHEET_ID = "1l0IcsO1GgPYcs8DPRPI6_lKdSCM9vWOypcrwIMJ96QY"

NOME_ABA_POCOS = "POCOS"
NOME_ABA_LOGGERS = "LOGGERS"
NOME_ABA_PONTOS = "PONTOS"
NOME_ABA_EVENTOS = "EVENTOS"
NOME_ABA_CONTROLE = "CONTROLE_FAROL"
NOME_ABA_OBSERVACOES = "OBS_CONCENTRACOES"
NOME_ABA_AREAS_PROTEGIDAS = "FAROL_AREAS_EDITADAS"
NOME_ABA_ATUALIZACOES = "FAROL_ATUALIZACOES"
FUSO_FAROL = ZoneInfo("America/Fortaleza")  # Teresina: UTC-3
RESET_HORARIO = horario(0, 1)
_RESET_LOCK = threading.Lock()

RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRETORIO_KMZ = os.path.join(RAIZ_PROJETO, "geodados", "municipios")
DIRETORIO_DADOS = os.path.join(RAIZ_PROJETO, "dados")
ARQUIVO_POCOS_CSV = os.path.join(DIRETORIO_DADOS, "pocos.csv")
ARQUIVO_LOGGERS_CSV = os.path.join(DIRETORIO_DADOS, "loggers.csv")
ARQUIVO_KMZ_PADRAO = os.path.join(RAIZ_PROJETO, "TERESINA.kmz")  # Compatibilidade com instalação anterior
RAIO_OPERACIONAL_PADRAO = 500
RAIO_CONCENTRACAO_PADRAO = 500

CABECALHO_POCOS = [
    "ID_POCO",
    "IDENTIFICACAO_ATIVO",
    "NOME_POCO",
