# ============================================================
# MÓDULO 1 — FILTRAGEM / CANCELAMENTO
# PLATAFORMA COI — GERADOR DE LOTES
# ============================================================
#
# Este módulo deve ser integrado ao HUB principal.
#
# Funções compartilhadas utilizadas:
#   - normalizar_texto()
#   - localizar_coluna()
#   - converter_datas_robusto()
#   - converter_hora()
#   - parse_protocolo()
#   - obter_zona()
#
# Estado compartilhado esperado:
#   st.session_state.df_api
#   st.session_state.df_the
#   st.session_state.modo_operacao
#   st.session_state.df_resultado
#   st.session_state.df_log
#   st.session_state.nome_arquivo_resultado
#
# ============================================================


# ============================================================
# 1. INICIALIZAÇÃO DO ESTADO
# ============================================================

def inicializar_estado_filtragem():

    valores_padrao = {
        "filtro_cidades": [],
        "filtro_bairros": [],
        "filtro_anos": [],
        "filtro_meses": [],
        "filtro_dias": [],

        "hora_inicio": "00:00",
        "hora_fim": "23:59",

        "observacoes_filtragem": "",

        "filtragem_preview": None,
        "filtragem_etapas": [],
        "filtragem_total_inicial": 0,

        "filtragem_geracao_info": None,

        "df_resultado": None,
        "df_log": None,
        "nome_arquivo_resultado": None,
    }

    for chave, valor in valores_padrao.items():

        if chave not in st.session_state:

            if isinstance(valor, list):
                st.session_state[chave] = valor.copy()

            else:
                st.session_state[chave] = valor


# ============================================================
# 2. OBTÉM A BASE ATIVA
# ============================================================

def obter_backlog_filtragem(modo=None):

    if modo is None:
        modo = st.session_state.get(
            "modo_operacao",
            "API"
        )

    modo = str(modo).upper().strip()

    if modo == "THE":

        return st.session_state.get(
            "df_the"
        )

    return st.session_state.get(
        "df_api"
    )


# ============================================================
# 3. COLUNAS DISPONÍVEIS
# ============================================================

def obter_colunas_filtragem(df):

    if df is None or df.empty:

        return {
            "cidade": None,
            "bairro": None,
            "data": None,
            "protocolo": None,
            "matricula": None,
        }

    return {
        "cidade": localizar_coluna(
            df,
            "cidade"
        ),

        "bairro": localizar_coluna(
            df,
            "bairro"
        ),

        "data": localizar_coluna(
            df,
            "data"
        ),

        "protocolo": localizar_coluna(
            df,
            "protocolo"
        ),

        "matricula": localizar_coluna(
            df,
            "matricula"
        ),
    }


# ============================================================
# 4. VALORES DE CIDADE
# ============================================================

def obter_cidades_filtragem(df):

    col_cidade = localizar_coluna(
        df,
        "cidade"
    )

    if col_cidade is None:

        return []

    valores = (
        df[col_cidade]
        .dropna()
        .astype(str)
        .str.strip()
    )

    valores = valores[
        valores != ""
    ]

    resultado = {}

    for valor in valores:

        normalizado = normalizar_texto(
            valor
        )

        if not normalizado:
            continue

        if normalizado not in resultado:

            resultado[normalizado] = valor

    return sorted(
        resultado.values(),
        key=normalizar_texto
    )


# ============================================================
# 5. VALORES DE BAIRRO
# ============================================================

def obter_bairros_filtragem(
    df,
    cidades_selecionadas=None
):

    col_bairro = localizar_coluna(
        df,
        "bairro"
    )

    if col_bairro is None:

        return []

    base = df

    cidades_selecionadas = (
        cidades_selecionadas
        or []
    )

    if cidades_selecionadas:

        col_cidade = localizar_coluna(
            df,
            "cidade"
        )

        if col_cidade is not None:

            cidades_norm = {
                normalizar_texto(cidade)
                for cidade
                in cidades_selecionadas
            }

            mascara = (
                df[col_cidade]
                .map(normalizar_texto)
                .isin(cidades_norm)
            )

            base = df.loc[
                mascara
            ]

    valores = (
        base[col_bairro]
        .dropna()
        .astype(str)
        .str.strip()
    )

    valores = valores[
        valores != ""
    ]

    resultado = {}

    for valor in valores:

        normalizado = normalizar_texto(
            valor
        )

        if not normalizado:
            continue

        if normalizado not in resultado:

            resultado[normalizado] = valor

    return sorted(
        resultado.values(),
        key=normalizar_texto
    )


# ============================================================
# 6. OBTÉM ANOS DISPONÍVEIS
# ============================================================

def obter_anos_filtragem(df):

    col_data = localizar_coluna(
        df,
        "data"
    )

    if col_data is None:
        return []

    datas = converter_datas_robusto(
        df[col_data]
    )

    anos = (
        datas
        .dropna()
        .dt.year
        .astype(int)
        .unique()
        .tolist()
    )

    anos = list(anos)

    anos.sort()

    return anos


# ============================================================
# 7. MESES
# ============================================================

MESES_FILTRAGEM = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def obter_meses_filtragem():

    return list(
        MESES_FILTRAGEM.keys()
    )


# ============================================================
# 8. DIAS
# ============================================================

def obter_dias_filtragem():

    return list(
        range(1, 32)
    )


# ============================================================
# 9. APLICAÇÃO DOS FILTROS
# ============================================================
#
# ESTA É A CONVERSÃO DIRETA DA LÓGICA ORIGINAL.
#
# As regras de negócio foram preservadas.
# ============================================================

def aplicar_filtros_filtragem(
    df_consolidado
):

    if df_consolidado is None:

        raise ValueError(
            "Nenhum arquivo foi carregado."
        )

    if df_consolidado.empty:

        raise ValueError(
            "A base carregada está vazia."
        )

    df = df_consolidado.copy()

    total_inicial = len(df)

    col_cidade = localizar_coluna(
        df,
        "cidade"
    )

    col_bairro = localizar_coluna(
        df,
        "bairro"
    )

    col_data = localizar_coluna(
        df,
        "data"
    )

    etapas = []


    # ========================================================
    # CIDADE
    # ========================================================

    cidades_selecionadas = list(
        st.session_state.get(
            "filtro_cidades",
            []
        )
    )

    if cidades_selecionadas:

        if col_cidade is None:

            raise ValueError(
                "A planilha não possui a coluna Cidade."
            )

        cidades_norm = {
            normalizar_texto(cidade)
            for cidade in cidades_selecionadas
        }

        mascara = (
            df[col_cidade]
            .map(normalizar_texto)
            .isin(cidades_norm)
        )

        df = df.loc[
            mascara
        ]

        etapas.append(
            (
                "Cidade",
                len(df)
            )
        )


    # ========================================================
    # BAIRRO
    # ========================================================

    bairros_selecionados = list(
        st.session_state.get(
            "filtro_bairros",
            []
        )
    )

    if bairros_selecionados:

        if col_bairro is None:

            raise ValueError(
                "A planilha não possui a coluna Bairro."
            )

        bairros_norm = {
            normalizar_texto(bairro)
            for bairro in bairros_selecionados
        }

        mascara = (
            df[col_bairro]
            .map(normalizar_texto)
            .isin(bairros_norm)
        )

        df = df.loc[
            mascara
        ]

        etapas.append(
            (
                "Bairro",
                len(df)
            )
        )


    # ========================================================
    # DATA
    # ========================================================

    anos_selecionados = list(
        st.session_state.get(
            "filtro_anos",
            []
        )
    )

    meses_selecionados = list(
        st.session_state.get(
            "filtro_meses",
            []
        )
    )

    dias_selecionados = list(
        st.session_state.get(
            "filtro_dias",
            []
        )
    )


    inicio = converter_hora(
        st.session_state.get(
            "hora_inicio",
            "00:00"
        )
    )

    fim = converter_hora(
        st.session_state.get(
            "hora_fim",
            "23:59"
        )
    )


    # ========================================================
    # INTERVALO DE HORÁRIO
    #
    # 00:00 → 23:59 = sem restrição
    #
    # Se início > fim:
    # atravessa a meia-noite.
    # ========================================================

    horario_restrito = not (
        inicio == time(0, 0)
        and
        fim == time(23, 59)
    )


    precisa_data = (
        bool(anos_selecionados)
        or
        bool(meses_selecionados)
        or
        bool(dias_selecionados)
        or
        horario_restrito
    )


    if precisa_data:

        if col_data is None:

            raise ValueError(
                "A planilha não possui a coluna "
                "'Início do SLA'.\n\n"
                "A ferramenta utiliza exclusivamente "
                "'Início do SLA' como data de referência."
            )


        datas = converter_datas_robusto(
            df[col_data]
        )


        # ====================================================
        # ANO
        # ====================================================

        if anos_selecionados:

            anos = {
                int(ano)
                for ano in anos_selecionados
            }

            mascara = (
                datas.dt.year
                .isin(anos)
            )

            df = df.loc[
                mascara
            ]

            datas = converter_datas_robusto(
                df[col_data]
            )

            etapas.append(
                (
                    "Ano",
                    len(df)
                )
            )


        # ====================================================
        # MÊS
        # ====================================================

        if meses_selecionados:

            meses = {
                int(mes)
                for mes in meses_selecionados
            }

            mascara = (
                datas.dt.month
                .isin(meses)
            )

            df = df.loc[
                mascara
            ]

            datas = converter_datas_robusto(
                df[col_data]
            )

            etapas.append(
                (
                    "Mês",
                    len(df)
                )
            )


        # ====================================================
        # DIA
        # ====================================================

        if dias_selecionados:

            dias = {
                int(dia)
                for dia in dias_selecionados
            }

            mascara = (
                datas.dt.day
                .isin(dias)
            )

            df = df.loc[
                mascara
            ]

            datas = converter_datas_robusto(
                df[col_data]
            )

            etapas.append(
                (
                    "Dia",
                    len(df)
                )
            )


        # ====================================================
        # HORÁRIO
        # ====================================================

        if horario_restrito:

            inicio_segundos = (
                inicio.hour * 3600
                +
                inicio.minute * 60
            )

            fim_segundos = (
                fim.hour * 3600
                +
                fim.minute * 60
                +
                59
            )

            segundos = (
                datas.dt.hour * 3600
                +
                datas.dt.minute * 60
                +
                datas.dt.second
            )


            if inicio_segundos <= fim_segundos:

                mascara_horario = (
                    datas.notna()
                    &
                    (segundos >= inicio_segundos)
                    &
                    (segundos <= fim_segundos)
                )

            else:

                mascara_horario = (
                    datas.notna()
                    &
                    (
                        (segundos >= inicio_segundos)
                        |
                        (segundos <= fim_segundos)
                    )
                )


            df = df.loc[
                mascara_horario
            ]

            etapas.append(
                (
                    "Horário",
                    len(df)
                )
            )


    df_filtrado_atual = (
        df
        .reset_index(drop=True)
    )


    return (
        df_filtrado_atual,
        etapas,
        total_inicial
    )


# ============================================================
# 10. GERAÇÃO DO LOTE DE CANCELAMENTO
# ============================================================

def gerar_lote_filtragem():

    modo = str(
        st.session_state.get(
            "modo_operacao",
            "API"
        )
    ).upper().strip()


    df_consolidado = obter_backlog_filtragem(
        modo
    )


    if df_consolidado is None:

        raise ValueError(
            f"Nenhuma base do modo {modo} foi carregada."
        )


    if df_consolidado.empty:

        raise ValueError(
            f"A base {modo} está vazia."
        )


    # ========================================================
    # APLICA FILTROS
    # ========================================================

    (
        df_filtrado,
        etapas,
        total_inicial
    ) = aplicar_filtros_filtragem(
        df_consolidado
    )


    st.session_state.filtragem_total_inicial = (
        total_inicial
    )

    st.session_state.filtragem_etapas = (
        etapas
    )

    st.session_state.filtragem_preview = (
        df_filtrado.copy()
    )


    if df_filtrado.empty:

        st.session_state.df_resultado = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

        raise ValueError(
            "Nenhuma O.S. foi encontrada com os filtros selecionados."
        )


    # ========================================================
    # LOCALIZA COLUNAS
    # ========================================================

    col_protocolo = localizar_coluna(
        df_filtrado,
        "protocolo"
    )

    col_matricula = localizar_coluna(
        df_filtrado,
        "matricula"
    )

    col_cidade = localizar_coluna(
        df_filtrado,
        "cidade"
    )


    if col_protocolo is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'COD. PROTOCOLO ORIGEM'."
        )


    if col_matricula is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'MATRICULA'."
        )


    if col_cidade is None:

        raise ValueError(
            "A planilha não possui a coluna "
            "'CIDADE'."
        )


    # ========================================================
    # OBSERVAÇÃO
    # ========================================================

    observacao = str(
        st.session_state.get(
            "observacoes_filtragem",
            ""
        )
    ).strip()


    # ========================================================
    # LISTAS DE LOG
    # ========================================================

    cidades_sem_zona = []
    protocolos_invalidos = []


    resultados = []


    # ========================================================
    # PROCESSAMENTO
    # ========================================================

    for _, linha in df_filtrado.iterrows():

        matricula = linha[
            col_matricula
        ]

        cidade = linha[
            col_cidade
        ]

        protocolo = linha[
            col_protocolo
        ]


        # ----------------------------------------------------
        # PROTOCOLO
        # ----------------------------------------------------

        numero_pedido, ano_pedido, numero_int = (
            parse_protocolo(
                protocolo
            )
        )


        if numero_int is None:

            protocolos_invalidos.append(
                {
                    "Matrícula": matricula,
                    "Protocolo": protocolo,
                    "Cidade": cidade,
                    "Motivo": (
                        "Protocolo não está no formato "
                        "número/ano."
                    ),
                }
            )

            continue


        # ----------------------------------------------------
        # ZONA
        # ----------------------------------------------------

        if modo == "THE":

            zona = 1

        else:

            zona = obter_zona(
                cidade
            )

            if zona is None:

                cidades_sem_zona.append(
                    {
                        "Matrícula": matricula,
                        "Protocolo": protocolo,
                        "Cidade": cidade,
                        "Motivo": (
                            "Cidade não possui zona "
                            "definida no MAPA_ZONAS."
                        ),
                    }
                )

                continue


        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        resultados.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_int,
                "Ano Do Pedido": int(ano_pedido),
                "Tipo Encerramento": 1,
                "Observações": observacao,
            }
        )


    # ========================================================
    # DATAFRAME FINAL
    # ========================================================

    df_resultado = pd.DataFrame(
        resultados,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações",
        ]
    )


    if df_resultado.empty:

        st.session_state.df_resultado = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

        raise ValueError(
            "Nenhuma O.S. válida pôde ser convertida em lote."
        )


    # ========================================================
    # TIPOS NUMÉRICOS
    # ========================================================

    df_resultado[
        "Zona Ligacao"
    ] = pd.to_numeric(
        df_resultado[
            "Zona Ligacao"
        ],
        errors="coerce"
    ).astype("Int64")


    df_resultado[
        "Numero Do Pedido"
    ] = pd.to_numeric(
        df_resultado[
            "Numero Do Pedido"
        ],
        errors="coerce"
    ).astype("Int64")


    df_resultado[
        "Ano Do Pedido"
    ] = pd.to_numeric(
        df_resultado[
            "Ano Do Pedido"
        ],
        errors="coerce"
    ).astype("Int64")


    df_resultado[
        "Tipo Encerramento"
    ] = pd.to_numeric(
        df_resultado[
            "Tipo Encerramento"
        ],
        errors="coerce"
    ).astype("Int64")


    # ========================================================
    # LOG
    # ========================================================

    linhas_log = []


    for item in cidades_sem_zona:

        linhas_log.append(
            {
                "Tipo": "Cidade sem zona",
                "Matrícula": item["Matrícula"],
                "Protocolo": item["Protocolo"],
                "Cidade": item["Cidade"],
                "Motivo": item["Motivo"],
            }
        )


    for item in protocolos_invalidos:

        linhas_log.append(
            {
                "Tipo": "Protocolo inválido",
                "Matrícula": item["Matrícula"],
                "Protocolo": item["Protocolo"],
                "Cidade": item["Cidade"],
                "Motivo": item["Motivo"],
            }
        )


    if linhas_log:

        df_log = pd.DataFrame(
            linhas_log
        )

    else:

        df_log = pd.DataFrame(
            columns=[
                "Tipo",
                "Matrícula",
                "Protocolo",
                "Cidade",
                "Motivo",
            ]
        )


    # ========================================================
    # NOME DO ARQUIVO
    # ========================================================

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )


    nome_arquivo = (
        f"Lote_Cancelamento_"
        f"{modo}_"
        f"{timestamp}.xlsx"
    )


    # ========================================================
    # SALVA NO SESSION STATE
    # ========================================================

    st.session_state.df_resultado = (
        df_resultado
    )

    st.session_state.df_log = (
        df_log
    )

    st.session_state.nome_arquivo_resultado = (
        nome_arquivo
    )


    st.session_state.filtragem_geracao_info = {
        "modo": modo,
        "total_inicial": total_inicial,
        "total_filtrado": len(df_filtrado),
        "total_resultado": len(df_resultado),
        "cidades_sem_zona": len(
            cidades_sem_zona
        ),
        "protocolos_invalidos": len(
            protocolos_invalidos
        ),
        "etapas": etapas,
    }


    return (
        df_resultado,
        df_log
    )


# ============================================================
# 11. CONVERTE DATAFRAME PARA EXCEL
# ============================================================

def dataframe_para_excel_filtragem(
    df,
    nome_aba="Lote"
):

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name=nome_aba
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# 12. CONVERTE LOG PARA EXCEL
# ============================================================

def log_para_excel_filtragem(
    df_log
):

    if df_log is None:

        return None

    if df_log.empty:

        return None

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df_log.to_excel(
            writer,
            index=False,
            sheet_name="LOG"
        )

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# 13. LIMPA SOMENTE O RESULTADO
# ============================================================

def limpar_resultado_filtragem():

    st.session_state.df_resultado = None

    st.session_state.df_log = None

    st.session_state.nome_arquivo_resultado = None

    st.session_state.filtragem_preview = None

    st.session_state.filtragem_etapas = []

    st.session_state.filtragem_total_inicial = 0

    st.session_state.filtragem_geracao_info = None


# ============================================================
# 14. INTERFACE DO MÓDULO
# ============================================================

def render_filtragem_cancelamento():

    inicializar_estado_filtragem()


    # ========================================================
    # BASE ATIVA
    # ========================================================

    modo = str(
        st.session_state.get(
            "modo_operacao",
            "API"
        )
    ).upper().strip()


    df = obter_backlog_filtragem(
        modo
    )


    st.subheader(
        "🔎 Filtragem / Cancelamento"
    )

    st.caption(
        "Filtre o backlog ativo e gere o lote de cancelamento."
    )


    # ========================================================
    # STATUS DA BASE
    # ========================================================

    if df is None:

        st.warning(
            f"Nenhuma base {modo} foi carregada."
        )

        st.info(
            "Carregue a base pelo painel de Uploads do HUB."
        )

        return


    if df.empty:

        st.error(
            f"A base {modo} está vazia."
        )

        return


    colunas = obter_colunas_filtragem(
        df
    )


    # ========================================================
    # RESUMO
    # ========================================================

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Modo ativo",
            modo
        )

    with col2:

        st.metric(
            "Registros na base",
            f"{len(df):,}".replace(
                ",",
                "."
            )
        )

    with col3:

        st.metric(
            "Coluna temporal",
            colunas["data"]
            or "Não encontrada"
        )


    st.divider()


    # ========================================================
    # FILTROS DE LOCALIZAÇÃO
    # ========================================================

    st.markdown(
        "### 📍 Localização"
    )


    cidades_disponiveis = (
        obter_cidades_filtragem(
            df
        )
    )


    cidades_atuais = (
        st.session_state.get(
            "filtro_cidades",
            []
        )
    )


    cidades_validas = [
        cidade
        for cidade
        in cidades_atuais
        if cidade in cidades_disponiveis
    ]


    cidades_selecionadas = st.multiselect(
        "Cidade",
        options=cidades_disponiveis,
        default=cidades_validas,
        key="ui_filtro_cidades",
        help=(
            "Selecione uma ou mais cidades. "
            "Sem seleção, todas as cidades serão consideradas."
        )
    )


    st.session_state.filtro_cidades = (
        cidades_selecionadas
    )


    # --------------------------------------------------------
    # BAIRROS
    # --------------------------------------------------------

    bairros_disponiveis = (
        obter_bairros_filtragem(
            df,
            cidades_selecionadas
        )
    )


    bairros_atuais = (
        st.session_state.get(
            "filtro_bairros",
            []
        )
    )


    bairros_validos = [
        bairro
        for bairro
        in bairros_atuais
        if bairro in bairros_disponiveis
    ]


    bairros_selecionados = st.multiselect(
        "Bairro",
        options=bairros_disponiveis,
        default=bairros_validos,
        key="ui_filtro_bairros",
        help=(
            "Selecione um ou mais bairros. "
            "Sem seleção, todos os bairros serão considerados."
        )
    )


    st.session_state.filtro_bairros = (
        bairros_selecionados
    )


    st.divider()


    # ========================================================
    # FILTROS DE DATA
    # ========================================================

    st.markdown(
        "### 📅 Data — Início do SLA"
    )


    if colunas["data"] is None:

        st.warning(
            "A base não possui uma coluna identificável "
            "como 'Início do SLA'. Os filtros temporais "
            "ficarão indisponíveis."
        )

    else:

        anos_disponiveis = (
            obter_anos_filtragem(
                df
            )
        )


        anos_atuais = (
            st.session_state.get(
                "filtro_anos",
                []
            )
        )


        anos_validos = [
            ano
            for ano in anos_atuais
            if ano in anos_disponiveis
        ]


        anos_selecionados = st.multiselect(
            "Ano",
            options=anos_disponiveis,
            default=anos_validos,
            key="ui_filtro_anos",
            help=(
                "Filtra pelo ano do Início do SLA."
            )
        )


        st.session_state.filtro_anos = (
            anos_selecionados
        )


        col_mes, col_dia = st.columns(2)


        with col_mes:

            meses_disponiveis = (
                obter_meses_filtragem()
            )


            meses_atuais = (
                st.session_state.get(
                    "filtro_meses",
                    []
                )
            )


            meses_validos = [
                mes
                for mes
                in meses_atuais
                if mes in meses_disponiveis
            ]


            meses_selecionados = st.multiselect(
                "Mês",
                options=meses_disponiveis,
                default=meses_validos,
                format_func=lambda x:
                    f"{x:02d} — {MESES_FILTRAGEM[x]}",
                key="ui_filtro_meses",
                help=(
                    "Filtra pelo mês do Início do SLA."
                )
            )


            st.session_state.filtro_meses = (
                meses_selecionados
            )


        with col_dia:

            dias_disponiveis = (
                obter_dias_filtragem()
            )


            dias_atuais = (
                st.session_state.get(
                    "filtro_dias",
                    []
                )
            )


            dias_validos = [
                dia
                for dia
                in dias_atuais
                if dia in dias_disponiveis
            ]


            dias_selecionados = st.multiselect(
                "Dia",
                options=dias_disponiveis,
                default=dias_validos,
                key="ui_filtro_dias",
                help=(
                    "Filtra pelo dia do Início do SLA."
                )
            )


            st.session_state.filtro_dias = (
                dias_selecionados
            )


        # ====================================================
        # HORÁRIO
        # ====================================================

        st.markdown(
            "#### ⏰ Horário"
        )


        col_hora1, col_hora2 = st.columns(2)


        with col_hora1:

            hora_inicio = st.text_input(
                "Hora inicial",
                value=st.session_state.get(
                    "hora_inicio",
                    "00:00"
                ),
                key="ui_hora_inicio",
                placeholder="HH:MM"
            )

            st.session_state.hora_inicio = (
                hora_inicio
            )


        with col_hora2:

            hora_fim = st.text_input(
                "Hora final",
                value=st.session_state.get(
                    "hora_fim",
                    "23:59"
                ),
                key="ui_hora_fim",
                placeholder="HH:MM"
            )

            st.session_state.hora_fim = (
                hora_fim
            )


        st.caption(
            "Use 00:00 → 23:59 para não restringir o horário. "
            "Também é permitido atravessar a meia-noite, "
            "por exemplo, 22:00 → 02:00."
        )


    st.divider()


    # ========================================================
    # OBSERVAÇÃO
    # ========================================================

    st.markdown(
        "### 📝 Observação do cancelamento"
    )


    observacao = st.text_area(
        "Observações",
        value=st.session_state.get(
            "observacoes_filtragem",
            ""
        ),
        key="ui_observacoes_filtragem",
        placeholder=(
            "Digite a observação que será gravada "
            "no lote de cancelamento."
        ),
        height=100
    )


    st.session_state.observacoes_filtragem = (
        observacao
    )


    st.divider()


    # ========================================================
    # BOTÕES
    # ========================================================

    col_preview, col_generate, col_clear = (
        st.columns(
            [1, 1, 1]
        )
    )


    # ========================================================
    # PRÉVIA
    # ========================================================

    with col_preview:

        if st.button(
            "👁️ Prévia",
            key="btn_filtragem_preview",
            use_container_width=True
        ):

            try:

                (
                    df_preview,
                    etapas,
                    total_inicial
                ) = aplicar_filtros_filtragem(
                    df
                )


                st.session_state.filtragem_preview = (
                    df_preview.copy()
                )

                st.session_state.filtragem_etapas = (
                    etapas
                )

                st.session_state.filtragem_total_inicial = (
                    total_inicial
                )


                st.success(
                    "Prévia atualizada."
                )

            except Exception as erro:

                st.error(
                    str(erro)
                )


    # ========================================================
    # GERAR
    # ========================================================

    with col_generate:

        if st.button(
            "📦 Gerar lote",
            key="btn_filtragem_gerar",
            type="primary",
            use_container_width=True
        ):

            try:

                gerar_lote_filtragem()

                st.success(
                    "✓ Lote gerado com sucesso."
                )

            except Exception as erro:

                st.error(
                    str(erro)
                )


    # ========================================================
    # LIMPAR RESULTADO
    # ========================================================

    with col_clear:

        if st.button(
            "🧹 Limpar resultado",
            key="btn_filtragem_limpar",
            use_container_width=True
        ):

            limpar_resultado_filtragem()

            st.rerun()


    # ========================================================
    # PRÉVIA
    # ========================================================

    df_preview = (
        st.session_state.get(
            "filtragem_preview"
        )
    )


    if df_preview is not None:

        st.divider()

        st.markdown(
            "### 👁️ Prévia da filtragem"
        )


        total_inicial = (
            st.session_state.get(
                "filtragem_total_inicial",
                len(df)
            )
        )


        total_filtrado = len(
            df_preview
        )


        c1, c2, c3 = st.columns(3)


        with c1:

            st.metric(
                "Total inicial",
                f"{total_inicial:,}".replace(
                    ",",
                    "."
                )
            )


        with c2:

            st.metric(
                "Após filtros",
                f"{total_filtrado:,}".replace(
                    ",",
                    "."
                )
            )


        with c3:

            if total_inicial:

                percentual = (
                    total_filtrado
                    /
                    total_inicial
                    *
                    100
                )

                st.metric(
                    "Percentual restante",
                    f"{percentual:.2f}%"
                )

            else:

                st.metric(
                    "Percentual restante",
                    "0%"
                )


        etapas = (
            st.session_state.get(
                "filtragem_etapas",
                []
            )
        )


        if etapas:

            st.markdown(
                "#### Etapas do filtro"
            )


            dados_etapas = []

            anterior = total_inicial


            for nome, quantidade in etapas:

                dados_etapas.append(
                    {
                        "Filtro": nome,
                        "Registros após filtro": quantidade,
                        "Redução": anterior - quantidade,
                    }
                )

                anterior = quantidade


            st.dataframe(
                pd.DataFrame(
                    dados_etapas
                ),
                use_container_width=True,
                hide_index=True
            )


        st.markdown(
            "#### Registros encontrados"
        )


        st.dataframe(
            df_preview.head(100),
            use_container_width=True,
            hide_index=True
        )


        if len(df_preview) > 100:

            st.caption(
                f"Exibindo os primeiros 100 de "
                f"{len(df_preview):,} registros."
            )


    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    df_resultado = (
        st.session_state.get(
            "df_resultado"
        )
    )


    if df_resultado is not None:

        st.divider()

        st.markdown(
            "### ✅ Lote gerado"
        )


        info = (
            st.session_state.get(
                "filtragem_geracao_info",
                {}
            )
        )


        c1, c2, c3, c4 = st.columns(4)


        with c1:

            st.metric(
                "Base",
                info.get(
                    "modo",
                    modo
                )
            )


        with c2:

            st.metric(
                "Filtrados",
                f"{info.get('total_filtrado', 0):,}".replace(
                    ",",
                    "."
                )
            )


        with c3:

            st.metric(
                "Incluídos no lote",
                f"{info.get('total_resultado', 0):,}".replace(
                    ",",
                    "."
                )
            )


        with c4:

            st.metric(
                "Ocorrências no LOG",
                f"{len(st.session_state.get('df_log', pd.DataFrame())):,}".replace(
                    ",",
                    "."
                )
            )


        # ====================================================
        # AVISOS
        # ====================================================

        qtd_sem_zona = info.get(
            "cidades_sem_zona",
            0
        )

        qtd_protocolos = info.get(
            "protocolos_invalidos",
            0
        )


        if qtd_sem_zona:

            st.warning(
                f"{qtd_sem_zona} registro(s) "
                "não incluído(s) por cidade sem zona definida."
            )


        if qtd_protocolos:

            st.warning(
                f"{qtd_protocolos} registro(s) "
                "não incluído(s) por protocolo inválido."
            )


        # ====================================================
        # RESULTADO
        # ====================================================

        st.markdown(
            "#### Conteúdo do lote"
        )


        st.dataframe(
            df_resultado.head(100),
            use_container_width=True,
            hide_index=True
        )


        if len(df_resultado) > 100:

            st.caption(
                f"Exibindo os primeiros 100 de "
                f"{len(df_resultado):,} registros."
            )


        # ====================================================
        # DOWNLOAD DO LOTE
        # ====================================================

        nome_arquivo = (
            st.session_state.get(
                "nome_arquivo_resultado",
                "Lote_Cancelamento.xlsx"
            )
        )


        excel_bytes = (
            dataframe_para_excel_filtragem(
                df_resultado
            )
        )


        st.download_button(
            label="⬇️ Baixar lote de cancelamento",
            data=excel_bytes,
            file_name=nome_arquivo,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key="download_lote_filtragem",
            use_container_width=True
        )


        # ====================================================
        # LOG
        # ====================================================

        df_log = (
            st.session_state.get(
                "df_log"
            )
        )


        if (
            df_log is not None
            and
            not df_log.empty
        ):

            st.markdown(
                "#### LOG de processamento"
            )


            st.dataframe(
                df_log,
                use_container_width=True,
                hide_index=True
            )


            log_bytes = (
                log_para_excel_filtragem(
                    df_log
                )
            )


            timestamp_log = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )


            nome_log = (
                f"LOG_Lote_Cancelamento_"
                f"{modo}_"
                f"{timestamp_log}.xlsx"
            )


            st.download_button(
                label="⬇️ Baixar LOG",
                data=log_bytes,
                file_name=nome_log,
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key="download_log_filtragem",
                use_container_width=True
            )

        else:

            st.success(
                "✓ Nenhuma ocorrência foi registrada no LOG."
            )
