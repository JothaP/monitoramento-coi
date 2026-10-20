"""Módulo 7 — Acompanhamento Operacional | Plataforma COI.
Conversão Streamlit do aplicativo Gradio/Colab fornecido pelo usuário.
ATENÇÃO: SQLite em disco local do Streamlit Cloud NÃO garante persistência.
Configure COI_ACOMPANHAMENTO_DB_PATH para um caminho em volume persistente,
ou migre o armazenamento antes de usar dados reais.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF
from auth import verificar_autenticacao, tem_acesso_modulo

st.set_page_config(page_title="Acompanhamento Operacional | COI", page_icon="🌊", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none!important;}</style>", unsafe_allow_html=True)
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Entre pelo Hub Central.")
    st.stop()
if not tem_acesso_modulo("7"):
    st.error("Seu perfil não tem acesso ao Módulo 7.")
    st.stop()

STATUS = ["Aguardando motivo", "Concluído - causa identificada", "Concluído - causa não identificada"]
UNIDADES = ["Águas do Piauí", "Águas de Teresina", "Águas de Timon"]
REGIONAIS = ["Semiárido Norte", "Semiárido Sul", "Cerrado", "Litoral", "Meio Norte", "Teresina", "Timon"]
SIM_NAO = ["Não", "Sim"]
DB_PATH = str(st.secrets.get("COI_ACOMPANHAMENTO_DB_PATH", "cco_monitoramento_v2.db"))

@contextmanager
def conectar():
    caminho = Path(DB_PATH).expanduser()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho), timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def inicializar():
    with conectar() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
            qtd_reclamacoes INTEGER DEFAULT 0, status TEXT NOT NULL,
            ultima_atualizacao TEXT NOT NULL, unidade TEXT NOT NULL,
            regional TEXT NOT NULL, municipio TEXT NOT NULL,
            data_identificacao TEXT NOT NULL, descricao TEXT,
            arcgis TEXT DEFAULT 'Não', sia TEXT DEFAULT 'Não',
            loggers TEXT DEFAULT 'Não', retorno_operacao TEXT DEFAULT 'Não',
            finalizado TEXT DEFAULT 'Não', data_finalizacao TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER NOT NULL,
            data_hora TEXT NOT NULL, descricao TEXT NOT NULL,
            status_momento TEXT NOT NULL,
            FOREIGN KEY(evento_id) REFERENCES eventos(id) ON DELETE CASCADE)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mov_evento ON movimentacoes(evento_id)")

def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def data_texto(valor):
    return valor.strftime("%d/%m/%Y %H:%M") if isinstance(valor, datetime) else str(valor or "").strip()

def cadastrar(titulo, qtd, status, unidade, regional, municipio, data_ident, descricao,
              arcgis, sia, loggers, retorno, finalizado, data_fim):
    if not titulo.strip() or not municipio.strip():
        raise ValueError("Título e município são obrigatórios.")
    momento = agora()
    if "Concluído" in status or finalizado == "Sim":
        finalizado = "Sim"
        data_fim = data_fim or momento
    with conectar() as conn:
        cursor = conn.execute("""INSERT INTO eventos
            (titulo,qtd_reclamacoes,status,ultima_atualizacao,unidade,regional,municipio,
             data_identificacao,descricao,arcgis,sia,loggers,retorno_operacao,finalizado,data_finalizacao)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (titulo.strip(), int(qtd), status, momento, unidade, regional, municipio.strip(),
             data_ident or momento, descricao, arcgis, sia, loggers, retorno, finalizado, data_fim))
        eid = cursor.lastrowid
        conn.execute("INSERT INTO movimentacoes(evento_id,data_hora,descricao,status_momento) VALUES(?,?,?,?)",
                     (eid, momento, f"Registro inicial criado. Relato: {descricao}", status))
    return eid

def listar(status="Todos", municipio="", regional="Todas", unidade="Todas", finalizado="Todos"):
    sql = """SELECT id,titulo,status,municipio,regional,unidade,qtd_reclamacoes,
             ultima_atualizacao,finalizado FROM eventos WHERE 1=1"""
    params = []
    for campo, valor, ignorar in [("status",status,"Todos"),("regional",regional,"Todas"),
                                   ("unidade",unidade,"Todas"),("finalizado",finalizado,"Todos")]:
        if valor != ignorar:
            sql += f" AND {campo}=?"
            params.append(valor)
    if municipio.strip():
        sql += " AND municipio LIKE ?"
        params.append("%" + municipio.strip() + "%")
    sql += " ORDER BY id DESC"
    with conectar() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def obter_evento(eid):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM eventos WHERE id=?", (eid,)).fetchone()
        return dict(r) if r else None

def obter_movimentacoes(eid):
    with conectar() as conn:
        return conn.execute("SELECT data_hora,descricao,status_momento FROM movimentacoes WHERE evento_id=? ORDER BY id", (eid,)).fetchall()

def atualizar(eid, status, observacao, finalizado, data_fim):
    ev = obter_evento(eid)
    if not ev:
        raise ValueError("Evento não encontrado.")
    momento = agora()
    if "Concluído" in status or finalizado == "Sim":
        finalizado = "Sim"
        data_fim = data_fim or momento
    texto = observacao.strip() or f"Status atualizado para: {status}"
    with conectar() as conn:
        conn.execute("UPDATE eventos SET status=?,ultima_atualizacao=?,finalizado=?,data_finalizacao=? WHERE id=?",
                     (status, momento, finalizado, data_fim or None, eid))
        conn.execute("INSERT INTO movimentacoes(evento_id,data_hora,descricao,status_momento) VALUES(?,?,?,?)",
                     (eid, momento, texto, status))

def seguro(texto):
    substituicoes = {'•':'-', '—':'-', '–':'-', '“':'"', '”':'"', '‘':"'", '’':"'", '⚠️':'!', '📌':'', '⏱️':''}
    s = str(texto if texto is not None else "")
    for a, b in substituicoes.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")

class PDFExecutivo(FPDF):
    def header(self):
        self.set_fill_color(26,54,93)
        self.rect(0,0,210,22,"F")
        self.set_font("Helvetica","B",13)
        self.set_text_color(255,255,255)
        self.cell(0,8,"SISTEMA DE MONITORAMENTO OPERACIONAL - COI",align="C",ln=True)
        self.set_font("Helvetica",size=8)
        self.cell(0,4,"Relatorio Executivo de Acompanhamento de Evento",align="C",ln=True)
        self.ln(8)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","I",8)
        self.set_text_color(120,120,120)
        self.cell(0,10,seguro(f"Relatorio gerado em {agora()} - Pagina {self.page_no()}/{{nb}}"),align="C")

def gerar_pdf(eid):
    ev = obter_evento(eid)
    if not ev:
        raise ValueError("Evento não encontrado.")
    movs = obter_movimentacoes(eid)
    pdf = PDFExecutivo()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_fill_color(240,244,248)
    pdf.set_draw_color(200,210,220)
    pdf.rect(10,28,190,22,"DF")
    pdf.set_xy(15,31)
    pdf.set_font("Helvetica","B",11)
    pdf.set_text_color(26,54,93)
    pdf.cell(175,6,seguro(f"EVENTO #{eid}: {ev['titulo']}")[:92],ln=True)
    pdf.set_xy(15,40)
    pdf.set_font("Helvetica",size=9)
    pdf.cell(180,5,seguro(f"Status: {ev['status']} | Ultima atualizacao: {ev['ultima_atualizacao']}"))
    pdf.set_xy(10,55)
    def secao(titulo):
        pdf.set_font("Helvetica","B",11)
        pdf.set_text_color(26,54,93)
        pdf.cell(0,7,seguro(titulo),ln=True)
        pdf.line(10,pdf.get_y(),200,pdf.get_y())
        pdf.ln(4)
        pdf.set_text_color(0,0,0)
    def linha(rotulo, valor):
        pdf.set_font("Helvetica",size=9)
        pdf.multi_cell(0,6,seguro(f"{rotulo}: {valor if valor not in (None,'') else 'N/A'}"))
    secao("1. RESUMO EXECUTIVO")
    for k, label in [("municipio","Municipio"),("regional","Regional"),("unidade","Unidade"),
                     ("qtd_reclamacoes","Qtd. reclamacoes")]:
        linha(label,ev[k])
    pdf.ln(4)
    secao("2. DADOS GERAIS")
    for k,label in [("data_identificacao","Data identificacao"),("status","Status atual"),
                    ("finalizado","Finalizado"),("data_finalizacao","Data finalizacao")]:
        linha(label,ev[k])
    pdf.ln(4)
    secao("3. VALIDACOES OPERACIONAIS")
    for k,label in [("arcgis","Evento no ArcGIS"),("sia","Evento no SIA"),
                    ("loggers","Loggers validados"),("retorno_operacao","Retorno Operacao/Controle")]:
        linha(label,ev[k])
    pdf.add_page()
    secao("4. DESCRICAO DETALHADA DA OCORRENCIA")
    linha("Relato",ev["descricao"] or "Nenhuma descricao informada")
    pdf.ln(6)
    secao("5. HISTORICO DE MOVIMENTACOES")
    for data, desc, status in movs:
        if pdf.get_y() > 257:
            pdf.add_page()
        pdf.set_font("Helvetica","B",9)
        pdf.set_text_color(26,54,93)
        pdf.multi_cell(0,5,seguro(f"{data} - Status: {status}"))
        pdf.set_font("Helvetica",size=9)
        pdf.set_text_color(50,50,50)
        pdf.multi_cell(0,5,seguro(desc))
        pdf.ln(4)
    resultado = pdf.output(dest="S")
    return bytes(resultado) if not isinstance(resultado,str) else resultado.encode("latin-1")

try:
    inicializar()
except (sqlite3.Error, OSError) as exc:
    st.error(f"Não foi possível abrir o banco de dados: {exc}")
    st.stop()

st.title("🌊 Módulo 7 — Acompanhamento Operacional")
st.caption("Plataforma COI | Registro, acompanhamento de anomalias e relatórios executivos")
with st.sidebar:
    st.markdown("### Navegação")
    if st.button("← Voltar ao Hub Central", use_container_width=True):
        st.switch_page("app.py")
    st.divider()
    st.caption("Armazenamento atual: SQLite. Para produção no Streamlit Cloud, configure armazenamento persistente.")

aba_novo, aba_consulta = st.tabs(["📝 Novo Registro Operacional", "🔍 Consulta, Histórico e PDF"])
with aba_novo:
    with st.form("form_novo_evento", clear_on_submit=False):
        c1,c2,c3 = st.columns([2,1,2])
        titulo = c1.text_input("Título do Acompanhamento", placeholder="Ex.: Rompimento de rede Parnaíba")
        qtd = c2.number_input("Nº de Reclamações",min_value=0,value=0,step=1)
        status = c3.selectbox("Status",STATUS)
        c1,c2,c3 = st.columns(3)
        unidade = c1.selectbox("Unidade",UNIDADES)
        regional = c2.selectbox("Regional",REGIONAIS,index=2)
        municipio = c3.text_input("Município")
        c1,c2,c3 = st.columns(3)
        ident_auto = c1.checkbox("Identificação automática",value=True)
        data_ident = c1.text_input("Data de Identificação (DD/MM/AAAA HH:MM)",disabled=ident_auto)
        finalizado = c2.radio("Finalizado?",SIM_NAO,horizontal=True)
        data_fim = c3.text_input("Data de Finalização (DD/MM/AAAA HH:MM)")
        descricao = st.text_area("Descrição / Relato Inicial",height=110)
        st.markdown("#### Validações de Sistemas")
        c1,c2,c3,c4 = st.columns(4)
        arcgis = c1.radio("Evento registrado no ArcGIS?",SIM_NAO,horizontal=True)
        sia = c2.radio("Evento registrado no SIA?",SIM_NAO,horizontal=True)
        loggers = c3.radio("Loggers validados?",SIM_NAO,horizontal=True)
        retorno = c4.radio("Retorno Operação/Controle?",SIM_NAO,horizontal=True)
        salvar = st.form_submit_button("🚀 Cadastrar Ação Operacional",type="primary")
    if salvar:
        try:
            eid = cadastrar(titulo,qtd,status,unidade,regional,municipio,
                            "" if ident_auto else data_ident.strip(),descricao,arcgis,sia,loggers,retorno,
                            finalizado,data_fim.strip())
            st.success(f"Evento #{eid} registrado com sucesso!")
        except (ValueError,sqlite3.Error) as exc:
            st.error(str(exc))

with aba_consulta:
    st.markdown("### Filtros de Pesquisa")
    with st.form("filtros_consulta"):
        c1,c2,c3,c4,c5 = st.columns(5)
        f_status = c1.selectbox("Status",["Todos"]+STATUS)
        f_uni = c2.selectbox("Unidade",["Todas"]+UNIDADES)
        f_reg = c3.selectbox("Regional",["Todas"]+REGIONAIS)
        f_fin = c4.selectbox("Finalizado",["Todos","Sim","Não"])
        f_mun = c5.text_input("Município")
        aplicar = st.form_submit_button("🔍 Aplicar Filtros")
    if aplicar or "filtros_acomp" not in st.session_state:
        st.session_state.filtros_acomp = (f_status,f_mun,f_reg,f_uni,f_fin)
    df = listar(*st.session_state.filtros_acomp)
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.caption(f"{len(df)} evento(s) encontrado(s)")
    st.divider()
    st.markdown("### ⚙️ Gestão de Evento Selecionado")
    todos = listar()
    if todos.empty:
        st.info("Nenhum evento cadastrado ainda.")
    else:
        opcoes = {f"#{int(r.id)} - {r.titulo} ({r.municipio})":int(r.id) for r in todos.itertuples()}
        escolhido = st.selectbox("Selecione o Evento para Gerenciar",list(opcoes),key="acomp_evento_selecionado")
        eid = opcoes[escolhido]
        ev = obter_evento(eid)
        if ev:
            st.info(f"📌 {ev['titulo']} | {ev['status']} | {ev['municipio']} | Reclamações: {ev['qtd_reclamacoes']} | Última atualização: {ev['ultima_atualizacao']}")
            c1,c2 = st.columns([1,2])
            with c1:
                try:
                    pdf_bytes = gerar_pdf(eid)
                    st.download_button("📄 Baixar Relatório PDF Executivo",data=pdf_bytes,
                                       file_name=f"Relatorio_Executivo_COI_{eid}.pdf",mime="application/pdf",
                                       use_container_width=True)
                except Exception as exc:
                    st.error(f"Falha ao gerar PDF: {exc}")
            with c2:
                st.markdown("#### Histórico de Movimentações")
                for dt, desc, stat in obter_movimentacoes(eid):
                    st.markdown(f"**⏱️ {dt} — {stat}**")
                    st.write(desc)
            st.markdown("#### Registrar Nova Movimentação / Atualização")
            with st.form(f"atualizar_evento_{eid}"):
                c1,c2,c3 = st.columns(3)
                novo_status = c1.selectbox("Novo Status",STATUS,index=STATUS.index(ev["status"]) if ev["status"] in STATUS else 0)
                fin_atual = c2.radio("Finalizado?",SIM_NAO,index=1 if ev["finalizado"]=="Sim" else 0,horizontal=True)
                data_fim_atual = c3.text_input("Data Finalização",value=ev["data_finalizacao"] or "")
                observacao = st.text_area("Descrição da Nova Atualização Operacional")
                gravar = st.form_submit_button("➕ Salvar Movimentação",type="primary")
            if gravar:
                try:
                    atualizar(eid,novo_status,observacao,fin_atual,data_fim_atual.strip())
                    st.success(f"Evento #{eid} atualizado com sucesso!")
                    st.rerun()
                except (ValueError,sqlite3.Error) as exc:
                    st.error(str(exc))
