"""Módulo 7 — Relatório Farol acrescido de medições do Módulo 1.
Fontes independentes e acesso somente leitura.
"""
import io
import json
import math
import re
import os
import shutil
import tempfile
from pathlib import Path
import unicodedata
from datetime import date, datetime, timedelta
from html import escape
from xml.sax.saxutils import escape as xml_escape

import folium
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image, PageBreak
from reportlab.graphics.shapes import Drawing, Circle, String, Rect
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from streamlit_folium import st_folium
from auth import verificar_autenticacao, tem_acesso_modulo

st.set_page_config(page_title="Relatórios Integrados — COI", page_icon="📊", layout="wide")
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Entre pelo Hub Central.")
    st.stop()
if str(st.session_state.get("perfil", "")).lower().strip() not in {"admin", "usuario", "operador"}:
    st.error("Acesso não autorizado.")
    st.stop()
# Quando o Hub cadastrar uma permissão explícita para o módulo 7, respeitá-la.
# Não exigir a permissão antes da configuração no Hub para não bloquear a implantação inicial.

ID_PRESSAO = str(st.secrets.get("modulo_1_spreadsheet_id", "15iN3YEGyxk3l1ZKaHJJp-BvTfVHqpd7gL1GX3RbAKUU")).strip()
ID_FAROL = str(st.secrets.get("farol_producao_spreadsheet_id", "")).strip()
if not ID_FAROL or ID_FAROL == ID_PRESSAO:
    st.error("Configure farol_producao_spreadsheet_id; as fontes devem ser independentes.")
    st.stop()

@st.cache_resource(show_spinner=False)
def cliente_google():
    conf = st.secrets["gcp_json"]
    if isinstance(conf, str):
        conf = json.loads(conf)
    else:
        conf = dict(conf)
    credentials = Credentials.from_service_account_info(
        conf, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=120, show_spinner=False)
def ler_base(spreadsheet_id, aba):
    """Uma consulta de valores por fonte, cacheada entre sessões para aliviar quota 429."""
    valores = cliente_google().open_by_key(spreadsheet_id).worksheet(aba).get_all_values()
    if not valores:
        return pd.DataFrame()
    cabe = [str(c).strip() for c in valores[0]]
    return pd.DataFrame([linha[:len(cabe)] + [""] * max(0, len(cabe)-len(linha))
                         for linha in valores[1:] if any(str(v).strip() for v in linha)], columns=cabe)

def normalizar(v):
    t = unicodedata.normalize("NFKD", str(v or "").upper().strip())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())

def unidade_da_cidade_farol(valor):
    """Mesma classificação do Módulo 3: THE, API e TIM não se misturam."""
    cidade = re.sub(r"[^A-Z0-9]", "", normalizar(valor))
    if cidade == "TERESINA":
        return "THE"
    if cidade in {"TIMON", "TIMONMA", "TIMONMARANHAO"}:
        return "TIM"
    return "API"

def flutuante(valor):
    texto = str("" if valor is None else valor).strip().replace(" ", "")
    if not texto or texto.lower() in {"nan", "none", "nat", "-"}:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".") if texto.rfind(",") > texto.rfind(".") else texto.replace(",", "")
    else:
        texto = texto.replace(",", ".")
    try:
        numero = float(texto)
        return numero if math.isfinite(numero) else None
    except ValueError:
        return None

def coordenada(v, tipo):
    num = flutuante(v)
    if num is None or num == 0 or not ( (-90 <= num <= 90) if tipo == "lat" else (-180 <= num <= 180)):
        return None
    return num

def haversine(lat1, lon1, lat2, lon2):
    la1, la2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 12742000 * math.asin(min(1, math.sqrt(a)))

def data_parse(v):
    """Datas do Farol e do M1: dia/mês/ano, ISO, hora opcional e serial Sheets.

    Zero, vazio ou valores não interpretáveis não são convertidos em data fictícia.
    """
    if v is None or (not isinstance(v, (list, tuple, dict)) and pd.isna(v)):
        return pd.NaT
    if isinstance(v, (pd.Timestamp, datetime, date)):
        try:
            return pd.Timestamp(v)
        except (TypeError, ValueError):
            return pd.NaT
    texto = str(v).strip()
    if not texto or texto.lower() in {"nan", "nat", "none", "-"}:
        return pd.NaT
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%d/%m/%y %H:%M", "%d/%m/%y", "%d-%m-%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d"):
        try:
            return pd.Timestamp(datetime.strptime(texto, fmt))
        except ValueError:
            pass
    # Datas seriadas podem ter vindo de exportações não formatadas.
    try:
        n = float(texto.replace(",", "."))
        if 20000 <= n <= 90000:
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(n, unit="D")
    except (ValueError, TypeError, OverflowError):
        pass
    try:
        return pd.to_datetime(texto, dayfirst=True, errors="coerce")
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def preparar_os(df):
    nomes = ["Nº da O.S", "Matrícula", "Cidade", "Bairro", "Latitude", "Longitude", "Dt. Emissão"]
    faltantes = [c for c in nomes if c not in df.columns]
    if faltantes:
        raise ValueError("Aba PONTOS — colunas ausentes: " + ", ".join(faltantes))
    df = df.copy()
    df["_municipio"] = df["Cidade"].map(normalizar)
    df["_bairro"] = df["Bairro"].map(normalizar)
    df["_lat"] = df["Latitude"].map(lambda v: coordenada(v, "lat"))
    df["_lon"] = df["Longitude"].map(lambda v: coordenada(v, "lon"))
    df["_data"] = df["Dt. Emissão"].map(data_parse)
    return df

def preparar_pressao(df):
    colunas = ["ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude", "Pressao_MCA", "Observacao", "Matricula"]
    faltantes = [c for c in colunas if c not in df.columns]
    if faltantes:
        raise ValueError("Aba baixa_pressao — colunas ausentes: " + ", ".join(faltantes))
    df = df.copy()
    df["_municipio"] = df["Municipio"].map(normalizar)
    df["_bairro"] = df["Bairro"].map(normalizar)
    df["_lat"] = df["Latitude"].map(lambda v: coordenada(v, "lat"))
    df["_lon"] = df["Longitude"].map(lambda v: coordenada(v, "lon"))
    df["_data"] = df["Data"].map(data_parse)
    df["_pressao"] = df["Pressao_MCA"].map(flutuante)
    df["_faixa"] = df["_pressao"].map(faixa_pressao)
    df["_id_medicao"] = [f"BP_{i}" for i in range(len(df))]
    return df

def faixa_pressao(p):
    if p is None or pd.isna(p): return "Sem dado válido"
    if p == 0: return "Sem pressão (0 mca)"
    if 0 < p <= 5: return "Baixa pressão (0–5 mca)"
    if 5 < p <= 10: return "Em atenção (5–10 mca)"
    if 10 < p <= 15: return "Faixa oculta no mapa M1 (10–15 mca)"
    if p > 15: return "Acima de 15 mca"
    return "Dado inválido"

def concentracoes_farol(df, raio_m, minimo):
    """Replica o agrupamento do Farol atual: grade + union-find por unidade.

    O.S. de municípios distintos podem compor o mesmo grupo na API, mas
    THE, API e TIM jamais formam uma concentração única.
    """
    df = df.dropna(subset=["_lat", "_lon"]).reset_index(drop=True).copy()
    if df.empty:
        return pd.DataFrame(), df
    df["_unidade"] = df["Cidade"].map(unidade_da_cidade_farol)
    unidades = df["_unidade"].tolist()
    lat_step = raio_m / 111320.0
    lon_step = raio_m / (111320.0 * max(0.2, math.cos(math.radians(float(df["_lat"].mean())))))
    buckets = {}
    for i, r in df.iterrows():
        celula = (int(math.floor(r["_lat"] / lat_step)), int(math.floor(r["_lon"] / lon_step)))
        buckets.setdefault(celula, []).append(i)
    parent = list(range(len(df)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for (x, y), indices in buckets.items():
        candidatos = [j for dx in (-1,0,1) for dy in (-1,0,1)
                      for j in buckets.get((x+dx,y+dy), [])]
        for i in indices:
            for j in candidatos:
                if j <= i or unidades[i] != unidades[j]:
                    continue
                if haversine(df.at[i,"_lat"],df.at[i,"_lon"],
                             df.at[j,"_lat"],df.at[j,"_lon"]) <= raio_m:
                    union(i,j)
    df["_grupo"] = [find(i) for i in range(len(df))]
    validos = df.groupby("_grupo").size()
    df = df[df["_grupo"].isin(validos[validos >= minimo].index)].copy()
    saida = []
    for grupo, bloco in df.groupby("_grupo"):
        cidades = sorted(set(bloco["_municipio"]) - {""})
        pares = sorted({(str(r["_municipio"]), str(r["_bairro"]))
                        for _,r in bloco.iterrows() if r["_municipio"] and r["_bairro"]})
        saida.append({"_grupo":grupo, "Latitude":float(bloco["_lat"].mean()),
                      "Longitude":float(bloco["_lon"].mean()), "O.S.":len(bloco),
                      "Matrículas":bloco["Matrícula"].replace("",pd.NA).dropna().nunique(),
                      "Município":", ".join(cidades),
                      "Bairros":", ".join(sorted(set(bloco["_bairro"]) - {""})),
                      "_unidade":str(bloco["_unidade"].iloc[0]),
                      "_pares_bairro":pares})
    cdf = pd.DataFrame(saida)
    if cdf.empty:
        return cdf,df
    cdf = cdf.sort_values(["O.S.","Matrículas"],ascending=False).reset_index(drop=True)
    contador={"THE":0,"API":0,"TIM":0}
    ids=[]
    for _,c in cdf.iterrows():
        tipo=c["_unidade"]
        contador[tipo]+=1
        ids.append(f"{tipo} C{contador[tipo]:03d}")
    cdf.insert(0,"Concentração",ids)
    return cdf,df


def relacionar(concs, os_cluster, pressao, raio, inicio, fim):
    """Cruza pontos no MESMO município: proximidade com qualquer O.S. do grupo.

    Critérios mutuamente exclusivos: geográfico, apenas bairro, sem evidência.
    Medições são eventos pontuais, não atestam toda a área ou causa das O.S.
    """
    resultados, geograficos, apenas_bairro = [], [], []
    pressao = pressao[pressao["_data"].dt.date.between(inicio, fim)].copy()
    for _, c in concs.iterrows():
        grupo = os_cluster[os_cluster["_grupo"] == c["_grupo"]].copy()
        municipios = set(grupo["_municipio"]) - {""}
        pares_bairro = set(c.get("_pares_bairro", []))
        cand = pressao[pressao["_municipio"].isin(municipios)].copy()
        geo_rows, bairro_rows = [], []
        for _, med in cand.iterrows():
            tem_coords = pd.notna(med["_lat"]) and pd.notna(med["_lon"])
            os_mesma_cidade = grupo[grupo["_municipio"] == med["_municipio"]]
            pontos = list(zip(os_mesma_cidade["_lat"], os_mesma_cidade["_lon"]))
            distancia = min((haversine(float(lat),float(lon),float(med["_lat"]),float(med["_lon"]))
                             for lat,lon in pontos), default=float("inf")) if tem_coords else float("inf")
            reg = med.to_dict()
            reg["Concentração"] = c["Concentração"]
            reg["Distância até O.S. (m)"] = round(distancia) if math.isfinite(distancia) else None
            reg["Critério de associação"] = "Proximidade geográfica" if distancia <= raio else "Bairro coincidente (sem proximidade confirmada)"
            if distancia <= raio:
                geo_rows.append(reg)
            elif (med["_municipio"], med["_bairro"]) in pares_bairro:
                bairro_rows.append(reg)
        geos = pd.DataFrame(geo_rows)
        territorial = pd.DataFrame(bairro_rows)
        # A mesma medição não é contada duas vezes dentro de uma concentração.
        n_geo, n_bairro = len(geos), len(territorial)
        avaliados = geos if n_geo else territorial
        valores = pd.to_numeric(avaliados["_pressao"],errors="coerce").dropna() if not avaliados.empty else pd.Series(dtype=float)
        criticos = int((valores <= 5).sum())
        atencao = int(((valores > 5)&(valores <= 10)).sum())
        ocultos = int(((valores > 10)&(valores <= 15)).sum())
        zeros = int((valores == 0).sum())
        if n_geo:
            situacao = ("PRESSÃO CRÍTICA PRÓXIMA" if criticos else "PRESSÃO EM ATENÇÃO PRÓXIMA" if atencao else "MEDIÇÃO PRÓXIMA SEM PRESSÃO CRÍTICA")
            leitura = (f"{n_geo} medição(ões) a até {raio} m de alguma O.S. do grupo; "
                       + (f"{criticos} até 5 mca." if criticos else "nenhuma até 5 mca."))
        elif n_bairro:
            situacao = "INDÍCIO NO MESMO BAIRRO"
            leitura = (f"{n_bairro} medição(ões) no(s) mesmo(s) bairro(s), mas fora do raio de {raio} m "
                       "ou sem coordenadas válidas. Não equivalem a confirmação no local da O.S.")
        else:
            situacao = ""
            leitura = ""
        resultados.append({**c.to_dict(),
            "Medições próximas": n_geo,
            "Medições mesmo bairro": n_bairro,
            "Sem/baixa pressão": criticos,
            "Medições 0 mca": zeros,
            "Em atenção (5–10)": atencao,
            "Faixa 10–15 (oculta no M1)": ocultos,
            "Menor pressão (mca)": float(valores.min()) if len(valores) else None,
            "Classificação indicativa": situacao,
            "Análise operacional": leitura,
            "O.S. do grupo": ", ".join(sorted(set(grupo["Nº da O.S"].astype(str))))})
        geograficos.extend(geo_rows)
        apenas_bairro.extend(bairro_rows)
    return pd.DataFrame(resultados),pd.DataFrame(geograficos),pd.DataFrame(apenas_bairro)


def diagnostico_geral(resumo, pressao, associados, territorial, inicio, fim):
    """Produz achados rastreáveis sem inferir causalidade nem normalidade de pressão."""
    if resumo.empty:
        return ["Nenhuma concentração encontrada com os filtros atuais."],pd.DataFrame()
    geo = resumo[resumo["Medições próximas"] > 0]
    bairro = resumo[(resumo["Medições próximas"] == 0) & (resumo["Medições mesmo bairro"] > 0)]
    lacunas = resumo[(resumo["Medições próximas"] == 0) & (resumo["Medições mesmo bairro"] == 0)]
    achados = [f"{len(resumo)} concentração(ões) de O.S. identificada(s) no período."]
    if len(geo) or len(bairro):
        achados.append(f"{len(geo)} concentração(ões) com medição próxima de alguma O.S.; {len(bairro)} com medição no mesmo bairro, fora do raio confirmado.")
    if len(geo):
        crit = geo[geo["Sem/baixa pressão"]>0]
        if len(crit):
            achados.append(f"{len(crit)} concentração(ões) têm medição de 0 a 5 mca próxima de pelo menos uma O.S.: " + ", ".join(crit["Concentração"].astype(str)) + ". Priorizar verificação operacional.")
        else:
            achados.append("Há medições próximas a O.S., mas nenhuma delas registrou de 0 a 5 mca no período.")
    if len(bairro):
        achados.append("Correspondências apenas por bairro NÃO são prova de que a baixa pressão ocorreu no endereço da reclamação; confirmar localização e janela de medição.")
    # Diagnóstico de cobertura: bairros com medição crítica e nenhuma concentração no mesmo bairro.
    bp = pressao[pressao["_data"].dt.date.between(inicio,fim)].copy()
    bp = bp[bp["_pressao"].notna() & (bp["_pressao"]<=5)]
    municipios_bairros = set()
    for _,r in resumo.iterrows():
        for municipio,bairro in r.get("_pares_bairro", []):
            municipios_bairros.add((municipio,bairro))
    isolados = bp[bp.apply(lambda r:(r["_municipio"],r["_bairro"]) not in municipios_bairros,axis=1)].copy()
    if not isolados.empty:
        locais = sorted({f"{r['_bairro']} ({r['_municipio']})" for _,r in isolados.iterrows() if r['_bairro']})
        achados.append(f"Há {len(isolados)} medição(ões) de até 5 mca em bairro(s) sem concentração identificada pelos critérios atuais" + (": " + ", ".join(locais[:6]) if locais else "") + ".")
    return achados,isolados

def resumo_pressao_por_bairro(pressao):
    """Consolida TODO o Módulo 1 filtrado, com ou sem concentração relacionada.

    Respeita as faixas visuais M1; 10–15 mca ficam na tabela, fora do mapa.
    """
    colunas = ["Município", "Bairro", "Medições", "0 mca", "Até 5 mca",
               "5–10 mca", "10–15 mca", ">15 mca", "Mín. (mca)"]
    if pressao is None or pressao.empty:
        return pd.DataFrame(columns=colunas)
    base = pressao[pressao["_pressao"].notna()].copy()
    if base.empty:
        return pd.DataFrame(columns=colunas)
    linhas=[]
    for (municipio, bairro), grupo in base.groupby(["_municipio","_bairro"], dropna=False):
        p=pd.to_numeric(grupo["_pressao"], errors="coerce").dropna()
        if p.empty:
            continue
        linhas.append({
            "Município": str(municipio or "Não informado"),
            "Bairro": str(bairro or "Não informado"),
            "Medições": int(len(p)),
            "0 mca": int((p == 0).sum()),
            "Até 5 mca": int(((p >= 0) & (p <= 5)).sum()),
            "5–10 mca": int(((p > 5) & (p <= 10)).sum()),
            "10–15 mca": int(((p > 10) & (p <= 15)).sum()),
            ">15 mca": int((p > 15).sum()),
            "Mín. (mca)": round(float(p.min()), 2),
        })
    if not linhas:
        return pd.DataFrame(columns=colunas)
    return (pd.DataFrame(linhas,columns=colunas)
            .sort_values(["Até 5 mca","Medições","Município","Bairro"],
                         ascending=[False,False,True,True]).reset_index(drop=True))


def diagnostico_pressao_independente(pressao, resumo_bairros, associados, territoriais):
    """Diagnóstico apoiado em todas as leituras, não apenas nas ligadas a O.S."""
    if pressao is None or pressao.empty:
        return []
    total = len(pressao)
    p = pd.to_numeric(pressao["_pressao"], errors="coerce").dropna()
    if p.empty:
        return []
    n_zero = int((p == 0).sum())
    n_baixa = int(((p > 0) & (p <= 5)).sum())
    n_atencao = int(((p > 5) & (p <= 10)).sum())
    n_oculta = int(((p > 10) & (p <= 15)).sum())
    n_alta = int((p > 15).sum())
    achados = [
        f"O Módulo 1 registrou {total} medição(ões) no período e unidade selecionados, "
        f"em {len(resumo_bairros)} bairro(s), independentemente das concentrações do Farol.",
        f"Distribuição: {n_zero} com 0 mca; {n_baixa} acima de 0 até 5 mca; "
        f"{n_atencao} acima de 5 até 10 mca; {n_oculta} acima de 10 até 15 mca "
        f"(faixa que não aparece no mapa); {n_alta} acima de 15 mca.",
    ]
    criticos=resumo_bairros[resumo_bairros["Até 5 mca"]>0]
    if not criticos.empty:
        nomes=[f"{r['Bairro']} ({r['Município']})" for _,r in criticos.head(5).iterrows()]
        achados.append("Prioridade de verificação da pressão (0–5 mca): "
                       + ", ".join(nomes) + ". A medição é pontual e não estabelece a causa.")
    relacionadas=set()
    for tabela in (associados, territoriais):
        if tabela is not None and not tabela.empty and "_id_medicao" in tabela:
            relacionadas.update(tabela["_id_medicao"].astype(str))
    q_sem_relacao = int((~pressao["_id_medicao"].astype(str).isin(relacionadas)).sum())
    if q_sem_relacao:
        achados.append(f"{q_sem_relacao} medição(ões) não estão vinculadas a nenhuma "
                       "concentração pela proximidade ou coincidência de bairro; continuam "
                       "representadas no panorama de pressão.")
    return achados


def mapa_integrado(concs, associados, raio):
    if concs.empty: return None
    mapa=folium.Map(location=[float(concs["Latitude"].mean()),float(concs["Longitude"].mean())],zoom_start=12,tiles="OpenStreetMap")
    for _,c in concs.iterrows():
        folium.Circle(location=[c["Latitude"],c["Longitude"]],radius=raio,color="#154c78",weight=2,fill=True,fill_opacity=.08).add_to(mapa)
        folium.Marker(location=[c["Latitude"],c["Longitude"]],tooltip=f"{c['Concentração']} — {c['O.S.']} O.S.",
            popup=folium.Popup(escape(str(c["Bairros"])),max_width=280),icon=folium.Icon(color="blue",icon="info-sign")).add_to(mapa)
    for _,r in associados.iterrows():
        # Espelha a regra visual do Módulo 1: pontos entre 10 e 15 mca não aparecem.
        if pd.notna(r["_pressao"]) and 10 < r["_pressao"] <= 15:
            continue
        cor=("#dc3545" if r["_pressao"] is not None and pd.notna(r["_pressao"]) and r["_pressao"]<=5 else
             "#ffbd22" if r["_pressao"] is not None and pd.notna(r["_pressao"]) and r["_pressao"]<=10 else
             "#989898")
        folium.CircleMarker(location=[r["_lat"],r["_lon"]],radius=5,color=cor,fill=True,fill_opacity=.9,
            tooltip=f"{r['Concentração']} · {r['_pressao']} mca · {r['Data']}").add_to(mapa)
    return mapa

def imagem_folium(mapa, largura=1100, altura=650):
    """Captura cartografia real como o Farol; não substitui o mapa por gráfico fictício."""
    from playwright.sync_api import sync_playwright
    html = mapa.get_root().render().replace('</head>',
        f'<style>html,body{{margin:0;width:{largura}px;height:{altura}px;overflow:hidden}}'
        f'.folium-map{{width:{largura}px !important;height:{altura}px !important}}</style></head>',1)
    with tempfile.TemporaryDirectory(prefix="relatorio_coi_") as diretorio:
        caminho = Path(diretorio)/"mapa.html"
        caminho.write_text(html,encoding="utf-8")
        with sync_playwright() as playwright:
            exe=(os.environ.get("CHROMIUM_PATH") or shutil.which("chromium")
                 or shutil.which("chromium-browser") or shutil.which("google-chrome"))
            opcoes={"headless":True,"args":["--no-sandbox","--disable-dev-shm-usage"]}
            if exe: opcoes["executable_path"]=exe
            browser=playwright.chromium.launch(**opcoes)
            try:
                pg=browser.new_page(viewport={"width":largura,"height":altura},device_scale_factor=1.2)
                pg.goto(caminho.as_uri(),wait_until="load",timeout=45000)
                pg.wait_for_function("typeof L !== 'undefined' && document.querySelector('.leaflet-map-pane') !== null",timeout=30000)
                pg.wait_for_timeout(2200)
                if pg.locator('.leaflet-tile-loaded').count()==0:
                    raise RuntimeError("O mapa-base não carregou. Verifique a rede do Chromium.")
                return pg.locator('.folium-map').first.screenshot(type="png")
            finally: browser.close()


def mapa_ficha(c, grupo, proximas, raio):
    centro=[float(c["Latitude"]),float(c["Longitude"])]
    mapa=folium.Map(location=centro,zoom_start=14,tiles="OpenStreetMap",control_scale=True)
    folium.Circle(location=centro,radius=raio,color="#164d85",fill=True,fill_opacity=.05).add_to(mapa)
    coords=[]
    for _,os_row in grupo.iterrows():
        lat,lon=os_row.get("_lat"),os_row.get("_lon")
        if pd.notna(lat) and pd.notna(lon):
            coords.append([float(lat),float(lon)])
            folium.CircleMarker([lat,lon],radius=5,color="#b51d35",fill=True,fill_opacity=.85,
                tooltip="O.S.: "+str(os_row.get("Nº da O.S",""))).add_to(mapa)
    for _,med in proximas.iterrows():
        press=med.get("_pressao")
        if pd.isna(press) or (10<float(press)<=15):continue
        lat,lon=med.get("_lat"),med.get("_lon")
        if pd.isna(lat) or pd.isna(lon):continue
        coords.append([float(lat),float(lon)])
        cor="#d21d47" if press<=5 else "#e5b700" if press<=10 else "#8024d6"
        folium.CircleMarker([lat,lon],radius=7,color=cor,weight=2,fill=True,fill_opacity=.85,
           tooltip=f"Pressão {press:g} mca · {med.get('Bairro','')}").add_to(mapa)
    if coords:
        if len(coords)>1: mapa.fit_bounds(coords,padding=(55,55))
    return mapa


# ============================================================
# RELATÓRIO NO PADRÃO FAROL — CONTEÚDO ORIGINAL + PRESSÃO
# ============================================================
@st.cache_data(ttl=120, show_spinner=False)
def carregar_contexto_farol():
    """Respeita fontes do Farol: EVENTOS no Sheets; poços e loggers nos CSV do GitHub.

    Outras abas de acompanhamento são lidas em lote. O relatório é somente leitura.
    """
    def opcional(identificador, aba):
        try:
            return ler_base(identificador, aba)
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()

    contexto = {"EVENTOS": opcional(ID_FAROL, "EVENTOS")}
    raiz = Path(__file__).resolve().parent.parent
    for aba, nome_arquivo in (("POCOS", "pocos.csv"), ("LOGGERS", "loggers.csv")):
        caminho = raiz / "dados" / nome_arquivo
        if caminho.is_file():
            try:
                contexto[aba] = pd.read_csv(caminho, dtype=str, keep_default_na=False,
                                            encoding="utf-8-sig", sep=None, engine="python")
            except Exception as erro:
                raise ValueError(f"Não foi possível ler dados/{nome_arquivo}: {erro}") from erro
        else:
            # Compatibilidade com instalações nas quais o cadastro ainda está no Sheets.
            contexto[aba] = opcional(ID_FAROL, aba)
    contexto.update({"vinculos_farol_producao": pd.DataFrame(),
                      "eventos_acomp": pd.DataFrame(), "movimentacoes": pd.DataFrame()})
    id_acomp = str(st.secrets.get("acompanhamento_operacional_spreadsheet_id", "")).strip()
    if id_acomp and id_acomp != ID_FAROL:
        for aba in ("vinculos_farol_producao", "eventos", "movimentacoes"):
            destino = "eventos_acomp" if aba == "eventos" else aba
            contexto[destino] = opcional(id_acomp, aba)
    return contexto


def pressao_visivel(m):
    v = m.get("_pressao")
    return pd.notna(v) and not (10 < float(v) <= 15)


def adicionar_pontos_pressao(mapa, pressao, pontos_limiter=None):
    """Pontos medidos sobrepostos às concentrações, mesmo sem relação direta com O.S.

    Apenas 10 < pressão <= 15 fica oculto, conforme a regra do Módulo 1.
    """
    if pressao is None or pressao.empty:
        return []
    camada = folium.FeatureGroup(name="Medições de pressão (Módulo 1)", show=True)
    posicoes = []
    for _, med in pressao.iterrows():
        lat, lon = med.get("_lat"), med.get("_lon")
        if pd.isna(lat) or pd.isna(lon) or not pressao_visivel(med):
            continue
        lat, lon = float(lat), float(lon)
        valor = float(med["_pressao"])
        cor = "#f04452" if valor <= 5 else "#f2c600" if valor <= 10 else "#8b27ef"
        popup = (f"<b>{escape(str(med.get('Bairro', '')))}</b><br>"
                 f"Pressão aferida: <b>{valor:g} mca</b><br>"
                 f"Data: {escape(str(med.get('Data','')))}<br>"
                 f"Matrícula: {escape(str(med.get('Matricula','')))}<br>"
                 f"Observação: {escape(str(med.get('Observacao','')))}")
        folium.CircleMarker([lat,lon],radius=7,color="#ffffff",weight=1.6,
            fill=True,fill_color=cor,fill_opacity=.98,
            tooltip=f"Pressão {valor:g} mca — {med.get('Bairro','')}",
            popup=folium.Popup(popup,max_width=350)).add_to(camada)
        posicoes.append([lat,lon])
    if posicoes:
        camada.add_to(mapa)
    return posicoes


def marcador_concentracao(c):
    """Alvo roxo do Farol, distinto dos pontos de aferição do Módulo 1."""
    nome=escape(str(c.get("Concentração", "")))
    icon=folium.DivIcon(icon_size=(26,26),icon_anchor=(13,13),html=(
        '<div style="width:24px;height:24px;border:4px solid #8a24bf;'
        'background:#ffffff;border-radius:50%;box-shadow:0 1px 5px #0006;'
        'box-sizing:border-box;display:flex;align-items:center;justify-content:center;">'
        '<div style="width:7px;height:7px;background:#8a24bf;border-radius:50%"></div>'
        '</div>'))
    return folium.Marker([float(c["Latitude"]),float(c["Longitude"])],
            icon=icon,tooltip=f"{nome} — {int(c['O.S.'])} O.S.")


def adicionar_legenda_integrada(mapa, tem_pressao):
    itens='<span style="color:#8729ad">●</span> Concentrações&nbsp;&nbsp; <span style="color:#1877d2">●</span> O.S.'
    if tem_pressao:
        itens+='&nbsp;&nbsp; <span style="color:#f04452">●</span> 0–5 mca&nbsp;&nbsp; <span style="color:#d0a700">●</span> 5–10 mca&nbsp;&nbsp; <span style="color:#8b27ef">●</span> &gt;15 mca'
    from branca.element import Element
    mapa.get_root().html.add_child(Element(
        '<div style="position:fixed;bottom:12px;left:12px;z-index:9999;'
        'background:rgba(255,255,255,.96);border:1px solid #bdc9d4;'
        'padding:6px 9px;border-radius:5px;font:11px Arial;color:#22354a">'
        +itens+'</div>'))


def adicionar_ativos_eventos_mapa(mapa, contexto, municipio=None, centros=None, raio=500, rotulos=False):
    """Usa os CSV de poços/loggers do Farol; limita os equipamentos aos centros."""
    for tipo, icone in (("POCOS", "tint"), ("LOGGERS", "signal")):
        base = contexto.get(tipo, pd.DataFrame())
        if base is None or base.empty:
            continue
        camada = folium.FeatureGroup(name="Ativos — " + ("Poços" if tipo=="POCOS" else "Loggers"), show=True)
        for _, item in base.iterrows():
            mun = normalizar(item.get("MUNICIPIO",item.get("Município","")))
            if municipio and mun and mun != normalizar(municipio):
                continue
            lat=coordenada(item.get("LATITUDE"),"lat")
            lon=coordenada(item.get("LONGITUDE"),"lon")
            if lat is None or lon is None:
                continue
            if centros and not any(haversine(lat,lon,y,x)<=raio for y,x in centros):
                continue
            nome=str(item.get("IDENTIFICACAO_ATIVO","") or item.get("ID_POCO","") or item.get("ID_LOGGER","") or "Ativo")
            nome_sec=str(item.get("NOME_POCO","") or item.get("ENDERECO", ""))
            folium.Marker([lat,lon],icon=folium.Icon(color="orange",icon=icone,prefix="fa"),
                tooltip=f"{nome} — {nome_sec}").add_to(camada)
            if rotulos:
                folium.Marker([lat,lon],icon=folium.DivIcon(icon_size=(155,20),icon_anchor=(-8,24),
                    html='<div style="display:inline-block;white-space:nowrap;'
                         'background:#ffffffed;border:1px solid #b8c4d0;'
                         'padding:2px 4px;border-radius:3px;font:bold 10px Arial;'
                         'color:#1b324a">'+escape(nome)+'</div>')).add_to(camada)
        if camada._children:
            camada.add_to(mapa)


def mapa_integrado_farol(concs, os_cluster, pressao, contexto, raio_cluster, pontos_todos=None):
    """Panorama do Farol com TODAS as O.S. do período, alvos, ativos e aferições.

    Inclusive as O.S. fora das concentrações, exatamente como no mapa do Módulo 3.
    """
    pontos_mapa=[]
    if concs is not None and not concs.empty:
        pontos_mapa.extend(concs[["Latitude","Longitude"]].astype(float).values.tolist())
    base_mapa = pontos_todos if pontos_todos is not None else os_cluster
    if base_mapa is not None and not base_mapa.empty:
        pontos_mapa.extend([[float(r["_lat"]),float(r["_lon"])]
            for _,r in base_mapa.dropna(subset=["_lat","_lon"]).iterrows()])
    if pressao is not None and not pressao.empty:
        pontos_mapa.extend([[float(r["_lat"]),float(r["_lon"])]
            for _,r in pressao.dropna(subset=["_lat","_lon"]).iterrows()
            if pressao_visivel(r)])
    if not pontos_mapa:
        return None
    centro_lat=sum(p[0] for p in pontos_mapa)/len(pontos_mapa)
    centro_lon=sum(p[1] for p in pontos_mapa)/len(pontos_mapa)
    mapa=folium.Map(location=[centro_lat,centro_lon], zoom_start=12,
                     tiles="OpenStreetMap",control_scale=True,zoom_control=False)
    posicoes=[]
    os_fg=folium.FeatureGroup(name="O.S. — Farol",show=True)
    if base_mapa is None:
        base_mapa = pd.DataFrame()
    for _,p in base_mapa.iterrows():
        if pd.isna(p.get("_lat")) or pd.isna(p.get("_lon")): continue
        lat,lon=float(p["_lat"]),float(p["_lon"])
        servico=str(p.get("Serviço Executado", ""))
        cor="#f28c28" if re.search(r"(?<!\d)146005(?!\d)",servico) else "#1677d2"
        folium.CircleMarker([lat,lon],radius=4.2,color=cor,weight=1,fill=True,
            fill_color=cor,fill_opacity=.9,
            tooltip=f"O.S. {p.get('Nº da O.S','')} — {p.get('Bairro','')}").add_to(os_fg)
        posicoes.append([lat,lon])
    os_fg.add_to(mapa)
    centros=[(float(c["Latitude"]),float(c["Longitude"])) for _,c in concs.iterrows()] if concs is not None and not concs.empty else []
    if centros:
        adicionar_ativos_eventos_mapa(mapa,contexto,centros=centros,raio=raio_cluster)
    # A inclusão de TODAS as aferições do período não depende de uma associação com O.S.
    pontos_bp=adicionar_pontos_pressao(mapa,pressao)
    for _,c in (concs if concs is not None else pd.DataFrame()).iterrows():
        y,x=float(c["Latitude"]),float(c["Longitude"])
        folium.Circle([y,x],radius=raio_cluster,color="#8522a5",weight=3,
                      fill=True,fill_color="#8522a5",fill_opacity=.05).add_to(mapa)
        marcador_concentracao(c).add_to(mapa)
        posicoes.append([y,x])
    # Todas as medições válidas selecionadas entram no enquadramento, inclusive
    # bairros sem O.S. concentradas (antes pontos >10 km eram cortados).
    enquadrar=posicoes+pontos_bp
    if len(enquadrar)>1:
        mapa.fit_bounds(enquadrar,padding=(35,35),max_zoom=14)
    adicionar_legenda_integrada(mapa,bool(pontos_bp))
    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


def mapa_ficha_farol(c, grupo, pressao, contexto, raio_cluster):
    centro=[float(c["Latitude"]),float(c["Longitude"])]
    mapa=folium.Map(location=centro,zoom_start=15,tiles="OpenStreetMap",control_scale=True,zoom_control=False)
    folium.Circle(centro,radius=raio_cluster,color="#8522a5",weight=3,
                  fill=True,fill_color="#8522a5",fill_opacity=.06).add_to(mapa)
    pontos_os=[]
    os_fg=folium.FeatureGroup(name="O.S. — Concentração",show=True)
    for _,p in grupo.iterrows():
        if pd.isna(p.get("_lat")) or pd.isna(p.get("_lon")):continue
        y,x=float(p["_lat"]),float(p["_lon"])
        cor="#f28c28" if re.search(r"(?<!\d)146005(?!\d)",str(p.get("Serviço Executado", ""))) else "#1677d2"
        folium.CircleMarker([y,x],radius=4.5,color=cor,weight=1,fill=True,
            fill_color=cor,fill_opacity=.92,tooltip=f"O.S. {p.get('Nº da O.S','')}").add_to(os_fg)
        pontos_os.append([y,x])
    os_fg.add_to(mapa)
    municipio=str(c.get("Município", "")).split(",")[0]
    adicionar_ativos_eventos_mapa(mapa,contexto,municipio=municipio,
                                   centros=[tuple(centro)],raio=raio_cluster,rotulos=True)
    codigo_set={normalizar(b) for b in str(c.get("Bairros", "")).split(",")}
    med_visivel=[]
    for _,p in pressao.iterrows():
        if p.get("_municipio")!=normalizar(municipio):continue
        if pd.isna(p.get("_lat")) or pd.isna(p.get("_lon")):continue
        if not pressao_visivel(p):continue
        y,x=float(p["_lat"]),float(p["_lon"])
        perto=any(haversine(y,x,p_os[0],p_os[1])<=max(raio_cluster*2,750) for p_os in pontos_os)
        if perto or (p.get("_bairro") in codigo_set and haversine(y,x,*centro)<=3000):
            med_visivel.append(p)
    pos_bp=adicionar_pontos_pressao(mapa,pd.DataFrame(med_visivel)) if med_visivel else []
    marcador_concentracao(c).add_to(mapa)
    extremos=pontos_os+pos_bp
    if extremos:
        extremos += [centro]
        if len(extremos)>1:
            mapa.fit_bounds(extremos,padding=(40,40),max_zoom=16)
    adicionar_legenda_integrada(mapa,bool(pos_bp))
    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


def ativos_da_concentracao(c,contexto,raio):
    achados=[]
    for tipo in ("POCOS","LOGGERS"):
        df=contexto.get(tipo,pd.DataFrame())
        if df.empty:continue
        for _,a in df.iterrows():
            lat=coordenada(a.get("LATITUDE",a.get("Latitude")),"lat")
            lon=coordenada(a.get("LONGITUDE",a.get("Longitude")),"lon")
            if lat is None or lon is None:continue
            cidade=normalizar(a.get("MUNICIPIO",a.get("Município","")))
            if cidade and cidade not in normalizar(c["Município"]):continue
            distancia=haversine(float(c["Latitude"]),float(c["Longitude"]),lat,lon)
            if distancia<=raio:
                ident=str(a.get("IDENTIFICACAO_ATIVO",a.get("ID_POCO",a.get("ID_LOGGER",""))))
                nome=str(a.get("NOME_POCO",a.get("ENDERECO","")))
                achados.append(["Poço" if tipo=="POCOS" else "Logger",ident,nome,f"{distancia:.0f} m"])
    return sorted(achados,key=lambda v:float(v[3].split()[0]))


def evento_tem_abrangencia_municipal(texto):
    return bool(re.search(r"(?:TODA A CIDADE|TODO O MUNICIPIO|MUNICIPIO INTEIRO|TODOS OS BAIRROS)", normalizar(texto)))


def nomes_bairros_evento(texto):
    bruto=normalizar(texto)
    bruto=re.sub(r"BAIRROS?\s*(?:IMPACTADOS?|AFETADOS?)?\s*:",";",bruto)
    bruto=re.sub(r"AREAS?\s+IMPACTADAS?\s*:",";",bruto)
    return {re.sub(r"\s*\(PARCIAL\)","",p).strip(" .:-")
            for p in re.split(r"[,;\n]+",bruto) if p.strip(" .:-")}


def evento_na_janela(evento, inicio, fim):
    """Verifica interseção temporal, sem declarar ativo evento encerrado sem término."""
    ini=data_parse(evento.get("Início", ""))
    term=data_parse(evento.get("Término Real", ""))
    if pd.isna(ini):return False
    finalizado=any(p in normalizar(evento.get("Status","")) for p in ("FINALIZ", "CONCLUID", "ENCERRAD"))
    if pd.isna(term) and finalizado:return False
    if pd.notna(term) and term.date()<inicio:return False
    if ini.date()>fim:return False
    return True


def eventos_da_concentracao(c,contexto,inicio=None,fim=None):
    """Mesmas chaves de município/bairro do Farol, e evento ativo no período."""
    eventos=contexto.get("EVENTOS",pd.DataFrame())
    if eventos is None or eventos.empty:return []
    pares=set(c.get("_pares_bairro", []))
    municipios={municipio for municipio,_ in pares}
    municipios.update(normalizar(v) for v in str(c.get("Município","")).split(",") if v.strip())
    encontrados=[]
    for _,e in eventos.iterrows():
        mun=normalizar(e.get("Cidade",""))
        if mun not in municipios:continue
        if inicio is not None and fim is not None and not evento_na_janela(e,inicio,fim):continue
        areas=e.get("Áreas Impactadas", "")
        municipal=evento_tem_abrangencia_municipal(areas)
        coincidentes=sorted({bairro for cidade,bairro in pares
                            if cidade==mun and bairro in nomes_bairros_evento(areas)})
        if not municipal and not coincidentes:continue
        item=e.to_dict()
        item["Bairros coincidentes"]="Todo o município" if municipal and not coincidentes else ", ".join(coincidentes)
        encontrados.append(item)
    return encontrados


def horario_operacional(valor):
    """Data sem hora não basta para vincular uma O.S. temporalmente ao evento."""
    texto=str(valor or "").strip()
    if not texto or re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}",texto):
        return pd.NaT
    return data_parse(texto)


def classificar_os_eventos(grupo,eventos):
    """Classificação Farol: município, bairro e horário [início, fim + 3h]."""
    vinculadas=[]; nao_vinculadas=[]
    agora=pd.Timestamp.now().tz_localize(None)
    for _,osr in grupo.iterrows():
        data_os=horario_operacional(osr.get("Dt. Emissão", ""))
        cidade=normalizar(osr.get("Cidade", ""))
        bairro=normalizar(osr.get("Bairro", ""))
        protocolos=[]
        if pd.notna(data_os):
            for e in eventos:
                if cidade!=normalizar(e.get("Cidade", "")):continue
                b_evt=nomes_bairros_evento(e.get("Bairros coincidentes", ""))
                if ("TODO O MUNICIPIO" not in normalizar(e.get("Bairros coincidentes", ""))
                    and bairro not in b_evt):
                    continue
                ini=horario_operacional(e.get("Início", ""))
                fim=horario_operacional(e.get("Término Real", ""))
                if pd.isna(ini):continue
                finalizado=any(p in normalizar(e.get("Status","")) for p in ("FINALIZ","CONCLUID","ENCERRAD"))
                if pd.isna(fim):
                    if finalizado:continue
                    fim=agora
                if ini <= data_os <= fim+pd.Timedelta(hours=3):
                    protocolos.append(str(e.get("Protocolo","") or e.get("Serviço", "") or "Evento"))
        registro=osr.to_dict()
        registro["Eventos vinculados"]="; ".join(dict.fromkeys(protocolos))
        (vinculadas if protocolos else nao_vinculadas).append(registro)
    return vinculadas,nao_vinculadas


def protocolo_os_relatorio(reg):
    """Usa O.S. e ano quando há emissão válida, como no Módulo 3."""
    numero=str(reg.get("Nº da O.S","") or "").strip()
    if not numero or numero.lower()=="nan":return ""
    if re.search(r"/\d{4}-1$",numero):return numero
    dt=data_parse(reg.get("Dt. Emissão", ""))
    return f"{numero}/{dt.year}-1" if pd.notna(dt) else numero


def ficha_acompanhamento(c,grupo,contexto):
    """Busca vínculo pela chave exata de O.S. usada pelo Farol, sem chamadas extras."""
    vinc=contexto.get("vinculos_farol_producao",pd.DataFrame())
    fichas=contexto.get("eventos_acomp",pd.DataFrame())
    mov=contexto.get("movimentacoes",pd.DataFrame())
    if vinc.empty or fichas.empty:return None, []
    try:
        from integracao_acompanhamento_producao import chave_concentracao
        numeros=sorted({str(x).strip() for x in grupo["Nº da O.S"] if str(x).strip()})
        chave=chave_concentracao(str(c.get("Município","")),float(c["Latitude"]),float(c["Longitude"]),numeros)
    except Exception:
        return None,[]
    cols={normalizar(z):z for z in vinc.columns}
    ch=cols.get("CHAVE")
    ev=cols.get("EVENTO_ID")
    if not ch or not ev:return None,[]
    achado=vinc[vinc[ch].astype(str)==chave]
    if achado.empty:return None,[]
    evento_id=str(achado.iloc[-1][ev])
    if "id" not in fichas.columns:return None,[]
    f=fichas[fichas["id"].astype(str)==evento_id]
    if f.empty:return None,[]
    movimentos=[]
    if not mov.empty and "evento_id" in mov.columns:
        for _,m in mov[mov["evento_id"].astype(str)==evento_id].iterrows():
            if not str(m.get("descricao","")).startswith("Registro inicial criado. Relato:"):
                movimentos.append(m.to_dict())
    return f.iloc[-1].to_dict(),movimentos


def pdf_relatorio(resumo, associados, territoriais, achados, inicio, fim, raio, n_os, n_bp,
                  concentracoes=None, grupos=None, raio_cluster=500, contexto=None, pressao=None,
                  pontos_todos=None):
    """Relatório do Farol: panorama + fichas com mapa e O.S. ao lado.

    Mantém ativos, eventos, classificação temporal de O.S. e acompanhamento.
    Detalha medições associadas nas fichas e todas as aferições no anexo M1.
    Não modifica nem importa a página do Módulo 3.
    """
    contexto = contexto or {}
    pressao = pressao if pressao is not None else pd.DataFrame()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
            leftMargin=1.2*cm, rightMargin=1.2*cm,
            topMargin=1.2*cm, bottomMargin=1.2*cm)
    regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.isfile(regular) and "FIntReg" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("FIntReg", regular))
        pdfmetrics.registerFont(TTFont("FIntBold", bold))
        pdfmetrics.registerFontFamily("FIntReg", normal="FIntReg", bold="FIntBold")
    fonte = "FIntReg" if "FIntReg" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    azul = colors.HexColor("#193c65")
    normal = ParagraphStyle("farol_integra_normal",fontName=fonte,fontSize=8.4,leading=11.5)
    pequeno = ParagraphStyle("farol_integra_pequeno",parent=normal,fontSize=7.1,leading=9.3)
    titulo = ParagraphStyle("farol_integra_titulo",parent=normal,fontSize=12.5,leading=16,spaceAfter=8,textColor=azul)
    secao = ParagraphStyle("farol_integra_secao",parent=normal,fontSize=9.7,leading=12,
                           spaceBefore=8,spaceAfter=5,textColor=azul)
    def P(v,sty=pequeno):
        return Paragraph(xml_escape(str(v if v is not None else "")).replace("\n","<br/>"),sty)
    def tabela(cab,linhas,larguras):
        dados=[[P(x) for x in cab]]+[[P(v) for v in linha] for linha in linhas]
        t=Table(dados,colWidths=larguras,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dee8f2")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f7fb")]),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),3),
            ("RIGHTPADDING",(0,0),(-1,-1),3),
            ("TOPPADDING",(0,0),(-1,-1),3),
            ("BOTTOMPADDING",(0,0),(-1,-1),3)
        ]))
        return t
    def tabela_os(linhas,largura=11.85*cm):
        return tabela(["O.S. / Ano","Matrícula","Status"],linhas,
                      [largura*.37,largura*.27,largura*.36])

    historia=[P("Farol Operacional — Relatório de concentrações",titulo),
             P(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} | Gerado em {datetime.now():%d/%m/%Y %H:%M}"
               + (" | Unidade: " + str(concentracoes.iloc[0]["_unidade"]) if concentracoes is not None and not concentracoes.empty else ""),normal),
             Spacer(1,9)]
    resumo_bp = resumo_pressao_por_bairro(pressao)

    def adicionar_secao_modulo1():
        """Anexo M1 completo, mesmo quando não houver pressão junto às O.S."""
        if pressao.empty or resumo_bp.empty:
            return
        historia.append(P("PANORAMA DE PRESSÃO — MÓDULO 1", titulo))
        achados_m1=diagnostico_pressao_independente(pressao,resumo_bp,associados,territoriais)
        for item in achados_m1:
            historia.append(P("• " + item, normal))
            historia.append(Spacer(1, 3))
        historia.append(Spacer(1, 5))
        linhas=[]
        for _,r_bp in resumo_bp.iterrows():
            linhas.append([f"{r_bp['Bairro']} — {r_bp['Município']}",
                r_bp["Medições"],r_bp["0 mca"],r_bp["Até 5 mca"],
                r_bp["5–10 mca"],r_bp["10–15 mca"],r_bp[">15 mca"],
                f"{r_bp['Mín. (mca)']:g}"])
        historia.append(tabela(["Bairro / município","Medições","0 mca","≤5 mca",
            "5–10 mca","10–15 mca",">15 mca","Mín. mca"], linhas,
            [9.1*cm,2.6*cm,2.2*cm,2.3*cm,2.4*cm,2.6*cm,2.2*cm,2.6*cm]))
        historia.extend([Spacer(1,6),P("Medições de 10 a 15 mca são contabilizadas, mas "
            "permanecem ocultas no mapa, conforme a configuração do Módulo 1.", pequeno)])

    if concentracoes is None or concentracoes.empty:
        historia.append(P("Nenhuma concentração identificada para a seleção.", normal))
        if not pressao.empty:
            mapa_bp=mapa_integrado_farol(pd.DataFrame(), pd.DataFrame(), pressao, contexto,
                                        raio_cluster, pontos_todos=pontos_todos)
            if mapa_bp is not None:
                historia.append(Spacer(1,8))
                historia.append(Image(io.BytesIO(imagem_folium(mapa_bp,1280,700)),
                                      width=26*cm,height=14.22*cm))
            historia.append(PageBreak())
            adicionar_secao_modulo1()
        doc.build(historia)
        return buffer.getvalue()

    # PANORAMA do Farol + todos os pontos cartográficos válidos de pressão.
    mapa=mapa_integrado_farol(concentracoes,grupos,pressao,contexto,raio_cluster,
                             pontos_todos=pontos_todos)
    imagem=imagem_folium(mapa,1280,700)
    n_bairros_bp = len(resumo_bp)
    p_criticos = (int(pd.to_numeric(pressao["_pressao"],errors="coerce").le(5).sum())
                  if not pressao.empty else 0)
    subtitulo=(f"Concentrações: {len(concentracoes)} · {n_os} O.S. e equipamentos operacionais"
               + (f" · Módulo 1: {len(pressao)} medições em {n_bairros_bp} bairros,"
                  f" {p_criticos} até 5 mca" if not pressao.empty else "") + ".")
    historia.append(KeepTogether([
        P("Panorama territorial das concentrações",titulo),
        Image(io.BytesIO(imagem),width=26*cm,height=14.22*cm),
        Spacer(1,4),P(subtitulo)
    ]))
    historia.append(PageBreak())

    for indice,(_,c) in enumerate(resumo.iterrows()):
        codigo=str(c["Concentração"])
        grupo=grupos[grupos["_grupo"]==c["_grupo"]].copy()
        proximas=associados[associados["Concentração"]==codigo] if not associados.empty else pd.DataFrame()
        territoriais_c=territoriais[territoriais["Concentração"]==codigo] if not territoriais.empty else pd.DataFrame()
        historia.append(P(f"{codigo} — {c['Município']} — {c['Bairros']}",titulo))
        med_ficha=(pd.concat([proximas,territoriais_c], ignore_index=True)
                   if not proximas.empty or not territoriais_c.empty else pressao.iloc[:0].copy())
        figura=imagem_folium(mapa_ficha_farol(c,grupo,med_ficha,contexto,raio_cluster),760,515)
        img=Image(io.BytesIO(figura),width=13.4*cm,height=9.08*cm)
        eventos=eventos_da_concentracao(c,contexto,inicio,fim)
        vinculadas,nao_vinculadas=classificar_os_eventos(grupo,eventos)
        ev_descr="; ".join((f"{e.get('Protocolo','')} — {e.get('Serviço','')} / "
                           f"{e.get('Código do Ativo','')} [{e.get('Status','')}] "
                           f"{e.get('Início','')} até {e.get('Término Real','') or 'em andamento'}")
                          for e in eventos)
        base_info=[P(f"{len(grupo)} O.S. · {int(c['Matrículas'])} matrículas distintas",normal),
                   Spacer(1,5),Paragraph("<b>Eventos relacionados:</b> " +
                          xml_escape(ev_descr or "Nenhum evento relacionado"),pequeno),
                   Spacer(1,3)]
        def linhas_os(registros):
            return [[protocolo_os_relatorio(r),str(r.get("Matrícula","")),
                     str(r.get("Status OS",""))] for r in registros]
        categorias=[("Ordens vinculadas aos eventos",linhas_os(vinculadas)),
                    ("Ordens não vinculadas",linhas_os(nao_vinculadas))]
        def conteudo_painel(qt):
            blocos=list(base_info)
            for (nome,linhas),qtd in zip(categorias,qt):
                blocos.extend([Spacer(1,4),Paragraph("<b>" +
                    xml_escape(f"{nome} ({len(linhas)})") + "</b>",pequeno)])
                if linhas and qtd:
                    blocos.append(tabela_os(linhas[:qtd]))
                elif not linhas:
                    blocos.append(P("Nenhuma O.S. nesta categoria."))
            return blocos
        # Reserva exatamente o espaço do painel lateral usado pelo Farol.
        limite_h=9.08*cm-12
        largura_painel=12.8*cm-16
        def altura_bloco(elements):
            altura=0
            for element in elements:
                _,h=element.wrap(largura_painel,limite_h)
                altura+=h+element.getSpaceBefore()+element.getSpaceAfter()
            return altura
        contagens=[0,0]
        for k,(_,linhas) in enumerate(categorias):
            for _ in linhas:
                candidato=contagens.copy(); candidato[k]+=1
                if altura_bloco(conteudo_painel(candidato))<=limite_h:
                    contagens=candidato
                else:break
        ficha=Table([[img,conteudo_painel(contagens)]],
                    colWidths=[13.8*cm,12.8*cm],hAlign="LEFT")
        ficha.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("BACKGROUND",(1,0),(1,0),colors.HexColor("#f4f7fb")),
            ("LEFTPADDING",(0,0),(0,0),0),
            ("LEFTPADDING",(1,0),(1,0),10),
            ("RIGHTPADDING",(1,0),(1,0),6),
            ("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ]))
        historia.extend([ficha,Spacer(1,7)])
        for (nome,linhas),ja_exibidas in zip(categorias,contagens):
            restantes=linhas[ja_exibidas:]
            if restantes:
                painel=Table([[[P(f"{nome} — continuação"),Spacer(1,4),
                                 tabela_os(restantes,25.6*cm)]]],colWidths=[26.6*cm],hAlign="LEFT")
                painel.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f4f7fb")),
                    ("LEFTPADDING",(0,0),(-1,-1),10),
                    ("RIGHTPADDING",(0,0),(-1,-1),10),
                    ("TOPPADDING",(0,0),(-1,-1),8),
                    ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
                historia.extend([Spacer(1,5),painel])
        # Padrão do Farol: equipamentos são exibidos no mapa e os eventos no
        # painel de O.S. Não criar quadros extras que alterem o layout original.
        acompanhamento,movimentacoes=ficha_acompanhamento(c,grupo,contexto)
        historia.append(P("ACOMPANHAMENTO OPERACIONAL",secao))
        if acompanhamento:
            historia.append(tabela(["Status / Finalizado","Município / Regional","Reclamações / Unidade"],[[
                f"{acompanhamento.get('status','')} · {acompanhamento.get('finalizado','')}",
                f"{acompanhamento.get('municipio','')} · {acompanhamento.get('regional','')}",
                f"{acompanhamento.get('qtd_reclamacoes','')} · {acompanhamento.get('unidade','')}"
            ]],[8.8*cm,8.8*cm,8.4*cm]))
            historia.extend([P("Validações operacionais",secao),
                tabela(["ArcGIS","SIA","Loggers","Retorno Operação/Controle"],[[
                acompanhamento.get("arcgis",""),acompanhamento.get("sia",""),
                acompanhamento.get("loggers",""),acompanhamento.get("retorno_operacao","")]],
                [6.0*cm,6.0*cm,6.0*cm,8.0*cm]),
                P("Descrição da ocorrência",secao),P(acompanhamento.get("descricao",""),normal)])
            if movimentacoes:
                historia.append(P("Histórico de movimentações",secao))
                historia.append(tabela(["Data / Hora","Status","Descrição"],[
                    [m.get("data_hora",""),m.get("status_momento",""),m.get("descricao","")]
                    for m in movimentacoes],[4.5*cm,4.5*cm,17.0*cm]))
        else:
            historia.append(P("Nenhum acompanhamento operacional iniciado para esta concentração."))
        # COMPLEMENTO M1 da ficha: só quando existir associação pertinente.
        if not proximas.empty or not territoriais_c.empty:
            historia.append(P("MEDIÇÕES DE PRESSÃO — MÓDULO 1",secao))
            if not proximas.empty:
                qtd=len(proximas)
                crit=int(pd.to_numeric(proximas["_pressao"],errors="coerce").le(5).sum())
                historia.append(P(f"{qtd} medição(ões) até {raio} m de pelo menos uma O.S. "
                                   + (f"{crit} com pressão de 0 a 5 mca." if crit else ""),normal))
            else:
                historia.append(P("Correspondência pelo bairro; a distância às O.S. não foi confirmada.",normal))
            for subt,base,confirmada in (("Medições próximas às O.S.",proximas,True),
                                         ("Medições no mesmo bairro",territoriais_c,False)):
                if base.empty:continue
                historia.append(P(f"{subt} ({len(base)})",secao))
                linhas=[]
                for _,med in base.iterrows():
                    v=med.get("_pressao")
                    distancia=med.get("Distância até O.S. (m)")
                    linhas.append([med.get("Data",""),med.get("Bairro",""),
                        f"{float(v):g}" if pd.notna(v) else "Não aferida",
                        (f"{distancia} m" if pd.notna(distancia) else "—") if confirmada else "Bairro",
                        med.get("Observacao","")])
                historia.append(tabela(["Data","Bairro","mca","Relação","Observação"],
                               linhas,[3.0*cm,5.4*cm,2.2*cm,4.6*cm,10.8*cm]))
            analise = str(c.get("Análise operacional", "") or "").strip()
            if analise:
                historia.extend([P("LEITURA OPERACIONAL",secao),P(analise,normal)])
            historia.append(P("Associação espacial/territorial não confirma causa hidráulica.",pequeno))
        if indice<len(resumo)-1:
            historia.append(PageBreak())
    if not pressao.empty:
        historia.append(PageBreak())
        adicionar_secao_modulo1()
    doc.build(historia)
    return buffer.getvalue()


st.title("📊 Relatórios Integrados — Farol + Baixa Pressão")
st.caption("Integração analítica entre concentrações de O.S. e registros de pressão · fontes somente leitura")
if st.button("← Voltar ao Hub Central",key="retornar_hub_ri"):
    st.switch_page("app.py")

hoje=date.today()
with st.form("parametros"):
    unidade_sel=st.radio("Unidade do relatório",["THE — Teresina", "API — Piauí", "TIM — Timon"],horizontal=True)
    a,b,c,d=st.columns(4)
    with a: inicio=st.date_input("Data inicial",value=hoje-timedelta(days=7),format="DD/MM/YYYY")
    with b: fim=st.date_input("Data final",value=hoje,format="DD/MM/YYYY")
    with c: raio_cluster=st.number_input("Raio das concentrações (m)",min_value=100,max_value=3000,value=500,step=100)
    with d: minimo=st.number_input("Mínimo de O.S.",min_value=2,max_value=30,value=2)
    e,f=st.columns(2)
    with e: raio_relacao=st.number_input("Raio da medição até alguma O.S. (m)",min_value=50,max_value=3000,value=500,step=50)
    with f: municipio_sel=st.text_input("Município (opcional)",placeholder="Todos os municípios")
    executar=st.form_submit_button("Gerar diagnóstico integrado",type="primary",use_container_width=True)
if executar:
    # Descarta resultados antigos antes de uma nova consulta, evitando exibir diagnósticos desatualizados.
    st.session_state.pop("relatorio_coi_integrado", None)
    st.session_state.pop("pdf_relatorio_integrado_farol", None)
    if inicio>fim:
        st.error("A data inicial não pode ser posterior à data final.")
        st.stop()
    try:
        with st.spinner("Consultando as bases e cruzando O.S. com medições..."):
            os_df=preparar_os(ler_base(ID_FAROL,"PONTOS"))
            contexto=carregar_contexto_farol()
            bp_todas=preparar_pressao(ler_base(ID_PRESSAO,"baixa_pressao"))
            contagem_origem={"total": len(bp_todas),
                "data_valida": int(bp_todas["_data"].notna().sum()),
                "pressao_valida": int(bp_todas["_pressao"].notna().sum())}
            os_df=os_df[os_df["_data"].dt.date.between(inicio,fim)].copy()
            bp=bp_todas[bp_todas["_data"].dt.date.between(inicio,fim) & bp_todas["_pressao"].notna()].copy()
            contagem_origem["periodo"] = len(bp)
            unidade=unidade_sel.split(" ",1)[0]
            os_df=os_df[os_df["Cidade"].map(unidade_da_cidade_farol)==unidade].copy()
            bp=bp[bp["Municipio"].map(unidade_da_cidade_farol)==unidade].copy()
            if municipio_sel.strip():
                mun=normalizar(municipio_sel)
                os_df=os_df[os_df["_municipio"]==mun]
                bp=bp[bp["_municipio"]==mun]
            contagem_origem["unidade_municipio"] = len(bp)
            resumo_bp=resumo_pressao_por_bairro(bp)
            concs,grupos=concentracoes_farol(os_df,int(raio_cluster),int(minimo))
            if not concs.empty:
                resumo,associados,territoriais=relacionar(concs,grupos,bp,int(raio_relacao),inicio,fim)
                achados,pressao_sem_conc=diagnostico_geral(resumo,bp,associados,territoriais,inicio,fim)
            else:
                resumo,associados,territoriais=pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
                achados=["Nenhuma concentração atende aos critérios selecionados."]
                pressao_sem_conc=bp.iloc[:0].copy()
            st.session_state["relatorio_coi_integrado"]={"versao_esquema":9,"resumo":resumo,"associados":associados,"territoriais":territoriais,
             "concentracoes":concs,"achados":achados,"pressao_sem_conc":pressao_sem_conc,
             "inicio":inicio,"fim":fim,"raio":int(raio_relacao),"n_os":len(os_df),"n_bp":len(bp),"grupos":grupos,"raio_cluster":int(raio_cluster),"contexto":contexto,"pressao_mapa":bp,"unidade":unidade,"os_base":os_df,"resumo_bp":resumo_bp,"contagem_origem":contagem_origem}
    except gspread.exceptions.APIError as ex:
        codigo=getattr(getattr(ex,"response",None),"status_code",None)
        st.error("Quota temporária do Google Sheets excedida (429)." if codigo==429 else f"Falha na consulta às fontes (HTTP {codigo or 'desconhecido'}).")
        st.stop()
    except Exception as ex:
        st.error(f"Falha ao preparar relatório: {ex}")
        st.stop()

r=st.session_state.get("relatorio_coi_integrado")
# Streamlit mantém session_state entre atualizações de código. Um resultado salvo
# pela versão anterior não tem as chaves "achados"/"associados" e não pode ser
# apresentado como se tivesse passado pela análise nova.
_chaves_necessarias = {
    "resumo", "associados", "territoriais", "concentracoes", "achados", "grupos", "raio_cluster",
    "pressao_sem_conc", "inicio", "fim", "raio", "n_os", "n_bp", "contexto", "pressao_mapa", "unidade", "os_base", "resumo_bp", "contagem_origem"
}
if r is not None and (
    not isinstance(r, dict)
    or r.get("versao_esquema") != 9
    or not _chaves_necessarias.issubset(r)
):
    st.session_state.pop("relatorio_coi_integrado", None)
    r = None
    st.info("O diagnóstico anterior é de uma versão antiga. Clique em **Gerar diagnóstico integrado** para atualizar a análise.")
if r:
    resumo=r["resumo"]
    tem_pressao = r["n_bp"] > 0
    if tem_pressao:
        a,b,c,d=st.columns(4)
        a.metric("O.S. no período",r["n_os"])
        b.metric("Concentrações",len(resumo))
        c.metric("Medições no período",r["n_bp"])
        d.metric("Concentrações com medição próxima",int((resumo["Medições próximas"]>0).sum()) if not resumo.empty else 0)
    else:
        a,b=st.columns(2)
        a.metric("O.S. no período",r["n_os"])
        b.metric("Concentrações",len(resumo))
    st.subheader(f"Análise operacional — {r['unidade']}")
    for achado in r["achados"]:
        st.write("• " + achado)
    if not resumo.empty or tem_pressao:
        st.subheader("Mapa consolidado")
        st.caption("Mapa integrado: concentrações, O.S. e equipamentos operacionais do Farol." +
                   (" Medições do Módulo 1 sobrepostas: vermelho (0–5 mca), amarelo (5–10 mca) e roxo (>15 mca)." if tem_pressao else ""))
        mapa=mapa_integrado_farol(r["concentracoes"],r["grupos"],r["pressao_mapa"],r["contexto"],
                                  r["raio_cluster"],pontos_todos=r["os_base"])
        if mapa is not None:
            st_folium(mapa,height=500,width=None,returned_objects=[],key="mapa_integrado_relatorio")
        st.subheader("Concentrações operacionais")
        visiveis=["Concentração","Município","Bairros","O.S.","Matrículas"]
        if not resumo.empty and ((resumo["Medições próximas"]>0)|(resumo["Medições mesmo bairro"]>0)).any():
            visiveis += ["Medições próximas","Medições mesmo bairro","Menor pressão (mca)","Classificação indicativa"]
        if not resumo.empty:
            st.dataframe(resumo[visiveis],hide_index=True,use_container_width=True)
        else:
            st.caption("Não há concentração nesta seleção. Os pontos medidos do Módulo 1 continuam visíveis no mapa.")
        if st.button("📄 Preparar relatório cartográfico (PDF)", type="primary", key="gerar_pdf_ri_farol"):
            try:
                with st.spinner("Capturando mapas e montando as fichas operacionais..."):
                    st.session_state["pdf_relatorio_integrado_farol"] = pdf_relatorio(
                        resumo,r["associados"],r["territoriais"],r["achados"],r["inicio"],r["fim"],
                        r["raio"],r["n_os"],r["n_bp"],r["concentracoes"],r["grupos"],r["raio_cluster"],r["contexto"],r["pressao_mapa"],r["os_base"])
            except Exception as erro_pdf:
                st.error(f"Não foi possível capturar o mapa para o PDF: {erro_pdf}. "
                         "Confirme a disponibilidade do Playwright/Chromium, como no Farol.")
        if st.session_state.get("pdf_relatorio_integrado_farol"):
            st.download_button("⬇️ Baixar relatório no padrão Farol (PDF)",
                data=st.session_state["pdf_relatorio_integrado_farol"],
                file_name="relatorio_operacional_integrado_coi.pdf",mime="application/pdf")
        if not resumo.empty:
            st.download_button("📋 Baixar diagnóstico (CSV)",data=resumo[visiveis].to_csv(index=False,sep=";").encode("utf-8-sig"),
                file_name="diagnostico_integrado_coi.csv",mime="text/csv")
        if not r["associados"].empty:
            with st.expander("Medições associadas por proximidade geográfica"):
                campos=["Concentração","Data","Municipio","Bairro","Matricula","Pressao_MCA","_faixa","Distância até O.S. (m)","Observacao"]
                st.dataframe(r["associados"].reindex(columns=campos),hide_index=True,use_container_width=True)
        if not r["territoriais"].empty:
            with st.expander("Indícios apenas pelo mesmo bairro (sem proximidade confirmada)"):
                campos=["Concentração","Data","Municipio","Bairro","Matricula","Pressao_MCA","_faixa","Observacao"]
                st.dataframe(r["territoriais"].reindex(columns=campos),hide_index=True,use_container_width=True)
        if not r["pressao_sem_conc"].empty:
            with st.expander("Medições até 5 mca em bairros sem concentração"):
                st.dataframe(r["pressao_sem_conc"][["Data","Municipio","Bairro","Pressao_MCA","Observacao"]],hide_index=True,use_container_width=True)
    if tem_pressao:
        st.divider()
        st.subheader("Módulo 1 — Panorama de pressão por bairro")
        st.caption("Inclui TODAS as medições do período e unidade, mesmo quando não se relacionam a uma concentração de O.S.")
        for item in diagnostico_pressao_independente(r["pressao_mapa"],r["resumo_bp"],r["associados"],r["territoriais"]):
            st.write("• " + item)
        st.dataframe(r["resumo_bp"], hide_index=True, use_container_width=True)
        st.download_button("📥 Baixar medições do Módulo 1 (CSV)",
            data=r["pressao_mapa"][["Data","Municipio","Bairro","Latitude","Longitude","Pressao_MCA","Observacao","Matricula"]].to_csv(index=False,sep=";").encode("utf-8-sig"),
            file_name="medicoes_pressao_modulo1.csv", mime="text/csv")
    else:
        origem=r["contagem_origem"]
        st.caption("Módulo 1: nenhuma medição válida para o período, unidade e município selecionados. "
                   f"Registros disponíveis na fonte: {origem['total']}; datas reconhecidas: "
                   f"{origem['data_valida']}; pressões numéricas: {origem['pressao_valida']}; "
                   f"válidas no período (antes de filtrar unidade): {origem['periodo']}.")
else:
    st.info("Selecione o período e clique em **Gerar diagnóstico integrado**. As bases são consultadas somente quando solicitado.")
