"""Módulo 7 — Relatórios Integrados COI.
Leitura exclusiva de Módulo 1 (baixa_pressao) e Módulo 3 (PONTOS).
Não importa os módulos interativos: reproduz o algoritmo espacial do Farol.
"""
import io
import json
import math
import os
import shutil
import tempfile
from pathlib import Path
import unicodedata
from datetime import date, datetime, timedelta
from html import escape

import folium
import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image, PageBreak
from reportlab.graphics.shapes import Drawing, Circle, String, Rect
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

def flutuante(valor):
    texto = str(valor or "").strip().replace(" ", "")
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
    # O Farol admite datas com hora; o Módulo 1 utiliza em geral DD/MM/AAAA.
    return pd.to_datetime(v, dayfirst=True, errors="coerce")

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
    """Algoritmo union-find e grade geográfica compatível com criar_concentracoes do Módulo 3."""
    df = df.dropna(subset=["_lat", "_lon"]).reset_index(drop=True).copy()
    if df.empty: return pd.DataFrame(), df
    lat_step = raio_m / 111320.0
    lon_step = raio_m / (111320.0 * max(0.2, math.cos(math.radians(float(df["_lat"].mean())))))
    buckets = {}
    for i, r in df.iterrows():
        cell = (math.floor(r["_lat"] / lat_step), math.floor(r["_lon"] / lon_step))
        buckets.setdefault(cell, []).append(i)
    parent = list(range(len(df)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(a, b):
        a, b = find(a), find(b)
        if a != b: parent[b] = a
    for (x, y), indices in buckets.items():
        candidatos = [j for dx in (-1,0,1) for dy in (-1,0,1) for j in buckets.get((x+dx,y+dy),[])]
        for i in indices:
            for j in candidatos:
                if j > i and df.at[i,"_municipio"] == df.at[j,"_municipio"] and haversine(df.at[i,"_lat"],df.at[i,"_lon"],df.at[j,"_lat"],df.at[j,"_lon"]) <= raio_m:
                    union(i,j)
    df["_grupo"] = [find(i) for i in range(len(df))]
    validos = df.groupby("_grupo").size()
    df = df[df["_grupo"].isin(validos[validos >= minimo].index)].copy()
    saida = []
    for grupo, bloco in df.groupby("_grupo"):
        cidades = sorted(set(bloco["_municipio"]) - {""})
        saida.append({"_grupo":grupo, "Latitude":float(bloco["_lat"].mean()),
                      "Longitude":float(bloco["_lon"].mean()), "O.S.":len(bloco),
                      "Matrículas":bloco["Matrícula"].replace("",pd.NA).dropna().nunique(),
                      "Município":", ".join(cidades),
                      "Bairros":", ".join(sorted(set(bloco["_bairro"]) - {""}))})
    cdf = pd.DataFrame(saida)
    if cdf.empty: return cdf, df
    cdf = cdf.sort_values(["O.S.","Matrículas"],ascending=False).reset_index(drop=True)
    contador={"THE":0,"API":0}
    ids=[]
    for _,c in cdf.iterrows():
        b = df[df["_grupo"]==c["_grupo"]]
        tipo = "THE" if "TERESINA" in set(b["_municipio"]) else "API"
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
        bairros = set(grupo["_bairro"]) - {""}
        pontos = list(zip(grupo["_lat"], grupo["_lon"]))
        cand = pressao[pressao["_municipio"].isin(municipios)].copy()
        geo_rows, bairro_rows = [], []
        for _, med in cand.iterrows():
            tem_coords = pd.notna(med["_lat"]) and pd.notna(med["_lon"])
            distancia = min((haversine(float(lat),float(lon),float(med["_lat"]),float(med["_lon"])) for lat,lon in pontos),default=float("inf")) if tem_coords else float("inf")
            reg = med.to_dict()
            reg["Concentração"] = c["Concentração"]
            reg["Distância até O.S. (m)"] = round(distancia) if math.isfinite(distancia) else None
            reg["Critério de associação"] = "Proximidade geográfica" if distancia <= raio else "Bairro coincidente (sem proximidade confirmada)"
            if distancia <= raio:
                geo_rows.append(reg)
            elif med["_bairro"] and med["_bairro"] in bairros:
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
            situacao = "SEM MEDIÇÃO CORRELACIONADA"
            leitura = "Não há medição próxima nem no(s) mesmo(s) bairro(s) no período; isso não comprova pressão normal."
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
    achados = [
        f"{len(resumo)} concentração(ões) de O.S. identificada(s); {len(geo)} com medição geograficamente próxima, {len(bairro)} apenas com indício no mesmo bairro e {len(lacunas)} sem medição correlacionada.",
    ]
    if len(geo):
        crit = geo[geo["Sem/baixa pressão"]>0]
        if len(crit):
            achados.append(f"{len(crit)} concentração(ões) têm medição de 0 a 5 mca próxima de pelo menos uma O.S.: " + ", ".join(crit["Concentração"].astype(str)) + ". Priorizar verificação operacional.")
        else:
            achados.append("Há medições próximas a O.S., mas nenhuma delas registrou de 0 a 5 mca no período.")
    if len(bairro):
        achados.append("Correspondências apenas por bairro NÃO são prova de que a baixa pressão ocorreu no endereço da reclamação; confirmar localização e janela de medição.")
    if len(lacunas):
        achados.append(f"Sem dados correlacionados em {len(lacunas)} concentração(ões): ausência de medição não deve ser interpretada como pressão normal.")
    # Diagnóstico de cobertura: bairros com medição crítica e nenhuma concentração no mesmo bairro.
    bp = pressao[pressao["_data"].dt.date.between(inicio,fim)].copy()
    bp = bp[bp["_pressao"].notna() & (bp["_pressao"]<=5)]
    municipios_bairros = set()
    for _,r in resumo.iterrows():
        for b in str(r["Bairros"]).split(","):
            municipios_bairros.add((normalizar(r["Município"]),normalizar(b)))
    isolados = bp[bp.apply(lambda r:(r["_municipio"],r["_bairro"]) not in municipios_bairros,axis=1)].copy()
    if not isolados.empty:
        locais = sorted({f"{r['_bairro']} ({r['_municipio']})" for _,r in isolados.iterrows() if r['_bairro']})
        achados.append(f"Há {len(isolados)} medição(ões) de até 5 mca em bairro(s) sem concentração identificada pelos critérios atuais" + (": " + ", ".join(locais[:6]) if locais else "") + ".")
    return achados,isolados

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


def pdf_relatorio(resumo, associados, territoriais, achados, inicio, fim, raio, n_os, n_bp,
                  concentracoes=None, grupos=None, raio_cluster=500):
    """Relatório padrão Farol: panorama cartográfico + uma ficha territorial por concentração."""
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),leftMargin=1.15*cm,rightMargin=1.15*cm,
                          topMargin=1.05*cm,bottomMargin=1.05*cm)
    largura=27.4*cm
    styles={
      "titulo":ParagraphStyle("ri3t",fontName="Helvetica-Bold",fontSize=16,leading=20,textColor=colors.HexColor("#193e67"),spaceAfter=8),
      "sub":ParagraphStyle("ri3s",fontName="Helvetica-Bold",fontSize=11,leading=14,textColor=colors.HexColor("#193e67"),spaceBefore=9,spaceAfter=5),
      "p":ParagraphStyle("ri3p",fontName="Helvetica",fontSize=9.1,leading=13,spaceAfter=5),
      "mini":ParagraphStyle("ri3m",fontName="Helvetica",fontSize=7.9,leading=10.5,spaceAfter=3),
      "cel":ParagraphStyle("ri3c",fontName="Helvetica",fontSize=8.1,leading=11),
    }
    def P(valor,sty="p"):
        return Paragraph(escape(str(valor)).replace("\n","<br/>"),styles[sty])
    def tabela(cab,linhas,larguras):
        itens=[[P(c,"cel") for c in cab]]+[[P(str(v),"cel") for v in linha] for linha in linhas]
        tb=Table(itens,colWidths=larguras,repeatRows=1,hAlign="LEFT")
        tb.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dce8f5")),
          ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f6fa")]),
          ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),5),
          ("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),4),
          ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        return tb
    historia=[P("COI | RELATÓRIO OPERACIONAL INTEGRADO", "titulo"),
      P(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}  ·  Fontes: Módulo 1 / Módulo 3"),
      P(f"{n_os} O.S. analisadas  ·  {n_bp} medições  ·  {len(resumo)} concentrações  ·  "
        f"{int((resumo['Medições próximas']>0).sum()) if not resumo.empty else 0} com medições próximas"),
      P("PANORAMA TERRITORIAL", "sub")]
    if concentracoes is not None and not concentracoes.empty:
        mapa=mapa_integrado(concentracoes,associados,raio)
        imagem=imagem_folium(mapa,1250,650)
        historia.append(Image(io.BytesIO(imagem),width=20.5*cm,height=10.66*cm))
        historia.append(Spacer(1,5))
        historia.append(P("Azul: concentração de O.S. · vermelho: pressão até 5 mca · amarelo: 5–10 mca. "
          "Medições de 10–15 mca não aparecem no mapa, conforme regra do Módulo 1.","mini"))
    historia.append(P("LEITURA EXECUTIVA", "sub"))
    for achado in achados:
        historia.append(P("• " + str(achado),"mini"))
    if not resumo.empty:
        historia.append(P("QUADRO DE PRIORIDADES", "sub"))
        linhas=[]
        for _,row in resumo.iterrows():
            linhas.append([row["Concentração"],row["Bairros"],row["O.S."],
                           row["Medições próximas"],row["Medições mesmo bairro"],row["Classificação indicativa"]])
        historia.append(tabela(["Área","Bairros","O.S.","Próximas","Mesmo bairro","Diagnóstico"],linhas,
                               [2.4*cm,7.0*cm,1.4*cm,2.3*cm,2.9*cm,11.4*cm]))
    if not resumo.empty:
        for _,c in resumo.iterrows():
            historia.append(PageBreak())
            id_c=str(c["Concentração"])
            historia.append(P(id_c+" — "+str(c["Município"])+" — "+str(c["Bairros"]),"titulo"))
            grupo=(grupos[grupos["_grupo"]==c["_grupo"]].copy()
                   if grupos is not None and not grupos.empty else pd.DataFrame())
            proximas=(associados[associados["Concentração"]==id_c].copy()
                       if not associados.empty else pd.DataFrame())
            por_bairro=(territoriais[territoriais["Concentração"]==id_c].copy()
                        if not territoriais.empty else pd.DataFrame())
            mapa=mapa_ficha(c,grupo,proximas,raio_cluster)
            imagem=imagem_folium(mapa,780,555)
            mapa_pdf=Image(io.BytesIO(imagem),width=11.25*cm,height=8.0*cm)
            minimo=c.get("Menor pressão (mca)")
            resumo_ficha=[P("RESUMO OPERACIONAL","sub"),
              P(f"Ordens de serviço: {int(c['O.S.'])}  ·  Matrículas distintas: {int(c['Matrículas'])}"),
              P(f"Medições até {raio} m de uma O.S.: {int(c['Medições próximas'])}"),
              P(f"Indícios no mesmo bairro: {int(c['Medições mesmo bairro'])}"),
              P("Menor pressão associada: "+(f"{float(minimo):.1f} mca" if pd.notna(minimo) else "não disponível")),
              P("CLASSIFICAÇÃO INDICATIVA","sub"),P(c["Classificação indicativa"]),
              P("INTERPRETAÇÃO","sub"),P(c["Análise operacional"]),
              P("Mapa: vermelho = O.S.; marcadores de pressão próximos por faixa.","mini")]
            painel=Table([[mapa_pdf,resumo_ficha]],colWidths=[13.7*cm,13.7*cm],hAlign="LEFT")
            painel.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                ("BACKGROUND",(1,0),(1,0),colors.HexColor("#f1f5fa")),
                ("LEFTPADDING",(0,0),(0,0),0), ("RIGHTPADDING",(0,0),(0,0),6),
                ("LEFTPADDING",(1,0),(1,0),12),
                ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
            historia.extend([painel,Spacer(1,6),P("O.S. QUE FORMAM A CONCENTRAÇÃO","sub")])
            if grupo.empty: historia.append(P("Nenhuma O.S. associada nesta execução."))
            else:
                linhas=[]
                for _,os_row in grupo.iterrows():
                    linhas.append([os_row.get("Nº da O.S",""),os_row.get("Matrícula",""),
                         os_row.get("Bairro",""),os_row.get("Dt. Emissão",""),os_row.get("Status OS","")])
                historia.append(tabela(["O.S.","Matrícula","Bairro","Emissão","Status"],linhas,
                              [4.0*cm,4.0*cm,9.0*cm,5.1*cm,5.3*cm]))
            historia.append(P("MEDIÇÕES DE PRESSÃO RELACIONADAS","sub"))
            for titulo,meds,com_distancia in (("Proximidade geográfica",proximas,True),
                                               ("Somente bairro coincidente",por_bairro,False)):
                historia.append(P(titulo+f" ({len(meds)})","mini"))
                if meds.empty:
                    historia.append(P("Nenhuma medição nesta categoria.","mini"))
                    continue
                linhas=[]
                for _,med in meds.iterrows():
                    press=med.get("_pressao")
                    linhas.append([med.get("Data",""),med.get("Bairro",""),
                      f"{float(press):.1f}" if pd.notna(press) else "inválida",
                      (str(med.get("Distância até O.S. (m)",""))+" m") if com_distancia else "Sem proximidade confirmada",
                      str(med.get("Observacao","") or "")])
                historia.append(tabela(["Data","Bairro","mca","Distância / vínculo","Observação"],linhas,
                                     [3.0*cm,5.2*cm,2.0*cm,5.6*cm,11.6*cm]))
            historia.append(P("ENCAMINHAMENTO SUGERIDO","sub"))
            if c["Medições próximas"] and c["Sem/baixa pressão"]:
                msg="Verificar abastecimento e pressão na área das O.S.; conferir eventos operacionais, poços e loggers disponíveis no Farol."
            elif c["Medições próximas"]:
                msg="Confrontar os horários das medições com a abertura das O.S. e avaliar necessidade de nova aferição."
            elif c["Medições mesmo bairro"]:
                msg="Validar endereços e coordenadas; a coincidência por bairro não confirma ocorrência no local das O.S."
            else:
                msg="Avaliar aferição de campo nos endereços reclamantes e consulta aos eventos/ativos do Farol."
            historia.append(P(msg))
            historia.append(P("Associação geográfica ou territorial não comprova causa da reclamação. "
                              "Ausência de medição associada não comprova normalidade.","mini"))
    doc.build(historia)
    return buf.getvalue()

st.title("📊 Relatórios Integrados — Diagnóstico Operacional")
st.caption("Integração analítica entre concentrações de O.S. e registros de pressão · fontes somente leitura")
if st.button("← Voltar ao Hub Central",key="retornar_hub_ri"):
    st.switch_page("app.py")

hoje=date.today()
with st.form("parametros"):
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
            bp=preparar_pressao(ler_base(ID_PRESSAO,"baixa_pressao"))
            os_df=os_df[os_df["_data"].dt.date.between(inicio,fim)].copy()
            bp=bp[bp["_data"].dt.date.between(inicio,fim)].copy()
            if municipio_sel.strip():
                mun=normalizar(municipio_sel)
                os_df=os_df[os_df["_municipio"]==mun]
                bp=bp[bp["_municipio"]==mun]
            concs,grupos=concentracoes_farol(os_df,int(raio_cluster),int(minimo))
            if not concs.empty:
                resumo,associados,territoriais=relacionar(concs,grupos,bp,int(raio_relacao),inicio,fim)
                achados,pressao_sem_conc=diagnostico_geral(resumo,bp,associados,territoriais,inicio,fim)
            else:
                resumo,associados,territoriais=pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
                achados=["Nenhuma concentração atende aos critérios selecionados."]
                pressao_sem_conc=bp.iloc[:0].copy()
            st.session_state["relatorio_coi_integrado"]={"versao_esquema":3,"resumo":resumo,"associados":associados,"territoriais":territoriais,
             "concentracoes":concs,"achados":achados,"pressao_sem_conc":pressao_sem_conc,
             "inicio":inicio,"fim":fim,"raio":int(raio_relacao),"n_os":len(os_df),"n_bp":len(bp),"grupos":grupos,"raio_cluster":int(raio_cluster)}
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
    "pressao_sem_conc", "inicio", "fim", "raio", "n_os", "n_bp"
}
if r is not None and (
    not isinstance(r, dict)
    or r.get("versao_esquema") != 3
    or not _chaves_necessarias.issubset(r)
):
    st.session_state.pop("relatorio_coi_integrado", None)
    r = None
    st.info("O diagnóstico anterior é de uma versão antiga. Clique em **Gerar diagnóstico integrado** para atualizar a análise.")
if r:
    resumo=r["resumo"]
    a,b,c,d=st.columns(4)
    a.metric("O.S. no período",r["n_os"])
    b.metric("Medições no período",r["n_bp"])
    c.metric("Concentrações",len(resumo))
    d.metric("Com medição próxima",int((resumo["Medições próximas"]>0).sum()) if not resumo.empty else 0)
    st.subheader("Análise consolidada")
    for achado in r["achados"]:
        st.write("• " + achado)
    if not resumo.empty:
        st.subheader("Mapa consolidado")
        st.caption("Azul: concentrações | vermelho: medição até 5 mca associada geograficamente | amarelo: 5–10 mca. Medições 10–15 mca continuam ocultas no mapa, conforme regra do Módulo 1. Pontos identificados só por bairro não são desenhados como próximos.")
        mapa=mapa_integrado(r["concentracoes"],r["associados"],r["raio"])
        if mapa is not None:
            st_folium(mapa,height=500,width=None,returned_objects=[],key="mapa_integrado_relatorio")
        st.subheader("Diagnóstico por concentração")
        visiveis=["Concentração","Município","Bairros","O.S.","Matrículas","Medições próximas","Medições mesmo bairro","Sem/baixa pressão","Em atenção (5–10)","Faixa 10–15 (oculta no M1)","Menor pressão (mca)","Classificação indicativa","Análise operacional"]
        st.dataframe(resumo[visiveis],hide_index=True,use_container_width=True)
        if st.button("📄 Preparar relatório cartográfico (PDF)", type="primary", key="gerar_pdf_ri_farol"):
            try:
                with st.spinner("Capturando mapas e montando as fichas operacionais..."):
                    st.session_state["pdf_relatorio_integrado_farol"] = pdf_relatorio(
                        resumo,r["associados"],r["territoriais"],r["achados"],r["inicio"],r["fim"],
                        r["raio"],r["n_os"],r["n_bp"],r["concentracoes"],r["grupos"],r["raio_cluster"])
            except Exception as erro_pdf:
                st.error(f"Não foi possível capturar o mapa para o PDF: {erro_pdf}. "
                         "Confirme a disponibilidade do Playwright/Chromium, como no Farol.")
        if st.session_state.get("pdf_relatorio_integrado_farol"):
            st.download_button("⬇️ Baixar relatório no padrão Farol (PDF)",
                data=st.session_state["pdf_relatorio_integrado_farol"],
                file_name="relatorio_operacional_integrado_coi.pdf",mime="application/pdf")
        st.download_button("📋 Baixar diagnóstico (CSV)",data=resumo[visiveis].to_csv(index=False,sep=";").encode("utf-8-sig"),
            file_name="diagnostico_integrado_coi.csv",mime="text/csv")
        with st.expander("Medições associadas por proximidade geográfica"):
            campos=["Concentração","Data","Municipio","Bairro","Matricula","Pressao_MCA","_faixa","Distância até O.S. (m)","Observacao"]
            st.dataframe(r["associados"][campos] if not r["associados"].empty else pd.DataFrame(columns=campos),hide_index=True,use_container_width=True)
        with st.expander("Indícios apenas pelo mesmo bairro (sem proximidade confirmada)"):
            campos=["Concentração","Data","Municipio","Bairro","Matricula","Pressao_MCA","_faixa","Observacao"]
            st.dataframe(r["territoriais"][campos] if not r["territoriais"].empty else pd.DataFrame(columns=campos),hide_index=True,use_container_width=True)
        if not r["pressao_sem_conc"].empty:
            with st.expander("Medições até 5 mca em bairros sem concentração"):
                st.dataframe(r["pressao_sem_conc"][["Data","Municipio","Bairro","Pressao_MCA","Observacao"]],hide_index=True,use_container_width=True)
else:
    st.info("Selecione o período e clique em **Gerar diagnóstico integrado**. As bases são consultadas somente quando solicitado.")
