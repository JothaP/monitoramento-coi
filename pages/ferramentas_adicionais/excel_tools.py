import io
import pandas as pd
import streamlit as st


def _ler_excel(uploaded_file):
    return pd.read_excel(uploaded_file)


def render_juntar_excel():
    """Sessão 6.1 — Excel Tools: Juntar Excel."""
    st.markdown("### 🔗 Juntar arquivos Excel")
    st.caption("Consolide vários arquivos Excel em uma única base, preservando os arquivos originais.")

    arquivos = st.file_uploader(
        "Selecione os arquivos Excel",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="excel_tools_juntar_upload",
        help="Você pode selecionar vários arquivos .xlsx ou .xls.",
    )

    if not arquivos:
        st.info("Selecione pelo menos dois arquivos Excel para iniciar a consolidação.")
        return

    st.markdown(f"**{len(arquivos)} arquivo(s) selecionado(s).**")

    dados = []
    erros = []

    for arquivo in arquivos:
        try:
            df = _ler_excel(arquivo)
            dados.append({
                "nome": arquivo.name,
                "df": df,
                "colunas": list(df.columns),
                "registros": len(df),
            })
        except Exception as exc:
            erros.append(f"{arquivo.name}: {exc}")

    if erros:
        st.error("Não foi possível ler um ou mais arquivos:")
        for erro in erros:
            st.write(f"- {erro}")
        return

    if not dados:
        st.warning("Nenhum arquivo válido foi carregado.")
        return

    total_registros = sum(item["registros"] for item in dados)
    estruturas = [item["colunas"] for item in dados]
    estruturas_iguais = all(colunas == estruturas[0] for colunas in estruturas[1:])

    st.markdown("#### Resumo dos arquivos")
    resumo = pd.DataFrame([
        {
            "Arquivo": item["nome"],
            "Registros": item["registros"],
            "Colunas": len(item["colunas"]),
        }
        for item in dados
    ])
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    if estruturas_iguais:
        st.success("As estruturas são iguais. Os arquivos podem ser juntados diretamente.")
        modo_juncao = "direta"
    else:
        st.warning("Os arquivos possuem estruturas diferentes.")

        todas_colunas = []
        for item in dados:
            for coluna in item["colunas"]:
                if coluna not in todas_colunas:
                    todas_colunas.append(coluna)

        tabela_diferencas = []
        for item in dados:
            conjunto = set(item["colunas"])
            tabela_diferencas.append({
                "Arquivo": item["nome"],
                "Colunas presentes": len(item["colunas"]),
                "Colunas ausentes": len([c for c in todas_colunas if c not in conjunto]),
                "Ausentes neste arquivo": ", ".join(
                    str(c) for c in todas_colunas if c not in conjunto
                ) or "—",
            })

        st.dataframe(
            pd.DataFrame(tabela_diferencas),
            use_container_width=True,
            hide_index=True,
        )

        modo_juncao = st.radio(
            "Como deseja tratar as estruturas diferentes?",
            options=[
                "A — Juntar mesmo (colunas ausentes ficam em branco)",
                "B — Bloquear operação",
            ],
            key="excel_tools_juntar_modo",
        )

        if modo_juncao.startswith("B"):
            st.error("Operação bloqueada. Nenhum arquivo foi alterado ou gerado.")
            return

    try:
        if modo_juncao == "direta":
            resultado = pd.concat(
                [item["df"] for item in dados],
                ignore_index=True,
            )
        else:
            resultado = pd.concat(
                [item["df"] for item in dados],
                ignore_index=True,
                sort=False,
            )
    except Exception as exc:
        st.error(f"Erro ao juntar os arquivos: {exc}")
        return

    st.markdown("#### Resultado")
    c1, c2, c3 = st.columns(3)
    c1.metric("Arquivos", len(dados))
    c2.metric("Registros", len(resultado))
    c3.metric("Colunas", len(resultado.columns))

    st.markdown("**Prévia — primeiros 100 registros**")
    st.dataframe(resultado.head(100), use_container_width=True, hide_index=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resultado.to_excel(writer, index=False, sheet_name="Consolidado")
    buffer.seek(0)

    st.download_button(
        "📥 Baixar Excel Consolidado",
        data=buffer.getvalue(),
        file_name="Excel_Consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="excel_tools_baixar_consolidado",
    )
