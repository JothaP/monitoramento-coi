import re
from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from ..estado import (
    base_carregada,
    obter_base,
    limpar_resultado,
)

from ..exportacao import dataframe_para_excel

from ..zonas import (
    normalizar_texto,
    obter_zona,
)

from .componentes import (
    selecionar_modo_api_the,
)


# ============================================================
# CONFIGURAÇÕES DO FILTRO DE HORÁRIO
# ============================================================

# A O.S. pode ser aberta até 1 hora antes do início informado.
MARGEM_HORA_INICIAL = timedelta(hours=1)

# A O.S. pode ser aberta até 3 horas depois do fim informado.
MARGEM_HORA_FINAL = timedelta(hours=3)


# ============================================================
# LOCALIZAÇÃO DE COLUNAS
# ============================================================

def localizar_coluna(df, tipo):

    if df is None or df.empty:
        return None

    mapa = {
        "protocolo": "COD. PROTOCOLO ORIGEM",
        "matricula": "MATRICULA",
        "cidade": "CIDADE",
        "bairro": "BAIRRO",
        "data": "INÍCIO DO SLA",
    }

    alvo = mapa.get(tipo)

    if not alvo:
        return None

    colunas = list(df.columns)

    normalizadas = {
        normalizar_texto(coluna): coluna
        for coluna in colunas
    }

    alvo_normalizado = normalizar_texto(alvo)

    if alvo_normalizado in normalizadas:
        return normalizadas[alvo_normalizado]

    if tipo == "protocolo":

        for coluna in colunas:

            nome = normalizar_texto(coluna)

            if (
                "PROTOCOLO" in nome
                and "ORIGEM" in nome
            ):
                return coluna

    elif tipo == "matricula":

        for coluna in colunas:

            nome = normalizar_texto(coluna)

            if "MATRICULA" in nome:
                return coluna

    elif tipo == "cidade":

        for coluna in colunas:

            nome = normalizar_texto(coluna)

            if "CIDADE" in nome:
                return coluna

    elif tipo == "bairro":

        for coluna in colunas:

            nome = normalizar_texto(coluna)

            if "BAIRRO" in nome:
                return coluna

    elif tipo == "data":

        # ====================================================
        # REGRA ESTRUTURAL:
        #
        # A única coluna utilizada para definir data e
        # horário de abertura da O.S. é INÍCIO DO SLA.
        #
        # A coluna DATA não é utilizada.
        # ====================================================

        for coluna in colunas:

            nome = normalizar_texto(coluna)

            if (
                "INICIO" in nome
                and "SLA" in nome
            ):
                return coluna

    return None


# ============================================================
# VALORES ÚNICOS
# ============================================================

def obter_valores_unicos(df, coluna):

    if (
        df is None
        or coluna is None
        or coluna not in df.columns
    ):
        return []

    valores = []
    vistos = set()

    for valor in df[coluna].dropna():

        texto = str(valor).strip()

        if not texto:
            continue

        chave = normalizar_texto(texto)

        if chave in {
            "",
            "NAN",
            "NONE",
            "NULL",
        }:
            continue

        if chave not in vistos:

            vistos.add(chave)
            valores.append(texto)

    valores.sort(
        key=normalizar_texto
    )

    return valores


# ============================================================
# PROTOCOLO
# ============================================================

def parse_protocolo(proto):

    if pd.isna(proto):
        return "", "", None

    texto = str(proto).strip()

    resultado = re.search(
        r"(\d+)\s*/\s*(\d{4})",
        texto,
    )

    if not resultado:
        return "", "", None

    numero = resultado.group(1)
    ano = resultado.group(2)

    try:
        numero_int = int(numero)
    except Exception:
        numero_int = None

    return numero, ano, numero_int


# ============================================================
# HORA
# ============================================================

def converter_hora(valor):

    texto = str(valor).strip()

    if not re.fullmatch(
        r"\d{1,2}:\d{2}",
        texto,
    ):
        raise ValueError(
            f"Horário inválido: '{valor}'. Use HH:MM."
        )

    hora, minuto = texto.split(":")

    hora = int(hora)
    minuto = int(minuto)

    if (
        hora < 0
        or hora > 23
        or minuto < 0
        or minuto > 59
    ):
        raise ValueError(
            f"Horário inválido: '{valor}'. Use HH:MM."
        )

    return time(
        hour=hora,
        minute=minuto,
    )


# ============================================================
# DATA ROBUSTA
# ============================================================

def converter_datas_robusto(serie):

    resultado = pd.Series(
        pd.NaT,
        index=serie.index,
        dtype="datetime64[ns]",
    )

    for indice, valor in serie.items():

        if pd.isna(valor):
            continue

        if isinstance(
            valor,
            pd.Timestamp,
        ):
            resultado.loc[indice] = valor
            continue

        if isinstance(
            valor,
            datetime,
        ):
            resultado.loc[indice] = pd.Timestamp(
                valor
            )
            continue

        if isinstance(
            valor,
            (int, float),
        ) and not isinstance(valor, bool):

            try:

                numero = float(valor)

                if 1 <= numero <= 100000:

                    resultado.loc[indice] = (
                        pd.Timestamp(
                            "1899-12-30"
                        )
                        + pd.to_timedelta(
                            numero,
                            unit="D",
                        )
                    )

                    continue

            except Exception:
                pass

        texto = str(valor).strip()

        if not texto:
            continue

        formatos = [
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]

        convertido = None

        for formato in formatos:

            try:

                convertido = pd.to_datetime(
                    texto,
                    format=formato,
                )

                break

            except Exception:
                continue

        if convertido is None:

            try:

                convertido = pd.to_datetime(
                    texto,
                    dayfirst=True,
                    errors="coerce",
                )

            except Exception:

                convertido = pd.NaT

        resultado.loc[indice] = convertido

    return resultado


# ============================================================
# CONVERSÃO DE MINUTOS
# ============================================================

def hora_para_minutos(valor_hora):

    if valor_hora is None:
        return None

    return (
        valor_hora.hour * 60
        + valor_hora.minute
    )


# ============================================================
# FILTRO DE HORÁRIO COM MARGEM OPERACIONAL
# ============================================================

def aplicar_filtro_horario(
    resultado,
    datas,
    hora_inicial=None,
    hora_final=None,
):
    """
    Aplica o filtro de horário utilizando exclusivamente o
    horário existente em INÍCIO DO SLA.

    Margens operacionais:

    - 1 hora antes do horário inicial;
    - 3 horas depois do horário final.

    Exemplos:

    09:00 -> 15:00
    08:00 -> 18:00

    22:00 -> 02:00
    21:00 -> 05:00

    00:30 -> 01:30
    23:30 -> 04:30

    Os limites são inclusivos.
    """

    if (
        hora_inicial is None
        and hora_final is None
    ):
        return resultado

    if datas.empty:
        return resultado

    # ========================================================
    # HORA DOS REGISTROS
    # ========================================================

    horas = (
        datas.dt.hour * 60
        + datas.dt.minute
    )

    horas = horas.astype("Float64")

    # ========================================================
    # SOMENTE HORA INICIAL
    # ========================================================

    if (
        hora_inicial is not None
        and hora_final is None
    ):

        inicio_minutos = hora_para_minutos(
            hora_inicial
        )

        inicio_efetivo = (
            inicio_minutos - 60
        ) % 1440

        # Como não existe limite superior,
        # mantém-se a semântica "a partir de".
        #
        # A margem de 1 hora é aplicada ao início.
        mascara = (
            horas.notna()
            & (
                horas >= inicio_efetivo
            )
        )

        return resultado.loc[
            mascara
        ]

    # ========================================================
    # SOMENTE HORA FINAL
    # ========================================================

    if (
        hora_inicial is None
        and hora_final is not None
    ):

        fim_minutos = hora_para_minutos(
            hora_final
        )

        fim_efetivo = (
            fim_minutos + 180
        )

        # Se a margem ultrapassar 23:59,
        # não existe limite superior dentro
        # do mesmo dia.
        if fim_efetivo >= 1440:

            mascara = horas.notna()

        else:

            mascara = (
                horas.notna()
                & (
                    horas <= fim_efetivo
                )
            )

        return resultado.loc[
            mascara
        ]

    # ========================================================
    # INÍCIO E FIM INFORMADOS
    # ========================================================

    inicio_minutos = hora_para_minutos(
        hora_inicial
    )

    fim_minutos = hora_para_minutos(
        hora_final
    )

    # ========================================================
    # INTERVALO ORIGINAL COMO INTERVALO CIRCULAR
    #
    # Exemplo normal:
    #
    # 09:00 -> 15:00
    # duração = 360 minutos
    #
    # Exemplo atravessando meia-noite:
    #
    # 22:00 -> 02:00
    # duração = 240 minutos
    # ========================================================

    duracao_original = (
        fim_minutos - inicio_minutos
    ) % 1440

    # ========================================================
    # APLICA AS MARGENS
    #
    # -60 minutos no início
    # +180 minutos no fim
    #
    # Total adicional = 240 minutos.
    # ========================================================

    duracao_efetiva = (
        duracao_original + 240
    )

    inicio_efetivo = (
        inicio_minutos - 60
    ) % 1440

    fim_efetivo = (
        fim_minutos + 180
    ) % 1440

    # ========================================================
    # SE A JANELA EFETIVA COBRIR 24 HORAS OU MAIS,
    # TODOS OS HORÁRIOS SÃO VÁLIDOS.
    # ========================================================

    if duracao_efetiva >= 1440:

        mascara = horas.notna()

        return resultado.loc[
            mascara
        ]

    # ========================================================
    # INTERVALO SEM CRUZAMENTO
    #
    # Exemplo:
    #
    # 09:00 -> 15:00
    # 08:00 -> 18:00
    # ========================================================

    if inicio_efetivo <= fim_efetivo:

        mascara = (
            horas.notna()
            & (
                horas >= inicio_efetivo
            )
            & (
                horas <= fim_efetivo
            )
        )

    # ========================================================
    # INTERVALO CRUZANDO MEIA-NOITE
    #
    # Exemplo:
    #
    # 22:00 -> 02:00
    # 21:00 -> 05:00
    #
    # Aceita:
    #
    # 21:00 ... 23:59
    # OU
    # 00:00 ... 05:00
    # ========================================================

    else:

        mascara = (
            horas.notna()
            & (
                (horas >= inicio_efetivo)
                | (
                    horas <= fim_efetivo
                )
            )
        )

    return resultado.loc[
        mascara
    ]


# ============================================================
# FILTROS
# ============================================================

def aplicar_filtros(
    df,
    coluna_cidade=None,
    cidades=None,
    coluna_bairro=None,
    bairros=None,
    coluna_data=None,
    anos=None,
    meses=None,
    dias=None,
    hora_inicial=None,
    hora_final=None,
    observacao="",
):

    if df is None or df.empty:
        return pd.DataFrame(
            columns=(
                df.columns
                if df is not None
                else []
            )
        )

    resultado = df.copy()

    # ========================================================
    # CIDADE
    # ========================================================

    if coluna_cidade and cidades:

        cidades_normalizadas = {
            normalizar_texto(valor)
            for valor in cidades
        }

        resultado = resultado[
            resultado[coluna_cidade]
            .map(normalizar_texto)
            .isin(cidades_normalizadas)
        ]

    # ========================================================
    # BAIRRO
    #
    # CORRESPONDÊNCIA EXATA NORMALIZADA.
    #
    # "Parque Sul" entra.
    #
    # "PARQUE SUL" entra.
    #
    # "Parque  Sul" entra.
    #
    # "Parque Piauí" NÃO entra.
    #
    # "Polo Empresarial Sul" NÃO entra.
    #
    # Não é utilizada busca parcial.
    # ========================================================

    if coluna_bairro and bairros:

        bairros_normalizados = {
            normalizar_texto(valor)
            for valor in bairros
        }

        resultado = resultado[
            resultado[coluna_bairro]
            .map(normalizar_texto)
            .isin(bairros_normalizados)
        ]

    # ========================================================
    # DATA / HORÁRIO
    #
    # REGRA:
    #
    # EXCLUSIVAMENTE INÍCIO DO SLA.
    #
    # A coluna DATA não é utilizada.
    # ========================================================

    if coluna_data:

        precisa_data = (
            bool(anos)
            or bool(meses)
            or bool(dias)
            or hora_inicial is not None
            or hora_final is not None
        )

        if precisa_data:

            datas = converter_datas_robusto(
                resultado[coluna_data]
            )

            # =================================================
            # ANO
            # =================================================

            if anos:

                mascara = datas.dt.year.isin(
                    anos
                )

                resultado = resultado.loc[
                    mascara
                ]

                datas = datas.loc[
                    resultado.index
                ]

            # =================================================
            # MÊS
            # =================================================

            if meses:

                mascara = datas.dt.month.isin(
                    meses
                )

                resultado = resultado.loc[
                    mascara
                ]

                datas = datas.loc[
                    resultado.index
                ]

            # =================================================
            # DIA
            # =================================================

            if dias:

                mascara = datas.dt.day.isin(
                    dias
                )

                resultado = resultado.loc[
                    mascara
                ]

                datas = datas.loc[
                    resultado.index
                ]

            # =================================================
            # HORÁRIO
            # =================================================

            if (
                hora_inicial is not None
                or hora_final is not None
            ):

                resultado = aplicar_filtro_horario(
                    resultado,
                    datas,
                    hora_inicial,
                    hora_final,
                )

    # ========================================================
    # PESQUISA GERAL
    # ========================================================

    if observacao and observacao.strip():

        termo = normalizar_texto(
            observacao
        )

        mascara = resultado.apply(
            lambda linha:
                linha.astype(str)
                .map(normalizar_texto)
                .str.contains(
                    termo,
                    regex=False,
                    na=False,
                )
                .any(),
            axis=1,
        )

        resultado = resultado.loc[
            mascara
        ]

    return resultado.reset_index(
        drop=True
    )


# ============================================================
# GERAÇÃO DO LOTE
# ============================================================

def gerar_lote_cancelamento(
    df_filtrado,
    modo,
):

    if (
        df_filtrado is None
        or df_filtrado.empty
    ):
        return (
            pd.DataFrame(),
            pd.DataFrame(),
        )

    coluna_protocolo = localizar_coluna(
        df_filtrado,
        "protocolo",
    )

    coluna_matricula = localizar_coluna(
        df_filtrado,
        "matricula",
    )

    coluna_cidade = localizar_coluna(
        df_filtrado,
        "cidade",
    )

    if coluna_protocolo is None:
        raise ValueError(
            "A coluna 'COD. PROTOCOLO ORIGEM' não foi localizada."
        )

    if coluna_matricula is None:
        raise ValueError(
            "A coluna 'MATRICULA' não foi localizada."
        )

    if (
        modo == "API"
        and coluna_cidade is None
    ):
        raise ValueError(
            "A coluna 'CIDADE' não foi localizada."
        )

    registros = []
    logs = []

    for _, linha in df_filtrado.iterrows():

        matricula = linha.get(
            coluna_matricula,
            "",
        )

        protocolo_original = linha.get(
            coluna_protocolo,
            "",
        )

        cidade = (
            linha.get(
                coluna_cidade,
                "",
            )
            if coluna_cidade
            else ""
        )

        numero, ano, numero_int = (
            parse_protocolo(
                protocolo_original
            )
        )

        if numero_int is None:

            logs.append(
                {
                    "Tipo": modo,
                    "Matrícula": matricula,
                    "Protocolo": protocolo_original,
                    "Cidade": cidade,
                    "Motivo": (
                        "Protocolo inválido "
                        "ou não localizado."
                    ),
                }
            )

            continue

        if modo == "API":

            zona = obter_zona(cidade)

            if zona is None:

                logs.append(
                    {
                        "Tipo": modo,
                        "Matrícula": matricula,
                        "Protocolo": protocolo_original,
                        "Cidade": cidade,
                        "Motivo": (
                            "Cidade sem zona definida."
                        ),
                    }
                )

                continue

        else:

            zona = 1

        registros.append(
            {
                "Matricula": matricula,
                "Zona Ligacao": zona,
                "Numero Do Pedido": numero_int,
                "Ano Do Pedido": ano,
                "Tipo Encerramento": 6,
                "Observações": "",
            }
        )

    lote = pd.DataFrame(
        registros,
        columns=[
            "Matricula",
            "Zona Ligacao",
            "Numero Do Pedido",
            "Ano Do Pedido",
            "Tipo Encerramento",
            "Observações",
        ],
    )

    log = pd.DataFrame(
        logs,
        columns=[
            "Tipo",
            "Matrícula",
            "Protocolo",
            "Cidade",
            "Motivo",
        ],
    )

    return lote, log


# ============================================================
# RENDERIZAÇÃO
# ============================================================

def render_filtragem():

    st.title(
        "🔎 Filtragem / Cancelamento"
    )

    st.caption(
        "Filtre a base carregada no Hub e gere o lote de cancelamento."
    )

    if st.button(
        "⬅️ Voltar ao Hub do Gerador de Lotes",
        key="btn_voltar_hub_filtragem",
    ):

        st.session_state.ferramenta_atual = None

        limpar_resultado()

        st.rerun()

    st.divider()

    # ========================================================
    # SELEÇÃO API / THE
    # ========================================================

    modo, df_base = selecionar_modo_api_the(
        key="filtragem_modo_api_the",
        titulo="Base de operação",
        limpar_resultado_callback=limpar_resultado,
    )

    if modo is None or df_base is None:
        return

    # ========================================================
    # LOCALIZAÇÃO DAS COLUNAS
    # ========================================================

    coluna_cidade = localizar_coluna(
        df_base,
        "cidade",
    )

    coluna_bairro = localizar_coluna(
        df_base,
        "bairro",
    )

    coluna_data = localizar_coluna(
        df_base,
        "data",
    )

    coluna_matricula = localizar_coluna(
        df_base,
        "matricula",
    )

    coluna_protocolo = localizar_coluna(
        df_base,
        "protocolo",
    )

    # ========================================================
    # INFORMAÇÕES
    # ========================================================

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "Registros",
            f"{len(df_base):,}".replace(
                ",",
                ".",
            ),
        )

    with col2:

        st.metric(
            "Colunas",
            len(df_base.columns),
        )

    with col3:

        st.metric(
            "Matrícula",
            "OK"
            if coluna_matricula
            else "Não encontrada",
        )

    with col4:

        st.metric(
            "Protocolo",
            "OK"
            if coluna_protocolo
            else "Não encontrado",
        )

    st.divider()

    # ========================================================
    # FILTROS
    # ========================================================

    st.subheader("🎯 Filtros")

    col1, col2 = st.columns(2)

    with col1:

        cidades = []

        if coluna_cidade:

            cidades = st.multiselect(
                "Cidade",
                obter_valores_unicos(
                    df_base,
                    coluna_cidade,
                ),
                key="filtragem_cidades",
            )

        else:

            st.info(
                "Coluna CIDADE não encontrada."
            )

    with col2:

        bairros = []

        if coluna_bairro:

            bairros = st.multiselect(
                "Bairro",
                obter_valores_unicos(
                    df_base,
                    coluna_bairro,
                ),
                key="filtragem_bairros",
            )

        else:

            st.info(
                "Coluna BAIRRO não encontrada."
            )

    # ========================================================
    # DATA
    # ========================================================

    anos = []
    meses = []
    dias = []

    if coluna_data:

        datas = converter_datas_robusto(
            df_base[coluna_data]
        )

        anos_disponiveis = sorted(
            datas.dt.year.dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        meses_disponiveis = sorted(
            datas.dt.month.dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        dias_disponiveis = sorted(
            datas.dt.day.dropna()
            .astype(int)
            .unique()
            .tolist()
        )

        col3, col4, col5 = st.columns(3)

        with col3:

            anos = st.multiselect(
                "Ano",
                anos_disponiveis,
                key="filtragem_anos",
            )

        with col4:

            meses = st.multiselect(
                "Mês",
                meses_disponiveis,
                key="filtragem_meses",
            )

        with col5:

            dias = st.multiselect(
                "Dia",
                dias_disponiveis,
                key="filtragem_dias",
            )

    else:

        st.error(
            "A coluna 'INÍCIO DO SLA' não foi encontrada na base."
        )

    # ========================================================
    # HORÁRIO
    # ========================================================

    st.markdown(
        "#### 🕐 Horário de abertura da O.S."
    )

    st.caption(
        "A referência do horário de abertura é exclusivamente "
        "**INÍCIO DO SLA**. O filtro considera automaticamente "
        "**1 hora antes do início** e **3 horas após o fim**."
    )

    col6, col7 = st.columns(2)

    with col6:

        hora_inicial_texto = st.text_input(
            "Hora Inicial",
            placeholder="HH:MM",
            key="filtragem_hora_inicial",
        )

    with col7:

        hora_final_texto = st.text_input(
            "Hora Final",
            placeholder="HH:MM",
            key="filtragem_hora_final",
        )

    hora_inicial = None
    hora_final = None
    erro_horario = False

    if hora_inicial_texto.strip():

        try:

            hora_inicial = converter_hora(
                hora_inicial_texto
            )

        except ValueError as erro:

            st.error(str(erro))

            erro_horario = True

    if hora_final_texto.strip():

        try:

            hora_final = converter_hora(
                hora_final_texto
            )

        except ValueError as erro:

            st.error(str(erro))

            erro_horario = True

    # ========================================================
    # MOSTRA A JANELA EFETIVA
    # ========================================================

    if (
        hora_inicial is not None
        and hora_final is not None
    ):

        inicio_minutos = hora_para_minutos(
            hora_inicial
        )

        fim_minutos = hora_para_minutos(
            hora_final
        )

        inicio_efetivo = (
            inicio_minutos - 60
        ) % 1440

        fim_efetivo = (
            fim_minutos + 180
        ) % 1440

        st.info(
            f"⏱️ Janela efetiva do filtro: "
            f"**{inicio_efetivo // 60:02d}:{inicio_efetivo % 60:02d}** "
            f"até "
            f"**{fim_efetivo // 60:02d}:{fim_efetivo % 60:02d}** "
            f"(margem de -1h / +3h)."
        )

    elif hora_inicial is not None:

        inicio_minutos = hora_para_minutos(
            hora_inicial
        )

        inicio_efetivo = (
            inicio_minutos - 60
        ) % 1440

        st.info(
            f"⏱️ O.S. abertas a partir de "
            f"**{inicio_efetivo // 60:02d}:{inicio_efetivo % 60:02d}** "
            f"(1h antes do horário inicial)."
        )

    elif hora_final is not None:

        fim_minutos = hora_para_minutos(
            hora_final
        )

        fim_efetivo = (
            fim_minutos + 180
        ) % 1440

        st.info(
            f"⏱️ O.S. abertas até "
            f"**{fim_efetivo // 60:02d}:{fim_efetivo % 60:02d}** "
            f"(3h após o horário final)."
        )

    # ========================================================
    # PESQUISA
    # ========================================================

    observacao = st.text_input(
        "🔍 Pesquisa geral",
        placeholder=(
            "Digite um valor para pesquisar em qualquer coluna..."
        ),
        key="filtragem_pesquisa",
    )

    # ========================================================
    # BOTÕES
    # ========================================================

    col_btn1, col_btn2 = st.columns(2)

    with col_btn1:

        aplicar = st.button(
            "🔎 Aplicar Filtros",
            type="primary",
            use_container_width=True,
            key="filtragem_aplicar",
            disabled=erro_horario,
        )

    with col_btn2:

        limpar = st.button(
            "🧹 Limpar Filtros",
            use_container_width=True,
            key="filtragem_limpar",
        )

    if limpar:

        for chave in [
            "filtragem_cidades",
            "filtragem_bairros",
            "filtragem_anos",
            "filtragem_meses",
            "filtragem_dias",
            "filtragem_hora_inicial",
            "filtragem_hora_final",
            "filtragem_pesquisa",
        ]:

            st.session_state.pop(
                chave,
                None,
            )

        limpar_resultado()

        st.rerun()

    # ========================================================
    # APLICAÇÃO
    # ========================================================

    if aplicar:

        df_filtrado = aplicar_filtros(
            df=df_base,
            coluna_cidade=coluna_cidade,
            cidades=cidades,
            coluna_bairro=coluna_bairro,
            bairros=bairros,
            coluna_data=coluna_data,
            anos=anos,
            meses=meses,
            dias=dias,
            hora_inicial=hora_inicial,
            hora_final=hora_final,
            observacao=observacao,
        )

        st.session_state.df_resultado = (
            df_filtrado
        )

        st.session_state.df_resultado_lote = None
        st.session_state.df_log = None
        st.session_state.nome_arquivo_resultado = None

    # ========================================================
    # RESULTADO
    # ========================================================

    df_resultado = st.session_state.get(
        "df_resultado"
    )

    if df_resultado is None:
        return

    st.divider()

    st.subheader(
        "📋 Resultado da Filtragem"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "Registros encontrados",
            f"{len(df_resultado):,}".replace(
                ",",
                ".",
            ),
        )

    with col2:

        st.metric(
            "Colunas preservadas",
            len(df_resultado.columns),
        )

    if df_resultado.empty:

        st.warning(
            "Nenhum registro corresponde aos filtros selecionados."
        )

        return

    st.dataframe(
        df_resultado,
        use_container_width=True,
        height=420,
    )

    arquivo_previa = dataframe_para_excel(
        df_resultado,
        nome_aba="Filtragem",
    )

    if arquivo_previa:

        st.download_button(
            "⬇️ Baixar Prévia Filtrada",
            data=arquivo_previa,
            file_name=(
                f"Previa_Filtragem_{modo}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
            key="download_previa_filtragem",
        )

    # ========================================================
    # GERAÇÃO
    # ========================================================

    st.divider()

    st.subheader(
        "📦 Geração do Lote de Cancelamento"
    )

    if st.button(
        "📦 Gerar Lote de Cancelamento",
        type="primary",
        use_container_width=True,
        key="filtragem_gerar_lote",
    ):

        try:

            lote, log = gerar_lote_cancelamento(
                df_resultado,
                modo,
            )

            st.session_state.df_resultado_lote = lote
            st.session_state.df_log = log

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            st.session_state.nome_arquivo_resultado = (
                f"Lote_Cancelamento_{modo}_{timestamp}.xlsx"
            )

            st.rerun()

        except Exception as erro:

            st.error(
                f"Erro ao gerar o lote: {erro}"
            )

    # ========================================================
    # LOTE
    # ========================================================

    lote = st.session_state.get(
        "df_resultado_lote"
    )

    log = st.session_state.get(
        "df_log"
    )

    if lote is None:
        return

    st.divider()

    st.subheader("✅ Lote Gerado")

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Registros no lote",
            f"{len(lote):,}".replace(
                ",",
                ".",
            ),
        )

    with col2:

        st.metric(
            "Registros no LOG",
            f"{len(log) if log is not None else 0:,}".replace(
                ",",
                ".",
            ),
        )

    with col3:

        st.metric(
            "Modo",
            modo,
        )

    if not lote.empty:

        st.dataframe(
            lote,
            use_container_width=True,
            height=300,
        )

        arquivo_lote = dataframe_para_excel(
            lote,
            nome_aba="Lote",
        )

        if arquivo_lote:

            st.download_button(
                "⬇️ Baixar Lote de Cancelamento",
                data=arquivo_lote,
                file_name=st.session_state.get(
                    "nome_arquivo_resultado",
                    f"Lote_Cancelamento_{modo}.xlsx",
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                type="primary",
                use_container_width=True,
                key="download_lote_cancelamento",
            )

    else:

        st.warning(
            "Nenhum registro válido foi gerado para o lote."
        )

    # ========================================================
    # LOG
    # ========================================================

    st.subheader("📝 LOG")

    if log is None or log.empty:

        st.success(
            "Nenhuma inconsistência foi encontrada durante a geração."
        )

    else:

        st.warning(
            f"{len(log)} registro(s) não foram incluídos no lote."
        )

        st.dataframe(
            log,
            use_container_width=True,
            height=300,
        )

        arquivo_log = dataframe_para_excel(
            log,
            nome_aba="LOG",
        )

        if arquivo_log:

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            st.download_button(
                "⬇️ Baixar LOG",
                data=arquivo_log,
                file_name=(
                    f"LOG_Cancelamento_{modo}_{timestamp}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="download_log_cancelamento",
            )
