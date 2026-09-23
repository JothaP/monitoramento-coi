import re
from datetime import datetime

import pandas as pd
import streamlit as st

from ..estado import limpar_resultado
from ..exportacao import dataframe_para_excel
from ..zonas import obter_zona
from .componentes import selecionar_modo_api_the


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_ARQUIVO_API = "Duplicidade API.xlsx"
NOME_ARQUIVO_THE = "Duplicidade THE.xlsx"

COLUNA_PROTOCOLO = "COD. PROTOCOLO ORIGEM"
COLUNA_MATRICULA = "MATRICULA"
COLUNA_DATA = "INÍCIO DO SLA"
COLUNA_CIDADE = "CIDADE"


# ============================================================
# LOCALIZAÇÃO DE COLUNAS
# ============================================================

def localizar_coluna(df, tipo):
    """
    Localiza as colunas necessárias sem alterar os nomes
    existentes no DataFrame.
    """

    mapa = {
        "protocolo": COLUNA_PROTOCOLO,
        "matricula": COLUNA_MATRICULA,
        "data": COLUNA_DATA,
        "cidade": COLUNA_CIDADE,
    }

    procurada = mapa[tipo]

    # Primeiro tenta encontrar exatamente.
    for coluna in df.columns:
        if str(coluna).strip().upper() == procurada.upper():
            return coluna

    # Depois aceita pequenas diferenças de espaços.
    procurada_norm = re.sub(r"\s+", " ", procurada).strip().upper()

    for coluna in df.columns:
        coluna_norm = re.sub(
            r"\s+",
            " ",
            str(coluna),
        ).strip().upper()

        if coluna_norm == procurada_norm:
            return coluna

    return None


# ============================================================
# MATRÍCULA
# ============================================================

def normalizar_matricula(valor):
    """
    Normaliza a matrícula exclusivamente para a regra deste módulo.

    A matrícula válida deve possuir somente dígitos.
    Não são aceitos pontos, hífens, espaços ou outros caracteres.
    """

    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if not texto:
        return ""

    # Trata valores numéricos vindos do Excel como 123456789.0.
    if re.fullmatch(r"\d+\.0", texto):
        texto = texto[:-2]

    if not texto.isdigit():
        return ""

    return texto


def matricula_valida(matricula, modo):
    """
    API  = exatamente 9 dígitos.
    THE  = exatamente 8 dígitos.
    """

    tamanho = 9 if modo == "API" else 8

    return (
        bool(matricula)
        and matricula.isdigit()
        and len(matricula) == tamanho
    )


# ============================================================
# DATA / HORA
# ============================================================

def converter_datas_robusto(serie):
    """
    Converte INÍCIO DO SLA de forma robusta.

    Valores impossíveis ou vazios tornam-se NaT.
    Datas inválidas não provocam erro na análise.
    """

    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]",
    )

    for indice, valor in serie.items():

        if pd.isna(valor):
            continue

        if isinstance(valor, pd.Timestamp):
            if not pd.isna(valor):
                resultado.loc[indice] = valor
            continue

        if isinstance(valor, datetime):
            resultado.loc[indice] = pd.Timestamp(valor)
            continue

        texto = str(valor).strip()

        if not texto:
            continue

        formatos = [
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]

        convertido = None

        for formato in formatos:
            try:
                convertido = datetime.strptime(
                    texto,
                    formato,
                )
                break
            except ValueError:
                continue

        if convertido is not None:
            resultado.loc[indice] = pd.Timestamp(convertido)
            continue

        try:
            convertido = pd.to_datetime(
                texto,
                dayfirst=True,
                errors="coerce",
            )

            if not pd.isna(convertido):
                resultado.loc[indice] = pd.Timestamp(
                    convertido
                )

        except Exception:
            pass

    return resultado


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(valor):
    """
    Retorna:
        número do pedido,
        ano,
        número inteiro usado para ordenação.

    Exemplo:
        1275203/2026
        -> ("1275203", "2026", 1275203)
    """

    if pd.isna(valor):
        return "", "", None

    texto = str(valor).strip()

    match = re.fullmatch(
        r"\s*(\d+)\s*/\s*(\d{4})\s*",
        texto,
    )

    if not match:
        return "", "", None

    numero = match.group(1)
    ano = match.group(2)

    try:
        numero_int = int(numero)
    except Exception:
        numero_int = None

    return numero, ano, numero_int


# ============================================================
# IDENTIFICAÇÃO DAS DUPLICIDADES
# ============================================================

def identificar_duplicidades(df, modo):
    """
    Identifica O.S. duplicadas por matrícula.

    Retorna:
        duplicidades
        mantidos
        estatísticas
        avisos
    """

    if df is None or df.empty:
        raise ValueError(
            f"A base {modo} está vazia."
        )

    col_matricula = localizar_coluna(
        df,
        "matricula",
    )

    col_data = localizar_coluna(
        df,
        "data",
    )

    col_protocolo = localizar_coluna(
        df,
        "protocolo",
    )

    if col_matricula is None:
        raise ValueError(
            "A base não possui a coluna obrigatória "
            f"'{COLUNA_MATRICULA}'."
        )

    if col_data is None:
        raise ValueError(
            "A base não possui a coluna obrigatória "
            f"'{COLUNA_DATA}'."
        )

    if col_protocolo is None:
        raise ValueError(
            "A base não possui a coluna obrigatória "
            f"'{COLUNA_PROTOCOLO}'."
        )

    trabalho = df.copy()

    # --------------------------------------------------------
    # Ordem original da planilha.
    # --------------------------------------------------------

    trabalho["_ORDEM_ORIGINAL_DUP"] = range(
        len(trabalho)
    )

    # --------------------------------------------------------
    # Matrícula normalizada.
    # --------------------------------------------------------

    trabalho["_MATRICULA_NORMALIZADA_DUP"] = (
        trabalho[col_matricula]
        .map(normalizar_matricula)
    )

    total_analisado = len(trabalho)

    mascara_matricula_valida = (
        trabalho["_MATRICULA_NORMALIZADA_DUP"]
        .map(
            lambda valor: matricula_valida(
                valor,
                modo,
            )
        )
    )

    qtd_ignoradas = int(
        (~mascara_matricula_valida).sum()
    )

    validas = trabalho.loc[
        mascara_matricula_valida
    ].copy()

    # --------------------------------------------------------
    # Datas.
    # --------------------------------------------------------

    validas["_DATA_DUP"] = converter_datas_robusto(
        validas[col_data]
    )

    # --------------------------------------------------------
    # Protocolo.
    # --------------------------------------------------------

    protocolos = validas[col_protocolo].map(
        parse_protocolo
    )

    validas["_PROTOCOLO_NUM_DUP"] = protocolos.map(
        lambda valor: valor[2]
    )

    validas["_PROTOCOLO_NUM_STR_DUP"] = protocolos.map(
        lambda valor: valor[0]
    )

    validas["_PROTOCOLO_ANO_DUP"] = protocolos.map(
        lambda valor: valor[1]
    )

    avisos = []

    duplicidades_indices = []
    mantidos_indices = []

    matriculas_com_duplicidade = 0
    qtd_datas_invalidas = int(
        validas["_DATA_DUP"].isna().sum()
    )

    # --------------------------------------------------------
    # Agrupamento por matrícula.
    # --------------------------------------------------------

    for matricula, grupo in validas.groupby(
        "_MATRICULA_NORMALIZADA_DUP",
        sort=False,
    ):

        if len(grupo) <= 1:
            continue

        matriculas_com_duplicidade += 1

        grupo = grupo.copy()

        possui_data_valida = (
            grupo["_DATA_DUP"].notna().any()
        )

        # ----------------------------------------------------
        # Critério de ordenação:
        #
        # 1. Data válida antes de inválida.
        # 2. Data mais antiga.
        # 3. Menor protocolo.
        #
        # A ordem original só é utilizada como último
        # desempate técnico quando não houver protocolo
        # comparável.
        # ----------------------------------------------------

        grupo["_DATA_INVALIDA_ORD_DUP"] = (
            grupo["_DATA_DUP"].isna()
        )

        grupo["_PROTOCOLO_INVALIDO_ORD_DUP"] = (
            grupo["_PROTOCOLO_NUM_DUP"].isna()
        )

        grupo_ordenado = grupo.sort_values(
            by=[
                "_DATA_INVALIDA_ORD_DUP",
                "_DATA_DUP",
                "_PROTOCOLO_INVALIDO_ORD_DUP",
                "_PROTOCOLO_NUM_DUP",
                "_ORDEM_ORIGINAL_DUP",
            ],
            ascending=[
                True,
                True,
                True,
                True,
                True,
            ],
            kind="mergesort",
        )

        original = grupo_ordenado.iloc[0]

        mantidos_indices.append(
            original.name
        )

        # ----------------------------------------------------
        # Todas as datas são inválidas.
        # ----------------------------------------------------

        if not possui_data_valida:
            protocolo_original = str(
                original[col_protocolo]
            ).strip()

            avisos.append(
                {
                    "Matrícula": matricula,
                    "Aviso": (
                        "Todas as O.S. desta matrícula "
                        "possuem 'INÍCIO DO SLA' inválido. "
                        "A O.S. original foi definida pelo "
                        "menor número do protocolo de origem."
                    ),
                    "O.S. mantida": protocolo_original,
                }
            )

        # ----------------------------------------------------
        # Demais O.S. = duplicidades.
        # ----------------------------------------------------

        for indice in grupo_ordenado.index[1:]:
            duplicidades_indices.append(indice)

    # --------------------------------------------------------
    # DataFrames finais.
    # --------------------------------------------------------

    if duplicidades_indices:
        duplicidades = validas.loc[
            duplicidades_indices
        ].copy()
    else:
        duplicidades = validas.iloc[0:0].copy()

    if mantidos_indices:
        mantidos = validas.loc[
            mantidos_indices
        ].copy()
    else:
        mantidos = validas.iloc[0:0].copy()

    # --------------------------------------------------------
    # Remove colunas técnicas dos DataFrames apresentados.
    # --------------------------------------------------------

    colunas_tecnicas = [
        "_ORDEM_ORIGINAL_DUP",
        "_MATRICULA_NORMALIZADA_DUP",
        "_DATA_DUP",
        "_PROTOCOLO_NUM_DUP",
        "_PROTOCOLO_NUM_STR_DUP",
        "_PROTOCOLO_ANO_DUP",
        "_DATA_INVALIDA_ORD_DUP",
        "_PROTOCOLO_INVALIDO_ORD_DUP",
    ]

    duplicidades = duplicidades.drop(
        columns=[
            coluna
            for coluna in colunas_tecnicas
            if coluna in duplicidades.columns
        ],
        errors="ignore",
    )

    mantidos = mantidos.drop(
        columns=[
            coluna
            for coluna in colunas_tecnicas
            if coluna in mantidos.columns
        ],
        errors="ignore",
    )

    # Mantém a ordem original dos resultados.
    duplicidades = duplicidades.sort_index()
    mantidos = mantidos.sort_index()

    estatisticas = {
        "Registros analisados": total_analisado,
        "Matrículas ignoradas": qtd_ignoradas,
        "Matrículas válidas": (
            validas[
                "_MATRICULA_NORMALIZADA_DUP"
            ].nunique()
        ),
        "Matrículas com duplicidade": (
            matriculas_com_duplicidade
        ),
        "O.S. a cancelar": len(duplicidades),
        "O.S. mantidas": len(mantidos),
        "Datas inválidas": qtd_datas_invalidas,
    }

    return (
        duplicidades,
        mantidos,
        estatisticas,
        avisos,
    )


# ============================================================
# GERAÇÃO DO LOTE
# ============================================================

def gerar_lote_cancelamento(
    duplicidades,
    modo,
):
    """
    Converte as duplicidades para o padrão oficial
    de lote de cancelamento da Plataforma COI.
    """

    if duplicidades is None or duplicidades.empty:
        return (
            pd.DataFrame(
                columns=[
                    "Matricula",
                    "Zona Ligacao",
                    "Numero Do Pedido",
                    "Ano Do Pedido",
                    "Tipo Encerramento",
                    "Observações",
                ]
            ),
            [],
        )

    col_matricula = localizar_coluna(
        duplicidades,
        "matricula",
    )

    col_protocolo = localizar_coluna(
        duplicidades,
        "protocolo",
    )

    col_cidade = localizar_coluna(
        duplicidades,
        "cidade",
    )

    if col_matricula is None:
        raise ValueError(
            "Não foi possível localizar a coluna "
            f"'{COLUNA_MATRICULA}' nas duplicidades."
        )

    if col_protocolo is None:
        raise ValueError(
            "Não foi possível localizar a coluna "
            f"'{COLUNA_PROTOCOLO}' nas duplicidades."
        )

    avisos = []
    registros = []

    for _, linha in duplicidades.iterrows():

        matricula = normalizar_matricula(
            linha[col_matricula]
        )

        protocolo = linha[col_protocolo]

        numero, ano, numero_int = parse_protocolo(
            protocolo
        )

        if numero_int is None:
            avisos.append(
                {
                    "Matrícula": matricula,
                    "O.S.": str(protocolo),
                    "Aviso": (
                        "Protocolo de origem inválido. "
                        "A O.S. foi identificada como "
                        "duplicidade, mas não foi incluída "
                        "no lote de cancelamento."
                    ),
                }
            )
            continue

        # ----------------------------------------------------
        # Zona.
        # ----------------------------------------------------

        if modo == "THE":

            zona = 1

        else:

            if col_cidade is None:
                avisos.append(
                    {
                        "Matrícula": matricula,
                        "O.S.": str(protocolo),
                        "Aviso": (
                            "A base API não possui a coluna "
                            f"'{COLUNA_CIDADE}'. "
                            "A O.S. não foi incluída no lote."
                        ),
                    }
                )
                continue

            zona = obter_zona(
                linha[col_cidade]
            )

            if zona is None:
                avisos.append(
                    {
                        "Matrícula": matricula,
                        "O.S.": str(protocolo),
                        "Aviso": (
                            "Não foi possível determinar a "
                            "zona da cidade para esta O.S. "
                            "A O.S. não foi incluída no lote."
                        ),
                    }
                )
                continue

        # ----------------------------------------------------
        # Observação.
        #
        # A observação referencia a O.S. original da
        # matrícula. Ela é preenchida posteriormente na
        # função que possui acesso à relação original.
        # ----------------------------------------------------

        registros.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero,
                "Ano Do Pedido": ano,
                "Tipo Encerramento": 6,
                "Observações": "",
                "_INDICE_ORIGINAL_DUP": _,
            }
        )

    lote = pd.DataFrame(registros)

    if lote.empty:
        return (
            pd.DataFrame(
                columns=[
                    "Matricula",
                    "Zona Ligacao",
                    "Numero Do Pedido",
                    "Ano Do Pedido",
                    "Tipo Encerramento",
                    "Observações",
                ]
            ),
            avisos,
        )

    lote = lote.drop(
        columns=["_INDICE_ORIGINAL_DUP"],
        errors="ignore",
    )

    return lote, avisos


# ============================================================
# RELAÇÃO ORIGINAL x DUPLICIDADE
# ============================================================

def adicionar_observacoes_duplicidade(
    lote,
    duplicidades,
    mantidos,
):
    """
    Preenche a observação de cada duplicidade com a O.S.
    original correspondente à mesma matrícula.
    """

    if lote is None or lote.empty:
        return lote

    col_matricula_dup = localizar_coluna(
        duplicidades,
        "matricula",
    )

    col_protocolo_dup = localizar_coluna(
        duplicidades,
        "protocolo",
    )

    col_matricula_man = localizar_coluna(
        mantidos,
        "matricula",
    )

    col_protocolo_man = localizar_coluna(
        mantidos,
        "protocolo",
    )

    if (
        col_matricula_dup is None
        or col_protocolo_dup is None
        or col_matricula_man is None
        or col_protocolo_man is None
    ):
        return lote

    originais = {}

    for _, linha in mantidos.iterrows():

        matricula = normalizar_matricula(
            linha[col_matricula_man]
        )

        protocolo = linha[col_protocolo_man]

        if matricula:
            originais[matricula] = str(
                protocolo
            ).strip()

    observacoes = []

    for _, linha in lote.iterrows():

        matricula = normalizar_matricula(
            linha["Matricula"]
        )

        protocolo_original = originais.get(
            matricula
        )

        if protocolo_original:
            observacoes.append(
                f"Duplicidade com O.S N. {protocolo_original}"
            )
        else:
            observacoes.append(
                "Duplicidade com O.S N. "
                "(protocolo original não localizado)"
            )

    lote = lote.copy()
    lote["Observações"] = observacoes

    return lote


# ============================================================
# ESTADO DO MÓDULO
# ============================================================

def inicializar_estado_duplicidade():
    """
    Estado específico da ferramenta.

    Os resultados são separados por modo para que a troca
    API/THE não afete as bases originais.
    """

    defaults = {
        "duplicidade_modo_anterior": None,

        "duplicidade_analisada_API": False,
        "duplicidade_analisada_THE": False,

        "duplicidade_duplicidades_API": None,
        "duplicidade_duplicidades_THE": None,

        "duplicidade_mantidos_API": None,
        "duplicidade_mantidos_THE": None,

        "duplicidade_lote_API": None,
        "duplicidade_lote_THE": None,

        "duplicidade_estatisticas_API": None,
        "duplicidade_estatisticas_THE": None,

        "duplicidade_avisos_API": [],
        "duplicidade_avisos_THE": [],

        "duplicidade_nome_API": NOME_ARQUIVO_API,
        "duplicidade_nome_THE": NOME_ARQUIVO_THE,
    }

    for chave, valor in defaults.items():

        if chave not in st.session_state:
            st.session_state[chave] = valor


def chave_modo(prefixo, modo):
    return f"{prefixo}_{modo}"


# ============================================================
# RENDER
# ============================================================

def render_duplicidade():

    inicializar_estado_duplicidade()

    st.title("♻️ Análise de Duplicidade")
    st.caption(
        "Identifique matrículas com mais de uma O.S. "
        "e mantenha somente a O.S. mais antiga."
    )

    st.divider()

    # --------------------------------------------------------
    # Seleção API / THE
    # --------------------------------------------------------

    modo, df = selecionar_modo_api_the(
        key="duplicidade_modo_api_the",
        titulo="Base de operação",
        limpar_resultado_callback=None,
    )

    if modo is None or df is None:
        st.info(
            "Selecione uma base API ou THE carregada "
            "para iniciar a análise."
        )

        st.divider()

        if st.button(
            "⬅️ Voltar ao Hub",
            use_container_width=True,
            key="btn_voltar_hub_duplicidade_sem_base",
        ):
            st.session_state.ferramenta_atual = None
            limpar_resultado()
            st.rerun()

        return

    # --------------------------------------------------------
    # Ao trocar de modo, apenas altera a análise exibida.
    #
    # As bases df_api e df_the permanecem intactas.
    # --------------------------------------------------------

    modo_anterior = st.session_state.get(
        "duplicidade_modo_anterior"
    )

    if modo_anterior != modo:
        st.session_state.duplicidade_modo_anterior = modo

    chave_analisada = chave_modo(
        "duplicidade_analisada",
        modo,
    )

    chave_duplicidades = chave_modo(
        "duplicidade_duplicidades",
        modo,
    )

    chave_mantidos = chave_modo(
        "duplicidade_mantidos",
        modo,
    )

    chave_lote = chave_modo(
        "duplicidade_lote",
        modo,
    )

    chave_estatisticas = chave_modo(
        "duplicidade_estatisticas",
        modo,
    )

    chave_avisos = chave_modo(
        "duplicidade_avisos",
        modo,
    )

    # --------------------------------------------------------
    # Resumo da base
    # --------------------------------------------------------

    st.markdown("### 📊 Base selecionada")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Modo",
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

    # --------------------------------------------------------
    # Critérios
    # --------------------------------------------------------

    st.markdown("### ⚙️ Critérios da análise")

    tamanho_matricula = (
        "9 dígitos"
        if modo == "API"
        else "8 dígitos"
    )

    st.info(
        f"Modo {modo}: somente matrículas com exatamente "
        f"{tamanho_matricula} numéricos participam da "
        "análise de duplicidade. Matrículas inválidas "
        "serão contabilizadas como ignoradas."
    )

    col_crit_1, col_crit_2 = st.columns(2)

    with col_crit_1:
        st.markdown(
            "**Identificação**"
        )
        st.caption(
            "Agrupamento por matrícula válida."
        )

    with col_crit_2:
        st.markdown(
            "**O.S. original**"
        )
        st.caption(
            "Data mais antiga; empate pelo menor "
            "número do protocolo de origem."
        )

    st.divider()

    # --------------------------------------------------------
    # Botão de análise
    # --------------------------------------------------------

    st.markdown("### 🔍 Análise")

    if st.button(
        "🔍 Analisar Duplicidades",
        type="primary",
        use_container_width=True,
        key=f"btn_analisar_duplicidades_{modo}",
    ):

        try:

            (
                duplicidades,
                mantidos,
                estatisticas,
                avisos_data,
            ) = identificar_duplicidades(
                df,
                modo,
            )

            # ------------------------------------------------
            # Geração do lote.
            # ------------------------------------------------

            lote, avisos_lote = gerar_lote_cancelamento(
                duplicidades,
                modo,
            )

            lote = adicionar_observacoes_duplicidade(
                lote,
                duplicidades,
                mantidos,
            )

            avisos = (
                avisos_data
                + avisos_lote
            )

            st.session_state[
                chave_duplicidades
            ] = duplicidades

            st.session_state[
                chave_mantidos
            ] = mantidos

            st.session_state[
                chave_lote
            ] = lote

            st.session_state[
                chave_estatisticas
            ] = estatisticas

            st.session_state[
                chave_avisos
            ] = avisos

            st.session_state[
                chave_analisada
            ] = True

            st.success(
                "✓ Análise de duplicidade concluída."
            )

        except Exception as erro:

            st.session_state[
                chave_analisada
            ] = False

            st.session_state[
                chave_duplicidades
            ] = None

            st.session_state[
                chave_mantidos
            ] = None

            st.session_state[
                chave_lote
            ] = None

            st.error(
                f"❌ Não foi possível realizar a análise: "
                f"{erro}"
            )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

    analisada = st.session_state.get(
        chave_analisada,
        False,
    )

    if analisada:

        duplicidades = st.session_state.get(
            chave_duplicidades
        )

        mantidos = st.session_state.get(
            chave_mantidos
        )

        lote = st.session_state.get(
            chave_lote
        )

        estatisticas = st.session_state.get(
            chave_estatisticas
        ) or {}

        avisos = st.session_state.get(
            chave_avisos,
            [],
        )

        st.divider()

        st.markdown("### 📋 Resultado da análise")

        # ----------------------------------------------------
        # Indicadores
        # ----------------------------------------------------

        colunas_metricas = st.columns(4)

        with colunas_metricas[0]:
            st.metric(
                "Registros analisados",
                str(
                    estatisticas.get(
                        "Registros analisados",
                        0,
                    )
                ),
            )

        with colunas_metricas[1]:
            st.metric(
                "Matrículas ignoradas",
                str(
                    estatisticas.get(
                        "Matrículas ignoradas",
                        0,
                    )
                ),
            )

        with colunas_metricas[2]:
            st.metric(
                "Matrículas com duplicidade",
                str(
                    estatisticas.get(
                        "Matrículas com duplicidade",
                        0,
                    )
                ),
            )

        with colunas_metricas[3]:
            st.metric(
                "O.S. a cancelar",
                str(
                    estatisticas.get(
                        "O.S. a cancelar",
                        0,
                    )
                ),
            )

        colunas_metricas_2 = st.columns(3)

        with colunas_metricas_2[0]:
            st.metric(
                "O.S. mantidas",
                str(
                    estatisticas.get(
                        "O.S. mantidas",
                        0,
                    )
                ),
            )

        with colunas_metricas_2[1]:
            st.metric(
                "Matrículas válidas",
                str(
                    estatisticas.get(
                        "Matrículas válidas",
                        0,
                    )
                ),
            )

        with colunas_metricas_2[2]:
            st.metric(
                "Datas inválidas",
                str(
                    estatisticas.get(
                        "Datas inválidas",
                        0,
                    )
                ),
            )

        # ----------------------------------------------------
        # Avisos
        # ----------------------------------------------------

        if avisos:

            st.warning(
                f"⚠️ {len(avisos)} aviso(s) registrado(s)."
            )

            with st.expander(
                "Ver avisos do processamento"
            ):

                st.dataframe(
                    pd.DataFrame(avisos),
                    use_container_width=True,
                    hide_index=True,
                )

        # ----------------------------------------------------
        # Prévia das duplicidades
        # ----------------------------------------------------

        st.markdown(
            "#### 🔎 Prévia das O.S. a cancelar"
        )

        if duplicidades is None or duplicidades.empty:

            st.success(
                "✓ Nenhuma duplicidade encontrada."
            )

        else:

            st.caption(
                "Amostra das 10 primeiras O.S. "
                "identificadas como duplicidade."
            )

            st.dataframe(
                duplicidades.head(10),
                use_container_width=True,
                hide_index=True,
            )

        # ----------------------------------------------------
        # O.S. mantidas
        # ----------------------------------------------------

        with st.expander(
            "📌 Ver O.S. mantidas"
        ):

            if mantidos is None or mantidos.empty:

                st.info(
                    "Nenhuma O.S. mantida."
                )

            else:

                st.dataframe(
                    mantidos,
                    use_container_width=True,
                    hide_index=True,
                )

        # ----------------------------------------------------
        # Lote
        # ----------------------------------------------------

        st.divider()

        st.markdown(
            "### 📦 Lote de cancelamento"
        )

        if lote is None or lote.empty:

            st.info(
                "Nenhuma O.S. válida foi produzida "
                "para o lote de cancelamento."
            )

        else:

            st.caption(
                f"{len(lote):,} O.S. serão incluídas "
                "no lote.".replace(",", ".")
            )

            st.dataframe(
                lote,
                use_container_width=True,
                hide_index=True,
            )

            nome_arquivo = (
                NOME_ARQUIVO_API
                if modo == "API"
                else NOME_ARQUIVO_THE
            )

            arquivo_excel = dataframe_para_excel(
                lote,
                nome_aba="Duplicidade",
            )

            if arquivo_excel is not None:

                st.download_button(
                    "⬇️ Baixar lote",
                    data=arquivo_excel,
                    file_name=nome_arquivo,
                    mime=(
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                    key=f"btn_download_duplicidade_{modo}",
                )

        # ----------------------------------------------------
        # Limpar somente a análise do modo atual
        # ----------------------------------------------------

        st.divider()

        col_limpar_1, col_limpar_2 = st.columns(2)

        with col_limpar_1:

            if st.button(
                "🗑️ Limpar análise",
                use_container_width=True,
                key=f"btn_limpar_analise_duplicidade_{modo}",
            ):

                st.session_state[
                    chave_analisada
                ] = False

                st.session_state[
                    chave_duplicidades
                ] = None

                st.session_state[
                    chave_mantidos
                ] = None

                st.session_state[
                    chave_lote
                ] = None

                st.session_state[
                    chave_estatisticas
                ] = None

                st.session_state[
                    chave_avisos
                ] = []

                st.rerun()

        with col_limpar_2:

            if st.button(
                "🔄 Nova análise",
                use_container_width=True,
                key=f"btn_nova_analise_duplicidade_{modo}",
            ):

                st.session_state[
                    chave_analisada
                ] = False

                st.session_state[
                    chave_duplicidades
                ] = None

                st.session_state[
                    chave_mantidos
                ] = None

                st.session_state[
                    chave_lote
                ] = None

                st.session_state[
                    chave_estatisticas
                ] = None

                st.session_state[
                    chave_avisos
                ] = []

                st.rerun()

    # --------------------------------------------------------
    # Retorno
    # --------------------------------------------------------

    st.divider()

    if st.button(
        "⬅️ Voltar ao Hub",
        use_container_width=True,
        key="btn_voltar_hub_duplicidade",
    ):

        st.session_state.ferramenta_atual = None

        # Importante:
        # não limpa df_api nem df_the.
        limpar_resultado()

        st.rerun()
