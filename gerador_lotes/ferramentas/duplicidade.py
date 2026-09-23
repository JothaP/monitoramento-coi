```python
import re
import unicodedata
from datetime import datetime

import pandas as pd
import streamlit as st

from ..exportacao import dataframe_para_excel
from ..zonas import obter_zona
from .componentes import selecionar_modo_api_the


# ============================================================
# CONFIGURAÇÕES
# ============================================================

NOME_ARQUIVO_API = "Duplicidade API.xlsx"
NOME_ARQUIVO_THE = "Duplicidade THE.xlsx"

COL_MATRICULA_PADRAO = "Matrícula"
COL_PROTOCOLO_PADRAO = "Cód. Protocolo Origem"
COL_DATA_PADRAO = "INÍCIO DO SLA"
COL_CIDADE_PADRAO = "Cidade"


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

def normalizar_texto(valor):
    if valor is None:
        return ""

    texto = str(valor).strip()

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return texto.upper()


# ============================================================
# LOCALIZAÇÃO DAS COLUNAS
# ============================================================

def localizar_coluna(df, tipo):
    colunas = list(df.columns)

    normalizadas = {
        coluna: normalizar_texto(coluna)
        for coluna in colunas
    }

    if tipo == "matricula":
        candidatos_exatos = [
            "MATRICULA",
        ]

        for coluna, normalizada in normalizadas.items():
            if normalizada in candidatos_exatos:
                return coluna

        for coluna, normalizada in normalizadas.items():
            if "MATRICULA" in normalizada:
                return coluna

        return None

    if tipo == "protocolo":
        candidatos_exatos = [
            "COD. PROTOCOLO ORIGEM",
            "COD PROTOCOLO ORIGEM",
        ]

        for coluna, normalizada in normalizadas.items():
            if normalizada in candidatos_exatos:
                return coluna

        for coluna, normalizada in normalizadas.items():
            if "PROTOCOLO" in normalizada and "ORIGEM" in normalizada:
                return coluna

        return None

    if tipo == "data":
        # REGRA INQUEBRÁVEL:
        # somente INÍCIO DO SLA pode ser utilizado.
        # A coluna "Data" jamais deve ser utilizada.

        candidatos_exatos = [
            "INICIO DO SLA",
            "INICIO SLA",
        ]

        for coluna, normalizada in normalizadas.items():
            if normalizada in candidatos_exatos:
                return coluna

        for coluna, normalizada in normalizadas.items():
            if (
                "INICIO DO SLA" in normalizada
                or "INICIO SLA" in normalizada
            ):
                return coluna

        return None

    if tipo == "cidade":
        for coluna, normalizada in normalizadas.items():
            if normalizada == "CIDADE":
                return coluna

        return None

    return None


# ============================================================
# NORMALIZAÇÃO / VALIDAÇÃO DA MATRÍCULA
# ============================================================

def normalizar_matricula(valor):
    if pd.isna(valor):
        return None

    if isinstance(valor, bool):
        return None

    if isinstance(valor, int):
        texto = str(valor)

    elif isinstance(valor, float):
        if not valor.is_integer():
            return None

        texto = str(int(valor))

    else:
        texto = str(valor).strip()

    # Não remover pontuação.
    # A matrícula deve ser composta exclusivamente por números.
    if not texto.isdigit():
        return None

    return texto


def matricula_valida(valor, modo):
    matricula = normalizar_matricula(valor)

    if matricula is None:
        return None

    tamanho_esperado = 9 if modo == "API" else 8

    if len(matricula) != tamanho_esperado:
        return None

    return matricula


# ============================================================
# CONVERSÃO ROBUSTA DE DATAS
# ============================================================

def converter_datas_robusto(serie):
    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]",
    )

    # Datas que já sejam datetime
    mascara_datetime = serie.apply(
        lambda valor: isinstance(valor, (datetime, pd.Timestamp))
    )

    if mascara_datetime.any():
        resultado.loc[mascara_datetime] = pd.to_datetime(
            serie.loc[mascara_datetime],
            errors="coerce",
        )

    # Datas numéricas do Excel
    mascara_numerica = (
        ~mascara_datetime
        & pd.to_numeric(serie, errors="coerce").notna()
    )

    if mascara_numerica.any():
        valores_numericos = pd.to_numeric(
            serie.loc[mascara_numerica],
            errors="coerce",
        )

        resultado.loc[mascara_numerica] = pd.to_datetime(
            valores_numericos,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )

    # Texto
    mascara_texto = ~mascara_datetime & ~mascara_numerica

    if mascara_texto.any():
        valores_texto = (
            serie.loc[mascara_texto]
            .astype(str)
            .str.strip()
        )

        # Formato brasileiro
        resultado.loc[mascara_texto] = pd.to_datetime(
            valores_texto,
            format="%d/%m/%Y %H:%M:%S",
            errors="coerce",
        )

        faltantes = (
            mascara_texto
            & resultado.isna()
        )

        if faltantes.any():
            valores_texto = (
                serie.loc[faltantes]
                .astype(str)
                .str.strip()
            )

            resultado.loc[faltantes] = pd.to_datetime(
                valores_texto,
                format="%d/%m/%Y %H:%M",
                errors="coerce",
            )

        faltantes = resultado.isna() & mascara_texto

        if faltantes.any():
            valores_texto = (
                serie.loc[faltantes]
                .astype(str)
                .str.strip()
            )

            resultado.loc[faltantes] = pd.to_datetime(
                valores_texto,
                format="%d/%m/%Y",
                errors="coerce",
            )

        faltantes = resultado.isna() & mascara_texto

        if faltantes.any():
            valores_texto = (
                serie.loc[faltantes]
                .astype(str)
                .str.strip()
            )

            resultado.loc[faltantes] = pd.to_datetime(
                valores_texto,
                format="%Y-%m-%d %H:%M:%S",
                errors="coerce",
            )

        faltantes = resultado.isna() & mascara_texto

        if faltantes.any():
            valores_texto = (
                serie.loc[faltantes]
                .astype(str)
                .str.strip()
            )

            resultado.loc[faltantes] = pd.to_datetime(
                valores_texto,
                format="%Y-%m-%d %H:%M",
                errors="coerce",
            )

        faltantes = resultado.isna() & mascara_texto

        if faltantes.any():
            valores_texto = (
                serie.loc[faltantes]
                .astype(str)
                .str.strip()
            )

            resultado.loc[faltantes] = pd.to_datetime(
                valores_texto,
                errors="coerce",
                dayfirst=True,
            )

    return resultado


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(valor):
    if pd.isna(valor):
        return None, None, None

    texto = str(valor).strip()

    if not texto:
        return None, None, None

    correspondencia = re.match(
        r"^\s*(\d+)\s*/\s*(\d+)\s*$",
        texto,
    )

    if not correspondencia:
        return None, None, None

    numero = correspondencia.group(1)
    ano = correspondencia.group(2)

    try:
        numero_int = int(numero)
    except Exception:
        numero_int = None

    return numero, ano, numero_int


# ============================================================
# IDENTIFICAÇÃO DAS DUPLICIDADES
# ============================================================

def identificar_duplicidades(df, modo):
    if df is None or df.empty:
        raise ValueError("A base de operação está vazia.")

    coluna_matricula = localizar_coluna(df, "matricula")
    coluna_protocolo = localizar_coluna(df, "protocolo")
    coluna_data = localizar_coluna(df, "data")
    coluna_cidade = localizar_coluna(df, "cidade")

    colunas_obrigatorias = []

    if coluna_matricula is None:
        colunas_obrigatorias.append(COL_MATRICULA_PADRAO)

    if coluna_protocolo is None:
        colunas_obrigatorias.append(COL_PROTOCOLO_PADRAO)

    if coluna_data is None:
        colunas_obrigatorias.append(COL_DATA_PADRAO)

    if modo == "API" and coluna_cidade is None:
        colunas_obrigatorias.append(COL_CIDADE_PADRAO)

    if colunas_obrigatorias:
        raise ValueError(
            "A base não possui a(s) coluna(s) obrigatória(s): "
            + ", ".join(colunas_obrigatorias)
        )

    trabalho = df.copy()

    trabalho["_ORDEM_ORIGINAL"] = range(len(trabalho))

    # --------------------------------------------------------
    # MATRÍCULA
    # --------------------------------------------------------

    trabalho["_MATRICULA_NORMALIZADA"] = trabalho[
        coluna_matricula
    ].apply(
        lambda valor: matricula_valida(valor, modo)
    )

    trabalho["_MATRICULA_VALIDA"] = (
        trabalho["_MATRICULA_NORMALIZADA"].notna()
    )

    registros_ignorados = trabalho[
        ~trabalho["_MATRICULA_VALIDA"]
    ].copy()

    registros_validos = trabalho[
        trabalho["_MATRICULA_VALIDA"]
    ].copy()

    total_registros = len(trabalho)
    total_matriculas_validas = len(registros_validos)
    total_matriculas_ignoradas = len(registros_ignorados)

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------
    # Somente INÍCIO DO SLA.
    # A coluna "Data" não participa desta análise.

    registros_validos["_DATA_SLA"] = converter_datas_robusto(
        registros_validos[coluna_data]
    )

    registros_validos["_DATA_INVALIDA"] = (
        registros_validos["_DATA_SLA"].isna()
    )

    total_datas_invalidas = int(
        registros_validos["_DATA_INVALIDA"].sum()
    )

    # --------------------------------------------------------
    # PROTOCOLO
    # --------------------------------------------------------

    protocolos = registros_validos[coluna_protocolo].apply(
        parse_protocolo
    )

    registros_validos["_PROTOCOLO_NUMERO"] = protocolos.apply(
        lambda item: item[2]
    )

    registros_validos["_PROTOCOLO_NUMERO_TEXTO"] = protocolos.apply(
        lambda item: item[0]
    )

    registros_validos["_PROTOCOLO_ANO"] = protocolos.apply(
        lambda item: item[1]
    )

    registros_validos["_PROTOCOLO_INVALIDO"] = (
        registros_validos["_PROTOCOLO_NUMERO"].isna()
    )

    # --------------------------------------------------------
    # GRUPOS COM DUPLICIDADE
    # --------------------------------------------------------

    contagem_por_matricula = (
        registros_validos
        .groupby("_MATRICULA_NORMALIZADA", dropna=False)
        .size()
    )

    matriculas_duplicadas = contagem_por_matricula[
        contagem_por_matricula > 1
    ].index

    grupos_duplicados = len(matriculas_duplicadas)

    duplicados_candidatos = registros_validos[
        registros_validos["_MATRICULA_NORMALIZADA"].isin(
            matriculas_duplicadas
        )
    ].copy()

    # --------------------------------------------------------
    # ORDENAMENTO PARA DEFINIÇÃO DA O.S. ORIGINAL
    # --------------------------------------------------------
    #
    # 1. Data válida tem prioridade sobre data inválida.
    # 2. Entre datas válidas, a mais antiga.
    # 3. Empate na data: menor número do protocolo.
    # 4. Protocolo inválido fica depois dos protocolos válidos.
    # 5. Último critério técnico: ordem original da planilha.
    #
    # A ordem original NÃO é utilizada para decidir entre datas
    # ou protocolos válidos; somente como desempate técnico final.

    duplicados_candidatos = duplicados_candidatos.sort_values(
        by=[
            "_MATRICULA_NORMALIZADA",
            "_DATA_INVALIDA",
            "_DATA_SLA",
            "_PROTOCOLO_INVALIDO",
            "_PROTOCOLO_NUMERO",
            "_ORDEM_ORIGINAL",
        ],
        ascending=[
            True,
            True,
            True,
            True,
            True,
            True,
        ],
        na_position="last",
        kind="mergesort",
    )

    # --------------------------------------------------------
    # ORIGINAL / MANTIDA
    # --------------------------------------------------------

    mantidos = (
        duplicados_candidatos
        .groupby(
            "_MATRICULA_NORMALIZADA",
            as_index=False,
            sort=False,
        )
        .head(1)
        .copy()
    )

    chaves_mantidas = set(
        zip(
            mantidos["_MATRICULA_NORMALIZADA"],
            mantidos["_ORDEM_ORIGINAL"],
        )
    )

    duplicados = duplicados_candidatos[
        ~duplicados_candidatos.apply(
            lambda linha: (
                linha["_MATRICULA_NORMALIZADA"],
                linha["_ORDEM_ORIGINAL"],
            ) in chaves_mantidas,
            axis=1,
        )
    ].copy()

    total_os_cancelar = len(duplicados)
    total_os_mantidas = len(mantidos)

    # --------------------------------------------------------
    # AVISOS
    # --------------------------------------------------------

    avisos = []

    grupos_todos_sem_data = (
        duplicados_candidatos
        .groupby("_MATRICULA_NORMALIZADA")["_DATA_SLA"]
        .apply(lambda serie: serie.isna().all())
    )

    matriculas_sem_data = list(
        grupos_todos_sem_data[
            grupos_todos_sem_data
        ].index
    )

    for matricula in matriculas_sem_data:
        quantidade = int(
            (
                duplicados_candidatos[
                    "_MATRICULA_NORMALIZADA"
                ] == matricula
            ).sum()
        )

        avisos.append(
            f"Matrícula {matricula}: todas as {quantidade} "
            "O.S. possuem INÍCIO DO SLA inválido. "
            "Foi mantida a O.S. com menor número de protocolo "
            "válido; em caso de empate técnico, foi utilizado "
            "critério de estabilidade."
        )

    if total_datas_invalidas:
        avisos.append(
            f"{total_datas_invalidas} registro(s) com "
            "INÍCIO DO SLA inválido foram considerados após "
            "as datas válidas na definição da O.S. original."
        )

    # --------------------------------------------------------
    # LIMPEZA DOS DATAFRAMES DE SAÍDA
    # --------------------------------------------------------

    colunas_internas = [
        "_ORDEM_ORIGINAL",
        "_MATRICULA_NORMALIZADA",
        "_MATRICULA_VALIDA",
        "_DATA_SLA",
        "_DATA_INVALIDA",
        "_PROTOCOLO_NUMERO",
        "_PROTOCOLO_NUMERO_TEXTO",
        "_PROTOCOLO_ANO",
        "_PROTOCOLO_INVALIDO",
    ]

    duplicados_saida = duplicados.drop(
        columns=[
            coluna
            for coluna in colunas_internas
            if coluna in duplicados.columns
        ],
        errors="ignore",
    ).copy()

    mantidos_saida = mantidos.drop(
        columns=[
            coluna
            for coluna in colunas_internas
            if coluna in mantidos.columns
        ],
        errors="ignore",
    ).copy()

    ignorados_saida = registros_ignorados.drop(
        columns=[
            coluna
            for coluna in colunas_internas
            if coluna in registros_ignorados.columns
        ],
        errors="ignore",
    ).copy()

    return {
        "duplicados": duplicados_saida,
        "mantidos": mantidos_saida,
        "ignorados": ignorados_saida,
        "total_registros": total_registros,
        "total_matriculas_validas": total_matriculas_validas,
        "total_matriculas_ignoradas": total_matriculas_ignoradas,
        "grupos_duplicados": grupos_duplicados,
        "total_os_cancelar": total_os_cancelar,
        "total_os_mantidas": total_os_mantidas,
        "total_datas_invalidas": total_datas_invalidas,
        "avisos": avisos,
        "coluna_matricula": coluna_matricula,
        "coluna_protocolo": coluna_protocolo,
        "coluna_data": coluna_data,
        "coluna_cidade": coluna_cidade,
    }


# ============================================================
# GERAÇÃO DO LOTE DE CANCELAMENTO
# ============================================================

def gerar_lote_cancelamento(
    resultado_analise,
    modo,
):
    duplicados = resultado_analise["duplicados"]
    mantidos = resultado_analise["mantidos"]

    if duplicados.empty:
        return pd.DataFrame(
            columns=[
                "Matricula",
                "Zona Ligacao",
                "Numero Do Pedido",
                "Ano Do Pedido",
                "Tipo Encerramento",
                "Observações",
            ]
        )

    coluna_matricula = resultado_analise["coluna_matricula"]
    coluna_protocolo = resultado_analise["coluna_protocolo"]
    coluna_cidade = resultado_analise["coluna_cidade"]

    # --------------------------------------------------------
    # MAPA DA O.S. ORIGINAL MANTIDA
    # --------------------------------------------------------

    mantidos_mapa = {}

    for _, linha in mantidos.iterrows():
        matricula = matricula_valida(
            linha[coluna_matricula],
            modo,
        )

        if matricula is None:
            continue

        protocolo_original = linha[coluna_protocolo]

        if pd.isna(protocolo_original):
            protocolo_original = ""

        mantidos_mapa[matricula] = str(
            protocolo_original
        ).strip()

    # --------------------------------------------------------
    # LOTE
    # --------------------------------------------------------

    registros_lote = []

    for _, linha in duplicados.iterrows():
        matricula = matricula_valida(
            linha[coluna_matricula],
            modo,
        )

        if matricula is None:
            continue

        protocolo = linha[coluna_protocolo]

        if pd.isna(protocolo):
            protocolo = ""

        protocolo = str(protocolo).strip()

        numero_pedido, ano_pedido, _ = parse_protocolo(
            protocolo
        )

        if numero_pedido is None:
            numero_pedido = ""

        if ano_pedido is None:
            ano_pedido = ""

        protocolo_original = mantidos_mapa.get(
            matricula,
            "",
        )

        observacao = (
            f"Duplicidade com O.S N. {protocolo_original}"
        )

        if modo == "THE":
            zona = 1
        else:
            cidade = linha[coluna_cidade]

            if pd.isna(cidade):
                cidade = ""

            zona = obter_zona(str(cidade).strip())

        registros_lote.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_pedido,
                "Ano Do Pedido": ano_pedido,
                "Tipo Encerramento": 6,
                "Observações": observacao,
            }
        )

    return pd.DataFrame(
        registros_lote,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações",
        ],
    )


# ============================================================
# NAVEGAÇÃO
# ============================================================

def render_botoes_retorno(modo):
    st.divider()

    col_ret1, col_ret2 = st.columns(2)

    with col_ret1:
        if st.button(
            "⬅️ Voltar às Ferramentas",
            width="stretch",
            key=f"duplicidade_voltar_ferramentas_{modo.lower()}",
        ):
            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )

    with col_ret2:
        if st.button(
            "🏠 Voltar ao Gerador de Lotes",
            width="stretch",
            key=f"duplicidade_voltar_hub_{modo.lower()}",
        ):
            st.switch_page(
                "pages/4_1_Gerador_Lotes_Cancelamento.py"
            )


# ============================================================
# INTERFACE PRINCIPAL
# ============================================================

def render_duplicidade():
    st.title("🔄 Duplicidade")
    st.caption(
        "Identificação de O.S. duplicadas por matrícula, "
        "mantendo a ocorrência mais antiga e gerando lote "
        "de cancelamento para as demais."
    )

    # ========================================================
    # SELEÇÃO API / THE
    # ========================================================

    modo = selecionar_modo_api_the(
        key="duplicidade_modo_api_the",
        titulo="Base de operação",
        limpar_resultado_callback=None,
    )

    # ========================================================
    # BASE ATIVA
    # ========================================================

    df_base = (
        st.session_state.get("df_the")
        if modo == "THE"
        else st.session_state.get("df_api")
    )

    if df_base is None or df_base.empty:
        st.warning(
            f"Nenhuma base {modo} está carregada."
        )

        st.info(
            "Carregue a base no Hub do Gerador de Lotes "
            "antes de executar a análise."
        )

        render_botoes_retorno(modo)
        return

    # ========================================================
    # ESTADO ESPECÍFICO POR MODO
    # ========================================================

    chave_resultado = (
        f"duplicidade_resultado_{modo.lower()}"
    )

    chave_lote = (
        f"duplicidade_lote_{modo.lower()}"
    )

    chave_mantidos = (
        f"duplicidade_mantidos_{modo.lower()}"
    )

    chave_ignorados = (
        f"duplicidade_ignorados_{modo.lower()}"
    )

    chave_analisada = (
        f"duplicidade_analisada_{modo.lower()}"
    )

    if chave_analisada not in st.session_state:
        st.session_state[chave_analisada] = False

    # ========================================================
    # RESUMO DA BASE
    # ========================================================

    st.markdown("### 📊 Base ativa")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Registros na base",
            f"{len(df_base):,}".replace(",", "."),
        )

    with col2:
        st.metric(
            "Colunas",
            f"{len(df_base.columns):,}".replace(",", "."),
        )

    with col3:
        st.metric(
            "Modo",
            modo,
        )

    # ========================================================
    # REGRAS
    # ========================================================

    with st.expander(
        "ℹ️ Regras utilizadas na análise",
        expanded=False,
    ):
        st.markdown(
            """
            **Backlog analisado:** base ativa carregada para o modo selecionado.

            **Matrícula:**
            - API: exatamente 9 dígitos numéricos.
            - THE: exatamente 8 dígitos numéricos.
            - Matrículas vazias ou inválidas são ignoradas da análise
              de duplicidade e contabilizadas separadamente.

            **Data:**
            - A única referência de data/hora utilizada é
              **INÍCIO DO SLA**.
            - A coluna **Data nunca é utilizada**.

            **Definição da O.S. original:**
            1. INÍCIO DO SLA válido tem prioridade.
            2. Entre datas válidas, permanece a mais antiga.
            3. Em empate, permanece o menor número do protocolo.
            4. O.S. com data inválida nunca é escolhida enquanto houver
               uma O.S. com data válida para a mesma matrícula.
            5. Se todas as datas forem inválidas, é utilizado o menor
               número de protocolo válido.

            **Duplicadas:** todas as demais O.S. da mesma matrícula.

            **Cancelamento:** Tipo Encerramento = 6.

            **Observação automática:**
            `Duplicidade com O.S N. {protocolo da original}`

            **Zona:**
            - API: determinada pela cidade.
            - THE: zona 1.

            A base original permanece preservada durante toda a sessão.
            """
        )

    # ========================================================
    # ANÁLISE
    # ========================================================

    if st.button(
        "🔍 Analisar Duplicidades",
        type="primary",
        width="stretch",
        key=f"duplicidade_analisar_{modo.lower()}",
    ):
        try:
            with st.spinner(
                "Analisando duplicidades..."
            ):
                resultado = identificar_duplicidades(
                    df_base,
                    modo,
                )

                lote = gerar_lote_cancelamento(
                    resultado,
                    modo,
                )

            st.session_state[chave_resultado] = resultado
            st.session_state[chave_lote] = lote
            st.session_state[chave_mantidos] = (
                resultado["mantidos"]
            )
            st.session_state[chave_ignorados] = (
                resultado["ignorados"]
            )
            st.session_state[chave_analisada] = True

            st.success(
                "Análise de duplicidades concluída."
            )

        except Exception as erro:
            st.error(
                f"Não foi possível realizar a análise: {erro}"
            )

            st.session_state[chave_analisada] = False

            render_botoes_retorno(modo)
            return

    # ========================================================
    # RESULTADOS
    # ========================================================

    if not st.session_state.get(
        chave_analisada,
        False,
    ):
        render_botoes_retorno(modo)
        return

    resultado = st.session_state.get(
        chave_resultado
    )

    lote = st.session_state.get(
        chave_lote
    )

    mantidos = st.session_state.get(
        chave_mantidos
    )

    ignorados = st.session_state.get(
        chave_ignorados
    )

    if resultado is None:
        render_botoes_retorno(modo)
        return

    # ========================================================
    # MÉTRICAS
    # ========================================================

    st.markdown("### 📈 Resultado da análise")

    m1, m2, m3 = st.columns(3)

    with m1:
        st.metric(
            "Registros analisados",
            f"{resultado['total_registros']:,}".replace(
                ",", "."
            ),
        )

    with m2:
        st.metric(
            "Matrículas válidas",
            f"{resultado['total_matriculas_validas']:,}".replace(
                ",", "."
            ),
        )

    with m3:
        st.metric(
            "Matrículas ignoradas",
            f"{resultado['total_matriculas_ignoradas']:,}".replace(
                ",", "."
            ),
        )

    m4, m5, m6 = st.columns(3)

    with m4:
        st.metric(
            "Grupos com duplicidade",
            f"{resultado['grupos_duplicados']:,}".replace(
                ",", "."
            ),
        )

    with m5:
        st.metric(
            "O.S. a cancelar",
            f"{resultado['total_os_cancelar']:,}".replace(
                ",", "."
            ),
        )

    with m6:
        st.metric(
            "O.S. mantidas",
            f"{resultado['total_os_mantidas']:,}".replace(
                ",", "."
            ),
        )

    # ========================================================
    # DATAS INVÁLIDAS
    # ========================================================

    if resultado["total_datas_invalidas"] > 0:
        st.warning(
            f"Foram identificados "
            f"{resultado['total_datas_invalidas']:,}".replace(
                ",", "."
            )
            + " registro(s) com INÍCIO DO SLA inválido."
        )

    # ========================================================
    # AVISOS
    # ========================================================

    avisos = resultado.get(
        "avisos",
        [],
    )

    if avisos:
        with st.expander(
            f"⚠️ Avisos da análise ({len(avisos)})",
            expanded=False,
        ):
            for aviso in avisos:
                st.warning(aviso)

    # ========================================================
    # MATRÍCULAS IGNORADAS
    # ========================================================

    with st.expander(
        f"⚠️ Matrículas ignoradas "
        f"({resultado['total_matriculas_ignoradas']:,})".replace(
            ",", "."
        ),
        expanded=False,
    ):
        if ignorados is not None and not ignorados.empty:
            st.caption(
                "Registros com matrícula vazia, não numérica "
                "ou com quantidade de dígitos diferente do "
                "padrão do modo selecionado."
            )

            st.dataframe(
                ignorados,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "Nenhuma matrícula foi ignorada."
            )

    # ========================================================
    # O.S. DUPLICADAS
    # ========================================================

    duplicados = resultado["duplicados"]

    st.markdown("### 🔴 O.S. identificadas como duplicadas")

    if duplicados.empty:
        st.info(
            "Nenhuma duplicidade foi encontrada na base ativa."
        )
    else:
        st.caption(
            "Prévia das primeiras 10 O.S. que serão canceladas."
        )

        st.dataframe(
            duplicados.head(10),
            width="stretch",
            hide_index=True,
        )

    # ========================================================
    # O.S. MANTIDAS
    # ========================================================

    st.markdown("### 🟢 O.S. mantidas")

    if mantidos is None or mantidos.empty:
        st.info(
            "Nenhuma O.S. foi mantida como original."
        )
    else:
        st.caption(
            "Uma O.S. original é mantida para cada matrícula "
            "que apresentou duplicidade."
        )

        st.dataframe(
            mantidos,
            width="stretch",
            hide_index=True,
        )

    # ========================================================
    # LOTE DE CANCELAMENTO
    # ========================================================

    st.markdown("### 📦 Lote de cancelamento")

    if lote is None or lote.empty:
        st.info(
            "Não há O.S. duplicadas para gerar lote."
        )
    else:
        st.dataframe(
            lote,
            width="stretch
```
