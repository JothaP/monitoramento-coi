"""SAI — importacao semiautomatica de medicoes de pressao.

Origem: arquivos XLSX/CSV exportados e sincronizados no OneDrive corporativo.
Destino: worksheet 'baixa_pressao' ja utilizada pelo Modulo 1, mais o diario
         'sai_sync_pressao' no mesmo Google Sheets.

Execucao: GitHub Actions (cron de 30 em 30 minutos) ou manual para diagnostico.
Este codigo NAO precisa ser executado no notebook do analista.

Nunca enviar credenciais, planilhas brutas ou dados de clientes ao GitHub.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd

COLUNAS_SAI = [
    "ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude",
    "Pressao_MCA", "Observacao", "Matricula",
]
COLUNAS_DIARIO = [
    "DataHora", "ArquivoID", "VersaoETag", "Arquivo", "Origem",
    "Elegiveis", "Inseridos", "JaExistentes", "SemPressaoNumerica",
    "Status", "Detalhes",
]
FUSO = ZoneInfo("America/Sao_Paulo")
TERMOS_EXCLUSAO = ("vazamento", "obstrucao", "obstrução", "entupido", "quebrado")
TERMOS_BAIXA = ("baixa pressão", "baixa pressao", "pouca água", "sem pressão", "fraca")


def normalizar_cabecalho(valor: object) -> str:
    return str(valor or "").strip().lower()


def encontrar_coluna(df: pd.DataFrame, opcoes: list[str]) -> str | None:
    """Mesma busca por cabecalhos usada no Colab, sem depender do Colab."""
    mapa = {normalizar_cabecalho(c): c for c in df.columns}
    return next((mapa[c] for opcao in opcoes if (c := normalizar_cabecalho(opcao)) in mapa), None)


def texto_limpo(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    s = str(valor).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def numero(valor: object, permitir_negativo: bool = False) -> float | None:
    """Replica o conversor do Colab: numero simples, sem sufixo MCA."""
    txt = texto_limpo(valor).replace(",", ".")
    if not txt:
        return None
    try:
        n = float(txt)
        if (n >= 0 or permitir_negativo) and n != float("inf") and n != float("-inf"):
            return n
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def normalizar_localidade(valor: str, padrao: str = "") -> str:
    raw = texto_limpo(valor) or padrao
    s = unicodedata.normalize("NFKD", raw)
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def parse_data(valor: object) -> str | None:
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    txt = texto_limpo(valor)
    for formato in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(txt, formato).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def data_pelo_nome(nome: str) -> str | None:
    # Exemplo validado: Atividades-AGUAS DE TERESINA_29_10_26.xlsx
    for padrao in (r"(?<!\d)(\d{2})[_-](\d{2})[_-](\d{4})(?!\d)",
                   r"(?<!\d)(\d{2})[_-](\d{2})[_-](\d{2})(?!\d)"):
        achou = re.search(padrao, nome)
        if achou:
            return parse_data("/".join(achou.groups()))
    return None


def analisar_parecer(row: pd.Series, col_pressao: str | None, col_parecer: str | None):
    """Mesma precedencia de regras do conversor fornecido pelo usuario."""
    p = numero(row.get(col_pressao)) if col_pressao else None
    parecer = texto_limpo(row.get(col_parecer)).lower() if col_parecer else ""
    if parecer:
        if any(termo in parecer for termo in TERMOS_EXCLUSAO):
            return None, False, True
        if p is None:
            achou = re.search(r"([\d]+[.,]?\d*)\s*(?:mca)", parecer, flags=re.I)
            if achou:
                p = numero(achou.group(1))
    mencao_baixa = any(termo in parecer for termo in TERMOS_BAIXA)
    return p, mencao_baixa, False


@dataclass
class Resultado:
    origem: int
    linhas: list[list]
    sem_pressao_numerica: int = 0
    sem_coordenadas: int = 0
    sem_data: int = 0
    excluidas_ou_fora_da_faixa: int = 0


def converter_bruta(df: pd.DataFrame, nome_arquivo: str) -> Resultado:
    """Converte a exportacao original; sem exportacao intermediaria do Colab.

    Dados sem MCA numerico NAO viram 0 MCA automaticamente: ficam de fora para
    evitar transformar uma mencao verbal em medicao que nao ocorreu.
    """
    col_mun = encontrar_coluna(df, ["Cidade", "Município", "Municipio"])
    col_bairro = encontrar_coluna(df, ["Bairro"])
    col_lat = encontrar_coluna(df, ["Latitude", "Lat"])
    col_lon = encontrar_coluna(df, ["Longitude", "Lon", "Long"])
    col_pressao = encontrar_coluna(df, ["Qual A Pressão Da Rede (Mca)", "Pressao_MCA", "Pressão (MCA)"])
    col_parecer = encontrar_coluna(df, ["Parecer De Campo", "Parecer de Campo"])
    col_matricula = encontrar_coluna(df, [
        "Matrícula", "Matricula", "Matrícula do Imóvel", "Matricula do Imovel",
        "Nr Matricula", "Número da Matrícula", "Numero da Matricula", "Matrícula do Cliente",
    ])
    col_data = encontrar_coluna(df, ["Data", "Data da atividade", "Data da Atividade"])
    col_protocolo = encontrar_coluna(df, [
        "Cód. Protocolo Origem", "Cod. Protocolo Origem", "Protocolo Origem", "Protocolo",
    ])
    if not col_bairro or not col_lat or not col_lon or not (col_pressao or col_parecer):
        raise ValueError("A planilha não possui as colunas essenciais: Bairro, Latitude, Longitude e Pressão/Parecer.")
    data_fallback = data_pelo_nome(nome_arquivo)
    resultado = Resultado(origem=len(df), linhas=[])
    for _, row in df.iterrows():
        bairro = texto_limpo(row.get(col_bairro))
        if not bairro:
            resultado.excluidas_ou_fora_da_faixa += 1
            continue
        pressao, mencao_baixa, excluir = analisar_parecer(row, col_pressao, col_parecer)
        if excluir:
            resultado.excluidas_ou_fora_da_faixa += 1
            continue
        if pressao is None and mencao_baixa:
            resultado.sem_pressao_numerica += 1
            continue
        if pressao is None or not (pressao < 10 or pressao > 15):
            resultado.excluidas_ou_fora_da_faixa += 1
            continue
        lat = numero(row.get(col_lat), permitir_negativo=True)
        lon = numero(row.get(col_lon), permitir_negativo=True)
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or lat == 0 or lon == 0:
            resultado.sem_coordenadas += 1
            continue
        data = parse_data(row.get(col_data)) if col_data else None
        data = data or data_fallback
        if data is None:
            resultado.sem_data += 1
            continue
        mun = normalizar_localidade(row.get(col_mun), "TERESINA") if col_mun else "TERESINA"
        bairro = normalizar_localidade(bairro)
        matricula = texto_limpo(row.get(col_matricula)) if col_matricula else ""
        # O Colab deixa a observacao vazia quando existe valor de MCA.
        # O protocolo de origem nao e incluido na planilha operacional.
        _ = col_protocolo  # preservado para futuras ampliacoes auditadas
        resultado.linhas.append([
            uuid.uuid4().hex[:8].upper(), data, mun, bairro,
            round(lat, 6), round(lon, 6), round(pressao, 2), "", matricula,
        ])
    if not resultado.linhas and resultado.sem_data:
        raise ValueError("Nenhuma data válida na planilha ou nome. Arquivo não importado para evitar data incorreta.")
    return resultado


def ler_arquivo(nome: str, conteudo: bytes) -> pd.DataFrame:
    extensao = Path(nome).suffix.lower()
    buffer = io.BytesIO(conteudo)
    if extensao == ".xlsx":
        return pd.read_excel(buffer, dtype=str, engine="openpyxl")
    if extensao == ".csv":
        # Alguns sistemas exportam CSV com separador ';' e codificacao Windows.
        for codificacao in ("utf-8-sig", "cp1252", "latin1"):
            try:
                return pd.read_csv(io.BytesIO(conteudo), sep=None, engine="python", dtype=str, encoding=codificacao)
            except UnicodeDecodeError:
                continue
    raise ValueError("Tipo de arquivo não aceito. Utilize XLSX ou CSV.")


def chave_medicao(linha: list) -> tuple[str, ...]:
    """Equivalente a chave de duplicidade do adicionar_lote_seguro() do Modulo 1."""
    return (
        parse_data(linha[1]) or texto_limpo(linha[1]),
        normalizar_localidade(linha[2]).lower(),
        normalizar_localidade(linha[3]).lower(),
        f"{float(str(linha[4]).replace(',', '.')):.6f}",
        f"{float(str(linha[5]).replace(',', '.')):.6f}",
    )


def filtrar_ja_existentes(linhas: list[list], linhas_sheet: list[list]) -> tuple[list[list], int]:
    existentes: set[tuple[str, ...]] = set()
    for r in linhas_sheet:
        if len(r) < 6:
            continue
        try:
            existentes.add(chave_medicao(r))
        except (ValueError, TypeError):
            continue
    novos: list[list] = []
    repetidos = 0
    for r in linhas:
        k = chave_medicao(r)
        if k not in existentes:
            novos.append(r)
            existentes.add(k)
        else:
            repetidos += 1
    return novos, repetidos


def google_sheets():
    """Credenciais de conta de servico, independentes do Streamlit Cloud."""
    import gspread
    from google.oauth2.service_account import Credentials
    raw = os.environ["GCP_SERVICE_ACCOUNT_JSON"].strip()
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
    ])
    spreadsheet_id = os.environ["SAI_SHEET_ID"].strip()
    return gspread.authorize(creds).open_by_key(spreadsheet_id)


def configurar_destino(spreadsheet):
    """Exige formato compativel com o importador atual; nunca migra cabecalhos sozinho."""
    ws = spreadsheet.worksheet("baixa_pressao")
    primeira = ws.row_values(1)
    if [normalizar_cabecalho(x) for x in primeira[:9]] != [normalizar_cabecalho(x) for x in COLUNAS_SAI]:
        raise ValueError("A aba baixa_pressao não possui as nove colunas esperadas. Nenhuma alteração feita.")
    try:
        diario = spreadsheet.worksheet("sai_sync_pressao")
        cab = diario.row_values(1)
        if [normalizar_cabecalho(x) for x in cab] != [normalizar_cabecalho(x) for x in COLUNAS_DIARIO]:
            raise ValueError("A aba sai_sync_pressao possui cabeçalho inesperado.")
    except Exception as erro:
        if erro.__class__.__name__ != "WorksheetNotFound":
            raise
        diario = spreadsheet.add_worksheet(title="sai_sync_pressao", rows=1000, cols=len(COLUNAS_DIARIO))
        diario.append_row(COLUNAS_DIARIO, value_input_option="RAW")
    return ws, diario


def logar(diario, *, item_id, etag, nome, resumo: Resultado, inseridos, repetidos, status, detalhes=""):
    agora = datetime.now(FUSO).strftime("%d/%m/%Y %H:%M:%S")
    diario.append_row([
        agora, item_id, etag, nome, resumo.origem, len(resumo.linhas),
        inseridos, repetidos, resumo.sem_pressao_numerica, status,
        str(detalhes)[:350],
    ], value_input_option="RAW")


def arquivos_processados(diario) -> set[tuple[str, str]]:
    valores = diario.get_all_values()
    return {
        (r[1], r[2]) for r in valores[1:]
        if len(r) > 9 and r[9] in {"IMPORTADO", "SEM_NOVOS", "SEM_ELEGIVEIS"}
    }


def registrar_lote(ws, resumo: Resultado) -> tuple[int, int]:
    valores = ws.get_all_values()
    # get_all_values retorna cabecalho mais linhas; indices 0..8 conforme COLUNAS_SAI.
    novos, repetidos = filtrar_ja_existentes(resumo.linhas, valores[1:])
    for inicio in range(0, len(novos), 400):
        ws.append_rows(novos[inicio:inicio + 400], value_input_option="USER_ENTERED")
    return len(novos), repetidos


def token_microsoft(session):
    import requests
    tenant = os.environ["MS_TENANT_ID"].strip()
    payload = {
        "client_id": os.environ["MS_CLIENT_ID"],
        "client_secret": os.environ["MS_CLIENT_SECRET"],
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default",
    }
    r = session.post(f"https://login.microsoftonline.com/{quote(tenant, safe='')}/oauth2/v2.0/token", data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def graph_get(session, token: str, endpoint: str):
    r = session.get(endpoint, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    return r.json()


def listar_arquivos_onedrive(session, token: str) -> list[dict]:
    drive = os.environ["MS_DRIVE_ID"].strip()
    pasta_id = os.environ.get("MS_FOLDER_ID", "").strip()
    pasta_caminho = os.environ.get("MS_FOLDER_PATH", "SAI/Medicoes_Pressao/Entrada").strip(" /")
    base = f"https://graph.microsoft.com/v1.0/drives/{quote(drive, safe='')}"
    if not pasta_id:
        caminho_codificado = "/".join(quote(p, safe="") for p in pasta_caminho.split("/"))
        pasta = graph_get(session, token, f"{base}/root:/{caminho_codificado}")
        pasta_id = pasta["id"]
    url = f"{base}/items/{quote(pasta_id, safe='')}/children?$top=200"
    saida = []
    while url:
        pagina = graph_get(session, token, url)
        for item in pagina.get("value", []):
            nome = item.get("name", "")
            if "file" in item and nome.lower().endswith((".xlsx", ".csv")) and not nome.startswith("~$"):
                saida.append(item)
        url = pagina.get("@odata.nextLink")
    return saida


def baixar_arquivo_onedrive(session, token, item: dict):
    drive = os.environ["MS_DRIVE_ID"].strip()
    item_id = item["id"]
    url = f"https://graph.microsoft.com/v1.0/drives/{quote(drive, safe='')}/items/{quote(item_id, safe='')}/content"
    resposta = session.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    resposta.raise_for_status()
    limite = int(os.getenv("SAI_MAX_ARQUIVO_MB", "30")) * 1024 * 1024
    if len(resposta.content) > limite:
        raise ValueError("Arquivo excede o limite configurado para processamento.")
    return resposta.content


def executar_agendado():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Verifica o acesso ao destino antes de tentar ler dados sensiveis do OneDrive.
    planilha = google_sheets()
    ws, diario = configurar_destino(planilha)
    finalizados = arquivos_processados(diario)
    sessao = requests.Session()
    sessao.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
    )))
    token = token_microsoft(sessao)
    arquivos = listar_arquivos_onedrive(sessao, token)
    pendentes = [a for a in arquivos if (a["id"], a.get("eTag", "")) not in finalizados]
    pendentes.sort(key=lambda a: (a.get("lastModifiedDateTime", ""), a.get("name", "")))
    limite = int(os.getenv("SAI_MAX_ARQUIVOS_POR_EXECUCAO", "20"))
    print(f"SAI: {len(arquivos)} arquivo(s) encontrados; {len(pendentes)} pendente(s).")
    falhas = 0
    for item in pendentes[:limite]:
        nome = item.get("name", "")
        etag = item.get("eTag", "")
        try:
            conteudo = baixar_arquivo_onedrive(sessao, token, item)
            dados = ler_arquivo(nome, conteudo)
            resumo = converter_bruta(dados, nome)
            if resumo.linhas:
                inseridos, repetidos = registrar_lote(ws, resumo)
                status = "IMPORTADO" if inseridos else "SEM_NOVOS"
            else:
                inseridos, repetidos, status = 0, 0, "SEM_ELEGIVEIS"
            detalhes = f"Coordenadas invalidas: {resumo.sem_coordenadas}; sem data: {resumo.sem_data}"
            logar(diario, item_id=item["id"], etag=etag, nome=nome, resumo=resumo,
                  inseridos=inseridos, repetidos=repetidos, status=status, detalhes=detalhes)
            print(f"{nome}: {status} | origem={resumo.origem}, elegiveis={len(resumo.linhas)}, novos={inseridos}.")
        except Exception as e:
            falhas += 1
            # Não registrar pareceres, matrículas, coordenadas ou conteúdo pessoal.
            # Falhas não são consideradas processadas: haverá nova tentativa no
            # próximo agendamento. O diário permite detectar o problema no SAI.
            print(f"Falha ao processar '{nome}': {e.__class__.__name__}", file=sys.stderr)
            try:
                logar(diario, item_id=item["id"], etag=etag, nome=nome,
                      resumo=Resultado(origem=0, linhas=[]), inseridos=0,
                      repetidos=0, status="ERRO", detalhes=e.__class__.__name__)
            except Exception:
                print("Não foi possível registrar a falha na aba de auditoria.", file=sys.stderr)
    if falhas:
        raise RuntimeError(f"Foram detectadas {falhas} falha(s) de importacao. Verifique os logs do workflow.")


def executar_validacao_local(nome: str):
    caminho = Path(nome)
    resumo = converter_bruta(ler_arquivo(caminho.name, caminho.read_bytes()), caminho.name)
    print(f"Validação local: origem={resumo.origem}; elegíveis={len(resumo.linhas)}; "
          f"sem MCA numérico={resumo.sem_pressao_numerica}; "
          f"sem coordenadas={resumo.sem_coordenadas}; sem data={resumo.sem_data}.")
    # Nunca salva conteúdo sensível nem apresenta registros em logs.
    return resumo


def main():
    p = argparse.ArgumentParser(description="Sincronizar medições do SAI: OneDrive → Google Sheets")
    p.add_argument("--arquivo-local", help="Arquivo bruto para validação local, sem upload ou acesso externo")
    a = p.parse_args()
    if a.arquivo_local:
        executar_validacao_local(a.arquivo_local)
    else:
        executar_agendado()


if __name__ == "__main__":
    main()
