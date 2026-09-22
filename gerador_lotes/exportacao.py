import io

import pandas as pd


# ============================================================
# GERAR EXCEL
# ============================================================

def dataframe_para_excel(df):

    if df is None or df.empty:
        return None

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Resultado"
        )

    buffer.seek(0)

    return buffer.getvalue()