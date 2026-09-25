def aplicar_estilo_lista_rapida():
    st.markdown(
        """
        <style>

        /* =========================================================
           CABEÇALHO
           ========================================================= */

        .lista-rapida-header {
            margin-bottom: 24px;
        }

        .lista-rapida-header-title {
            font-size: 1.65rem;
            font-weight: 700;
            line-height: 1.2;
            margin-bottom: 5px;
        }

        .lista-rapida-header-description {
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.92rem;
        }


        /* =========================================================
           CARDS
           ========================================================= */

        .lista-rapida-card {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 12px;
            padding: 20px 22px;
            margin-bottom: 18px;
            background: rgba(128, 128, 128, 0.025);
        }

        .lista-rapida-card-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .lista-rapida-card-description {
            color: rgba(128, 128, 128, 0.9);
            font-size: 0.85rem;
            margin-bottom: 14px;
        }


        /* =========================================================
           SEÇÕES
           ========================================================= */

        .lista-rapida-section {
            margin-top: 8px;
            margin-bottom: 12px;
        }

        .lista-rapida-section-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin-bottom: 12px;
        }


        /* =========================================================
           MÉTRICAS
           ========================================================= */

        .lista-rapida-metricas {
            display: grid;
            grid-template-columns: repeat(
                4,
                minmax(0, 1fr)
            );
            gap: 12px;
            margin: 16px 0 20px 0;
        }

        .lista-rapida-metrica {
            border: 1px solid rgba(128, 128, 128, 0.22);
            border-radius: 10px;
            padding: 13px 16px;
            background: rgba(128, 128, 128, 0.025);
        }

        .lista-rapida-metrica-label {
            color: rgba(128, 128, 128, 0.9);
            font-size: 0.78rem;
            margin-bottom: 3px;
        }

        .lista-rapida-metrica-valor {
            font-size: 1.3rem;
            font-weight: 700;
            line-height: 1.2;
        }


        /* =========================================================
           PRÉVIA
           ========================================================= */

        .lista-rapida-preview-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin-bottom: 10px;
        }


        /* =========================================================
           BOTÕES — PADRÃO TEMA ESCURO
           ========================================================= */

        [data-testid="stButton"] > button,
        [data-testid="stDownloadButton"] > button {
            border-radius: 8px !important;
            min-height: 42px !important;
            font-weight: 600 !important;
            transition:
                background-color 0.15s ease,
                border-color 0.15s ease,
                color 0.15s ease !important;
        }


        /* Botões normais */

        [data-testid="stButton"] > button:not(
            [kind="primary"]
        ),
        [data-testid="stDownloadButton"] > button {
            background-color: transparent !important;
            color: inherit !important;
            border: 1px solid rgba(
                128,
                128,
                128,
                0.45
            ) !important;
        }

        [data-testid="stButton"] > button:not(
            [kind="primary"]
        ):hover,
        [data-testid="stDownloadButton"] > button:hover {
            background-color: rgba(
                128,
                128,
                128,
                0.12
            ) !important;
            color: inherit !important;
            border-color: rgba(
                128,
                128,
                128,
                0.65
            ) !important;
        }


        /* Botão primário */

        [data-testid="stButton"] > button[kind="primary"] {
            color: white !important;
            border: 1px solid transparent !important;
        }

        [data-testid="stButton"] > button[kind="primary"]:hover {
            filter: brightness(1.08);
        }


        /* Garante que o texto interno acompanhe o botão */

        [data-testid="stButton"] > button p,
        [data-testid="stButton"] > button span,
        [data-testid="stDownloadButton"] > button p,
        [data-testid="stDownloadButton"] > button span {
            color: inherit !important;
        }


        /* =========================================================
           RESPONSIVIDADE
           ========================================================= */

        @media (max-width: 900px) {
            .lista-rapida-metricas {
                grid-template-columns: repeat(
                    2,
                    minmax(0, 1fr)
                );
            }
        }

        @media (max-width: 600px) {
            .lista-rapida-metricas {
                grid-template-columns: 1fr;
            }

            .lista-rapida-card {
                padding: 16px;
            }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
