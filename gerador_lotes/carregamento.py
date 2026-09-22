import hashlib
import io

import pandas as pd
import streamlit as st

from .estado import (
    definir_base,
    definir_modo_operacao,
)


# ============================================================
# ASSINATURA DE UM ARQUIVO
# ============================================================

def assinatura_arquivo(arquivo):

    if arquivo is None:
        return None

    conteudo = arquivo.getvalue()

    return (
        arquivo.name,
        len(conteudo),
        hashlib.md5(conteudo).hexdigest()
    )


# ============================================================
# ASSINATURA DE VÁRIOS ARQUIVOS
# ============================================================

def assinatura_arquivos(arquivos):

    if not arquivos:
        return None

    assinaturas = []

    for arquivo in arquivos:

        conteudo = arquivo.getvalue()

        assinaturas.append(
            (
                arquivo.name,
                len(conteudo),
                hashlib.md5(conteudo).hexdigest()
            )
        )

    return tuple(
        sorted(assinaturas)
    )


# ============================================================
# LEITURA EXCEL
# ============================================================

def ler_excel(arquivo):

    if arquivo is None:
        return None

    nome = arquivo.name.lower()

    if not nome.endswith(
        (".xlsx", ".xlsm")
    ):

        raise ValueError(
            f"O arquivo '{arquivo.name}' "
            "não é um Excel válido. "
            "Utilize .xlsx ou .xlsm."
        )

    conteudo = arquivo.getvalue()

    if not conteudo:

        raise ValueError(
            f"O arquivo '{arquivo.name}' "
            "está vazio."
        )

    df = pd.read_excel(
        io.BytesIO(conteudo),
        engine="openpyxl"
    )

    # --------------------------------------------------------
    # PRESERVA TODAS AS COLUNAS
    # Apenas remove espaços extras dos nomes.
    # --------------------------------------------------------

    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    return df


# ============================================================
# REMOVER LINHAS VAZIAS
# ============================================================

def remover_linhas_vazias(df):

    if df is None or df.empty:
        return df

    df = df.copy()

    mascara_vazia = df.apply(
        lambda linha: all(
            pd.isna(valor)
            or str(valor).strip() == ""
            for valor in linha
        ),
        axis=1
    )

    return df.loc[
        ~mascara_vazia
    ].reset_index(drop=True)


# ============================================================
# CONSOLIDAR
# ============================================================

def consolidar_arquivos(arquivos):

    if not arquivos:
        return None

    dfs = []

    for arquivo in arquivos:

        df = ler_excel(arquivo)

        if df is not None and not df.empty:

            dfs.append(df)

    if not dfs:
        return None

    # --------------------------------------------------------
    # CONCATENAÇÃO
    #
    # sort=False preserva a estrutura das colunas.
    # Colunas ausentes em um arquivo são criadas no resultado.
    # --------------------------------------------------------

    df_final = pd.concat(
        dfs,
        ignore_index=True,
        sort=False
    )

    df_final = remover_linhas_vazias(
        df_final
    )

    # --------------------------------------------------------
    # SOMENTE DUPLICAÇÕES EXATAS
    # --------------------------------------------------------

    df_final = df_final.drop_duplicates(
        keep="first"
    ).reset_index(drop=True)

    return df_final


# ============================================================
# UPLOAD MÚLTIPLO
# ============================================================

def processar_upload_multiplo(
    nome_base,
    arquivos
):

    if not arquivos:
        return False

    assinatura = assinatura_arquivos(
        arquivos
    )

    assinatura_anterior = (
        st.session_state.get(
            f"assinatura_{nome_base}"
        )
    )

    # --------------------------------------------------------
    # MESMO ARQUIVO / MESMO CONJUNTO
    # --------------------------------------------------------

    if assinatura == assinatura_anterior:

        return False

    # --------------------------------------------------------
    # NOVO CONJUNTO
    # --------------------------------------------------------

    df = consolidar_arquivos(
        arquivos
    )

    if df is None or df.empty:

        st.warning(
            f"Nenhum dado válido encontrado "
            f"para a base '{nome_base}'."
        )

        return False

    definir_base(
        nome=nome_base,
        dataframe=df,
        arquivos=[
            arquivo.name
            for arquivo in arquivos
        ],
        assinatura=assinatura
    )

    # --------------------------------------------------------
    # SE FOR API OU THE E NÃO HOUVER MODO DEFINIDO,
    # DEFINE AUTOMATICAMENTE.
    # --------------------------------------------------------

    if nome_base.lower() == "api":

        if st.session_state.get(
            "modo_operacao"
        ) is None:

            definir_modo_operacao("API")

    elif nome_base.lower() == "the":

        if st.session_state.get(
            "modo_operacao"
        ) is None:

            definir_modo_operacao("THE")

    return True


# ============================================================
# UPLOAD ÚNICO
# ============================================================

def processar_upload_unico(
    nome_base,
    arquivo
):

    if arquivo is None:
        return False

    assinatura = assinatura_arquivo(
        arquivo
    )

    assinatura_anterior = (
        st.session_state.get(
            f"assinatura_{nome_base}"
        )
    )

    # --------------------------------------------------------
    # JÁ CARREGADO
    # --------------------------------------------------------

    if assinatura == assinatura_anterior:

        return False

    df = ler_excel(
        arquivo
    )

    if df is None or df.empty:

        st.warning(
            f"O arquivo '{arquivo.name}' "
            "não contém dados."
        )

        return False

    df = remover_linhas_vazias(
        df
    )

    if df.empty:

        st.warning(
            f"O arquivo '{arquivo.name}' "
            "não contém dados válidos."
        )

        return False

    definir_base(
        nome=nome_base,
        dataframe=df,
        arquivos=[
            arquivo.name
        ],
        assinatura=assinatura
    )

    # --------------------------------------------------------
    # DEFINE MODO AUTOMATICAMENTE
    # --------------------------------------------------------

    if nome_base.lower() == "api":

        if st.session_state.get(
            "modo_operacao"
        ) is None:

            definir_modo_operacao("API")

    elif nome_base.lower() == "the":

        if st.session_state.get(
            "modo_operacao"
        ) is None:

            definir_modo_operacao("THE")

    return True
