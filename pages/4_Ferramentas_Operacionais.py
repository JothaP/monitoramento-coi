# ============================================================
# 4.3 — CARDS OPERACIONAIS
# ============================================================

with col3:

    st.markdown("#### 🃏 Cards Operacionais")
    st.markdown("**Cards e Indicadores**")

    if st.session_state.get("perfil") == "admin":

        st.caption("Status: Em desenvolvimento (Admin)")

        if st.button(
            "Acessar Cards Operacionais",
            type="primary",
            use_container_width=True,
            key="btn_cards_operacionais",
        ):
            st.switch_page(
                "pages/4_3_Cards_Operacionais.py"
            )

    else:

        st.caption("Status: Em desenvolvimento")

        st.button(
            "Acessar Cards Operacionais",
            disabled=True,
            use_container_width=True,
            key="btn_cards_operacionais_bloqueado",
        )

        st.markdown(
            """
            <p style='font-size:12px; color:gray;'>
                🔒 Restrito a administradores
            </p>
            """,
            unsafe_allow_html=True,
        )
