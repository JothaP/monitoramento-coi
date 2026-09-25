import io
import re
import unicodedata

import pandas as pd
import streamlit as st

from ..estado import obter_base, base_carregada, limpar_resultado
from ..exportacao import dataframe_para_excel
from .componentes import selecionar_modo_api_the


COLUNAS_RESULTADO = [
    "Matrícula",
    "Número da O.S.",
    "Bairro",
    "Motivo do cancelamento",
    "Arquivo Lote",
]

COLUNAS_LOG = [
    "Número da O.S.",
    "Ano",
    "Matrícula",
    "Arquivo Lote",
    "Aviso",
]


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar_texto(valor):
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    ).encode(
        "ASCII",
        "ignore",
    ).decode(
        "ASCII"
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def normalizar_matricula(valor):
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return re.sub(r"\D", "", texto)


def normalizar_numero(valor):
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    numeros = re.sub(r"\D", "", texto)

    return numeros


def normalizar_ano(valor):
    if valor is None or pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    numeros = re.sub(r"\D", "", texto)

    return numeros


# ============================================================
# IDENTIFICAÇÃO DE COLUNAS
# ============================================================

def encontrar_coluna(df, candidatos):
    mapa = {
        normalizar_texto(coluna): coluna
        for coluna in df.columns
    }

    for candidato in candidatos:
        chave = normalizar_texto(candidato)

        if chave in mapa:
            return mapa[chave]

    for coluna_normalizada, coluna_original in mapa.items():
        for candidato in candidatos:
            chave = normalizar_texto(candidato)

            if (
                chave in coluna_normalizada
                or coluna_normalizada in chave
            ):
                return coluna_original

    return None


def encontrar_coluna_matricula(df):
    return encontrar_coluna(
        df,
        [
            "MATRICULA",
            "MATRÍCULA",
            "MATRICULA DO CLIENTE",
            "MATRÍCULA DO CLIENTE",
        ],
    )


def encontrar_coluna_numero(df):
    return encontrar_coluna(
        df,
        [
            "NUMERO DO PEDIDO",
            "NÚMERO DO PEDIDO",
            "NUMERO DA OS",
            "NÚMERO DA OS",
            "NUMERO DA O.S.",
            "NÚMERO DA O.S.",
            "NUMERO O.S.",
            "NÚMERO O.S.",
            "OS",
            "O.S.",
        ],
    )


def encontrar_coluna_ano(df):
    return encontrar_coluna(
        df,
        [
            "ANO DO PEDIDO",
            "ANO DA OS",
            "ANO DA O.S.",
            "ANO O.S.",
            "ANO",
        ],
    )


def encontrar_coluna_bairro(df):
    return encontrar_coluna(
        df,
        [
            "BAIRRO",
        ],
    )


# ============================================================
# LEITURA DOS ARQUIVOS DE LOTE
# ============================================================

def ler_excel(arquivo):
    if arquivo is None:
        return None

    nome = arquivo.name.lower()

    if not nome.endswith((".xlsx", ".xlsm")):
        raise ValueError(
            f"O arquivo '{arquivo.name}' não é um Excel válido. "
            "Utilize .xlsx ou .xlsm."
        )

    conteudo = arquivo.getvalue()

    df = pd.read_excel(
        io.BytesIO(conteudo),
        engine="openpyxl",
    )

    df.columns = [
        str(coluna).strip()
        for coluna in df.columns
    ]

    return df


def preparar_lote(df, nome_arquivo):
    if df is None or df.empty:
        return None, (
            f"O arquivo '{nome_arquivo}' não contém registros."
        )

    coluna_matricula = encontrar_coluna_matricula(df)
    coluna_numero = encontrar_coluna_numero(df)
    coluna_ano = encontrar_coluna_ano(df)

    faltantes = []

    if coluna_matricula is None:
        faltantes.append("Matrícula")

    if coluna_numero is None:
        faltantes.append("Número da O.S.")

    if coluna_ano is None:
        faltantes.append("Ano")

    if faltantes:
        return None, (
            f"O arquivo '{nome_arquivo}' não possui as colunas "
            f"necessárias: {', '.join(faltantes)}."
        )

    lote = pd.DataFrame(
        {
            "_MATRICULA_CHAVE": df[coluna_matricula].apply(
                normalizar_matricula
            ),
            "_NUMERO_CHAVE": df[coluna_numero].apply(
                normalizar_numero
            ),
            "_ANO_CHAVE": df[coluna_ano].apply(
                normalizar_ano
            ),
            "_NUMERO_EXIBICAO": df[coluna_numero],
            "_ANO_EXIBICAO": df[coluna_ano],
            "_MATRICULA_EXIBICAO": df[coluna_matricula],
            "_FONTE_LOTE": nome_arquivo,
        }
    )

    lote = lote[
        lote["_MATRICULA_CHAVE"] != ""
    ].copy()

    lote = lote[
        lote["_NUMERO_CHAVE"] != ""
    ].copy()

    lote = lote[
        lote["_ANO_CHAVE"] != ""
    ].copy()

    lote.reset_index(drop=True, inplace=True)

    if lote.empty:
        return None, (
            f"O arquivo '{nome_arquivo}' não possui registros "
            "válidos para cruzamento."
        )

    return lote, None


# ============================================================
# PREPARAÇÃO DO BACKLOG
# ============================================================

def preparar_backlog(df):
    if df is None or df.empty:
        return None, "A base de backlog está vazia."

    coluna_matricula = encontrar_coluna_matricula(df)
    coluna_numero = encontrar_coluna_numero(df)
    coluna_ano = encontrar_coluna_ano(df)
    coluna_bairro = encontrar_coluna_bairro(df)

    faltantes = []

    if coluna_matricula is None:
        faltantes.append("Matrícula")

    if coluna_numero is None:
        faltantes.append("Número da O.S.")

    if coluna_ano is None:
        faltantes.append("Ano")

    if coluna_bairro is None:
        faltantes.append("Bairro")

    if faltantes:
        return None, (
            "A base de backlog não possui as colunas necessárias: "
            + ", ".join(faltantes)
            + "."
        )

    backlog = pd.DataFrame(
        {
            "_MATRICULA_CHAVE": df[coluna_matricula].apply(
                normalizar_matricula
            ),
            "_NUMERO_CHAVE": df[coluna_numero].apply(
                normalizar_numero
            ),
            "_ANO_CHAVE": df[coluna_ano].apply(
                normalizar_ano
            ),
            "_MATRICULA": df[coluna_matricula],
            "_NUMERO": df[coluna_numero],
            "_BAIRRO": df[coluna_bairro],
        }
    )

    backlog = backlog[
        backlog["_MATRICULA_CHAVE"] != ""
    ].copy()

    backlog = backlog[
        backlog["_NUMERO_CHAVE"] != ""
    ].copy()

    backlog = backlog[
        backlog["_ANO_CHAVE"] != ""
    ].copy()

    backlog.reset_index(drop=True, inplace=True)

    if backlog.empty:
        return None, (
            "Não existem registros válidos no backlog "
            "para o cruzamento."
        )

    # Mantém somente a primeira ocorrência de cada chave.
    backlog = backlog.drop_duplicates(
        subset=[
            "_MATRICULA_CHAVE",
            "_NUMERO_CHAVE",
            "_ANO_CHAVE",
        ],
        keep="first",
    )

    return backlog, None


# ============================================================
# CRUZAMENTO
# ============================================================

def cruzar_lotes_com_backlog(
    lotes,
    backlog,
    motivos,
):
    indice_backlog = {}

    for _, linha in backlog.iterrows():
        chave = (
            linha["_MATRICULA_CHAVE"],
            linha["_NUMERO_CHAVE"],
            linha["_ANO_CHAVE"],
        )

        if chave not in indice_backlog:
            indice_backlog[chave] = linha

    resultado = []
    avisos = []

    chaves_processadas = set()

    for _, lote in lotes.iterrows():

        chave = (
            lote["_MATRICULA_CHAVE"],
            lote["_NUMERO_CHAVE"],
            lote["_ANO_CHAVE"],
        )

        fonte = lote["_FONTE_LOTE"]
        motivo = motivos.get(fonte, "")

        # A O.S. só entra uma vez no resultado,
        # respeitando a primeira ocorrência na consolidação.
        if chave in chaves_processadas:
            continue

        chaves_processadas.add(chave)

        registro_backlog = indice_backlog.get(chave)

        if registro_backlog is None:
            avisos.append(
                {
                    "Número da O.S.": lote[
                        "_NUMERO_EXIBICAO"
                    ],
                    "Ano": lote[
                        "_ANO_EXIBICAO"
                    ],
                    "Matrícula": lote[
                        "_MATRICULA_EXIBICAO"
                    ],
                    "Arquivo Lote": fonte,
                    "Aviso": (
                        "O.S. não encontrada no backlog."
                    ),
                }
            )

            continue

        resultado.append(
            {
                "Matrícula": registro_backlog[
                    "_MATRICULA"
                ],
                "Número da O.S.": registro_backlog[
                    "_NUMERO"
                ],
                "Bairro": registro_backlog[
                    "_BAIRRO"
                ],
                "Motivo do cancelamento": motivo,
                "Arquivo Lote": fonte,
            }
        )

    df_resultado = pd.DataFrame(
        resultado,
        columns=COLUNAS_RESULTADO,
    )

    df_log = pd.DataFrame(
        avisos,
        columns=COLUNAS_LOG,
    )

    return df_resultado, df_log


# ============================================================
# ESTADO
# ============================================================

def limpar_estado_lotes():
    chaves = [
        "lotes_arquivos",
        "lotes_motivos",
        "lotes_resultado",
        "lotes_log",
        "lotes_analisado",
    ]

    for chave in chaves:
        if chave in st.session_state:
            del st.session_state[chave]

    limpar_resultado()


# ============================================================
# ESTILO
# ============================================================

def aplicar_estilo_lotes():
    st.markdown(
        """
        <style>

        .lotes-header {
            margin-bottom: 24px;
        }

        .lotes-header-title {
            font-size: 1.65rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 5px;
        }

        .lotes-header-description {
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.92rem;
        }

        .lotes-card {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 12px;
            padding: 20px 22px;
            margin-bottom: 18px;
            background: rgba(128, 128, 128, 0.025);
        }

        .lotes-card-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .lotes-card-description {
            color: rgba(128, 128, 128, 0.9);
            font-size: 0.85rem;
            margin-bottom: 14px;
        }

        [data-testid="stButton"] > button,
        [data-testid="stDownloadButton"] > button {
            border-radius: 8px !important;
            min-height: 42px !important;
            font-weight: 600 !important;
        }

        [data-testid="stButton"] > button:not([kind="primary"]),
        [data-testid="stDownloadButton"] > button {
            background-color: transparent !important;
            color: inherit !important;
            border: 1px solid rgba(
                128,
                128,
                128,
                0.45
            ) !important;
        }

        [data-testid="stButton"] > button:not([kind="primary"]):hover,
        [data-testid="stDownloadButton"] > button:hover {
            background-color: rgba(
                128,
                128,
                128,
                0.10
            ) !important;
            color: inherit !important;
            border-color: rgba(
                128,
                128,
                128,
                0.65
            ) !important;
        }

        [data-testid="stButton"] > button[kind="primary"] {
            color: white !important;
            border: 1px solid transparent !important;
        }

        [data-testid="stButton"] > button[kind="primary"]:hover {
            filter: brightness(1.08);
        }

        [data-testid="stButton"] > button p,
        [data-testid="stButton"] > button span,
        [data-testid="stDownloadButton"] > button p,
        [data-testid="stDownloadButton"] > button span {
            color: inherit !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# RENDER
# ============================================================

def render_lotes():
    aplicar_estilo_lotes()

    st.markdown(
        """
        <div class="lotes-header">
            <div class="lotes-header-title">
                📦 Análise de Lotes
            </div>
            <div class="lotes-header-description">
                Cruza lotes de cancelamento já gerados com o
                backlog de reclamação para identificar bairro e
                acompanhar o motivo do cancelamento.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not base_carregada("api") and not base_carregada("the"):
        st.warning(
            "Nenhuma base de operação API ou THE está carregada."
        )

        st.info(
            "Volte ao Hub, carregue a base de operação e "
            "acesse novamente esta ferramenta."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lotes_sem_backlog",
        ):
            st.session_state.ferramenta_atual = None
            st.rerun()

        st.stop()

    # ========================================================
    # MODO
    # ========================================================

    modo, df_backlog = selecionar_modo_api_the(
        key="lotes_modo_api_the",
        titulo="Base de operação",
        limpar_resultado_callback=limpar_estado_lotes,
    )

    if modo is None or df_backlog is None:
        st.stop()

    st.divider()

    # ========================================================
    # ARQUIVOS DE LOTE
    # ========================================================

    st.markdown(
        """
        <div class="lotes-card">
            <div class="lotes-card-title">
                📂 Arquivos de lote
            </div>
            <div class="lotes-card-description">
                Selecione um ou mais arquivos de lote de
                cancelamento. O nome de cada arquivo será
                preservado no resultado.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    arquivos = st.file_uploader(
        "Arquivos de lote",
        type=["xlsx", "xlsm"],
        accept_multiple_files=True,
        key="lotes_upload_arquivos",
        label_visibility="collapsed",
    )

    if not arquivos:
        st.info(
            "Selecione pelo menos um arquivo de lote para "
            "continuar."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lotes_sem_arquivos",
        ):
            st.session_state.ferramenta_atual = None
            st.rerun()

        return

    # ========================================================
    # MOTIVOS
    # ========================================================

    st.markdown("### 📝 Motivo do cancelamento")

    st.caption(
        "Informe o motivo correspondente a cada arquivo de lote."
    )

    motivos = {}

    for indice, arquivo in enumerate(arquivos):
        chave_motivo = (
            f"lotes_motivo_{indice}_"
            f"{arquivo.name}"
        )

        motivo = st.text_input(
            f"Motivo — {arquivo.name}",
            key=chave_motivo,
            placeholder="Digite o motivo do cancelamento",
        )

        motivos[arquivo.name] = motivo.strip()

    st.divider()

    # ========================================================
    # RESUMO
    # ========================================================

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Arquivos de lote",
            len(arquivos),
        )

    with col2:
        st.metric(
            "Registros no backlog",
            f"{len(df_backlog):,}".replace(",", "."),
        )

    with col3:
        motivos_preenchidos = sum(
            bool(valor)
            for valor in motivos.values()
        )

        st.metric(
            "Motivos preenchidos",
            f"{motivos_preenchidos}/{len(arquivos)}",
        )

    st.divider()

    # ========================================================
    # ANÁLISE
    # ========================================================

    if st.button(
        "⚙️ Gerar acompanhamento",
        type="primary",
        use_container_width=True,
        key="btn_gerar_acompanhamento_lotes",
    ):
        arquivos_sem_motivo = [
            nome
            for nome, motivo in motivos.items()
            if not motivo
        ]

        if arquivos_sem_motivo:
            st.error(
                "Informe o motivo do cancelamento para todos "
                "os arquivos antes de gerar o acompanhamento."
            )

        else:
            lotes_consolidados = []

            erros = []

            for arquivo in arquivos:
                try:
                    df_lote = ler_excel(arquivo)

                    lote_preparado, erro = preparar_lote(
                        df_lote,
                        arquivo.name,
                    )

                    if erro:
                        erros.append(erro)
                    else:
                        lotes_consolidados.append(
                            lote_preparado
                        )

                except Exception as exc:
                    erros.append(
                        f"Erro ao ler '{arquivo.name}': {exc}"
                    )

            if erros:
                for erro in erros:
                    st.error(erro)

            elif not lotes_consolidados:
                st.error(
                    "Nenhum lote válido foi encontrado."
                )

            else:
                lotes = pd.concat(
                    lotes_consolidados,
                    ignore_index=True,
                )

                backlog, erro_backlog = preparar_backlog(
                    df_backlog
                )

                if erro_backlog:
                    st.error(erro_backlog)

                else:
                    resultado, log = (
                        cruzar_lotes_com_backlog(
                            lotes,
                            backlog,
                            motivos,
                        )
                    )

                    st.session_state[
                        "lotes_resultado"
                    ] = resultado

                    st.session_state[
                        "lotes_log"
                    ] = log

                    st.session_state[
                        "lotes_analisado"
                    ] = True

                    st.session_state[
                        "lotes_total_entrada"
                    ] = len(lotes)

                    st.session_state[
                        "lotes_total_resultado"
                    ] = len(resultado)

                    st.session_state[
                        "lotes_total_log"
                    ] = len(log)

                    st.rerun()

    # ========================================================
    # RESULTADO
    # ========================================================

    if not st.session_state.get(
        "lotes_analisado",
        False,
    ):
        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lotes",
        ):
            st.session_state.ferramenta_atual = None
            st.rerun()

        return

    resultado = st.session_state.get(
        "lotes_resultado"
    )

    log = st.session_state.get(
        "lotes_log"
    )

    st.divider()

    st.markdown("### 📊 Resultado do acompanhamento")

    total_entrada = st.session_state.get(
        "lotes_total_entrada",
        0,
    )

    total_resultado = st.session_state.get(
        "lotes_total_resultado",
        0,
    )

    total_log = st.session_state.get(
        "lotes_total_log",
        0,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Registros dos lotes",
            f"{total_entrada:,}".replace(",", "."),
        )

    with col2:
        st.metric(
            "Encontrados no backlog",
            f"{total_resultado:,}".replace(",", "."),
        )

    with col3:
        st.metric(
            "Não encontrados",
            f"{total_log:,}".replace(",", "."),
        )

    # ========================================================
    # TABELA
    # ========================================================

    st.markdown("#### 📋 Registros encontrados")

    if resultado is None or resultado.empty:
        st.info(
            "Nenhum registro dos lotes foi encontrado "
            "no backlog."
        )
    else:
        st.dataframe(
            resultado,
            use_container_width=True,
            hide_index=True,
        )

        arquivo_resultado = dataframe_para_excel(
            resultado,
            nome_aba="Acompanhamento",
        )

        if arquivo_resultado is not None:
            st.download_button(
                "📥 Baixar acompanhamento",
                data=arquivo_resultado.getvalue(),
                file_name="Acompanhamento de Lotes.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="btn_download_acompanhamento_lotes",
            )

    # ========================================================
    # LOG
    # ========================================================

    if log is not None and not log.empty:
        st.markdown("#### ⚠️ Avisos")

        st.dataframe(
            log,
            use_container_width=True,
            hide_index=True,
        )

        arquivo_log = dataframe_para_excel(
            log,
            nome_aba="Avisos",
        )

        if arquivo_log is not None:
            st.download_button(
                "📥 Baixar log de avisos",
                data=arquivo_log.getvalue(),
                file_name="Log de Avisos - Lotes.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="btn_download_log_lotes",
            )

    # ========================================================
    # AÇÕES
    # ========================================================

    st.divider()

    col_acao_1, col_acao_2 = st.columns(2)

    with col_acao_1:
        if st.button(
            "🗑️ Limpar análise",
            use_container_width=True,
            key="btn_limpar_lotes",
        ):
            limpar_estado_lotes()
            st.rerun()

    with col_acao_2:
        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_lotes_resultado",
        ):
            st.session_state.ferramenta_atual = None
            limpar_resultado()
            st.rerun()
