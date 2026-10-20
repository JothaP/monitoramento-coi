"""Módulo 7 — Acompanhamento Operacional | Plataforma COI.
Conversão Streamlit do aplicativo Gradio/Colab fornecido pelo usuário.
Persistência: Google Sheets dedicado, separado dos demais módulos.
"""
import json
import threading
import time
import random
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from fpdf import FPDF
from integracao_acompanhamento_producao import registrar_vinculo as registrar_vinculo_producao


STATUS = ["Aguardando motivo", "Concluído - causa identificada", "Concluído - causa não identificada"]
UNIDADES = ["Águas do Piauí", "Águas de Teresina", "Águas de Timon"]
REGIONAIS = ["Semiárido Norte", "Semiárido Sul", "Cerrado", "Litoral", "Meio Norte", "Teresina", "Timon"]
SIM_NAO = ["Não", "Sim"]
SPREADSHEET_ID = str(st.secrets.get("acompanhamento_operacional_spreadsheet_id", "")).strip()
CAMPOS_EVENTOS = ["id", "titulo", "qtd_reclamacoes", "status", "ultima_atualizacao", "unidade", "regional", "municipio", "data_identificacao", "descricao", "arcgis", "sia", "loggers", "retorno_operacao", "finalizado", "data_finalizacao"]
CAMPOS_MOVIMENTACOES = ["id", "evento_id", "data_hora", "descricao", "status_momento"]
# Protege gravações concorrentes dentro de um mesmo processo Streamlit.
_GRAVACAO_LOCK = threading.RLock()

@st.cache_resource(show_spinner=False)
def cliente_google():
    dados = st.secrets["gcp_json"]
    dados = json.loads(dados) if isinstance(dados, str) else dict(dados)
    credenciais = Credentials.from_service_account_info(dados, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    return gspread.authorize(credenciais)

@st.cache_resource(show_spinner=False)
def planilha_google():
    return cliente_google().open_by_key(SPREADSHEET_ID)

@st.cache_resource(show_spinner=False)
def aba_google(nome):
    planilha = planilha_google()
    colunas = CAMPOS_EVENTOS if nome == "eventos" else CAMPOS_MOVIMENTACOES
    try:
        aba = planilha.worksheet(nome)
    except gspread.WorksheetNotFound:
        aba = planilha.add_worksheet(title=nome, rows=1000, cols=len(colunas))
    primeira = aba.row_values(1)
    if not primeira:
        aba.update(range_name="A1", values=[colunas])
    elif primeira != colunas:
        raise ValueError(f"A aba '{nome}' possui cabeçalhos diferentes dos esperados. Faça backup e confira a estrutura antes de continuar.")
    return aba

@st.cache_data(ttl=20, show_spinner=False)
def ler_registros(nome):
    """Evita leituras repetidas no mesmo rerun e faz retentativas apenas em falhas transitórias."""
    aba = aba_google(nome)
    colunas = CAMPOS_EVENTOS if nome == "eventos" else CAMPOS_MOVIMENTACOES
    for tentativa in range(4):
        try:
            linhas = aba.get_all_values()
            return [dict(zip(colunas, (linha + [""] * len(colunas))[:len(colunas)]))
                    for linha in linhas[1:] if linha and str(linha[0]).strip()]
        except gspread.exceptions.APIError as erro:
            codigo = getattr(getattr(erro, "response", None), "status_code", None)
            if codigo not in (429, 500, 502, 503, 504) or tentativa == 3:
                raise
            time.sleep(min(2 ** tentativa + random.uniform(0, 0.5), 8))


def novo_id(registros):
    return max((int(r["id"]) for r in registros if str(r.get("id", "")).isdigit()), default=0) + 1

def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")

def cadastrar(titulo, qtd, status, unidade, regional, municipio, data_ident, descricao,
              arcgis, sia, loggers, retorno, finalizado, data_fim):
    if not titulo.strip() or not municipio.strip():
        raise ValueError("Título e município são obrigatórios.")
    momento = agora()
    if "Concluído" in status or finalizado == "Sim":
        finalizado = "Sim"
        data_fim = data_fim or momento
    with _GRAVACAO_LOCK:
        ev_aba = aba_google("eventos")
        mov_aba = aba_google("movimentacoes")
        eid = novo_id(ler_registros("eventos"))
        mid = novo_id(ler_registros("movimentacoes"))
        dados = [eid, titulo.strip(), int(qtd), status, momento, unidade, regional, municipio.strip(),
                 data_ident or momento, descricao, arcgis, sia, loggers, retorno, finalizado, data_fim]
        ev_aba.append_row(dados, value_input_option="RAW")
        mov_aba.append_row([mid, eid, momento, f"Registro inicial criado. Relato: {descricao}", status], value_input_option="RAW")
        ler_registros.clear()
    return eid

def listar(status="Todos", municipio="", regional="Todas", unidade="Todas", finalizado="Todos"):
    df = pd.DataFrame(ler_registros("eventos"), columns=CAMPOS_EVENTOS)
    colunas = ["id", "titulo", "status", "municipio", "regional", "unidade", "qtd_reclamacoes", "ultima_atualizacao", "finalizado"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    for campo, valor, ignorar in [("status",status,"Todos"),("regional",regional,"Todas"),
                                   ("unidade",unidade,"Todas"),("finalizado",finalizado,"Todos")]:
        if valor != ignorar:
            df = df[df[campo] == valor]
    if municipio.strip():
        df = df[df["municipio"].str.contains(municipio.strip(), case=False, regex=False, na=False)]
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["qtd_reclamacoes"] = pd.to_numeric(df["qtd_reclamacoes"], errors="coerce").fillna(0).astype(int)
    return df.sort_values("id", ascending=False)[colunas].reset_index(drop=True)

def obter_evento(eid):
    return next((r for r in ler_registros("eventos") if str(r["id"]) == str(eid)), None)

def obter_movimentacoes(eid):
    rows = [r for r in ler_registros("movimentacoes") if str(r["evento_id"]) == str(eid)]
    rows.sort(key=lambda r: int(r["id"]) if str(r["id"]).isdigit() else 0)
    return [(r["data_hora"], r["descricao"], r["status_momento"]) for r in rows]

def atualizar(eid, status, observacao, finalizado, data_fim):
    momento = agora()
    if "Concluído" in status or finalizado == "Sim":
        finalizado = "Sim"
        data_fim = data_fim or momento
    texto = observacao.strip() or f"Status atualizado para: {status}"
    with _GRAVACAO_LOCK:
        aba = aba_google("eventos")
        ids_coluna = aba.col_values(1)
        linhas_exatas = [i for i, valor in enumerate(ids_coluna, start=1) if i > 1 and str(valor).strip() == str(eid)]
        if len(linhas_exatas) != 1:
            raise ValueError("Evento não encontrado ou ID duplicado.")
        numero_linha = linhas_exatas[0]
        # Atualiza o intervalo D:E (status e data da última atualização) e O:P (finalização).
        aba.batch_update([
            {"range": f"D{numero_linha}:E{numero_linha}", "values": [[status, momento]]},
            {"range": f"O{numero_linha}:P{numero_linha}", "values": [[finalizado, data_fim or ""]]},
        ], value_input_option="RAW")
        mov_aba = aba_google("movimentacoes")
        mid = novo_id(ler_registros("movimentacoes"))
        mov_aba.append_row([mid, eid, momento, texto, status], value_input_option="RAW")
        ler_registros.clear()

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


def renderizar_acompanhamento_farol(pode_editar=True):
    """Ficha integrada ao Módulo 3, sem navegação para uma página separada."""
    if not SPREADSHEET_ID or SPREADSHEET_ID == str(st.secrets.get("farol_producao_spreadsheet_id", "")).strip():
        st.error("Configure a planilha de acompanhamento separadamente da planilha do Farol.")
        return
    if not pode_editar:
        st.warning("Seu perfil possui acesso somente de leitura.")
        st.stop()
    try:
        aba_google("eventos")
        aba_google("movimentacoes")
    except Exception as exc:
        st.error(f"Não foi possível acessar a planilha do Módulo 7: {exc}")
        st.info("Confira o Secret gcp_json, o compartilhamento com a conta de serviço e o ID da planilha.")
        st.stop()

    contexto_farol = st.session_state.get("acomp_farol_contexto")
    if contexto_farol:
        st.info(f"Farol Operacional · {contexto_farol['codigo']} · {contexto_farol['municipio']} · {contexto_farol['bairros']}")
        if st.button("← Voltar à análise das concentrações"):
            st.session_state.pop("acomp_farol_contexto", None)
            st.session_state.pop("farol_exibir_acompanhamento", None)
            st.rerun()

    st.title("🌊 Acompanhamento Operacional — Farol")
    st.caption("Plataforma COI | Registro, acompanhamento de anomalias e relatórios executivos")
    with st.sidebar:
        st.markdown("### Navegação")
        if st.button("← Voltar ao Hub Central", use_container_width=True):
            st.session_state.pop("farol_exibir_acompanhamento", None)
            st.session_state.pop("acomp_farol_contexto", None)
            st.rerun()
        st.divider()
        st.caption("Armazenamento: Google Sheets exclusivo do Acompanhamento Operacional.")

    aba_novo, aba_consulta = st.tabs(["📝 Novo Registro Operacional", "🔍 Consulta, Histórico e PDF"])
    with aba_novo:
        with st.form("form_novo_evento", clear_on_submit=False):
            c1,c2,c3 = st.columns([2,1,2])
            titulo = c1.text_input("Título do Acompanhamento", value=(f"{contexto_farol['codigo']} — {contexto_farol['municipio']} — {contexto_farol['bairros']}" if contexto_farol and not contexto_farol.get("evento_id") else ""), placeholder="Ex.: Rompimento de rede Parnaíba")
            qtd = c2.number_input("Nº de Reclamações",min_value=0,value=int(contexto_farol["qtd"]) if contexto_farol and not contexto_farol.get("evento_id") else 0,step=1)
            status = c3.selectbox("Status",STATUS)
            c1,c2,c3 = st.columns(3)
            unidade = c1.selectbox("Unidade",UNIDADES)
            regional = c2.selectbox("Regional",REGIONAIS,index=2)
            municipio = c3.text_input("Município", value=contexto_farol["municipio"] if contexto_farol and not contexto_farol.get("evento_id") else "")
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
                if contexto_farol and contexto_farol.get("evento_id"):
                    raise ValueError("Esta concentração já possui ficha. Utilize a aba Consulta, Histórico e PDF.")
                eid = cadastrar(titulo,qtd,status,unidade,regional,municipio,
                                "" if ident_auto else data_ident.strip(),descricao,arcgis,sia,loggers,retorno,
                                finalizado,data_fim.strip())
                if contexto_farol:
                    registrar_vinculo_producao(contexto_farol, eid)
                    st.session_state["acomp_farol_contexto"]["evento_id"] = str(eid)
                st.success(f"Evento #{eid} registrado com sucesso!")
            except (ValueError, gspread.exceptions.GSpreadException) as exc:
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
            opcoes_lista = list(opcoes)
            id_contexto = str(contexto_farol.get("evento_id", "")) if contexto_farol else ""
            indice_contexto = next((i for i, rotulo in enumerate(opcoes_lista) if str(opcoes[rotulo]) == id_contexto), 0)
            escolhido = st.selectbox("Selecione o Evento para Gerenciar", opcoes_lista, index=indice_contexto, key="acomp_evento_selecionado")
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
                    except (ValueError, gspread.exceptions.GSpreadException) as exc:
                        st.error(str(exc))
