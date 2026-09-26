import io
import re

import pandas as pd
import streamlit as st


# ============================================================
# FUNÇÕES GERAIS
# ============================================================

def _normalizar_coluna(nome):
    return re.sub(r"\s+", " ", str(nome).strip()).casefold()


def _ler_excel(arquivo):
    nome = arquivo.name.lower()

    if nome.endswith(".xlsx"):
        return pd.read_excel(arquivo, engine="openpyxl")

    if nome.endswith(".xls"):
        try:
            return pd.read_excel(arquivo, engine="xlrd")
        except ImportError as exc:
            raise ValueError(
                "Arquivos .xls exigem a dependência 'xlrd'. "
                "Adicione 'xlrd' ao requirements.txt e faça o novo deploy."
            ) from exc

    raise ValueError(f"Formato não suportado: {arquivo.name}")


def _estrutura_dataframe(df):
    return [_normalizar_coluna(coluna) for coluna in df.columns]


def _montar_excel(df):
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Dados",
        )

    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# 6.1.1 — JUNTAR EXCEL
# ============================================================

def _assinatura_arquivos(arquivos):
    return tuple(
        (arquivo.name, arquivo.size)
        for arquivo in arquivos
    )


def _preparar_resultado(dataframes, estruturas_iguais):
    if estruturas_iguais:
        return pd.concat(
            [df for _, df in dataframes],
            ignore_index=True,
        )

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

        colunas_df = {
            _normalizar_coluna(col): col
            for col in df.columns
        }

        for chave in ordem_colunas:
            nome_saida = nomes_por_chave[chave]

            if chave in colunas_df:
                novo[nome_saida] = df[
                    colunas_df[chave]
                ].values
            else:
                novo[nome_saida] = pd.NA

        padronizados.append(novo)

    return pd.concat(
        padronizados,
        ignore_index=True,
    )


def render_juntar_excel():
    """Renderiza a ferramenta 6.1.1 — Juntar Excel."""

    st.markdown("### Juntar arquivos Excel")

    st.caption(
        "Selecione dois ou mais arquivos. As estruturas serão verificadas "
        "antes da junção. Os arquivos originais não serão alterados."
    )

    arquivos = st.file_uploader(
        "Selecione os arquivos Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="juntar_excel_arquivos",
    )

    if not arquivos:
        st.info("Selecione os arquivos que deseja juntar.")
        return

    assinatura = _assinatura_arquivos(arquivos)

    if st.session_state.get(
        "juntar_excel_assinatura"
    ) != assinatura:

        st.session_state["juntar_excel_assinatura"] = assinatura
        st.session_state["juntar_excel_resultado"] = None
        st.session_state["juntar_excel_nome"] = None
        st.session_state["juntar_excel_estruturas_iguais"] = None

    if len(arquivos) < 2:
        st.warning(
            "Selecione pelo menos 2 arquivos para realizar a junção."
        )
        return

    st.write(f"**{len(arquivos)} arquivos selecionados.**")

    dataframes = []
    erros = []

    for arquivo in arquivos:
        try:
            arquivo.seek(0)
            df = _ler_excel(arquivo)
            dataframes.append((arquivo.name, df))

        except Exception as exc:
            erros.append(f"**{arquivo.name}:** {exc}")

    if erros:
        st.error(
            "Não foi possível ler um ou mais arquivos:"
        )

        for erro in erros:
            st.write(f"- {erro}")

        return

    estruturas = [
        _estrutura_dataframe(df)
        for _, df in dataframes
    ]

    estrutura_base = estruturas[0]

    estruturas_iguais = all(
        estrutura == estrutura_base
        for estrutura in estruturas[1:]
    )

    st.markdown("#### 📋 Estrutura dos arquivos")

    resumo = pd.DataFrame(
        {
            "Arquivo": [
                nome for nome, _ in dataframes
            ],
            "Registros": [
                len(df) for _, df in dataframes
            ],
            "Colunas": [
                len(df.columns)
                for _, df in dataframes
            ],
        }
    )

    st.dataframe(
        resumo,
        use_container_width=True,
        hide_index=True,
    )

    if estruturas_iguais:

        st.success(
            "✅ Todos os arquivos possuem a mesma estrutura. "
            "A junção pode ser realizada diretamente."
        )

    else:

        st.warning(
            "⚠️ Os arquivos possuem estruturas diferentes."
        )

        todas_colunas = []

        for _, df in dataframes:
            for coluna in df.columns:
                chave = _normalizar_coluna(coluna)

                if chave not in todas_colunas:
                    todas_colunas.append(chave)

        detalhes = []

        for nome, df in dataframes:

            presentes = {
                _normalizar_coluna(col)
                for col in df.columns
            }

            faltantes = [
                col
                for col in todas_colunas
                if col not in presentes
            ]

            detalhes.append(
                {
                    "Arquivo": nome,
                    "Colunas presentes": len(presentes),
                    "Colunas ausentes": len(faltantes),
                    "Ausentes": (
                        ", ".join(faltantes)
                        if faltantes
                        else "—"
                    ),
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

            st.error(
                "A operação está bloqueada. "
                "Nenhum arquivo foi alterado."
            )

            return

        st.info(
            "As colunas serão unificadas. "
            "Quando uma coluna não existir em determinado arquivo, "
            "as células correspondentes ficarão em branco."
        )

    if st.button(
        "🔗 Juntar arquivos",
        type="primary",
        use_container_width=True,
        key="executar_juntar_excel",
    ):

        try:

            resultado = _preparar_resultado(
                dataframes,
                estruturas_iguais,
            )

            st.session_state["juntar_excel_resultado"] = resultado
            st.session_state["juntar_excel_nome"] = (
                "Excel_Consolidado.xlsx"
            )
            st.session_state[
                "juntar_excel_estruturas_iguais"
            ] = estruturas_iguais

        except Exception as exc:

            st.error(
                f"Não foi possível juntar os arquivos: {exc}"
            )

            return

    resultado = st.session_state.get(
        "juntar_excel_resultado"
    )

    if resultado is None:
        return

    st.success(
        f"✅ Junção concluída: "
        f"{len(resultado):,} registros e "
        f"{len(resultado.columns):,} colunas."
    )

    st.download_button(
        "📥 Baixar Excel consolidado",
        data=_montar_excel(resultado),
        file_name=st.session_state.get(
            "juntar_excel_nome",
            "Excel_Consolidado.xlsx",
        ),
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
        key="download_juntar_excel",
    )


# ============================================================
# 6.1.2 — VISUALIZAR EXCEL
# ============================================================

def render_visualizar_excel():
    """Renderiza a ferramenta 6.1.2 — Visualizar Excel."""

    st.markdown("### Visualizar arquivo Excel")

    st.caption(
        "Carregue um arquivo Excel para pesquisar, filtrar e "
        "ordenar os dados sem alterar o arquivo original."
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
        key="visualizar_excel_arquivo",
    )

    if arquivo is None:
        st.info(
            "Selecione um arquivo Excel para começar."
        )
        return

    assinatura = (
        arquivo.name,
        arquivo.size,
    )

    if st.session_state.get(
        "visualizar_excel_assinatura"
    ) != assinatura:

        st.session_state[
            "visualizar_excel_assinatura"
        ] = assinatura

        try:
            arquivo.seek(0)

            df = _ler_excel(arquivo)

            st.session_state[
                "visualizar_excel_df"
            ] = df

        except Exception as exc:

            st.session_state[
                "visualizar_excel_df"
            ] = None

            st.error(
                f"Não foi possível ler o arquivo: {exc}"
            )

            return

    df_original = st.session_state.get(
        "visualizar_excel_df"
    )

    if df_original is None:
        return

    if df_original.empty:
        st.warning(
            "O arquivo não possui registros."
        )
        return

    st.success(
        f"Arquivo carregado: **{arquivo.name}** — "
        f"{len(df_original):,} registros e "
        f"{len(df_original.columns):,} colunas."
    )

    st.markdown("#### 🔍 Pesquisa")

    pesquisa = st.text_input(
        "Pesquisar em todas as colunas",
        placeholder="Digite um texto para pesquisar...",
        key="visualizar_excel_pesquisa",
    )

    st.markdown("#### 🔽 Filtro por coluna")

    colunas = list(df_original.columns)

    coluna_filtro = st.selectbox(
        "Coluna",
        options=["Nenhum"] + colunas,
        key="visualizar_excel_coluna_filtro",
    )

    valor_filtro = ""

    if coluna_filtro != "Nenhum":

        valor_filtro = st.text_input(
            "Valor do filtro",
            placeholder=(
                "Digite parte ou o valor completo..."
            ),
            key="visualizar_excel_valor_filtro",
        )

    st.markdown("#### ↕️ Ordenação")

    col_ordem, col_direcao = st.columns(2)

    with col_ordem:

        coluna_ordenacao = st.selectbox(
            "Ordenar por",
            options=["Nenhum"] + colunas,
            key="visualizar_excel_coluna_ordenacao",
        )

    with col_direcao:

        ordem = st.radio(
            "Ordem",
            options=[
                "Crescente",
                "Decrescente",
            ],
            horizontal=True,
            key="visualizar_excel_ordem",
        )

    quantidade_maxima = st.number_input(
        "Quantidade máxima de linhas exibidas",
        min_value=10,
        max_value=10000,
        value=1000,
        step=100,
        key="visualizar_excel_quantidade",
    )

    resultado = df_original.copy()

    if pesquisa.strip():

        termo = pesquisa.strip().casefold()

        mascara = (
            resultado.astype(str)
            .apply(
                lambda coluna: coluna.str.casefold()
                .str.contains(
                    termo,
                    na=False,
                    regex=False,
                )
            )
            .any(axis=1)
        )

        resultado = resultado.loc[mascara]

    if (
        coluna_filtro != "Nenhum"
        and valor_filtro.strip()
    ):

        termo = valor_filtro.strip().casefold()

        mascara = (
            resultado[coluna_filtro]
            .astype(str)
            .str.casefold()
            .str.contains(
                termo,
                na=False,
                regex=False,
            )
        )

        resultado = resultado.loc[mascara]

    if coluna_ordenacao != "Nenhum":

        try:

            resultado = resultado.sort_values(
                by=coluna_ordenacao,
                ascending=(
                    ordem == "Crescente"
                ),
                kind="stable",
                na_position="last",
            )

        except Exception:

            resultado = resultado.sort_values(
                by=coluna_ordenacao,
                ascending=(
                    ordem == "Crescente"
                ),
                kind="stable",
                key=lambda serie: serie.astype(str),
            )

    total_original = len(df_original)
    total_filtrado = len(resultado)

    resultado_exibicao = resultado.head(
        int(quantidade_maxima)
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Registros originais",
            f"{total_original:,}",
        )

    with col2:
        st.metric(
            "Registros encontrados",
            f"{total_filtrado:,}",
        )

    with col3:
        st.metric(
            "Colunas",
            f"{len(resultado.columns):,}",
        )

    if total_filtrado == 0:

        st.warning(
            "Nenhum registro corresponde aos critérios informados."
        )

        return

    if total_filtrado > len(resultado_exibicao):

        st.caption(
            f"Exibindo {len(resultado_exibicao):,} "
            f"de {total_filtrado:,} registros encontrados."
        )

    else:

        st.caption(
            f"Exibindo {total_filtrado:,} registros."
        )

    st.dataframe(
        resultado_exibicao,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# 6.1.3 — COMPARAR BASES
# ============================================================

def _normalizar_valor_comparacao(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    texto = re.sub(r"\s+", " ", texto)

    return texto.casefold()


def _criar_chave_comparacao(df, colunas_chave):
    return df[colunas_chave].apply(
        lambda linha: "¦".join(
            _normalizar_valor_comparacao(valor)
            for valor in linha
        ),
        axis=1,
    )


def _montar_excel_comparacao(
    somente_base_1,
    somente_base_2,
    em_ambas,
):
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        somente_base_1.to_excel(
            writer,
            index=False,
            sheet_name="Somente_Base_1",
        )

        somente_base_2.to_excel(
            writer,
            index=False,
            sheet_name="Somente_Base_2",
        )

        em_ambas.to_excel(
            writer,
            index=False,
            sheet_name="Em_Ambas",
        )

    buffer.seek(0)

    return buffer.getvalue()


def render_comparar_bases():
    """Renderiza a ferramenta 6.1.3 — Comparar Bases."""

    st.markdown("### Comparar bases Excel")

    st.caption(
        "Compare dois arquivos Excel utilizando uma ou mais colunas "
        "como chave de comparação. Os arquivos originais não serão alterados."
    )

    col1, col2 = st.columns(2)

    with col1:

        arquivo_1 = st.file_uploader(
            "📂 Base 1",
            type=["xlsx", "xls"],
            accept_multiple_files=False,
            key="comparar_bases_arquivo_1",
        )

    with col2:

        arquivo_2 = st.file_uploader(
            "📂 Base 2",
            type=["xlsx", "xls"],
            accept_multiple_files=False,
            key="comparar_bases_arquivo_2",
        )

    if arquivo_1 is None or arquivo_2 is None:

        st.info(
            "Selecione os dois arquivos para iniciar a comparação."
        )

        return

    assinatura = (
        arquivo_1.name,
        arquivo_1.size,
        arquivo_2.name,
        arquivo_2.size,
    )

    if st.session_state.get(
        "comparar_bases_assinatura"
    ) != assinatura:

        st.session_state[
            "comparar_bases_assinatura"
        ] = assinatura

        st.session_state[
            "comparar_bases_df_1"
        ] = None

        st.session_state[
            "comparar_bases_df_2"
        ] = None

        st.session_state[
            "comparar_bases_resultado"
        ] = None

    if st.session_state.get(
        "comparar_bases_df_1"
    ) is None:

        try:

            arquivo_1.seek(0)

            st.session_state[
                "comparar_bases_df_1"
            ] = _ler_excel(arquivo_1)

        except Exception as exc:

            st.error(
                f"Não foi possível ler a Base 1: {exc}"
            )

            return

    if st.session_state.get(
        "comparar_bases_df_2"
    ) is None:

        try:

            arquivo_2.seek(0)

            st.session_state[
                "comparar_bases_df_2"
            ] = _ler_excel(arquivo_2)

        except Exception as exc:

            st.error(
                f"Não foi possível ler a Base 2: {exc}"
            )

            return

    df1 = st.session_state[
        "comparar_bases_df_1"
    ]

    df2 = st.session_state[
        "comparar_bases_df_2"
    ]

    if df1.empty:

        st.warning(
            "A Base 1 não possui registros."
        )

        return

    if df2.empty:

        st.warning(
            "A Base 2 não possui registros."
        )

        return

    st.markdown("#### 📊 Resumo das bases")

    resumo = pd.DataFrame(
        {
            "Base": [
                arquivo_1.name,
                arquivo_2.name,
            ],
            "Registros": [
                len(df1),
                len(df2),
            ],
            "Colunas": [
                len(df1.columns),
                len(df2.columns),
            ],
        }
    )

    st.dataframe(
        resumo,
        use_container_width=True,
        hide_index=True,
    )

    colunas_base_2 = list(df2.columns)

    mapa_base_2 = {
        _normalizar_coluna(coluna): coluna
        for coluna in colunas_base_2
    }

    colunas_comuns = []

    for coluna in df1.columns:

        chave = _normalizar_coluna(coluna)

        if chave in mapa_base_2:

            colunas_comuns.append(coluna)

    if not colunas_comuns:

        st.error(
            "As bases não possuem nenhuma coluna em comum "
            "para realizar a comparação."
        )

        return

    st.markdown(
        "#### 🔑 Colunas utilizadas na comparação"
    )

    st.caption(
        "Selecione uma ou mais colunas que identificam o registro. "
        "As colunas selecionadas precisam existir nas duas bases."
    )

    colunas_chave = st.multiselect(
        "Colunas-chave",
        options=colunas_comuns,
        key="comparar_bases_colunas_chave",
    )

    if not colunas_chave:

        st.info(
            "Selecione pelo menos uma coluna-chave."
        )

        return

    colunas_chave_base_2 = [
        mapa_base_2[
            _normalizar_coluna(coluna)
        ]
        for coluna in colunas_chave
    ]

    if st.button(
        "🔍 Comparar bases",
        type="primary",
        use_container_width=True,
        key="executar_comparar_bases",
    ):

        try:

            temp1 = df1.copy()
            temp2 = df2.copy()

            temp1[
                "__chave_comparacao__"
            ] = _criar_chave_comparacao(
                temp1,
                colunas_chave,
            )

            temp2[
                "__chave_comparacao__"
            ] = _criar_chave_comparacao(
                temp2,
                colunas_chave_base_2,
            )

            chaves_1 = set(
                temp1[
                    "__chave_comparacao__"
                ]
            )

            chaves_2 = set(
                temp2[
                    "__chave_comparacao__"
                ]
            )

            chaves_comuns = (
                chaves_1 & chaves_2
            )

            chaves_somente_1 = (
                chaves_1 - chaves_2
            )

            chaves_somente_2 = (
                chaves_2 - chaves_1
            )

            somente_base_1 = temp1[
                temp1[
                    "__chave_comparacao__"
                ].isin(chaves_somente_1)
            ].drop(
                columns=[
                    "__chave_comparacao__"
                ]
            )

            somente_base_2 = temp2[
                temp2[
                    "__chave_comparacao__"
                ].isin(chaves_somente_2)
            ].drop(
                columns=[
                    "__chave_comparacao__"
                ]
            )

            em_ambas = temp1[
                temp1[
                    "__chave_comparacao__"
                ].isin(chaves_comuns)
            ].drop(
                columns=[
                    "__chave_comparacao__"
                ]
            )

            st.session_state[
                "comparar_bases_resultado"
            ] = {
                "somente_base_1": somente_base_1,
                "somente_base_2": somente_base_2,
                "em_ambas": em_ambas,
            }

        except Exception as exc:

            st.error(
                f"Não foi possível comparar as bases: {exc}"
            )

            return

    resultado = st.session_state.get(
        "comparar_bases_resultado"
    )

    if resultado is None:
        return

    somente_base_1 = resultado[
        "somente_base_1"
    ]

    somente_base_2 = resultado[
        "somente_base_2"
    ]

    em_ambas = resultado[
        "em_ambas"
    ]

    st.markdown(
        "#### 📊 Resultado da comparação"
    )

    r1, r2, r3 = st.columns(3)

    with r1:

        st.metric(
            "Somente na Base 1",
            f"{len(somente_base_1):,}",
        )

    with r2:

        st.metric(
            "Somente na Base 2",
            f"{len(somente_base_2):,}",
        )

    with r3:

        st.metric(
            "Presentes nas duas",
            f"{len(em_ambas):,}",
        )

    st.caption(
        "A comparação considera os valores das colunas-chave, "
        "ignorando diferenças de maiúsculas/minúsculas e espaços excedentes."
    )

    arquivo_resultado = _montar_excel_comparacao(
        somente_base_1,
        somente_base_2,
        em_ambas,
    )

    st.download_button(
        "📥 Baixar resultado da comparação",
        data=arquivo_resultado,
        file_name="Comparacao_Bases.xlsx",
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
        key="download_comparar_bases",
    )


# ============================================================
# 6.1.4 — REMOVER DUPLICIDADES
# ============================================================

def _normalizar_dataframe_para_duplicidade(
    df,
    colunas_chave,
):
    normalizado = pd.DataFrame(index=df.index)

    for coluna in colunas_chave:

        normalizado[coluna] = (
            df[coluna]
            .apply(_normalizar_valor_comparacao)
        )

    return normalizado


def render_remover_duplicidades():
    """Renderiza a ferramenta 6.1.4 — Remover Duplicidades."""

    st.markdown("### Remover duplicidades")

    st.caption(
        "Carregue um arquivo Excel e selecione as colunas que serão "
        "utilizadas para identificar registros duplicados. "
        "O arquivo original não será alterado."
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
        key="remover_duplicidades_arquivo",
    )

    if arquivo is None:

        st.info(
            "Selecione um arquivo Excel para começar."
        )

        return

    assinatura = (
        arquivo.name,
        arquivo.size,
    )

    if st.session_state.get(
        "remover_duplicidades_assinatura"
    ) != assinatura:

        st.session_state[
            "remover_duplicidades_assinatura"
        ] = assinatura

        st.session_state[
            "remover_duplicidades_df"
        ] = None

        st.session_state[
            "remover_duplicidades_resultado"
        ] = None

    if st.session_state.get(
        "remover_duplicidades_df"
    ) is None:

        try:

            arquivo.seek(0)

            st.session_state[
                "remover_duplicidades_df"
            ] = _ler_excel(arquivo)

        except Exception as exc:

            st.session_state[
                "remover_duplicidades_df"
            ] = None

            st.error(
                f"Não foi possível ler o arquivo: {exc}"
            )

            return

    df_original = st.session_state.get(
        "remover_duplicidades_df"
    )

    if df_original is None:
        return

    if df_original.empty:

        st.warning(
            "O arquivo não possui registros."
        )

        return

    st.success(
        f"Arquivo carregado: **{arquivo.name}** — "
        f"{len(df_original):,} registros e "
        f"{len(df_original.columns):,} colunas."
    )

    # --------------------------------------------------------
    # COLUNAS PARA IDENTIFICAÇÃO
    # --------------------------------------------------------

    st.markdown(
        "#### 🔑 Colunas para identificar duplicidades"
    )

    st.caption(
        "Selecione uma ou mais colunas. Registros com os mesmos "
        "valores nessas colunas serão considerados duplicados."
    )

    colunas = list(df_original.columns)

    colunas_chave = st.multiselect(
        "Colunas utilizadas",
        options=colunas,
        key="remover_duplicidades_colunas_chave",
    )

    if not colunas_chave:

        st.info(
            "Selecione pelo menos uma coluna para identificar "
            "os registros duplicados."
        )

        return

    # --------------------------------------------------------
    # OPÇÃO DE MANUTENÇÃO
    # --------------------------------------------------------

    st.markdown(
        "#### 📌 Registro que será mantido"
    )

    modo_manter = st.radio(
        "Escolha qual ocorrência manter",
        options=[
            "Manter a primeira ocorrência",
            "Manter a última ocorrência",
        ],
        horizontal=True,
        key="remover_duplicidades_modo",
    )

    # --------------------------------------------------------
    # INFORMAÇÃO SOBRE DUPLICIDADES
    # --------------------------------------------------------

    try:

        normalizado = _normalizar_dataframe_para_duplicidade(
            df_original,
            colunas_chave,
        )

        mascara_duplicado = normalizado.duplicated(
            keep=False
        )

        quantidade_registros_duplicados = int(
            mascara_duplicado.sum()
        )

        quantidade_grupos_duplicados = int(
            normalizado.loc[
                mascara_duplicado
            ].drop_duplicates().shape[0]
        )

    except Exception as exc:

        st.error(
            f"Não foi possível analisar as duplicidades: {exc}"
        )

        return

    d1, d2, d3 = st.columns(3)

    with d1:

        st.metric(
            "Registros originais",
            f"{len(df_original):,}",
        )

    with d2:

        st.metric(
            "Registros em grupos duplicados",
            f"{quantidade_registros_duplicados:,}",
        )

    with d3:

        st.metric(
            "Grupos duplicados",
            f"{quantidade_grupos_duplicados:,}",
        )

    if quantidade_registros_duplicados == 0:

        st.success(
            "✅ Nenhum registro duplicado foi encontrado "
            "com as colunas selecionadas."
        )

    # --------------------------------------------------------
    # EXECUÇÃO
    # --------------------------------------------------------

    if st.button(
        "🧹 Remover duplicidades",
        type="primary",
        use_container_width=True,
        key="executar_remover_duplicidades",
    ):

        try:

            manter = (
                "first"
                if modo_manter.startswith("Manter a primeira")
                else "last"
            )

            indices_manter = normalizado.drop_duplicates(
                subset=colunas_chave,
                keep=manter,
            ).index

            resultado = df_original.loc[
                indices_manter
            ].copy()

            resultado = resultado.reset_index(
                drop=True
            )

            st.session_state[
                "remover_duplicidades_resultado"
            ] = resultado

        except Exception as exc:

            st.error(
                f"Não foi possível remover as duplicidades: {exc}"
            )

            return

    resultado = st.session_state.get(
        "remover_duplicidades_resultado"
    )

    if resultado is None:
        return

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    registros_removidos = (
        len(df_original) - len(resultado)
    )

    st.markdown(
        "#### 📊 Resultado"
    )

    r1, r2, r3 = st.columns(3)

    with r1:

        st.metric(
            "Registros originais",
            f"{len(df_original):,}",
        )

    with r2:

        st.metric(
            "Registros após limpeza",
            f"{len(resultado):,}",
        )

    with r3:

        st.metric(
            "Duplicidades removidas",
            f"{registros_removidos:,}",
        )

    if registros_removidos == 0:

        st.info(
            "Nenhum registro foi removido."
        )

    else:

        st.success(
            f"✅ Limpeza concluída. "
            f"{registros_removidos:,} registros duplicados "
            f"foram removidos."
        )

    st.caption(
        "A comparação ignora diferenças de maiúsculas/minúsculas "
        "e espaços excedentes nos valores das colunas selecionadas."
    )

    arquivo_resultado = _montar_excel(
        resultado
    )

    st.download_button(
        "📥 Baixar Excel sem duplicidades",
        data=arquivo_resultado,
        file_name="Excel_Sem_Duplicidades.xlsx",
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
        key="download_remover_duplicidades",
    )


# ============================================================
# 6.1.5 — SEPARAR EXCEL
# ============================================================

def _valor_separacao(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    texto = re.sub(r"\s+", " ", texto)

    return texto.casefold()


def _nome_arquivo_seguro(valor):
    valor = str(valor).strip()

    if not valor:
        valor = "Vazios"

    valor = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        valor,
    )

    valor = re.sub(
        r"\s+",
        " ",
        valor,
    )

    return valor[:120]


def render_separar_excel():
    """Renderiza a ferramenta 6.1.5 — Separar Excel."""

    st.markdown("### Separar Excel")

    st.caption(
        "Divida uma base em vários arquivos Excel utilizando "
        "os valores de uma coluna. O arquivo original não será alterado."
    )

    arquivo = st.file_uploader(
        "Selecione o arquivo Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
        key="separar_excel_arquivo",
    )

    if arquivo is None:

        st.info(
            "Selecione um arquivo Excel para começar."
        )

        return

    assinatura = (
        arquivo.name,
        arquivo.size,
    )

    if st.session_state.get(
        "separar_excel_assinatura"
    ) != assinatura:

        st.session_state[
            "separar_excel_assinatura"
        ] = assinatura

        st.session_state[
            "separar_excel_df"
        ] = None

        st.session_state[
            "separar_excel_resultados"
        ] = None

        st.session_state[
            "separar_excel_coluna"
        ] = None

        st.session_state[
            "separar_excel_valores"
        ] = []

        try:

            arquivo.seek(0)

            df = _ler_excel(arquivo)

            st.session_state[
                "separar_excel_df"
            ] = df

        except Exception as exc:

            st.session_state[
                "separar_excel_df"
            ] = None

            st.error(
                f"Não foi possível ler o arquivo: {exc}"
            )

            return

    df = st.session_state.get(
        "separar_excel_df"
    )

    if df is None:
        return

    if df.empty:

        st.warning(
            "O arquivo não possui registros."
        )

        return

    st.success(
        f"Arquivo carregado: **{arquivo.name}** — "
        f"{len(df):,} registros e "
        f"{len(df.columns):,} colunas."
    )

    st.markdown(
        "#### 🔑 Coluna utilizada para separar"
    )

    coluna = st.selectbox(
        "Selecione a coluna",
        options=list(df.columns),
        key="separar_excel_coluna",
    )

    if coluna is None:
        return

    valores_mapeados = {}

    for valor in df[coluna]:

        chave = _valor_separacao(valor)

        if chave not in valores_mapeados:

            if pd.isna(valor) or str(valor).strip() == "":
                valores_mapeados[chave] = "Vazios"

            else:
                valores_mapeados[chave] = str(
                    valor
                ).strip()

    opcoes = list(
        valores_mapeados.items()
    )

    opcoes.sort(
        key=lambda item: item[1].casefold()
    )

    labels = [
        rotulo
        for _, rotulo in opcoes
    ]

    st.markdown(
        "#### 📂 Valores para gerar"
    )

    selecionados = st.multiselect(
        "Selecione os valores que deseja transformar em arquivos",
        options=labels,
        key="separar_excel_valores",
    )

    if not selecionados:

        st.info(
            "Selecione pelo menos um valor para gerar os arquivos."
        )

        return

    resumo = []

    for chave, rotulo in opcoes:

        if rotulo not in selecionados:
            continue

        if chave == "":

            mascara = (
                df[coluna].isna()
                | df[coluna]
                .astype(str)
                .str.strip()
                .eq("")
            )

        else:

            mascara = (
                df[coluna]
                .apply(_valor_separacao)
                .eq(chave)
            )

        resumo.append(
            {
                "Valor": rotulo,
                "Registros": int(
                    mascara.sum()
                ),
            }
        )

    st.markdown(
        "#### 📊 Resumo da separação"
    )

    st.dataframe(
        pd.DataFrame(resumo),
        use_container_width=True,
        hide_index=True,
    )

    if st.button(
        "✂️ Gerar arquivos separados",
        type="primary",
        use_container_width=True,
        key="executar_separar_excel",
    ):

        resultados = []

        for chave, rotulo in opcoes:

            if rotulo not in selecionados:
                continue

            if chave == "":

                mascara = (
                    df[coluna].isna()
                    | df[coluna]
                    .astype(str)
                    .str.strip()
                    .eq("")
                )

            else:

                mascara = (
                    df[coluna]
                    .apply(_valor_separacao)
                    .eq(chave)
                )

            df_separado = df.loc[
                mascara
            ].copy()

            resultados.append(
                {
                    "valor": rotulo,
                    "registros": df_separado,
                    "nome_arquivo": (
                        "Separado_"
                        f"{_nome_arquivo_seguro(rotulo)}.xlsx"
                    ),
                }
            )

        st.session_state[
            "separar_excel_resultados"
        ] = resultados

    resultados = st.session_state.get(
        "separar_excel_resultados"
    )

    if not resultados:
        return

    st.success(
        f"✅ {len(resultados)} arquivo(s) separado(s) com sucesso."
    )

    st.markdown(
        "#### 📥 Arquivos para download"
    )

    for indice, resultado in enumerate(
        resultados
    ):

        df_resultado = resultado[
            "registros"
        ]

        col1, col2 = st.columns(
            [2, 1]
        )

        with col1:

            st.write(
                f"**{resultado['nome_arquivo']}**  \n"
                f"{len(df_resultado):,} registros"
            )

        with col2:

            st.download_button(
                "📥 Baixar",
                data=_montar_excel(
                    df_resultado
                ),
                file_name=resultado[
                    "nome_arquivo"
                ],
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                use_container_width=True,
                key=(
                    "download_separar_excel_"
                    f"{indice}"
                ),
            )
