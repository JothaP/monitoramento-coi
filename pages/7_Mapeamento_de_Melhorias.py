                        st.session_state["farol_concentracao_expandida"] = melhor
                        st.rerun()
            # A lista tradicional de concentrações permanece abaixo do mapa.
            # Evita-se o seletor adicional, que causava outra interação e rerun.
        exibir_atualizacoes_abaixo_mapa()
        if sincronizar_mapa_pdf and estado_mapa and selecionada:
            if estado_mapa.get("center") is not None:
                st.session_state["farol_ultimo_centro_mapa"] = estado_mapa["center"]
            if estado_mapa.get("zoom") is not None:
                st.session_state["farol_ultimo_zoom_mapa"] = estado_mapa["zoom"]

        _tempo_mapa = tempo_execucao.perf_counter() - _inicio_renderizacao
        if PERFIL_FAROL == "admin":
            with espaco_diagnostico_farol.container():
                with st.expander("⏱️ Diagnóstico de desempenho", expanded=False):
                    st.caption("Tempo desta interação; valores baixos podem indicar uso do cache.")
                    st.write(f"Geometrias: {_tempo_geometria:.2f} s")
                    st.write(f"Google Sheets: {_tempo_planilhas:.2f} s")
                    st.write(f"Análise espacial: {_tempo_analise:.2f} s")
                    st.write(f"Montagem e exibição do mapa: {_tempo_mapa:.2f} s")
        if concentracoes.empty:
            st.warning("Nenhuma concentração atingiu o mínimo configurado.")
        else:
            st.markdown("### 📋 Análise das Concentrações")
            st.caption("Expanda uma concentração para consultar O.S., equipamentos, eventos relacionados e baixar o PDF.")
            observacoes_df = carregar_observacoes_concentracoes()
            resumo_pdf = concentracoes.copy()
            grupos_os = {chave: quadro for chave, quadro in pontos_cluster.groupby("_grupo", sort=False)} if not pontos_cluster.empty else {}
            for _, concentracao in concentracoes.iterrows():
                codigo = concentracao["ID_CONCENTRACAO"]
                os_grupo = grupos_os.get(concentracao["GRUPO"], pontos_cluster.iloc[0:0])
                cidades_grupo = sorted({str(v).strip() for v in os_grupo["Cidade"] if str(v).strip()})
                qtd_ativos = (int((proximidades["Concentração"] == codigo).sum())
                              if not proximidades.empty else 0)
                _, _, eventos_do_grupo = dados_relatorio_concentracao(
                    concentracao, pontos_cluster, proximidades, df_eventos, bairros
                )
                indicador_eventos = (
                    f"⚡ {len(eventos_do_grupo)} evento(s) relacionado(s)"
                    if not eventos_do_grupo.empty else "Sem evento relacionado"
                )
                municipio_nota, chave_nota, texto_nota = identificar_observacao(
                    concentracao, os_grupo, observacoes_df, raio_concentracao
                )
                resumo_pdf.loc[resumo_pdf["ID_CONCENTRACAO"] == codigo, "OBSERVACAO_ANALISTA"] = texto_nota
                resumo_pdf.loc[resumo_pdf["ID_CONCENTRACAO"] == codigo, "EVENTOS_RELACIONADOS"] = len(eventos_do_grupo)
                indicador_nota = ("📝 " + texto_nota.replace("\n", " ")[:110] + ("…" if len(texto_nota) > 110 else "")) if texto_nota.strip() else "Sem acompanhamento registrado"
                bairros_grupo = str(concentracao.get("BAIRROS", "") or "").strip()
                titulo = (
                    f"{codigo} — {', '.join(cidades_grupo) or 'Município não informado'}"
                    f" — {bairros_grupo or 'Bairro não informado'} | "
                    f"{int(concentracao['QTD_OS'])} O.S. · "
                    f"{int(concentracao['QTD_MATRICULAS'])} matrículas · "
                    f"{qtd_ativos} ativo(s) próximo(s) · {indicador_eventos} · {indicador_nota}"
                )
                # Preservar TODOS os registros no formato original de expansores.
                # Somente a concentração ativa carrega o relatório detalhado,
                # evitando gerar tabelas e componentes pesados para as demais.
                ativa = str(codigo) == str(st.session_state.get("farol_v2_concentracao", ""))
                with st.expander(titulo, expanded=ativa):
                    if st.button("🗺️ Abrir mapa desta concentração" if not ativa else "📍 Mapa desta concentração aberto",
                                 key=f"foco_{codigo}", disabled=ativa):
                        st.session_state["farol_v2_concentracao"] = str(codigo)
                        st.session_state["farol_concentracao_expandida"] = str(codigo)
                        st.rerun()
                    if ativa:
                        if PODE_EDITAR_FAROL:
                            nota_editada = st.text_area("Observação do analista", value=texto_nota,
                                                        key=f"nota_{codigo}_{chave_nota}", height=90,
                                                        placeholder="Ex.: Contato com a operação, verificação do abastecimento, providências...")
                            if st.button("💾 Salvar acompanhamento", key=f"salvar_nota_{codigo}"):
                                try:
                                    salvar_observacao_concentracao(chave_nota, municipio_nota,
                                        float(concentracao["LATITUDE"]), float(concentracao["LONGITUDE"]), nota_editada)
                                    st.success("Acompanhamento salvo.")
                                    st.rerun()
                                except Exception as erro:
                                    st.error(f"Não foi possível salvar: {erro}")
                        else:
                            st.caption("Observação do analista: " + (texto_nota or "Nenhuma observação registrada."))
                        exibir_relatorio_concentracao(
                            codigo, concentracoes, pontos_cluster, proximidades,
                            df_eventos, int(raio_operacional), bairros
                        )
        # Disponível também quando não há concentrações no filtro atual.
        if concentracoes.empty:
            resumo_pdf = concentracoes.copy()
            observacoes_df = pd.DataFrame()
        with espaco_relatorio_operacional.container():
            st.caption("Relatórios API (exceto Teresina) ou THE (somente Teresina), com panorama e fichas individuais.")
            if st.button("📄 Configurar e gerar relatório (PDF)",
                         use_container_width=True, key="abrir_configuracao_relatorio"):
                modal_configurar_relatorio(resumo_pdf, analise, pontos_cluster,
                    proximidades, df_eventos, bairros, int(raio_operacional),
                    observacoes_df, df_pocos, df_loggers)
    # Sem dados de O.S.: manter a opção visível, porém desabilitada.
    if df_pontos.empty:
        espaco_relatorio_operacional.button(
            "📄 Gerar relatório operacional (PDF)", disabled=True,
            use_container_width=True, key="relatorio_sem_pontos"
        )



if st.session_state.get("farol_tela", "mapa") == "cadastros":
    espaco_relatorio_operacional.caption("📄 Relatório disponível na tela Mapa operacional.")
    st.subheader("Consulta de Poços / Ativos e Loggers")
    st.caption("Cadastros fixos carregados dos arquivos dados/pocos.csv e dados/loggers.csv do GitHub. Para atualizar, substitua os arquivos no repositório.")
    c_poco, c_logger = st.columns(2)
    with c_poco:
        st.markdown("### Poços / Ativos")
        st.metric("Registros", len(df_pocos))
        st.dataframe(df_pocos, use_container_width=True, hide_index=True)
    with c_logger:
        st.markdown("### Loggers")
        st.metric("Registros", len(df_loggers))
        st.dataframe(df_loggers, use_container_width=True, hide_index=True)
