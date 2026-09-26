import io
import re

import pandas as pd
import streamlit as st

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Ferramentas Adicionais - COI",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SIDEBAR
# ============================================================

if "modo_escuro_ferramentas" not in st.session_state:
    st.session_state["modo_escuro_ferramentas"] = False

with st.sidebar:
    st.markdown("## ⚙️ Opções")

    modo_escuro = st.toggle(
        "🌙 Modo escuro",
        value=st.session_state["modo_escuro_ferramentas"],
        key="toggle_modo_escuro_ferramentas",
    )

    if modo_escuro != st.session_state["modo_escuro_ferramentas"]:
        st.session_state["modo_escuro_ferramentas"] = modo_escuro
        st.rerun()

    st.divider()

    if st.button(
        "🏢 Voltar ao Hub Central",
        key="voltar_hub_sidebar_ferramentas",
        use_container_width=True,
    ):
        st.switch_page("app.py")


# ============================================================
# AUTENTICAÇÃO
# ============================================================

verificar_autenticacao()

if not st.session_state.get("autenticado"):
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("🔐 Ir para o login", key="ir_login_ferramentas", use_container_width=True):
        st.switch_page("app.py")
    st.stop()

if st.session_state.get("perfil") != "admin":
    st.error("Este módulo é restrito a administradores.")
    if st.button("↩️ Voltar ao Hub", key="voltar_hub_restrito_ferramentas", use_container_width=True):
        st.switch_page("app.py")
    st.stop()


# ============================================================
# ESTILO
# ============================================================

if st.session_state.get("modo_escuro_ferramentas"):
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { background-color: #0e1117; }
        [data-testid="stHeader"] { background-color: #0e1117; }
        [data-testid="stSidebar"] { background-color: #161b22; }
        [data-testid="stSidebar"] * { color: #f0f2f6; }
        .secao-ferramentas p { color: #b8c0cc !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <style>
    .titulo-ferramentas {
        background: linear-gradient(135deg, #17365D, #1F4E78);
        color: white;
        padding: 22px 26px;
        border-radius: 14px;
        margin-bottom: 24px;
    }
    .titulo-ferramentas h1 {
        margin: 0;
        font-size: 28px;
        font-weight: 700;
    }
    .titulo-ferramentas p {
        margin: 7px 0 0 0;
        font-size: 14px;
        opacity: 0.92;
    }
    .secao-ferramentas {
        margin-top: 10px;
        margin-bottom: 12px;
    }
    .secao-ferramentas h2 {
        font-size: 21px;
        margin-bottom: 4px;
    }
    .secao-ferramentas p {
        margin-top: 0;
        margin-bottom: 14px;
    }
    div.stButton > button {
        min-height: 64px;
        border-radius: 10px;
        font-weight: 600;
        font-size: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# CABEÇALHO
# ============================================================

st.markdown(
    """
    <div class="titulo-ferramentas">
        <h1>🔧 Ferramentas Adicionais</h1>
        <p>Ferramentas rápidas para Excel e cálculos operacionais.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EXCEL TOOLS — JUNTAR EXCEL
# ============================================================

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ferramentas_adicionais.excel_tools import render_juntar_excel


@st.dialog("🔗 Juntar Excel", width="large")
def abrir_juntar_excel():
    render_juntar_excel()


@st.dialog("👁️ Visualizar Excel", width="large")
def abrir_visualizar_excel():
    st.markdown("### Visualizador de Excel")
    st.info("A ferramenta será implementada neste popup.")


@st.dialog("🔍 Comparar Bases", width="large")
def abrir_comparar_bases():
    st.markdown("### Comparador de Bases")
    st.info("A ferramenta será implementada neste popup.")


@st.dialog("🧹 Remover Duplicidades", width="large")
def abrir_remover_duplicidades():
    st.markdown("### Remover Duplicidades")
    st.info("A ferramenta será implementada neste popup.")


@st.dialog("✂️ Separar Excel", width="large")
def abrir_separar_excel():
    st.markdown("### Separar Excel")
    st.info("A ferramenta será implementada neste popup.")


@st.dialog("📤 Exportar / Converter Excel", width="large")
def abrir_exportar_excel():
    st.markdown("### Exportar / Converter Excel")
    st.info("A ferramenta será implementada neste popup.")


@st.dialog("💧 Vazão", width="large")
def abrir_vazao():
    st.markdown("### Calculadora de Vazão")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("📈 Pressão", width="large")
def abrir_pressao():
    st.markdown("### Calculadora de Pressão")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("🚰 Consumo", width="large")
def abrir_consumo():
    st.markdown("### Calculadora de Consumo")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("📦 Volume", width="large")
def abrir_volume():
    st.markdown("### Calculadora de Volume")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("⏱️ Tempo", width="large")
def abrir_tempo():
    st.markdown("### Calculadora de Tempo")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("📅 SLA", width="large")
def abrir_sla():
    st.markdown("### Calculadora de SLA")
    st.info("A calculadora será implementada neste popup.")


@st.dialog("🔄 Conversor de Unidades", width="large")
def abrir_unidades():
    st.markdown("### Conversor de Unidades")
    st.info("O conversor será implementado neste popup.")


# ============================================================
# EXCEL TOOLS
# ============================================================

st.markdown(
    """
    <div class="secao-ferramentas">
        <h2>📊 Excel Tools</h2>
        <p>Ferramentas rápidas para manipulação e tratamento de arquivos Excel.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

excel_tools = [
    ("🔗 Juntar Excel", abrir_juntar_excel),
    ("👁️ Visualizar Excel", abrir_visualizar_excel),
    ("🔍 Comparar Bases", abrir_comparar_bases),
    ("🧹 Remover Duplicidades", abrir_remover_duplicidades),
    ("✂️ Separar Excel", abrir_separar_excel),
    ("📤 Exportar/Converter Excel", abrir_exportar_excel),
]

colunas_excel = st.columns(4)

for indice, (nome, funcao) in enumerate(excel_tools):
    with colunas_excel[indice % 4]:
        if st.button(nome, key=f"ferramenta_excel_{indice}", use_container_width=True):
            funcao()


st.divider()


# ============================================================
# CALCULADORAS
# ============================================================

st.markdown(
    """
    <div class="secao-ferramentas">
        <h2>🧮 Calculadoras</h2>
        <p>Calculadoras rápidas para operações e conversões.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

calculadoras = [
    ("💧 Vazão", abrir_vazao),
    ("📈 Pressão", abrir_pressao),
    ("🚰 Consumo", abrir_consumo),
    ("📦 Volume", abrir_volume),
    ("⏱️ Tempo", abrir_tempo),
    ("📅 SLA", abrir_sla),
    ("🔄 Conversor de Unidades", abrir_unidades),
]

colunas_calculadoras = st.columns(4)

for indice, (nome, funcao) in enumerate(calculadoras):
    with colunas_calculadoras[indice % 4]:
        if st.button(nome, key=f"calculadora_{indice}", use_container_width=True):
            funcao()


st.divider()

if st.button("🏢 Voltar ao Hub Central", key="voltar_hub_ferramentas", use_container_width=True):
    st.switch_page("app.py")
