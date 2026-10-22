"""Módulo 7 — Relatórios Integrados COI.
Leitura exclusiva de Módulo 1 (baixa_pressao) e Módulo 3 (PONTOS).
Não importa os módulos interativos: reproduz o algoritmo espacial do Farol.
"""
import io
import json
import math
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
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

def pdf_relatorio(resumo, associados, territoriais, achados, inicio, fim, raio, n_os, n_bp):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=1.15*cm,leftMargin=1.15*cm,topMargin=1*cm,bottomMargin=1*cm)
    styles = {
      "titulo":ParagraphStyle("titulo_ri",fontName="Helvetica-Bold",fontSize=15,leading=19,textColor=colors.HexColor("#163b61"),spaceAfter=9),
      "sub":ParagraphStyle("sub_ri",fontName="Helvetica-Bold",fontSize=10,leading=13,textColor=colors.HexColor("#163b61"),spaceBefore=10,spaceAfter=5),
      "p":ParagraphStyle("p_ri",fontName="Helvetica",fontSize=9,leading=12,spaceAfter=5),
      "cell":ParagraphStyle("cell_ri",fontName="Helvetica",fontSize=7.8,leading=10),
    }
    p=lambda v,sty="p":Paragraph(escape(str(v)),styles[sty])
    historia=[p("RELATÓRIO INTEGRADO — DIAGNÓSTICO OPERACIONAL","titulo"),
       p(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} | Distância máxima a uma O.S.: {raio} m | Fontes: Módulos 1 e 3"),
       p(f"O.S. no período: {n_os} | Medições: {n_bp} | Concentrações: {len(resumo)} | Com medição próxima: {int((resumo['Medições próximas']>0).sum()) if not resumo.empty else 0}"),
       p("ANÁLISE CONSOLIDADA","sub")]
    for a in achados:
        historia.append(p("• " + a))
    historia.append(p("DIAGNÓSTICO POR CONCENTRAÇÃO","sub"))
    cab=["Concentração / bairro(s)","O.S.","Medições até raio","Mesmo bairro*","Mín. mca","Situação"]
    tabela=[[p(c,"cell") for c in cab]]
    for _,r in resumo.iterrows():
        val=r["Menor pressão (mca)"]
        txt=f"{r['Concentração']} — {r['Bairros']}"
        linha=[txt, r["O.S."],r["Medições próximas"],r["Medições mesmo bairro"],f"{float(val):.1f}" if pd.notna(val) else "—",r["Classificação indicativa"]]
        tabela.append([p(v,"cell") for v in linha])
    tab=Table(tabela,colWidths=[10.3*cm,1.2*cm,2.65*cm,2.55*cm,1.8*cm,7.4*cm],repeatRows=1,hAlign="LEFT")
    tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#deebf5")),("VALIGN",(0,0),(-1,-1),"TOP"),
       ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f5f9")]),("BOTTOMPADDING",(0,0),(-1,-1),6),
       ("TOPPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5)]))
    historia.append(tab)
    historia.extend([Spacer(1,7),p("* Mesmo bairro: não há confirmação de proximidade com a O.S. e não deve ser somado às medições geográficas."),
       p("Regra de visualização do Módulo 1 preservada: 10–15 mca não é exibido no mapa; valores válidos permanecem nos dados de análise."),
       p("Associação no mesmo dia/intervalo ou bairro não comprova causalidade. A ausência de medição não comprova pressão normal.")])
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
            st.session_state["relatorio_coi_integrado"]={"resumo":resumo,"associados":associados,"territoriais":territoriais,
             "concentracoes":concs,"achados":achados,"pressao_sem_conc":pressao_sem_conc,
             "inicio":inicio,"fim":fim,"raio":int(raio_relacao),"n_os":len(os_df),"n_bp":len(bp)}
    except gspread.exceptions.APIError as ex:
        codigo=getattr(getattr(ex,"response",None),"status_code",None)
        st.error("Quota temporária do Google Sheets excedida (429)." if codigo==429 else f"Falha na consulta às fontes (HTTP {codigo or 'desconhecido'}).")
        st.stop()
    except Exception as ex:
        st.error(f"Falha ao preparar relatório: {ex}")
        st.stop()

r=st.session_state.get("relatorio_coi_integrado")
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
        st.download_button("📄 Baixar diagnóstico integrado (PDF)",
            data=pdf_relatorio(resumo,r["associados"],r["territoriais"],r["achados"],r["inicio"],r["fim"],r["raio"],r["n_os"],r["n_bp"]),
            file_name="diagnostico_integrado_coi.pdf",mime="application/pdf")
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
