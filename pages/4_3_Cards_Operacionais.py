# ============================================================
# MÓDULO 4_3 — CARDS OPERACIONAIS
# PLATAFORMA COI
# Adaptado do Card Executivo V4.5 — Águas do Piauí
# ============================================================

import io
import re
import unicodedata
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from PIL import Image

from auth import verificar_autenticacao


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Cards Operacionais - COI",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# AUTENTICAÇÃO
# ============================================================

if not verificar_autenticacao():
    st.warning("Acesso restrito. Faça login para acessar o módulo.")

    if st.button("Ir para o Login"):
        st.switch_page("app.py")

    st.stop()


# ============================================================
# PALETA DE CORES
# ============================================================

C_PRIMARY = "#0027BC"
C_PRIMARY_LIGHT = "#F0F4FF"
C_INFO = "#F59E0B"
C_ALERT = "#D32F2F"
C_SUCCESS = "#059669"
C_TEXT = "#0F172A"
C_MUTED = "#64748B"
C_OBS_DARK = "#334155"
C_BORDER = "#CBD5E1"
C_BG = "#F4F7FB"
C_CARD = "#FFFFFF"


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans"]


# ============================================================
# ESTILO DA INTERFACE
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 30px;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 2px;
    }

    .main-subtitle {
        font-size: 14px;
        color: #64748B;
        margin-bottom: 20px;
    }

    .section-title {
        font-size: 15px;
        font-weight: 700;
        color: #0F172A;
        border-left: 4px solid #0027BC;
        padding-left: 10px;
        margin-top: 8px;
        margin-bottom: 12px;
    }

    .status-box {
        background: #F0F4FF;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 12px 14px;
        color: #334155;
        font-size: 13px;
    }

    .info-box {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 12px 14px;
        color: #475569;
        font-size: 13px;
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 10px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# FUNÇÕES DE TEXTO
# ============================================================

def remover_acentos(texto):
    if pd.isna(texto):
        return ""

    texto = str(texto)

    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    return "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )


def criar_chave_texto(valor):
    if pd.isna(valor):
        return ""

    texto = remover_acentos(valor).upper()

    texto = re.sub(
        r"[^A-Z0-9 ]",
        " ",
        texto
    )

    return re.sub(
        r"\s+",
        " ",
        texto
    ).strip()


def padronizar_nome_coluna(col):
    if pd.isna(col):
        return ""

    col_limpa = remover_acentos(
        str(col)
    ).lower()

    return re.sub(
        r"[^a-z0-9]",
        "",
        col_limpa
    )


def formatar_nome_cidade(nome):
    if pd.isna(nome):
        return "Não informado"

    palavras = str(nome).strip().split()

    minusculas = {
        "de",
        "do",
        "da",
        "dos",
        "das",
        "e"
    }

    resultado = []

    for idx, palavra in enumerate(palavras):

        if idx > 0 and palavra.lower() in minusculas:
            resultado.append(
                palavra.lower()
            )
        else:
            resultado.append(
                palavra.capitalize()
            )

    return " ".join(resultado)


def corrigir_nome_exibicao(nome):

    correcoes = {
        "Parnaiba": "Parnaíba",
        "Luis Correia": "Luís Correia",
        "Cajueiro da Praia": "Cajueiro da Praia",
        "Piracuruca": "Piracuruca",
        "Sao Raimundo Nonato": "São Raimundo Nonato",
        "Sao Joao do Piaui": "São João do Piauí",
        "Santo Inacio do Piaui": "Santo Inácio do Piauí",
        "Conceicao do Caninde": "Conceição do Canindé",
        "Anisio de Abreu": "Anísio de Abreu",
        "Dom Inocencio": "Dom Inocêncio",
        "Simplicio Mendes": "Simplício Mendes",
        "Bonfim do Piaui": "Bonfim do Piauí",
        "Sao Lourenco": "São Lourenço",
        "Sao Francisco de Assis": "São Francisco de Assis"
    }

    return correcoes.get(
        nome,
        nome
    )


# ============================================================
# CLASSIFICAÇÃO DOS REGISTROS
# ============================================================

def classificar_tipo_registro(
    servico,
    codigo=None
):

    if pd.notna(codigo):

        cod_str = str(codigo).strip()

        if "146003" in cod_str:
            return "RECLAMACAO"

        elif "146005" in cod_str:
            return "INFORMACAO"

    texto = criar_chave_texto(servico)

    if (
        "146003" in texto
        or "RECLAMACAO DE FALTA DE AGUA" in texto
    ):
        return "RECLAMACAO"

    if (
        "146005" in texto
        or "INFORMACAO DE FALTA DE AGUA" in texto
    ):
        return "INFORMACAO"

    return "OUTRO"


# ============================================================
# COLUNA ÚNICA
# ============================================================

def obter_coluna_unica(
    df_target,
    nome_col
):

    if nome_col not in df_target.columns:

        return pd.Series(
            [None] * len(df_target),
            index=df_target.index
        )

    val = df_target[nome_col]

    if isinstance(val, pd.DataFrame):
        return val.iloc[:, 0]

    return val


# ============================================================
# AGRUPAMENTO
# ============================================================

def obter_campo_agrupamento(escopo):

    escopo = str(
        escopo
    ).upper()

    if escopo == "TERESINA":

        return (
            "bairro_fmt",
            "bairro_key",
            "BAIRROS",
            "BAIRRO"
        )

    return (
        "cidade_fmt",
        "cidade_key",
        "MUNICÍPIOS",
        "MUNICÍPIO"
    )


# ============================================================
# DETECÇÃO DE CABEÇALHO
# ============================================================

def ajustar_cabecalho_dataframe(df):

    if df.empty:
        return df

    termos_chave = [
        "dataemissao",
        "dtemissao",
        "data",
        "emissao",
        "ndaos",
        "numos",
        "numeroos",
        "os",
        "servicosolicitado",
        "servicoexecutado",
        "servico",
        "solicitacao",
        "cidade",
        "municipio",
        "bairro",
        "localidade",
        "inicio",
        "termino",
        "codigoservico",
        "codigo"
    ]

    cols_atuais = [
        padronizar_nome_coluna(c)
        for c in df.columns
    ]

    match_header = sum(
        1
        for c in cols_atuais
        if any(
            t == c or t in c
            for t in termos_chave
        )
    )

    if match_header >= 2:
        return df

    for idx in range(
        min(25, len(df))
    ):

        linha_vals = [
            padronizar_nome_coluna(val)
            for val in df.iloc[idx].values
            if pd.notna(val)
        ]

        match_count = sum(
            1
            for v in linha_vals
            if any(
                t == v or t in v
                for t in termos_chave
            )
        )

        if match_count >= 2:

            novos_cabecalhos = [
                str(c).strip()
                if pd.notna(c)
                else f"Col_{i}"
                for i, c
                in enumerate(df.iloc[idx])
            ]

            df.columns = novos_cabecalhos

            df = df.iloc[
                idx + 1:
            ].reset_index(drop=True)

            return df

    return df


# ============================================================
# PREPARAÇÃO DA BASE DE O.S.
# ============================================================

def preparar_dataframe_os(df):

    df = df.loc[
        :,
        ~df.columns.duplicated()
    ].copy()

    df = ajustar_cabecalho_dataframe(
        df
    )

    cols_unidas = " ".join(
        [
            str(c)
            for c in df.columns
        ]
    ).lower()

    if (
        "contagem de" in cols_unidas
        or "rotulos de coluna" in cols_unidas
    ):
        raise ValueError(
            "O arquivo anexado é uma Tabela Dinâmica. "
            "Envie a base bruta de O.S."
        )

    mapa_colunas = {

        "Data Emissão": [
            "dtemissao",
            "dataemissao",
            "data",
            "emissao",
            "dtabertura",
            "dataabertura"
        ],

        "Nº da O.S": [
            "ndaos",
            "numos",
            "numeroos",
            "os",
            "nos",
            "numero",
            "ordemdeservico"
        ],

        "Serviço Solicitado": [
            "servicoexecutado",
            "servicosolicitado",
            "servico",
            "descricaoservico",
            "solicitacao",
            "tiposervico",
            "descricao"
        ],

        "Código Serviço": [
            "codigoservico",
            "codservico",
            "codigo",
            "cdservico"
        ],

        "Cidade": [
            "cidade",
            "municipio",
            "localidade",
            "cidadenome"
        ],

        "Bairro": [
            "bairro",
            "bairronome",
            "subdistrito"
        ]
    }

    colunas_renomeadas = {}
    colunas_usadas = set()

    for col_orig in df.columns:

        col_clean = padronizar_nome_coluna(
            col_orig
        )

        for (
            col_oficial,
            sinonimos
        ) in mapa_colunas.items():

            if col_oficial in colunas_usadas:
                continue

            if (
                col_clean in sinonimos
                or
                col_clean ==
                padronizar_nome_coluna(
                    col_oficial
                )
            ):

                colunas_renomeadas[
                    col_orig
                ] = col_oficial

                colunas_usadas.add(
                    col_oficial
                )

                break

    df = df.rename(
        columns=colunas_renomeadas
    )

    obrigatorias = [
        "Data Emissão",
        "Nº da O.S",
        "Serviço Solicitado",
        "Cidade",
        "Bairro"
    ]

    faltantes = [
        c
        for c in obrigatorias
        if c not in df.columns
    ]

    if faltantes:

        raise ValueError(
            "Colunas obrigatórias ausentes "
            "na planilha de O.S.: "
            + ", ".join(faltantes)
        )

    df = df.dropna(
        subset=["Nº da O.S"]
    ).copy()

    col_dt_emissao = obter_coluna_unica(
        df,
        "Data Emissão"
    )

    df["data_emissao"] = pd.to_datetime(
        col_dt_emissao,
        dayfirst=True,
        errors="coerce"
    )

    col_cod = (
        df["Código Serviço"]
        if "Código Serviço" in df.columns
        else None
    )

    col_serv_sol = obter_coluna_unica(
        df,
        "Serviço Solicitado"
    )

    df["tipo_registro"] = [
        classificar_tipo_registro(
            serv,
            col_cod.iloc[idx]
            if col_cod is not None
            else None
        )
        for idx, serv
        in enumerate(col_serv_sol)
    ]

    col_cid = obter_coluna_unica(
        df,
        "Cidade"
    )

    col_bairro = obter_coluna_unica(
        df,
        "Bairro"
    )

    df["cidade_fmt"] = (
        col_cid
        .apply(formatar_nome_cidade)
        .apply(corrigir_nome_exibicao)
    )

    df["cidade_key"] = (
        col_cid
        .apply(criar_chave_texto)
    )

    df["bairro_fmt"] = (
        col_bairro
        .fillna("Não informado")
        .astype(str)
        .str.strip()
        .str.title()
    )

    df["bairro_key"] = (
        col_bairro
        .apply(criar_chave_texto)
    )

    return df


# ============================================================
# PERÍODO
# ============================================================

def detectar_periodo_e_data_ref(
    df_os,
    modo_selecionado="AUTO",
    data_manual=""
):

    if (
        df_os.empty
        or "data_emissao" not in df_os.columns
    ):
        return (
            "DIARIO",
            datetime.now().strftime("%d/%m/%Y")
        )

    datas_validas = (
        df_os["data_emissao"]
        .dropna()
    )

    if datas_validas.empty:

        return (
            "DIARIO",
            datetime.now().strftime("%d/%m/%Y")
        )

    maior_data = datas_validas.max()
    menor_data = datas_validas.min()

    if data_manual and str(
        data_manual
    ).strip():

        dt_valida = pd.to_datetime(
            data_manual,
            dayfirst=True,
            errors="coerce"
        )

        if pd.notna(dt_valida):
            data_ref_str = dt_valida.strftime(
                "%d/%m/%Y"
            )
        else:
            data_ref_str = maior_data.strftime(
                "%d/%m/%Y"
            )

    else:

        data_ref_str = maior_data.strftime(
            "%d/%m/%Y"
        )

    if modo_selecionado != "AUTO":

        return (
            modo_selecionado,
            data_ref_str
        )

    diferenca_dias = (
        maior_data.date()
        -
        menor_data.date()
    ).days + 1

    if diferenca_dias <= 1:

        return (
            "DIARIO",
            data_ref_str
        )

    elif diferenca_dias <= 7:

        return (
            "SEMANAL",
            data_ref_str
        )

    return (
        "MENSAL",
        data_ref_str
    )


def filtrar_periodo(
    df,
    modo,
    data_referencia
):

    if df.empty:
        return df.copy()

    data_ref = pd.to_datetime(
        data_referencia,
        dayfirst=True,
        errors="coerce"
    )

    if pd.isna(data_ref):
        raise ValueError(
            "Data de referência inválida."
        )

    data_ref = data_ref.normalize()

    modo = str(modo).upper()

    if modo == "DIARIO":

        inicio = data_ref

        fim = (
            data_ref
            + timedelta(days=1)
        )

    elif modo == "SEMANAL":

        inicio = (
            data_ref
            - timedelta(days=6)
        )

        fim = (
            data_ref
            + timedelta(days=1)
        )

    elif modo == "MENSAL":

        inicio = data_ref.replace(
            day=1
        )

        if data_ref.month == 12:

            fim = data_ref.replace(
                year=data_ref.year + 1,
                month=1,
                day=1
            )

        else:

            fim = data_ref.replace(
                month=data_ref.month + 1,
                day=1
            )

    else:

        raise ValueError(
            "Modo de período inválido."
        )

    return df[
        (df["data_emissao"] >= inicio)
        &
        (df["data_emissao"] < fim)
    ].copy()


# ============================================================
# FORMATAÇÃO DO CABEÇALHO
# ============================================================

def formatar_periodo_cabecalho(
    data_ref_str,
    modo
):

    data_ref = pd.to_datetime(
        data_ref_str,
        dayfirst=True,
        errors="coerce"
    )

    if pd.isna(data_ref):
        return data_ref_str

    modo = str(modo).upper()

    if modo == "DIARIO":

        return data_ref.strftime(
            "%d/%m/%Y"
        )

    elif modo == "SEMANAL":

        inicio = (
            data_ref
            - timedelta(days=6)
        )

        return (
            f"{inicio.strftime('%d/%m/%Y')} "
            f"a {data_ref.strftime('%d/%m/%Y')}"
        )

    elif modo == "MENSAL":

        meses = {
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

        return (
            f"{meses[data_ref.month]}/"
            f"{data_ref.year}"
        )

    return data_ref_str


# ============================================================
# KPIs
# ============================================================

def calcular_kpis_principais(
    df_periodo,
    escopo="PIAUI"
):

    base = df_periodo[
        df_periodo["tipo_registro"].isin(
            [
                "RECLAMACAO",
                "INFORMACAO"
            ]
        )
    ]

    _, col_key, _, _ = obter_campo_agrupamento(
        escopo
    )

    return {

        "total_registros": len(base),

        "total_reclamacoes": len(
            base[
                base["tipo_registro"]
                == "RECLAMACAO"
            ]
        ),

        "total_informacoes": len(
            base[
                base["tipo_registro"]
                == "INFORMACAO"
            ]
        ),

        "municipios_afetados": base[
            col_key
        ].nunique()
    }


# ============================================================
# TOP 5
# ============================================================

def calcular_top5_municipios(
    df_periodo,
    escopo="PIAUI"
):

    base = df_periodo[
        df_periodo["tipo_registro"].isin(
            [
                "RECLAMACAO",
                "INFORMACAO"
            ]
        )
    ]

    col_fmt, _, _, _ = obter_campo_agrupamento(
        escopo
    )

    if base.empty:

        return pd.DataFrame(
            columns=[
                col_fmt,
                "RECLAMACAO",
                "INFORMACAO",
                "TOTAL",
                "PERCENTUAL"
            ]
        )

    total_periodo = len(base)

    agrupado = (
        base
        .groupby(
            [
                col_fmt,
                "tipo_registro"
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    if "RECLAMACAO" not in agrupado.columns:
        agrupado["RECLAMACAO"] = 0

    if "INFORMACAO" not in agrupado.columns:
        agrupado["INFORMACAO"] = 0

    agrupado["TOTAL"] = (
        agrupado["RECLAMACAO"]
        +
        agrupado["INFORMACAO"]
    )

    agrupado["PERCENTUAL"] = (
        agrupado["TOTAL"]
        /
        total_periodo
        *
        100
    ).round(1)

    agrupado = (
        agrupado
        .sort_values(
            by="TOTAL",
            ascending=False
        )
        .reset_index()
    )

    if escopo == "PIAUI":

        agrupado[col_fmt] = (
            agrupado[col_fmt]
            .apply(corrigir_nome_exibicao)
        )

    return agrupado.head(5)


# ============================================================
# LÍDER
# ============================================================

def calcular_municipio_lider(
    df_periodo,
    escopo="PIAUI"
):

    base = df_periodo[
        df_periodo["tipo_registro"].isin(
            [
                "RECLAMACAO",
                "INFORMACAO"
            ]
        )
    ]

    col_fmt, _, _, tipo_rotulo = obter_campo_agrupamento(
        escopo
    )

    if base.empty:

        return {
            "municipio": "Sem dados",
            "total_registros": 0,
            "lider_tipo": tipo_rotulo
        }

    ranking = (
        base[col_fmt]
        .value_counts()
    )

    nome_lider = ranking.index[0]

    if escopo == "PIAUI":

        nome_lider = corrigir_nome_exibicao(
            nome_lider
        )

    return {

        "municipio": nome_lider,

        "total_registros": int(
            ranking.iloc[0]
        ),

        "lider_tipo": tipo_rotulo
    }


# ============================================================
# ÁREAS CRÍTICAS
# ============================================================

def calcular_kpi_areas_criticas(
    df_periodo,
    escopo="PIAUI"
):

    base_rec = df_periodo[
        df_periodo["tipo_registro"]
        == "RECLAMACAO"
    ]

    col_fmt, _, _, _ = obter_campo_agrupamento(
        escopo
    )

    rotulo = (
        "Bairros"
        if escopo == "TERESINA"
        else "Municípios"
    )

    if base_rec.empty:

        return {
            "qtd_criticas": 0,
            "rotulo_entidade": rotulo
        }

    rec_por_agrupamento = (
        base_rec
        .groupby(col_fmt)
        .size()
    )

    qtd_criticas = int(
        (
            rec_por_agrupamento > 5
        ).sum()
    )

    return {
        "qtd_criticas": qtd_criticas,
        "rotulo_entidade": rotulo
    }


# ============================================================
# ÁREAS EM ATENÇÃO
# ============================================================

def calcular_municipios_atencao(
    df_periodo,
    limite=5,
    escopo="PIAUI"
):

    col_fmt, _, _, _ = obter_campo_agrupamento(
        escopo
    )

    base = df_periodo[
        df_periodo["tipo_registro"].isin(
            [
                "RECLAMACAO",
                "INFORMACAO"
            ]
        )
    ]

    if base.empty:
        return []

    agrupado = (
        base
        .groupby(
            [
                col_fmt,
                "tipo_registro"
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    if "RECLAMACAO" not in agrupado.columns:
        agrupado["RECLAMACAO"] = 0

    if "INFORMACAO" not in agrupado.columns:
        agrupado["INFORMACAO"] = 0

    agrupado["TOTAL"] = (
        agrupado["RECLAMACAO"]
        +
        agrupado["INFORMACAO"]
    )

    agrupado = (
        agrupado
        .sort_values(
            by="TOTAL",
            ascending=False
        )
        .reset_index()
    )

    resultado = []

    for _, row in agrupado.head(limite).iterrows():

        nome_item = row[col_fmt]

        if escopo == "PIAUI":
            nome_item = corrigir_nome_exibicao(
                nome_item
            )

        resultado.append({

            "municipio": nome_item,

            "registros": int(
                row["TOTAL"]
            ),

            "rec_oficial": int(
                row["RECLAMACAO"]
            ),

            "inf_oficial": int(
                row["INFORMACAO"]
            )
        })

    return resultado


# ============================================================
# DADOS DO DASHBOARD
# ============================================================

def construir_dashboard_data(
    df_periodo,
    escopo="PIAUI",
    eventos_manuais=None
):

    if (
        str(escopo).upper()
        == "TERESINA"
    ):

        df_periodo = df_periodo[
            df_periodo["cidade_key"]
            == "TERESINA"
        ].copy()

    kpis = calcular_kpis_principais(
        df_periodo,
        escopo=escopo
    )

    top5 = calcular_top5_municipios(
        df_periodo,
        escopo=escopo
    )

    total_registros = (
        kpis["total_registros"]
    )

    concentracao = (

        (
            top5["TOTAL"].sum()
            /
            total_registros
            *
            100
        )

        if total_registros > 0

        else 0.0
    )

    return {

        "kpis": kpis,

        "top5": top5,

        "lider": calcular_municipio_lider(
            df_periodo,
            escopo=escopo
        ),

        "areas_criticas":
            calcular_kpi_areas_criticas(
                df_periodo,
                escopo=escopo
            ),

        "concentracao_top5":
            round(concentracao, 1),

        "municipios_atencao":
            calcular_municipios_atencao(
                df_periodo,
                escopo=escopo
            ),

        "escopo": escopo,

        "eventos_manuais":
            eventos_manuais or []
    }


# ============================================================
# RENDERIZAÇÃO DO CARD
# ============================================================

def renderizar_card_executivo(
    dashboard_data,
    data_ref,
    modo,
    regional,
    logo_img=None
):

    escopo = dashboard_data.get(
        "escopo",
        "PIAUI"
    )

    col_fmt, _, plural_rotulo, singular_rotulo = (
        obter_campo_agrupamento(
            escopo
        )
    )

    fig = plt.figure(
        figsize=(16, 9),
        facecolor=C_BG
    )

    gs = fig.add_gridspec(
        5,
        7,
        height_ratios=[
            0.8,
            1.2,
            2.5,
            2.5,
            0.3
        ],
        wspace=0.18,
        hspace=0.3,
        left=0.03,
        right=0.97,
        top=0.95,
        bottom=0.02
    )

    # ========================================================
    # CABEÇALHO
    # ========================================================

    patch_header = FancyBboxPatch(
        (
            0.03,
            0.88
        ),
        0.94,
        0.075,
        boxstyle=(
            "round,pad=0.0,"
            "rounding_size=0.02"
        ),
        facecolor=C_PRIMARY,
        edgecolor="none",
        zorder=1,
        transform=fig.transFigure
    )

    fig.patches.append(
        patch_header
    )

    ax_header = fig.add_axes(
        [
            0.04,
            0.88,
            0.92,
            0.075
        ],
        facecolor="none",
        zorder=2
    )

    ax_header.axis("off")

    periodo_texto = formatar_periodo_cabecalho(
        data_ref,
        modo
    )

    ax_header.text(
        0.01,
        0.75,
        regional.upper(),
        color="#8DB4FF",
        fontsize=9.0,
        fontweight="bold",
        va="center"
    )

    ax_header.text(
        0.01,
        0.45,
        "RELATÓRIO EXECUTIVO DE FALTA DE ÁGUA",
        color="#FFFFFF",
        fontsize=18,
        fontweight="bold",
        va="center"
    )

    ax_header.text(
        0.01,
        0.15,
        (
            f"Período Analisado: "
            f"{periodo_texto} ({modo})"
        ),
        color="#E2E8F0",
        fontsize=9.5,
        va="center"
    )

    # ========================================================
    # LOGO
    # ========================================================

    if logo_img is not None:

        try:

            logo_branca = (
                logo_img
                .convert("RGBA")
            )

            data_logo = np.array(
                logo_branca
            )

            data_logo[..., :3] = [
                255,
                255,
                255
            ]

            logo_branca = Image.fromarray(
                data_logo
            )

            ax_logo = fig.add_axes(
                [
                    0.80,
                    0.885,
                    0.15,
                    0.06
                ],
                zorder=3
            )

            ax_logo.imshow(
                logo_branca
            )

            ax_logo.axis("off")

        except Exception:

            ax_header.text(
                0.99,
                0.50,
                "ÁGUAS DO PIAUÍ",
                color="#FFFFFF",
                fontsize=16,
                fontweight="bold",
                ha="right",
                va="center"
            )

    else:

        ax_header.text(
            0.99,
            0.50,
            "ÁGUAS DO PIAUÍ",
            color="#FFFFFF",
            fontsize=16,
            fontweight="bold",
            ha="right",
            va="center"
        )

    # ========================================================
    # ESTILO DOS CARDS
    # ========================================================

    def estilizar_card(
        ax,
        border_color=C_BORDER,
        bg_color=C_CARD
    ):

        ax.set_facecolor(
            bg_color
        )

        ax.set_xticks([])
        ax.set_yticks([])

        for spine in ax.spines.values():

            spine.set_color(
                border_color
            )

            spine.set_linewidth(
                1.1
            )

    kpis = dashboard_data["kpis"]

    lider = dashboard_data["lider"]

    areas_criticas = (
        dashboard_data["areas_criticas"]
    )

    # ========================================================
    # FUNÇÃO DE KPI
    # ========================================================

    def desenhar_kpi(
        ax,
        titulo,
        valor,
        cor_val,
        subtexto=None,
        cor_sub=C_MUTED
    ):

        estilizar_card(ax)

        patch_accent = FancyBboxPatch(
            (
                0.0,
                0.90
            ),
            1.0,
            0.10,
            boxstyle=(
                "round,pad=0.0"
            ),
            facecolor=cor_val,
            edgecolor="none",
            transform=ax.transAxes
        )

        ax.add_patch(
            patch_accent
        )

        ax.text(
            0.08,
            0.72,
            titulo.upper(),
            fontsize=7.5,
            fontweight="bold",
            color=C_MUTED,
            transform=ax.transAxes
        )

        ax.text(
            0.08,
            0.35,
            str(valor),
            fontsize=26,
            fontweight="bold",
            color=C_TEXT,
            transform=ax.transAxes
        )

        if subtexto:

            ax.text(
                0.08,
                0.12,
                subtexto,
                fontsize=7.5,
                fontweight="semibold",
                color=cor_sub,
                transform=ax.transAxes
            )

    # ========================================================
    # KPIs
    # ========================================================

    ax_k1 = fig.add_subplot(
        gs[1, 0]
    )

    desenhar_kpi(
        ax_k1,
        "Total O.S.",
        kpis["total_registros"],
        C_PRIMARY,
        "Demanda total do período"
    )

    ax_k2 = fig.add_subplot(
        gs[1, 1]
    )

    percentual_rec = (
        kpis["total_reclamacoes"]
        /
        kpis["total_registros"]
        *
        100
        if kpis["total_registros"] > 0
        else 0
    )

    desenhar_kpi(
        ax_k2,
        "Reclamações",
        kpis["total_reclamacoes"],
        C_PRIMARY,
        f"{percentual_rec:.0f}% do total"
    )

    ax_k3 = fig.add_subplot(
        gs[1, 2]
    )

    percentual_inf = (
        kpis["total_informacoes"]
        /
        kpis["total_registros"]
        *
        100
        if kpis["total_registros"] > 0
        else 0
    )

    desenhar_kpi(
        ax_k3,
        "Informações",
        kpis["total_informacoes"],
        C_INFO,
        f"{percentual_inf:.0f}% do total"
    )

    ax_k4 = fig.add_subplot(
        gs[1, 3]
    )

    desenhar_kpi(
        ax_k4,
        plural_rotulo,
        kpis["municipios_afetados"],
        "#334155",
        "Com registros no período"
    )

    ax_k5 = fig.add_subplot(
        gs[1, 4]
    )

    desenhar_kpi(
        ax_k5,
        f"{singular_rotulo} LÍDER",
        lider["total_registros"],
        C_PRIMARY,
        lider["municipio"].upper(),
        cor_sub=C_PRIMARY
    )

    ax_k6 = fig.add_subplot(
        gs[1, 5]
    )

    qtd_criticas = (
        areas_criticas[
            "qtd_criticas"
        ]
    )

    cor_al = (
        C_ALERT
        if qtd_criticas > 0
        else C_TEXT
    )

    desenhar_kpi(
        ax_k6,
        "ÁREAS CRÍTICAS",
        qtd_criticas,
        cor_al,
        "> 5 rec."
        if qtd_criticas > 0
        else "Nenhum alerta",
        cor_sub=cor_al
    )

    ax_k7 = fig.add_subplot(
        gs[1, 6]
    )

    desenhar_kpi(
        ax_k7,
        "CONCENTRAÇÃO TOP 5",
        f"{dashboard_data.get('concentracao_top5', 0.0):.0f}%",
        C_PRIMARY,
        "Volume acumulado",
        cor_sub=C_MUTED
    )

    # ========================================================
    # TOP 5
    # ========================================================

    ax_top5 = fig.add_subplot(
        gs[2:4, 0:4]
    )

    estilizar_card(
        ax_top5
    )

    ax_top5.grid(False)

    top5_df = dashboard_data["top5"]

    if not top5_df.empty:

        cidades = (
            top5_df[col_fmt]
            .tolist()
        )

        reclamacoes_of = (
            top5_df["RECLAMACAO"]
            .tolist()
        )

        informacoes_of = (
            top5_df["INFORMACAO"]
            .tolist()
        )

        totais_of = (
            top5_df["TOTAL"]
            .tolist()
        )

        x = np.arange(
            len(cidades)
        )

        width = 0.35

        rects1 = ax_top5.bar(
            x - width / 2,
            reclamacoes_of,
            width,
            label="Reclamação",
            color=C_PRIMARY
        )

        rects2 = ax_top5.bar(
            x + width / 2,
            informacoes_of,
            width,
            label="Informação",
            color=C_INFO
        )

        ax_top5.set_title(
            (
                f"TOP 5 {plural_rotulo} "
                "COM MAIOR DEMANDA"
            ),
            fontsize=11.0,
            fontweight="bold",
            color=C_TEXT,
            pad=15,
            loc="left"
        )

        ax_top5.set_xticks(x)

        labels_eixo = [
            f"{cid}\nTotal: {tot}"
            for cid, tot
            in zip(
                cidades,
                totais_of
            )
        ]

        ax_top5.set_xticklabels(
            labels_eixo,
            fontsize=10.0,
            fontweight="bold",
            color=C_TEXT
        )

        ax_top5.legend(
            loc="upper right",
            frameon=False,
            fontsize=9.5
        )

        max_val = max(
            max(
                reclamacoes_of,
                default=1
            ),
            max(
                informacoes_of,
                default=1
            )
        )

        ax_top5.set_ylim(
            0,
            max_val * 1.25
        )

        for rects, col_color in zip(
            [
                rects1,
                rects2
            ],
            [
                C_PRIMARY,
                C_INFO
            ]
        ):

            for rect in rects:

                h = rect.get_height()

                if h > 0:

                    y_pos = (
                        h
                        +
                        (
                            max_val
                            * 0.02
                        )
                        if h
                        < max_val * 0.15
                        else h * 0.5
                    )

                    color_txt = (
                        col_color
                        if h
                        < max_val * 0.15
                        else "white"
                    )

                    va_align = (
                        "bottom"
                        if h
                        < max_val * 0.15
                        else "center"
                    )

                    ax_top5.text(
                        rect.get_x()
                        +
                        rect.get_width()
                        / 2.,
                        y_pos,
                        f"{int(h)}",
                        ha="center",
                        va=va_align,
                        fontsize=10.5,
                        fontweight="bold",
                        color=color_txt
                    )

        ax_top5.spines[
            "top"
        ].set_visible(False)

        ax_top5.spines[
            "right"
        ].set_visible(False)

    else:

        ax_top5.text(
            0.5,
            0.5,
            "Não existem registros no período selecionado.",
            ha="center",
            va="center",
            fontsize=10,
            color=C_MUTED,
            transform=ax_top5.transAxes
        )

    # ========================================================
    # ÁREAS EM ATENÇÃO
    # ========================================================

    ax_atencao = fig.add_subplot(
        gs[2, 4:7]
    )

    estilizar_card(
        ax_atencao
    )

    ax_atencao.text(
        0.04,
        0.86,
        f"⚠ {plural_rotulo} EM ATENÇÃO",
        fontsize=10.5,
        fontweight="bold",
        color=C_ALERT,
        transform=ax_atencao.transAxes
    )

    atencao_list = (
        dashboard_data[
            "municipios_atencao"
        ]
    )

    if not atencao_list:

        ax_atencao.text(
            0.04,
            0.50,
            (
                f"Nenhum "
                f"{singular_rotulo.lower()} "
                "registrado."
            ),
            fontsize=9.5,
            color=C_MUTED,
            va="center",
            transform=ax_atencao.transAxes
        )

    else:

        y_p = 0.58

        for i, item in enumerate(
            atencao_list[:3]
        ):

            if i > 0:

                ax_atencao.plot(
                    [
                        0.04,
                        0.96
                    ],
                    [
                        y_p + 0.12,
                        y_p + 0.12
                    ],
                    color="#E2E8F0",
                    linewidth=0.8,
                    transform=ax_atencao.transAxes
                )

            ax_atencao.text(
                0.04,
                y_p,
                f"{item['registros']}",
                fontsize=18,
                fontweight="bold",
                color=C_ALERT,
                va="center",
                transform=ax_atencao.transAxes
            )

            ax_atencao.text(
                0.15,
                y_p + 0.06,
                f"{item['municipio']}",
                fontsize=11.0,
                fontweight="bold",
                color=C_TEXT,
                va="center",
                transform=ax_atencao.transAxes
            )

            ax_atencao.text(
                0.15,
                y_p - 0.06,
                (
                    f"R: {item.get('rec_oficial', 0)}"
                    f"   |   "
                    f"I: {item.get('inf_oficial', 0)}"
                ),
                fontsize=9.5,
                fontweight="bold",
                color=C_MUTED,
                va="center",
                transform=ax_atencao.transAxes
            )

            y_p -= 0.22

    # ========================================================
    # INFORMAÇÕES OPERACIONAIS
    # ========================================================

    ax_eventos = fig.add_subplot(
        gs[3, 4:7]
    )

    estilizar_card(
        ax_eventos
    )

    ax_eventos.text(
        0.04,
        0.88,
        "INFORMAÇÕES OPERACIONAIS",
        fontsize=10.5,
        fontweight="bold",
        color=C_PRIMARY,
        transform=ax_eventos.transAxes
    )

    ev_manuais = dashboard_data.get(
        "eventos_manuais",
        []
    )

    if not ev_manuais:

        ax_eventos.text(
            0.04,
            0.50,
            (
                "Nenhum evento operacional "
                "de destaque registrado."
            ),
            fontsize=9.5,
            color=C_MUTED,
            va="center",
            transform=ax_eventos.transAxes
        )

    else:

        num_ev = len(
            ev_manuais
        )

        if num_ev == 3:

            y_tops = [
                0.72,
                0.44,
                0.16
            ]

        elif num_ev == 2:

            y_tops = [
                0.65,
                0.30
            ]

        else:

            y_tops = [
                0.55
            ]

        for i, ev in enumerate(
            ev_manuais
        ):

            y_top = y_tops[i]

            mun_str = (
                ev.get(
                    "mun",
                    ""
                )
                .strip()
                .title()
            )

            tag_str = (
                ev.get(
                    "tag",
                    ""
                )
                .strip()
                .upper()
            )

            desc_str = (
                ev.get(
                    "desc",
                    ""
                )
                .strip()
                .title()
            )

            linha_parts = []

            if mun_str:
                linha_parts.append(
                    mun_str
                )

            if tag_str:
                linha_parts.append(
                    tag_str
                )

            if desc_str:
                linha_parts.append(
                    desc_str
                )

            titulo_completo = (
                " – ".join(
                    linha_parts
                )
            )

            if not titulo_completo:

                titulo_completo = (
                    f"Evento {i + 1}"
                )

            obs = str(
                ev.get(
                    "obs",
                    ""
                )
            ).strip()

            if len(obs) > 150:
                obs = obs[:150]

            if obs:

                import textwrap

                obs_wrap = "\n".join(
                    textwrap.wrap(
                        obs,
                        width=78
                    )
                )

            else:

                obs_wrap = ""

            ax_eventos.text(
                0.04,
                y_top,
                titulo_completo,
                fontsize=10.0,
                fontweight="bold",
                color=C_TEXT,
                transform=ax_eventos.transAxes
            )

            if obs_wrap:

                ax_eventos.text(
                    0.04,
                    y_top - 0.08,
                    obs_wrap,
                    fontsize=9.5,
                    color=C_OBS_DARK,
                    va="top",
                    transform=ax_eventos.transAxes
                )

    # ========================================================
    # RODAPÉ
    # ========================================================

    ax_footer = fig.add_subplot(
        gs[4, :]
    )

    ax_footer.axis("off")

    ax_footer.text(
        0.5,
        0.50,
        (
            "Fonte: COI – "
            "Centro de Operações Integradas"
        ),
        ha="center",
        va="center",
        fontsize=9.0,
        fontweight="semibold",
        color=C_MUTED
    )

    # ========================================================
    # EXPORTAÇÃO PARA MEMÓRIA
    # ========================================================

    output = io.BytesIO()

    plt.savefig(
        output,
        format="png",
        dpi=200,
        bbox_inches="tight",
        facecolor=fig.get_facecolor()
    )

    output.seek(0)

    plt.close(fig)

    return output


# ============================================================
# EVENTOS OPERACIONAIS
# ============================================================

def extrair_eventos_manuais(
    evento1,
    tag1,
    desc1,
    obs1,
    evento2,
    tag2,
    desc2,
    obs2,
    evento3,
    tag3,
    desc3,
    obs3
):

    eventos = []

    grupos = [
        (
            evento1,
            tag1,
            desc1,
            obs1
        ),
        (
            evento2,
            tag2,
            desc2,
            obs2
        ),
        (
            evento3,
            tag3,
            desc3,
            obs3
        )
    ]

    for (
        mun,
        tag,
        desc,
        obs
    ) in grupos:

        if any(
            str(v).strip()
            for v in [
                mun,
                tag,
                desc,
                obs
            ]
        ):

            eventos.append({

                "mun": str(mun),

                "tag": str(tag),

                "desc": str(desc),

                "obs": str(obs)
            })

    return eventos[:3]


# ============================================================
# INICIALIZAÇÃO DO ESTADO
# ============================================================

if "card_operacional_png" not in st.session_state:

    st.session_state[
        "card_operacional_png"
    ] = None

if "card_operacional_info" not in st.session_state:

    st.session_state[
        "card_operacional_info"
    ] = None


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### Cards Operacionais"
    )

    st.caption(
        "Configuração do relatório executivo"
    )

    st.divider()

    # ========================================================
    # BASE
    # ========================================================

    st.markdown(
        "**1. Base de dados**"
    )

    arquivo_os = st.file_uploader(
        "Planilha de O.S.",
        type=[
            "xlsx",
            "xls"
        ],
        help=(
            "Envie a base bruta de Ordens de Serviço."
        )
    )

    logo_upload = st.file_uploader(
        "Logo (opcional)",
        type=[
            "png",
            "jpg",
            "jpeg"
        ]
    )

    st.divider()

    # ========================================================
    # CONFIGURAÇÃO
    # ========================================================

    st.markdown(
        "**2. Configuração do relatório**"
    )

    escopo = st.selectbox(
        "Escopo",
        options=[
            "PIAUI",
            "TERESINA"
        ],
        format_func=lambda x: (
            "Piauí (Municípios)"
            if x == "PIAUI"
            else "Teresina (Bairros)"
        )
    )

    regional = st.text_input(
        "Regional",
        value="REGIONAL SEMIÁRIDO - SUL"
    )

    modo = st.selectbox(
        "Período",
        options=[
            "AUTO",
            "DIARIO",
            "SEMANAL",
            "MENSAL"
        ],
        format_func=lambda x: {

            "AUTO": "Automático",

            "DIARIO": "Diário",

            "SEMANAL": "Semanal",

            "MENSAL": "Mensal"

        }[x]
    )

    data_manual = st.text_input(
        "Data de referência",
        placeholder="Ex.: 30/09/2026",
        help=(
            "Deixe vazio para utilizar automaticamente "
            "a maior data encontrada na base."
        )
    )

    st.divider()

    # ========================================================
    # EVENTOS
    # ========================================================

    st.markdown(
        "**3. Informações operacionais**"
    )

    st.caption(
        "Até 3 eventos podem ser incluídos no card."
    )

    st.markdown(
        "Evento 1"
    )

    ev1_mun = st.text_input(
        "Município",
        key="ev1_mun"
    )

    ev1_tag = st.text_input(
        "Tag",
        key="ev1_tag"
    )

    ev1_desc = st.text_input(
        "Evento",
        key="ev1_desc"
    )

    ev1_obs = st.text_area(
        "Observação",
        key="ev1_obs",
        height=70
    )

    st.markdown(
        "Evento 2"
    )

    ev2_mun = st.text_input(
        "Município",
        key="ev2_mun"
    )

    ev2_tag = st.text_input(
        "Tag",
        key="ev2_tag"
    )

    ev2_desc = st.text_input(
        "Evento",
        key="ev2_desc"
    )

    ev2_obs = st.text_area(
        "Observação",
        key="ev2_obs",
        height=70
    )

    st.markdown(
        "Evento 3"
    )

    ev3_mun = st.text_input(
        "Município",
        key="ev3_mun"
    )

    ev3_tag = st.text_input(
        "Tag",
        key="ev3_tag"
    )

    ev3_desc = st.text_input(
        "Evento",
        key="ev3_desc"
    )

    ev3_obs = st.text_area(
        "Observação",
        key="ev3_obs",
        height=70
    )

    st.divider()

    gerar = st.button(
        "GERAR CARD",
        type="primary",
        use_container_width=True
    )

    if st.button(
        "Voltar ao Menu Principal",
        use_container_width=True
    ):
        st.switch_page(
            "app.py"
        )


# ============================================================
# CABEÇALHO DA PÁGINA
# ============================================================

st.markdown(
    '<div class="main-title">Cards Operacionais</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="main-subtitle">'
    'Relatório executivo de falta de água'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# ÁREA PRINCIPAL
# ============================================================

if arquivo_os is None:

    st.markdown(
        """
        <div class="info-box">
        <strong>Base de dados não carregada.</strong><br>
        Utilize o painel lateral para enviar a planilha de O.S.
        e configurar o relatório.
        </div>
        """,
        unsafe_allow_html=True
    )

else:

    st.markdown(
        '<div class="section-title">Base carregada</div>',
        unsafe_allow_html=True
    )

    col_info1, col_info2, col_info3 = st.columns(3)

    col_info1.metric(
        "Arquivo",
        arquivo_os.name
    )

    col_info2.metric(
        "Formato",
        arquivo_os.name.split(".")[-1].upper()
    )

    col_info3.metric(
        "Tamanho",
        f"{arquivo_os.size / 1024:.1f} KB"
    )


# ============================================================
# PROCESSAMENTO
# ============================================================

if gerar:

    if arquivo_os is None:

        st.error(
            "Envie a planilha de O.S. antes de gerar o card."
        )

        st.stop()

    with st.spinner(
        "Processando a base e gerando o Card Operacional..."
    ):

        try:

            # ------------------------------------------------
            # LEITURA DA PLANILHA
            # ------------------------------------------------

            arquivo_os.seek(0)

            raw_df = pd.read_excel(
                arquivo_os
            )

            if raw_df.empty:

                raise ValueError(
                    "A planilha enviada está vazia."
                )

            # ------------------------------------------------
            # PREPARAÇÃO
            # ------------------------------------------------

            df_os = preparar_dataframe_os(
                raw_df
            )

            # ------------------------------------------------
            # PERÍODO
            # ------------------------------------------------

            modo_final, data_ref = (
                detectar_periodo_e_data_ref(
                    df_os,
                    modo,
                    data_manual
                )
            )

            # ------------------------------------------------
            # FILTRO
            # ------------------------------------------------

            df_periodo = filtrar_periodo(
                df_os,
                modo_final,
                data_ref
            )

            # ------------------------------------------------
            # EVENTOS
            # ------------------------------------------------

            eventos = extrair_eventos_manuais(

                ev1_mun,
                ev1_tag,
                ev1_desc,
                ev1_obs,

                ev2_mun,
                ev2_tag,
                ev2_desc,
                ev2_obs,

                ev3_mun,
                ev3_tag,
                ev3_desc,
                ev3_obs
            )

            # ------------------------------------------------
            # DADOS DO DASHBOARD
            # ------------------------------------------------

            dashboard_data = construir_dashboard_data(
                df_periodo,
                escopo=escopo,
                eventos_manuais=eventos
            )

            # ------------------------------------------------
            # LOGO
            # ------------------------------------------------

            logo_img = None

            if logo_upload is not None:

                logo_upload.seek(0)

                logo_img = Image.open(
                    logo_upload
                )

            # ------------------------------------------------
            # RENDERIZAÇÃO
            # ------------------------------------------------

            png_buffer = renderizar_card_executivo(
                dashboard_data,
                data_ref,
                modo_final,
                regional.strip()
                or "REGIONAL",
                logo_img
            )

            # ------------------------------------------------
            # SESSION STATE
            # ------------------------------------------------

            st.session_state[
                "card_operacional_png"
            ] = png_buffer.getvalue()

            st.session_state[
                "card_operacional_info"
            ] = {

                "modo": modo_final,

                "data_ref": data_ref,

                "registros_base": len(
                    df_os
                ),

                "registros_periodo": len(
                    df_periodo
                ),

                "escopo": escopo
            }

            st.success(
                "Card Operacional gerado com sucesso."
            )

        except Exception as err:

            st.session_state[
                "card_operacional_png"
            ] = None

            st.session_state[
                "card_operacional_info"
            ] = None

            st.error(
                f"Não foi possível gerar o card: {err}"
            )


# ============================================================
# EXIBIÇÃO DO CARD
# ============================================================

if (
    st.session_state[
        "card_operacional_png"
    ] is not None
):

    st.markdown(
        '<div class="section-title">Card Operacional</div>',
        unsafe_allow_html=True
    )

    info = st.session_state[
        "card_operacional_info"
    ]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Período",
        info["modo"]
    )

    col2.metric(
        "Data de referência",
        info["data_ref"]
    )

    col3.metric(
        "Registros na base",
        info["registros_base"]
    )

    col4.metric(
        "Registros no período",
        info["registros_periodo"]
    )

    st.markdown(
        "<br>",
        unsafe_allow_html=True
    )

    st.image(
        st.session_state[
            "card_operacional_png"
        ],
        use_container_width=True
    )

    st.markdown(
        "<br>",
        unsafe_allow_html=True
    )

    st.download_button(
        label="BAIXAR CARD EM PNG",
        data=st.session_state[
            "card_operacional_png"
        ],
        file_name=(
            "card_operacional.png"
        ),
        mime="image/png",
        use_container_width=False
    )

else:

    if arquivo_os is not None:

        st.markdown(
            """
            <div class="info-box">
            A base foi carregada. Configure o relatório no painel
            lateral e clique em <strong>GERAR CARD</strong>.
            </div>
            """,
            unsafe_allow_html=True
        )
