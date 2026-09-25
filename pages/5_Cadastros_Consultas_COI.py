with aba_consulta:

    if df_pessoas.empty:

        st.info(
            "Nenhuma pessoa foi cadastrada ainda."
        )

    else:

        busca_pessoa = st.text_input(
            "Pesquisar pessoa",
            key="busca_pessoa",
        )

        if busca_pessoa.strip():

            termo = normalizar_texto(
                busca_pessoa
            )

            nomes_encontrados = sorted(
                [
                    nome
                    for nome in df_pessoas["NOME"]
                    .dropna()
                    .astype(str)
                    .unique()
                    if nome.strip()
                    and termo in normalizar_texto(nome)
                ]
            )

            if not nomes_encontrados:

                st.info(
                    "Nenhuma pessoa encontrada para a consulta."
                )

            else:

                pessoa_selecionada = st.selectbox(
                    "Selecione a pessoa encontrada",
                    nomes_encontrados,
                    key="pessoa_consulta",
                )

                registros = df_pessoas[
                    df_pessoas["NOME"].apply(normalizar_texto)
                    == normalizar_texto(
                        pessoa_selecionada
                    )
                ].copy()

                primeira_linha = registros.iloc[0]

                st.markdown(
                    f"### 👤 {pessoa_selecionada}"
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown(
                        f"**Função:** "
                        f"{primeira_linha['FUNCAO'] or '-'}"
                    )

                with col2:
                    st.markdown(
                        f"**Telefone:** "
                        f"{primeira_linha['TELEFONE'] or '-'}"
                    )

                with col3:
                    st.markdown(
                        f"**E-mail:** "
                        f"{primeira_linha['EMAIL'] or '-'}"
                    )

                st.divider()

                regionais = sorted(
                    [
                        str(regional).strip()
                        for regional in registros["REGIONAL"]
                        if str(regional).strip()
                    ]
                )

                regionais_unicas = []

                for regional in regionais:
                    if normalizar_texto(
                        regional
                    ) not in [
                        normalizar_texto(item)
                        for item in regionais_unicas
                    ]:
                        regionais_unicas.append(
                            regional
                        )

                if regionais_unicas:

                    st.markdown(
                        "**Regional:** "
                        + ", ".join(regionais_unicas)
                    )

                st.markdown(
                    "#### 🗂️ Responsabilidades"
                )

                linhas_responsabilidades = []

                for _, registro in registros.iterrows():

                    municipio = str(
                        registro["MUNICIPIO"]
                    ).strip()

                    base = str(
                        registro["BASE"]
                    ).strip()

                    regional = str(
                        registro["REGIONAL"]
                    ).strip()

                    if (
                        municipio
                        or base
                        or regional
                    ):
                        linhas_responsabilidades.append(
                            {
                                "REGIONAL": regional,
                                "BASE": base,
                                "MUNICIPIO": municipio,
                            }
                        )

                if linhas_responsabilidades:

                    df_responsabilidades = (
                        pd.DataFrame(
                            linhas_responsabilidades
                        )
                        .drop_duplicates()
                        .sort_values(
                            [
                                "REGIONAL",
                                "BASE",
                                "MUNICIPIO",
                            ]
                        )
                    )

                    st.dataframe(
                        df_responsabilidades,
                        use_container_width=True,
                        hide_index=True,
                    )

                else:

                    st.info(
                        "Nenhum vínculo operacional informado."
                    )

                observacoes = [
                    str(valor).strip()
                    for valor in registros["OBSERVACAO"]
                    if str(valor).strip()
                ]

                if observacoes:

                    st.markdown(
                        "#### 📝 Observações"
                    )

                    observacoes_unicas = []

                    for observacao in observacoes:
                        if observacao not in observacoes_unicas:
                            observacoes_unicas.append(
                                observacao
                            )

                    for observacao in observacoes_unicas:
                        st.write(
                            f"• {observacao}"
                        )
