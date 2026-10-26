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
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from html import escape as html_escape
from zoneinfo import ZoneInfo
import unicodedata
from datetime import datetime, date, timedelta, time as horario
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

# Importações de módulos auxiliares na raiz do repositório Streamlit.
_RAIZ_IMPORT = str(Path(__file__).resolve().parent.parent)
if _RAIZ_IMPORT not in sys.path:
    sys.path.insert(0, _RAIZ_IMPORT)

from auth import verificar_autenticacao, tem_acesso_modulo
from farol_graficos_temporarios import (
    data_hoje as dia_graficos, indice_do_dia, salvar_grafico, excluir_grafico,
    chave_logger, rotulo_logger, filtrar_loggers,
)
from integracao_acompanhamento_producao import (chave_concentracao, localizar_vinculo, listar_vinculos, dados_acompanhamento, historico_evento, texto_pdf)
from acompanhamento_operacional_farol import popup_acompanhamento_farol


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Farol Operacional — Módulo 3",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Módulo 3 — produção. Perfil operador: somente leitura.
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Entre pelo Hub Central.")
    st.stop()

PERFIL_FAROL = str(st.session_state.get("perfil", "")).strip().lower()
if PERFIL_FAROL not in {"admin", "usuario", "operador"}:
    st.error("Seu perfil não está autorizado a acessar o Farol Operacional.")
    st.stop()

PODE_EDITAR_FAROL = PERFIL_FAROL in {"admin", "usuario"}

def exigir_edicao_farol():
    """Bloqueia mutações mesmo quando funções são chamadas sem seus botões."""
    if not PODE_EDITAR_FAROL:
        raise PermissionError("Seu perfil permite apenas consultar o Farol Operacional.")

# Fontes independentes: Farol (mapa/O.S./eventos) e Acompanhamento (fichas/histórico).
SPREADSHEET_ID = str(st.secrets.get("farol_producao_spreadsheet_id", "")).strip()
SPREADSHEET_ID_DEMO_CONHECIDO = "1plvaCyZ23zAIjasrFnJxZm9Q-jB85AbCtSjIizhuoKg"
ID_PLANILHA_ACOMP = str(st.secrets.get("acompanhamento_operacional_spreadsheet_id", "")).strip()
if not SPREADSHEET_ID or SPREADSHEET_ID == SPREADSHEET_ID_DEMO_CONHECIDO:
    st.error("Configure farol_producao_spreadsheet_id com o ID da planilha de produção.")
    st.stop()
if not ID_PLANILHA_ACOMP or ID_PLANILHA_ACOMP == SPREADSHEET_ID:
    st.error("Configure acompanhamento_operacional_spreadsheet_id com uma OUTRA planilha Google Sheets, independente da planilha do Farol.")
    st.stop()
