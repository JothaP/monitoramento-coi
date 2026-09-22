# ============================================================
# MÓDULO: FILTRAGEM / CANCELAMENTO
# ============================================================

import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from datetime import datetime, time


# ============================================================
# 1. NORMALIZAÇÃO
# ============================================================

def normalizar_texto(texto):

    if pd.isna(texto):
        return ""

    texto = str(texto)

    texto = unicodedata.normalize("NFKD", texto)

    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.upper().strip()

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto


# ============================================================
# 2. LOCALIZAÇÃO DE COLUNAS
# ============================================================

def localizar_coluna(df, tipo):

    colunas_norm = {
        normalizar_texto(col): col
        for col in df.columns
    }

    if tipo == "protocolo":

        nome = "COD. PROTOCOLO ORIGEM"

        if nome in colunas_norm:
            return colunas_norm[nome]

        for normalizada, original in colunas_norm.items():

            if (
                "PROTOCOLO" in normalizada
                and "ORIGEM" in normalizada
            ):
                return original

        return None

    if tipo == "matricula":

        if "MATRICULA" in colunas_norm:
            return colunas_norm["MATRICULA"]

        for normalizada, original in colunas_norm.items():

            if "MATRICULA" in normalizada:
                return original

        return None

    if tipo == "cidade":

        if "CIDADE" in colunas_norm:
            return colunas_norm["CIDADE"]

        return None

    if tipo == "bairro":

        if "BAIRRO" in colunas_norm:
            return colunas_norm["BAIRRO"]

        for normalizada, original in colunas_norm.items():

            if "BAIRRO" in normalizada:
                return original

        return None

    if tipo == "data":

        if "INICIO DO SLA" in colunas_norm:
            return colunas_norm["INICIO DO SLA"]

        for normalizada, original in colunas_norm.items():

            if (
                "INICIO DO SLA" in normalizada
                or "INICIO SLA" in normalizada
            ):
                return original

        return None

    return None


# ============================================================
# 3. CONVERSÃO ROBUSTA DE DATAS
# ============================================================

def converter_datas_robusto(serie):

    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]"
    )

    for idx, valor in serie.items():

        if pd.isna(valor):
            continue

        # ----------------------------------------------------
        # Já é datetime
        # ----------------------------------------------------

        if isinstance(
            valor,
            (datetime, pd.Timestamp)
        ):

            resultado.loc[idx] = pd.Timestamp(valor)

            continue

        # ----------------------------------------------------
        # Número Excel
        # ----------------------------------------------------

        if isinstance(
            valor,
            (int, float)
        ) and not isinstance(valor, bool):

            try:

                numero = float(valor)

                if 1 <= numero <= 100000:

                    resultado.loc[idx] = (
                        pd.Timestamp("1899-12-30")
                        + pd.to_timedelta(
                            numero,
                            unit="D"
                        )
                    )

                    continue

            except Exception:
                pass

        # ----------------------------------------------------
        # Texto
        # ----------------------------------------------------

        texto = str(valor).strip()

        texto = re.sub(
            r"\s+[hH]$",
            "",
            texto
        )

        formatos = [
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",

            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",

            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]

        convertido = None

        for formato in formatos:

            try:

                convertido = datetime.strptime(
                    texto,
                    formato
                )

                break

            except ValueError:
                continue

        if convertido is not None:

            resultado.loc[idx] = convertido

            continue

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------

        try:

            convertido = pd.to_datetime(
                texto,
                dayfirst=True,
                errors="coerce"
            )

            if not pd.isna(convertido):

                resultado.loc[idx] = convertido

        except Exception:
            pass

    return resultado


# ============================================================
# 4. PROTOCOLO
# ============================================================

def parse_protocolo(proto):

    if pd.isna(proto):
        return "", "", None

    texto = str(proto).strip()

    match = re.search(
        r"(\d+)\s*/\s*(\d{4})",
        texto
    )

    if not match:

        return "", "", None

    numero = match.group(1)

    ano = match.group(2)

    numero_int = int(numero)

    return (
        numero,
        ano,
        numero_int
    )


# ============================================================
# 5. MAPA DE ZONAS
# ============================================================
#
# IMPORTANTE:
# Aqui deve permanecer o MAPA_ZONAS COMPLETO que você enviou.
#
# Não reduza este dicionário.
#
# ============================================================

MAPA_ZONAS_NORMALIZADO = {
    normalizar_texto(cidade): zona
    for cidade, zona in MAPA_ZONAS.items()
}


def obter_zona(cidade):

    cidade_normalizada = normalizar_texto(
        cidade
    )

    if not cidade_normalizada:
        return None

    return MAPA_ZONAS_NORMALIZADO.get(
        cidade_normalizada
    )


# ============================================================
# 6. OBTER BASE ATIVA
# ============================================================

def obter_backlog_ativo(modo):

    if modo == "API":

        return st.session_state.get(
            "df_api"
        )

    return st.session_state.get(
        "df_the"
    )


# ============================================================
# 7. PREPARAR BASE PARA FILTRAGEM
# ============================================================

def preparar_base_filtragem(df):

    if df is None:
        return None

    if df.empty:
        return None

    df = df.copy()

    coluna_data = localizar_coluna(
        df,
        "data"
    )

    if not coluna_data:

        raise ValueError(
            "A base não possui a coluna "
            "'Início do SLA'."
        )

    df["_DATA_SLA_FILTRAGEM"] = (
        converter_datas_robusto(
            df[coluna_data]
        )
    )

    coluna_cidade = localizar_coluna(
        df,
        "cidade"
    )

    coluna_bairro = localizar_coluna(
        df,
        "bairro"
    )

    if coluna_cidade:

        df["_CIDADE_FILTRAGEM"] = (
            df[coluna_cidade]
            .map(normalizar_texto)
        )

    else:

        df["_CIDADE_FILTRAGEM"] = ""

    if coluna_bairro:

        df["_BAIRRO_FILTRAGEM"] = (
            df[coluna_bairro]
            .map(normalizar_texto)
        )

    else:

        df["_BAIRRO_FILTRAGEM"] = ""

    return df


# ============================================================
# 8. APLICAR FILTROS
# ============================================================

def aplicar_filtros_filtragem(
    df,
    cidades=None,
    bairros=None,
    anos=None,
    meses=None,
    dias=None,
    hora_inicio=None,
    hora_fim=None
):

    if df is None or df.empty:

        return pd.DataFrame()

    resultado = df.copy()

    # --------------------------------------------------------
    # Cidade
    # --------------------------------------------------------

    if cidades:

        cidades_norm = {
            normalizar_texto(c)
            for c in cidades
        }

        resultado = resultado[
            resultado[
                "_CIDADE_FILTRAGEM"
            ].isin(cidades_norm)
        ]

    # --------------------------------------------------------
    # Bairro
    # --------------------------------------------------------

    if bairros:

        bairros_norm = {
            normalizar_texto(b)
            for b in bairros
        }

        resultado = resultado[
            resultado[
                "_BAIRRO_FILTRAGEM"
            ].isin(bairros_norm)
        ]

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    datas = resultado[
        "_DATA_SLA_FILTRAGEM"
    ]

    if anos:

        resultado = resultado[
            resultado[
                "_DATA_SLA_FILTRAGEM"
            ].dt.year.isin(anos)
        ]

    if meses:

        resultado = resultado[
            resultado[
                "_DATA_SLA_FILTRAGEM"
            ].dt.month.isin(meses)
        ]

    if dias:

        resultado = resultado[
            resultado[
                "_DATA_SLA_FILTRAGEM"
            ].dt.day.isin(dias)
        ]

    # --------------------------------------------------------
    # Horário
    # --------------------------------------------------------

    if (
        hora_inicio is not None
        and hora_fim is not None
    ):

        horas = (
            resultado[
                "_DATA_SLA_FILTRAGEM"
            ].dt.hour * 60
            +
            resultado[
                "_DATA_SLA_FILTRAGEM"
            ].dt.minute
        )

        inicio_min = (
            hora_inicio.hour * 60
            +
            hora_inicio.minute
        )

        fim_min = (
            hora_fim.hour * 60
            +
            hora_fim.minute
        )

        if inicio_min <= fim_min:

            mascara_hora = (
                (horas >= inicio_min)
                &
                (horas <= fim_min)
            )

        else:

            # Atravessa meia-noite
            mascara_hora = (
                (horas >= inicio_min)
                |
                (horas <= fim_min)
            )

        resultado = resultado[
            mascara_hora
        ]

    return resultado


# ============================================================
# 9. GERAR LOTE DE CANCELAMENTO
# ============================================================

def gerar_lote_filtragem(
    df_filtrado,
    modo,
    observacao
):

    if df_filtrado is None:
        raise ValueError(
            "Nenhum registro foi selecionado."
        )

    if df_filtrado.empty:
        raise ValueError(
            "Nenhuma O.S. atende aos filtros."
        )

    coluna_protocolo = localizar_coluna(
        df_filtrado,
        "protocolo"
    )

    coluna_matricula = localizar_coluna(
        df_filtrado,
        "matricula"
    )

    coluna_cidade = localizar_coluna(
        df_filtrado,
        "cidade"
    )

    if not coluna_protocolo:

        raise ValueError(
            "Não foi encontrada a coluna "
            "'COD. PROTOCOLO ORIGEM'."
        )

    if not coluna_matricula:

        raise ValueError(
            "Não foi encontrada a coluna "
            "'MATRICULA'."
        )

    if not coluna_cidade:

        raise ValueError(
            "Não foi encontrada a coluna "
            "'CIDADE'."
        )

    saida = []

    cidades_sem_zona = []

    protocolos_com_erro = []

    for _, linha in df_filtrado.iterrows():

        protocolo = linha[
            coluna_protocolo
        ]

        matricula = linha[
            coluna_matricula
        ]

        cidade = linha[
            coluna_cidade
        ]

        numero, ano, numero_int = (
            parse_protocolo(
                protocolo
            )
        )

        if numero_int is None:

            protocolos_com_erro.append({
                "Matrícula": matricula,
                "Protocolo": protocolo,
                "Cidade": cidade,
                "Motivo": "Protocolo inválido"
            })

            continue

        if modo == "THE":

            zona = 1

        else:

            zona = obter_zona(
                cidade
            )

            if zona is None:

                cidades_sem_zona.append({
                    "Matrícula": matricula,
                    "Protocolo": protocolo,
                    "Cidade": cidade,
                    "Motivo": "Cidade sem zona definida"
                })

                continue

        saida.append({
            "Matricula": matricula,
            "Zona Ligacao": zona,
            "Numero Do Pedido": numero_int,
            "Ano Do Pedido": int(ano),
            "Tipo Encerramento": 1,
            "Observações": observacao or ""
        })

    df_saida = pd.DataFrame(
        saida,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações"
        ]
    )

    if not df_saida.empty:

        df_saida[
            "Numero Do Pedido"
        ] = pd.to_numeric(
            df_saida[
                "Numero Do Pedido"
            ],
            errors="coerce"
        ).astype("Int64")

        df_saida[
            "Ano Do Pedido"
        ] = pd.to_numeric(
            df_saida[
                "Ano Do Pedido"
            ],
            errors="coerce"
        ).astype("Int64")

        df_saida[
            "Zona Ligacao"
        ] = pd.to_numeric(
            df_saida[
                "Zona Ligacao"
            ],
            errors="coerce"
        ).astype("Int64")

        df_saida[
            "Tipo Encerramento"
        ] = pd.to_numeric(
            df_saida[
                "Tipo Encerramento"
            ],
            errors="coerce"
        ).astype("Int64")

    logs = []

    logs.extend(
        cidades_sem_zona
    )

    logs.extend(
        protocolos_com_erro
    )

    df_log = pd.DataFrame(
        logs
    )

    return (
        df_saida,
        df_log,
        cidades_sem_zona,
        protocolos_com_erro
    )


# ============================================================
# 10. INTERFACE DO MÓDULO
# ============================================================

def modulo_filtragem():

    st.subheader(
        "🔎 Filtragem / Cancelamento"
    )

    st.caption(
        "Filtre o backlog carregado e gere "
        "o lote de cancelamento."
    )

    # --------------------------------------------------------
    # Modo
    # --------------------------------------------------------

    modo = st.radio(
        "Modo de operação",
        ["API", "THE"],
        horizontal=True,
        key="filtragem_modo"
    )

    df_base = obter_backlog_ativo(
        modo
    )

    if df_base is None or df_base.empty:

        st.info(
            f"Nenhuma base {modo} foi carregada."
        )

        return

    # --------------------------------------------------------
    # Preparação
    # --------------------------------------------------------

    try:

        df_trabalho = preparar_base_filtragem(
            df_base
        )

    except Exception as erro:

        st.error(
            str(erro)
        )

        return

    # --------------------------------------------------------
    # Valores disponíveis
    # --------------------------------------------------------

    cidades = sorted(
        [
            x for x in
            df_trabalho[
                "_CIDADE_FILTRAGEM"
            ].dropna().unique()
            if x
        ]
    )

    bairros = sorted(
        [
            x for x in
            df_trabalho[
                "_BAIRRO_FILTRAGEM"
            ].dropna().unique()
            if x
        ]
    )

    anos = sorted(
        df_trabalho[
            "_DATA_SLA_FILTRAGEM"
        ]
        .dropna()
        .dt.year
        .unique()
        .tolist()
    )

    meses = list(
        range(1, 13)
    )

    dias = list(
        range(1, 32)
    )

    nomes_meses = {
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
        12: "Dezembro"
    }

    # --------------------------------------------------------
    # Localização
    # --------------------------------------------------------

    st.markdown("### 📍 Localização")

    col1, col2 = st.columns(2)

    with col1:

        filtro_cidades = st.multiselect(
            "Cidade",
            options=cidades,
            key="filtragem_cidades"
        )

    with col2:

        filtro_bairros = st.multiselect(
            "Bairro",
            options=bairros,
            key="filtragem_bairros"
        )

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    st.markdown("### 📅 Data")

    col1, col2, col3 = st.columns(3)

    with col1:

        filtro_anos = st.multiselect(
            "Ano",
            options=anos,
            key="filtragem_anos"
        )

    with col2:

        filtro_meses = st.multiselect(
            "Mês",
            options=meses,
            format_func=lambda x:
                nomes_meses[x],
            key="filtragem_meses"
        )

    with col3:

        filtro_dias = st.multiselect(
            "Dia",
            options=dias,
            key="filtragem_dias"
        )

    # --------------------------------------------------------
    # Horário
    # --------------------------------------------------------

    st.markdown("### 🕐 Horário")

    col1, col2 = st.columns(2)

    with col1:

        hora_inicio = st.time_input(
            "Hora inicial",
            value=time(0, 0),
            key="filtragem_hora_inicio"
        )

    with col2:

        hora_fim = st.time_input(
            "Hora final",
            value=time(23, 59),
            key="filtragem_hora_fim"
        )

    st.caption(
        "O intervalo pode atravessar a meia-noite. "
        "Exemplo: 22:00 → 02:00."
    )

    # --------------------------------------------------------
    # Observação
    # --------------------------------------------------------

    st.markdown("### 📝 Observações")

    observacao = st.text_input(
        "Texto que será gravado no lote",
        key="filtragem_observacao"
    )

    # --------------------------------------------------------
    # Aplicação dos filtros
    # --------------------------------------------------------

    df_filtrado = aplicar_filtros_filtragem(
        df_trabalho,
        cidades=filtro_cidades,
        bairros=filtro_bairros,
        anos=filtro_anos,
        meses=filtro_meses,
        dias=filtro_dias,
        hora_inicio=hora_inicio,
        hora_fim=hora_fim
    )

    # --------------------------------------------------------
    # Indicadores
    # --------------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "O.S. consolidadas",
            f"{len(df_base):,}".replace(",", ".")
        )

    with col2:

        st.metric(
            "O.S. após filtros",
            f"{len(df_filtrado):,}".replace(",", ".")
        )

    # --------------------------------------------------------
    # Prévia
    # --------------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        btn_previa = st.button(
            "🔎 Prévia",
            use_container_width=True,
            key="btn_previa_filtragem"
        )

    with col2:

        btn_gerar = st.button(
            "📦 Gerar lote",
            type="primary",
            use_container_width=True,
            key="btn_gerar_filtragem"
        )

    # ========================================================
    # PRÉVIA
    # ========================================================

    if btn_previa:

        st.session_state.df_resultado = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

        st.markdown(
            "### 🔎 Prévia do resultado"
        )

        if df_filtrado.empty:

            st.warning(
                "Nenhuma O.S. atende aos filtros."
            )

        else:

            st.dataframe(
                df_filtrado.drop(
                    columns=[
                        "_DATA_SLA_FILTRAGEM",
                        "_CIDADE_FILTRAGEM",
                        "_BAIRRO_FILTRAGEM"
                    ],
                    errors="ignore"
                ).head(100),
                use_container_width=True,
                height=400
            )

    # ========================================================
    # GERAÇÃO
    # ========================================================

    if btn_gerar:

        if df_filtrado.empty:

            st.error(
                "Nenhuma O.S. atende aos filtros."
            )

        else:

            try:

                (
                    df_saida,
                    df_log,
                    cidades_sem_zona,
                    protocolos_com_erro
                ) = gerar_lote_filtragem(
                    df_filtrado,
                    modo,
                    observacao
                )

                if df_saida.empty:

                    st.warning(
                        "Nenhum registro pôde ser "
                        "gerado para o lote."
                    )

                    return

                # ------------------------------------------------
                # Excel
                # ------------------------------------------------

                buffer = io.BytesIO()

                with pd.ExcelWriter(
                    buffer,
                    engine="openpyxl"
                ) as writer:

                    df_saida.to_excel(
                        writer,
                        index=False,
                        sheet_name="Lote"
                    )

                buffer.seek(0)

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )

                nome_arquivo = (
                    f"Lote_Cancelamento_"
                    f"{modo}_"
                    f"{timestamp}.xlsx"
                )

                # ------------------------------------------------
                # Estado
                # ------------------------------------------------

                st.session_state.df_resultado = (
                    df_saida
                )

                st.session_state.df_log = (
                    df_log
                )

                st.session_state.nome_arquivo_resultado = (
                    nome_arquivo
                )

                st.session_state.arquivo_resultado_bytes = (
                    buffer.getvalue()
                )

                # ------------------------------------------------
                # Resultado
                # ------------------------------------------------

                st.success(
                    "✓ LOTE GERADO COM SUCESSO"
                )

                col1, col2, col3 = st.columns(3)

                with col1:

                    st.metric(
                        "O.S. consolidadas",
                        f"{len(df_base):,}".replace(
                            ",", "."
                        )
                    )

                with col2:

                    st.metric(
                        "Após filtros",
                        f"{len(df_filtrado):,}".replace(
                            ",", "."
                        )
                    )

                with col3:

                    st.metric(
                        "Registros no lote",
                        f"{len(df_saida):,}".replace(
                            ",", "."
                        )
                    )

                if cidades_sem_zona:

                    st.warning(
                        f"Cidades sem zona: "
                        f"{len(cidades_sem_zona):,}"
                        .replace(",", ".")
                    )

                if protocolos_com_erro:

                    st.warning(
                        f"Protocolos inválidos: "
                        f"{len(protocolos_com_erro):,}"
                        .replace(",", ".")
                    )

            except Exception as erro:

                st.error(
                    f"❌ ERRO AO GERAR O LOTE:\n\n{erro}"
                )

    # ========================================================
    # RESULTADO PERSISTENTE
    # ========================================================

    if (
        st.session_state.get(
            "df_resultado"
        ) is not None
    ):

        st.markdown(
            "### 📦 Lote gerado"
        )

        st.dataframe(
            st.session_state.df_resultado,
            use_container_width=True,
            height=400
        )

        st.download_button(
            "⬇️ Baixar lote",
            data=st.session_state.get(
                "arquivo_resultado_bytes"
            ),
            file_name=st.session_state.get(
                "nome_arquivo_resultado",
                "lote_cancelamento.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True
        )

        # ----------------------------------------------------
        # LOG
        # ----------------------------------------------------

        df_log = st.session_state.get(
            "df_log"
        )

        if (
            df_log is not None
            and not df_log.empty
        ):

            buffer_log = io.BytesIO()

            with pd.ExcelWriter(
                buffer_log,
                engine="openpyxl"
            ) as writer:

                df_log.to_excel(
                    writer,
                    index=False,
                    sheet_name="LOG"
                )

            buffer_log.seek(0)

            st.download_button(
                "📋 Baixar LOG",
                data=buffer_log.getvalue(),
                file_name=(
                    "LOG_"
                    +
                    st.session_state.get(
                        "nome_arquivo_resultado",
                        "lote"
                    )
                    .replace(
                        ".xlsx",
                        ""
                    )
                    +
                    ".xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                use_container_width=True
            )
