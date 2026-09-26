import io
import re

import pandas as pd
import streamlit as st


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
        df.to_excel(writer, index=False, sheet_name="Dados")
    buffer.seek(0)
    return buffer.getvalue()


def _assinatura_arquivos(arquivos):
    return tuple((arquivo.name, arquivo.size) for arquivo in arquivos)


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
        colunas_df = {_normalizar_coluna(col): col for col in df.columns}

        for chave in ordem_colunas:
            nome_saida = nomes_por_chave[chave]
            if chave in colunas_df:
                novo[nome_saida] = df[colunas_df[chave]].values
            else:
                novo[nome_saida] = pd.NA

        padronizados.append(novo)

    return pd.concat(padronizados, ignore_index=True)


def render_juntar_excel():
    """Renderiza a ferramenta 6.1.1 — Juntar Excel."""

    st.markdown("### Juntar arquivos Excel")
    st.caption(
        "Selecione dois ou mais arquivos. As estruturas serão verificadas antes da junção. "
        "Os arquivos originais não serão alterados."
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

    if st.session_state.get("juntar_excel_assinatura") != assinatura:
        st.session_state["juntar_excel_assinatura"] = assinatura
        st.session_state["juntar_excel_resultado"] = None
        st.session_state["juntar_excel_nome"] = None
        st.session_state["juntar_excel_estruturas_iguais"] = None

    if len(arquivos) < 2:
        st.warning("Selecione pelo menos 2 arquivos para realizar a junção.")
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
        st.error("Não foi possível ler um ou mais arquivos:")
        for erro in erros:
            st.write(f"- {erro}")
        return

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
        st.success(
            "✅ Todos os arquivos possuem a mesma estrutura. "
            "A junção pode ser realizada diretamente."
        )
    else:
        st.warning("⚠️ Os arquivos possuem estruturas diferentes.")

        todas_colunas = []
        for _, df in dataframes:
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

    if st.button(
        "🔗 Juntar arquivos",
        type="primary",
        use_container_width=True,
        key="executar_juntar_excel",
    ):
        try:
            resultado = _preparar_resultado(dataframes, estruturas_iguais)

            st.session_state["juntar_excel_resultado"] = resultado
            st.session_state["juntar_excel_nome"] = "Excel_Consolidado.xlsx"
            st.session_state["juntar_excel_estruturas_iguais"] = estruturas_iguais

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

    st.download_button(
        "📥 Baixar Excel consolidado",
        data=_montar_excel(resultado),
        file_name=st.session_state.get(
            "juntar_excel_nome",
            "Excel_Consolidado.xlsx",
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="download_juntar_excel",
    )
