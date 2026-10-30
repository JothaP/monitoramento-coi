"""SAI — importacao semiautomatica de medicoes de pressao.

Origem: XLSX/CSV recebidos em pasta privada do Google Drive via Power Automate.
Destino: worksheet 'baixa_pressao' ja utilizada pelo Modulo 1, mais o diario
         'sai_sync_pressao' no mesmo Google Sheets.

Execução: serviço Python do SAI no GitHub Actions a cada 30 minutos; não depende do app aberto.
Este codigo NAO precisa ser executado no notebook do analista.

Nunca enviar credenciais, planilhas brutas ou dados de clientes ao repositório GitHub.
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
from zoneinfo import ZoneInfo

import pandas as pd

COLUNAS_SAI = [
    "ID", "Data", "Municipio", "Bairro", "Latitude", "Longitude",
    "Pressao_MCA", "Observacao", "Matricula",
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




def conectar_google():
    """Usa a mesma conta de serviço do SAI; não escreve arquivos no Drive."""
    import gspread
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    credenciais = json.loads(os.environ['SAI_GCP_JSON'])
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.readonly',
    ]
    cred = Credentials.from_service_account_info(credenciais, scopes=scopes)
    sheets = gspread.authorize(cred).open_by_key(os.environ['SAI_SHEET_ID'])
    drive = build('drive', 'v3', credentials=cred, cache_discovery=False)
    return sheets, drive


COLUNAS_DIARIO = [
    'DataHora', 'ArquivoID', 'MD5Drive', 'HashSHA256', 'Arquivo',
    'LinhasOrigem', 'Elegiveis', 'Inseridos', 'JaExistentes',
    'SemPressaoNumerica', 'Status', 'Detalhes',
]
SUCESSOS = {'IMPORTADO', 'SEM_NOVOS', 'SEM_ELEGIVEIS', 'SEM_ALTERACOES'}


def abrir_abas(spreadsheet, dry_run=False):
    """Em homologação, nunca cria abas nem modifica a planilha."""
    from gspread.exceptions import WorksheetNotFound
    ws = spreadsheet.worksheet('baixa_pressao')
    cab = ws.row_values(1)
    if [normalizar_cabecalho(x) for x in cab[:len(COLUNAS_SAI)]] != [
        normalizar_cabecalho(x) for x in COLUNAS_SAI
    ]:
        raise ValueError('Cabeçalho de baixa_pressao divergente; nenhuma importação realizada')
    try:
        diario = spreadsheet.worksheet('sai_sync_pressao')
    except WorksheetNotFound:
        if dry_run:
            diario = None
        else:
            diario = spreadsheet.add_worksheet(title='sai_sync_pressao', rows=1000, cols=12)
            diario.append_row(COLUNAS_DIARIO, value_input_option='RAW')
    else:
        if diario.row_values(1) != COLUNAS_DIARIO:
            raise ValueError('Cabeçalho de sai_sync_pressao divergente; verifique a aba')
    return ws, diario


def ler_diario(diario):
    if diario is None:
        return set(), set()
    dados = diario.get_all_values()
    finalizados = set()
    hashes_finalizados = set()
    for linha in dados[1:]:
        if len(linha) > 10 and linha[10] in SUCESSOS:
            finalizados.add((linha[1], linha[2]))
            hashes_finalizados.add(linha[3])
    return finalizados, hashes_finalizados


def logar(diario, *, meta, hash_sha, resumo, novos, repetidos, status, detalhes=''):
    now = datetime.now(FUSO).strftime('%d/%m/%Y %H:%M:%S')
    diario.append_row([
        now, meta['id'], meta.get('md5Checksum') or meta.get('modifiedTime',''),
        hash_sha, meta['name'], resumo.origem, len(resumo.linhas),
        novos, repetidos, resumo.sem_pressao_numerica, status, detalhes[:350],
    ], value_input_option='RAW')


def listar_arquivos_drive(drive, folder_id):
    """Só XLSX/CSV reais da pasta; não lê planilhas Google nativas."""
    q = "'{}' in parents and trashed = false".format(folder_id.replace("'", "\\'"))
    pagina = None
    dados = []
    while True:
        resposta = drive.files().list(
            q=q, fields='nextPageToken,files(id,name,size,mimeType,md5Checksum,modifiedTime)',
            pageSize=100, pageToken=pagina, supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for item in resposta.get('files', []):
            name = item.get('name', '')
            if name.lower().endswith(('.xlsx', '.csv')) and not name.startswith('~$'):
                dados.append(item)
        pagina = resposta.get('nextPageToken')
        if not pagina:
            break
    return sorted(dados, key=lambda x: (x.get('modifiedTime',''), x.get('name','')))


def baixar_drive(drive, meta):
    tamanho_max = int(os.getenv('SAI_MAX_FILE_MB','20')) * 1024 * 1024
    if int(meta.get('size') or 0) > tamanho_max:
        raise ValueError('Tamanho superior ao limite permitido')
    from googleapiclient.http import MediaIoBaseDownload
    buff = io.BytesIO()
    request = drive.files().get_media(fileId=meta['id'], supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buff, request, chunksize=1024*1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
        if buff.tell() > tamanho_max:
            raise ValueError('Arquivo excede o limite configurado')
    return buff.getvalue()


def carregar_chaves_sheet(ws):
    """Uma leitura por execução, não uma consulta Google por cada O.S./medição."""
    valores = ws.get_all_values()
    chaves = set()
    for row in valores[1:]:
        if len(row) >= 6:
            try:
                chaves.add(chave_medicao(row))
            except (ValueError, TypeError):
                continue
    return chaves


def novos_sem_duplicacao(linhas, chaves):
    novos = []
    repetidos = 0
    for row in linhas:
        chave = chave_medicao(row)
        if chave not in chaves:
            novos.append(row)
            chaves.add(chave)
        else:
            repetidos += 1
    return novos, repetidos


def executar_sincronizacao():
    import hashlib
    sheet, drive = conectar_google()
    dry_run = os.getenv('SAI_DRY_RUN', 'true').lower() in ('true','1','yes')
    ws, diario = abrir_abas(sheet, dry_run=dry_run)
    finalizados, hashes_finalizados = ler_diario(diario)
    metas = listar_arquivos_drive(drive, os.environ['SAI_DRIVE_FOLDER_ID'])
    print(f'SAI: {len(metas)} arquivo(s) elegível(is) na pasta de entrada')
    # Não há credenciais Microsoft nem consultas diretas ao OneDrive.
    pendentes = [meta for meta in metas if (meta['id'], meta.get('md5Checksum') or meta.get('modifiedTime','')) not in finalizados]
    limite = int(os.getenv('SAI_MAX_FILES_PER_RUN', '20'))
    chaves = None
    falhas = 0
    for meta in pendentes[:limite]:
        try:
            content = baixar_drive(drive, meta)
            hash_sha = hashlib.sha256(content).hexdigest()
            if (meta['id'], meta.get('md5Checksum') or meta.get('modifiedTime','')) in finalizados:
                continue
            if hash_sha in hashes_finalizados:
                resumo = Resultado(origem=0, linhas=[])
                if not dry_run:
                    logar(diario, meta=meta, hash_sha=hash_sha, resumo=resumo,
                          novos=0, repetidos=0, status='SEM_ALTERACOES',
                          detalhes='Arquivo de conteúdo idêntico já processado')
                finalizados.add((meta['id'], meta.get('md5Checksum') or meta.get('modifiedTime','')))
                print('SAI: conteúdo já processado, ignorado')
                continue
            df = ler_arquivo(meta['name'], content)
            resultado = converter_bruta(df, meta['name'])
            if not resultado.linhas:
                status, novos_qtd, repetidos = 'SEM_ELEGIVEIS', 0, 0
            else:
                if chaves is None:
                    chaves = carregar_chaves_sheet(ws)
                # Novos sem duplicação em relação à planilha oficial (inclusive dados manuais).
                # Somente acrescenta chaves à memória após confirmar a gravação do lote.
                novos = []
                repetidos = 0
                repetidos_planilha = 0
                repetidos_arquivo = 0
                chaves_novas = set()
                for row in resultado.linhas:
                    ck = chave_medicao(row)
                    if ck in chaves:
                        repetidos += 1
                        repetidos_planilha += 1
                    elif ck in chaves_novas:
                        repetidos += 1
                        repetidos_arquivo += 1
                    else:
                        novos.append(row)
                        chaves_novas.add(ck)
                if dry_run:
                    print(
                        f'SAI: SIMULAÇÃO (SEM GRAVAÇÃO) | arquivo={meta["name"]} '
                        f'| atividades={resultado.origem} '
                        f'| elegiveis={len(resultado.linhas)} '
                        f'| ja_na_planilha={repetidos_planilha} '
                        f'| repetidos_no_arquivo={repetidos_arquivo} '
                        f'| novos={len(novos)} '
                        f'| descartados={resultado.origem-len(resultado.linhas)}'
                    )
                    continue
                for inicio in range(0, len(novos), 200):
                    lote = novos[inicio:inicio+200]
                    ws.append_rows(lote, value_input_option='RAW')
                    chaves.update(chave_medicao(r) for r in lote)
                novos_qtd = len(novos)
                status = 'IMPORTADO' if novos_qtd else 'SEM_NOVOS'
            if dry_run:
                print(f'SAI: SIMULAÇÃO: arquivo={meta["name"]}; elegíveis={len(resultado.linhas)}; sem escrita')
                continue
            logar(diario, meta=meta, hash_sha=hash_sha, resumo=resultado,
                  novos=novos_qtd, repetidos=repetidos, status=status,
                  detalhes=(f'Coord. inválidas: {resultado.sem_coordenadas}; '
                            f'sem data: {resultado.sem_data}'))
            hashes_finalizados.add(hash_sha)
            finalizados.add((meta['id'], meta.get('md5Checksum') or meta.get('modifiedTime','')))
            print(f'SAI: {meta["name"]}: {status}; novos={novos_qtd}; repetidos={repetidos}')
        except Exception as exc:
            falhas += 1
            # Não expor dados de clientes, nomes de matrículas nem conteúdo da base em logs.
            print(f'SAI: falha de processamento: {exc.__class__.__name__}', file=sys.stderr)
            try:
                if dry_run:
                    continue
                logar(diario, meta=meta, hash_sha=meta.get('md5Checksum',''),
                      resumo=Resultado(origem=0,linhas=[]), novos=0,repetidos=0,
                      status='ERRO', detalhes=exc.__class__.__name__)
            except Exception:
                pass
    if falhas:
        raise RuntimeError(f'{falhas} arquivo(s) apresentaram erro; consultar log sai_sync_pressao')


def validar_local(path):
    arquivo = Path(path)
    r = converter_bruta(ler_arquivo(arquivo.name,arquivo.read_bytes()),arquivo.name)
    print(f'SAI validação local: atividades={r.origem}; elegíveis={len(r.linhas)}; '
          f'0 MCA={sum(row[6] == 0 for row in r.linhas)}; '
          f'sem cota numérica={r.sem_pressao_numerica}; sem data={r.sem_data}')
    return r


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--arquivo-local', help='Validação sem acesso a Drive/Sheets')
    args = parser.parse_args()
    if args.arquivo_local:
        validar_local(args.arquivo_local)
    else:
        executar_sincronizacao()


if __name__ == '__main__':
    main()
