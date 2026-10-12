"""Ferramenta temporária: execute com `streamlit run Exportar_cadastros_Farol.py`.

Requer as mesmas credenciais st.secrets['gcp_json'] do Farol.
Remova este arquivo do repositório depois de exportar os dados.
"""
import io
import json
import zipfile

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1l0IcsO1GgPYcs8DPRPI6_lKdSCM9vWOypcrwIMJ96QY"
ABAS = {
    "POCOS": ("pocos.csv", ["ID_POCO", "IDENTIFICACAO_ATIVO", "NOME_POCO", "MUNICIPIO", "LATITUDE", "LONGITUDE"]),
    "LOGGERS": ("loggers.csv", ["ID_LOGGER", "IDENTIFICACAO_ATIVO", "ENDERECO", "MUNICIPIO", "LATITUDE", "LONGITUDE"]),
}

st.set_page_config(page_title="Exportação de cadastros do Farol")
st.title("Exportação dos cadastros do Farol")
st.info("Ferramenta temporária. Exporte os dois cadastros e adicione os CSV à pasta dados/ do repositório antes de implantar o novo Farol.")

# Se executado como página do Hub, preserva a autenticação do projeto.
try:
    from auth import verificar_autenticacao
    if not verificar_autenticacao():
        st.error("Faça login no Hub Central antes de exportar os dados.")
        st.stop()
    if str(st.session_state.get("perfil", "")).strip().lower() != "admin":
        st.error("A exportação dos cadastros está restrita ao administrador.")
        st.stop()
except ImportError:
    st.error("O módulo auth.py do Hub Central é obrigatório para esta exportação.")
    st.stop()

if st.button("Preparar arquivos CSV", type="primary"):
    try:
        cred = st.secrets["gcp_json"]
        cred = json.loads(cred) if isinstance(cred, str) else dict(cred)
        client = gspread.authorize(Credentials.from_service_account_info(
            cred, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        ))
        planilha = client.open_by_key(SPREADSHEET_ID)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pacote:
            for aba_nome, (arquivo, colunas) in ABAS.items():
                valores = planilha.worksheet(aba_nome).get_all_records(numericise_ignore=["all"])
                df = pd.DataFrame(valores)
                faltantes = [c for c in colunas if c not in df.columns]
                if faltantes and not df.empty:
                    raise ValueError(f"A aba {aba_nome} não contém as colunas: {faltantes}")
                df = df.reindex(columns=colunas).fillna("")
                pacote.writestr(f"dados/{arquivo}", df.to_csv(index=False).encode("utf-8-sig"))
                st.success(f"{aba_nome}: {len(df)} registros exportados")
        st.download_button("Baixar cadastros (ZIP)", data=buffer.getvalue(),
                           file_name="cadastros_farol_github.zip", mime="application/zip")
    except Exception as erro:
        st.error(f"Falha na exportação: {erro}")
