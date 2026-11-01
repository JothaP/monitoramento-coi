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

# Mesmo conversor e mesmas regras de duplicidade do upload no Modulo 1.
from sai_pressao_importacao import (
    COLUNAS_SAI, Resultado, IndiceDuplicidades, converter_bruta,
    ler_arquivo, chave_medicao, normalizar_cabecalho,
)


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
    """Uma leitura do Sheets para identificar medições já registradas."""
    return IndiceDuplicidades(ws.get_all_values()[1:])


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
                # Usa a mesma regra de duplicidade do upload do Módulo 1.
                novos, repetidos, correspondencias_legadas = chaves.selecionar(resultado.linhas)
                repetidos_planilha = repetidos
                repetidos_arquivo = 0  # Incluídos no total de repetidos nesta versão.
                if dry_run:
                    print(
                        f'SAI: SIMULAÇÃO (SEM GRAVAÇÃO) | arquivo={meta["name"]} '
                        f'| atividades={resultado.origem} '
                        f'| elegiveis={len(resultado.linhas)} '
                        f'| ja_na_planilha={repetidos_planilha} '
                        f'| repetidos_no_arquivo={repetidos_arquivo} '
                        f'| novos={len(novos)} '
                        f'| sem_pressao_numerica={resultado.sem_pressao_numerica} '
                        f'| sem_coordenadas={resultado.sem_coordenadas} '
                        f'| sem_data={resultado.sem_data} '
                        f'| descartados={resultado.origem-len(resultado.linhas)}'
                    )
                    continue
                for inicio in range(0, len(novos), 200):
                    lote = novos[inicio:inicio+200]
                    ws.append_rows(lote, value_input_option='RAW')
                    # O índice já foi atualizado ao selecionar o lote.
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
