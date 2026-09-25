import re

import pandas as pd
import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado
from ..exportacao import dataframe_para_excel
from ..zonas import obter_zona


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TIPO_ENCERRAMENTO = 6

COLUNAS_LOTE = [
    "Matricula",
    "Zona Ligacao",
    "Numero Do Pedido",
    "Ano Do Pedido",
    "Tipo Encerramento",
    "Observações",
]


# ============================================================
# ESTILO
# ============================================================

def aplicar_modo_visual(modo_escuro):
    if modo_escuro:
        st.markdown(
            """
            <style>
            .stApp {
                background-color: #0e1117;
                color: #f1f5f9;
            }

            [data-testid="stAppViewContainer"] {
                background-color: #0e1117;
            }

            [data-testid="stHeader"] {
                background-color: #0e1117;
            }

            h1, h2, h3, h4, h5, h6,
            p, label,
            [data-testid="stMarkdownContainer"] {
                color: #f1f5f9;
            }

            .stCaption,
            [data-testid="stCaptionContainer"] {
                color: #aab4c3 !important;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 12px;
            }

            textarea,
            input,
            select {
                background-color: #1b222c !important;
                color: #f1f5f9 !important;
                border-color: #3b4654 !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                border-radius: 8px;
                border: 1px solid #3b4654;
            }

            [data-testid="stSidebar"] {
                background-color: #161b22;
                border-right: 1px solid #30363d;
            }

            [data-testid="stSidebar"] * {
                color: #f1f5f9;
            }

            [data-testid="stSidebar"] .stButton > button {
                background-color: #212833 !important;
                color: #f1f5f9 !important;
                border: 1px solid #3b4654 !important;
                border-radius: 8px !important;
            }

            [data-testid="stSidebar"] .stButton > button:hover {
                background-color: #2b3441 !important;
                color: #ffffff !important;
                border-color: #64748b !important;
            }

            [data-testid="stSidebar"] .stButton > button p {
                color: #f1f5f9 !important;
            }

            hr {
                border-color: #30363d;
            }

            .lista-rapida-status {
                font-size: 0.82rem;
                margin-top: -0.1rem;
                margin-bottom: 0.4rem;
            }

            </style>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            """
            <style>
            .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
            }

            h1 {
                margin-bottom: 0.2rem;
            }

            h2, h3 {
                margin-top: 0.5rem;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-radius: 12px;
            }

            .lista-rapida-status {
                font-size: 0.82rem;
                margin-top: -0.1rem;
                margin-bottom: 0.4rem;
            }

            </style>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# UTILITÁRIOS
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    return str(valor).strip()


def encontrar_coluna(df, candidatos):
    mapa = {
        normalizar_texto(col).upper(): col
        for col in df.columns
    }

    for candidato in candidatos:
        chave = normalizar_texto(candidato).upper()

        if chave in mapa:
            return mapa[chave]

    return None


def normalizar_numero(valor):
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass

    texto = str(valor).strip()

    if not texto:
        return None

    if re.fullmatch(r"\d+\.0+", texto):
        texto = texto.split(".")[0]

    numero = re.sub(r"\D", "", texto)

    return numero or None


def normalizar_ano(valor):
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass

    texto = str(valor).strip()

    if re.fullmatch(r"\d+\.0+", texto):
        texto = texto.split(".")[0]

    match = re.search(r"\b(19|20)\d{2}\b", texto)

    if match:
        return match.group(0)

    somente_digitos = re.sub(r"\D", "", texto)

    if len(somente_digitos) == 4:
        return somente_digitos

    return None


def parse_protocolo(valor):
    """
    Aceita:
        123456/2026
        123456-2026
        123456 / 2026
        123456
    """

    texto = normalizar_texto(valor)

    if not texto:
        return None, None

    match = re.fullmatch(
        r"(\d+)\s*[/\\\-]\s*(\d{4})",
        texto,
    )

    if match:
        return (
            match.group(1),
            match.group(2),
        )

    match = re.fullmatch(
        r"(\d+)\s+(\d{4})",
        texto,
    )

    if match:
        return (
            match.group(1),
            match.group(2),
        )

    somente_digitos = re.sub(r"\D", "", texto)

    if somente_digitos:
        return somente_digitos, None

    return None, None


def extrair_protocolos(texto):
    if texto is None:
        return []

    texto = str(texto).strip()

    if not texto:
        return []

    itens = re.split(
        r"[\n,;]+",
        texto,
    )

    return [
        item.strip()
        for item in itens
        if item.strip()
    ]


# ============================================================
# PREPARAÇÃO DO BACKLOG
# ============================================================

def preparar_backlog(df):
    coluna_numero = encontrar_coluna(
        df,
        [
            "COD. PROTOCOLO ORIGEM",
            "COD PROTOCOLO ORIGEM",
            "PROTOCOLO ORIGEM",
        ],
    )

    coluna_ano = encontrar_coluna(
        df,
        [
            "ANO DO PEDIDO",
            "ANO DO PEDIDO ORIGEM",
            "ANO",
        ],
    )

    coluna_matricula = encontrar_coluna(
        df,
        [
            "MATRICULA",
            "MATRÍCULA",
        ],
    )

    coluna_cidade = encontrar_coluna(
        df,
        [
            "CIDADE",
        ],
    )

    if coluna_numero is None:
        raise ValueError(
            "A base selecionada não possui a coluna "
            "'COD. PROTOCOLO ORIGEM'."
        )

    if coluna_ano is None:
        raise ValueError(
            "A base selecionada não possui a coluna "
            "'ANO DO PEDIDO'."
        )

    if coluna_matricula is None:
        raise ValueError(
            "A base selecionada não possui a coluna "
            "'MATRICULA'."
        )

    if coluna_cidade is None:
        raise ValueError(
            "A base selecionada não possui a coluna "
            "'CIDADE'."
        )

    backlog = df.copy()

    backlog["_lista_numero"] = backlog[
        coluna_numero
    ].apply(normalizar_numero)

    backlog["_lista_ano"] = backlog[
        coluna_ano
    ].apply(normalizar_ano)

    backlog["_lista_cidade"] = backlog[
        coluna_cidade
    ].apply(normalizar_texto)

    return (
        backlog,
        coluna_matricula,
    )


# ============================================================
# CRUZAMENTO
# ============================================================

def cruzar_lista_com_backlog(
    df,
    itens_lista,
    modo,
    observacoes,
):
    backlog, coluna_matricula = preparar_backlog(df)

    encontrados = []
    nao_encontrados = []

    incluidos = set()

    for item in itens_lista:

        numero, ano = parse_protocolo(item)

        if numero is None:
            nao_encontrados.append(
                {
                    "Entrada": item,
                    "Motivo": "O.S. inválida",
                }
            )
            continue

        # ----------------------------------------------------
        # PRIMEIRA TENTATIVA:
        # número + ano
        # ----------------------------------------------------

        candidatos = pd.DataFrame()

        if ano is not None:
            candidatos = backlog[
                (backlog["_lista_numero"] == numero)
                & (backlog["_lista_ano"] == ano)
            ]

        # ----------------------------------------------------
        # SEGUNDA TENTATIVA:
        # somente número
        # ----------------------------------------------------

        if candidatos.empty:
            candidatos = backlog[
                backlog["_lista_numero"] == numero
            ]

        if candidatos.empty:
            nao_encontrados.append(
                {
                    "Entrada": item,
                    "Motivo": "O.S. não encontrada",
                }
            )
            continue

        # ----------------------------------------------------
        # SE HOUVER MAIS DE UMA OCORRÊNCIA,
        # utiliza a primeira ocorrência encontrada.
        # ----------------------------------------------------

        linha = candidatos.iloc[0]

        numero_encontrado = normalizar_numero(
            linha["_lista_numero"]
        )

        ano_encontrado = normalizar_ano(
            linha["_lista_ano"]
        )

        chave = (
            numero_encontrado,
            ano_encontrado,
        )

        # ----------------------------------------------------
        # EVITA DUPLICIDADE NA PRÓPRIA LISTA
        # ----------------------------------------------------

        if chave in incluidos:
            continue

        cidade = normalizar_texto(
            linha["_lista_cidade"]
        )

        # ----------------------------------------------------
        # ZONA
        # ----------------------------------------------------

        if modo == "THE":
            zona = 1
        else:
            zona = obter_zona(cidade)

        if zona is None:
            nao_encontrados.append(
                {
                    "Entrada": item,
                    "Motivo": (
                        f"Cidade sem zona cadastrada: {cidade}"
                    ),
                }
            )
            continue

        # ----------------------------------------------------
        # REGISTRO DO LOTE
        # ----------------------------------------------------

        encontrados.append(
            {
                "Matricula": linha[coluna_matricula],
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_encontrado,
                "Ano Do Pedido": ano_encontrado,
                "Tipo Encerramento": TIPO_ENCERRAMENTO,
                "Observações": observacoes,
            }
        )

        incluidos.add(chave)

    resultado = pd.DataFrame(
        encontrados,
        columns=COLUNAS_LOTE,
    )

    return resultado, nao_encontrados


# ============================================================
# ESTADO
# ============================================================

def inicializar_estado_lista_rapida():

    if "lista_rapida_modo_api_the" not in st.session_state:
        st.session_state[
            "lista_rapida_modo_api_the"
        ] = None

    if "lista_rapida_protocolos" not in st.session_state:
        st.session_state[
            "lista_rapida_protocolos"
        ] = ""

    if "lista_rapida_observacoes" not in st.session_state:
        st.session_state[
            "lista_rapida_observacoes"
        ] = ""

    if "lista_rapida_gerada" not in st.session_state:
        st.session_state[
            "lista_rapida_gerada"
        ] = False

    if "lista_rapida_resultado" not in st.session_state:
        st.session_state[
            "lista_rapida_resultado"
        ] = None

    if "lista_rapida_nao_encontrados" not in st.session_state:
        st.session_state[
            "lista_rapida_nao_encontrados"
        ] = []


def limpar_estado_lista_rapida():

    st.session_state[
        "lista_rapida_protocolos"
    ] = ""

    st.session_state[
        "lista_rapida_observacoes"
    ] = ""

    st.session_state[
        "lista_rapida_gerada"
    ] = False

    st.session_state[
        "lista_rapida_resultado"
    ] = None

    st.session_state[
        "lista_rapida_nao_encontrados"
    ] = []


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_lista_rapida():

    inicializar_estado_lista_rapida()

    modo_escuro = st.session_state.get(
        "modo_escuro_gerador",
        False,
    )

    aplicar_modo_visual(modo_escuro)

    # ========================================================
    # CABEÇALHO
    # ========================================================

    st.title("⚡ Lista Rápida")

    st.caption(
        "Cole uma lista de protocolos/O.S. para gerar "
        "rapidamente um lote de cancelamento."
    )

    st.divider()

    # ========================================================
    # BASE DE OPERAÇÃO
    # ========================================================

    bases_disponiveis = []

    if base_carregada("api"):
        bases_disponiveis.append("API")

    if base_carregada("the"):
        bases_disponiveis.append("THE")

    if not bases_disponiveis:

        st.warning(
            "Nenhuma base API ou THE está carregada."
        )

        st.info(
            "Volte ao Hub, carregue uma base API ou THE "
            "e depois acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lista_rapida_sem_base",
        ):
            st.session_state.ferramenta_atual = None
            limpar_estado_lista_rapida()
            limpar_resultado()
            st.rerun()

        st.stop()

    modo_anterior = st.session_state.get(
        "lista_rapida_modo_api_the"
    )

    if modo_anterior not in bases_disponiveis:
        modo_anterior = bases_disponiveis[0]

    modo = st.radio(
        "Base de operação",
        bases_disponiveis,
        index=bases_disponiveis.index(
            modo_anterior
        ),
        horizontal=True,
        key="lista_rapida_modo_api_the",
    )

    nome_base = (
        "api"
        if modo == "API"
        else "the"
    )

    df = obter_base(nome_base)

    if df is None or df.empty:
        st.warning(
            f"A base {modo} não possui dados disponíveis."
        )
        st.stop()

    # ========================================================
    # INFORMAÇÕES DA BASE
    # ========================================================

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Base",
            modo,
        )

    with col2:
        st.metric(
            "Registros",
            f"{len(df):,}".replace(",", "."),
        )

    with col3:
        st.metric(
            "Colunas",
            f"{len(df.columns):,}".replace(",", "."),
        )

    st.divider()

    # ========================================================
    # LISTA
    # ========================================================

    st.markdown("### 📋 Protocolos / O.S.")

    st.caption(
        "Cole um item por linha ou utilize vírgulas ou "
        "ponto e vírgula para separar os protocolos."
    )

    st.text_area(
        "Lista de protocolos",
        height=220,
        placeholder=(
            "Exemplo:\n"
            "123456/2026\n"
            "123457/2026\n"
            "123458/2026"
        ),
        key="lista_rapida_protocolos",
        label_visibility="collapsed",
    )

    # ========================================================
    # OBSERVAÇÕES
    # ========================================================

    st.markdown("### 📝 Observações")

    st.caption(
        "Digite a observação que deverá ser gravada "
        "no lote gerado."
    )

    st.text_area(
        "Observações do lote",
        height=120,
        placeholder=(
            "Digite aqui a observação que será aplicada "
            "aos registros do lote."
        ),
        key="lista_rapida_observacoes",
        label_visibility="collapsed",
    )

    st.divider()

    # ========================================================
    # GERAÇÃO
    # ========================================================

    if st.button(
        "⚡ Gerar Lote",
        type="primary",
        use_container_width=True,
        key="btn_gerar_lista_rapida",
    ):

        texto = st.session_state.get(
            "lista_rapida_protocolos",
            "",
        )

        itens_lista = extrair_protocolos(texto)

        if not itens_lista:
            st.warning(
                "Informe pelo menos uma O.S. ou protocolo."
            )
            st.stop()

        observacoes = st.session_state.get(
            "lista_rapida_observacoes",
            "",
        ).strip()

        with st.spinner(
            "Cruzando a lista com o backlog..."
        ):

            resultado, nao_encontrados = (
                cruzar_lista_com_backlog(
                    df=df,
                    itens_lista=itens_lista,
                    modo=modo,
                    observacoes=observacoes,
                )
            )

        st.session_state[
            "lista_rapida_resultado"
        ] = resultado

        st.session_state[
            "lista_rapida_nao_encontrados"
        ] = nao_encontrados

        st.session_state[
            "lista_rapida_gerada"
        ] = True

        st.rerun()

    # ========================================================
    # RESULTADO
    # ========================================================

    if not st.session_state.get(
        "lista_rapida_gerada",
        False,
    ):

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lista_rapida",
        ):
            st.session_state.ferramenta_atual = None
            limpar_estado_lista_rapida()
            limpar_resultado()
            st.rerun()

        return

    resultado = st.session_state.get(
        "lista_rapida_resultado"
    )

    nao_encontrados = st.session_state.get(
        "lista_rapida_nao_encontrados",
        [],
    )

    if resultado is None:
        resultado = pd.DataFrame(
            columns=COLUNAS_LOTE
        )

    itens_informados = extrair_protocolos(
        st.session_state.get(
            "lista_rapida_protocolos",
            "",
        )
    )

    st.divider()

    st.markdown("### 📊 Resultado")

    col_resultado_1, col_resultado_2, col_resultado_3 = (
        st.columns(3)
    )

    with col_resultado_1:
        st.metric(
            "Itens informados",
            f"{len(itens_informados):,}".replace(
                ",",
                ".",
            ),
        )

    with col_resultado_2:
        st.metric(
            "Incluídos no lote",
            f"{len(resultado):,}".replace(
                ",",
                ".",
            ),
        )

    with col_resultado_3:
        st.metric(
            "Não encontrados",
            f"{len(nao_encontrados):,}".replace(
                ",",
                ".",
            ),
        )

    # ========================================================
    # NÃO ENCONTRADOS
    # ========================================================

    if nao_encontrados:

        st.warning(
            f"{len(nao_encontrados)} item(ns) não foram "
            "incluídos no lote."
        )

        with st.expander(
            "Ver O.S. não encontradas",
            expanded=False,
        ):

            df_nao_encontrados = pd.DataFrame(
                nao_encontrados
            )

            st.dataframe(
                df_nao_encontrados,
                use_container_width=True,
                hide_index=True,
            )

    # ========================================================
    # LOTE
    # ========================================================

    if resultado.empty:

        st.error(
            "Nenhuma O.S. válida foi encontrada no backlog."
        )

    else:

        st.markdown("#### 📦 Lote gerado")

        st.dataframe(
            resultado,
            use_container_width=True,
            hide_index=True,
        )

        arquivo = dataframe_para_excel(
            resultado,
            nome_aba="Lote",
        )

        st.download_button(
            "📥 Baixar lote Excel",
            data=(
                arquivo
                if arquivo is not None
                else b""
            ),
            file_name="Lista_Rapida_Cancelamento.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
            disabled=arquivo is None,
            key="btn_baixar_lista_rapida",
        )

    st.divider()

    # ========================================================
    # AÇÕES
    # ========================================================

    col_acao_1, col_acao_2 = st.columns(2)

    with col_acao_1:

        if st.button(
            "🗑️ Limpar lista",
            use_container_width=True,
            key="btn_limpar_lista_rapida",
        ):
            limpar_estado_lista_rapida()
            st.rerun()

    with col_acao_2:

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lista_rapida_resultado",
        ):
            st.session_state.ferramenta_atual = None
            limpar_estado_lista_rapida()
            limpar_resultado()
            st.rerun()
