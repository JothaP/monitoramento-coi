import streamlit as st
import io
import re
from pathlib import Path
from datetime import datetime, date

import pandas as pd
import numpy as np

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================

st.set_page_config(
    page_title="Relatório de Falta de Água - COI",
    page_icon="💧",
    layout="wide",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    .titulo-principal {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .subtitulo {
        color: #666;
        margin-bottom: 1.5rem;
    }

    .stButton > button {
        width: 100%;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# MAPA DE BAIRROS / ZONAS
# ============================================================
# Mantido no código por compatibilidade com o restante do
# projeto. NÃO é utilizado na geração do relatório THE/TIM.
# ============================================================

ZONA_POR_BAIRRO = {
    # Mantenha aqui o seu dicionário original ZONA_POR_BAIRRO.
    #
    # Exemplo:
    #
    # "CENTRO": "ZONA CENTRO",
    # "MOCAMBINHO": "ZONA NORTE",
    #
    # O relatório atual não utiliza essa informação.
}


# ============================================================
# BASES POR CIDADE - API
# ============================================================

BASE_POR_CIDADE = {
    # Mantenha aqui o seu mapeamento original.
    #
    # Exemplo:
    # "TERESINA": "BASE TERESINA",
    # "PARNAIBA": "BASE PARNAÍBA",
}


# ============================================================
# MESES
# ============================================================

MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


# ============================================================
# LOGOS
# ============================================================

LOGOS = {
    "API": "assets/logos/logo_aguas_do_piaui.png",
    "THE": "assets/logos/logo_aguas_de_teresina.png",
    "TIM": "assets/logos/logo_aguas_de_timon.png",
}


# ============================================================
# NOMES DAS EMPRESAS
# ============================================================

NOMES_EMPRESAS = {
    "API": "Águas do Piauí",
    "THE": "Águas de Teresina",
    "TIM": "Águas de Timon",
}


# ============================================================
# TÍTULOS
# ============================================================

TITULOS = {
    "API": "Relatório de Falta de Água - Águas do Piauí",
    "THE": "Relatório de Falta de Água - Águas de Teresina",
    "TIM": "Relatório de Falta de Água - Águas de Timon",
}


# ============================================================
# CORES
# ============================================================

COR_AZUL = (0, 83, 155)
COR_AZUL_ESCURO = (0, 55, 110)
COR_AZUL_CLARO = (225, 239, 250)

COR_CINZA = (245, 247, 249)
COR_CINZA_BORDA = (210, 215, 220)
COR_CINZA_TEXTO = (90, 90, 90)

COR_BRANCO = (255, 255, 255)
COR_PRETO = (30, 30, 30)


# ============================================================
# FONTES
# ============================================================

def obter_fonte(tamanho, negrito=False):
    """
    Tenta encontrar uma fonte adequada no ambiente.
    """

    caminhos_negrito = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    caminhos_normal = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    caminhos = caminhos_negrito if negrito else caminhos_normal

    for caminho in caminhos:
        if Path(caminho).exists():
            try:
                return ImageFont.truetype(caminho, tamanho)
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalizar(valor):
    if pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    texto = (
        texto.replace("Á", "A")
        .replace("À", "A")
        .replace("Ã", "A")
        .replace("Â", "A")
        .replace("Ä", "A")
        .replace("É", "E")
        .replace("È", "E")
        .replace("Ê", "E")
        .replace("Ë", "E")
        .replace("Í", "I")
        .replace("Ì", "I")
        .replace("Î", "I")
        .replace("Ï", "I")
        .replace("Ó", "O")
        .replace("Ò", "O")
        .replace("Õ", "O")
        .replace("Ô", "O")
        .replace("Ö", "O")
        .replace("Ú", "U")
        .replace("Ù", "U")
        .replace("Û", "U")
        .replace("Ü", "U")
        .replace("Ç", "C")
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto


def normalizar_cidade(valor):
    return normalizar(valor)


# ============================================================
# ZONA
# ============================================================

def obter_zona(bairro):
    bairro_norm = normalizar(bairro)

    return ZONA_POR_BAIRRO.get(
        bairro_norm,
        "Não classificado"
    )


# ============================================================
# BASE
# ============================================================

def obter_base(cidade):
    cidade_norm = normalizar_cidade(cidade)

    return BASE_POR_CIDADE.get(
        cidade_norm,
        "Não classificada"
    )


# ============================================================
# LOCALIZAÇÃO DE COLUNAS
# ============================================================

def localizar_coluna(df, candidatos):
    """
    Localiza uma coluna considerando pequenas diferenças
    de acentuação, caixa e espaços.
    """

    mapa = {}

    for coluna in df.columns:
        chave = normalizar(coluna)
        mapa[chave] = coluna

    for candidato in candidatos:
        chave = normalizar(candidato)

        if chave in mapa:
            return mapa[chave]

    # Busca aproximada
    for candidato in candidatos:
        chave_candidato = normalizar(candidato)

        for chave, coluna_real in mapa.items():
            if (
                chave_candidato in chave
                or chave in chave_candidato
            ):
                return coluna_real

    return None


# ============================================================
# CONVERSÃO DE DATA
# ============================================================

def converter_abertura(serie):
    """
    Converte a coluna Início do SLA para datetime.

    Exemplos aceitos:
    02/10/2026 14:04
    02/10/2026 14:04:00
    """

    if serie is None:
        return pd.Series(dtype="datetime64[ns]")

    resultado = pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=True
    )

    return resultado


# ============================================================
# FORMATAÇÃO DE NÚMEROS
# ============================================================

def formatar_numero(valor):
    try:
        valor = int(valor)

        return f"{valor:,}".replace(",", ".")

    except Exception:
        return str(valor)


# ============================================================
# ABREVIAÇÃO DE TEXTO
# ============================================================

def abreviar_texto(texto, limite=28):
    texto = str(texto)

    if len(texto) <= limite:
        return texto

    return texto[:limite - 3] + "..."


# ============================================================
# TEXTO DO PERÍODO
# ============================================================

def texto_cabecalho_periodo(df):
    if df is None or df.empty:
        return ""

    data_min = df["_ABERTURA"].min()
    data_max = df["_ABERTURA"].max()

    if pd.isna(data_min) or pd.isna(data_max):
        return ""

    if data_min.date() == data_max.date():
        return data_min.strftime("%d/%m/%Y")

    return (
        f"{data_min.strftime('%d/%m/%Y')} "
        f"a "
        f"{data_max.strftime('%d/%m/%Y')}"
    )


# ============================================================
# LEITURA DA PLANILHA
# ============================================================

def ler_planilha(arquivo):

    if arquivo is None:
        return None

    nome = arquivo.name.lower()

    try:
        arquivo.seek(0)

        if nome.endswith(".xlsx"):

            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="openpyxl"
            )

        elif nome.endswith(".xlsb"):

            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="pyxlsb"
            )

        elif nome.endswith(".xls"):

            return pd.read_excel(
                arquivo,
                sheet_name=0,
                engine="xlrd"
            )

        else:

            st.error(
                "Formato não suportado. "
                "Use .xlsx, .xls ou .xlsb."
            )

            return None

    except Exception as erro:

        st.error(
            f"Não foi possível ler o arquivo: {erro}"
        )

        return None


# ============================================================
# PREPARAÇÃO DOS DADOS
# ============================================================

def preparar_dados(df, operacao):

    if df is None or df.empty:
        return None

    dados = df.copy()

    # --------------------------------------------------------
    # DATA DE ABERTURA
    # --------------------------------------------------------

    coluna_abertura = localizar_coluna(
        dados,
        [
            "Início do SLA",
            "Inicio do SLA",
            "Início SLA",
            "Inicio SLA",

            # Fallbacks antigos
            "Abertura",
            "Data Abertura",
            "Data de Abertura",
            "Data_Abertura",
            "Dt Abertura",
            "Data",
        ]
    )

    if coluna_abertura is None:

        st.error(
            "Não foi encontrada a coluna "
            "'Início do SLA' na planilha."
        )

        return None

    dados["_ABERTURA"] = converter_abertura(
        dados[coluna_abertura]
    )

    dados = dados.dropna(
        subset=["_ABERTURA"]
    ).copy()

    if dados.empty:
        st.warning(
            "Não existem registros com data de "
            "abertura válida."
        )

        return None

    # --------------------------------------------------------
    # PROTOCOLO / O.S.
    # --------------------------------------------------------

    coluna_protocolo = localizar_coluna(
        dados,
        [
            "Cód. Protocolo Origem",
            "Cod. Protocolo Origem",
            "Código Protocolo Origem",
            "Codigo Protocolo Origem",
            "Protocolo Origem",
            "Protocolo",
            "O.S.",
            "OS",
            "Ordem de Serviço",
            "Ordem Serviço",
        ]
    )

    if coluna_protocolo is not None:

        dados["_PROTOCOLO"] = (
            dados[coluna_protocolo]
            .astype(str)
            .str.strip()
        )

        dados["_PROTOCOLO"] = dados[
            "_PROTOCOLO"
        ].replace(
            {
                "nan": "",
                "None": "",
                "NaN": "",
            }
        )

    else:

        dados["_PROTOCOLO"] = ""

    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    if operacao in ["THE", "TIM"]:

        coluna_bairro = localizar_coluna(
            dados,
            [
                "Bairro",
                "BAIRRO",
            ]
        )

        if coluna_bairro is None:

            st.error(
                "Não foi encontrada a coluna "
                "'Bairro' na planilha."
            )

            return None

        dados["_LOCAL"] = (
            dados[coluna_bairro]
            .fillna("Não informado")
            .astype(str)
            .str.strip()
        )

        dados["_LOCAL"] = dados[
            "_LOCAL"
        ].replace(
            {
                "": "Não informado",
                "nan": "Não informado",
            }
        )

        dados["_BASE"] = ""

    else:

        coluna_cidade = localizar_coluna(
            dados,
            [
                "Cidade",
                "CIDADE",
                "Município",
                "Municipio",
            ]
        )

        if coluna_cidade is None:

            st.error(
                "Não foi encontrada a coluna "
                "'Cidade' ou 'Município' na planilha."
            )

            return None

        dados["_LOCAL"] = (
            dados[coluna_cidade]
            .fillna("Não informado")
            .astype(str)
            .str.strip()
        )

        dados["_LOCAL"] = dados[
            "_LOCAL"
        ].replace(
            {
                "": "Não informado",
                "nan": "Não informado",
            }
        )

        dados["_BASE"] = dados[
            "_LOCAL"
        ].apply(obter_base)

    # --------------------------------------------------------
    # DATA / MÊS
    # --------------------------------------------------------

    dados["_DATA"] = (
        dados["_ABERTURA"]
        .dt.normalize()
    )

    dados["_MES_ORDEM"] = (
        dados["_ABERTURA"]
        .dt.to_period("M")
        .dt.to_timestamp()
    )

    return dados


# ============================================================
# CONTAGEM DAS O.S.
# ============================================================

def contar_os(series_protocolos):

    protocolos = (
        series_protocolos
        .astype(str)
        .str.strip()
    )

    protocolos_validos = protocolos[
        ~protocolos.isin(
            [
                "",
                "nan",
                "None",
                "NaN",
            ]
        )
    ]

    if not protocolos_validos.empty:
        return protocolos_validos.nunique()

    return len(series_protocolos)


# ============================================================
# MATRIZ DO RELATÓRIO
# ============================================================

def construir_matriz(dados, modo):

    if dados is None or dados.empty:
        return None

    if modo == "Por dia":

        periodos = sorted(
            dados["_DATA"].dropna().unique()
        )

        chave_periodo = "_DATA"

    else:

        periodos = sorted(
            dados["_MES_ORDEM"].dropna().unique()
        )

        chave_periodo = "_MES_ORDEM"

    if not periodos:
        return None

    locais = sorted(
        dados["_LOCAL"]
        .dropna()
        .astype(str)
        .unique(),
        key=lambda x: normalizar(x)
    )

    registros = []

    for local in locais:

        linha = {
            "LOCAL": local
        }

        total = 0

        for periodo in periodos:

            filtro = (
                dados["_LOCAL"].astype(str) == str(local)
            ) & (
                dados[chave_periodo] == periodo
            )

            quantidade = contar_os(
                dados.loc[filtro, "_PROTOCOLO"]
            )

            total += quantidade

            linha[periodo] = quantidade

        linha["TOTAL"] = total

        registros.append(linha)

    matriz = pd.DataFrame(registros)

    return matriz, periodos


# ============================================================
# FORMATAÇÃO DOS PERÍODOS
# ============================================================

def formatar_periodo(periodo, modo):

    periodo = pd.Timestamp(periodo)

    if modo == "Por dia":

        return periodo.strftime("%d/%m")

    mes = MESES_PT.get(
        periodo.month,
        periodo.strftime("%b")
    )

    return f"{mes}/{periodo.strftime('%y')}"


# ============================================================
# MEDIÇÃO DE TEXTO
# ============================================================

def medir_texto(draw, texto, fonte):

    try:

        caixa = draw.textbbox(
            (0, 0),
            str(texto),
            font=fonte
        )

        return (
            caixa[2] - caixa[0],
            caixa[3] - caixa[1]
        )

    except Exception:

        return draw.textsize(
            str(texto),
            font=fonte
        )


# ============================================================
# DESENHAR TEXTO CENTRALIZADO
# ============================================================

def desenhar_texto_centralizado(
    draw,
    texto,
    caixa,
    fonte,
    fill=COR_PRETO
):

    x1, y1, x2, y2 = caixa

    largura, altura = medir_texto(
        draw,
        texto,
        fonte
    )

    x = x1 + (x2 - x1 - largura) / 2
    y = y1 + (y2 - y1 - altura) / 2

    draw.text(
        (x, y),
        str(texto),
        font=fonte,
        fill=fill
    )


# ============================================================
# DESENHO DA TABELA
# ============================================================

def desenhar_tabela(
    draw,
    matriz,
    periodos,
    modo,
    x,
    y,
    largura_total,
):
    """
    Desenha a tabela principal.

    A tabela ocupa toda a largura disponível.
    Quando existem muitos períodos, eles são divididos
    em blocos verticais para manter o relatório em formato
    vertical e preservar a leitura.
    """

    if matriz is None or matriz.empty:
        return y

    # --------------------------------------------------------
    # CONFIGURAÇÕES
    # --------------------------------------------------------

    margem = 25

    altura_cabecalho = 52
    altura_linha = 43

    fonte_cabecalho = obter_fonte(
        18,
        negrito=True
    )

    fonte_local = obter_fonte(
        16,
        negrito=False
    )

    fonte_valor = obter_fonte(
        16,
        negrito=True
    )

    fonte_total = obter_fonte(
        17,
        negrito=True
    )

    # --------------------------------------------------------
    # LARGURAS
    # --------------------------------------------------------

    largura_util = (
        largura_total
        - (margem * 2)
    )

    largura_local = 360
    largura_total_coluna = 110

    largura_periodo_disponivel = (
        largura_util
        - largura_local
        - largura_total_coluna
    )

    # Número máximo de períodos por bloco.
    #
    # Isso evita que uma visualização diária com muitos dias
    # gere uma tabela horizontal impossível de ler.
    # --------------------------------------------------------

    largura_minima_periodo = 72

    periodos_por_bloco = max(
        1,
        int(
            largura_periodo_disponivel
            / largura_minima_periodo
        )
    )

    # Mantém um limite visual confortável.
    periodos_por_bloco = min(
        periodos_por_bloco,
        14
    )

    blocos = [
        periodos[i:i + periodos_por_bloco]
        for i in range(
            0,
            len(periodos),
            periodos_por_bloco
        )
    ]

    y_atual = y

    # --------------------------------------------------------
    # CADA BLOCO DE PERÍODOS
    # --------------------------------------------------------

    for numero_bloco, periodos_bloco in enumerate(blocos):

        numero_periodos = len(
            periodos_bloco
        )

        largura_periodo = (
            largura_periodo_disponivel
            / numero_periodos
        )

        # ----------------------------------------------------
        # CABEÇALHO DO BLOCO
        # ----------------------------------------------------

        x_atual = x + margem

        y_inicio = y_atual

        # ----------------------------------------------------
        # LOCAL
        # ----------------------------------------------------

        x1 = x_atual
        x2 = x1 + largura_local

        draw.rectangle(
            [
                x1,
                y_inicio,
                x2,
                y_inicio + altura_cabecalho
            ],
            fill=COR_AZUL_ESCURO,
            outline=COR_BRANCO,
            width=1
        )

        desenhar_texto_centralizado(
            draw,
            "BAIRRO / CIDADE",
            (
                x1,
                y_inicio,
                x2,
                y_inicio + altura_cabecalho
            ),
            fonte_cabecalho,
            COR_BRANCO
        )

        x_atual = x2

        # ----------------------------------------------------
        # PERÍODOS
        # ----------------------------------------------------

        for periodo in periodos_bloco:

            x1 = x_atual
            x2 = x1 + largura_periodo

            draw.rectangle(
                [
                    x1,
                    y_inicio,
                    x2,
                    y_inicio + altura_cabecalho
                ],
                fill=COR_AZUL_ESCURO,
                outline=COR_BRANCO,
                width=1
            )

            desenhar_texto_centralizado(
                draw,
                formatar_periodo(
                    periodo,
                    modo
                ),
                (
                    x1,
                    y_inicio,
                    x2,
                    y_inicio + altura_cabecalho
                ),
                fonte_cabecalho,
                COR_BRANCO
            )

            x_atual = x2

        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        x1 = x_atual
        x2 = x1 + largura_total_coluna

        draw.rectangle(
            [
                x1,
                y_inicio,
                x2,
                y_inicio + altura_cabecalho
            ],
            fill=COR_AZUL_ESCURO,
            outline=COR_BRANCO,
            width=1
        )

        desenhar_texto_centralizado(
            draw,
            "TOTAL",
            (
                x1,
                y_inicio,
                x2,
                y_inicio + altura_cabecalho
            ),
            fonte_cabecalho,
            COR_BRANCO
        )

        # ----------------------------------------------------
        # LINHAS
        # ----------------------------------------------------

        y_linha = (
            y_inicio
            + altura_cabecalho
        )

        for indice, linha in matriz.iterrows():

            fundo = (
                COR_BRANCO
                if indice % 2 == 0
                else COR_CINZA
            )

            x_atual = x + margem

            # --------------------------------------------
            # LOCAL
            # --------------------------------------------

            x1 = x_atual
            x2 = x1 + largura_local

            draw.rectangle(
                [
                    x1,
                    y_linha,
                    x2,
                    y_linha + altura_linha
                ],
                fill=fundo,
                outline=COR_CINZA_BORDA,
                width=1
            )

            texto_local = str(
                linha["LOCAL"]
            )

            texto_local = abreviar_texto(
                texto_local,
                limite=38
            )

            draw.text(
                (
                    x1 + 12,
                    y_linha + 11
                ),
                texto_local,
                font=fonte_local,
                fill=COR_PRETO
            )

            x_atual = x2

            # --------------------------------------------
            # PERÍODOS
            # --------------------------------------------

            for periodo in periodos_bloco:

                x1 = x_atual
                x2 = x1 + largura_periodo

                valor = linha.get(
                    periodo,
                    0
                )

                try:
                    valor = int(valor)
                except Exception:
                    valor = 0

                draw.rectangle(
                    [
                        x1,
                        y_linha,
                        x2,
                        y_linha + altura_linha
                    ],
                    fill=fundo,
                    outline=COR_CINZA_BORDA,
                    width=1
                )

                desenhar_texto_centralizado(
                    draw,
                    formatar_numero(valor),
                    (
                        x1,
                        y_linha,
                        x2,
                        y_linha + altura_linha
                    ),
                    fonte_valor,
                    COR_PRETO
                )

                x_atual = x2

            # --------------------------------------------
            # TOTAL
            # --------------------------------------------

            x1 = x_atual
            x2 = x1 + largura_total_coluna

            valor_total = linha.get(
                "TOTAL",
                0
            )

            try:
                valor_total = int(valor_total)
            except Exception:
                valor_total = 0

            draw.rectangle(
                [
                    x1,
                    y_linha,
                    x2,
                    y_linha + altura_linha
                ],
                fill=COR_AZUL_CLARO,
                outline=COR_CINZA_BORDA,
                width=1
            )

            desenhar_texto_centralizado(
                draw,
                formatar_numero(valor_total),
                (
                    x1,
                    y_linha,
                    x2,
                    y_linha + altura_linha
                ),
                fonte_total,
                COR_AZUL_ESCURO
            )

            y_linha += altura_linha

        # ----------------------------------------------------
        # PRÓXIMO BLOCO
        # ----------------------------------------------------

        y_atual = y_linha

        if numero_bloco < len(blocos) - 1:

            # Espaço discreto entre os blocos.
            y_atual += 35

            # Identificação do bloco seguinte.
            texto_bloco = (
                f"Continuação — "
                f"períodos seguintes"
            )

            draw.text(
                (
                    x + margem,
                    y_atual - 25
                ),
                texto_bloco,
                font=obter_fonte(
                    14,
                    negrito=True
                ),
                fill=COR_CINZA_TEXTO
            )

    return y_atual


# ============================================================
# GERAÇÃO DO RELATÓRIO
# ============================================================

def gerar_painel(
    dados,
    operacao,
    modo,
):
    """
    Gera a imagem final do relatório.

    O relatório é focado exclusivamente na tabela de dados.
    """

    if dados is None or dados.empty:
        return None

    resultado = construir_matriz(
        dados,
        modo
    )

    if resultado is None:
        return None

    matriz, periodos = resultado

    if matriz is None or matriz.empty:
        return None

    # ========================================================
    # DIMENSÕES
    # ========================================================

    largura = 1500

    margem_lateral = 30

    # --------------------------------------------------------
    # Altura do cabeçalho
    # --------------------------------------------------------

    altura_cabecalho = 250

    # --------------------------------------------------------
    # Dimensões da tabela
    # --------------------------------------------------------

    altura_tabela_cabecalho = 52
    altura_linha = 43

    largura_util = (
        largura
        - (25 * 2)
    )

    largura_local = 360
    largura_total_coluna = 110

    largura_periodo_disponivel = (
        largura_util
        - largura_local
        - largura_total_coluna
    )

    largura_minima_periodo = 72

    periodos_por_bloco = max(
        1,
        int(
            largura_periodo_disponivel
            / largura_minima_periodo
        )
    )

    periodos_por_bloco = min(
        periodos_por_bloco,
        14
    )

    quantidade_blocos = max(
        1,
        int(
            np.ceil(
                len(periodos)
                / periodos_por_bloco
            )
        )
    )

    quantidade_linhas = len(matriz)

    altura_por_bloco = (
        altura_tabela_cabecalho
        + (
            quantidade_linhas
            * altura_linha
        )
    )

    espaco_entre_blocos = (
        max(
            0,
            quantidade_blocos - 1
        )
        * 35
    )

    altura = (
        altura_cabecalho
        + (
            quantidade_blocos
            * altura_por_bloco
        )
        + espaco_entre_blocos
        + 50
    )

    altura = max(
        altura,
        600
    )

    # ========================================================
    # CANVAS
    # ========================================================

    imagem = Image.new(
        "RGB",
        (
            largura,
            altura
        ),
        COR_BRANCO
    )

    draw = ImageDraw.Draw(
        imagem
    )

    # ========================================================
    # FONTES
    # ========================================================

    fonte_titulo = obter_fonte(
        34,
        negrito=True
    )

    fonte_subtitulo = obter_fonte(
        20,
        negrito=False
    )

    fonte_periodo = obter_fonte(
        18,
        negrito=True
    )

    fonte_rodape = obter_fonte(
        14,
        negrito=False
    )

    # ========================================================
    # CABEÇALHO
    # ========================================================

    y = 30

    # --------------------------------------------------------
    # LOGO
    # --------------------------------------------------------

    caminho_logo = LOGOS.get(
        operacao
    )

    if caminho_logo:

        try:

            logo = Image.open(
                caminho_logo
            ).convert("RGBA")

            largura_logo_max = 230
            altura_logo_max = 100

            fator = min(
                largura_logo_max / logo.width,
                altura_logo_max / logo.height,
                1
            )

            nova_largura = int(
                logo.width * fator
            )

            nova_altura = int(
                logo.height * fator
            )

            logo = logo.resize(
                (
                    nova_largura,
                    nova_altura
                ),
                Image.LANCZOS
            )

            imagem.paste(
                logo,
                (
                    margem_lateral,
                    y
                ),
                logo
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = TITULOS.get(
        operacao,
        "Relatório de Falta de Água - COI"
    )

    draw.text(
        (
            300,
            42
        ),
        titulo,
        font=fonte_titulo,
        fill=COR_AZUL_ESCURO
    )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    empresa = NOMES_EMPRESAS.get(
        operacao,
        ""
    )

    draw.text(
        (
            300,
            92
        ),
        f"Empresa: {empresa}",
        font=fonte_subtitulo,
        fill=COR_CINZA_TEXTO
    )

    # --------------------------------------------------------
    # PERÍODO
    # --------------------------------------------------------

    periodo_texto = texto_cabecalho_periodo(
        dados
    )

    draw.text(
        (
            300,
            130
        ),
        f"Período: {periodo_texto}",
        font=fonte_periodo,
        fill=COR_AZUL
    )

    # --------------------------------------------------------
    # TIPO DE VISUALIZAÇÃO
    # --------------------------------------------------------

    draw.text(
        (
            300,
            165
        ),
        f"Visualização: {modo}",
        font=fonte_subtitulo,
        fill=COR_CINZA_TEXTO
    )

    # ========================================================
    # LINHA DIVISÓRIA
    # ========================================================

    draw.line(
        [
            margem_lateral,
            220,
            largura - margem_lateral,
            220
        ],
        fill=COR_CINZA_BORDA,
        width=2
    )

    # ========================================================
    # TABELA
    # ========================================================

    y_tabela = 240

    desenhar_tabela(
        draw=draw,
        matriz=matriz,
        periodos=periodos,
        modo=modo,
        x=0,
        y=y_tabela,
        largura_total=largura
    )

    # ========================================================
    # RODAPÉ
    # ========================================================

    y_rodape = (
        altura
        - 30
    )

    texto_rodape = (
        "Controle Operacional Integrado - COI"
    )

    largura_rodape, altura_rodape = medir_texto(
        draw,
        texto_rodape,
        fonte_rodape
    )

    draw.text(
        (
            (
                largura
                - largura_rodape
            ) / 2,
            y_rodape
        ),
        texto_rodape,
        font=fonte_rodape,
        fill=COR_CINZA_TEXTO
    )

    return imagem


# ============================================================
# TÍTULO DA PÁGINA
# ============================================================

st.markdown(
    '<div class="titulo-principal">'
    'Relatório de Falta de Água - COI'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitulo">'
    'Geração de relatório operacional a partir das O.S. '
    'de Falta de Água.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# SELEÇÃO DA OPERAÇÃO
# ============================================================

st.markdown("### Operação")

operacao = st.radio(
    "Selecione a operação:",
    [
        "API",
        "THE",
        "TIM",
    ],
    format_func=lambda x: NOMES_EMPRESAS.get(
        x,
        x
    ),
    horizontal=True
)


# ============================================================
# UPLOAD
# ============================================================

st.markdown("### Arquivo de dados")

arquivo = st.file_uploader(
    "Envie a planilha de O.S. de Falta de Água",
    type=[
        "xlsx",
        "xls",
        "xlsb"
    ],
    key=f"upload_{operacao}"
)


# ============================================================
# MODO
# ============================================================

st.markdown("### Visualização")

modo = st.radio(
    "Como deseja visualizar os dados?",
    [
        "Por dia",
        "Por mês",
    ],
    horizontal=True
)


# ============================================================
# PROCESSAMENTO
# ============================================================

if arquivo is not None:

    dados_brutos = ler_planilha(
        arquivo
    )

    if dados_brutos is not None:

        dados = preparar_dados(
            dados_brutos,
            operacao
        )

        if dados is not None and not dados.empty:

            # =================================================
            # BASE - APENAS API
            # =================================================

            base_selecionada = None

            if operacao == "API":

                bases_disponiveis = sorted(
                    [
                        base
                        for base in dados["_BASE"]
                        .dropna()
                        .astype(str)
                        .unique()
                        if base.strip()
                        and base != "Não classificada"
                    ]
                )

                if bases_disponiveis:

                    st.markdown(
                        "### Base"
                    )

                    opcoes_base = [
                        "Todas as bases"
                    ] + bases_disponiveis

                    base_selecionada = st.selectbox(
                        "Selecione a base:",
                        opcoes_base
                    )

                    if (
                        base_selecionada
                        != "Todas as bases"
                    ):

                        dados = dados[
                            dados["_BASE"]
                            == base_selecionada
                        ].copy()

                else:

                    st.info(
                        "Não foi possível identificar "
                        "as bases através do mapeamento "
                        "de cidades."
                    )

            # =================================================
            # RESUMO SIMPLES
            # =================================================

            if dados.empty:

                st.warning(
                    "Não existem dados para a seleção realizada."
                )

            else:

                st.success(
                    f"{len(dados):,} registros encontrados."
                    .replace(",", ".")
                )

                # =================================================
                # BOTÃO DE GERAÇÃO
                # =================================================

                if st.button(
                    "Gerar relatório",
                    type="primary"
                ):

                    with st.spinner(
                        "Gerando relatório..."
                    ):

                        imagem = gerar_painel(
                            dados=dados,
                            operacao=operacao,
                            modo=modo
                        )

                    if imagem is not None:

                        st.session_state[
                            "relatorio_fa"
                        ] = imagem

                        st.session_state[
                            "relatorio_operacao"
                        ] = operacao

                        st.session_state[
                            "relatorio_modo"
                        ] = modo

                    else:

                        st.error(
                            "Não foi possível gerar "
                            "o relatório."
                        )


# ============================================================
# EXIBIÇÃO DO RELATÓRIO
# ============================================================

if (
    "relatorio_fa"
    in st.session_state
):

    imagem_relatorio = (
        st.session_state[
            "relatorio_fa"
        ]
    )

    operacao_relatorio = (
        st.session_state.get(
            "relatorio_operacao",
            operacao
        )
    )

    modo_relatorio = (
        st.session_state.get(
            "relatorio_modo",
            modo
        )
    )

    st.markdown("---")

    st.markdown(
        "### Relatório gerado"
    )

    st.image(
        imagem_relatorio,
        use_container_width=True
    )

    # =========================================================
    # DOWNLOAD
    # =========================================================

    buffer = io.BytesIO()

    imagem_relatorio.save(
        buffer,
        format="PNG"
    )

    buffer.seek(0)

    nome_arquivo = (
        f"relatorio_falta_agua_"
        f"{operacao_relatorio.lower()}_"
        f"{modo_relatorio.lower().replace(' ', '_')}.png"
    )

    st.download_button(
        label="Baixar relatório em PNG",
        data=buffer.getvalue(),
        file_name=nome_arquivo,
        mime="image/png"
    )
