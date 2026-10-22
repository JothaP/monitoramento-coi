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
                if j > i and haversine(df.at[i,"_lat"],df.at[i,"_lon"],df.at[j,"_lat"],df.at[j,"_lon"]) <= raio_m:
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
    """Só une dados de mesma cidade e período; proximidade isolada não demonstra causalidade."""
    resultados=[]
    relevantes=[]
    pressao=pressao[pressao["_data"].dt.date.between(inicio,fim)].copy()
    pressao=pressao.dropna(subset=["_lat","_lon"])
    for _,c in concs.iterrows():
        os_grupo=os_cluster[os_cluster["_grupo"]==c["_grupo"]]
        cidades=set(os_grupo["_municipio"])
        candidatos=pressao[pressao["_municipio"].isin(cidades)].copy()
        if not candidatos.empty:
            candidatos["Distância (m)"]=candidatos.apply(
                lambda r: round(haversine(float(c["Latitude"]),float(c["Longitude"]),r["_lat"],r["_lon"])),axis=1)
            candidatos=candidatos[candidatos["Distância (m)"]<=raio].copy()
        criticos=candidatos[candidatos["_pressao"].notna() & (candidatos["_pressao"]<=5)]
        atencao=candidatos[candidatos["_pressao"].notna() & (candidatos["_pressao"]>5) & (candidatos["_pressao"]<=10)]
        ocultos=candidatos[candidatos["_pressao"].notna() & (candidatos["_pressao"]>10) & (candidatos["_pressao"]<=15)]
        # Rótulo de prioridade é INDICATIVO; confirmar na operação.
        prioridade=("Alta — medição ≤ 5 mca" if len(criticos) else
                    "Moderada — medição 5–10 mca" if len(atencao) else
                    "Sem confirmação de pressão crítica")
        resultados.append({**c.to_dict(), "Medições próximas":len(candidatos),
                           "Sem/baixa pressão":len(criticos), "Em atenção (5–10)":len(atencao),
                           "Faixa 10–15 (oculta no M1)":len(ocultos),
                           "Menor pressão (mca)":min(candidatos["_pressao"].dropna()) if candidatos["_pressao"].notna().any() else None,
                           "Classificação indicativa":prioridade})
        if not candidatos.empty:
            candidatos.insert(0,"Concentração",c["Concentração"])
            relevantes.append(candidatos)
    return pd.DataFrame(resultados),pd.concat(relevantes,ignore_index=True) if relevantes else pressao.iloc[:0].copy()

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

def pdf_relatorio(resumo, associados, inicio, fim, raio, n_os, n_bp):
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=1.25*cm,leftMargin=1.25*cm,topMargin=1.1*cm,bottomMargin=1.1*cm)
    styles={
       "titulo":ParagraphStyle("titulo",fontName="Helvetica-Bold",fontSize=16,leading=20,textColor=colors.HexColor("#14365b"),spaceAfter=10),
       "sub":ParagraphStyle("sub",fontName="Helvetica-Bold",fontSize=10,leading=13,textColor=colors.HexColor("#14365b"),spaceBefore=12,spaceAfter=6),
       "p":ParagraphStyle("p",fontName="Helvetica",fontSize=8.5,leading=12,spaceAfter=4),
       "cell":ParagraphStyle("cell",fontName="Helvetica",fontSize=7.5,leading=9.5),
    }
    story=[Paragraph("RELATÓRIO INTEGRADO — CONCENTRAÇÕES E PRESSÃO",styles["titulo"]),
           Paragraph(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}  |  Raio de associação: {raio} m  |  Fonte: Módulos 1 e 3",styles["p"]),
           Paragraph(f"O.S. analisadas: {n_os}  |  Medições no período: {n_bp}  |  Concentrações: {len(resumo)}  |  Com medição até 5 mca: {int((resumo['Sem/baixa pressão']>0).sum()) if not resumo.empty else 0}",styles["p"]),
           Paragraph("Concentrações e medições associadas",styles["sub"])]
    headers=["Concentração","Município / bairros","O.S.","Medições","≤5 mca","5–10 mca","10–15 mca*","Mín. (mca)"]
    data=[[Paragraph(escape(x),styles["cell"]) for x in headers]]
    for _,r in resumo.iterrows():
        info=f"{r['Município']} — {r['Bairros']}"
        valor=r["Menor pressão (mca)"]
        minimo=f"{float(valor):.1f}" if pd.notna(valor) else "—"
        raw=[r["Concentração"],info,r["O.S."],r["Medições próximas"],r["Sem/baixa pressão"],r["Em atenção (5–10)"],r["Faixa 10–15 (oculta no M1)"],minimo]
        data.append([Paragraph(escape(str(x)),styles["cell"]) for x in raw])
    widths=[2.6*cm,10.9*cm,1.25*cm,1.6*cm,1.45*cm,1.65*cm,1.75*cm,1.8*cm]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dce8f5")),
                           ("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),.5,colors.HexColor("#9fb6ca")),
                           ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f6fa")]),
                           ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
                           ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [t,Spacer(1,8),Paragraph("* Medições de 10 a 15 mca contabilizadas para análise, mas ocultas no mapa do Módulo 1. Não representam confirmação de causa das reclamações.",styles["p"]),
              Paragraph("Nota: coincidência espacial e temporal indica associação, não prova causalidade. Registros sem coordenadas válidas não são associados geograficamente.",styles["p"])]
    doc.build(story)
    return buf.getvalue()

st.title("📊 Relatórios Integrados — Concentrações e Baixa Pressão")
st.caption("Leitura consolidada dos Módulos 1 e 3 · sem alterações nas planilhas de origem")
hoje=date.today()
with st.form("parametros"):
    a,b,c,d=st.columns(4)
    with a: inicio=st.date_input("Data inicial",value=hoje-timedelta(days=7),format="DD/MM/YYYY")
    with b: fim=st.date_input("Data final",value=hoje,format="DD/MM/YYYY")
    with c: raio_cluster=st.number_input("Raio das concentrações (m)",min_value=100,max_value=3000,value=500,step=100)
    with d: minimo=st.number_input("Mínimo de O.S.",min_value=2,max_value=30,value=2)
    e,f=st.columns(2)
    with e: raio_relacao=st.number_input("Raio para associar pressão (m)",min_value=50,max_value=3000,value=500,step=50)
    with f: municipio_sel=st.text_input("Município (opcional)",placeholder="Todos os municípios")
    executar=st.form_submit_button("Gerar relatório integrado",type="primary",use_container_width=True)
if executar:
    if inicio>fim:
        st.error("A data inicial não pode ser posterior à data final.")
        st.stop()
    try:
        with st.spinner("Consultando bases do Módulo 1 e do Farol..."):
            bruto_os=ler_base(ID_FAROL,"PONTOS")
            bruto_pressao=ler_base(ID_PRESSAO,"baixa_pressao")
            os_df=preparar_os(bruto_os)
            bp=preparar_pressao(bruto_pressao)
            os_df=os_df[os_df["_data"].dt.date.between(inicio,fim)].copy()
            bp=bp[bp["_data"].dt.date.between(inicio,fim)].copy()
            if municipio_sel.strip():
                mun=normalizar(municipio_sel)
                os_df=os_df[os_df["_municipio"]==mun]
                bp=bp[bp["_municipio"]==mun]
            concs,grupos=concentracoes_farol(os_df,int(raio_cluster),int(minimo))
            resumo,associados=relacionar(concs,grupos,bp,int(raio_relacao),inicio,fim) if not concs.empty else (pd.DataFrame(),pd.DataFrame())
            st.session_state["relatorio_coi_integrado"]={"resumo":resumo,"associados":associados,"concentracoes":concs,"inicio":inicio,"fim":fim,"raio":int(raio_relacao),"n_os":len(os_df),"n_bp":len(bp)}
    except gspread.exceptions.APIError as ex:
        codigo=getattr(getattr(ex,"response",None),"status_code",None)
        if codigo==429: st.error("Google Sheets retornou erro 429 (limite de leituras). Aguarde a renovação da quota e tente novamente; as bases permanecem intactas.")
        else: st.error(f"Não foi possível ler as planilhas (HTTP {codigo or 'desconhecido'}). Confira permissões e IDs.")
        st.stop()
    except Exception as ex:
        st.error(f"Falha ao preparar relatório: {ex}")
        st.stop()

r=st.session_state.get("relatorio_coi_integrado")
if r:
    resumo=r["resumo"]
    a,b,c,d=st.columns(4)
    a.metric("O.S. analisadas",r["n_os"])
    b.metric("Medições de pressão",r["n_bp"])
    c.metric("Concentrações",len(resumo))
    d.metric("Concentrações com ≤ 5 mca",int((resumo["Sem/baixa pressão"]>0).sum()) if not resumo.empty else 0)
    if resumo.empty:
        st.info("Nenhuma concentração atende aos critérios selecionados.")
    else:
        st.subheader("Mapa consolidado")
        st.caption("Marcadores azuis: concentrações · vermelho: pressão até 5 mca · amarelo: 5 a 10 mca · cinza: acima de 15 mca ou inválidos. Assim como no Módulo 1, os pontos de 10 a 15 mca são contabilizados, mas não desenhados no mapa.")
        mapa=mapa_integrado(r["concentracoes"],r["associados"],r["raio"])
        if mapa is not None: st_folium(mapa,height=500,width=None,returned_objects=[],key="mapa_integrado_relatorio")
        st.subheader("Diagnóstico por concentração")
        visiveis=["Concentração","Município","Bairros","O.S.","Matrículas","Medições próximas","Sem/baixa pressão","Em atenção (5–10)","Faixa 10–15 (oculta no M1)","Menor pressão (mca)","Classificação indicativa"]
        st.dataframe(resumo[visiveis],hide_index=True,use_container_width=True)
        st.download_button("📄 Baixar relatório consolidado (PDF)",data=pdf_relatorio(resumo,r["associados"],r["inicio"],r["fim"],r["raio"],r["n_os"],r["n_bp"]),
                           file_name="relatorio_integrado_coi.pdf",mime="application/pdf")
        st.download_button("📋 Baixar tabela consolidada (CSV)",data=resumo[visiveis].to_csv(index=False,sep=";").encode("utf-8-sig"),
                           file_name="relatorio_integrado_coi.csv",mime="text/csv")
        with st.expander("Consultar medições associadas"):
            detalhes=r["associados"]
            campos=["Concentração","Data","Municipio","Bairro","Matricula","Pressao_MCA","_faixa","Distância (m)","Observacao"]
            st.dataframe(detalhes[campos] if not detalhes.empty else pd.DataFrame(columns=campos),hide_index=True,use_container_width=True)
else:
    st.info("Selecione um período e clique em **Gerar relatório integrado**. As planilhas serão consultadas apenas quando solicitado.")
