import io
import json
import os
import re
import math
import hashlib
import zipfile
import sqlite3
import threading
from xml.sax.saxutils import escape as xml_escape
from html import escape as html_escape
from zoneinfo import ZoneInfo
import unicodedata
from datetime import datetime, date, time as horario
import xml.etree.ElementTree as ET

import gspread
import pandas as pd
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from google.oauth2.service_account import Credentials
from streamlit_folium import st_folium

from auth import verificar_autenticacao, tem_acesso_modulo


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Farol Operacional",
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
FUSO_FAROL = ZoneInfo("America/Fortaleza")  # Teresina: UTC-3
RESET_HORARIO = horario(0, 1)
_RESET_LOCK = threading.Lock()

RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRETORIO_KMZ = os.path.join(RAIZ_PROJETO, "geodados", "municipios")
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
    texto = re.sub(r"\s+", " ", texto).strip()
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


def extrair_bairros_evento(valor, municipio="", bairros_geograficos=None):
    """Lê bairros em listas, linhas e rótulos; separa 'e' só se ambos existirem no GPKG.

    Nunca usa fuzzy matching nem divide nomes compostos sem confirmação.
    Retorna chaves normalizadas para mapa, cruzamento de O.S. e relatórios.
    """
    if valor is None or str(valor).strip().lower() in ("", "nan", "none"):
        return []
    nomes = indice_nomes_bairros(bairros_geograficos, municipio)
    texto = str(valor).replace("\r", "\n")
    texto = re.sub(r"(?i)\bBAIRROS?\s*(?:IMPACTADOS?|AFETADOS?)?\s*:", "\n", texto)
    texto = re.sub(r"(?i)\bAREAS?\s+IMPACTADAS?\s*:", "\n", texto)
    partes = re.split(r"[,;\n]+", texto)
    saida = []
    vistos = set()
    for parte in partes:
        original = parte.strip(" \t-*•")
        if not original:
            continue
        # Desconsidera linha isolada com o nome da cidade, quando a descrição o inclui.
        if municipio and normalizar_municipio(original) == normalizar_municipio(municipio):
            continue
        parcial = bool(re.search(r"\(\s*PARCIAL\s*\)", original, flags=re.I))
        chave = resolver_nome_bairro(original, nomes)
        candidatos = [(chave, original)]
        if nomes and chave not in nomes:
            # Só divide 'A e B' se os dois nomes resultantes estiverem no município.
            pedacos = re.split(r"\s+E\s+", chave)
            if len(pedacos) == 2:
                esquerda = resolver_nome_bairro(pedacos[0], nomes)
                direita = resolver_nome_bairro(pedacos[1], nomes)
                if esquerda in nomes and direita in nomes:
                    candidatos = [(esquerda, pedacos[0]), (direita, pedacos[1])]
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
def obter_planilha():
    planilha = obter_cliente_google().open_by_key(SPREADSHEET_ID)

    return planilha


def obter_aba(nome, cabecalho):
    planilha = obter_planilha()
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


@st.cache_data(ttl=60, show_spinner=False)
def carregar_aba(nome, cabecalho):
    aba = obter_aba(nome, cabecalho)
    # Preserva as vírgulas decimais das coordenadas (ex.: -5,18817).
    # A conversão automática do gspread interpreta a vírgula como milhar
    # e transforma -5,18817 em -518817, invalidando os marcadores.
    registros = aba.get_all_records(numericise_ignore=["all"])
    if not registros:
        return pd.DataFrame(columns=cabecalho)
    return pd.DataFrame(registros)


def invalidar_cache():
    carregar_aba.clear()


def reset_diario_se_necessario():
    """Limpa apenas PONTOS e EVENTOS uma vez por dia operacional.

    Executa na primeira abertura/atualização do app após 00:01 de Teresina.
    A aba de controle guarda a data do último reset para evitar repetição.
    """
    agora = datetime.now(FUSO_FAROL)
    dia_operacional = agora.date() if agora.time() >= RESET_HORARIO else (agora.date() - pd.Timedelta(days=1)).date()
    chave_dia = dia_operacional.isoformat()

    with _RESET_LOCK:
        planilha = obter_planilha()
        if planilha.id != SPREADSHEET_ID:
            raise RuntimeError("ID da planilha diferente da planilha exclusiva do Farol.")
        try:
            controle = planilha.worksheet(NOME_ABA_CONTROLE)
        except gspread.WorksheetNotFound:
            # A única aba criada automaticamente é o controle de reset, na planilha Farol validada.
            controle = planilha.add_worksheet(title=NOME_ABA_CONTROLE, rows=10, cols=2)
            controle.update("A1:B1", [["ULTIMO_RESET", "HORARIO_LOCAL"]])

        ultimo_reset = str(controle.acell("A2").value or "").strip()
        if ultimo_reset == chave_dia:
            return

        # A limpeza é feita antes de registrar a data. Em caso de erro,
        # a próxima execução tentará novamente, sem perder os cabeçalhos.
        for nome in (NOME_ABA_PONTOS, NOME_ABA_EVENTOS):
            aba = planilha.worksheet(nome)
            if aba.row_count > 1:
                ultima_coluna = gspread.utils.rowcol_to_a1(1, aba.col_count)[:-1]
                aba.batch_clear([f"A2:{ultima_coluna}{aba.row_count}"])
        controle.update("A2:B2", [[chave_dia, agora.strftime("%d/%m/%Y %H:%M:%S")]])
        invalidar_cache()


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


def upsert_eventos(df_novo):
    exigir_edicao_farol()
    atual = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)
    atual = atual.reindex(columns=CABECALHO_EVENTOS).fillna("")
    novo = df_novo.reindex(columns=CABECALHO_EVENTOS).fillna("")

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
            campo_bairro = next((campos[k] for k in ("NMBAIRRO", "BAIRRO", "NOMEBAIRRO", "NOME") if k in campos), None)
            campo_mun = next((campos[k] for k in ("NMMUN", "MUNICIPIO", "CIDADE", "NOMEMUNICIPIO") if k in campos), None)
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
    return re.sub(r"^NM_MUN[_\s-]*", "", nome, flags=re.I)


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
            todos.extend(registros)
        except Exception:
            # Não exibe avisos de arquivos sem cobertura, mantendo os eventos na planilha.
            continue
    return todos


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
    cdf["ID_CONCENTRACAO"] = [f"C{i:03d}" for i in range(1, len(cdf) + 1)]
    return cdf, df


def pontos_proximos_concentracoes(concentracoes, df_pocos, df_loggers, raio=500):
    registros = []

    for _, c in concentracoes.iterrows():
        for _, p in df_pocos.iterrows():
            lat = parse_float(p.get("LATITUDE"))
            lon = parse_float(p.get("LONGITUDE"))
            d = distancia_metros(c["LATITUDE"], c["LONGITUDE"], lat, lon)
            if d is not None and d <= raio:
                registros.append({
                    "Concentração": c["ID_CONCENTRACAO"],
                    "Tipo": "Poço / Ativo",
                    "Identificação": p.get("IDENTIFICACAO_ATIVO", ""),
                    "Nome": p.get("NOME_POCO", ""),
                    "Município": p.get("MUNICIPIO", ""),
                    "Distância (m)": round(d, 1),
                    "Distância": distancia_formatada(d),
                })

        for _, p in df_loggers.iterrows():
            lat = parse_float(p.get("LATITUDE"))
            lon = parse_float(p.get("LONGITUDE"))
            d = distancia_metros(c["LATITUDE"], c["LONGITUDE"], lat, lon)
            if d is not None and d <= raio:
                registros.append({
                    "Concentração": c["ID_CONCENTRACAO"],
                    "Tipo": "Logger",
                    "Identificação": p.get("IDENTIFICACAO_ATIVO", ""),
                    "Nome": p.get("ENDERECO", ""),
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
    fg = folium.FeatureGroup(name="Eventos de abastecimento", show=True)
    for item in eventos_mapeados:
        evento = item["evento"]
        bairro = item["bairro"]
        categoria = item["categoria"]
        parcial = item["parcial"]
        def esc(campo):
            return html_escape(str(evento.get(campo, "") or "—"))
        abrangencia = "Parcial (polígono do bairro inteiro como referência)" if parcial else "Bairro informado como impactado"
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
            f"<b>Descrição:</b> {esc('Descrição do Serviço')}<br>"
            f"<b>Abrangência:</b> {html_escape(abrangencia)}"
            f"</div>"
        )
        for poligono in bairro["poligonos"]:
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

def filtrar_ativos_proximos(concentracoes, df_pocos, df_loggers, raio_m):
    """Retorna ativos dentro do raio de qualquer centro de concentração, sem duplicar."""
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
        selecionados = []
        for _, r in df.iterrows():
            lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
            lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
            if lat is None or lon is None:
                continue
            if any(distancia_metros(lat, lon, clat, clon) <= raio_m for clat, clon in centros):
                selecionados.append(r.name)
        return df.loc[selecionados].copy()

    return filtrar(df_pocos), filtrar(df_loggers)


def criar_mapa(bairros, df_pontos, df_pocos, df_loggers, concentracoes, proximidades, mostrar_bairros=True, eventos_mapeados=None):
    mapa = folium.Map(location=[-5.09, -42.80], zoom_start=12, control_scale=True, tiles="OpenStreetMap")

    if mostrar_bairros:
        fg_bairros = folium.FeatureGroup(name="Bairros", show=True)
        for bairro in bairros:
            for poly in bairro["poligonos"]:
                folium.Polygon(
                    locations=poly,
                    color="#666666",
                    weight=1,
                    fill=False,
                    tooltip=bairro["nome"],
                ).add_to(fg_bairros)
        fg_bairros.add_to(mapa)

    adicionar_camada_eventos(mapa, eventos_mapeados or [])

    fg_os = folium.FeatureGroup(name="O.S.", show=True)
    if not df_pontos.empty:
        for _, r in df_pontos.iterrows():
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
                f"<b>O.S.:</b> {r.get('Nº da O.S','')}<br>"
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

    fg_pocos = folium.FeatureGroup(name="Poços / Ativos", show=True)
    for _, r in df_pocos.iterrows():
        lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if lat is None or lon is None:
            continue
        folium.Marker(
            [lat, lon],
            tooltip=f"Poço / Ativo: {r.get('IDENTIFICACAO_ATIVO','')}",
            popup=folium.Popup(
                f"<b>Poço / Ativo:</b> {r.get('IDENTIFICACAO_ATIVO','')}<br>"
                f"<b>Nome:</b> {r.get('NOME_POCO','')}<br>"
                f"<b>Município:</b> {r.get('MUNICIPIO','')}", max_width=300
            ),
            icon=folium.Icon(icon="tint", prefix="fa", color="blue"),
        ).add_to(fg_pocos)
    fg_pocos.add_to(mapa)

    fg_loggers = folium.FeatureGroup(name="Loggers", show=True)
    for _, r in df_loggers.iterrows():
        lat = normalizar_coordenada(r.get("LATITUDE"), "lat")
        lon = normalizar_coordenada(r.get("LONGITUDE"), "lon")
        if lat is None or lon is None:
            continue
        folium.Marker(
            [lat, lon],
            tooltip=f"Logger: {r.get('IDENTIFICACAO_ATIVO','')}",
            popup=folium.Popup(
                f"<b>Logger:</b> {r.get('IDENTIFICACAO_ATIVO','')}<br>"
                f"<b>Endereço:</b> {r.get('ENDERECO','')}", max_width=300
            ),
            icon=folium.Icon(icon="signal", prefix="fa", color="orange"),
        ).add_to(fg_loggers)
    fg_loggers.add_to(mapa)

    fg_conc = folium.FeatureGroup(name="Concentrações", show=True)
    for _, c in concentracoes.iterrows():
        lat, lon = c["LATITUDE"], c["LONGITUDE"]
        folium.Circle(
            [lat, lon], radius=RAIO_CONCENTRACAO_PADRAO,
            color="purple", fill=True, fill_opacity=0.08,
            popup=folium.Popup(
                f"<b>{c['ID_CONCENTRACAO']}</b><br>"
                f"O.S.: {c['QTD_OS']}<br>"
                f"Matrículas: {c['QTD_MATRICULAS']}<br>"
                f"Bairros: {c['BAIRROS']}", max_width=350
            ),
        ).add_to(fg_conc)
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(html=f"<div style='font-size:12px;font-weight:bold'>{c['ID_CONCENTRACAO']}<br>{c['QTD_OS']} O.S.</div>"),
        ).add_to(fg_conc)
    fg_conc.add_to(mapa)

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
    return carregar_aba(NOME_ABA_POCOS, CABECALHO_POCOS)


def preparar_pocos(df):
    df = df.copy()
    for col in ("LATITUDE", "LONGITUDE"):
        if col in df:
            df[col] = df[col].map(lambda v: normalizar_coordenada(v, "lat" if col == "LATITUDE" else "lon"))
    return df


def invalidar_cache_dados():
    invalidar_cache()


def adicionar_poco(identificacao, nome, municipio, latitude, longitude):
    exigir_edicao_farol()
    atual = carregar_pocos()
    ids = atual["ID_POCO"].astype(str).tolist() if not atual.empty else []
    nums = [int(x[4:]) for x in ids if re.fullmatch(r"POCO\d+", x)]
    id_poco = f"POCO{max(nums, default=0)+1:05d}"
    linha = pd.DataFrame([[id_poco, identificacao, nome, municipio, latitude, longitude]], columns=CABECALHO_POCOS)
    append_dataframe(NOME_ABA_POCOS, CABECALHO_POCOS, linha)
    return id_poco


def atualizar_poco(linha_planilha, id_poco, identificacao, nome, municipio, latitude, longitude):
    exigir_edicao_farol()
    aba = obter_aba(NOME_ABA_POCOS, CABECALHO_POCOS)
    aba.update(range_name=f"A{linha_planilha}:F{linha_planilha}", values=[[id_poco, identificacao, nome, municipio, latitude, longitude]], value_input_option="USER_ENTERED")
    invalidar_cache_dados()


def excluir_poco(linha_planilha):
    exigir_edicao_farol()
    obter_aba(NOME_ABA_POCOS, CABECALHO_POCOS).delete_rows(linha_planilha)
    invalidar_cache_dados()


@st.dialog("➕ Cadastrar novo poço")
def modal_novo_poco():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return

    with st.form(
        "form_novo_poco_modal",
        clear_on_submit=True,
    ):

        identificacao = st.text_input(
            "Identificação do ativo *",
            placeholder="Ex.: PL-API-PCO0001",
        )

        nome = st.text_input(
            "Nome do poço",
            placeholder="Opcional",
        )

        municipio = st.text_input(
            "Município *",
        )

        c1, c2 = st.columns(2)

        with c1:

            latitude = st.text_input(
                "Latitude *",
                placeholder="-5.089200",
            )

        with c2:

            longitude = st.text_input(
                "Longitude *",
                placeholder="-42.801900",
            )

        salvar_poco = st.form_submit_button(
            "Cadastrar poço",
            type="primary",
            width="stretch",
        )

        if salvar_poco:

            lat_n = normalizar_coordenada(
                latitude,
                "lat",
            )

            lon_n = normalizar_coordenada(
                longitude,
                "lon",
            )

            if not identificacao.strip():

                st.error(
                    "A identificação do ativo é obrigatória."
                )

            elif not municipio.strip():

                st.error(
                    "O município é obrigatório."
                )

            elif lat_n is None:

                st.error(
                    "Latitude inválida. Informe um valor entre -90 e 90."
                )

            elif lon_n is None:

                st.error(
                    "Longitude inválida. Informe um valor entre -180 e 180."
                )

            else:

                try:

                    id_criado = adicionar_poco(
                        identificacao=identificacao.strip(),
                        nome=nome.strip(),
                        municipio=municipio.strip(),
                        latitude=lat_n,
                        longitude=lon_n,
                    )

                    st.success(
                        f"Poço cadastrado com ID {id_criado}."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao cadastrar poço: {erro}"
                    )



@st.dialog("✏️ Editar ou excluir poço")
def modal_editar_poco():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return

    df_atual = preparar_pocos(
        carregar_pocos()
    )

    if df_atual.empty:

        st.info(
            "Nenhum poço cadastrado."
        )

        return

    opcoes_edicao = {
        identificacao_exibicao(row): row
        for _, row in df_atual.iterrows()
    }

    selecionado = st.selectbox(
        "Selecione o poço",
        list(opcoes_edicao.keys()),
        key="modal_poco_edicao",
    )

    poco_atual = opcoes_edicao[
        selecionado
    ]

    linha_df = df_atual.index[
        df_atual[
            "ID_POCO"
        ].astype(str)
        == str(
            poco_atual[
                "ID_POCO"
            ]
        )
    ]

    if len(linha_df) > 0:

        indice_df = linha_df[0]

        linha_planilha = indice_df + 2

    else:

        linha_planilha = None

    with st.form(
        "form_edicao_poco_modal"
    ):

        identificacao_edit = st.text_input(
            "Identificação do ativo *",
            value=str(
                poco_atual[
                    "IDENTIFICACAO_ATIVO"
                ]
            ),
        )

        nome_edit = st.text_input(
            "Nome do poço",
            value=str(
                poco_atual[
                    "NOME_POCO"
                ]
            ),
        )

        municipio_edit = st.text_input(
            "Município *",
            value=str(
                poco_atual[
                    "MUNICIPIO"
                ]
            ),
        )

        latitude_atual = normalizar_coordenada(
            poco_atual["LATITUDE"],
            "lat",
        )

        longitude_atual = normalizar_coordenada(
            poco_atual["LONGITUDE"],
            "lon",
        )

        c1, c2 = st.columns(2)

        with c1:

            latitude_edit = st.text_input(
                "Latitude *",
                value=(
                    str(latitude_atual)
                    if latitude_atual is not None
                    else ""
                ),
            )

        with c2:

            longitude_edit = st.text_input(
                "Longitude *",
                value=(
                    str(longitude_atual)
                    if longitude_atual is not None
                    else ""
                ),
            )

        salvar_edicao = st.form_submit_button(
            "💾 Salvar alterações",
            type="primary",
            width="stretch",
        )

        if salvar_edicao:

            lat_n = normalizar_coordenada(
                latitude_edit,
                "lat",
            )

            lon_n = normalizar_coordenada(
                longitude_edit,
                "lon",
            )

            if not identificacao_edit.strip():

                st.error(
                    "A identificação do ativo é obrigatória."
                )

            elif not municipio_edit.strip():

                st.error(
                    "O município é obrigatório."
                )

            elif lat_n is None:

                st.error(
                    "Latitude inválida. Informe um valor entre -90 e 90."
                )

            elif lon_n is None:

                st.error(
                    "Longitude inválida. Informe um valor entre -180 e 180."
                )

            elif linha_planilha is None:

                st.error(
                    "Não foi possível localizar a linha do poço."
                )

            else:

                try:

                    atualizar_poco(
                        linha_planilha=linha_planilha,
                        id_poco=str(
                            poco_atual[
                                "ID_POCO"
                            ]
                        ),
                        identificacao=identificacao_edit.strip(),
                        nome=nome_edit.strip(),
                        municipio=municipio_edit.strip(),
                        latitude=lat_n,
                        longitude=lon_n,
                    )

                    st.success(
                        "Poço atualizado com sucesso."
                    )

                    st.rerun()

                except Exception as erro:

                    st.error(
                        f"Erro ao atualizar poço: {erro}"
                    )

    st.divider()

    confirmar_exclusao = st.checkbox(
        "Confirmo que desejo excluir este poço.",
        key="confirmar_exclusao_poco_modal",
    )

    if st.button(
        "🗑️ Excluir poço",
        type="secondary",
        width="stretch",
        key="btn_excluir_poco_modal",
    ):

        if not confirmar_exclusao:

            st.warning(
                "Marque a confirmação antes de excluir."
            )

        elif linha_planilha is None:

            st.error(
                "Não foi possível localizar a linha do poço."
            )

        else:

            try:

                excluir_poco(
                    linha_planilha
                )

                st.success(
                    "Poço excluído."
                )

                st.rerun()

            except Exception as erro:

                st.error(
                    f"Erro ao excluir poço: {erro}"
                )



@st.dialog("➕ Cadastrar novo logger")
def modal_novo_logger():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return
    with st.form("form_novo_logger_modal", clear_on_submit=True):
        identificacao = st.text_input("Identificação do logger *")
        endereco = st.text_input("Endereço")
        municipio = st.text_input("Município *", value="Teresina")
        c1, c2 = st.columns(2)
        latitude = c1.text_input("Latitude *", placeholder="-5,089200")
        longitude = c2.text_input("Longitude *", placeholder="-42,801900")
        salvar = st.form_submit_button("Cadastrar logger", type="primary", use_container_width=True)

    if salvar:
        lat = normalizar_coordenada(latitude, "lat")
        lon = normalizar_coordenada(longitude, "lon")
        if not identificacao.strip() or not municipio.strip() or lat is None or lon is None:
            st.error("Informe identificação, município e coordenadas válidas.")
        else:
            try:
                novo = pd.DataFrame([{
                    "ID_LOGGER": novo_id("LOGGER"),
                    "IDENTIFICACAO_ATIVO": identificacao.strip(),
                    "ENDERECO": endereco.strip(),
                    "MUNICIPIO": municipio.strip(),
                    "LATITUDE": lat,
                    "LONGITUDE": lon,
                }], columns=CABECALHO_LOGGERS)
                append_dataframe(NOME_ABA_LOGGERS, CABECALHO_LOGGERS, novo)
                st.success("Logger cadastrado com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao cadastrar logger: {erro}")


@st.dialog("✏️ Editar ou excluir logger")
def modal_editar_logger():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return
    dados = carregar_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS)
    if dados.empty:
        st.info("Nenhum logger cadastrado.")
        return

    # Índices originais preservados para identificar a linha real no Google Sheets.
    opcoes = {
        f"{str(r.get('IDENTIFICACAO_ATIVO', ''))} — {str(r.get('ID_LOGGER', ''))} (linha {i + 2})": i
        for i, r in dados.iterrows()
    }
    selecionado = st.selectbox("Selecione o logger", list(opcoes), key="modal_logger_selecionado")
    indice = opcoes[selecionado]
    registro = dados.loc[indice]
    linha_planilha = int(indice) + 2

    with st.form("form_edicao_logger_modal"):
        identificacao = st.text_input("Identificação do logger *", value=str(registro.get("IDENTIFICACAO_ATIVO", "")))
        endereco = st.text_input("Endereço", value=str(registro.get("ENDERECO", "")))
        municipio = st.text_input("Município *", value=str(registro.get("MUNICIPIO", "")))
        c1, c2 = st.columns(2)
        latitude = c1.text_input("Latitude *", value=str(registro.get("LATITUDE", "")))
        longitude = c2.text_input("Longitude *", value=str(registro.get("LONGITUDE", "")))
        salvar = st.form_submit_button("💾 Salvar alterações", type="primary", use_container_width=True)

    if salvar:
        lat = normalizar_coordenada(latitude, "lat")
        lon = normalizar_coordenada(longitude, "lon")
        if not identificacao.strip() or not municipio.strip() or lat is None or lon is None:
            st.error("Informe identificação, município e coordenadas válidas.")
        else:
            try:
                obter_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS).update(
                    range_name=f"A{linha_planilha}:F{linha_planilha}",
                    values=[[
                        str(registro.get("ID_LOGGER", "")), identificacao.strip(), endereco.strip(),
                        municipio.strip(), lat, lon,
                    ]],
                    value_input_option="USER_ENTERED",
                )
                invalidar_cache()
                st.success("Logger atualizado com sucesso.")
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao atualizar logger: {erro}")

    st.divider()
    confirmar = st.checkbox("Confirmo que desejo excluir este logger.", key="confirmar_exclusao_logger_modal")
    if st.button("🗑️ Excluir logger", key="btn_excluir_logger_modal"):
        if not confirmar:
            st.warning("Marque a confirmação antes de excluir.")
        else:
            try:
                obter_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS).delete_rows(linha_planilha)
                invalidar_cache()
                st.success("Logger excluído.")
                st.rerun()
            except Exception as erro:
                st.error(f"Erro ao excluir logger: {erro}")


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
            cidade_evento = normalizar_municipio(evento.get("Cidade", ""))
            if not cidade_evento:
                continue
            bairros_evento = {a["bairro"] for a in extrair_bairros_evento(evento.get("Áreas Impactadas", ""), evento.get("Cidade", ""), bairros_geograficos)}
            intersecao = sorted({bairro for cidade, bairro in pares_grupo if cidade == cidade_evento and bairro in bairros_evento})
            if intersecao:
                item = evento.to_dict()
                item["Bairros coincidentes"] = ", ".join(intersecao)
                eventos_relacionados.append(item)
    return os_grupo, ativos, pd.DataFrame(eventos_relacionados)


def texto_relatorio(valor):
    if valor is None or pd.isna(valor):
        return "—"
    return str(valor).strip() or "—"


def gerar_pdf_concentracao(concentracao, os_grupo, ativos, eventos_relacionados, raio):
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
    cidades = ", ".join(sorted({str(v).strip() for v in os_grupo["Cidade"] if str(v).strip()}))
    resumo = (
        f"Município(s): {cidades or 'Não informado'} | Bairros: {texto_relatorio(concentracao['BAIRROS'])} | "
        f"O.S.: {len(os_grupo)} | Matrículas: {concentracao['QTD_MATRICULAS']} | "
        f"Raio operacional: {raio} m"
    )
    historia.append(p(resumo, normal))
    historia.append(p(f"Centro: {float(concentracao['LATITUDE']):.6f}, {float(concentracao['LONGITUDE']):.6f}", normal))
    historia.append(p("Ordens de serviço da concentração", subtitulo))
    colunas = ["Nº da O.S", "Matrícula", "Cidade", "Bairro", "Status OS", "Dt. Emissão", "Serviço Executado"]
    linhas = [[r.get(c, "") for c in colunas] for _, r in os_grupo.iterrows()]
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
        cols = ["Protocolo", "Status", "Cidade", "Bairros coincidentes", "Serviço", "Descrição do Serviço"]
        historia.append(tabela(cols, [[r.get(c, "") for c in cols] for _, r in eventos_relacionados.iterrows()],
                                [3.1*cm, 2.5*cm, 3.0*cm, 5.0*cm, 4.5*cm, 8.0*cm]))
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
    st.markdown("#### Ordens de serviço")
    colunas_os = ["Nº da O.S", "Matrícula", "Cidade", "Bairro", "Status OS", "Dt. Emissão", "Serviço Executado"]
    st.dataframe(os_grupo.reindex(columns=colunas_os).fillna(""), use_container_width=True, hide_index=True)
    st.markdown("#### Poços / ativos e loggers próximos")
    if ativos.empty:
        st.info("Nenhum equipamento dentro do raio operacional desta concentração.")
    else:
        st.dataframe(ativos[["Tipo", "Identificação", "Nome", "Município", "Distância"]],
                     use_container_width=True, hide_index=True)
    st.markdown("#### Eventos relacionados")
    st.caption("Correspondência por município e bairro impactado; não estabelece relação causal.")
    if eventos_relacionados.empty:
        st.info("Nenhum evento com município e bairro correspondente.")
    else:
        colunas_eventos = ["Protocolo", "Status", "Cidade", "Bairros coincidentes", "Serviço", "Descrição do Serviço"]
        st.dataframe(eventos_relacionados.reindex(columns=colunas_eventos).fillna(""),
                     use_container_width=True, hide_index=True)
    try:
        pdf = gerar_pdf_concentracao(concentracao, os_grupo, ativos, eventos_relacionados, raio)
        st.download_button("📄 Baixar relatório em PDF", data=pdf,
                           file_name=f"Farol_{codigo}_{datetime.now(FUSO_FAROL):%Y%m%d}.pdf",
                           mime="application/pdf", key=f"baixar_pdf_{codigo}")
    except Exception as erro:
        st.error(f"Não foi possível gerar o PDF: {erro}")


@st.dialog("📥 Importação de bases", width="large")
def modal_importacao():
    if not PODE_EDITAR_FAROL:
        st.error("Acesso somente para visualização.")
        return
    st.subheader("Importação das bases")
    st.info("Os dados de O.S. e eventos são usados apenas no dia operacional. Às 00h01 (Teresina), PONTOS e EVENTOS são limpos na primeira execução do aplicativo após esse horário. Poços e loggers são preservados.")

    c1, c2 = st.columns(2)
    with c1:
        arq_os = st.file_uploader("Base diária de O.S.", type=["xlsx", "xls", "csv"], key="upload_os")
        if arq_os is not None:
            try:
                previa = ler_planilha_upload(arq_os)
                st.write(f"**{len(previa):,}** linhas encontradas")
                st.dataframe(previa.head(10), use_container_width=True, hide_index=True)
                if st.button("Importar O.S. para PONTOS", type="primary", key="btn_importar_os"):
                    preparados = preparar_pontos(previa)
                    inseridas, total = upsert_pontos(preparados)
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
                st.dataframe(previa_e.head(10), use_container_width=True, hide_index=True)
                if st.button("Importar eventos para EVENTOS", type="primary", key="btn_importar_eventos"):
                    preparados_e = preparar_eventos(previa_e)
                    processados, total = upsert_eventos(preparados_e)
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
            st.dataframe(rel.sort_values(["O.S. encontradas", "Matrículas"], ascending=False), use_container_width=True, hide_index=True)

            fig = px.bar(
                rel.sort_values("O.S. encontradas", ascending=False),
                x="Bairro",
                y="O.S. encontradas",
                color="Status",
                hover_data=["Protocolo", "Matrículas", "Parcial"],
                title="O.S. encontradas nos bairros impactados pelos eventos",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown("### Eventos armazenados")
        mostrar_eventos = df_eventos.copy()
        colunas_evento = [c for c in ["Data", "Status", "Cidade", "Serviço", "Protocolo", "Áreas Impactadas", "Descrição do Serviço"] if c in mostrar_eventos.columns]
        st.dataframe(mostrar_eventos[colunas_evento], use_container_width=True, hide_index=True)


# ============================================================
# INTERFACE
# ============================================================

st.title("Farol Operacional")
st.caption("O.S. + Eventos + Bairros geográficos + Poços/Ativos + Loggers")

with st.sidebar:
    st.header("Configuração")
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
        "Mínimo de O.S. por concentração", min_value=2, max_value=100,
        value=2, step=1,
    )

    st.divider()
    modo_escuro = st.toggle("🌙 Modo escuro", key="farol_modo_escuro")
    if st.button("🏠 Voltar ao Menu Principal", use_container_width=True):
        try:
            st.switch_page("app.py")
        except Exception as erro:
            st.error(f"Não foi possível voltar ao Hub. Confira o nome do arquivo principal (app.py): {erro}")

if modo_escuro:
    st.markdown("""
    <style>
      .stApp { background-color: #0e1117; color: #fafafa; }
      .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
      .stApp h4, .stApp h5, .stApp h6 { color: #f0f0f0 !important; }
      .stButton > button { background-color: #20252d; color: #fafafa; border-color: #444c56; }
    </style>
    """, unsafe_allow_html=True)

# Carregamento automático de polígonos de todos os municípios disponíveis.
# A ausência de arquivo geográfico é normal e não gera avisos no mapa.
bairros = descobrir_kmz()

# Reset diário persistente, executado antes de ler dados (00:01, horário de Teresina).
# Streamlit não é um agendador: se ninguém acessar o app nesse horário,
# a limpeza ocorre na primeira execução posterior.
try:
    if PODE_EDITAR_FAROL:
        reset_diario_se_necessario()
except Exception as erro:
    st.error(f"Não foi possível verificar/executar o reset diário: {erro}")
    st.stop()  # Evita operar sobre dados de um dia anterior sem reset.

# Inicializa as quatro abas.
with st.spinner("Carregando dados operacionais..."):
    df_pocos = carregar_aba(NOME_ABA_POCOS, CABECALHO_POCOS)
    df_loggers = carregar_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS)
    df_pontos = carregar_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS)
    df_eventos = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)

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
    st.divider()
    st.markdown("### 🧭 Navegação")
    if "farol_tela" not in st.session_state:
        st.session_state["farol_tela"] = "mapa"
    if st.button("🗺️ Mapa operacional", use_container_width=True, type="primary" if st.session_state["farol_tela"] == "mapa" else "secondary"):
        st.session_state["farol_tela"] = "mapa"
        st.rerun()
    if PODE_EDITAR_FAROL:
        if st.button("📥 Importação", use_container_width=True):
            modal_importacao()
    if st.button("⚡ Eventos", use_container_width=True):
        modal_eventos()
    if st.button("📍 Cadastros", use_container_width=True, type="primary" if st.session_state["farol_tela"] == "cadastros" else "secondary"):
        st.session_state["farol_tela"] = "cadastros"
        st.rerun()
    if not PODE_EDITAR_FAROL:
        st.caption("🔒 Perfil Operador: somente visualização e downloads.")
    st.caption("O mapa é a tela inicial do Farol Operacional.")


if st.session_state.get("farol_tela", "mapa") == "mapa":
    eventos_mapeados, eventos_sem_geometria = eventos_georreferenciados(df_eventos, bairros)
    st.subheader("🗺️ Visão geográfica operacional")

    st.caption("Eventos: vermelho = em andamento · amarelo = programado · verde = finalizado · cinza = outro status. "
               "As áreas destacadas representam os bairros inteiros dos arquivos geográficos, inclusive quando o evento informa impacto parcial.")
    modo_ativos = st.radio(
        "Visualização de poços e loggers",
        ["Somente próximos às concentrações", "Todos os cadastrados", "Ocultar poços e loggers"],
        horizontal=True,
        key="farol_modo_ativos",
    )

    if df_pontos.empty:
        st.warning("A aba PONTOS ainda não possui dados.")
        ativos_pocos = df_pocos if modo_ativos == "Todos os cadastrados" else df_pocos.iloc[0:0]
        ativos_loggers = df_loggers if modo_ativos == "Todos os cadastrados" else df_loggers.iloc[0:0]
        mapa = criar_mapa(
            bairros, df_pontos, ativos_pocos, ativos_loggers,
            pd.DataFrame(), pd.DataFrame(), mostrar_bairros=bool(bairros),
            eventos_mapeados=eventos_mapeados,
        )
        st_folium(mapa, width=None, height=650, returned_objects=[])
    else:
        # Filtros.
        f1, f2, f3, f4 = st.columns(4)
        cidades = sorted([x for x in df_pontos["Cidade"].dropna().astype(str).unique() if x.strip()])
        bairros_os = sorted([x for x in df_pontos["Bairro"].dropna().astype(str).unique() if x.strip()])
        status_os = sorted([x for x in df_pontos["Status OS"].dropna().astype(str).unique() if x.strip()])

        with f1:
            cidade_sel = st.selectbox("Cidade", ["Todas"] + cidades)
        with f2:
            bairro_sel = st.multiselect("Bairro", bairros_os)
        with f3:
            status_sel = st.multiselect("Status", status_os)
        with f4:
            apenas_com_coord = st.checkbox("Somente O.S. georreferenciada", value=True)

        servicos_os = sorted({str(x).strip() for x in df_pontos["Serviço Executado"].fillna("")
                              if str(x).strip()})
        servico_sel = st.multiselect(
            "Serviço Executado",
            options=servicos_os,
            placeholder="Todos os serviços",
            help="Selecione um ou mais serviços; sem seleção, todos são exibidos.",
            key="farol_filtro_servico_executado",
        )

        analise = df_pontos.copy()
        if cidade_sel != "Todas":
            analise = analise[normalizar_texto_series(analise["Cidade"]) == normalizar_texto(cidade_sel)]
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

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("O.S. analisadas", len(analise))
        k2.metric("O.S. com coordenada", int(analise[["Latitude", "Longitude"]].notna().all(axis=1).sum()))
        k3.metric("Concentrações", len(concentracoes))
        k4.metric("Pontos operacionais próximos", len(proximidades))

        if modo_ativos == "Todos os cadastrados":
            ativos_pocos, ativos_loggers = df_pocos, df_loggers
        elif modo_ativos == "Ocultar poços e loggers":
            ativos_pocos, ativos_loggers = df_pocos.iloc[0:0], df_loggers.iloc[0:0]
        else:
            ativos_pocos, ativos_loggers = filtrar_ativos_proximos(
                concentracoes, df_pocos, df_loggers, float(raio_operacional)
            )

        st.caption(
            f"Exibindo {len(ativos_pocos)} poço(s)/ativo(s) e "
            f"{len(ativos_loggers)} logger(s) no mapa."
        )
        st.markdown("### 🗺️ Mapa operacional")
        st.caption("🟠 Laranja: Informação de Falta de água (146005) · 🔵 Azul: Reclamação de Falta de água (demais serviços).")
        mapa = criar_mapa(
            bairros, analise, ativos_pocos, ativos_loggers, concentracoes,
            proximidades, mostrar_bairros=bool(bairros),
            eventos_mapeados=eventos_mapeados,
        )
        st_folium(mapa, width=None, height=650, returned_objects=[])

        if concentracoes.empty:
            st.warning("Nenhuma concentração atingiu o mínimo configurado.")
        else:
            st.markdown("### 📋 Análise das Concentrações")
            st.caption("Expanda uma concentração para consultar O.S., equipamentos, eventos relacionados e baixar o PDF.")
            for _, concentracao in concentracoes.iterrows():
                codigo = concentracao["ID_CONCENTRACAO"]
                os_grupo = pontos_cluster[pontos_cluster["_grupo"] == concentracao["GRUPO"]]
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
                titulo = (
                    f"{codigo} — {', '.join(cidades_grupo) or 'Município não informado'} | "
                    f"{int(concentracao['QTD_OS'])} O.S. · "
                    f"{int(concentracao['QTD_MATRICULAS'])} matrículas · "
                    f"{qtd_ativos} ativo(s) próximo(s) · {indicador_eventos}"
                )
                with st.expander(titulo, expanded=False):
                    exibir_relatorio_concentracao(
                        codigo, concentracoes, pontos_cluster, proximidades,
                        df_eventos, int(raio_operacional), bairros
                    )


if st.session_state.get("farol_tela", "mapa") == "cadastros":
    st.subheader("Cadastro de Poços / Ativos e Loggers")

    c_poco, c_logger = st.columns(2)

    with c_poco:
        st.markdown("### Poços / Ativos")
        if PODE_EDITAR_FAROL:
            if st.button("➕ Cadastrar novo poço", key="poco_novo_modal"):
                modal_novo_poco()
            if st.button("✏️ Editar ou excluir poço", key="poco_editar_modal"):
                modal_editar_poco()
        st.dataframe(df_pocos, use_container_width=True, hide_index=True)

    with c_logger:
        st.markdown("### Loggers")
        if PODE_EDITAR_FAROL:
            if st.button("➕ Cadastrar novo logger", key="logger_novo_modal"):
                modal_novo_logger()
            if st.button("✏️ Editar ou excluir logger", key="logger_editar_modal"):
                modal_editar_logger()
        st.dataframe(df_loggers, use_container_width=True, hide_index=True)
