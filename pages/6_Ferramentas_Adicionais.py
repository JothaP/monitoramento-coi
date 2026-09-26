import io
import re

import pandas as pd
import streamlit as st

from auth import verificar_autenticacao
from ferramentas_adicionais import render_juntar_excel


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
# AUXILIARES — JUNTAR EXCEL
# ============================================================

def _normalizar_coluna(nome):
    return re.sub(r"\s+", " ", str(nome).strip()).casefold()


def _ler_excel(arquivo):
    nome = arquivo.name.lower()
    if nome.endswith(".xlsx"):
        return pd.read_excel(arquivo, engine="openpyxl")
    if nome.endswith(".xls"):
        return pd.read_excel(arquivo)
    raise ValueError(f"Formato não suportado: {arquivo.name}")


def _estrutura_dataframe(df):
    return [_normalizar_coluna(coluna) for coluna in df.columns]


def _formatar_tamanho(quantidade):
    if quantidade == 1:
        return "1 arquivo"
    return f"{quantidade} arquivos"


def _montar_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# MODAIS
# ============================================================

@st.dialog("🔗 Juntar Excel", width="large")
def abrir_juntar_excel():
    st.markdown("### Juntar arquivos Excel")
    st.caption(
        "Selecione dois ou mais arquivos. As estruturas serão verificadas antes da junção."
    )

    arquivos = st.file_uploader(
        "Selecione os arquivos Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="juntar_excel_arquivos",
        help="Os arquivos originais não serão alterados.",
    )

    if not arquivos:
        st.info("Selecione os arquivos que deseja juntar.")
        return

    st.write(f"**{_formatar_tamanho(len(arquivos))} selecionados.**")

    dataframes = []
    erros = []

    for arquivo in arquivos:
        try:
            df = _ler_excel(arquivo)
            dataframes.append((arquivo.name, df))
        except Exception as exc:
            erros.append(f"**{arquivo.name}:** {exc}")

    if erros:
        st.error("Não foi possível ler um ou mais arquivos:")
        for erro in erros:
            st.write(f"- {erro}")
        st.stop()

    if len(dataframes) < 2:
        st.warning("Selecione pelo menos 2 arquivos para realizar a junção.")
        return

    # --------------------------------------------------------
    # Diagnóstico das estruturas
    # --------------------------------------------------------

    estruturas = [_estrutura_dataframe(df) for _, df in dataframes]
    estrutura_base = estruturas[0]
    estruturas_iguais = all(estrutura == estrutura_base for estrutura in estruturas[1:])

    st.markdown("#### 📋 Estrutura dos arquivos")

    resumo = pd.DataFrame(
        {
            "Arquivo": [nome for nome, _ in dataframes],
            "Registros": [len(df) for _, df in dataframes],
            "Colunas": [len(df.columns) for _, df in dataframes],
        }
    )
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    if estruturas_iguais:
        st.success("✅ Todos os arquivos possuem a mesma estrutura. A junção pode ser realizada diretamente.")
        modo_juncao = "direta"
    else:
        st.warning("⚠️ Os arquivos possuem estruturas diferentes.")

        todas_colunas = []
        mapa_colunas = {}
        for nome, df in dataframes:
            mapa_colunas[nome] = list(df.columns)
            for coluna in df.columns:
                chave = _normalizar_coluna(coluna)
                if chave not in todas_colunas:
                    todas_colunas.append(chave)

        detalhes = []
        for nome, df in dataframes:
            presentes = {_normalizar_coluna(col) for col in df.columns}
            faltantes = [col for col in todas_colunas if col not in presentes]
            detalhes.append(
                {
                    "Arquivo": nome,
                    "Colunas presentes": len(presentes),
                    "Colunas ausentes": len(faltantes),
                    "Ausentes": ", ".join(faltantes) if faltantes else "—",
                }
            )

        st.dataframe(
            pd.DataFrame(detalhes),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Escolha como proceder")
        modo_juncao = st.radio(
            "",
            [
                "A — Juntar mesmo, preenchendo colunas ausentes em branco",
                "B — Bloquear a operação",
            ],
            key="juntar_excel_modo_estrutura",
        )

        if modo_juncao.startswith("B"):
            st.error("A operação está bloqueada. Nenhum arquivo foi alterado.")
            return

        st.info(
            "As colunas serão unificadas. Quando uma coluna não existir em determinado arquivo, "
            "as células correspondentes ficarão em branco."
        )

    # --------------------------------------------------------
    # Junção
    # --------------------------------------------------------

    if st.button(
        "🔗 Juntar arquivos",
        type="primary",
        use_container_width=True,
        key="executar_juntar_excel",
    ):
        try:
            if estruturas_iguais:
                resultado = pd.concat(
                    [df for _, df in dataframes],
                    ignore_index=True,
                )
            else:
                # União por posição lógica de coluna, preservando o nome da
                # primeira ocorrência e preenchendo ausentes com vazio/NaN.
                ordem_colunas = []
                chaves_colunas = set()
                nomes_por_chave = {}

                for _, df in dataframes:
                    for coluna in df.columns:
                        chave = _normalizar_coluna(coluna)
                        if chave not in chaves_colunas:
                            chaves_colunas.add(chave)
                            ordem_colunas.append(chave)
                            nomes_por_chave[chave] = coluna

                padronizados = []
                for _, df in dataframes:
                    novo = pd.DataFrame(index=df.index)
                    colunas_df = {_normalizar_coluna(col): col for col in df.columns}
                    for chave in ordem_colunas:
                        if chave in colunas_df:
                            novo[nomes_por_chave[chave]] = df[colunas_df[chave]].values
                        else:
                            novo[nomes_por_chave[chave]] = pd.NA
                    padronizados.append(novo)

                resultado = pd.concat(padronizados, ignore_index=True)

            st.session_state["juntar_excel_resultado"] = resultado
            st.session_state["juntar_excel_nome"] = "Excel_Consolidado.xlsx"

        except Exception as exc:
            st.error(f"Não foi possível juntar os arquivos: {exc}")
            return

    resultado = st.session_state.get("juntar_excel_resultado")

    if resultado is None:
        return

    st.success(
        f"✅ Junção concluída: {len(resultado):,} registros e "
        f"{len(resultado.columns):,} colunas."
    )

    st.markdown("#### 👁️ Prévia do resultado")
    st.dataframe(
        resultado.head(100),
        use_container_width=True,
        hide_index=True,
    )

    arquivo_saida = _montar_excel(resultado)

    st.download_button(
        "📥 Baixar Excel consolidado",
        data=arquivo_saida,
        file_name=st.session_state.get("juntar_excel_nome", "Excel_Consolidado.xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="download_juntar_excel",
    )


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
