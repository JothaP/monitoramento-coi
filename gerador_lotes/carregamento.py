import hashlib
import io

import pandas as pd
import streamlit as st

from .estado import definir_base


# ============================================================
# ASSINATURA DOS ARQUIVOS
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

    return tuple(sorted(assinaturas))


# ============================================================
# LEITURA DO EXCEL
# ============================================================

def ler_excel(arquivo):

    if arquivo is None:
        return None

    extensao = arquivo.name.lower()

    if not extensao.endswith((".xlsx", ".xlsm")):

        raise ValueError(
            f"O arquivo '{arquivo.name}' não é um Excel válido. "
            "Utilize .xlsx ou .xlsm."
        )

    conteudo = arquivo.getvalue()

    df = pd.read_excel(
        io.BytesIO(conteudo),
        engine="openpyxl"
    )

    # Limpeza dos nomes das colunas
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    return df


# ============================================================
# REMOVER LINHAS COMPLETAMENTE VAZIAS
# ============================================================

def remover_linhas_vazias(df):

    if df is None or df.empty:
        return df

    df = df.copy()

    mascara = df.apply(
        lambda linha: all(
            pd.isna(valor) or str(valor).strip() == ""
            for valor in linha
        ),
        axis=1
    )

    return df.loc[~mascara].reset_index(drop=True)


# ============================================================
# CONSOLIDAR ARQUIVOS
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

    df_final = pd.concat(
        dfs,
        ignore_index=True,
        sort=False
    )

    df_final = remover_linhas_vazias(df_final)

    # Somente duplicações EXATAS
    df_final = df_final.drop_duplicates(
        keep="first"
    ).reset_index(drop=True)

    return df_final


# ============================================================
# PROCESSAR UPLOAD
# ============================================================

def processar_upload_multiplo(
    nome_base,
    arquivos
):

    if not arquivos:
        return False

    assinatura = assinatura_arquivos(arquivos)

    assinatura_anterior = st.session_state.get(
        f"assinatura_{nome_base}"
    )

    # --------------------------------------------------------
    # ARQUIVOS JÁ PROCESSADOS
    # --------------------------------------------------------

    if assinatura == assinatura_anterior:

        return False

    # --------------------------------------------------------
    # NOVOS ARQUIVOS
    # --------------------------------------------------------

    df = consolidar_arquivos(arquivos)

    if df is None or df.empty:

        st.warning(
            f"Nenhum dado válido encontrado para a base "
            f"'{nome_base}'."
        )

        return False

    definir_base(
        nome=nome_base,
        dataframe=df,
        arquivos=[arquivo.name for arquivo in arquivos],
        assinatura=assinatura
    )

    return True


# ============================================================
# PROCESSAR UPLOAD ÚNICO
# ============================================================

def processar_upload_unico(
    nome_base,
    arquivo
):

    if arquivo is None:
        return False

    assinatura = assinatura_arquivo(arquivo)

    assinatura_anterior = st.session_state.get(
        f"assinatura_{nome_base}"
    )

    # Já foi carregado
    if assinatura == assinatura_anterior:

        return False

    df = ler_excel(arquivo)

    if df is None or df.empty:

        st.warning(
            f"O arquivo '{arquivo.name}' não contém dados."
        )

        return False

    df = remover_linhas_vazias(df)

    definir_base(
        nome=nome_base,
        dataframe=df,
        arquivos=[arquivo.name],
        assinatura=assinatura
    )

    return True