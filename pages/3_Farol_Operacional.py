import io
import json
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

SPREADSHEET_ID = "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU"

NOME_ABA_POCOS = "POCOS"
NOME_ABA_LOGGERS = "LOGGERS"
NOME_ABA_PONTOS = "PONTOS"
NOME_ABA_EVENTOS = "EVENTOS"

ARQUIVO_KMZ_PADRAO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "TERESINA.kmz")
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


def extrair_bairros_evento(valor):
    if not valor:
        return []
    saida = []
    for parte in str(valor).split(","):
        original = parte.strip()
        if not original:
            continue
        parcial = bool(re.search(r"\(\s*PARCIAL\s*\)", original, flags=re.I))
        bairro = limpar_nome_bairro(original)
        if bairro:
            saida.append({
                "bairro": bairro,
                "parcial": parcial,
                "original": original,
            })
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
    return obter_cliente_google().open_by_key(SPREADSHEET_ID)


def obter_aba(nome, cabecalho):
    planilha = obter_planilha()
    try:
        aba = planilha.worksheet(nome)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=nome, rows=1000, cols=max(20, len(cabecalho) + 5))
        aba.update("A1", [cabecalho])
        return aba

    valores = aba.get_all_values()
    if not valores:
        aba.update("A1", [cabecalho])
    elif [normalizar_cabecalho(x) for x in valores[0]] != [normalizar_cabecalho(x) for x in cabecalho]:
        # Não apaga dados existentes. Apenas garante que as colunas mínimas estejam presentes.
        cab_atual = valores[0]
        faltantes = [c for c in cabecalho if normalizar_cabecalho(c) not in {normalizar_cabecalho(x) for x in cab_atual}]
        if faltantes:
            nova_linha = cab_atual + faltantes
            aba.resize(cols=max(aba.col_count, len(nova_linha)))
            aba.update("A1", [nova_linha])
    return aba


@st.cache_data(ttl=60, show_spinner=False)
def carregar_aba(nome, cabecalho):
    aba = obter_aba(nome, cabecalho)
    registros = aba.get_all_records()
    if not registros:
        return pd.DataFrame(columns=cabecalho)
    return pd.DataFrame(registros)


def invalidar_cache():
    carregar_aba.clear()


def garantir_cabecalho_exato(nome, cabecalho):
    aba = obter_aba(nome, cabecalho)
    valores = aba.get_all_values()
    if not valores:
        aba.update("A1", [cabecalho])
    return aba


def append_dataframe(nome, cabecalho, df):
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
    aba = garantir_cabecalho_exato(nome, cabecalho)
    df = df.reindex(columns=cabecalho).fillna("")
    linhas = [cabecalho] + [[limpar_valor(v) for v in row] for row in df.itertuples(index=False, name=None)]
    aba.clear()
    aba.resize(rows=max(1000, len(linhas) + 20), cols=max(len(cabecalho) + 5, 20))
    aba.update("A1", linhas, value_input_option="USER_ENTERED")
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
    out["Latitude"] = out["Latitude"].map(parse_float)
    out["Longitude"] = out["Longitude"].map(parse_float)
    out = out.loc[~out.apply(lambda r: all(not str(x).strip() for x in r), axis=1)].copy()
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
    # Composição estável para impedir duplicações sem depender da posição da linha.
    campos = [
        "Data", "Controlador", "Código do Ativo", "Serviço", "Protocolo",
        "Início", "Prev. Término", "Término Real", "Áreas Impactadas",
        "Descrição do Serviço", "Data de Criação",
    ]
    return "EVT:" + slug_hash(*[row.get(c, "") for c in campos])


def upsert_pontos(df_novo):
    atual = carregar_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS)
    atual = atual.reindex(columns=CABECALHO_PONTOS).fillna("")
    novo = df_novo.reindex(columns=CABECALHO_PONTOS).fillna("")

    if atual.empty:
        final = novo.copy()
    else:
        mapa = {}
        for _, r in atual.iterrows():
            mapa[chave_ponto(r)] = r.to_dict()
        for _, r in novo.iterrows():
            mapa[chave_ponto(r)] = r.to_dict()
        final = pd.DataFrame(list(mapa.values()), columns=CABECALHO_PONTOS)

    # Mantém ordem cronológica aproximada, sem exigir datas válidas.
    if not final.empty:
        final["_ord"] = pd.to_datetime(final["Dt. Emissão"], dayfirst=True, errors="coerce")
        final = final.sort_values("_ord", na_position="last").drop(columns="_ord")
    substituir_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS, final)
    return len(novo), len(final)


def upsert_eventos(df_novo):
    atual = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)
    atual = atual.reindex(columns=CABECALHO_EVENTOS).fillna("")
    novo = df_novo.reindex(columns=CABECALHO_EVENTOS).fillna("")

    mapa = {}
    for _, r in atual.iterrows():
        mapa[chave_evento(r)] = r.to_dict()
    for _, r in novo.iterrows():
        mapa[chave_evento(r)] = r.to_dict()
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
        areas = extrair_bairros_evento(evento.get("Áreas Impactadas", ""))
        for area in areas:
            bloco = pontos[pontos["_bairro_cruzamento"] == area["bairro"]].copy()
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
# MAPA
# ============================================================

def criar_mapa(bairros, df_pontos, df_pocos, df_loggers, concentracoes, proximidades, mostrar_bairros=True):
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

    fg_os = folium.FeatureGroup(name="O.S.", show=True)
    if not df_pontos.empty:
        for _, r in df_pontos.iterrows():
            lat = parse_float(r.get("Latitude"))
            lon = parse_float(r.get("Longitude"))
            if lat is None or lon is None:
                continue
            status = normalizar_texto(r.get("Status OS", ""))
            cor = "red" if "PEND" in status else "green" if "ENCERR" in status or "VISIT" in status else "blue"
            popup = folium.Popup(
                f"<b>O.S.:</b> {r.get('Nº da O.S','')}<br>"
                f"<b>Matrícula:</b> {r.get('Matrícula','')}<br>"
                f"<b>Bairro:</b> {r.get('Bairro','')}<br>"
                f"<b>Status:</b> {r.get('Status OS','')}<br>"
                f"<b>Serviço:</b> {r.get('Serviço Executado','')}",
                max_width=350,
            )
            folium.CircleMarker(
                [lat, lon], radius=4, color=cor, fill=True, fill_opacity=0.75, popup=popup
            ).add_to(fg_os)
    fg_os.add_to(mapa)

    fg_pocos = folium.FeatureGroup(name="Poços / Ativos", show=True)
    for _, r in df_pocos.iterrows():
        lat, lon = parse_float(r.get("LATITUDE")), parse_float(r.get("LONGITUDE"))
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
        lat, lon = parse_float(r.get("LATITUDE")), parse_float(r.get("LONGITUDE"))
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

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def normalizar_texto_series(serie):
    return serie.fillna("").astype(str).map(normalizar_texto)



# ============================================================
# CADASTRO DE POÇOS — OPERAÇÕES PRESERVADAS DO MÓDULO ORIGINAL
# ============================================================
def normalizar_coordenada(valor, tipo="lat"):
    n = parse_float(valor)
    if n is None or n == 0:
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
    atual = carregar_pocos()
    ids = atual["ID_POCO"].astype(str).tolist() if not atual.empty else []
    nums = [int(x[4:]) for x in ids if re.fullmatch(r"POCO\d+", x)]
    id_poco = f"POCO{max(nums, default=0)+1:05d}"
    linha = pd.DataFrame([[id_poco, identificacao, nome, municipio, latitude, longitude]], columns=CABECALHO_POCOS)
    append_dataframe(NOME_ABA_POCOS, CABECALHO_POCOS, linha)
    return id_poco


def atualizar_poco(linha_planilha, id_poco, identificacao, nome, municipio, latitude, longitude):
    aba = obter_aba(NOME_ABA_POCOS, CABECALHO_POCOS)
    aba.update(range_name=f"A{linha_planilha}:F{linha_planilha}", values=[[id_poco, identificacao, nome, municipio, latitude, longitude]], value_input_option="USER_ENTERED")
    invalidar_cache_dados()


def excluir_poco(linha_planilha):
    obter_aba(NOME_ABA_POCOS, CABECALHO_POCOS).delete_rows(linha_planilha)
    invalidar_cache_dados()


@st.dialog("➕ Cadastrar novo poço")
def modal_novo_poco():

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

# Camada geográfica fixa, versionada junto com o projeto no GitHub.
bairros = []
kmz_nome = ARQUIVO_KMZ_PADRAO
try:
    if os.path.isfile(ARQUIVO_KMZ_PADRAO):
        with open(ARQUIVO_KMZ_PADRAO, "rb") as arquivo_kmz:
            bairros = carregar_kmz_bytes(arquivo_kmz.read())
    else:
        st.sidebar.warning("TERESINA.kmz não encontrado na raiz do projeto.")
except Exception as erro:
    st.error(f"Erro ao carregar a camada de bairros: {erro}")

# Inicializa as quatro abas.
with st.spinner("Carregando dados operacionais..."):
    df_pocos = carregar_aba(NOME_ABA_POCOS, CABECALHO_POCOS)
    df_loggers = carregar_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS)
    df_pontos = carregar_aba(NOME_ABA_PONTOS, CABECALHO_PONTOS)
    df_eventos = carregar_aba(NOME_ABA_EVENTOS, CABECALHO_EVENTOS)

# Normaliza tipos para análise.
if not df_pontos.empty:
    df_pontos = df_pontos.reindex(columns=CABECALHO_PONTOS).fillna("")
    df_pontos["Latitude"] = df_pontos["Latitude"].map(parse_float)
    df_pontos["Longitude"] = df_pontos["Longitude"].map(parse_float)

if not df_pocos.empty:
    df_pocos = df_pocos.reindex(columns=CABECALHO_POCOS).fillna("")
if not df_loggers.empty:
    df_loggers = df_loggers.reindex(columns=CABECALHO_LOGGERS).fillna("")

# ============================================================
# ABAS
# ============================================================

aba_importacao, aba_farol, aba_eventos, aba_cadastros = st.tabs([
    "📥 Importação",
    "🚨 Farol O.S.",
    "⚡ Eventos",
    "📍 Cadastros",
])


with aba_importacao:
    st.subheader("Importação das bases")
    st.info("Os dados de O.S. e eventos são acumulados no Google Sheets. O.S. repetida é atualizada; eventos idênticos não são duplicados.")

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


with aba_farol:
    st.subheader("Concentração geográfica de O.S.")

    if df_pontos.empty:
        st.warning("A aba PONTOS ainda não possui dados.")
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

        analise = df_pontos.copy()
        if cidade_sel != "Todas":
            analise = analise[normalizar_texto_series(analise["Cidade"]) == normalizar_texto(cidade_sel)]
        if bairro_sel:
            bairros_norm = {limpar_nome_bairro(x) for x in bairro_sel}
            analise = analise[analise["Bairro"].map(limpar_nome_bairro).isin(bairros_norm)]
        if status_sel:
            status_norm = {normalizar_texto(x) for x in status_sel}
            analise = analise[analise["Status OS"].map(normalizar_texto).isin(status_norm)]
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

        if concentracoes.empty:
            st.warning("Nenhuma concentração atingiu o mínimo configurado.")
        else:
            esquerda, direita = st.columns([1.1, 1.9])
            with esquerda:
                st.markdown("### Ranking das concentrações")
                tabela_c = concentracoes[["ID_CONCENTRACAO", "QTD_OS", "QTD_MATRICULAS", "BAIRROS"]].rename(columns={
                    "ID_CONCENTRACAO": "Concentração",
                    "QTD_OS": "O.S.",
                    "QTD_MATRICULAS": "Matrículas",
                    "BAIRROS": "Bairros",
                })
                st.dataframe(tabela_c, use_container_width=True, hide_index=True)

                if not proximidades.empty:
                    st.markdown("### Poços / Ativos e Loggers próximos")
                    st.dataframe(
                        proximidades.sort_values("Distância (m)")[["Concentração", "Tipo", "Identificação", "Nome", "Distância"]],
                        use_container_width=True,
                        hide_index=True,
                    )

            with direita:
                mapa = criar_mapa(
                    bairros,
                    analise,
                    df_pocos,
                    df_loggers,
                    concentracoes,
                    proximidades,
                    mostrar_bairros=bool(bairros),
                )
                st_folium(mapa, width=None, height=650, returned_objects=[])


with aba_eventos:
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


with aba_cadastros:
    st.subheader("Cadastro de Poços / Ativos e Loggers")

    c_poco, c_logger = st.columns(2)

    with c_poco:
        st.markdown("### Poços / Ativos")
        st.caption("Cadastro original preservado, com edição e exclusão em janelas modais.")
        if st.button("➕ Cadastrar novo poço", key="poco_novo_modal"):
            modal_novo_poco()
        if st.button("✏️ Editar ou excluir poço", key="poco_editar_modal"):
            modal_editar_poco()
        st.dataframe(df_pocos, use_container_width=True, hide_index=True)

    with c_logger:
        st.markdown("### Logger")
        with st.form("form_novo_logger"):
            identificacao = st.text_input("Identificação do logger", key="novo_logger_id")
            endereco = st.text_input("Endereço", key="novo_logger_endereco")
            municipio_l = st.text_input("Município", value="Teresina", key="novo_municipio_logger")
            col1, col2 = st.columns(2)
            lat_l = col1.text_input("Latitude", key="novo_lat_logger")
            lon_l = col2.text_input("Longitude", key="novo_lon_logger")
            salvar_logger = st.form_submit_button("Cadastrar logger", type="primary")

        if salvar_logger:
            if not identificacao.strip() or parse_float(lat_l) is None or parse_float(lon_l) is None:
                st.error("Informe identificação, latitude e longitude válidas.")
            else:
                novo = pd.DataFrame([{
                    "ID_LOGGER": novo_id("LOGGER"),
                    "IDENTIFICACAO_ATIVO": identificacao.strip(),
                    "ENDERECO": endereco.strip(),
                    "MUNICIPIO": municipio_l.strip(),
                    "LATITUDE": parse_float(lat_l),
                    "LONGITUDE": parse_float(lon_l),
                }], columns=CABECALHO_LOGGERS)
                append_dataframe(NOME_ABA_LOGGERS, CABECALHO_LOGGERS, novo)
                st.success("Logger cadastrado.")
                st.rerun()

        st.dataframe(df_loggers, use_container_width=True, hide_index=True)


    st.divider()
    st.markdown("### Gerenciar loggers cadastrados")
    if not df_loggers.empty:
        opcoes = {f"{r['IDENTIFICACAO_ATIVO']} — {r['ID_LOGGER']}": i for i, r in df_loggers.iterrows()}
        escolha = st.selectbox("Selecionar logger para editar ou excluir", list(opcoes), key="logger_edicao")
        i = opcoes[escolha]
        registro = df_loggers.loc[i]
        with st.form("editar_logger"):
            ativo_edit = st.text_input("Identificação", value=str(registro['IDENTIFICACAO_ATIVO']))
            endereco_edit = st.text_input("Endereço", value=str(registro['ENDERECO']))
            municipio_edit = st.text_input("Município", value=str(registro['MUNICIPIO']))
            a, b = st.columns(2)
            lat_edit = a.text_input("Latitude", value=str(registro['LATITUDE']))
            lon_edit = b.text_input("Longitude", value=str(registro['LONGITUDE']))
            salvar = st.form_submit_button("💾 Salvar alterações")
        if salvar:
            lat_ok = normalizar_coordenada(lat_edit, 'lat')
            lon_ok = normalizar_coordenada(lon_edit, 'lon')
            if not ativo_edit.strip() or lat_ok is None or lon_ok is None:
                st.error("Informe identificação e coordenadas válidas.")
            else:
                obter_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS).update(
                    range_name=f"A{i+2}:F{i+2}",
                    values=[[str(registro['ID_LOGGER']), ativo_edit, endereco_edit, municipio_edit, lat_ok, lon_ok]],
                    value_input_option="USER_ENTERED")
                invalidar_cache()
                st.rerun()
        if st.checkbox("Confirmo a exclusão deste logger", key="confirmar_excluir_logger"):
            if st.button("🗑️ Excluir logger", key="excluir_logger"):
                obter_aba(NOME_ABA_LOGGERS, CABECALHO_LOGGERS).delete_rows(int(i)+2)
                invalidar_cache()
                st.rerun()
