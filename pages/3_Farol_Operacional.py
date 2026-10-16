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
    page_title="Farol Operacional V2 - Demonstração (Módulo 7)",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Módulo 7 de demonstração: apenas admin e usuario.
# Dados totalmente separados da planilha de produção.
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Entre pelo Hub Central.")
    st.stop()

PERFIL_FAROL = str(st.session_state.get("perfil", "")).strip().lower()
if PERFIL_FAROL not in {"admin", "usuario"}:
    st.error("Seu perfil não está autorizado a acessar o Farol Operacional.")
    st.stop()

PODE_EDITAR_FAROL = PERFIL_FAROL in {"admin", "usuario"}

def exigir_edicao_farol():
    """Bloqueia mutações mesmo quando funções são chamadas sem seus botões."""
    if not PODE_EDITAR_FAROL:
        raise PermissionError("Seu perfil permite apenas consultar o Farol Operacional.")

# Definir em Streamlit Cloud > App settings > Secrets:
# farol_v2_spreadsheet_id = "ID_DA_COPIA_DA_PLANILHA"
# Não utilizar a planilha de produção como fallback.
SPREADSHEET_ID_PRODUCAO = "1l0IcsO1GgPYcs8DPRPI6_lKdSCM9vWOypcrwIMJ96QY"
SPREADSHEET_ID = str(st.secrets.get("farol_v2_spreadsheet_id", "")).strip()
if not SPREADSHEET_ID or SPREADSHEET_ID == SPREADSHEET_ID_PRODUCAO:
    st.error("Módulo 7 protegido: configure farol_v2_spreadsheet_id com o ID de uma CÓPIA independente da planilha de produção em Secrets.")
    st.stop()

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
    "Nº da O.S",
    "Matrícula",
    "Cidade",
    "Bairro",
    "Latitude",
    "Longitude",
    "Status OS",
    "Dt. Emissão",
    "Serviço Executado",
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
    "Tempo de Atendimento",
    "Prazo de Normalização",
    "Áreas Impactadas",
    "Economias Afetadas",
    "% Economias",
    "Governança",
    "Descrição do Serviço",
    "Data de Criação",
]


# ============================================================
# NORMALIZAÇÃO / UTILITÁRIOS
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def normalizar_cabecalho(valor):
    texto = normalizar_texto(valor)
    texto = texto.replace("º", "O")
    texto = re.sub(r"[^A-Z0-9]+", "", texto)
    return texto


def limpar_valor(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, (pd.Timestamp, datetime, date)):
        return valor.strftime("%d/%m/%Y %H:%M:%S") if hasattr(valor, "hour") else valor.strftime("%d/%m/%Y")
    texto = str(valor).strip()
    if texto.lower() in {"nan", "nat", "none"}:
        return ""
    return texto


def parse_float(valor):
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return None
    texto = str(valor).strip().replace(" ", "")
    if not texto:
        return None
    try:
        # Trata 5,1234 e 5.1234, além de 1.234,56.
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        else:
            texto = texto.replace(",", ".")
        return float(texto)
    except Exception:
        return None


def novo_id(prefixo):
    return f"{prefixo}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def distancia_metros(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except Exception:
        return None

    raio = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * raio * math.asin(min(1, math.sqrt(a)))


def distancia_formatada(metros):
    if metros is None:
        return ""
    if metros < 1000:
        return f"{metros:.0f} m"
    return f"{metros / 1000:.2f} km"


def slug_hash(*valores):
    base = "|".join(normalizar_texto(v) for v in valores)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def limpar_nome_bairro(valor):
    texto = normalizar_texto(valor)
    texto = re.sub(r"\s*\(\s*PARCIAL\s*\)\s*$", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" \t.,;:!?")
    return texto


def indice_nomes_bairros(bairros_geograficos, municipio):
    """Catálogo restrito ao município, sem correspondência aproximada arriscada."""
    cidade = normalizar_municipio(municipio)
    nomes = set()
    for item in (bairros_geograficos or []):
        if normalizar_municipio(item.get("municipio", "")) == cidade:
            nome = limpar_nome_bairro(item.get("nome_normalizado") or item.get("nome"))
            if nome:
                nomes.add(nome)
    return nomes


def resolver_nome_bairro(nome, nomes_disponiveis):
    """Equivalência conservadora: nomes exatos ou prefixo genérico 'Bairro'."""
    chave = limpar_nome_bairro(nome)
    if chave in nomes_disponiveis:
        return chave
    sem_prefixo = re.sub(r"^BAIRRO\s+", "", chave).strip()
    if sem_prefixo and sem_prefixo in nomes_disponiveis:
        return sem_prefixo
    return chave


def evento_abrange_municipio(valor):
    """Identifica abrangência municipal explícita, sem inferir por bairro vazio."""
    texto = normalizar_texto(valor)
    return bool(re.search(
        r"\b(?:TODO\s+O\s+MUNICIPIO|MUNICIPIO\s+INTEIRO|"
        r"TODA\s+A\s+CIDADE|CIDADE\s+INTEIRA|"
        r"TODO\s+O\s+TERRITORIO\s+MUNICIPAL|"
        r"TODOS\s+OS\s+BAIRROS)\b", texto
    ))


def extrair_bairros_evento(valor, municipio="", bairros_geograficos=None):
    """Lê bairros em listas, linhas e rótulos; separa 'e' só se ambos existirem no GPKG.

    Nunca usa fuzzy matching nem divide nomes compostos sem confirmação.
    Retorna chaves normalizadas para mapa, cruzamento de O.S. e relatórios.
    """
    if valor is None or str(valor).strip().lower() in ("", "nan", "none"):
        return []
    nomes = indice_nomes_bairros(bairros_geograficos, municipio)
    if evento_abrange_municipio(valor):
        return [{"bairro": nome, "parcial": False, "original": "Todo o município"}
                for nome in sorted(nomes)]
    texto = str(valor).replace("\r", "\n")
    texto = re.sub(r"(?i)\bBAIRROS?\s*(?:IMPACTADOS?|AFETADOS?)?\s*:", "\n", texto)
    texto = re.sub(r"(?i)\bAREAS?\s+IMPACTADAS?\s*:", "\n", texto)
    partes = re.split(r"[,;\n]+", texto)
    saida = []
    vistos = set()
    for parte in partes:
        original = parte.strip(" \t-*•.,;:!?")
        if not original:
            continue
        # Desconsidera linha isolada com o nome da cidade, quando a descrição o inclui.
        if municipio and normalizar_municipio(original) == normalizar_municipio(municipio):
            continue
        parcial = bool(re.search(r"\(\s*PARCIAL\s*\)", original, flags=re.I))
        chave = resolver_nome_bairro(original, nomes)
        candidatos = [(chave, original)]
        if nomes and chave not in nomes:
            # Só divide a conjunção quando TODOS os nomes resultantes existem
            # no catálogo geográfico do município. Preserva nomes compostos.
            pedacos = [resolver_nome_bairro(p, nomes) for p in re.split(r"\s+E\s+", chave)]
            if len(pedacos) >= 2 and all(p in nomes for p in pedacos):
                candidatos = [(p, p) for p in pedacos]
        for bairro, origem in candidatos:
            if bairro and bairro not in vistos:
                vistos.add(bairro)
                saida.append({"bairro": bairro, "parcial": parcial, "original": origem})
    return saida


# ============================================================
# GOOGLE SHEETS
# ============================================================

@st.cache_resource(show_spinner=False)
def obter_cliente_google():
    dados = st.secrets["gcp_json"]
    if isinstance(dados, str):
        dados = json.loads(dados)
    else:
        dados = dict(dados)
    credenciais = Credentials.from_service_account_info(
        dados,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(credenciais)


@st.cache_resource(show_spinner=False)
def obter_planilha(spreadsheet_id):
    planilha = obter_cliente_google().open_by_key(spreadsheet_id)

    return planilha


def obter_aba(nome, cabecalho):
    planilha = obter_planilha(SPREADSHEET_ID)
    if planilha.id != SPREADSHEET_ID:
        st.error("Conexão bloqueada: planilha diferente da configurada para o Farol.")
        st.stop()

    try:
        aba = planilha.worksheet(nome)

    except gspread.WorksheetNotFound:
        st.error(
            f"ABA NÃO ENCONTRADA: {nome} | "
            f"PLANILHA: {planilha.title} | "
            f"ID: {planilha.id}"
        )
        st.stop()

    valores = aba.get_all_values()
    if not valores:
        if PODE_EDITAR_FAROL:
            aba.update("A1", [cabecalho])
    elif [normalizar_cabecalho(x) for x in valores[0]] != [normalizar_cabecalho(x) for x in cabecalho]:
        # Não apaga dados existentes. Apenas garante que as colunas mínimas estejam presentes.
        cab_atual = valores[0]
        faltantes = [c for c in cabecalho if normalizar_cabecalho(c) not in {normalizar_cabecalho(x) for x in cab_atual}]
        if faltantes and PODE_EDITAR_FAROL:
            nova_linha = cab_atual + faltantes
            aba.resize(cols=max(aba.col_count, len(nova_linha)))
            aba.update("A1", [nova_linha])
    return aba


@st.cache_resource(ttl=600, show_spinner=False)
def obter_aba_para_leitura(nome, spreadsheet_id):
    """Reutiliza o objeto Worksheet; não lê toda a planilha para conferir cabeçalhos."""
    planilha = obter_planilha(SPREADSHEET_ID)
    if planilha.id != SPREADSHEET_ID:
        raise PermissionError("A planilha conectada não é a planilha autorizada do Farol.")
    return planilha.worksheet(nome)


@st.cache_data(ttl=60, show_spinner=False)
def carregar_aba(nome, cabecalho, spreadsheet_id=None):
    aba = obter_aba_para_leitura(nome, spreadsheet_id or SPREADSHEET_ID)
    # Preserva as vírgulas decimais das coordenadas (ex.: -5,18817).
    # A conversão automática do gspread interpreta a vírgula como milhar
    # e transforma -5,18817 em -518817, invalidando os marcadores.
    registros = aba.get_all_records(numericise_ignore=["all"])
    if not registros:
        return pd.DataFrame(columns=cabecalho)
    return pd.DataFrame(registros)


@st.cache_data(show_spinner=False, max_entries=8)
def carregar_cadastro_local(caminho, assinatura, cabecalho):
    """Lê o CSV versionado no GitHub; a assinatura atualiza o cache após um deploy."""
    del assinatura
    try:
        dados = pd.read_csv(caminho, sep=",", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except UnicodeDecodeError as erro:
        raise ValueError(f"Arquivo CSV precisa estar em UTF-8: {os.path.basename(caminho)}") from erro
    faltantes = [col for col in cabecalho if col not in dados.columns]
    if faltantes:
        raise ValueError(f"{os.path.basename(caminho)}: colunas ausentes: {', '.join(faltantes)}")
    return dados.reindex(columns=cabecalho).fillna("")


def carregar_cadastro_github(caminho, cabecalho):
    if not os.path.isfile(caminho):
        raise FileNotFoundError(
            f"Arquivo não encontrado: dados/{os.path.basename(caminho)}. "
            "Envie os dois CSV à pasta dados/ na raiz do repositório."
        )
    info = os.stat(caminho)
    return carregar_cadastro_local(caminho, (info.st_size, info.st_mtime_ns), tuple(cabecalho))


def invalidar_cache():
    carregar_aba.clear()
    criar_concentracoes.clear()
    pontos_proximos_concentracoes.clear()
    eventos_georreferenciados.clear()
    filtrar_ativos_proximos.clear()


# O reset automático de PONTOS e EVENTOS foi desativado.
# As duas abas permanecem preservadas até que um usuário autorizado
# faça uma operação explícita de importação/atualização.

@st.cache_data(ttl=30, show_spinner=False)
def carregar_observacoes_concentracoes():
    """Lê anotações persistentes; operador não cria nem altera planilhas."""
    try:
        aba = obter_planilha(SPREADSHEET_ID).worksheet(NOME_ABA_OBSERVACOES)
    except gspread.WorksheetNotFound:
        return pd.DataFrame(columns=["CHAVE", "MUNICIPIO", "LATITUDE", "LONGITUDE", "OBSERVACAO", "ATUALIZADO_EM", "AUTOR"])
    registros = aba.get_all_records(numericise_ignore=["all"])
    return pd.DataFrame(registros) if registros else pd.DataFrame(columns=["CHAVE", "MUNICIPIO", "LATITUDE", "LONGITUDE", "OBSERVACAO", "ATUALIZADO_EM", "AUTOR"])


def identificar_observacao(concentracao, os_grupo, observacoes, raio_m):
    """Associa observações por município e centro próximo, mesmo que o ID C001 mude."""
    cidades = sorted({normalizar_municipio(v) for v in os_grupo.get("Cidade", []) if str(v).strip()})
    municipio = cidades[0] if cidades else ""
    lat, lon = float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"])
    melhor = None
    menor_distancia = float("inf")
    for _, r in observacoes.iterrows():
        if normalizar_municipio(r.get("MUNICIPIO", "")) != municipio:
            continue
        olat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        olon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if olat is None or olon is None:
            continue
        distancia = distancia_metros(lat, lon, olat, olon)
        if distancia is not None and distancia < menor_distancia and distancia <= min(float(raio_m), 300):
            menor_distancia, melhor = distancia, r
    return municipio, (str(melhor.get("CHAVE", "")) if melhor is not None else ""), (str(melhor.get("OBSERVACAO", "")) if melhor is not None else "")


def salvar_observacao_concentracao(chave, municipio, lat, lon, observacao):
    exigir_edicao_farol()
    planilha = obter_planilha(SPREADSHEET_ID)
    cab = ["CHAVE", "MUNICIPIO", "LATITUDE", "LONGITUDE", "OBSERVACAO", "ATUALIZADO_EM", "AUTOR"]
    try:
        aba = planilha.worksheet(NOME_ABA_OBSERVACOES)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=NOME_ABA_OBSERVACOES, rows=1000, cols=len(cab))
        aba.update(range_name="A1:G1", values=[cab], value_input_option="RAW")
    if not chave:
        chave = hashlib.sha256(f"{municipio}|{lat:.5f}|{lon:.5f}|{datetime.now(FUSO_FAROL).isoformat()}".encode()).hexdigest()[:20]
    valores = [chave, municipio, str(lat), str(lon), observacao.strip(), datetime.now(FUSO_FAROL).strftime("%d/%m/%Y %H:%M"), st.session_state.get("usuario_logado", "")]
    linhas = aba.get_all_values()
    for i, linha in enumerate(linhas[1:], start=2):
        if linha and linha[0] == chave:
            aba.update(range_name=f"A{i}:G{i}", values=[valores], value_input_option="RAW")
            carregar_observacoes_concentracoes.clear()
            return
    aba.append_row(valores, value_input_option="RAW")
    carregar_observacoes_concentracoes.clear()


@st.cache_data(ttl=60, show_spinner=False)
def carregar_datas_atualizacao():
    """Consulta apenas duas linhas de metadados; nunca lê as bases para obter datas."""
    try:
        aba = obter_planilha(SPREADSHEET_ID).worksheet(NOME_ABA_ATUALIZACOES)
        linhas = aba.get_all_values()
    except gspread.WorksheetNotFound:
        return {}
    except Exception:
        return {}
    return {linha[0].strip().upper(): linha[1].strip()
            for linha in linhas[1:] if len(linha) >= 2 and linha[0].strip()}


def registrar_atualizacao_base(tipo):
    """Persiste data/hora real de importação, inclusive entre sessões e reinícios."""
    exigir_edicao_farol()
    if tipo not in {"PONTOS", "EVENTOS"}:
        raise ValueError("Tipo de base desconhecido.")
    planilha = obter_planilha(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet(NOME_ABA_ATUALIZACOES)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=NOME_ABA_ATUALIZACOES, rows=10, cols=2)
        aba.update(range_name="A1:B1", values=[["BASE", "ATUALIZADO_EM"]], value_input_option="RAW")
    linhas = aba.get_all_values()
    momento = datetime.now(FUSO_FAROL).strftime("%d/%m/%Y %H:%M:%S")
    for numero_linha, linha in enumerate(linhas[1:], start=2):
        if linha and linha[0].strip().upper() == tipo:
            aba.update(range_name=f"A{numero_linha}:B{numero_linha}",
                       values=[[tipo, momento]], value_input_option="RAW")
            carregar_datas_atualizacao.clear()
            return
    aba.append_row([tipo, momento], value_input_option="RAW")
    carregar_datas_atualizacao.clear()


def exibir_atualizacoes_abaixo_mapa():
    datas = carregar_datas_atualizacao()
    os_em = datas.get("PONTOS", "Sem importação registrada")
    eventos_em = datas.get("EVENTOS", "Sem importação registrada")
    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px 26px;margin:4px 0 14px;'
        'font-size:13px;font-weight:600;color:#1558b0;">'
        f'<span>O.S. — Atualizado em {os_em}</span>'
        f'<span>Eventos — Atualizado em {eventos_em}</span>'
        '</div>', unsafe_allow_html=True,
    )


def limpar_dados_operacionais_admin():
    """Limpa PONTOS, EVENTOS e correções manuais de áreas, preservando cabeçalhos."""
    if not verificar_autenticacao() or str(st.session_state.get("perfil", "")).strip().lower() != "admin":
        raise PermissionError("Somente administradores podem limpar os dados operacionais.")
    planilha = obter_planilha(SPREADSHEET_ID)
    resultados = []
    abas = (
        (NOME_ABA_PONTOS, CABECALHO_PONTOS),
        (NOME_ABA_EVENTOS, CABECALHO_EVENTOS),
        (NOME_ABA_AREAS_PROTEGIDAS, ["CHAVE_EVENTO", "AREAS_IMPACTADAS", "ATUALIZADO_EM", "AUTOR"]),
        (NOME_ABA_ATUALIZACOES, ["BASE", "ATUALIZADO_EM"]),
    )
    for nome, cabecalho in abas:
        try:
            aba = planilha.worksheet(nome)
        except gspread.WorksheetNotFound:
            # A aba auxiliar só existe após a primeira edição manual.
            if nome in {NOME_ABA_AREAS_PROTEGIDAS, NOME_ABA_ATUALIZACOES}:
                continue
            raise
        # Apaga registros, não a aba, e mantém os cabeçalhos para futuras importações.
        aba.clear()
        aba.update(range_name="A1", values=[cabecalho], value_input_option="RAW")
        resultados.append(nome)
    invalidar_cache()
    carregar_datas_atualizacao.clear()
    return resultados


@st.dialog("🗑️ Limpar dados operacionais")
def modal_limpar_dados_operacionais():
    if str(st.session_state.get("perfil", "")).strip().lower() != "admin" or not verificar_autenticacao():
        st.error("Operação exclusiva do administrador.")
        st.stop()
    st.warning(
        "Esta ação excluirá todas as O.S. de PONTOS, os eventos de EVENTOS e "
        "as correções manuais de FAROL_AREAS_EDITADAS e os registros de atualização. "
        "Não é possível desfazer pela ferramenta."
    )
    st.caption("Poços, loggers, observações das concentrações e demais abas serão preservados.")
    confirmado = st.checkbox(
        "Confirmo que desejo apagar os registros de PONTOS, EVENTOS e FAROL_AREAS_EDITADAS.",
        key="confirmar_limpeza_farol",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancelar", width="stretch", key="cancelar_limpeza_farol"):
            st.rerun()
    with c2:
        if st.button("🗑️ Limpar agora", type="primary", disabled=not confirmado,
                     width="stretch", key="executar_limpeza_farol"):
            try:
                abas = limpar_dados_operacionais_admin()
                st.session_state["farol_mensagem_limpeza"] = "Dados removidos das abas: " + ", ".join(abas) + "."
                st.rerun()
            except Exception as erro:
                invalidar_cache()
                st.error(f"Falha durante a limpeza: {erro}. Confira o conteúdo das abas antes de repetir.")


def garantir_cabecalho_exato(nome, cabecalho):
    aba = obter_aba(nome, cabecalho)
    valores = aba.get_all_values()
    if not valores:
        if PODE_EDITAR_FAROL:
            aba.update("A1", [cabecalho])
    return aba


def append_dataframe(nome, cabecalho, df):
    exigir_edicao_farol()
    if df is None or df.empty:
        return 0
    aba = garantir_cabecalho_exato(nome, cabecalho)
    df = df.reindex(columns=cabecalho).fillna("")
    linhas = [[limpar_valor(v) for v in row] for row in df.itertuples(index=False, name=None)]
    if linhas:
        aba.append_rows(linhas, value_input_option="USER_ENTERED")
    invalidar_cache()
    return len(linhas)


def substituir_aba(nome, cabecalho, df):
    exigir_edicao_farol()
    aba = garantir_cabecalho_exato(nome, cabecalho)
    df = df.reindex(columns=cabecalho).fillna("")
    linhas = [cabecalho] + [[limpar_valor(v) for v in row] for row in df.itertuples(index=False, name=None)]
    aba.clear()
    aba.resize(rows=max(1000, len(linhas) + 20), cols=max(len(cabecalho) + 5, 20))
    # PONTOS: RAW preserva o ponto decimal como texto literal.
    # USER_ENTERED interpreta o ponto como separador de milhar em planilhas pt-BR,
    # convertendo -5.038017 em -5.038.017 e invalidando a coordenada.
    modo_escrita = "RAW" if nome == NOME_ABA_PONTOS else "USER_ENTERED"
    aba.update("A1", linhas, value_input_option=modo_escrita)
    invalidar_cache()


# ============================================================
# LEITURA DE ARQUIVOS
# ============================================================

def ler_planilha_upload(upload):
    if upload is None:
        return pd.DataFrame()
    nome = upload.name.lower()
    dados = upload.getvalue()
    if nome.endswith(".csv"):
        for encoding in ("utf-8-sig", "latin1", "cp1252"):
            try:
                return pd.read_csv(io.BytesIO(dados), sep=None, engine="python", encoding=encoding, dtype=str)
            except Exception:
                pass
        raise ValueError("Não foi possível ler o CSV.")
    return pd.read_excel(io.BytesIO(dados), dtype=str)


def localizar_coluna(df, candidatos, obrigatoria=False):
    mapa = {normalizar_cabecalho(c): c for c in df.columns}
    for candidato in candidatos:
        n = normalizar_cabecalho(candidato)
        if n in mapa:
            return mapa[n]
    for col in df.columns:
        n = normalizar_cabecalho(col)
        for candidato in candidatos:
            nc = normalizar_cabecalho(candidato)
            if nc and nc in n:
                return col
    if obrigatoria:
        raise ValueError(f"Coluna não encontrada. Procuradas: {', '.join(candidatos)}")
    return None


def mapear_colunas(df, destino):
    resultado = pd.DataFrame(index=df.index)
    for col_destino in destino:
        candidatos = [col_destino]
        if col_destino == "Nº da O.S":
            candidatos += ["N O S", "Nº OS", "OS", "NUMERO OS", "NUMERO DA OS", "ORDEM DE SERVICO"]
        elif col_destino == "Dt. Emissão":
            candidatos += ["DATA EMISSAO", "DATA DE EMISSAO", "DT EMISSAO"]
        elif col_destino == "Matrícula":
            candidatos += ["MATRICULA", "MATRÍCULA"]
        elif col_destino == "Latitude":
            candidatos += ["LAT", "LATITUDE"]
        elif col_destino == "Longitude":
            candidatos += ["LON", "LONG", "LONGITUDE"]
        elif col_destino == "Código do Ativo":
            candidatos += ["CODIGO DO ATIVO", "ATIVO", "COD ATIVO"]
        elif col_destino == "Áreas Impactadas":
            candidatos += ["AREAS IMPACTADAS", "ÁREA IMPACTADA", "BAIRROS AFETADOS"]
        elif col_destino == "Descrição do Serviço":
            candidatos += ["DESCRICAO DO SERVICO", "DESCRIÇÃO", "DESCRICAO"]

        origem = localizar_coluna(df, candidatos)
        resultado[col_destino] = df[origem].map(limpar_valor) if origem else ""
    return resultado


def preparar_pontos(df):
    out = mapear_colunas(df, CABECALHO_PONTOS)
    for coluna, tipo in (("Latitude", "lat"), ("Longitude", "lon")):
        out[coluna] = out[coluna].map(lambda valor: normalizar_coordenada(valor, tipo))
    # Preserva as O.S. sem geolocalização para consulta e diagnóstico.
    colunas_conteudo = [c for c in CABECALHO_PONTOS if c not in ("Latitude", "Longitude")]
    out = out.loc[out[colunas_conteudo].apply(
        lambda linha: any(str(v).strip() for v in linha), axis=1
    )].copy()
    return out


def chave_ponto(row):
    os_num = normalizar_texto(row.get("Nº da O.S", ""))
    if os_num:
        return f"OS:{os_num}"
    return "HASH:" + slug_hash(*[row.get(c, "") for c in CABECALHO_PONTOS])


def preparar_eventos(df):
    out = mapear_colunas(df, CABECALHO_EVENTOS)
    out = out.loc[~out.apply(lambda r: all(not str(x).strip() for x in r), axis=1)].copy()
    return out


def chave_evento(row):
    """Protocolo identifica o evento mesmo após alterações de status e horários.

    Na ausência de protocolo, usa campos de identificação relativamente estáveis.
    """
    protocolo = normalizar_texto(row.get("Protocolo", ""))
    if protocolo:
        return "PROTOCOLO:" + protocolo
    campos = ["Data", "Código do Ativo", "Serviço", "Início", "Cidade", "Unidade"]
    return "SEM_PROTOCOLO:" + slug_hash(*[row.get(c, "") for c in campos])


def upsert_pontos(df_novo):
    exigir_edicao_farol()
    atual = carregar_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS)
    # Preserva colunas extras já existentes na aba PONTOS.
    colunas = list(dict.fromkeys(list(atual.columns) + list(CABECALHO_PONTOS)))
    atual = atual.reindex(columns=colunas).fillna("")
    novo = df_novo.reindex(columns=colunas).fillna("")

    if atual.empty:
        final = novo.copy()
    else:
        mapa = {}
        for _, r in atual.iterrows():
            mapa[chave_ponto(r)] = r.to_dict()
        for _, r in novo.iterrows():
            mapa[chave_ponto(r)] = r.to_dict()
        final = pd.DataFrame(list(mapa.values()), columns=colunas)

    # Padroniza as coordenadas de O.S. para texto decimal com ponto antes
    # de enviar ao Sheets em modo RAW, sem depender da região da planilha.
    # Valores inválidos permanecem vazios; a O.S. continua armazenada.
    for coluna, tipo in (("Latitude", "lat"), ("Longitude", "lon")):
        final[coluna] = final[coluna].map(
            lambda valor: (
                format(n, ".6f") if (n := normalizar_coordenada(valor, tipo)) is not None else ""
            )
        )

    # Mantém ordem cronológica aproximada, sem exigir datas válidas.
    if not final.empty:
        final["_ord"] = pd.to_datetime(final["Dt. Emissão"], dayfirst=True, errors="coerce")
        final = final.sort_values("_ord", na_position="last").drop(columns="_ord")
    substituir_aba(NOME_ABA_PONTOS, colunas, final)
    return len(novo), len(final)


def carregar_areas_editadas():
    """Correções explícitas sobrevivem à reimportação de EVENTOS.

    Aba separada também permite proteger uma correção para campo vazio.
    """
    try:
        aba = obter_planilha(SPREADSHEET_ID).worksheet(NOME_ABA_AREAS_PROTEGIDAS)
    except gspread.WorksheetNotFound:
        return {}
    linhas = aba.get_all_values()
    if not linhas:
        return {}
    cab = linhas[0]
    if "CHAVE_EVENTO" not in cab or "AREAS_IMPACTADAS" not in cab:
        raise ValueError("Cabeçalho inválido em FAROL_AREAS_EDITADAS.")
    i_chave, i_area = cab.index("CHAVE_EVENTO"), cab.index("AREAS_IMPACTADAS")
    return {linha[i_chave]: linha[i_area] if i_area < len(linha) else ""
            for linha in linhas[1:] if i_chave < len(linha) and linha[i_chave]}


def registrar_area_editada(chave, area):
    """Registra correção humana com chave estável do evento, mesmo quando vazia."""
    exigir_edicao_farol()
    if not chave:
        raise ValueError("Não foi possível identificar o evento para proteger a área.")
    planilha = obter_planilha(SPREADSHEET_ID)
    try:
        aba = planilha.worksheet(NOME_ABA_AREAS_PROTEGIDAS)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=NOME_ABA_AREAS_PROTEGIDAS, rows=1000, cols=4)
        aba.update(range_name="A1:D1", values=[["CHAVE_EVENTO", "AREAS_IMPACTADAS", "ATUALIZADO_EM", "AUTOR"]], value_input_option="RAW")
    linhas = aba.get_all_values()
    cab = linhas[0] if linhas else ["CHAVE_EVENTO", "AREAS_IMPACTADAS", "ATUALIZADO_EM", "AUTOR"]
    if "CHAVE_EVENTO" not in cab or "AREAS_IMPACTADAS" not in cab:
        raise ValueError("Cabeçalho inválido em FAROL_AREAS_EDITADAS.")
    dados = {"CHAVE_EVENTO": chave, "AREAS_IMPACTADAS": str(area),
             "ATUALIZADO_EM": datetime.now(FUSO_FAROL).strftime("%d/%m/%Y %H:%M"),
             "AUTOR": str(st.session_state.get("usuario_logado", ""))}
    valores = [dados.get(c, "") for c in cab]
    col_chave = cab.index("CHAVE_EVENTO")
    for n, linha in enumerate(linhas[1:], start=2):
        if col_chave < len(linha) and linha[col_chave] == chave:
            from gspread.utils import rowcol_to_a1
            aba.update(range_name=f"A{n}:{rowcol_to_a1(n, len(cab))}", values=[valores], value_input_option="RAW")
            return
    aba.append_row(valores, value_input_option="RAW")


def upsert_eventos(df_novo):
    exigir_edicao_farol()
    atual = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)
    atual = atual.reindex(columns=CABECALHO_EVENTOS).fillna("")
    novo = df_novo.reindex(columns=CABECALHO_EVENTOS).fillna("")
    areas_protegidas = carregar_areas_editadas()

    mapa = {}
    for _, registro in atual.iterrows():
        mapa[chave_evento(registro)] = registro.to_dict()
    for _, registro in novo.iterrows():
        chave = chave_evento(registro)
        dados_novos = registro.to_dict()
        if chave in mapa:
            # Atualizações parciais não apagam campos antigos preenchidos.
            anterior = mapa[chave]
            mapa[chave] = {
                campo: dados_novos[campo] if str(dados_novos[campo]).strip() else anterior.get(campo, "")
                for campo in CABECALHO_EVENTOS
            }
        else:
            mapa[chave] = dados_novos
    # Reaplica a correção humana APÓS a mesclagem de dados da importação.
    for chave, evento in mapa.items():
        if chave in areas_protegidas:
            evento["Áreas Impactadas"] = areas_protegidas[chave]
    final = pd.DataFrame(list(mapa.values()), columns=CABECALHO_EVENTOS)
    substituir_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS, final)
    return len(novo), len(final)


# ============================================================
# KMZ / POLÍGONOS DOS BAIRROS
# ============================================================

@st.cache_data(show_spinner=False)
def carregar_kmz_bytes(kmz_bytes):
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        nomes_kml = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not nomes_kml:
            raise ValueError("O KMZ não contém arquivo KML.")
        data = z.read(nomes_kml[0])
    return carregar_kml_bytes(data)


@st.cache_data(show_spinner=False)
def carregar_kml_bytes(kml_bytes):
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    raiz = ET.fromstring(kml_bytes)
    bairros = []

    for placemark in raiz.findall(".//k:Placemark", ns):
        nome_el = placemark.find("k:name", ns)
        nome = nome_el.text.strip() if nome_el is not None and nome_el.text else ""
        if not nome:
            continue

        poligonos = []
        for poly in placemark.findall(".//k:Polygon", ns):
            outer = poly.find("k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
            if outer is None or not outer.text:
                continue
            coords = []
            for item in outer.text.strip().split():
                partes = item.split(",")
                if len(partes) >= 2:
                    try:
                        lon = float(partes[0])
                        lat = float(partes[1])
                        coords.append((lat, lon))
                    except ValueError:
                        pass
            if len(coords) >= 3:
                poligonos.append(coords)

        if poligonos:
            bairros.append({
                "nome": nome,
                "nome_normalizado": limpar_nome_bairro(nome),
                "poligonos": poligonos,
            })

    return bairros



def normalizar_municipio(valor):
    """Usa a mesma chave para Cidade da planilha e nome do arquivo KMZ."""
    return re.sub(r"[^A-Z0-9]", "", normalizar_texto(valor))


def carregar_gpkg(caminho):
    """Lê os polígonos do GeoPackage sem geopandas/GDAL.

    Identifica bairro e município pelos atributos do QGIS; converte o SRC
    original para WGS84 antes de entregar coordenadas ao Folium.
    """
    registros = []
    with sqlite3.connect(f"file:{caminho}?mode=ro", uri=True) as conexao:
        camadas = conexao.execute(
            "SELECT table_name, srs_id FROM gpkg_contents WHERE data_type='features'"
        ).fetchall()
        for tabela, srs_id in camadas:
            info = conexao.execute(
                "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?",
                (tabela,),
            ).fetchone()
            if not info:
                continue
            campo_geometria, srs_geom = info
            nomes = [r[1] for r in conexao.execute(f'PRAGMA table_info("{tabela.replace(chr(34), chr(34)*2)}")')]
            campos = {normalizar_cabecalho(c): c for c in nomes}
            # Compatibilidade automática com as duas origens de bairros:
            # IBGE: NM_BAIRRO + NM_RGI/NM_MUN
            # Municípios (ArcGIS): NOME + MUNICIPIO
            campo_bairro = next(
                (campos[k] for k in ("NMBAIRRO", "NOMEBAIRRO", "BAIRRO", "NOME") if k in campos),
                None,
            )
            campo_mun = next(
                (campos[k] for k in ("NMMUN", "MUNICIPIO", "NOMEMUNICIPIO", "CIDADE", "NMRGI") if k in campos),
                None,
            )
            if not campo_bairro:
                continue
            # GeoPackage usa WKB com cabeçalho GP de 8+ bytes, definido pelos flags.
            src_id = srs_geom or srs_id
            linha_srs = conexao.execute(
                "SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys WHERE srs_id=?",
                (src_id,),
            ).fetchone()
            if not linha_srs:
                continue
            org, cod, definicao = linha_srs
            try:
                origem = CRS.from_user_input(f"{org}:{cod}") if org and cod else CRS.from_wkt(definicao)
            except Exception:
                origem = CRS.from_wkt(definicao)
            conversor = None if origem.equals(CRS.from_epsg(4326)) else Transformer.from_crs(origem, 4326, always_xy=True)
            quoted = lambda x: '"' + x.replace('"', '""') + '"'
            colunas = [campo_geometria, campo_bairro] + ([campo_mun] if campo_mun else [])
            consulta = f'SELECT {", ".join(quoted(c) for c in colunas)} FROM {quoted(tabela)}'
            for row in conexao.execute(consulta):
                bruto, nome, *municipio_atributo = row
                if not bruto or not nome:
                    continue
                bruto = bytes(bruto)
                if len(bruto) < 8 or bruto[:2] != b"GP":
                    continue
                flags = bruto[3]
                envelope = (flags >> 1) & 7
                tamanhos = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
                if envelope not in tamanhos:
                    continue
                geometria = wkb.loads(bruto[8 + tamanhos[envelope]:])
                if conversor:
                    geometria = transformar_geometria(conversor.transform, geometria)
                if geometria.geom_type == "Polygon":
                    partes = [geometria]
                elif geometria.geom_type == "MultiPolygon":
                    partes = list(geometria.geoms)
                else:
                    continue
                poligonos = []
                for parte in partes:
                    coords = [(float(y), float(x)) for x, y in parte.exterior.coords]
                    if len(coords) >= 4 and all(-90 <= lat <= 90 and -180 <= lon <= 180 for lat, lon in coords):
                        poligonos.append(coords)
                if poligonos:
                    municipio = (municipio_atributo[0] if municipio_atributo else "") or nome_municipio_arquivo(caminho)
                    registros.append({
                        "nome": str(nome).strip(),
                        "nome_normalizado": limpar_nome_bairro(nome),
                        "municipio": normalizar_municipio(municipio),
                        "poligonos": poligonos,
                    })
    return registros


def nome_municipio_arquivo(caminho):
    nome = os.path.splitext(os.path.basename(caminho))[0]
    return re.sub(r"^(?:NM_MUN|NM_RGI)[_\s-]*", "", nome, flags=re.I)


def preparar_poligonos_para_mapa(registros, tolerancia=0.00007):
    """Reduz vértices SOMENTE no desenho. Preserva 'poligonos' originais para análise.

    0.00007 grau corresponde aproximadamente a alguns metros na região de operação.
    A geometria simplificada é calculada apenas quando os arquivos mudam (cache).
    """
    from shapely.geometry import Polygon
    for bairro in registros:
        visuais = []
        for coords in bairro.get("poligonos", []):
            if len(coords) < 25:
                visuais.append(coords)
                continue
            try:
                # shapely usa longitude,latitude; Folium usa latitude,longitude.
                geom = Polygon([(lon, lat) for lat, lon in coords])
                simplificado = geom.simplify(tolerancia, preserve_topology=True)
                if simplificado.is_empty or simplificado.geom_type != "Polygon":
                    visuais.append(coords)
                else:
                    novo = [(float(lat), float(lon)) for lon, lat in simplificado.exterior.coords]
                    visuais.append(novo if len(novo) >= 4 else coords)
            except (ValueError, TypeError):
                visuais.append(coords)
        bairro["poligonos_mapa"] = visuais
    return registros


@st.cache_data(show_spinner=False, ttl=300)
def carregar_geometrias_municipais(arquivos_assinados):
    """Carrega GeoPackage, KMZ e KML por município, sem impedir uso do mapa em caso de erro."""
    todos = []
    for caminho, _tamanho, _mtime in arquivos_assinados:
        extensao = os.path.splitext(caminho)[1].lower()
        municipio = normalizar_municipio(nome_municipio_arquivo(caminho))
        try:
            if extensao == ".gpkg":
                registros = carregar_gpkg(caminho)
            elif extensao in (".kmz", ".kml"):
                with open(caminho, "rb") as arquivo:
                    dados = arquivo.read()
                registros = carregar_kmz_bytes(dados) if extensao == ".kmz" else carregar_kml_bytes(dados)
                registros = [{**bairro, "municipio": municipio} for bairro in registros]
            else:
                continue
            todos.extend(preparar_poligonos_para_mapa(registros))
        except Exception:
            # Não exibe avisos de arquivos sem cobertura, mantendo os eventos na planilha.
            continue
    return todos


@st.cache_data(ttl=60, show_spinner=False)
def descobrir_kmz():
    """Compatibilidade com nome antigo; descobre KMZ, KML e GPKG da pasta."""
    arquivos = []
    if os.path.isdir(DIRETORIO_KMZ):
        for nome in sorted(os.listdir(DIRETORIO_KMZ)):
            if nome.lower().endswith((".gpkg", ".kmz", ".kml")):
                caminho = os.path.join(DIRETORIO_KMZ, nome)
                if os.path.isfile(caminho):
                    arquivos.append(caminho)
    # Para municípios com dois formatos, prefere o GPKG por conter NM_BAIRRO/NM_MUN.
    prioridades = {".gpkg": 0, ".kmz": 1, ".kml": 2}
    escolhidos = {}
    for caminho in arquivos:
        municipio = normalizar_municipio(nome_municipio_arquivo(caminho))
        if municipio and (municipio not in escolhidos or
                          prioridades[os.path.splitext(caminho)[1].lower()] < prioridades[os.path.splitext(escolhidos[municipio])[1].lower()]):
            escolhidos[municipio] = caminho
    if os.path.isfile(ARQUIVO_KMZ_PADRAO) and "TERESINA" not in escolhidos:
        escolhidos["TERESINA"] = ARQUIVO_KMZ_PADRAO
    assinaturas = []
    for caminho in escolhidos.values():
        try:
            info = os.stat(caminho)
            assinaturas.append((caminho, info.st_size, info.st_mtime_ns))
        except OSError:
            continue
    return carregar_geometrias_municipais(tuple(assinaturas))


def ponto_em_poligono(lat, lon, poligono):
    # Ray casting. poligono: [(lat, lon), ...]
    dentro = False
    x = lon
    y = lat
    n = len(poligono)
    j = n - 1
    for i in range(n):
        yi, xi = poligono[i]
        yj, xj = poligono[j]
        cruza = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi)
        if cruza:
            dentro = not dentro
        j = i
    return dentro


def ponto_em_bairro(lat, lon, bairro):
    for poligono in bairro["poligonos"]:
        if ponto_em_poligono(lat, lon, poligono):
            return True
    return False


def identificar_bairro_por_ponto(lat, lon, bairros):
    if lat is None or lon is None:
        return ""
    for bairro in bairros:
        if ponto_em_bairro(lat, lon, bairro):
            return bairro["nome_normalizado"]
    return ""


# ============================================================
# CONCENTRAÇÕES / ANÁLISE ESPACIAL
# ============================================================

@st.cache_data(ttl=180, show_spinner=False, max_entries=12)
def criar_concentracoes(df_pontos, raio_m=500, minimo_os=2):
    df = df_pontos.copy()
    df["_lat"] = df["Latitude"].map(parse_float)
    df["_lon"] = df["Longitude"].map(parse_float)
    df = df.dropna(subset=["_lat", "_lon"]).reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Grade geográfica para evitar comparação de todos contra todos.
    lat_step = raio_m / 111320.0
    lon_step = raio_m / (111320.0 * max(0.2, math.cos(math.radians(float(df["_lat"].mean())))))

    buckets = {}
    for idx, r in df.iterrows():
        cell = (int(math.floor(r["_lat"] / lat_step)), int(math.floor(r["_lon"] / lon_step)))
        buckets.setdefault(cell, []).append(idx)

    parent = list(range(len(df)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for cell, indices in buckets.items():
        cx, cy = cell
        candidatos = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidatos.extend(buckets.get((cx + dx, cy + dy), []))
        for i in indices:
            for j in candidatos:
                if j <= i:
                    continue
                d = distancia_metros(df.at[i, "_lat"], df.at[i, "_lon"], df.at[j, "_lat"], df.at[j, "_lon"])
                if d is not None and d <= raio_m:
                    union(i, j)

    df["_grupo"] = [find(i) for i in range(len(df))]
    contagens = df.groupby("_grupo").size()
    grupos_validos = contagens[contagens >= minimo_os].index.tolist()
    df = df[df["_grupo"].isin(grupos_validos)].copy()

    if df.empty:
        return pd.DataFrame(), df

    concentracoes = []
    for grupo, bloco in df.groupby("_grupo"):
        lat = bloco["_lat"].mean()
        lon = bloco["_lon"].mean()
        os_count = len(bloco)
        matriculas = bloco["Matrícula"].replace("", pd.NA).dropna().nunique()
        bairros = sorted({limpar_nome_bairro(x) for x in bloco["Bairro"] if str(x).strip()})
        concentracoes.append({
            "ID_CONCENTRACAO": f"C{len(concentracoes) + 1:03d}",
            "GRUPO": grupo,
            "LATITUDE": lat,
            "LONGITUDE": lon,
            "QTD_OS": os_count,
            "QTD_MATRICULAS": matriculas,
            "BAIRROS": ", ".join(bairros),
        })

    cdf = pd.DataFrame(concentracoes).sort_values(["QTD_OS", "QTD_MATRICULAS"], ascending=False).reset_index(drop=True)
    # Sequências independentes por abrangência, sem alterar o identificador
    # interno GRUPO (que vincula as O.S., ativos, eventos e acompanhamentos).
    # Concentrações que incluam Teresina são atribuídas a THE, evitando
    # identificadores duplicados entre as abas.
    contador = {"API": 0, "THE": 0}
    novos_ids = []
    for _, concentracao in cdf.iterrows():
        grupo = df[df["_grupo"] == concentracao["GRUPO"]]
        cidades = {normalizar_municipio(c) for c in grupo["Cidade"].dropna()}
        abrangencia = "THE" if "TERESINA" in cidades else "API"
        contador[abrangencia] += 1
        novos_ids.append(f"{abrangencia} C{contador[abrangencia]:03d}")
    cdf["ID_CONCENTRACAO"] = novos_ids
    return cdf, df


def _indice_espacial_ativos(df, tamanho_celula=0.01):
    """Grade espacial simples, sem dependências adicionais.

    Retém posições por índice posicional para preservar a ordem e índices repetidos.
    """
    grade = {}
    registros = list(df.to_dict("records"))
    for pos, r in enumerate(registros):
        lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if lat is None or lon is None:
            continue
        celula = (math.floor(lat / tamanho_celula), math.floor(lon / tamanho_celula))
        grade.setdefault(celula, []).append((pos, lat, lon))
    return grade, registros


def _candidatos_no_raio(grade, lat, lon, raio_m, tamanho_celula=0.01):
    """Busca por caixa conservadora; a decisão final usa Haversine original."""
    if lat is None or lon is None or raio_m < 0:
        return []
    # A margem é deliberadamente conservadora para evitar falsos negativos.
    delta_lat = raio_m / 110000.0 + 1e-9
    limite_lat = min(89.999999, abs(lat) + delta_lat)
    cos_min = max(0.000001, math.cos(math.radians(limite_lat)))
    delta_lon = raio_m / (110000.0 * cos_min) + 1e-9
    x0 = math.floor((lat - delta_lat) / tamanho_celula)
    x1 = math.floor((lat + delta_lat) / tamanho_celula)
    y0 = math.floor((lon - delta_lon) / tamanho_celula)
    y1 = math.floor((lon + delta_lon) / tamanho_celula)
    candidatos = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for pos, alat, alon in grade.get((x, y), ()):
                d = distancia_metros(lat, lon, alat, alon)
                if d is not None and d <= raio_m:
                    candidatos.append((pos, d))
    candidatos.sort(key=lambda item: item[0])
    return candidatos


@st.cache_data(ttl=180, show_spinner=False, max_entries=12)
def pontos_proximos_concentracoes(concentracoes, df_pocos, df_loggers, raio=500):
    registros = []
    grade_pocos, pocos = _indice_espacial_ativos(df_pocos)
    grade_loggers, loggers = _indice_espacial_ativos(df_loggers)
    for _, c in concentracoes.iterrows():
        lat = normalizar_coordenada(c.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(c.get("LONGITUDE"), "lon")
        for grade, ativos, tipo, nome_coluna in (
            (grade_pocos, pocos, "Poço / Ativo", "NOME_POCO"),
            (grade_loggers, loggers, "Logger", "ENDERECO"),
        ):
            for pos, d in _candidatos_no_raio(grade, lat, lon, raio):
                p = ativos[pos]
                registros.append({
                    "Concentração": c["ID_CONCENTRACAO"],
                    "Tipo": tipo,
                    "Identificação": p.get("IDENTIFICACAO_ATIVO", ""),
                    "Nome": p.get(nome_coluna, ""),
                    "Município": p.get("MUNICIPIO", ""),
                    "Distância (m)": round(d, 1),
                    "Distância": distancia_formatada(d),
                })
    return pd.DataFrame(registros)


def relacionar_eventos_pontos(df_eventos, df_pontos, bairros):
    if df_eventos.empty or df_pontos.empty:
        return pd.DataFrame()

    pontos = df_pontos.copy()
    pontos["_bairro_base"] = pontos["Bairro"].map(limpar_nome_bairro)

    # Quando o bairro textual da O.S. não for confiável, usa a geometria do KMZ.
    if bairros:
        pontos["_bairro_poligono"] = pontos.apply(
            lambda r: identificar_bairro_por_ponto(parse_float(r["Latitude"]), parse_float(r["Longitude"]), bairros),
            axis=1,
        )
        pontos["_bairro_cruzamento"] = pontos["_bairro_poligono"].where(
            pontos["_bairro_poligono"].astype(bool), pontos["_bairro_base"]
        )
    else:
        pontos["_bairro_cruzamento"] = pontos["_bairro_base"]

    registros = []
    for _, evento in df_eventos.iterrows():
        municipal = evento_abrange_municipio(evento.get("Áreas Impactadas", ""))
        if municipal:
            cidade = normalizar_municipio(evento.get("Cidade", ""))
            bloco = pontos[pontos["Cidade"].map(normalizar_municipio) == cidade]
            if not bloco.empty:
                registros.append({
                    "Evento": evento.get("Descrição do Serviço", "") or evento.get("Serviço", ""),
                    "Protocolo": evento.get("Protocolo", ""),
                    "Status": evento.get("Status", ""),
                    "Bairro": "Todo o município", "Parcial": "Não",
                    "O.S. encontradas": len(bloco),
                    "Matrículas": bloco["Matrícula"].replace("", pd.NA).dropna().nunique(),
                    "Data": evento.get("Data", ""),
                })
            continue
        areas = extrair_bairros_evento(evento.get("Áreas Impactadas", ""), evento.get("Cidade", ""), bairros)
        for area in areas:
            bloco = pontos[
                (pontos["_bairro_cruzamento"] == area["bairro"])
                & (pontos["Cidade"].map(normalizar_municipio) == normalizar_municipio(evento.get("Cidade", "")))
            ].copy()
            if bloco.empty:
                continue
            registros.append({
                "Evento": evento.get("Descrição do Serviço", "") or evento.get("Serviço", ""),
                "Protocolo": evento.get("Protocolo", ""),
                "Status": evento.get("Status", ""),
                "Bairro": area["bairro"],
                "Parcial": "Sim" if area["parcial"] else "Não",
                "O.S. encontradas": len(bloco),
                "Matrículas": bloco["Matrícula"].replace("", pd.NA).dropna().nunique(),
                "Data": evento.get("Data", ""),
            })
    return pd.DataFrame(registros)


# ============================================================
# EVENTOS GEORREFERENCIADOS — SOMENTE ONDE HÁ POLÍGONOS
# ============================================================

def classificar_status_evento(valor):
    status = normalizar_texto(valor)
    if any(p in status for p in ("FINALIZ", "ENCERR", "CONCLUI", "CONCLUID", "NORMALIZ", "RESOLVID", "CANCELAD")):
        return "Finalizado", "#2eaa59"
    if any(p in status for p in ("PROGRAM", "AGEND", "PREVIST", "PLANEJ")):
        return "Programado", "#f2b233"
    if any(p in status for p in ("ANDAMENTO", "EXECU", "INICIAD", "ATIVO", "ABERTO", "OCORRENCIA", "EM CURSO")):
        return "Em andamento", "#e04747"
    return "Status não classificado", "#8b95a7"


@st.cache_data(ttl=180, show_spinner=False, max_entries=12)
def eventos_georreferenciados(eventos, bairros_kmz):
    """Relaciona polígonos por município + bairro, sem misturar cidades."""
    saida = []
    sem_geometria = 0
    if eventos is None or eventos.empty:
        return saida, 0
    indice = {}
    for bairro in bairros_kmz:
        chave = (bairro.get("municipio", "TERESINA"), bairro["nome_normalizado"])
        indice.setdefault(chave, []).append(bairro)
    for _, evento in eventos.iterrows():
        # Eventos encerrados permanecem na base, mas não geram feições no mapa.
        categoria_status, _ = classificar_status_evento(evento.get("Status", ""))
        if categoria_status == "Finalizado":
            continue
        cidade = normalizar_municipio(evento.get("Cidade", ""))
        areas = extrair_bairros_evento(evento.get("Áreas Impactadas", ""), evento.get("Cidade", ""), bairros_kmz)
        if not cidade or not areas:
            sem_geometria += 1
            continue
        identificados = set()
        encontrou = False
        faltou = False
        for area in areas:
            nome = area["bairro"]
            if nome in identificados:
                continue
            identificados.add(nome)
            correspondencias = indice.get((cidade, nome), [])
            if not correspondencias:
                faltou = True
                continue
            encontrou = True
            categoria, cor = classificar_status_evento(evento.get("Status", ""))
            for bairro in correspondencias:
                saida.append({
                    "bairro": bairro,
                    "evento": evento.to_dict(),
                    "parcial": area["parcial"],
                    "categoria": categoria,
                    "cor": cor,
                })
        if not encontrou or faltou:
            sem_geometria += 1
    return saida, sem_geometria


def adicionar_camada_eventos(mapa, eventos_mapeados):
    fg = folium.FeatureGroup(name="Eventos de desabastecimento", show=True)
    for item in eventos_mapeados:
        evento = item["evento"]
        # Proteção adicional contra feições finalizadas vindas de outra origem.
        if classificar_status_evento(evento.get("Status", ""))[0] == "Finalizado":
            continue
        bairro = item["bairro"]
        categoria = item["categoria"]
        parcial = item["parcial"]
        def esc(campo):
            return html_escape(str(evento.get(campo, "") or "—"))
        abrangencia = ("Parcial (polígono do bairro inteiro como referência)" if parcial
                       else "Todo o município" if evento_abrange_municipio(evento.get("Áreas Impactadas", ""))
                       else "Bairro informado como impactado")
        html = (
            f"<div style='min-width:250px;max-width:400px'>"
            f"<b>Evento — {html_escape(bairro['nome'])}</b><br>"
            f"<b>Situação no mapa:</b> {html_escape(categoria)}<br>"
            f"<b>Status original:</b> {esc('Status')}<br>"
            f"<b>Protocolo:</b> {esc('Protocolo')}<br>"
            f"<b>Serviço:</b> {esc('Serviço')}<br>"
            f"<b>Início:</b> {esc('Início')}<br>"
            f"<b>Previsão de término:</b> {esc('Prev. Término')}<br>"
            f"<b>Término real:</b> {esc('Término Real')}<br>"
            f"<b>Código do Ativo:</b> {esc('Código do Ativo')}<br>"
            f"<b>Abrangência:</b> {html_escape(abrangencia)}"
            f"</div>"
        )
        for poligono in bairro.get("poligonos_mapa", bairro["poligonos"]):
            folium.Polygon(
                locations=poligono,
                color=item["cor"], weight=2.5, opacity=0.9,
                fill=True, fill_color=item["cor"], fill_opacity=0.23,
                tooltip=f"Evento: {bairro['nome']} — {categoria}",
                popup=folium.Popup(html, max_width=430),
            ).add_to(fg)
    fg.add_to(mapa)


# ============================================================
# MAPA
# ============================================================

@st.cache_data(ttl=180, show_spinner=False, max_entries=12)
def filtrar_ativos_proximos(concentracoes, df_pocos, df_loggers, raio_m):
    """Exibe ativos perto de qualquer concentração, sem duplicatas, na ordem original."""
    if concentracoes.empty:
        return df_pocos.iloc[0:0].copy(), df_loggers.iloc[0:0].copy()
    centros = [
        (normalizar_coordenada(r.get("LATITUDE"), "lat"), normalizar_coordenada(r.get("LONGITUDE"), "lon"))
        for _, r in concentracoes.iterrows()
    ]
    centros = [(lat, lon) for lat, lon in centros if lat is not None and lon is not None]
    if not centros:
        return df_pocos.iloc[0:0].copy(), df_loggers.iloc[0:0].copy()

    def filtrar(df):
        grade, _ = _indice_espacial_ativos(df)
        posicoes = set()
        for lat, lon in centros:
            posicoes.update(pos for pos, _ in _candidatos_no_raio(grade, lat, lon, raio_m))
        return df.iloc[sorted(posicoes)].copy()

    return filtrar(df_pocos), filtrar(df_loggers)


def icone_bandeira_concentracao():
    """Bandeira central da concentração, distinta dos pontos de O.S."""
    return folium.DivIcon(
        html=("<div style=\"font-size:25px;line-height:29px;"
              "width:30px;height:30px;text-align:center;"
              "filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));\">🚩</div>"),
        icon_size=(30, 30),
        icon_anchor=(15, 25),
        class_name="farol-bandeira-concentracao",
    )


def municipios_das_concentracoes(concentracoes, pontos_cluster):
    """Municípios reais por grupo; o cadastro de concentrações não possui cidade."""
    resultado = {}
    if pontos_cluster is None or pontos_cluster.empty or "Cidade" not in pontos_cluster.columns:
        return resultado
    por_grupo = pontos_cluster.groupby("_grupo")["Cidade"].agg(
        lambda valores: {normalizar_municipio(v) for v in valores if str(v).strip()}
    ).to_dict()
    for _, c in concentracoes.iterrows():
        resultado[str(c["ID_CONCENTRACAO"])] = por_grupo.get(c["GRUPO"], set())
    return resultado


def bairros_dos_municipios(bairros, municipios):
    """Todos os bairros cadastrados dos municípios solicitados, sem recorte por raio."""
    if not municipios:
        return []
    return [b for b in bairros if normalizar_municipio(b.get("municipio", "")) in municipios]


def adicionar_limites_bairros(mapa, bairros):
    """Camada única GeoJSON: mais leve que criar um Polygon Leaflet por bairro."""
    features = []
    for b in bairros:
        for pol in b.get("poligonos_mapa", b["poligonos"]):
            if len(pol) < 4:
                continue
            features.append({
                "type": "Feature",
                "properties": {"bairro": str(b.get("nome", "")), "municipio": str(b.get("municipio", ""))},
                "geometry": {"type": "Polygon", "coordinates": [[[float(lon), float(lat)] for lat, lon in pol]]},
            })
    if not features:
        return
    fg = folium.FeatureGroup(name="Limites dos bairros", show=True)
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        name="Bairros", smooth_factor=1.0,
        style_function=lambda _feature: {"color": "#65758b", "weight": 1.15, "opacity": 0.75, "fillOpacity": 0},
        highlight_function=lambda _feature: {"color": "#334155", "weight": 2, "fillOpacity": 0.06},
        tooltip=folium.GeoJsonTooltip(fields=["bairro", "municipio"], aliases=["Bairro:", "Município:"], sticky=True),
    ).add_to(fg)
    fg.add_to(mapa)


def criar_mapa_panorama_v2(concentracoes, raio_m=500, bairros=None, eventos_mapeados=None):
    """Panorama leve: somente mapa-base e concentrações clicáveis.

    A ausência das camadas operacionais no panorama é intencional.
    """
    mapa = folium.Map(location=[-5.09, -42.80], zoom_start=12,
                      control_scale=True, tiles="OpenStreetMap", prefer_canvas=True)
    adicionar_limites_bairros(mapa, bairros or [])
    adicionar_camada_eventos(mapa, eventos_mapeados or [])
    limites = []
    for _, c in concentracoes.iterrows():
        lat, lon = float(c["LATITUDE"]), float(c["LONGITUDE"])
        codigo = html_escape(str(c["ID_CONCENTRACAO"]))
        bairros_txt = html_escape(str(c.get("BAIRROS", "") or "Não informado"))
        resumo = (f"<b>{codigo}</b><br>{bairros_txt}<br>"
                  f"{int(c['QTD_OS'])} O.S. · {int(c['QTD_MATRICULAS'])} matrículas<br>"
                  "<small>Clique no ponto central para abrir a análise detalhada.</small>")
        folium.Circle([lat, lon], radius=float(raio_m), color="#7c3aed",
                      weight=2, fill=True, fill_opacity=.07,
                      tooltip=f"{codigo} · {int(c['QTD_OS'])} O.S.").add_to(mapa)
        folium.Marker([lat, lon], icon=icone_bandeira_concentracao(),
                      popup=folium.Popup(resumo, max_width=320),
                      tooltip=f"{codigo} — Abrir concentração").add_to(mapa)
        limites.append([lat, lon])
    if len(limites) > 1:
        mapa.fit_bounds(limites, padding=(35, 35), max_zoom=14)
    elif len(limites) == 1:
        mapa.location = limites[0]
        mapa.options["zoom"] = 14
    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


def criar_mapa(bairros, df_pontos, df_pocos, df_loggers, concentracoes, proximidades, mostrar_bairros=True, eventos_mapeados=None, raio_circulo=None, outras_concentracoes=None, rotulos_equipamentos=False):
    mapa = folium.Map(location=[-5.09, -42.80], zoom_start=12, control_scale=True, tiles=None, zoom_snap=0.5, zoom_delta=0.5, wheel_px_per_zoom_level=120, prefer_canvas=True)
    folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap", control=False).add_to(mapa)

    if mostrar_bairros:
        adicionar_limites_bairros(mapa, bairros)

    adicionar_camada_eventos(mapa, eventos_mapeados or [])

    fg_os = folium.FeatureGroup(name="O.S.", show=True)
    if not df_pontos.empty:
        for r in df_pontos.to_dict("records"):
            lat = normalizar_coordenada(r.get("Latitude"), "lat")
            lon = normalizar_coordenada(r.get("Longitude"), "lon")
            if lat is None or lon is None:
                continue
            # Cor definida pelo serviço executado, independentemente do status da O.S.
            servico_os = str(r.get("Serviço Executado", "") or "")
            eh_informacao = bool(re.search(r"(?<!\d)146005(?!\d)", servico_os))
            cor = "#F28C28" if eh_informacao else "#1677D2"
            classificacao = ("Informação de Falta de água (146005)" if eh_informacao
                             else "Reclamação de Falta de água")
            popup = folium.Popup(
                f"O.S.: {r.get('Nº da O.S','')}<br>"
                f"<b>Matrícula:</b> {r.get('Matrícula','')}<br>"
                f"<b>Bairro:</b> {r.get('Bairro','')}<br>"
                f"<b>Status:</b> {r.get('Status OS','')}<br>"
                f"<b>Serviço:</b> {r.get('Serviço Executado','')}<br>"
                f"<b>Classificação:</b> {classificacao}",
                max_width=350,
            )
            folium.CircleMarker(
                [lat, lon], radius=4, color=cor, fill=True, fill_opacity=0.75, popup=popup
            ).add_to(fg_os)
    fg_os.add_to(mapa)

    # Rótulos independentes, controlados manualmente no menu de camadas.
    # Esta camada só existe no detalhamento operacional e inicia desmarcada.
    fg_rotulos = (folium.FeatureGroup(name="Rótulos de ativos e loggers", show=False)
                  if rotulos_equipamentos else None)
    if fg_rotulos is not None:
        mapa.get_root().header.add_child(Element("""
        <style>
          .farol-etiqueta-equipamento {
            display: inline-block; width: max-content;
            padding: 2px 5px; border-radius: 4px;
            background: rgba(255,255,255,.95); color: #1e293b;
            border: 1px solid #cbd5e1; font: 600 11px/1.25 Arial,sans-serif;
            box-shadow: 0 1px 3px rgba(0,0,0,.18);
            white-space: nowrap; pointer-events: none;
          }
        </style>
        """))

    def adicionar_rotulo_equipamento(lat, lon, nome):
        if fg_rotulos is None:
            return
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                html=f'<span class="farol-etiqueta-equipamento">{html_escape(str(nome))}</span>',
                icon_size=(0, 0), icon_anchor=(-12, 24),
            ),
        ).add_to(fg_rotulos)

    fg_loggers = folium.FeatureGroup(name="Loggers", show=True)
    for _, r in df_loggers.iterrows():
        lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if lat is None or lon is None:
            continue
        adicionar_rotulo_equipamento(lat, lon, r.get("IDENTIFICACAO_ATIVO", "") or "Logger")
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(
                f"<b>Logger:</b> {r.get('IDENTIFICACAO_ATIVO','')}<br>"
                f"<b>Endereço:</b> {r.get('ENDERECO','')}", max_width=300
            ),
            icon=folium.Icon(icon="signal", prefix="fa", color="orange"),
        ).add_to(fg_loggers)
    fg_loggers.add_to(mapa)

    fg_pocos = folium.FeatureGroup(name="Poços / Ativos", show=True)
    for _, r in df_pocos.iterrows():
        lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if lat is None or lon is None:
            continue
        adicionar_rotulo_equipamento(lat, lon, r.get("IDENTIFICACAO_ATIVO", "") or r.get("NOME_POCO", "") or "Ativo")
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(
                f"<b>Poço / Ativo:</b> {r.get('IDENTIFICACAO_ATIVO','')}<br>"
                f"<b>Nome:</b> {r.get('NOME_POCO','')}<br>"
                f"Município: {r.get('MUNICIPIO','')}", max_width=300
            ),
            icon=folium.Icon(icon="tint", prefix="fa", color="blue"),
            z_index_offset=1000,  # Mantém ativos acima dos loggers coincidentes.
        ).add_to(fg_pocos)
    fg_pocos.add_to(mapa)
    if fg_rotulos is not None:
        fg_rotulos.add_to(mapa)

    fg_conc = folium.FeatureGroup(name="Concentrações", show=True)
    for _, c in concentracoes.iterrows():
        lat, lon = float(c["LATITUDE"]), float(c["LONGITUDE"])
        codigo = html_escape(str(c["ID_CONCENTRACAO"]))
        bairros_html = html_escape(str(c.get("BAIRROS", "") or "Não informados"))
        # Sem rótulos permanentes: os dados aparecem somente ao clicar na concentração.
        conteudo_popup = (
            "<div style='min-width:230px;max-width:340px;font-size:13px'>"
            f"<b>Concentração {codigo}</b>"
            "<details open style='margin-top:7px'>"
            "<summary style='cursor:pointer;font-weight:600'>Informações da concentração</summary>"
            f"<div style='padding-top:7px'>O.S.: {int(c['QTD_OS'])}<br>"
            f"<b>Matrículas:</b> {int(c['QTD_MATRICULAS'])}<br>"
            f"Bairros: {bairros_html}</div>"
            "</details>"
            "<small style='display:block;margin-top:8px'>O painel completo da concentração também será expandido abaixo do mapa.</small>"
            "</div>"
        )
        popup_concentracao = folium.Popup(conteudo_popup, max_width=370)
        folium.Circle(
            [lat, lon], radius=(raio_circulo if raio_circulo is not None else RAIO_CONCENTRACAO_PADRAO),
            color="purple", fill=True, fill_opacity=0.08,
            popup=popup_concentracao,
        ).add_to(fg_conc)
        # Ponto central discreto e clicável; sem código, contagens ou texto sobre o mapa.
        folium.Marker(
            [lat, lon], icon=icone_bandeira_concentracao(),
            tooltip="🚩 Clique para consultar a concentração",
            popup=folium.Popup(conteudo_popup, max_width=370),
        ).add_to(fg_conc)
    fg_conc.add_to(mapa)

    # As outras concentrações do mesmo município ficam sinalizadas, mesmo
    # quando estão distantes da concentração aberta. Sem carregar suas O.S.
    if outras_concentracoes is not None and not outras_concentracoes.empty:
        fg_outras = folium.FeatureGroup(name="Outras concentrações do município", show=True)
        for _, c in outras_concentracoes.iterrows():
            codigo = html_escape(str(c["ID_CONCENTRACAO"]))
            lat, lon = float(c["LATITUDE"]), float(c["LONGITUDE"])
            resumo = (f"<b>{codigo}</b><br>"
                      f"{html_escape(str(c.get('BAIRROS', '')))}<br>"
                      f"{int(c['QTD_OS'])} O.S. · {int(c['QTD_MATRICULAS'])} matrículas")
            folium.Marker([lat, lon], icon=icone_bandeira_concentracao(),
                          tooltip=f"🚩 {codigo} — outra concentração",
                          popup=folium.Popup(resumo, max_width=320)).add_to(fg_outras)
        fg_outras.add_to(mapa)

    # Centraliza o mapa nos registros efetivamente desenhados, como no Módulo 1.
    coordenadas_visiveis = []
    for quadro, lat_col, lon_col in (
        (df_pontos, "Latitude", "Longitude"),
        (df_pocos, "LATITUDE", "LONGITUDE"),
        (df_loggers, "LATITUDE", "LONGITUDE"),
    ):
        if quadro is not None and not quadro.empty:
            for _, registro in quadro.iterrows():
                lat = normalizar_coordenada(registro.get(lat_col), "lat")
                lon = normalizar_coordenada(registro.get(lon_col), "lon")
                if lat is not None and lon is not None:
                    coordenadas_visiveis.append([lat, lon])
    if coordenadas_visiveis:
        if len(coordenadas_visiveis) == 1:
            mapa.location = coordenadas_visiveis[0]
            mapa.options["zoom"] = 15
        else:
            mapa.fit_bounds(coordenadas_visiveis, padding=(25, 25), max_zoom=15)
    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def normalizar_texto_series(serie):
    return serie.fillna("").astype(str).map(normalizar_texto)



# ============================================================
# CADASTRO DE POÇOS — OPERAÇÕES PRESERVADAS DO MÓDULO ORIGINAL
# ============================================================
def normalizar_coordenada(valor, tipo="lat"):
    n = parse_float(valor)
    if n is None or not math.isfinite(n) or n == 0:
        return None
    if tipo == "lat" and not (-90 <= n <= 90):
        return None
    if tipo == "lon" and not (-180 <= n <= 180):
        return None
    return round(float(n), 6)


def identificacao_exibicao(row):
    nome = str(row.get("NOME_POCO", "")).strip()
    ativo = str(row.get("IDENTIFICACAO_ATIVO", "")).strip()
    return f"{nome} — {ativo}" if nome and ativo else nome or ativo or str(row.get("ID_POCO", ""))


def carregar_pocos():
    return carregar_cadastro_github(ARQUIVO_POCOS_CSV, CABECALHO_POCOS)


def preparar_pocos(df):
    df = df.copy()
    for col in ("LATITUDE", "LONGITUDE"):
        if col in df:
            df[col] = df[col].map(lambda v: normalizar_coordenada(v, "lat" if col == "LATITUDE" else "lon"))
    return df


def invalidar_cache_dados():
    invalidar_cache()


# Os cadastros de poços e loggers são arquivos fixos no GitHub.
# Não há rotinas de cadastro, edição ou exclusão pelo Farol.


# ============================================================
# RELATÓRIOS INDIVIDUAIS DAS CONCENTRAÇÕES
# ============================================================

def dados_relatorio_concentracao(concentracao, pontos_cluster, proximidades, eventos, bairros_geograficos=None):
    """Associa O.S. pelo identificador real do grupo, não pelo ID reordenado."""
    grupo = concentracao["GRUPO"]
    os_grupo = pontos_cluster[pontos_cluster["_grupo"] == grupo].copy()
    codigo = concentracao["ID_CONCENTRACAO"]
    ativos = (
        proximidades[proximidades["Concentração"] == codigo].copy()
        if not proximidades.empty else pd.DataFrame()
    )
    pares_grupo = {
        (normalizar_municipio(r.get("Cidade", "")), limpar_nome_bairro(r.get("Bairro", "")))
        for _, r in os_grupo.iterrows()
        if str(r.get("Cidade", "")).strip() and str(r.get("Bairro", "")).strip()
    }
    eventos_relacionados = []
    if not eventos.empty:
        for _, evento in eventos.iterrows():
            # Preservar histórico de eventos encerrados no relatório; somente o mapa os oculta.
            cidade_evento = normalizar_municipio(evento.get("Cidade", ""))
            if not cidade_evento:
                continue
            municipal = evento_abrange_municipio(evento.get("Áreas Impactadas", ""))
            bairros_evento = {a["bairro"] for a in extrair_bairros_evento(evento.get("Áreas Impactadas", ""), evento.get("Cidade", ""), bairros_geograficos)}
            intersecao = sorted({bairro for cidade, bairro in pares_grupo
                                  if cidade == cidade_evento and (municipal or bairro in bairros_evento)})
            # Uma concentração pode não ter bairro preenchido, mas ainda pertence ao município.
            if municipal and not intersecao and any(
                normalizar_municipio(c) == cidade_evento for c in os_grupo.get("Cidade", [])
            ):
                intersecao = ["Todo o município"]
            if intersecao:
                item = evento.to_dict()
                item["Bairros coincidentes"] = ", ".join(intersecao)
                eventos_relacionados.append(item)
    return os_grupo, ativos, pd.DataFrame(eventos_relacionados)



def interpretar_data_operacional(valor):
    """Converte data/hora real; data sem hora não prova vínculo temporal."""
    if valor is None or str(valor).strip().lower() in ("", "nan", "none", "nat", "-"):
        return pd.NaT
    if isinstance(valor, (datetime, pd.Timestamp)):
        return pd.Timestamp(valor)
    texto = str(valor).strip()
    # Não presumir meia-noite para campos que informam somente a data.
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}", texto):
        return pd.NaT
    try:
        resultado = pd.to_datetime(texto, dayfirst=True, errors="coerce")
        if pd.isna(resultado):
            return pd.NaT
        return pd.Timestamp(resultado).tz_localize(None) if resultado.tzinfo else pd.Timestamp(resultado)
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def classificar_os_por_evento(os_grupo, eventos_relacionados):
    """Associa O.S. por município, bairro e janela [início, término real + 3h].

    Sem horário completo ou término real de evento concluído, não presume vínculo.
    Para eventos ainda abertos, considera o período desde o início até o presente.
    """
    vinculadas, nao_vinculadas = [], []
    agora = pd.Timestamp.now(tz=FUSO_FAROL).tz_localize(None)
    for _, os_reg in os_grupo.iterrows():
        data_os = interpretar_data_operacional(os_reg.get("Dt. Emissão", ""))
        cidade_os = normalizar_municipio(os_reg.get("Cidade", ""))
        bairro_os = limpar_nome_bairro(os_reg.get("Bairro", ""))
        protocolos = []
        if pd.notna(data_os) and eventos_relacionados is not None and not eventos_relacionados.empty:
            for _, evento in eventos_relacionados.iterrows():
                if cidade_os != normalizar_municipio(evento.get("Cidade", "")):
                    continue
                bairros = [limpar_nome_bairro(b) for b in str(evento.get("Bairros coincidentes", "")).split(",")]
                if "Todo o município" not in str(evento.get("Bairros coincidentes", "")) and bairro_os not in bairros:
                    continue
                inicio = interpretar_data_operacional(evento.get("Início", ""))
                fim = interpretar_data_operacional(evento.get("Término Real", ""))
                encerrado = classificar_status_evento(evento.get("Status", ""))[0] == "Finalizado"
                if pd.isna(inicio):
                    continue
                if pd.isna(fim):
                    if encerrado:
                        continue  # Encerrado sem término real: não inventar janela.
                    fim = agora
                if inicio <= data_os <= fim + pd.Timedelta(hours=3):
                    protocolos.append(str(evento.get("Protocolo", "") or evento.get("Serviço", "") or "Evento"))
        linha = os_reg.copy()
        linha["Evento(s) vinculado(s)"] = ", ".join(dict.fromkeys(protocolos))
        if protocolos:
            vinculadas.append(linha)
        else:
            nao_vinculadas.append(linha)
    cols = list(os_grupo.columns) + ["Evento(s) vinculado(s)"]
    def dataframe(linhas):
        return pd.DataFrame(linhas).reindex(columns=cols) if linhas else pd.DataFrame(columns=cols)
    return dataframe(vinculadas), dataframe(nao_vinculadas)


def descricao_eventos_pdf(eventos_relacionados):
    """Resumo Serviço / Código do Ativo dos eventos efetivamente relacionados à concentração."""
    if eventos_relacionados is None or eventos_relacionados.empty:
        return "Nenhum evento relacionado"
    descricoes = []
    for _, evento in eventos_relacionados.iterrows():
        servico = str(evento.get("Serviço", "") or "").strip()
        ativo = str(evento.get("Código do Ativo", "") or "").strip()
        if servico.lower() in ("nan", "none", "nat"):
            servico = ""
        if ativo.lower() in ("nan", "none", "nat"):
            ativo = ""
        descricao = " / ".join(parte for parte in (servico, ativo) if parte)
        if descricao and descricao not in descricoes:
            descricoes.append(descricao)
    return "; ".join(descricoes) if descricoes else "Evento sem serviço/ativo informado"


def texto_relatorio(valor):
    if valor is None or pd.isna(valor):
        return "—"
    return str(valor).strip() or "—"


def mapa_exclusivo_concentracao(concentracao, os_grupo, ativos):
    """Mapa compacto do agrupamento; não depende do enquadramento do mapa principal."""
    lat, lon = float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"])
    mapa = folium.Map(location=[lat, lon], zoom_start=16, tiles="OpenStreetMap",
                      control_scale=True, zoom_control=False, attribution_control=True)
    raio_grupo = RAIO_CONCENTRACAO_PADRAO
    folium.Circle([lat, lon], radius=raio_grupo, color="#8522a5", weight=3,
                  fill=True, fill_color="#8522a5", fill_opacity=0.07).add_to(mapa)
    folium.Marker([lat, lon], icon=icone_bandeira_concentracao()).add_to(mapa)
    for _, registro in os_grupo.iterrows():
        y = normalizar_coordenada(registro.get("Latitude"), "lat")
        x = normalizar_coordenada(registro.get("Longitude"), "lon")
        if y is None or x is None:
            continue
        servico = str(registro.get("Serviço Executado", "") or "")
        cor = "#F28C28" if re.search(r"(?<!\d)146005(?!\d)", servico) else "#1677D2"
        folium.CircleMarker([y, x], radius=4.5, color=cor, weight=1,
                            fill=True, fill_color=cor, fill_opacity=.9).add_to(mapa)
    # A tabela de proximidades não possui coordenadas: recuperá-las dos cadastros locais.
    cadastros = {"LOGGER": carregar_cadastro_github(ARQUIVO_LOGGERS_CSV, CABECALHO_LOGGERS), "ATIVO": carregar_pocos()}
    for _, ativo in ativos.iterrows():
        tipo = str(ativo.get("Tipo", ""))
        eh_logger = "LOGGER" in tipo.upper()
        cadastro = cadastros["LOGGER" if eh_logger else "ATIVO"]
        identificacao = str(ativo.get("Identificação", "") or "").strip()
        correspondencias = cadastro[cadastro["IDENTIFICACAO_ATIVO"].astype(str).str.strip() == identificacao]
        if correspondencias.empty:
            continue
        registro_geo = correspondencias.iloc[0]
        y = normalizar_coordenada(registro_geo.get("LATITUDE"), "lat")
        x = normalizar_coordenada(registro_geo.get("LONGITUDE"), "lon")
        if y is None or x is None:
            continue
        identificacao = identificacao or str(ativo.get("Nome", "") or tipo)
        folium.Marker(
            [y, x], icon=folium.Icon(icon="signal" if eh_logger else "tint",
                                    prefix="fa", color="orange" if eh_logger else "blue"),
            tooltip=folium.Tooltip(html_escape(identificacao), permanent=True,
                                  direction="top", offset=(0, -12),
                                  class_name="farol-rotulo-relatorio"),
            z_index_offset=0 if eh_logger else 1000,
        ).add_to(mapa)
    mapa.get_root().header.add_child(Element("""<style>
    .leaflet-tooltip.farol-rotulo-relatorio {background:rgba(255,255,255,.96);color:#1e293b;
      border:1px solid #cbd5e1;border-radius:4px;padding:2px 5px;
      font:600 11px Arial,sans-serif;box-shadow:0 1px 3px #0002;white-space:nowrap}
    </style>"""))
    # O círculo inteiro deve caber no enquadramento; pequena margem para ruas e rótulos.
    delta_lat = (raio_grupo * 1.13) / 111320.0
    delta_lon = (raio_grupo * 1.13) / (111320.0 * max(.2, math.cos(math.radians(lat))))
    mapa.fit_bounds([[lat-delta_lat, lon-delta_lon], [lat+delta_lat, lon+delta_lon]],
                    padding=(12, 12))
    return mapa


def gerar_pdf_concentracao(concentracao, os_grupo, ativos, eventos_relacionados, raio, imagem_mapa=None):
    """Gera PDF em memória, sem gravar ou alterar informações no Sheets."""
    fonte_regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fonte_negrito = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.isfile(fonte_regular) and "FarolDejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("FarolDejaVu", fonte_regular))
        pdfmetrics.registerFont(TTFont("FarolDejaVu-Bold", fonte_negrito))
        pdfmetrics.registerFontFamily("FarolDejaVu", normal="FarolDejaVu", bold="FarolDejaVu-Bold")
    fonte = "FarolDejaVu" if "FarolDejaVu" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.4*cm,
                            rightMargin=1.4*cm, topMargin=1.3*cm, bottomMargin=1.3*cm)
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("FarolNormal", parent=estilos["Normal"], fontName=fonte, fontSize=8.5, leading=12)
    pequeno = ParagraphStyle("FarolPequeno", parent=normal, fontSize=7, leading=10)
    titulo = ParagraphStyle("FarolTitulo", parent=normal, fontSize=17, leading=22, spaceAfter=8)
    subtitulo = ParagraphStyle("FarolSubtitulo", parent=normal, fontSize=11, leading=16, spaceBefore=12, spaceAfter=6)
    historia = []
    def p(valor, estilo=pequeno):
        return Paragraph(xml_escape(texto_relatorio(valor)), estilo)
    def tabela(cabecalho, linhas, larguras):
        dados = [[p(v) for v in cabecalho]] + [[p(v) for v in linha] for linha in linhas]
        t = Table(dados, colWidths=larguras, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EFF7")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D4DCE5")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t
    historia.append(p("Farol Operacional — " + str(concentracao["ID_CONCENTRACAO"]), titulo))
    historia.append(p("RELATÓRIO INDIVIDUAL DE CONCENTRAÇÃO | VISÃO TERRITORIAL", pequeno))
    historia.append(Spacer(1, .25*cm))
    if imagem_mapa:
        # Ficha em duas colunas: 55% mapa e 45% dados. O restante do PDF permanece tabular.
        largura_mapa, largura_info = 14.15*cm, 11.15*cm
        altura_mapa = 12.1*cm
        mapa_pdf = Image(io.BytesIO(imagem_mapa), width=largura_mapa, height=altura_mapa)
        mapa_pdf.hAlign = "LEFT"
        cidades_ficha = ", ".join(sorted({str(v).strip() for v in os_grupo["Cidade"] if str(v).strip()}))
        info = [
            p("RESUMO OPERACIONAL", subtitulo), Spacer(1, .15*cm),
            p(f"O.S.: {len(os_grupo)}", normal), Spacer(1, .18*cm),
            p(f"Matrículas distintas: {concentracao['QTD_MATRICULAS']}", normal), Spacer(1, .18*cm),
            p(f"Município: {cidades_ficha or 'Não informado'}", normal), Spacer(1, .18*cm),
            p(f"Bairros: {texto_relatorio(concentracao['BAIRROS'])}", normal), Spacer(1, .18*cm),
            p(f"Equipamentos próximos: {len(ativos)}", normal), Spacer(1, .18*cm),
            p(f"Eventos relacionados: {descricao_eventos_pdf(eventos_relacionados)}", normal), Spacer(1, .18*cm),
            p(f"Raio operacional: {raio} m", normal), Spacer(1, .25*cm),
            p("A imagem mostra a concentração e seus equipamentos próximos. A proximidade não comprova vínculo hidráulico ou causalidade.", pequeno),
        ]
        ficha = Table([[mapa_pdf, info]], colWidths=[largura_mapa+.35*cm, largura_info],
                      hAlign="LEFT")
        ficha.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("BACKGROUND", (1,0), (1,0), colors.HexColor("#F4F7FB")),
            ("LEFTPADDING", (0,0), (0,0), 0),
            ("RIGHTPADDING", (0,0), (0,0), 6),
            ("LEFTPADDING", (1,0), (1,0), 12),
            ("TOPPADDING", (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ]))
        historia.append(ficha)
        historia.append(Spacer(1, .25*cm))
    cidades = ", ".join(sorted({str(v).strip() for v in os_grupo["Cidade"] if str(v).strip()}))
    resumo = (
        f"Município(s): {cidades or 'Não informado'} | Bairros: {texto_relatorio(concentracao['BAIRROS'])} | "
        f"O.S.: {len(os_grupo)} | Matrículas: {concentracao['QTD_MATRICULAS']} | "
        f"Raio operacional: {raio} m"
    )
    historia.append(p(resumo, normal))
    historia.append(p(f"Centro: {float(concentracao['LATITUDE']):.6f}, {float(concentracao['LONGITUDE']):.6f}", normal))
    vinculadas, nao_vinculadas = classificar_os_por_evento(os_grupo, eventos_relacionados)
    colunas = ["Nº da O.S", "Matrícula", "Cidade", "Bairro", "Status OS", "Dt. Emissão", "Serviço Executado"]
    for nome_grupo, base in (("Ordens vinculadas aos eventos", vinculadas),
                             ("Ordens não vinculadas", nao_vinculadas)):
        historia.append(p(f"{nome_grupo} ({len(base)})", subtitulo))
        if base.empty:
            historia.append(p("Nenhuma O.S. nesta categoria.", pequeno))
        else:
            linhas = [[r.get(c, "") for c in colunas] for _, r in base.iterrows()]
            historia.append(tabela(colunas, linhas, [2.1*cm, 2.2*cm, 2.5*cm, 3.0*cm, 3.0*cm, 3.3*cm, 10.0*cm]))
    historia.append(p("Poços / ativos e loggers próximos", subtitulo))
    if ativos.empty:
        historia.append(p("Nenhum equipamento encontrado no raio operacional.", normal))
    else:
        cols = ["Tipo", "Identificação", "Nome", "Município", "Distância"]
        historia.append(tabela(cols, [[r.get(c, "") for c in cols] for _, r in ativos.iterrows()],
                                [3.0*cm, 4.0*cm, 10.0*cm, 5.0*cm, 4.1*cm]))
    historia.append(p("Eventos relacionados por município e bairro", subtitulo))
    if eventos_relacionados.empty:
        historia.append(p("Nenhum evento relacionado por correspondência de município e bairro.", normal))
    else:
        cols = ["Protocolo", "Status", "Cidade", "Bairros coincidentes", "Início", "Término Real", "Serviço"]
        historia.append(tabela(cols, [[r.get(c, "") for c in cols] for _, r in eventos_relacionados.iterrows()],
                                [3.1*cm, 2.5*cm, 3.0*cm, 4.5*cm, 4.2*cm, 4.2*cm, 4.6*cm]))
    historia.append(Spacer(1, 0.3*cm))
    historia.append(p("Nota: a relação de eventos é indicativa, baseada na coincidência de bairros e município; não comprova causalidade.", pequeno))
    doc.build(historia)
    return buffer.getvalue()


def exibir_relatorio_concentracao(codigo, concentracoes, pontos_cluster, proximidades, eventos, raio, bairros_geograficos=None):
    registro = concentracoes[concentracoes["ID_CONCENTRACAO"] == codigo]
    if registro.empty:
        st.warning("Concentração não encontrada com os filtros atuais.")
        return
    concentracao = registro.iloc[0]
    os_grupo, ativos, eventos_relacionados = dados_relatorio_concentracao(
        concentracao, pontos_cluster, proximidades, eventos, bairros_geograficos
    )
    cidades = sorted({str(c).strip() for c in os_grupo["Cidade"] if str(c).strip()})
    st.subheader(f"{codigo} — {', '.join(cidades) or 'Município não informado'}")
    st.caption(f"Bairros: {concentracao['BAIRROS'] or 'Não informados'}")
    a, b, c = st.columns(3)
    a.metric("O.S.", len(os_grupo))
    b.metric("Matrículas distintas", int(concentracao["QTD_MATRICULAS"]))
    c.metric("Equipamentos próximos", len(ativos))
    st.markdown(
        f"**Eventos relacionados:** {len(eventos_relacionados)} evento(s) identificado(s)"
        if not eventos_relacionados.empty else "**Eventos relacionados:** nenhum evento identificado"
    )
    st.caption(
        f"Centro geográfico: {float(concentracao['LATITUDE']):.6f}, "
        f"{float(concentracao['LONGITUDE']):.6f} | Raio operacional: {raio} m"
    )
    vinculadas, nao_vinculadas = classificar_os_por_evento(os_grupo, eventos_relacionados)
    colunas_os = ["Nº da O.S", "Matrícula", "Cidade", "Bairro", "Status OS", "Dt. Emissão", "Serviço Executado"]
    for nome_grupo, base in (("Ordens vinculadas aos eventos", vinculadas),
                             ("Ordens não vinculadas", nao_vinculadas)):
        st.markdown(f"#### {nome_grupo} ({len(base)})")
        st.dataframe(base.reindex(columns=colunas_os).fillna(""), width="stretch", hide_index=True)
    st.markdown("#### Poços / ativos e loggers próximos")
    if ativos.empty:
        st.info("Nenhum equipamento dentro do raio operacional desta concentração.")
    else:
        st.dataframe(ativos[["Tipo", "Identificação", "Nome", "Município", "Distância"]],
                     width="stretch", hide_index=True)
    st.markdown("#### Eventos relacionados")
    st.caption("Correspondência por município e bairro impactado; não estabelece relação causal.")
    if eventos_relacionados.empty:
        st.info("Nenhum evento com município e bairro correspondente.")
    else:
        colunas_eventos = ["Protocolo", "Status", "Cidade", "Bairros coincidentes", "Início", "Término Real", "Serviço", "Descrição do Serviço"]
        st.dataframe(eventos_relacionados.reindex(columns=colunas_eventos).fillna(""),
                     width="stretch", hide_index=True)
    # Captura cartográfica apenas sob demanda; evita Chromium em cada rerun do Streamlit.
    if st.button("📸 Preparar PDF com mapa da concentração", key=f"preparar_pdf_{codigo}"):
        try:
            with st.spinner("Capturando mapa aproximado e preparando relatório..."):
                mapa_ficha = mapa_exclusivo_concentracao(concentracao, os_grupo, ativos)
                imagem_ficha = capturar_mapa_folium(mapa_ficha, largura=800, altura=690)
                st.session_state[f"farol_pdf_individual_{codigo}"] = gerar_pdf_concentracao(
                    concentracao, os_grupo, ativos, eventos_relacionados, raio, imagem_ficha
                )
        except Exception as erro:
            st.error(f"Não foi possível gerar o PDF cartográfico: {erro}")
    if st.session_state.get(f"farol_pdf_individual_{codigo}"):
        st.download_button("📄 Baixar relatório em PDF", data=st.session_state[f"farol_pdf_individual_{codigo}"],
                           file_name=f"Farol_{codigo}_{datetime.now(FUSO_FAROL):%Y%m%d}.pdf",
                           mime="application/pdf", key=f"baixar_pdf_{codigo}")


@st.dialog("📥 Importação de bases", width="large")
def modal_importacao():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return
    st.subheader("Importação das bases")
    st.info("PONTOS e EVENTOS não são apagados automaticamente. A limpeza manual está disponível somente ao administrador, na barra lateral do mapa.")

    c1, c2 = st.columns(2)
    with c1:
        arq_os = st.file_uploader("Base diária de O.S.", type=["xlsx", "xls", "csv"], key="upload_os")
        if arq_os is not None:
            try:
                previa = ler_planilha_upload(arq_os)
                st.write(f"**{len(previa):,}** linhas encontradas")
                st.dataframe(previa.head(10), width="stretch", hide_index=True)
                if st.button("Importar O.S. para PONTOS", type="primary", key="btn_importar_os"):
                    preparados = preparar_pontos(previa)
                    inseridas, total = upsert_pontos(preparados)
                    registrar_atualizacao_base("PONTOS")
                    st.success(f"Importação concluída: {inseridas:,} linhas processadas. PONTOS agora possui {total:,} registros.")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro na base de O.S.: {e}")

    with c2:
        arq_eventos = st.file_uploader("Base de eventos", type=["xlsx", "xls", "csv"], key="upload_eventos")
        if arq_eventos is not None:
            try:
                previa_e = ler_planilha_upload(arq_eventos)
                st.write(f"**{len(previa_e):,}** linhas encontradas")
                st.dataframe(previa_e.head(10), width="stretch", hide_index=True)
                if st.button("Importar eventos para EVENTOS", type="primary", key="btn_importar_eventos"):
                    preparados_e = preparar_eventos(previa_e)
                    processados, total = upsert_eventos(preparados_e)
                    registrar_atualizacao_base("EVENTOS")
                    st.success(f"Importação concluída: {processados:,} linhas processadas. EVENTOS agora possui {total:,} registros.")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro na base de eventos: {e}")

    st.divider()
    st.subheader("Resumo do armazenamento")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Poços / Ativos", len(df_pocos))
    m2.metric("Loggers", len(df_loggers))
    m3.metric("O.S. em PONTOS", len(df_pontos))
    m4.metric("Eventos", len(df_eventos))


def atualizar_evento_cadastrado(indice, original, alteracoes):
    """Atualiza somente as células editadas, com proteção contra edição concorrente."""
    exigir_edicao_farol()
    aba = obter_aba_para_leitura(NOME_ABA_EVENTOS)
    valores = aba.get_all_values()
    if not valores or indice + 1 >= len(valores):
        raise ValueError("Evento não encontrado. Reabra a janela e tente novamente.")
    cabecalho = valores[0]
    linha_atual = valores[indice + 1]
    mapa_atual = dict(zip(cabecalho, linha_atual))
    # Garante que outra pessoa não alterou o evento desde sua abertura.
    for campo in CABECALHO_EVENTOS:
        if str(mapa_atual.get(campo, "")) != str(original.get(campo, "")):
            raise ValueError("Este evento foi alterado na planilha. Atualize a página antes de salvar.")
    # A proteção fica em aba independente, para sobreviver à substituição
    # completa da aba EVENTOS durante futuras importações.
    area_antiga = str(original.get("Áreas Impactadas", ""))
    area_nova = str(alteracoes.get("Áreas Impactadas", area_antiga))
    if area_nova != area_antiga:
        registrar_area_editada(chave_evento(original), area_nova)
    for campo, novo_valor in alteracoes.items():
        if campo not in cabecalho:
            raise ValueError(f"Coluna não encontrada na planilha: {campo}")
        pos = cabecalho.index(campo)
        antigo = str(original.get(campo, ""))
        if novo_valor != antigo:
            from gspread.utils import rowcol_to_a1
            aba.update(range_name=rowcol_to_a1(indice + 2, pos + 1),
                       values=[[novo_valor]], value_input_option="RAW")
    invalidar_cache()
    eventos_georreferenciados.clear()


@st.dialog("⚡ Eventos x O.S.", width="large")
def modal_eventos():
    st.subheader("Eventos x O.S. por bairro")

    if df_eventos.empty:
        st.info("A aba EVENTOS ainda não possui dados.")
    elif df_pontos.empty:
        st.warning("Há eventos cadastrados, mas ainda não existem O.S. em PONTOS para o cruzamento.")
    else:
        rel = relacionar_eventos_pontos(df_eventos, df_pontos, bairros)

        if rel.empty:
            st.info("Nenhuma O.S. foi encontrada nos bairros informados em Áreas Impactadas.")
        else:
            st.dataframe(rel.sort_values(["O.S. encontradas", "Matrículas"], ascending=False), width="stretch", hide_index=True)

            fig = px.bar(
                rel.sort_values("O.S. encontradas", ascending=False),
                x="Bairro",
                y="O.S. encontradas",
                color="Status",
                hover_data=["Protocolo", "Matrículas", "Parcial"],
                title="O.S. encontradas nos bairros impactados pelos eventos",
            )
            st.plotly_chart(fig, width="stretch")

        st.divider()
        st.markdown("### Eventos armazenados")
        mostrar_eventos = df_eventos.copy()
        colunas_evento = [c for c in ["Data", "Status", "Cidade", "Serviço", "Protocolo", "Áreas Impactadas", "Descrição do Serviço"] if c in mostrar_eventos.columns]
        st.dataframe(mostrar_eventos[colunas_evento], width="stretch", hide_index=True)

    # A edição permanece disponível mesmo sem O.S. cadastradas.
    if PODE_EDITAR_FAROL and not df_eventos.empty:
        st.divider()
        st.markdown("### ✏️ Corrigir evento cadastrado")
        st.caption("Selecione o evento pela identificação e corrija somente Áreas Impactadas, quando necessário. A correção será preservada nas próximas importações.")
        opcoes = list(range(len(df_eventos)))
        indice_evento = st.selectbox(
            "Evento para editar", opcoes,
            format_func=lambda i: (
                f"{df_eventos.iloc[i].get('Protocolo', '') or 'Sem protocolo'} · "
                f"{df_eventos.iloc[i].get('Cidade', '')} · "
                f"{df_eventos.iloc[i].get('Serviço', '')} · "
                f"{df_eventos.iloc[i].get('Data', '')} · Evento {i + 1}"
            ), key="farol_evento_editar_indice",
        )
        registro = df_eventos.iloc[indice_evento].to_dict()
        st.caption(
            f"Evento {indice_evento + 1} de {len(df_eventos)} — "
            "a numeração exibida não inclui o cabeçalho da planilha."
        )
        with st.form(f"farol_edicao_evento_{indice_evento}"):
            area_atual = str(registro.get("Áreas Impactadas", "") or "")
            area_editada = st.text_area(
                "Áreas Impactadas",
                value=area_atual,
                height=110,
                help="Somente este campo pode ser alterado. A correção ficará protegida nas próximas importações.",
            )
            salvar = st.form_submit_button(
                "💾 Salvar área impactada",
                width="stretch",
            )
        campos = {"Áreas Impactadas": area_editada}
        if salvar:
            try:
                atualizar_evento_cadastrado(indice_evento, registro, campos)
                st.success("Evento atualizado. O mapa e as associações serão recalculados.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar o evento: {erro}")


def capturar_mapa_folium(mapa, largura=1100, altura=600):
    """Renderiza o Folium em Chromium e captura o mapa com as camadas visíveis.

    Requer `playwright` no requirements.txt e Chromium no sistema (packages.txt).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as erro:
        raise RuntimeError("Instale playwright no requirements.txt para gerar o relatório cartográfico.") from erro

    html = mapa.get_root().render()
    # A captura deve ter uma proporção próxima da visualização operacional.
    html = html.replace('</head>', f"""<style>
        html, body {{margin:0 !important; padding:0 !important; width:{largura}px !important; height:{altura}px !important; overflow:hidden !important;}}
        .folium-map {{width:{largura}px !important; height:{altura}px !important;}}
        </style></head>""", 1)
    with tempfile.TemporaryDirectory(prefix="farol_mapa_") as pasta:
        arquivo = os.path.join(pasta, "mapa.html")
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write(html)
        with sync_playwright() as playwright:
            executavel = (os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
                          or shutil.which("chromium-browser") or shutil.which("google-chrome"))
            kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if executavel:
                kwargs["executable_path"] = executavel
            try:
                browser = playwright.chromium.launch(**kwargs)
            except Exception as erro:
                raise RuntimeError("Chromium indisponível. Configure packages.txt com 'chromium' e requirements.txt com 'playwright'.") from erro
            try:
                pagina = browser.new_page(viewport={"width": largura, "height": altura}, device_scale_factor=1.5)
                pagina.goto(Path(arquivo).as_uri(), wait_until="load", timeout=45000)
                pagina.wait_for_function("typeof L !== 'undefined' && document.querySelector('.leaflet-map-pane') !== null", timeout=30000)
                pagina.wait_for_timeout(2400)
                # A imagem não é utilizável se o mapa de fundo não carregou.
                tiles = pagina.locator(".leaflet-tile-loaded")
                if tiles.count() == 0:
                    raise RuntimeError("As imagens de fundo do OpenStreetMap não carregaram no navegador de captura. Verifique a conectividade do servidor.")
                return pagina.locator(".folium-map").first.screenshot(type="png")
            finally:
                browser.close()


def cidades_da_concentracao(concentracao, pontos_cluster):
    if "_grupo" not in pontos_cluster.columns or "Cidade" not in pontos_cluster.columns:
        return []
    grupo = pontos_cluster[pontos_cluster["_grupo"] == concentracao["GRUPO"]]
    return sorted({str(v).strip() for v in grupo["Cidade"] if str(v).strip()}, key=normalizar_texto)


def filtrar_concentracoes_relatorio(concentracoes, pontos_cluster, cidades):
    if not cidades:
        return concentracoes.iloc[0:0].copy()
    nomes = {normalizar_municipio(c) for c in cidades}
    indices = [i for i, c in concentracoes.iterrows()
               if any(normalizar_municipio(nome) in nomes
                      for nome in cidades_da_concentracao(c, pontos_cluster))]
    return concentracoes.loc[indices].copy()


def limites_cidades_relatorio(bairros, cidades):
    """Obtém o enquadramento a partir das feições cartográficas disponíveis."""
    selecionadas = {normalizar_municipio(c) for c in cidades}
    coordenadas = []
    for bairro in bairros:
        if normalizar_municipio(bairro.get("municipio", "")) not in selecionadas:
            continue
        for poligono in bairro.get("poligonos", []):
            for ponto in poligono:
                try:
                    coordenadas.append((float(ponto[0]), float(ponto[1])))
                except (ValueError, TypeError, IndexError):
                    continue
    if not coordenadas:
        return None
    return [[min(y for y, x in coordenadas), min(x for y, x in coordenadas)],
            [max(y for y, x in coordenadas), max(x for y, x in coordenadas)]]


def protocolo_os_relatorio(registro):
    """Número de O.S. com ano da emissão, sem fabricar ano quando ausente."""
    numero = str(registro.get("Nº da O.S", "") or "").strip()
    if not numero or numero.lower() == "nan":
        return ""
    if re.search(r"/\d{4}-1$", numero):
        return numero
    emissao = str(registro.get("Dt. Emissão", "") or "").strip()
    ano = None
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            ano = datetime.strptime(emissao, formato).year
            break
        except ValueError:
            pass
    if ano is None:
        encontrado = re.search(r"(?<!\d)(20\d{2})(?!\d)", emissao)
        if encontrado:
            ano = int(encontrado.group(1))
    return f"{numero}/{ano}-1" if ano else numero


def planilha_os_relatorio(concentracoes, pontos_cluster):
    """CSV tabular, pronto para Excel e para selecionar O.S. por concentração."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(["Concentração", "Município", "Bairro", "O.S. / Ano", "Matrícula", "Status", "Dt. Emissão", "Serviço Executado"])
    for _, c in concentracoes.iterrows():
        if "_grupo" not in pontos_cluster.columns:
            continue
        grupo = pontos_cluster[pontos_cluster["_grupo"] == c["GRUPO"]]
        for _, registro in grupo.iterrows():
            escritor.writerow([str(c["ID_CONCENTRACAO"]), str(registro.get("Cidade", "")),
                              str(registro.get("Bairro", "")), protocolo_os_relatorio(registro),
                              str(registro.get("Matrícula", "")), str(registro.get("Status OS", "")),
                              str(registro.get("Dt. Emissão", "")), str(registro.get("Serviço Executado", ""))])
    return ("\ufeff" + saida.getvalue()).encode("utf-8")


def nome_arquivo_relatorio(cidades=None, extensao="pdf"):
    data = datetime.now(FUSO_FAROL).strftime("%d-%m-%Y")
    if not cidades:
        base = "Relatorio_Geral"
    else:
        nomes = [re.sub(r"[^A-Za-z0-9_-]", "_", unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode("ascii")) for c in cidades]
        base = "Relatorio_" + "_".join(nomes)
    return f"Farol_{base}_{data}.{extensao}"


def mapa_relatorio_concentracoes(concentracoes, pontos_cluster, concentracao=None,
                                  cidades=None, bairros=None, pocos=None, loggers=None,
                                  panoramico=False, pontos=None, raio_ativos=500):
    """Panorama completo com O.S. e infraestrutura; fichas com equipamentos próximos."""
    mapa = folium.Map(location=[-5.09, -42.80], zoom_start=13, tiles="OpenStreetMap",
                      control_scale=True, zoom_control=False)
    selecionadas = (concentracoes if concentracao is None else
                    concentracoes[concentracoes["ID_CONCENTRACAO"] == concentracao["ID_CONCENTRACAO"]])
    coordenadas = []
    # No panorama, a camada de O.S. será desenhada uma única vez, incluindo
    # registros dentro e fora das concentrações.
    if panoramico and pontos is not None and not pontos.empty:
        nomes_os = {normalizar_municipio(v) for v in cidades} if cidades else None
        for _, r in pontos.iterrows():
            if nomes_os is not None and normalizar_municipio(r.get("Cidade", "")) not in nomes_os:
                continue
            y = normalizar_coordenada(r.get("Latitude"), "lat")
            x = normalizar_coordenada(r.get("Longitude"), "lon")
            if y is None or x is None:
                continue
            servico = str(r.get("Serviço Executado", "") or "")
            cor = "#F28C28" if re.search(r"(?<!\d)146005(?!\d)", servico) else "#1677D2"
            folium.CircleMarker([y, x], radius=4, color=cor, weight=1,
                                fill=True, fill_color=cor, fill_opacity=.85).add_to(mapa)
    for _, c in selecionadas.iterrows():
        lat, lon = float(c["LATITUDE"]), float(c["LONGITUDE"])
        raio = RAIO_CONCENTRACAO_PADRAO
        if not panoramico:
            folium.Circle([lat, lon], radius=raio, color="#8522A5", weight=2.5,
                          fill=True, fill_color="#8522A5", fill_opacity=.09).add_to(mapa)
            folium.Marker([lat, lon], icon=icone_bandeira_concentracao()).add_to(mapa)
        coordenadas.append((lat, lon))
        if "_grupo" not in pontos_cluster.columns:
            continue
        grupo = pontos_cluster[pontos_cluster["_grupo"] == c["GRUPO"]]
        if panoramico:
            continue
        for _, r in grupo.iterrows():
            y = normalizar_coordenada(r.get("Latitude"), "lat")
            x = normalizar_coordenada(r.get("Longitude"), "lon")
            if y is None or x is None:
                continue
            servico = str(r.get("Serviço Executado", "") or "")
            cor = "#F28C28" if re.search(r"(?<!\d)146005(?!\d)", servico) else "#1677D2"
            folium.CircleMarker([y, x], radius=4.5, color=cor, weight=1,
                                fill=True, fill_color=cor, fill_opacity=.92).add_to(mapa)
            coordenadas.append((y, x))
    # Panorama: equipamentos do(s) município(s) selecionado(s), sem mostrar
    # cadastros nacionais inteiros. Individual: apenas equipamentos próximos.
    nomes = {normalizar_municipio(v) for v in cidades} if cidades else None
    if panoramico and pocos is not None and loggers is not None:
        # Exatamente como o mapa operacional: apenas equipamentos próximos
        # das concentrações, nunca o cadastro inteiro da cidade.
        pocos, loggers = filtrar_ativos_proximos(selecionadas, pocos, loggers, raio_ativos)
    for cadastro, eh_logger in ((loggers, True), (pocos, False)):
        if cadastro is None or cadastro.empty:
            continue
        for _, r in cadastro.iterrows():
            y = normalizar_coordenada(r.get("LATITUDE"), "lat")
            x = normalizar_coordenada(r.get("LONGITUDE"), "lon")
            if y is None or x is None:
                continue
            if concentracao is not None:
                # Distância geodésica aproximada em metros, suficiente para filtro visual.
                lat0, lon0 = float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"])
                dy = (y-lat0)*111320.0
                dx = (x-lon0)*111320.0*math.cos(math.radians(lat0))
                if math.hypot(dx, dy) > raio_ativos:
                    continue
            elif nomes is not None and normalizar_municipio(r.get("MUNICIPIO", "")) not in nomes:
                continue
            nome = str(r.get("IDENTIFICACAO_ATIVO", "") or r.get("NOME_POCO", "") or "Equipamento")
            if panoramico:
                # No PDF, ambos os tipos de equipamento usam laranja.
                icone = (folium.Icon(icon="signal", prefix="fa", color="orange") if eh_logger
                         else folium.Icon(icon="tint", prefix="fa", color="orange"))
                folium.Marker([y, x], icon=icone,
                              z_index_offset=0 if eh_logger else 1000).add_to(mapa)
            else:
                # Mesma cor para poços/ativos e loggers somente nos mapas do relatório.
                cor = "#FF8C00"
                folium.CircleMarker([y, x], radius=5, color="#663600", weight=1.2,
                                    fill=True, fill_color=cor, fill_opacity=.95).add_to(mapa)
            if concentracao is not None:
                # Rótulo permanente nas fichas, sem alterar o mapa interativo.
                folium.Marker([y, x], icon=folium.DivIcon(
                    html='<div style="position:relative;left:9px;top:-12px;white-space:nowrap;'
                         'font: bold 11px Arial;background:rgba(255,255,255,.94);'
                         'border:1px solid #aab7c4;border-radius:3px;padding:2px 4px;'
                         'color:#193348;display:inline-block">'+html_escape(nome)+'</div>')).add_to(mapa)
    if panoramico:
        # Desenha os círculos DEPOIS dos equipamentos, garantindo que as
        # concentrações continuem visíveis como na referência enviada.
        for _, c in selecionadas.iterrows():
            lat, lon = float(c["LATITUDE"]), float(c["LONGITUDE"])
            folium.Circle([lat, lon], radius=RAIO_CONCENTRACAO_PADRAO,
                          color="#8522A5", weight=3.2, fill=True,
                          fill_color="#8522A5", fill_opacity=.055).add_to(mapa)
            folium.Marker([lat, lon], icon=icone_bandeira_concentracao()).add_to(mapa)
    if coordenadas:
        if concentracao is not None:
            lat, lon = float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"])
            raio = RAIO_CONCENTRACAO_PADRAO * 1.08
            dy = raio / 111320.0
            dx = raio / (111320.0 * max(.2, math.cos(math.radians(lat))))
            extremos = coordenadas + [(lat-dy, lon-dx), (lat+dy, lon+dx)]
            bounds = [[min(y for y, _ in extremos), min(x for _, x in extremos)],
                      [max(y for y, _ in extremos), max(x for _, x in extremos)]]
        else:
            extremos = list(coordenadas)
            for _, c in selecionadas.iterrows():
                y, x = float(c["LATITUDE"]), float(c["LONGITUDE"])
                dy = RAIO_CONCENTRACAO_PADRAO / 111320.0
                dx = RAIO_CONCENTRACAO_PADRAO / (111320.0 * max(.2, math.cos(math.radians(y))))
                extremos.extend([(y-dy, x-dx), (y+dy, x+dx)])
            bounds = [[min(y for y, _ in extremos), min(x for _, x in extremos)],
                      [max(y for y, _ in extremos), max(x for _, x in extremos)]]
            if cidades:
                bounds_cidades = limites_cidades_relatorio(bairros or [], cidades)
                if bounds_cidades:
                    bounds = bounds_cidades
        mapa.fit_bounds(bounds, padding=(18, 18))
    return mapa


def gerar_pdf_operacional(concentracoes, pontos, pontos_cluster, proximidades, eventos,
                           bairros, raio, observacoes, mapa_relatorio=None,
                           cidades=None, pocos=None, loggers=None):
    """Panorama territorial seguido de fichas compactas, com O.S. ao lado do mapa."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2*cm,
                            rightMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("FarolGeralNormal2", parent=estilos["Normal"], fontSize=8.4, leading=11.5)
    pequeno = ParagraphStyle("FarolGeralPequeno2", parent=normal, fontSize=7.1, leading=9.3)
    titulo = ParagraphStyle("FarolGeralTitulo2", parent=estilos["Heading2"], fontSize=12.5, leading=16, spaceAfter=8)
    historia = [Paragraph("Farol Operacional — Relatório de concentrações", estilos["Title"]),
                Paragraph("Gerado em " + datetime.now(FUSO_FAROL).strftime("%d/%m/%Y %H:%M") +
                          (" · Municípios: " + ", ".join(cidades) if cidades else " · Visão geral"), normal),
                Spacer(1, 10)]
    if concentracoes.empty:
        historia.append(Paragraph("Nenhuma concentração identificada para a seleção.", normal))
    else:
        mapa_geral = mapa_relatorio_concentracoes(concentracoes, pontos_cluster,
                    cidades=cidades, bairros=bairros, pocos=pocos, loggers=loggers,
                    panoramico=True, pontos=pontos, raio_ativos=raio)
        imagem_geral = capturar_mapa_folium(mapa_geral, largura=1280, altura=700)
        # Mantém título, imagem e legenda na MESMA página.
        # Altura calculada para caber no A4 paisagem com cabeçalho e margens.
        historia.append(KeepTogether([
            Paragraph("Panorama territorial das concentrações", titulo),
            Image(io.BytesIO(imagem_geral), width=26.0*cm, height=14.22*cm),
            Spacer(1, 4),
            Paragraph(f"Concentrações: {len(concentracoes)} · O.S., concentrações e equipamentos operacionais.", pequeno),
        ]))
        historia.append(PageBreak())
        for indice, (_, c) in enumerate(concentracoes.iterrows()):
            grupo = (pontos_cluster[pontos_cluster["_grupo"] == c["GRUPO"]]
                     if "_grupo" in pontos_cluster.columns else pd.DataFrame())
            codigo = str(c["ID_CONCENTRACAO"])
            nota = str(c.get("OBSERVACAO_ANALISTA", "") or "")
            nomes_cidades = cidades_da_concentracao(c, pontos_cluster)
            bairros_concentracao = str(c.get("BAIRROS", "") or "").replace(";", ", ")
            cabecalho = " - ".join([codigo, ", ".join(nomes_cidades) or "MUNICÍPIO NÃO INFORMADO",
                                     bairros_concentracao or "BAIRRO NÃO INFORMADO"])
            historia.append(Paragraph(xml_escape(cabecalho), titulo))
            imagem_foco = capturar_mapa_folium(
                mapa_relatorio_concentracoes(concentracoes, pontos_cluster, concentracao=c,
                                            pocos=pocos, loggers=loggers, raio_ativos=raio),
                largura=760, altura=560)
            imagem = Image(io.BytesIO(imagem_foco), width=13.4*cm, height=9.87*cm)
            resumo = [
                Paragraph(xml_escape(f"{int(c['QTD_OS'])} O.S. · {int(c['QTD_MATRICULAS'])} matrículas distintas"), normal),
                Spacer(1, 5),
                Paragraph("<b>Acompanhamento:</b> " + xml_escape(nota or "Sem observação registrada"), pequeno),
            ]
            # Usar os registros dos eventos associados à concentração, e não somente sua quantidade.
            _, _, eventos_da_concentracao = dados_relatorio_concentracao(
                c, pontos_cluster, proximidades, eventos, bairros
            )
            resumo.extend([
                Spacer(1, 4),
                Paragraph("<b>Eventos relacionados:</b> " +
                          xml_escape("; ".join(
                              f"{r.get('Protocolo', '')} — {r.get('Serviço', '')} / {r.get('Código do Ativo', '')} "
                              f"[{r.get('Status', '')}] {r.get('Início', '')} até {r.get('Término Real', '') or 'em andamento'}"
                              for _, r in eventos_da_concentracao.iterrows()
                          ) or "Nenhum evento relacionado"), pequeno),
            ])
            vinculadas, nao_vinculadas = classificar_os_por_evento(grupo, eventos_da_concentracao)
            # Distribuir as duas tabelas dentro da área cinza ao lado do mapa.
            # O espaço abaixo do mapa só recebe linhas que não couberem no painel.
            def linhas_pdf(base):
                return [[protocolo_os_relatorio(r), str(r.get("Matrícula", "")),
                         str(r.get("Status OS", ""))] for _, r in base.iterrows()]

            def tabela_os(linhas, largura_total=11.85*cm):
                cab = [[Paragraph("<b>O.S. / Ano</b>", pequeno),
                        Paragraph("<b>Matrícula</b>", pequeno),
                        Paragraph("<b>Status</b>", pequeno)]]
                cab.extend([[Paragraph(xml_escape(str(v)), pequeno) for v in linha] for linha in linhas])
                larguras = [largura_total * 0.37, largura_total * 0.27, largura_total * 0.36]
                t = Table(cab, colWidths=larguras, repeatRows=1, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DEE8F2")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [colors.white, colors.HexColor("#F4F7FB")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                return t

            categorias = [
                ("Ordens vinculadas aos eventos", linhas_pdf(vinculadas)),
                ("Ordens não vinculadas", linhas_pdf(nao_vinculadas)),
            ]

            def construir_resumo(contagens):
                conteudo = list(resumo)
                for (nome, linhas), quantidade in zip(categorias, contagens):
                    conteudo.extend([Spacer(1, 5),
                                     Paragraph(f"<b>{nome} ({len(linhas)})</b>", pequeno)])
                    if linhas:
                        if quantidade:
                            conteudo.append(tabela_os(linhas[:quantidade]))
                    else:
                        conteudo.append(Paragraph("Nenhuma O.S. nesta categoria.", pequeno))
                return conteudo

            # Medir o conteúdo com o próprio motor de layout do ReportLab.
            # Reservar alguns pontos para as margens internas da célula.
            largura_painel = 12.8*cm - 16
            altura_painel = 9.87*cm - 12
            def altura_resumo(elementos):
                altura = 0
                for elemento in elementos:
                    _, h = elemento.wrap(largura_painel, altura_painel)
                    altura += h + elemento.getSpaceBefore() + elemento.getSpaceAfter()
                return altura

            contagens = [0, 0]
            # Preencher primeiro a tabela de vinculadas e depois a de não vinculadas.
            # O cabeçalho de cada categoria é sempre preservado.
            for i, (_, linhas) in enumerate(categorias):
                for _ in linhas:
                    proposta = contagens.copy()
                    proposta[i] += 1
                    if altura_resumo(construir_resumo(proposta)) <= altura_painel:
                        contagens = proposta
                    else:
                        break
            conteudo_painel = construir_resumo(contagens)
            ficha = Table([[imagem, conteudo_painel]], colWidths=[13.8*cm, 12.8*cm], hAlign="LEFT")
            ficha.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F4F7FB")),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            historia.append(ficha)

            # Se houver excedente, continuar abaixo do mapa com o mesmo
            # fundo cinza, cabeçalho azul-claro e listras da tabela lateral.
            for (nome, linhas), exibidas in zip(categorias, contagens):
                restantes = linhas[exibidas:]
                if not restantes:
                    continue
                conteudo_extra = [Paragraph(f"<b>{nome} — continuação</b>", pequeno),
                                  Spacer(1, 4), tabela_os(restantes, largura_total=25.6*cm)]
                painel_extra = Table([[conteudo_extra]], colWidths=[26.6*cm], hAlign="LEFT")
                painel_extra.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FB")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]))
                historia.append(Spacer(1, 6))
                historia.append(painel_extra)
            if indice < len(concentracoes) - 1:
                historia.append(PageBreak())
    doc.build(historia)
    return buffer.getvalue()


@st.dialog("📄 Configurar relatório operacional", width="large")
def modal_configurar_relatorio(concentracoes, pontos, pontos_cluster, proximidades,
                               eventos, bairros, raio, observacoes, pocos, loggers):
    st.caption("API: concentrações dos municípios exceto Teresina. THE: somente Teresina. Os filtros do mapa principal não são alterados.")
    tipo = st.radio("Relatório", ["API", "THE"], horizontal=True,
                    key="farol_tipo_relatorio_api_the")
    disponiveis = sorted({cidade for _, c in concentracoes.iterrows()
                         for cidade in cidades_da_concentracao(c, pontos_cluster)},
                        key=normalizar_texto)
    cidades = ([cidade for cidade in disponiveis
                if normalizar_municipio(cidade) != "TERESINA"]
               if tipo == "API" else
               [cidade for cidade in disponiveis
                if normalizar_municipio(cidade) == "TERESINA"])
    selecionadas = filtrar_concentracoes_relatorio(concentracoes, pontos_cluster, cidades)
    st.caption(f"{len(selecionadas)} concentração(ões) incluída(s) em {tipo}.")
    gerar = st.button("📸 Gerar relatório em PDF", type="primary", width="stretch",
                      disabled=selecionadas.empty)
    if gerar:
        if selecionadas.empty:
            st.warning("Nenhuma concentração encontrada para a seleção.")
        else:
            try:
                # O panorama também deve excluir as O.S. de Teresina no relatório API.
                cidades_normalizadas = {normalizar_municipio(c) for c in cidades}
                pontos_relatorio = pontos.loc[
                    pontos["Cidade"].map(normalizar_municipio).isin(cidades_normalizadas)
                ].copy()
                with st.spinner("Gerando mapa panorâmico e fichas das concentrações..."):
                    pdf = gerar_pdf_operacional(selecionadas, pontos_relatorio, pontos_cluster,
                          proximidades, eventos, bairros, raio, observacoes,
                          cidades=cidades, pocos=pocos, loggers=loggers)
                st.session_state["farol_pdf_operacional_pronto"] = pdf
                st.session_state["farol_pdf_operacional_nome"] = f"Farol_Relatorio_{tipo}.pdf"
                st.session_state["farol_os_relatorio_csv"] = planilha_os_relatorio(selecionadas, pontos_cluster)
                st.session_state["farol_os_relatorio_nome"] = f"Farol_OS_{tipo}.csv"
                st.success(f"Relatório {tipo} gerado. Faça o download abaixo.")
            except Exception as erro:
                st.error(f"Não foi possível gerar o relatório: {erro}")
    if st.session_state.get("farol_pdf_operacional_pronto"):
        st.download_button("⬇️ Baixar relatório gerado",
            data=st.session_state["farol_pdf_operacional_pronto"],
            file_name=st.session_state.get("farol_pdf_operacional_nome", "Farol_Relatorio.pdf"),
            mime="application/pdf", width="stretch",
            key="farol_download_relatorio_modal")
        if st.session_state.get("farol_os_relatorio_csv"):
            st.download_button("📊 Baixar planilha das O.S. (Excel/CSV)",
                data=st.session_state["farol_os_relatorio_csv"],
                file_name=st.session_state.get("farol_os_relatorio_nome", "Farol_OS.csv"),
                mime="text/csv", width="stretch",
                key="farol_download_os_relatorio_csv")

# ============================================================
# INTERFACE
# ============================================================

st.title("Farol Operacional")
st.caption("🧪 AMBIENTE DE DEMONSTRAÇÃO — dados isolados do Módulo 3 | O.S. + Eventos + Bairros geográficos + Poços/Ativos + Loggers")

# Carregamento automático de polígonos de todos os municípios disponíveis.
# A ausência de arquivo geográfico é normal e não gera avisos no mapa.
_inicio_geometria = tempo_execucao.perf_counter()
bairros = descobrir_kmz()
_tempo_geometria = tempo_execucao.perf_counter() - _inicio_geometria

# PONTOS e EVENTOS são mantidos sem limpeza automática.

# Os cadastros são lidos localmente; apenas PONTOS e EVENTOS usam Google Sheets.
_inicio_planilhas = tempo_execucao.perf_counter()
with st.spinner("Carregando dados operacionais..."):
    try:
        df_pocos = carregar_pocos()
        df_loggers = carregar_cadastro_github(ARQUIVO_LOGGERS_CSV, CABECALHO_LOGGERS)
    except (FileNotFoundError, ValueError, pd.errors.ParserError, OSError) as erro:
        st.error(f"Não foi possível carregar os cadastros locais: {erro}")
        st.info("Confira dados/pocos.csv e dados/loggers.csv no GitHub. As abas originais do Google Sheets permanecem como backup.")
        st.stop()
    df_pontos = carregar_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS)
    df_eventos = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)
_tempo_planilhas = tempo_execucao.perf_counter() - _inicio_planilhas

# Normaliza tipos para análise.
if not df_pontos.empty:
    df_pontos = df_pontos.copy()
    for coluna in CABECALHO_PONTOS:
        if coluna not in df_pontos.columns:
            df_pontos[coluna] = ""
    df_pontos["Latitude"] = df_pontos["Latitude"].map(lambda v: normalizar_coordenada(v, "lat"))
    df_pontos["Longitude"] = df_pontos["Longitude"].map(lambda v: normalizar_coordenada(v, "lon"))

if not df_pocos.empty:
    df_pocos = df_pocos.reindex(columns=CABECALHO_POCOS).fillna("")
if not df_loggers.empty:
    df_loggers = df_loggers.reindex(columns=CABECALHO_LOGGERS).fillna("")

# ============================================================
# ABAS
# ============================================================

with st.sidebar:
    st.markdown("### 🚰 Farol Operacional — Módulo 3")
    st.markdown("### 🧭 Navegação")
    if "farol_tela" not in st.session_state:
        st.session_state["farol_tela"] = "mapa"
    if st.button("🗺️ Mapa operacional", width="stretch", type="primary" if st.session_state["farol_tela"] == "mapa" else "secondary"):
        st.session_state["farol_tela"] = "mapa"
        st.rerun()
    if PODE_EDITAR_FAROL:
        if st.button("📥 Importação", width="stretch"):
            modal_importacao()
    if st.button("⚡ Eventos", width="stretch"):
        modal_eventos()
    if st.button("📍 Cadastros", width="stretch", type="primary" if st.session_state["farol_tela"] == "cadastros" else "secondary"):
        st.session_state["farol_tela"] = "cadastros"
        st.rerun()
    if not PODE_EDITAR_FAROL:
        st.caption("🔒 Perfil Operador: somente visualização e downloads.")

    st.divider()
    st.markdown("### 🔎 Filtros")
    # Este seletor controla apenas as camadas de poços e loggers; não filtra O.S. nem concentrações.
    cidades_filtro = set()
    for dados, campo in ((df_pontos, "Cidade"), (df_pocos, "MUNICIPIO"), (df_loggers, "MUNICIPIO")):
        if campo in dados.columns and not dados.empty:
            cidades_filtro.update(str(v).strip() for v in dados[campo].dropna() if str(v).strip())
    cidades_filtro = sorted(cidades_filtro, key=normalizar_texto)
    cidade_sel = st.selectbox("Cidade dos poços e loggers", ["Todas"] + cidades_filtro, key="farol_filtro_cidade_sidebar")
    cidade_especifica = cidade_sel != "Todas"
    mostrar_pocos_cidade = st.checkbox(
        "Mostrar poços / ativos da cidade", value=False,
        disabled=not cidade_especifica, key="farol_mostrar_pocos_cidade",
    )
    mostrar_loggers_cidade = st.checkbox(
        "Mostrar loggers da cidade", value=False,
        disabled=not cidade_especifica, key="farol_mostrar_loggers_cidade",
    )
    if not cidade_especifica:
        st.caption("Os equipamentos próximos às concentrações continuam visíveis. Selecione uma cidade para acrescentar outros equipamentos.")

    st.divider()
    st.markdown("### ⚙️ Configuração")
    raio_operacional = st.number_input(
        "Raio operacional (m)", min_value=50, max_value=5000,
        value=RAIO_OPERACIONAL_PADRAO, step=50,
        help="Distância máxima entre a concentração de O.S. e um Poço/Ativo ou Logger.",
    )
    raio_concentracao = st.number_input(
        "Raio da concentração (m)", min_value=50, max_value=5000,
        value=RAIO_CONCENTRACAO_PADRAO, step=50,
        help="Distância usada para agrupar O.S. espacialmente.",
    )
    minimo_os = st.number_input(
    "Mínimo de O.S. por concentração",
    min_value=2,
    value=3,
    step=1,
)

    # Desativado por padrão: o navegador move o mapa sem enviar centro/zoom
    # ao Python a cada arrasto. Ative apenas para registrar o enquadramento
    # exato que será usado no relatório PDF.
    sincronizar_mapa_pdf = st.checkbox(
        "Sincronizar enquadramento para PDF",
        value=False,
        key="farol_sincronizar_mapa_pdf",
        help="Ative antes de ajustar o mapa para o PDF. Enquanto ativo, arrastar/zoom pode recarregar a página.",
    )
    if sincronizar_mapa_pdf:
        st.caption("Modo PDF ativo: centro e zoom serão registrados. Para navegar sem recarregamentos, desmarque esta opção.")

    if st.session_state.pop("farol_mensagem_limpeza", None):
        st.success("Dados operacionais limpos com sucesso.")
    espaco_relatorio_operacional = st.empty()
    if PERFIL_FAROL == "admin":
        if st.button("🗑️ Limpar dados (PONTOS e EVENTOS)",
                     width="stretch", key="abrir_limpeza_farol"):
            modal_limpar_dados_operacionais()
    if PERFIL_FAROL == "admin":
        espaco_diagnostico_farol = st.empty()
    st.divider()
    if st.button("🏠 Voltar ao Menu Principal", width="stretch"):
        try:
            st.switch_page("app.py")
        except Exception as erro:
            st.error(f"Não foi possível voltar ao Hub. Confira o nome do arquivo principal (app.py): {erro}")
    # O seletor de tema permanece no fim da barra lateral.
    modo_escuro = st.toggle("🌙 Modo escuro", key="farol_modo_escuro")

if modo_escuro:
    st.markdown("""
    <style>
      .stApp { background-color: #0e1117; color: #fafafa; }
      .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
      .stApp h4, .stApp h5, .stApp h6 { color: #f0f0f0 !important; }
      .stButton > button { background-color: #20252d; color: #fafafa; border-color: #444c56; }
    </style>
    """, unsafe_allow_html=True)


def ativos_da_cidade(df, campo, cidade, habilitado):
    """Evita enviar ao Folium milhares de equipamentos de outros municípios."""
    if not habilitado or cidade == "Todas" or df.empty or campo not in df.columns:
        return df.iloc[0:0].copy()
    return df.loc[normalizar_texto_series(df[campo]) == normalizar_texto(cidade)].copy()

ativos_pocos_cidade = ativos_da_cidade(df_pocos, "MUNICIPIO", cidade_sel, mostrar_pocos_cidade)
ativos_loggers_cidade = ativos_da_cidade(df_loggers, "MUNICIPIO", cidade_sel, mostrar_loggers_cidade)


if st.session_state.get("farol_tela", "mapa") == "mapa":
    eventos_mapeados, eventos_sem_geometria = [], []  # V2: eventos geográficos somente no detalhe
    st.subheader("🗺️ Farol V2 — Panorama e concentrações")

    st.caption("Eventos: vermelho = em andamento · amarelo = programado · verde = finalizado · cinza = outro status. "
               "As áreas destacadas representam os bairros inteiros dos arquivos geográficos, inclusive quando o evento informa impacto parcial.")

    if df_pontos.empty:
        st.warning("A aba PONTOS ainda não possui dados.")
        ativos_pocos = ativos_pocos_cidade
        ativos_loggers = ativos_loggers_cidade
        mapa = criar_mapa(
            bairros, df_pontos, ativos_pocos, ativos_loggers,
            pd.DataFrame(), pd.DataFrame(), mostrar_bairros=bool(bairros),
            eventos_mapeados=eventos_mapeados,
        )
        if st.session_state.get("farol_foco_concentracao"):
            lat_foco, lon_foco = st.session_state["farol_foco_concentracao"]
            mapa.location = [lat_foco, lon_foco]
            mapa.options["zoom"] = 15
            mapa.fit_bounds([[lat_foco - .007, lon_foco - .007], [lat_foco + .007, lon_foco + .007]])
        estado_mapa = st_folium(
            mapa, width=None, height=650,
            returned_objects=["center", "zoom"] if sincronizar_mapa_pdf else [],
            key="farol_mapa_principal",
        )
        exibir_atualizacoes_abaixo_mapa()
        if sincronizar_mapa_pdf and estado_mapa:
            if estado_mapa.get("center") is not None:
                st.session_state["farol_ultimo_centro_mapa"] = estado_mapa["center"]
            if estado_mapa.get("zoom") is not None:
                st.session_state["farol_ultimo_zoom_mapa"] = estado_mapa["zoom"]
    else:
        # Filtros.
        f1, f2, f3 = st.columns(3)
        bairros_os = sorted([x for x in df_pontos["Bairro"].dropna().astype(str).unique() if x.strip()])
        status_os = sorted([x for x in df_pontos["Status OS"].dropna().astype(str).unique() if x.strip()])

        with f1:
            bairro_sel = st.multiselect("Bairro", bairros_os)
        with f2:
            status_sel = st.multiselect("Status", status_os)
        with f3:
            apenas_com_coord = st.checkbox("Somente O.S. georreferenciada", value=True)

        servicos_os = sorted({str(x).strip() for x in df_pontos["Serviço Executado"].fillna("")
                              if str(x).strip()})
        servico_sel = st.multiselect(
            "Tipo da O.S",
            options=servicos_os,
            placeholder="Todos os tipos",
            help="Selecione um ou mais serviços; sem seleção, todos são exibidos.",
            key="farol_filtro_servico_executado",
        )

        analise = df_pontos.copy()
        if bairro_sel:
            bairros_norm = {limpar_nome_bairro(x) for x in bairro_sel}
            analise = analise[analise["Bairro"].map(limpar_nome_bairro).isin(bairros_norm)]
        if status_sel:
            status_norm = {normalizar_texto(x) for x in status_sel}
            analise = analise[analise["Status OS"].map(normalizar_texto).isin(status_norm)]
        if servico_sel:
            servicos_norm = {normalizar_texto(x) for x in servico_sel}
            analise = analise[analise["Serviço Executado"].map(normalizar_texto).isin(servicos_norm)]
        if apenas_com_coord:
            analise = analise.dropna(subset=["Latitude", "Longitude"])

        _inicio_analise = tempo_execucao.perf_counter()
        concentracoes, pontos_cluster = criar_concentracoes(
            analise,
            raio_m=raio_concentracao,
            minimo_os=int(minimo_os),
        )
        proximidades = pontos_proximos_concentracoes(
            concentracoes,
            df_pocos,
            df_loggers,
            raio=int(raio_operacional),
        )
        municipios_por_concentracao = municipios_das_concentracoes(concentracoes, pontos_cluster)
        municipios_panorama = set().union(*municipios_por_concentracao.values()) if municipios_por_concentracao else set()
        bairros_panorama = bairros_dos_municipios(bairros, municipios_panorama)
        eventos_mapeados_todos, eventos_sem_geometria = eventos_georreferenciados(df_eventos, bairros)
        eventos_panorama = [e for e in eventos_mapeados_todos
                            if normalizar_municipio(e["bairro"].get("municipio", "")) in municipios_panorama]


        _tempo_analise = tempo_execucao.perf_counter() - _inicio_analise

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("O.S. analisadas", len(analise))
        k2.metric("O.S. com coordenada", int(analise[["Latitude", "Longitude"]].notna().all(axis=1).sum()))
        k3.metric("Concentrações", len(concentracoes))
        k4.metric("Pontos operacionais próximos", len(proximidades))

        # Panorama sem O.S./equipamentos, mas com bairros e eventos de todos os municípios analisados.
        st.caption("Panorama: limites de bairros e áreas impactadas por eventos; selecione uma bandeira 🚩 para abrir a concentração.")
        _inicio_renderizacao = tempo_execucao.perf_counter()
        codigos_validos = set(concentracoes["ID_CONCENTRACAO"].astype(str))
        selecionada = str(st.session_state.get("farol_v2_concentracao", "") or "")
        if selecionada not in codigos_validos:
            selecionada = ""
            st.session_state["farol_v2_concentracao"] = ""

        if selecionada:
            c_atual = concentracoes.loc[concentracoes["ID_CONCENTRACAO"].astype(str) == selecionada].iloc[0]
            st.markdown(f"### 📍 {selecionada} — Detalhamento operacional")
            if st.button("⬅️ Voltar ao panorama", key="farol_v2_voltar"):
                st.session_state["farol_v2_concentracao"] = ""
                st.session_state["farol_concentracao_expandida"] = ""
                st.rerun()
            grupo_atual = pontos_cluster.loc[pontos_cluster["_grupo"] == c_atual["GRUPO"]].copy()
            lat_c, lon_c = float(c_atual["LATITUDE"]), float(c_atual["LONGITUDE"])

            # Exibir as demais concentrações cujos círculos se tocam ou ficam
            # muito próximos. A proximidade é VISUAL: não altera a formação,
            # a numeração nem as contagens das concentrações originais.
            raio_feicao = float(raio_concentracao)
            tolerancia_vizinhanca_m = 75.0
            cidades_atual = {
                normalizar_texto(x) for x in grupo_atual["Cidade"].dropna().astype(str)
                if str(x).strip()
            } if "Cidade" in grupo_atual.columns else set()
            concentracoes_visiveis = [c_atual]
            for _, candidata in concentracoes.iterrows():
                if str(candidata["ID_CONCENTRACAO"]) == selecionada:
                    continue
                # Não aproximar concentrações de municípios distintos.
                grupo_candidata = pontos_cluster.loc[
                    pontos_cluster["_grupo"] == candidata["GRUPO"]
                ]
                cidades_candidata = {
                    normalizar_texto(x) for x in grupo_candidata["Cidade"].dropna().astype(str)
                    if str(x).strip()
                } if "Cidade" in grupo_candidata.columns else set()
                if cidades_atual and cidades_candidata and not (cidades_atual & cidades_candidata):
                    continue
                distancia = distancia_metros(lat_c, lon_c, candidata["LATITUDE"], candidata["LONGITUDE"])
                if distancia is not None and distancia <= 2 * raio_feicao + tolerancia_vizinhanca_m:
                    concentracoes_visiveis.append(candidata)

            concentracoes_detalhe = pd.DataFrame(concentracoes_visiveis)
            ids_detalhe = set(concentracoes_detalhe["ID_CONCENTRACAO"].astype(str))
            vizinhas = [str(c["ID_CONCENTRACAO"]) for c in concentracoes_visiveis[1:]]

            # Inclui os pontos das concentrações vizinhas e O.S. no entorno,
            # sem carregar as O.S. do município inteiro.
            raio_visual = max(raio_feicao * 1.5, 650.0)
            lat_os = pd.to_numeric(analise["Latitude"], errors="coerce").to_numpy(dtype=float)
            lon_os = pd.to_numeric(analise["Longitude"], errors="coerce").to_numpy(dtype=float)
            mascara_os = np.zeros(len(analise), dtype=bool)
            for c in concentracoes_visiveis:
                lat_ref = math.radians(float(c["LATITUDE"]))
                lon_ref = math.radians(float(c["LONGITUDE"]))
                dlat = np.radians(lat_os) - lat_ref
                dlon = np.radians(lon_os) - lon_ref
                h = (np.sin(dlat / 2) ** 2
                     + np.cos(lat_ref) * np.cos(np.radians(lat_os)) * np.sin(dlon / 2) ** 2)
                distancias = 2 * 6371000.0 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
                mascara_os |= np.isfinite(distancias) & (distancias <= raio_visual)
            pontos_mapa = analise.loc[mascara_os].copy()

            # Equipamentos próximos de TODAS as feições visíveis, sem mudar
            # os equipamentos vinculados ao painel da concentração principal.
            proximidades_atuais = proximidades.loc[
                proximidades["Concentração"].astype(str).isin(ids_detalhe)
            ].copy() if not proximidades.empty else proximidades.copy()
            def _ativos_detalhe(base, tipo):
                if base.empty or proximidades_atuais.empty:
                    return base.iloc[0:0].copy()
                ids = set(proximidades_atuais.loc[
                    proximidades_atuais["Tipo"] == tipo, "Identificação"
                ].fillna("").astype(str).map(normalizar_texto))
                return base.loc[base["IDENTIFICACAO_ATIVO"].fillna("").astype(str).map(normalizar_texto).isin(ids)].copy()
            ativos_pocos = _ativos_detalhe(df_pocos, "Poço / Ativo")
            ativos_loggers = _ativos_detalhe(df_loggers, "Logger")
            # O filtro opcional da cidade acrescenta equipamentos, sem duplicações.
            if not ativos_pocos_cidade.empty:
                ativos_pocos = df_pocos.loc[df_pocos.index.isin(ativos_pocos.index.union(ativos_pocos_cidade.index))].copy()
            if not ativos_loggers_cidade.empty:
                ativos_loggers = df_loggers.loc[df_loggers.index.isin(ativos_loggers.index.union(ativos_loggers_cidade.index))].copy()
            # Todas as feições dos bairros do município, não apenas as
            # próximas ao círculo ou com evento cadastrado.
            cidades_detalhe = municipios_por_concentracao.get(selecionada, set())
            bairros_detalhe = bairros_dos_municipios(bairros, cidades_detalhe)
            eventos_mapeados = [e for e in eventos_mapeados_todos
                                if normalizar_municipio(e["bairro"].get("municipio", "")) in cidades_detalhe]
            # As concentrações distantes permanecem identificadas com bandeira.
            # As vizinhas, cujos círculos se tocam, já são desenhadas completas.
            outras_concentracoes = concentracoes.loc[
                concentracoes["ID_CONCENTRACAO"].astype(str).map(
                    lambda cod: cod not in ids_detalhe and bool(
                        municipios_por_concentracao.get(cod, set()) & cidades_detalhe)
                )
            ].copy()
            mapa = criar_mapa(
                bairros_detalhe, pontos_mapa, ativos_pocos, ativos_loggers,
                concentracoes_detalhe,
                proximidades_atuais, mostrar_bairros=True,
                eventos_mapeados=eventos_mapeados,
                raio_circulo=raio_concentracao,
                outras_concentracoes=outras_concentracoes,
                rotulos_equipamentos=True,
            )
            # Ajusta o enquadramento para mostrar integralmente os círculos
            # próximos, com margem para O.S. e equipamentos.
            limites = []
            for c in concentracoes_visiveis:
                lat_ref, lon_ref = float(c["LATITUDE"]), float(c["LONGITUDE"])
                delta_lat = raio_visual / 111320.0
                delta_lon = raio_visual / (111320.0 * max(.2, math.cos(math.radians(lat_ref))))
                limites.extend([[lat_ref - delta_lat, lon_ref - delta_lon],
                                [lat_ref + delta_lat, lon_ref + delta_lon]])
            mapa.fit_bounds(limites, padding=(25, 25))
            estado_mapa = st_folium(
                mapa, width=None, height=650,
                returned_objects=["center", "zoom"] if sincronizar_mapa_pdf else [],
                key="farol_v2_mapa_detalhe",
            )
            st.caption(f"Mapa detalhado: {len(pontos_mapa)} O.S. na área, "
                       f"{len(ativos_pocos)} poço(s)/ativo(s) e {len(ativos_loggers)} logger(s).")
            if vizinhas:
                st.info("Concentração(ões) próxima(s) também visível(is): "
                        + ", ".join(vizinhas)
                        + ". Os agrupamentos permanecem independentes; selecione outro registro na lista para analisar seus dados.")
        else:
            mapa = criar_mapa_panorama_v2(
                concentracoes, raio_m=raio_concentracao,
                bairros=bairros_panorama, eventos_mapeados=eventos_panorama,
            )
            estado_mapa = st_folium(
                mapa, width=None, height=650,
                returned_objects=["last_object_clicked"],
                key="farol_v2_mapa_panorama",
            )
            clique = (estado_mapa or {}).get("last_object_clicked")
            if isinstance(clique, dict) and not concentracoes.empty:
                lat_clique = parse_float(clique.get("lat"))
                lon_clique = parse_float(clique.get("lng"))
                if lat_clique is not None and lon_clique is not None:
                    melhor, menor = "", float("inf")
                    for _, centro in concentracoes.iterrows():
                        d = distancia_metros(lat_clique, lon_clique,
                                             centro["LATITUDE"], centro["LONGITUDE"])
                        if d is not None and d < menor:
                            menor, melhor = d, str(centro["ID_CONCENTRACAO"])
                    if melhor and menor <= 4:
                        st.session_state["farol_v2_concentracao"] = melhor
                        st.session_state["farol_concentracao_expandida"] = melhor
                        st.rerun()
            # A lista tradicional de concentrações permanece abaixo do mapa.
            # Evita-se o seletor adicional, que causava outra interação e rerun.
        exibir_atualizacoes_abaixo_mapa()
        if sincronizar_mapa_pdf and estado_mapa and selecionada:
            if estado_mapa.get("center") is not None:
                st.session_state["farol_ultimo_centro_mapa"] = estado_mapa["center"]
            if estado_mapa.get("zoom") is not None:
                st.session_state["farol_ultimo_zoom_mapa"] = estado_mapa["zoom"]

        _tempo_mapa = tempo_execucao.perf_counter() - _inicio_renderizacao
        if PERFIL_FAROL == "admin":
            with espaco_diagnostico_farol.container():
                with st.expander("⏱️ Diagnóstico de desempenho", expanded=False):
                    st.caption("Tempo desta interação; valores baixos podem indicar uso do cache.")
                    st.write(f"Geometrias: {_tempo_geometria:.2f} s")
                    st.write(f"Google Sheets: {_tempo_planilhas:.2f} s")
                    st.write(f"Análise espacial: {_tempo_analise:.2f} s")
                    st.write(f"Montagem e exibição do mapa: {_tempo_mapa:.2f} s")
        if concentracoes.empty:
            st.warning("Nenhuma concentração atingiu o mínimo configurado.")
        else:
            st.markdown("### 📋 Análise das Concentrações")
            st.caption("Expanda uma concentração para consultar O.S., equipamentos, eventos relacionados e baixar o PDF.")
            observacoes_df = carregar_observacoes_concentracoes()
            resumo_pdf = concentracoes.copy()
            grupos_os = {chave: quadro for chave, quadro in pontos_cluster.groupby("_grupo", sort=False)} if not pontos_cluster.empty else {}
            # Mesma divisão geográfica adotada nos relatórios PDF.
            aba_api, aba_the = st.tabs(["🌐 API — Demais municípios", "📍 THE — Teresina"])
            for aba, abrangencia in ((aba_api, "API"), (aba_the, "THE")):
                with aba:
                    cidades_abrangencia = sorted({
                        cidade
                        for _, conc in concentracoes.iterrows()
                        for cidade in cidades_da_concentracao(conc, pontos_cluster)
                        if (normalizar_municipio(cidade) != "TERESINA") == (abrangencia == "API")
                    }, key=normalizar_texto)
                    concentracoes_abrangencia = concentracoes.loc[
                        concentracoes["ID_CONCENTRACAO"].astype(str).str.startswith(f"{abrangencia} ")
                    ].copy()
                    st.caption(f"{len(concentracoes_abrangencia)} concentração(ões) em {abrangencia}.")
                    if concentracoes_abrangencia.empty:
                        st.info("Nenhuma concentração encontrada nesta abrangência.")
                    for _, concentracao in concentracoes_abrangencia.iterrows():
                        codigo = concentracao["ID_CONCENTRACAO"]
                        os_grupo = grupos_os.get(concentracao["GRUPO"], pontos_cluster.iloc[0:0])
                        cidades_grupo = sorted({str(v).strip() for v in os_grupo["Cidade"] if str(v).strip()})
                        qtd_ativos = (int((proximidades["Concentração"] == codigo).sum())
                                      if not proximidades.empty else 0)
                        _, _, eventos_do_grupo = dados_relatorio_concentracao(
                            concentracao, pontos_cluster, proximidades, df_eventos, bairros
                        )
                        indicador_eventos = (
                            f"⚡ {len(eventos_do_grupo)} evento(s) relacionado(s)"
                            if not eventos_do_grupo.empty else "Sem evento relacionado"
                        )
                        municipio_nota, chave_nota, texto_nota = identificar_observacao(
                            concentracao, os_grupo, observacoes_df, raio_concentracao
                        )
                        resumo_pdf.loc[resumo_pdf["ID_CONCENTRACAO"] == codigo, "OBSERVACAO_ANALISTA"] = texto_nota
                        resumo_pdf.loc[resumo_pdf["ID_CONCENTRACAO"] == codigo, "EVENTOS_RELACIONADOS"] = len(eventos_do_grupo)
                        indicador_nota = ("📝 " + texto_nota.replace("\n", " ")[:110] + ("…" if len(texto_nota) > 110 else "")) if texto_nota.strip() else "Sem acompanhamento registrado"
                        bairros_grupo = str(concentracao.get("BAIRROS", "") or "").strip()
                        titulo = (
                            f"{codigo} — {', '.join(cidades_grupo) or 'Município não informado'}"
                            f" — {bairros_grupo or 'Bairro não informado'} | "
                            f"{int(concentracao['QTD_OS'])} O.S. · "
                            f"{int(concentracao['QTD_MATRICULAS'])} matrículas · "
                            f"{qtd_ativos} ativo(s) próximo(s) · {indicador_eventos} · {indicador_nota}"
                        )
                        # Preservar TODOS os registros no formato original de expansores.
                        # Somente a concentração ativa carrega o relatório detalhado,
                        # evitando gerar tabelas e componentes pesados para as demais.
                        ativa = str(codigo) == str(st.session_state.get("farol_v2_concentracao", ""))
                        with st.expander(titulo, expanded=ativa):
                            if st.button("🗺️ Abrir mapa desta concentração" if not ativa else "📍 Mapa desta concentração aberto",
                                         key=f"farol_v2_foco_{abrangencia}_{codigo}", disabled=ativa):
                                st.session_state["farol_v2_concentracao"] = str(codigo)
                                st.session_state["farol_concentracao_expandida"] = str(codigo)
                                st.rerun()
                            # As informações são exibidas ao expandir o painel,
                            # independentemente de abrir o mapa da concentração.
                            if PODE_EDITAR_FAROL:
                                nota_editada = st.text_area("Observação do analista", value=texto_nota,
                                                            key=f"farol_v2_nota_{abrangencia}_{codigo}_{chave_nota}", height=90,
                                                            placeholder="Ex.: Contato com a operação, verificação do abastecimento, providências...")
                                if st.button("💾 Salvar acompanhamento", key=f"farol_v2_salvar_nota_{abrangencia}_{codigo}"):
                                    try:
                                        salvar_observacao_concentracao(chave_nota, municipio_nota,
                                            float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"]), nota_editada)
                                        st.success("Acompanhamento salvo.")
                                        st.rerun()
                                    except Exception as erro:
                                        st.error(f"Não foi possível salvar: {erro}")
                            else:
                                st.caption("Observação do analista: " + (texto_nota or "Nenhuma observação registrada."))
                            exibir_relatorio_concentracao(
                                codigo, concentracoes, pontos_cluster, proximidades,
                                df_eventos, int(raio_operacional), bairros
                            )
        # Disponível também quando não há concentrações no filtro atual.
        if concentracoes.empty:
            resumo_pdf = concentracoes.copy()
            observacoes_df = pd.DataFrame()
        with espaco_relatorio_operacional.container():
            st.caption("Relatórios API (exceto Teresina) ou THE (somente Teresina), com panorama e fichas individuais.")
            if st.button("📄 Configurar e gerar relatório (PDF)",
                         width="stretch", key="abrir_configuracao_relatorio"):
                modal_configurar_relatorio(resumo_pdf, analise, pontos_cluster,
                    proximidades, df_eventos, bairros, int(raio_operacional),
                    observacoes_df, df_pocos, df_loggers)
    # Sem dados de O.S.: manter a opção visível, porém desabilitada.
    if df_pontos.empty:
        espaco_relatorio_operacional.button(
            "📄 Gerar relatório operacional (PDF)", disabled=True,
            width="stretch", key="relatorio_sem_pontos"
        )



if st.session_state.get("farol_tela", "mapa") == "cadastros":
    espaco_relatorio_operacional.caption("📄 Relatório disponível na tela Mapa operacional.")
    st.subheader("Consulta de Poços / Ativos e Loggers")
    st.caption("Cadastros fixos carregados dos arquivos dados/pocos.csv e dados/loggers.csv do GitHub. Para atualizar, substitua os arquivos no repositório.")
    c_poco, c_logger = st.columns(2)
    with c_poco:
        st.markdown("### Poços / Ativos")
        st.metric("Registros", len(df_pocos))
        st.dataframe(df_pocos, width="stretch", hide_index=True)
    with c_logger:
        st.markdown("### Loggers")
        st.metric("Registros", len(df_loggers))
        st.dataframe(df_loggers, width="stretch", hide_index=True)
