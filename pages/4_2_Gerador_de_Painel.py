            "Controle Operacional Integrado — COI"
        ),
        font=fonte(
            15,
        ),
        fill=CINZA,
    )

    draw.text(
        (
            largura - margem - 250,
            y_rodape + 25,
        ),
        datetime.now().strftime(
            "Gerado em %d/%m/%Y %H:%M"
        ),
        font=fonte(
            14,
        ),
        fill=CINZA,
    )

    # ========================================================
    # EXPORTAÇÃO
    # ========================================================

    output = io.BytesIO()

    imagem_rgb = imagem.convert(
        "RGB"
    )

    imagem_rgb.save(
        output,
        format="PNG",
        optimize=True,
    )

    output.seek(0)

    return output


# ============================================================
# INTERFACE
# ============================================================

st.markdown(
    '<div class="module-title">'
    "Relatório de Falta de Água - COI"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="module-subtitle">'
    "Geração de relatório consolidado de reclamações de Falta de Água."
    "</div>",
    unsafe_allow_html=True,
)


# ============================================================
# UPLOADS
# ============================================================

col_api, col_the, col_tim = st.columns(
    3,
    gap="medium",
)


with col_api:

    st.markdown("### API")

    arquivos_api = st.file_uploader(
        "Planilha(s) API",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_api",
    )


with col_the:

    st.markdown("### THE")

    arquivos_the = st.file_uploader(
        "Planilha(s) THE",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_the",
    )


with col_tim:

    st.markdown("### TIM")

    arquivos_tim = st.file_uploader(
        "Planilha(s) TIM",
        type=[
            "xlsx",
            "xls",
            "xlsb",
        ],
        accept_multiple_files=True,
        key="upload_tim",
    )


st.divider()


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.markdown(
    "### Configuração do relatório"
)

col1, col2 = st.columns(
    [1, 1],
    gap="large",
)


with col1:

    modulo = st.radio(
        "Empresa / operação",
        [
            "API",
            "THE",
            "TIM",
        ],
        horizontal=True,
    )


with col2:

    modo = st.radio(
        "Apresentação temporal",
        [
            "Por dia",
            "Por mês",
        ],
        horizontal=True,
    )


# ============================================================
# ARQUIVOS
# ============================================================

arquivos = {
    "API": arquivos_api,
    "THE": arquivos_the,
    "TIM": arquivos_tim,
}

arquivos_selecionados = arquivos[
    modulo
]


# ============================================================
# LEITURA E CONSOLIDAÇÃO
# ============================================================

if not arquivos_selecionados:

    st.info(
        f"Carregue uma ou mais planilhas de {modulo} "
        "para gerar o relatório."
    )

    st.stop()


with st.spinner(
