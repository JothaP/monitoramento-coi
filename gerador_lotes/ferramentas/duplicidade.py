    # ========================================================
    # NAVEGAÇÃO
    # ========================================================

    st.divider()

    col_ret1, col_ret2 = st.columns(2)

    with col_ret1:
        if st.button(
            "⬅️ Voltar às Ferramentas",
            use_container_width=True,
            key=f"duplicidade_voltar_ferramentas_{modo.lower()}",
        ):
            st.switch_page(
                "pages/4_Ferramentas_Operacionais.py"
            )

    with col_ret2:
        if st.button(
            "🏠 Voltar ao Gerador de Lotes",
            use_container_width=True,
            key=f"duplicidade_voltar_hub_{modo.lower()}",
        ):
            st.switch_page(
                "pages/4_1_Gerador_Lotes_Cancelamento.py"
            )
