import hashlib
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
