import re
import unicodedata

import pandas as pd
import streamlit as st

from ..exportacao import dataframe_para_excel
from ..estado import base_carregada, obter_base
from ..zonas import obter_zona

from .componentes import selecionar_modo_api_the


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_ARQUIVO_API = "Serviços API.xlsx"
NOME_ARQUIVO_THE = "Serviços THE.xlsx"

COL_MATRICULA = "MATRICULA"
COL_PROTOCOLO = "COD. PROTOCOLO ORIGEM"
COL_CIDADE = "CIDADE"

COL_SAIDA_MATRICULA = "Matricula"
COL_SAIDA_ZONA = "Zona Ligacao"
COL_SAIDA_NUMERO = "Numero Do Pedido"
COL_SAIDA_ANO = "Ano Do Pedido"
COL_SAIDA_TIPO = "Tipo Encerramento"
COL_SAIDA_OBSERVACOES = "Observações"


# ============================================================
# VISUAL
# ============================================================

def aplicar_modo_visual():
    modo_escuro = st.session_state.get(
        "servicos_modo_escuro",
        False,
    )

    if modo_escuro:
        st.markdown(
            """
            <style>
            .stApp {
                background-color: #0e1117;
                color: #fafafa;
            }

            [data-testid="stSidebar"] {
                background-color: #161b22;
            }

            [data-testid="stSidebar"] * {
                color: #fafafa !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                background-color: #21262d;
                color: #ffffff !important;
                border: 1px solid #444c56;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                border-color: #8b949e;
                color: #ffffff !important;
            }

            [data-testid="stMetric"] {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 10px;
            }

            .stExpander {
                border-color: #30363d;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] {
                background-color: #f7f7f7;
            }

            .stButton > button,
            .stDownloadButton > button {
                color: #111111;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


# ============================================================
# SIDEBAR
# ============================================================

def render_sidebar():
    with st.sidebar:
        st.markdown("## 🛠️ Serviços")
        st.caption("Navegação da ferramenta")

        st.divider()

        modo_escuro = st.toggle(
            "🌙 Modo escuro",
            value=st.session_state.get(
                "servicos_modo_escuro",
                False,
            ),
            key="servicos_modo_escuro",
        )

        if modo_escuro:
            st.caption("Modo escuro ativado")
        else:
            st.caption("Modo claro ativado")

        st.divider()

        if st.button(
            "⬅️ Voltar às Ferramentas",
            use_container_width=True,
            key="servicos_voltar_ferramentas",
        ):
            st.session_state.ferramenta_atual = None
            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )

        if st.button(
            "🏠 Voltar ao Gerador de Lotes",
            use_container_width=True,
            key="servicos_voltar_gerador",
        ):
            st.session_state.ferramenta_atual = None
            st.switch_page(
                "pages/4_1_Gerador_Lotes_Cancelamento.py"
            )

    aplicar_modo_visual()


# ============================================================
# NORMALIZAÇÃO DE TEXTO / COLUNAS
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""

    texto = str(valor).strip().upper()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    ).encode(
        "ASCII",
        "ignore",
    ).decode("ASCII")

    texto = re.sub(r"\s+", " ", texto)

    return texto


def localizar_coluna(df, nomes):
    if df is None or df.empty:
        return None

    mapa = {
        normalizar_texto(col): col
        for col in df.columns
    }

    for nome in nomes:
        chave = normalizar_texto(nome)

        if chave in mapa:
            return mapa[chave]

    return None


# ============================================================
# MATRÍCULA
# ============================================================

def normalizar_matricula(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if not texto:
        return ""

    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]

    return re.sub(r"\D", "", texto)


def matricula_valida(valor, modo):
    matricula = normalizar_matricula(valor)

    tamanho_esperado = 9 if modo == "API" else 8

    return (
        bool(matricula)
        and matricula.isdigit()
        and len(matricula) == tamanho_esperado
    )


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(valor):
    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    match = re.fullmatch(
        r"(\d+)\s*/\s*(\d{4})",
        texto,
    )

    if not match:
        return None

    numero = int(match.group(1))
    ano = int(match.group(2))

    return {
        "numero": numero,
        "ano": ano,
        "original": texto,
    }


def chave_protocolo(info):
    return (
        info["ano"],
        info["numero"],
    )


# ============================================================
# LOCALIZAÇÃO DA DESCRIÇÃO DO SERVIÇO
# ============================================================

def localizar_coluna_descricao(df):
    return localizar_coluna(
        df,
        [
            "DESCRIÇÃO DO SERVIÇO",
            "DESCRICAO DO SERVICO",
            "DESCRIÇÃO SERVIÇO",
            "DESCRICAO SERVICO",
            "DESCRIÇÃO",
            "DESCRICAO",
            "SERVIÇO",
            "SERVICO",
        ],
    )


# ============================================================
# CONSOLIDAÇÃO DOS SERVIÇOS
# ============================================================

def consolidar_servicos(df_servicos, modo):
    resultado = {}

    if df_servicos is None or df_servicos.empty:
        return resultado, {
            "total": 0,
            "matriculas_validas": 0,
            "ignorados": 0,
        }

    col_matricula = localizar_coluna(
        df_servicos,
        [
            "MATRICULA",
            "MATRÍCULA",
        ],
    )

    col_protocolo = localizar_coluna(
        df_servicos,
        [
            "COD. PROTOCOLO ORIGEM",
            "CÓD. PROTOCOLO ORIGEM",
            "COD PROTOCOLO ORIGEM",
            "PROTOCOLO",
            "CÓDIGO DO PROTOCOLO",
            "CODIGO DO PROTOCOLO",
        ],
    )

    col_descricao = localizar_coluna_descricao(
        df_servicos
    )

    if not col_matricula or not col_protocolo or not col_descricao:
        raise ValueError(
            "A planilha de Serviços não possui todas as "
            "informações necessárias. São necessárias as "
            "colunas de matrícula, protocolo e descrição do serviço."
        )

    total = len(df_servicos)
    matriculas_validas = 0
    ignorados = 0

    for _, linha in df_servicos.iterrows():
        matricula = normalizar_matricula(
            linha[col_matricula]
        )

        if not matricula_valida(
            matricula,
            modo,
        ):
            ignorados += 1
            continue

        protocolo = parse_protocolo(
            linha[col_protocolo]
        )

        descricao = (
            ""
            if pd.isna(linha[col_descricao])
            else str(linha[col_descricao]).strip()
        )

        if protocolo is None or not descricao:
            ignorados += 1
            continue

        matriculas_validas += 1

        registro = {
            "matricula": matricula,
            "numero": protocolo["numero"],
            "ano": protocolo["ano"],
            "protocolo": protocolo["original"],
            "descricao": descricao,
            "chave": chave_protocolo(protocolo),
        }

        anterior = resultado.get(matricula)

        if anterior is None:
            resultado[matricula] = registro
            continue

        if registro["chave"] < anterior["chave"]:
            resultado[matricula] = registro

    return resultado, {
        "total": total,
        "matriculas_validas": matriculas_validas,
        "ignorados": ignorados,
    }


# ============================================================
# GERAÇÃO DO LOTE
# ============================================================

def gerar_lote_servicos(
    df_backlog,
    servicos_por_matricula,
    modo,
):
    if df_backlog is None or df_backlog.empty:
        return (
            pd.DataFrame(),
            {
                "total_backlog": 0,
                "matriculas_validas": 0,
                "sem_correspondencia": 0,
                "os_canceladas": 0,
                "protocolos_invalidos": 0,
                "zonas_invalidas": 0,
            },
            [],
        )

    col_matricula = localizar_coluna(
        df_backlog,
        [
            "MATRICULA",
            "MATRÍCULA",
        ],
    )

    col_protocolo = localizar_coluna(
        df_backlog,
        [
            "COD. PROTOCOLO ORIGEM",
            "CÓD. PROTOCOLO ORIGEM",
            "COD PROTOCOLO ORIGEM",
            "PROTOCOLO",
            "CÓDIGO DO PROTOCOLO",
            "CODIGO DO PROTOCOLO",
        ],
    )

    col_cidade = localizar_coluna(
        df_backlog,
        [
            "CIDADE",
        ],
    )

    if not col_matricula or not col_protocolo:
        raise ValueError(
            "O backlog de Falta de Água não possui as "
            "colunas necessárias de matrícula e protocolo."
        )

    if modo == "API" and not col_cidade:
        raise ValueError(
            "O backlog da API não possui a coluna CIDADE, "
            "necessária para determinar a zona."
        )

    lote = []
    avisos = []

    total_backlog = len(df_backlog)
    matriculas_validas = 0
    sem_correspondencia = 0
    protocolos_invalidos = 0
    zonas_invalidas = 0

    for indice, linha in df_backlog.iterrows():
        matricula = normalizar_matricula(
            linha[col_matricula]
        )

        if not matricula_valida(
            matricula,
            modo,
        ):
            continue

        matriculas_validas += 1

        servico = servicos_por_matricula.get(
            matricula
        )

        if servico is None:
            sem_correspondencia += 1
            continue

        protocolo_falta = parse_protocolo(
            linha[col_protocolo]
        )

        if protocolo_falta is None:
            protocolos_invalidos += 1
            avisos.append(
                f"Linha {indice + 2}: protocolo de Falta "
                "de Água inválido ou ausente."
            )
            continue

        if modo == "THE":
            zona = 1
        else:
            cidade = linha[col_cidade]

            if pd.isna(cidade) or not str(cidade).strip():
                zonas_invalidas += 1
                avisos.append(
                    f"Linha {indice + 2}: cidade ausente; "
                    "O.S. não incluída no lote."
                )
                continue

            try:
                zona = obter_zona(
                    str(cidade)
                )
            except Exception:
                zona = None

            if zona is None:
                zonas_invalidas += 1
                avisos.append(
                    f"Linha {indice + 2}: cidade "
                    f"'{cidade}' sem zona cadastrada; "
                    "O.S. não incluída no lote."
                )
                continue

        observacao = (
            "Cliente já possui serviço em aberto: "
            f"{servico['descricao']} - "
            f"O.S. {servico['protocolo']}"
        )

        lote.append(
            {
                COL_SAIDA_MATRICULA: matricula,
                COL_SAIDA_ZONA: zona,
                COL_SAIDA_NUMERO: protocolo_falta["numero"],
                COL_SAIDA_ANO: protocolo_falta["ano"],
                COL_SAIDA_TIPO: 6,
                COL_SAIDA_OBSERVACOES: observacao,
            }
        )

    resultado = pd.DataFrame(
        lote,
        columns=[
            COL_SAIDA_MATRICULA,
            COL_SAIDA_ZONA,
            COL_SAIDA_NUMERO,
            COL_SAIDA_ANO,
            COL_SAIDA_TIPO,
            COL_SAIDA_OBSERVACOES,
        ],
    )

    indicadores = {
        "total_backlog": total_backlog,
        "matriculas_validas": matriculas_validas,
        "sem_correspondencia": sem_correspondencia,
        "os_canceladas": len(resultado),
        "protocolos_invalidos": protocolos_invalidos,
        "zonas_invalidas": zonas_invalidas,
    }

    return resultado, indicadores, avisos


# ============================================================
# ESTADO
# ============================================================

def inicializar_estado_servicos():
    estados = {
        "servicos_resultado_api": None,
        "servicos_resultado_the": None,
        "servicos_indicadores_api": None,
        "servicos_indicadores_the": None,
        "servicos_avisos_api": [],
        "servicos_avisos_the": [],
        "servicos_info_api": None,
        "servicos_info_the": None,
    }

    for chave, valor in estados.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_servicos():
    inicializar_estado_servicos()
    render_sidebar()

    st.title("🛠️ Análise de Serviços")
    st.caption(
        "Cancela O.S. de Falta de Água quando a matrícula "
        "possui Serviço em aberto no mesmo modo."
    )

    st.divider()

    # --------------------------------------------------------
    # MODO API / THE
    # --------------------------------------------------------

    modo = selecionar_modo_api_the(
        key="servicos_modo_api_the"
    )

    if modo not in {"API", "THE"}:
        modo = "API"

    chave_backlog = (
        "api"
        if modo == "API"
        else "the"
    )

    chave_servicos = (
        "servicos_api"
        if modo == "API"
        else "servicos_the"
    )

    df_backlog = obter_base(
        chave_backlog
    )

    df_servicos = obter_base(
        chave_servicos
    )

    # --------------------------------------------------------
    # BASES UTILIZADAS
    # --------------------------------------------------------

    st.subheader("📊 Bases utilizadas")

    col1, col2 = st.columns(2)

    with col1:
        if base_carregada(chave_backlog):
            st.success(
                f"Falta de Água {modo}: "
                f"{len(df_backlog):,} registros"
            )
        else:
            st.warning(
                f"Base de Falta de Água {modo} não carregada."
            )

    with col2:
        if base_carregada(chave_servicos):
            st.success(
                f"Serviços {modo}: "
                f"{len(df_servicos):,} registros"
            )
        else:
            st.warning(
                f"Base de Serviços {modo} não carregada."
            )

    st.divider()

    if not base_carregada(chave_backlog):
        st.info(
            f"Carregue a base de Falta de Água {modo} "
            "no Gerador de Lotes para utilizar esta ferramenta."
        )
        return

    if not base_carregada(chave_servicos):
        st.info(
            f"Carregue a base de Serviços {modo} "
            "no Gerador de Lotes para utilizar esta ferramenta."
        )
        return

    # --------------------------------------------------------
    # EXECUÇÃO
    # --------------------------------------------------------

    st.subheader("🔎 Análise")

    if st.button(
        "▶️ Executar análise",
        type="primary",
        use_container_width=True,
        key="servicos_executar_analise",
    ):
        try:
            with st.spinner(
                "Consolidando Serviços e analisando o backlog..."
            ):
                (
                    servicos_por_matricula,
                    info_servicos,
                ) = consolidar_servicos(
                    df_servicos,
                    modo,
                )

                (
                    resultado,
                    indicadores,
                    avisos,
                ) = gerar_lote_servicos(
                    df_backlog,
                    servicos_por_matricula,
                    modo,
                )

            st.session_state[
                f"servicos_resultado_{modo.lower()}"
            ] = resultado

            st.session_state[
                f"servicos_indicadores_{modo.lower()}"
            ] = indicadores

            st.session_state[
                f"servicos_avisos_{modo.lower()}"
            ] = avisos

            st.session_state[
                f"servicos_info_{modo.lower()}"
            ] = info_servicos

            st.rerun()

        except ValueError as erro:
            st.error(str(erro))
            return

        except Exception as erro:
            st.error(
                "Ocorreu um erro durante a análise."
            )
            st.exception(erro)
            return

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    resultado = st.session_state.get(
        f"servicos_resultado_{modo.lower()}"
    )

    indicadores = st.session_state.get(
        f"servicos_indicadores_{modo.lower()}"
    )

    avisos = st.session_state.get(
        f"servicos_avisos_{modo.lower()}",
        [],
    )

    info_servicos = st.session_state.get(
        f"servicos_info_{modo.lower()}"
    )

    if indicadores is None:
        return

    st.divider()
    st.subheader("📈 Resultado da análise")

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "O.S. no backlog",
        f"{indicadores['total_backlog']:,}",
    )

    m2.metric(
        "Matrículas válidas",
        f"{indicadores['matriculas_validas']:,}",
    )

    m3.metric(
        "O.S. para cancelar",
        f"{indicadores['os_canceladas']:,}",
    )

    m4.metric(
        "Sem Serviço correspondente",
        f"{indicadores['sem_correspondencia']:,}",
    )

    if info_servicos:
        st.caption(
            "Serviços consolidados: "
            f"{info_servicos['matriculas_validas']:,} registros "
            "com matrícula, protocolo e descrição válidos."
        )

        if info_servicos["ignorados"] > 0:
            st.warning(
                f"{info_servicos['ignorados']:,} registro(s) "
                "de Serviços foram ignorados por falta de "
                "informação completa."
            )

    if indicadores["protocolos_invalidos"] > 0:
        st.warning(
            f"{indicadores['protocolos_invalidos']:,} O.S. "
            "não foram incluídas por protocolo inválido."
        )

    if indicadores["zonas_invalidas"] > 0:
        st.warning(
            f"{indicadores['zonas_invalidas']:,} O.S. "
            "não foram incluídas por impossibilidade de "
            "determinar a zona."
        )

    # --------------------------------------------------------
    # AVISOS
    # --------------------------------------------------------

    if avisos:
        with st.expander(
            f"⚠️ Avisos da análise ({len(avisos)})",
            expanded=False,
        ):
            for aviso in avisos:
                st.warning(aviso)

    # --------------------------------------------------------
    # PREVIEW
    # --------------------------------------------------------

    st.subheader("📋 Prévia do lote de cancelamento")

    if resultado is None:
        return

    if resultado.empty:
        st.info(
            "Nenhuma O.S. de Falta de Água possui matrícula "
            "correspondente a um Serviço em aberto."
        )
        return

    st.dataframe(
        resultado.head(100),
        use_container_width=True,
        hide_index=True,
    )

    if len(resultado) > 100:
        st.caption(
            f"Exibindo as primeiras 100 de "
            f"{len(resultado):,} O.S. do lote."
        )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    arquivo = dataframe_para_excel(
        resultado,
        nome_aba="Serviços",
    )

    if arquivo:
        nome_arquivo = (
            NOME_ARQUIVO_API
            if modo == "API"
            else NOME_ARQUIVO_THE
        )

        st.download_button(
            label="⬇️ Baixar lote de cancelamento",
            data=arquivo,
            file_name=nome_arquivo,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
            key=f"servicos_download_{modo.lower()}",
        )

        st.caption(
            "As bases originais permanecem carregadas e "
            "podem ser utilizadas novamente ou alternadas "
            "entre API e THE sem novo upload."
        )
