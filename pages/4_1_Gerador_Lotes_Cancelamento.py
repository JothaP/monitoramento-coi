import streamlit as st
import pandas as pd
import io
import re
import unicodedata
from datetime import datetime, time, timedelta
from auth import verificar_autenticacao

# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Gerador de Lotes de Cancelamento - COI",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# AUTENTICAÇÃO
# ============================================================
if not verificar_autenticacao():
    st.warning("Sessão não iniciada ou expirada.")
    if st.button("Ir para o Login"):
        st.switch_page("app.py")
    st.stop()

# ============================================================
# FUNÇÕES AUXILIARES (mantidas do original)
# ============================================================

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.upper().strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto

def normalizar_coluna(coluna):
    return normalizar_texto(coluna)

def normalizar_cidade_evento(cidade):
    c = normalizar_texto(cidade)
    c = re.sub(r'^(ZONA RURAL\s*-\s*|POV\.?\s*|POVOADO\s*)', '', c).strip()
    substituicoes = {
        'CURRAL NOVO DO PIAUI': 'CURRAL NOVO PI',
        'SAO LOURENCO DO PIAUI': 'SAO LOURENCO',
        'OLHO D AGUA DO PIAUI': "OLHO D'AGUA DO PIAUI",
    }
    return substituicoes.get(c, c)

def parse_protocolo(proto):
    if pd.isna(proto):
        return "", "", None
    texto = str(proto).strip()
    match = re.search(r"(\d+)\s*/\s*(\d{4})", texto)
    if not match:
        return "", "", None
    numero_str = match.group(1)
    ano_str = match.group(2)
    try:
        numero_int = int(numero_str)
    except:
        numero_int = None
    return numero_str, ano_str, numero_int

def converter_datas_robusto(serie):
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    for idx, valor in serie.items():
        if pd.isna(valor):
            continue
        if isinstance(valor, (datetime, pd.Timestamp)):
            try:
                resultado.loc[idx] = pd.Timestamp(valor)
            except Exception:
                pass
            continue
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            try:
                numero = float(valor)
                if 1 <= numero <= 100000:
                    resultado.loc[idx] = pd.Timestamp("1899-12-30") + pd.to_timedelta(numero, unit="D")
                    continue
            except Exception:
                pass
        texto = str(valor).strip()
        if not texto or texto.lower() in {"nan", "nat", "none", "null", "-", "--"}:
            continue
        texto = re.sub(r"\s+", " ", texto)
        texto = re.sub(r"[hH]$", "", texto).strip()
        formatos = [
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
            "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
            "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        ]
        convertido = None
        for formato in formatos:
            try:
                convertido = datetime.strptime(texto, formato)
                break
            except ValueError:
                pass
        if convertido is not None:
            resultado.loc[idx] = pd.Timestamp(convertido)
            continue
        try:
            resultado.loc[idx] = pd.to_datetime(texto, dayfirst=True, errors="coerce")
        except Exception:
            pass
    return resultado

def parse_data_hora_evento(valor):
    if pd.isna(valor):
        return pd.NaT
    try:
        convertido = converter_datas_robusto(pd.Series([valor])).iloc[0]
        if pd.notna(convertido):
            return convertido
    except Exception:
        pass
    texto = str(valor).strip()
    if not texto or texto in {"--", "-"}:
        return pd.NaT
    texto = re.sub(r"[hH]$", "", texto).strip()
    texto = re.sub(r"\s+", " ", texto)
    formatos = [
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    ]
    for formato in formatos:
        try:
            return pd.Timestamp(datetime.strptime(texto, formato))
        except ValueError:
            pass
    return pd.NaT

def evento_eh_todo_municipio(areas_texto):
    if not areas_texto:
        return False
    padroes = [
        r'TODO\s+O\s+MUNIC[IÍ]PIO', r'TODA\s+A?\s+CIDADE',
        r'TODO\s+O\s+MUNICIPIO', r'TODA\s+CIDADE',
        r'TODO\s+MUNIC[IÍ]PIO', r'TODA\s+A\s+CIDADE',
        r'TODO\s+O\s+POVOADO', r'TODA\s+A\s+ÁREA', r'TODA\s+AREA',
    ]
    for padrao in padroes:
        if re.search(padrao, areas_texto, re.IGNORECASE):
            return True
    return False

def bairro_aparece_nas_areas_evento(bairro_os, areas_texto):
    if not bairro_os or not areas_texto:
        return False
    bairro = normalizar_texto(bairro_os)
    areas = normalizar_texto(areas_texto)
    if bairro in areas:
        return True
    tokens_bairro = [token for token in bairro.split() if len(token) > 2]
    if not tokens_bairro:
        return False
    matches = sum(1 for token in tokens_bairro if token in areas)
    if matches >= max(1, len(tokens_bairro) * 0.7):
        return True
    equivalentes = {
        'CENTRO': ['CENTRO', 'CENTRAL'],
        'SAO JOSE': ['SAO JOSE', 'S JOSE', 'SAO JOSÉ'],
        'NOVA ESPERANCA': ['NOVA ESPERANCA', 'NOVA ESPERANÇA'],
    }
    for chave, lista in equivalentes.items():
        if any(eq in bairro for eq in lista):
            if any(eq in areas for eq in lista):
                return True
    return False

def localizar_coluna(df, tipo):
    colunas = list(df.columns)
    normalizadas = {coluna: normalizar_coluna(coluna) for coluna in colunas}
    if tipo == "protocolo":
        for coluna, nome in normalizadas.items():
            if nome == "COD. PROTOCOLO ORIGEM":
                return coluna
        for coluna, nome in normalizadas.items():
            if "PROTOCOLO" in nome and "ORIGEM" in nome:
                return coluna
    elif tipo == "matricula":
        for coluna, nome in normalizadas.items():
            if nome == "MATRICULA":
                return coluna
        for coluna, nome in normalizadas.items():
            if "MATRICULA" in nome:
                return coluna
    elif tipo == "cidade":
        for coluna, nome in normalizadas.items():
            if nome == "CIDADE":
                return coluna
    elif tipo == "bairro":
        for coluna, nome in normalizadas.items():
            if nome == "BAIRRO":
                return coluna
        for coluna, nome in normalizadas.items():
            if "BAIRRO" in nome:
                return coluna
    elif tipo == "data":
        for coluna, nome in normalizadas.items():
            if nome == "INICIO DO SLA":
                return coluna
        for coluna, nome in normalizadas.items():
            if "INICIO DO SLA" in nome or "INICIO SLA" in nome:
                return coluna
        return None
    return None

def localizar_coluna_eventos(df, candidatos, obrigatoria=True):
    normalizadas = {coluna: normalizar_texto(coluna) for coluna in df.columns}
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if nome == candidato_norm:
                return coluna
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if candidato_norm in nome:
                return coluna
    if obrigatoria:
        raise ValueError('Não foi encontrada a coluna de eventos: ' + ' / '.join(candidatos))
    return None

def localizar_coluna_servico(df):
    candidatos = [
        "Descrição do Serviço", "Descricao do Servico", "Tipo de Serviço",
        "Tipo Servico", "Tipo de Servico", "Serviço", "Servico",
        "Descrição", "Descricao", "Motivo", "Tipo OS", "Tipo O.S.", "Tipo",
    ]
    normalizadas = {coluna: normalizar_texto(coluna) for coluna in df.columns}
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if nome == candidato_norm:
                return coluna
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if candidato_norm in nome:
                return coluna
    return None

def localizar_coluna_lote(df, candidatos, obrigatoria=True):
    normalizadas = {coluna: normalizar_texto(coluna) for coluna in df.columns}
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if nome == candidato_norm:
                return coluna
    for candidato in candidatos:
        candidato_norm = normalizar_texto(candidato)
        for coluna, nome in normalizadas.items():
            if candidato_norm in nome:
                return coluna
    if obrigatoria:
        raise ValueError("Não foi encontrada a coluna de lote: " + " / ".join(candidatos))
    return None

def ler_excel_bytes(nome_arquivo, conteudo):
    nome_lower = nome_arquivo.lower()
    if not (nome_lower.endswith(".xlsx") or nome_lower.endswith(".xlsm")):
        raise ValueError(f"O arquivo '{nome_arquivo}' não é um Excel .xlsx ou .xlsm.")
    df = pd.read_excel(io.BytesIO(conteudo), engine="openpyxl")
    novas_colunas = []
    for coluna in df.columns:
        texto = str(coluna).strip()
        texto = re.sub(r"\s+", " ", texto)
        novas_colunas.append(texto)
    df.columns = novas_colunas
    return df

def remover_linhas_vazias(df):
    if df.empty:
        return df.copy()
    df = df.copy()
    mascara = ~df.apply(
        lambda linha: all(pd.isna(valor) or str(valor).strip() == "" for valor in linha),
        axis=1
    )
    return df.loc[mascara].reset_index(drop=True)

def consolidar_lista_dfs(lista_dfs, mensagem_vazio="Nenhum arquivo foi carregado."):
    bases = []
    for df in lista_dfs:
        if df is not None and not getattr(df, "empty", True):
            bases.append(df.copy())
    if not bases:
        raise ValueError(mensagem_vazio)
    df = pd.concat(bases, ignore_index=True, sort=False)
    df = remover_linhas_vazias(df)
    if df.empty:
        raise ValueError("Os arquivos carregados não possuem dados.")
    antes = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    qtd_duplicadas = antes - len(df)
    return df, qtd_duplicadas

# ============================================================
# MAPA DE ZONAS
# ============================================================
MAPA_ZONAS = {
    "ACAUA": 229, "AGRICOLANDIA": 1, "AGUA BRANCA": 3, "ALAGOINHA": 129,
    "ALEGRETE DO PIAUI": 439, "ALTO LONGA": 2, "ALTOS": 4, "ALVORADA DO GURGUEIA": 414,
    "AMARANTE": 5, "ANGICAL DO PIAUI": 6, "ANISIO DE ABREU": 7, "ANTONIO ALMEIDA": 474,
    "AROAZES": 10, "AROEIRAS DO ITAIM": 415, "ARRAIAL": 9, "ASSUNCAO DO PIAUI": 422,
    "AVELINO LOPES": 11, "BAIXA GRANDE DO RIBEIRO": 125, "BARRA D ALCANTARA": 423,
    "BARRAS": 12, "BARREIRAS DO PIAUI": 13, "BARRO DURO": 14, "BATALHA": 15,
    "BELA VISTA DO PIAUI": 438, "BELEM DO PIAUI": 318, "BENEDITINOS": 19,
    "BERTOLINIA": 17, "BETANIA DO PIAUI": 441, "BOA HORA": 416, "BOCAINA": 16,
    "BOM JESUS": 20, "BOM PRINCIPIO DO PIAUI": 442, "BONFIM DO PIAUI": 179,
    "BOQUEIRAO DO PIAUI": 401, "BRASILEIRA": 121, "BREJO DO PIAUI": 160,
    "BURITI DOS LOPES": 18, "BURITI DOS MONTES": 443, "CABECEIRAS DO PIAUI": 127,
    "CAJAZEIRAS DO PIAUI": 444, "CAJUEIRO DA PRAIA": 206, "CALDEIRAO GRANDE DO PIAUI": 417,
    "CAMPINAS DO PIAUI": 22, "CAMPO ALEGRE DO FIDALGO": 418, "CAMPO GRANDE DO PIAUI": 195,
    "CAMPO LARGO DO PIAUI": 419, "CANAVIEIRA": 138, "CANTO DO BURITI": 24,
    "CAPITAO DE CAMPOS": 21, "CAPITAO GERVASIO OLIVEIRA": 429, "CARACOL": 25,
    "CARAUBAS DO PIAUI": 402, "CARIDADE": 322, "CASTELO DO PIAUI": 27, "CAXINGO": 446,
    "COCAL": 28, "COCAL DE TELHA": 403, "COCAL DOS ALVES": 447, "COIVARAS": 448,
    "COLONIA DO GURGUEIA": 123, "COLONIA DO PIAUI": 162, "CONCEICAO DO CANINDE": 26,
    "CORONEL JOSE DIAS": 270, "CORRENTE": 29, "CRISTALANDIA": 30, "CRISTINO CASTRO": 31,
    "CURIMATA": 32, "CURRAIS": 449, "CURRAL NOVO PI": 268, "CURRALINHOS": 412,
    "DEMERVAL LOBAO": 33, "DIRCEU ARCOVERDE": 115, "DOM EXPEDITO LOPES": 34,
    "DOM INOCENCIO": 400, "DOMINGOS MOURAO": 70, "ELESBAO VELOSO": 36,
    "ELIZEU MARTINS": 35, "ESPERANTINA": 37, "FARTURA DO PIAUI": 329,
    "FLORES DO PIAUI": 39, "FLORESTA DO PIAUI": 450, "FLORIANO": 41,
    "FRANCINOPOLIS": 38, "FRANCISCO AIRES": 40, "FRANCISCO MACEDO": 404,
    "FRANCISCO SANTOS": 42, "FRONTEIRAS": 43, "GEMINIANO": 433, "GILBUES": 44,
    "GUADALUPE": 45, "GUARIBAS": 281, "HUGO NAPOLEAO": 46, "ILHA GRANDE": 149,
    "INHUMA": 47, "IPIRANGA": 49, "ISAIAS COELHO": 50, "ITAINOPOLIS": 51,
    "ITAUEIRA": 48, "JACOBINA DO PIAUI": 192, "JAICOS": 52, "JARDIM MULATO": 136,
    "JATOBA DO PIAUI": 452, "JERUMENHA": 54, "JOAO COSTA": 453, "JOAQUIM PIRES": 55,
    "JOCA MARQUES": 454, "JOSE DE FREITAS": 53, "JUAZEIRO DO PIAUI": 214,
    "JULIO BORGES": 203, "JUREMA": 209, "LAGOA ALEGRE": 120, "LAGOA DE SAO FRANCISCO": 424,
    "LAGOA DO BARRO DO PIAUI": 176, "LAGOA DO PIAUI": 455, "LAGOA DO SITIO": 425,
    "LAGOINHA DO PIAUI": 456, "LANDRI SALES": 435, "LUIS CORREIA": 57, "LUZILANDIA": 58,
    "MADEIRO": 457, "MANOEL EMIDIO": 59, "MARCOLANDIA": 406, "MARCOS PARENTE": 60,
    "MASSAPE DO PIAUI": 431, "MATIAS OLIMPIO": 61, "MIGUEL ALVES": 62, "MIGUEL LEAO": 459,
    "MILTON BRANDAO": 473, "MONSENHOR GIL": 65, "MONSENHOR HIPOLITO": 66,
    "MONTE ALEGRE": 64, "MORRO CABECA NO TEMPO": 434, "MORRO DO CHAPEU DO PIAUI": 405,
    "MURICI DOS PORTELAS": 320, "NAZARE DO PIAUI": 67, "NAZARIA": 131,
    "NOSSA SENHORA DE NAZARE": 420, "NOSSA SRA DOS REMEDIOS": 69, "NOVA SANTA RITA": 312,
    "NOVO ORIENTE DO PIAU": 68, "NOVO SANTO ANTONIO": 410, "OEIRAS": 71,
    "OLHO D'AGUA DO PIAUI": 461, "PADRE MARCOS": 72, "PAES LANDIM": 73,
    "PAJEU DO PIAUI": 462, "PALMEIRA DO PIAUI": 74, "PALMEIRAIS": 75, "PAQUETA": 187,
    "PARNAGUA": 76, "PARNAIBA": 77, "PASSAGEM FRANCA": 130, "PATOS DO PIAUI": 310,
    "PAU D ARCO DO PIAUI": 436, "PAULISTANA": 79, "PAVUSSU": 135, "PEDRO II": 80,
    "PEDRO LAURENTINO": 428, "PICOS": 81, "PIMENTEIRAS": 82, "PIO IX": 78,
    "PIRACURUCA": 83, "PIRIPIRI": 84, "PORTO": 85, "PORTO ALEGRE DO PIAUI": 426,
    "PRATA DO PIAUI": 86, "QUEIMADA NOVA": 465, "REDENCAO DO GURGUEIA": 466,
    "REGENERACAO": 89, "RIACHO FRIO": 146, "RIBEIRA DO PIAUI": 467,
    "RIBEIRO GONCALVES": 88, "RIO GRANDE DO PIAUI": 90, "SANTA CRUZ DO PIAUI": 93,
    "SANTA CRUZ DOS MILAGRES": 468, "SANTA FILOMENA": 94, "SANTA LUZ": 96,
    "SANTA ROSA DO PIAUI": 117, "SANTA TERESA": 158, "SANTANA DO PIAUI": 212,
    "SANTO ANTONIO DE LISBOA": 91, "SANTO ANTONIO D MILA": 122, "SANTO INACIO DO PIAUI": 102,
    "SAO BRAZ": 319, "SAO FELIX": 95, "SAO FRANCISCO DE ASSIS": 263,
    "SAO FRANCISCO DO PIAUI": 97, "SAO GONCALO DO GURGUEIA": 469, "SAO GONCALO DO PIAUI": 98,
    "SAO JOAO DA CANABRAVA": 116, "SAO JOAO DA FRONTEIRA": 408, "SAO JOAO DA SERRA": 99,
    "SAO JOAO DA VARJOTA": 411, "SAO JOAO DO ARRAIAL": 470, "SAO JOAO DO PIAUI": 104,
    "SAO JOSE DO DIVINO": 174, "SAO JOSE DO PEIXE": 103, "SAO JOSE DO PIAUI": 92,
    "SAO JULIAO": 100, "SAO LOURENCO": 269, "SAO LUIS DO PIAUI": 202,
    "SAO MIGUEL DA BAIXA GRANDE": 427, "SAO MIGUEL DO FIDALGO": 432, "SAO MIGUEL TAPUIO": 101,
    "SAO PEDRO": 105, "SAO RAIMUNDO NONATO": 106, "SEBASTIAO BARROS": 472,
    "SEBASTIAO LEAL": 126, "SIGEFREDO PACHECO": 409, "SIMOES": 107, "SIMPLICIO MENDES": 108,
    "SOCORRO DO PIAUI": 109, "SUSSUAPARA": 421, "TAMBORIL DO PIAUI": 437,
    "TANQUE DO PIAUI": 430, "TERESINA": 110, "UNIAO": 111, "URUCUI": 112, "VALENCA": 113,
    "VARZEA BRANCA": 193, "VARZEA GRANDE": 114, "VERA MENDES": 413, "VILA NOVA DO PIAUI": 196,
    "WALL FERRAZ": 309, "POV SANTA TERESA": 158, "POV CALDEIRAOZINHO": 287,
    "POVOADO BURITIZINHO": 233, "POV COROA DE SAO REMIGIO": 277, "POVOADO PEDRA": 157,
    "POVOADO APARECIDA": 143, "POV BARRA DO LONGA": 124, "POV INGAZEIRA": 330,
    "POV SERRA DA SOLTA": 302, "POVOADO BARRA GRANDE": 239, "POVOADO SAO JOAQUIM": 210,
    "POVOADO TRANQUEIRA": 235, "POV MOCAMBINHO": 148, "POV BURITI DO CASTELO": 189,
    "POVOADO MANDACARU": 288, "POVOADO MATINHA": 183, "POV DAVID CALDAS": 119,
    "POV. LAGOA DE BAIXO": 331,
}

MAPA_ZONAS_NORMALIZADO = {normalizar_texto(cidade): zona for cidade, zona in MAPA_ZONAS.items()}

def obter_zona(cidade):
    cidade_normalizada = normalizar_texto(cidade)
    if not cidade_normalizada:
        return None
    return MAPA_ZONAS_NORMALIZADO.get(cidade_normalizada)

# ============================================================
# FUNÇÕES DE CRUZAMENTO (mantidas)
# ============================================================

def preparar_dados_eventos(df_eventos_bruto, df_os):
    col_evento_cidade = localizar_coluna_eventos(df_eventos_bruto, ['Cidade'])
    col_areas = localizar_coluna_eventos(df_eventos_bruto, ['Áreas Impactadas', 'Areas Impactadas'])
    col_inicio = localizar_coluna_eventos(df_eventos_bruto, ['Início', 'Inicio'])
    col_prev_termino = localizar_coluna_eventos(df_eventos_bruto, ['Prev. Término', 'Prev. Termino', 'Previsão de Término'])
    col_descricao = localizar_coluna_eventos(df_eventos_bruto, ['Descrição do Serviço', 'Descricao do Servico', 'Descrição', 'Descricao'], obrigatoria=False)
    col_os_cidade = localizar_coluna_eventos(df_os, ['Cidade'])
    col_os_bairro = localizar_coluna_eventos(df_os, ['Bairro'])
    col_os_data = localizar_coluna_eventos(df_os, ['Início do SLA', 'Inicio do SLA'])
    col_os_protocolo = localizar_coluna_eventos(df_os, ['Cód. Protocolo Origem', 'Cod. Protocolo Origem'])
    col_os_matricula = localizar_coluna_eventos(df_os, ['Matrícula', 'Matricula'])

    eventos = df_eventos_bruto.copy()
    os_base = df_os.copy()

    eventos['_CIDADE_NORM_EVENTO'] = eventos[col_evento_cidade].apply(normalizar_cidade_evento)
    eventos['_AREAS_NORM_EVENTO'] = eventos[col_areas].apply(normalizar_texto)
    eventos['_DT_INICIO_EVENTO'] = eventos[col_inicio].apply(parse_data_hora_evento)
    eventos['_DT_PREV_TERMINO_EVENTO'] = eventos[col_prev_termino].apply(parse_data_hora_evento)
    eventos['_FIM_EFETIVO_EVENTO'] = eventos['_DT_PREV_TERMINO_EVENTO'] + timedelta(hours=3)
    eventos['_TODO_MUNICIPIO_EVENTO'] = eventos['_AREAS_NORM_EVENTO'].apply(evento_eh_todo_municipio)
    eventos = eventos[eventos['_AREAS_NORM_EVENTO'] != ''].copy()

    os_base['_CIDADE_NORM_EVENTO'] = os_base[col_os_cidade].apply(normalizar_cidade_evento)
    os_base['_BAIRRO_NORM_EVENTO'] = os_base[col_os_bairro].apply(normalizar_texto)
    os_base['_DATA_ABERTURA_EVENTO'] = converter_datas_robusto(os_base[col_os_data])
    os_base['_NUMERO_EVENTO'], os_base['_ANO_EVENTO'] = zip(*[
        (parse_protocolo(valor)[2], int(parse_protocolo(valor)[1]) if parse_protocolo(valor)[1] else None)
        for valor in os_base[col_os_protocolo]
    ])

    return eventos, os_base, {
        'cidade_evento': col_evento_cidade, 'areas': col_areas, 'inicio': col_inicio,
        'prev_termino': col_prev_termino, 'descricao': col_descricao,
        'os_cidade': col_os_cidade, 'os_bairro': col_os_bairro, 'os_data': col_os_data,
        'os_protocolo': col_os_protocolo, 'os_matricula': col_os_matricula,
    }

def cruzar_eventos_com_backlog(df_eventos_bruto, df_backlog, modo="API"):
    eventos, os_base, colunas = preparar_dados_eventos(df_eventos_bruto, df_backlog)
    resultados = []
    os_ja_incluidas = set()
    avisos = []

    for idx, os_row in os_base.iterrows():
        cidade_os = os_row['_CIDADE_NORM_EVENTO']
        bairro_os = os_row['_BAIRRO_NORM_EVENTO']
        data_os = os_row['_DATA_ABERTURA_EVENTO']
        if pd.isna(data_os) or not cidade_os:
            continue
        eventos_cidade = eventos[eventos['_CIDADE_NORM_EVENTO'] == cidade_os]
        for idx_evento, ev in eventos_cidade.iterrows():
            inicio_evento = ev['_DT_INICIO_EVENTO']
            fim_evento = ev['_FIM_EFETIVO_EVENTO']
            if pd.isna(inicio_evento) or pd.isna(fim_evento):
                continue
            if fim_evento < inicio_evento:
                avisos.append({
                    'Tipo': 'Evento com período inválido',
                    'Cidade': ev[colunas['cidade_evento']],
                    'Matrícula': '', 'Cód. Protocolo Origem': '',
                    'Motivo': f'Início: {inicio_evento.strftime("%d/%m/%Y %H:%M")} | Fim efetivo: {fim_evento.strftime("%d/%m/%Y %H:%M")}'
                })
                continue
            if not (inicio_evento <= data_os <= fim_evento):
                continue
            match_area = True if ev['_TODO_MUNICIPIO_EVENTO'] else bairro_aparece_nas_areas_evento(bairro_os, ev['_AREAS_NORM_EVENTO'])
            if not match_area:
                continue
            if idx in os_ja_incluidas:
                break
            protocolo = os_row[colunas['os_protocolo']]
            numero_str, ano_str, numero_int = parse_protocolo(protocolo)
            try:
                ano_pedido = int(ano_str) if ano_str else None
            except Exception:
                ano_pedido = None
            if numero_int is None:
                avisos.append({
                    'Tipo': 'Protocolo inválido', 'Cidade': os_row[colunas['os_cidade']],
                    'Matrícula': os_row[colunas['os_matricula']], 'Cód. Protocolo Origem': protocolo,
                    'Motivo': 'Protocolo inválido'
                })
            cidade_original = os_row[colunas['os_cidade']]
            zona = 1 if modo == "THE" else obter_zona(cidade_original)
            if zona is None and modo != "THE":
                avisos.append({
                    'Tipo': 'Cidade sem zona', 'Cidade': cidade_original,
                    'Matrícula': os_row[colunas['os_matricula']], 'Cód. Protocolo Origem': protocolo,
                    'Motivo': 'Cidade não encontrada no MAPA_ZONAS'
                })
            descricao = ''
            if colunas['descricao'] is not None:
                valor_descricao = ev[colunas['descricao']]
                if pd.notna(valor_descricao):
                    descricao = str(valor_descricao).strip()
            if len(descricao) > 280:
                descricao = descricao[:277] + '...'
            observacao = 'Abertura indevida - OS aberta durante evento de falta de água (' + descricao + ')'
            resultados.append({
                'Matricula': os_row[colunas['os_matricula']],
                'Zona Ligacao': zona,
                'Numero Do Pedido': numero_int,
                'Ano Do Pedido': ano_pedido,
                'Tipo Encerramento': 6,
                'Observações': observacao
            })
            os_ja_incluidas.add(idx)
            break

    df_saida = pd.DataFrame(resultados, columns=['Matricula', 'Zona Ligacao', 'Numero Do Pedido', 'Ano Do Pedido', 'Tipo Encerramento', 'Observações'])
    return df_saida, avisos, len(eventos), len(os_ja_incluidas)

def cruzar_falta_com_servicos(df_falta, df_servicos, modo="API"):
    if df_falta is None or df_falta.empty:
        raise ValueError("Backlog de Falta de Água vazio ou não carregado.")
    if df_servicos is None or df_servicos.empty:
        raise ValueError("Backlog de Serviços vazio ou não carregado.")
    col_mat_falta = localizar_coluna(df_falta, "matricula")
    col_prot_falta = localizar_coluna(df_falta, "protocolo")
    col_cidade_falta = localizar_coluna(df_falta, "cidade")
    if col_mat_falta is None:
        raise ValueError("Não foi encontrada a coluna 'Matrícula' no backlog de Falta de Água.")
    if col_prot_falta is None:
        raise ValueError("Não foi encontrada a coluna 'Cód. Protocolo Origem' no backlog de Falta de Água.")
    if col_cidade_falta is None:
        raise ValueError("Não foi encontrada a coluna 'Cidade' no backlog de Falta de Água.")
    col_mat_serv = localizar_coluna(df_servicos, "matricula")
    col_prot_serv = localizar_coluna(df_servicos, "protocolo")
    col_servico = localizar_coluna_servico(df_servicos)
    if col_mat_serv is None:
        raise ValueError("Não foi encontrada a coluna 'Matrícula' no backlog de Serviços.")
    if col_prot_serv is None:
        raise ValueError("Não foi encontrada a coluna 'Cód. Protocolo Origem' no backlog de Serviços.")

    servicos_por_matricula = {}
    for _, linha in df_servicos.iterrows():
        mat_norm = normalizar_texto(linha[col_mat_serv])
        if not mat_norm or mat_norm in servicos_por_matricula:
            continue
        protocolo_serv = "" if pd.isna(linha[col_prot_serv]) else str(linha[col_prot_serv]).strip()
        descricao_serv = ""
        if col_servico is not None:
            valor = linha[col_servico]
            if pd.notna(valor):
                descricao_serv = str(valor).strip()
        if not descricao_serv:
            descricao_serv = "Serviço em aberto"
        if len(descricao_serv) > 120:
            descricao_serv = descricao_serv[:117] + "..."
        servicos_por_matricula[mat_norm] = {"protocolo": protocolo_serv, "servico": descricao_serv}

    resultados = []
    avisos = []
    os_ja_incluidas = set()
    for idx, linha in df_falta.iterrows():
        mat_norm = normalizar_texto(linha[col_mat_falta])
        if not mat_norm or mat_norm not in servicos_por_matricula or idx in os_ja_incluidas:
            continue
        info_serv = servicos_por_matricula[mat_norm]
        protocolo_falta = linha[col_prot_falta]
        cidade = linha[col_cidade_falta]
        matricula = linha[col_mat_falta]
        numero_str, ano_str, numero_int = parse_protocolo(protocolo_falta)
        if numero_int is None:
            avisos.append({
                "Tipo": "Protocolo inválido", "Cidade": cidade, "Matrícula": matricula,
                "Cód. Protocolo Origem": protocolo_falta, "Motivo": "Protocolo inválido no backlog de Falta de Água",
            })
        try:
            ano_pedido = int(ano_str) if ano_str else None
        except Exception:
            ano_pedido = None
        zona = 1 if modo == "THE" else obter_zona(cidade)
        if zona is None and modo != "THE":
            avisos.append({
                "Tipo": "Cidade sem zona", "Cidade": cidade, "Matrícula": matricula,
                "Cód. Protocolo Origem": protocolo_falta, "Motivo": "Cidade não encontrada no MAPA_ZONAS",
            })
        observacao = "Cliente já possui serviço em aberto: " + info_serv["servico"] + " - O.S. " + str(info_serv["protocolo"])
        resultados.append({
            "Matricula": matricula, "Zona Ligacao": zona, "Numero Do Pedido": numero_int,
            "Ano Do Pedido": ano_pedido, "Tipo Encerramento": 6, "Observações": observacao,
        })
        os_ja_incluidas.add(idx)

    df_saida = pd.DataFrame(resultados, columns=["Matricula", "Zona Ligacao", "Numero Do Pedido", "Ano Do Pedido", "Tipo Encerramento", "Observações"])
    return df_saida, avisos, len(servicos_por_matricula), len(os_ja_incluidas)

def consolidar_lotes_com_fonte(lista_lotes):
    if not lista_lotes:
        raise ValueError("Nenhum arquivo de lote foi carregado.")
    bases = []
    for item in lista_lotes:
        df = item["df"]
        if df is None or df.empty:
            continue
        temp = df.copy()
        temp["_FONTE_LOTE"] = item["nome"]
        bases.append(temp)
    if not bases:
        raise ValueError("Os arquivos de lote carregados não possuem dados.")
    df = pd.concat(bases, ignore_index=True, sort=False)
    df = remover_linhas_vazias(df)
    if df.empty:
        raise ValueError("Após consolidação, os lotes ficaram sem registros.")
    return df

def cruzar_acompanhamento_lote(df_backlog, df_lotes_com_fonte, motivos_por_arquivo):
    if df_backlog is None or df_backlog.empty:
        raise ValueError("Backlog de O.S. de reclamação vazio ou não carregado.")
    if df_lotes_com_fonte is None or df_lotes_com_fonte.empty:
        raise ValueError("Nenhum lote consolidado. Faça o upload de um ou mais arquivos de lote.")
    col_mat_lote = localizar_coluna_lote(df_lotes_com_fonte, ["Matricula", "Matrícula"])
    col_num_lote = localizar_coluna_lote(df_lotes_com_fonte, ["Numero Do Pedido", "Número Do Pedido", "Numero do Pedido"])
    col_ano_lote = localizar_coluna_lote(df_lotes_com_fonte, ["Ano Do Pedido", "Ano do Pedido"])
    col_mat_back = localizar_coluna(df_backlog, "matricula")
    col_prot_back = localizar_coluna(df_backlog, "protocolo")
    col_bairro_back = localizar_coluna(df_backlog, "bairro")
    if col_mat_back is None:
        raise ValueError("Não foi encontrada a coluna 'Matrícula' no backlog de reclamação.")
    if col_prot_back is None:
        raise ValueError("Não foi encontrada a coluna 'Cód. Protocolo Origem' no backlog.")
    if col_bairro_back is None:
        raise ValueError("Não foi encontrada a coluna 'Bairro' no backlog de reclamação.")

    indice_backlog = {}
    for _, linha in df_backlog.iterrows():
        mat_norm = normalizar_texto(linha[col_mat_back])
        if not mat_norm:
            continue
        protocolo = linha[col_prot_back]
        numero_str, ano_str, numero_int = parse_protocolo(protocolo)
        if numero_int is None:
            continue
        try:
            ano_int = int(ano_str) if ano_str else None
        except Exception:
            ano_int = None
        if ano_int is None:
            continue
        chave = (mat_norm, numero_int, ano_int)
        if chave in indice_backlog:
            continue
        bairro = "" if pd.isna(linha[col_bairro_back]) else str(linha[col_bairro_back]).strip()
        indice_backlog[chave] = {
            "bairro": bairro,
            "protocolo": str(protocolo).strip() if pd.notna(protocolo) else "",
            "matricula_original": linha[col_mat_back],
        }

    resultados = []
    avisos = []
    ja_incluidas = set()
    for _, linha in df_lotes_com_fonte.iterrows():
        mat_lote = linha[col_mat_lote]
        mat_norm = normalizar_texto(mat_lote)
        if not mat_norm:
            continue
        try:
            numero = int(linha[col_num_lote]) if pd.notna(linha[col_num_lote]) else None
        except Exception:
            numero = None
        try:
            ano = int(linha[col_ano_lote]) if pd.notna(linha[col_ano_lote]) else None
        except Exception:
            ano = None
        fonte = ""
        if "_FONTE_LOTE" in df_lotes_com_fonte.columns and pd.notna(linha.get("_FONTE_LOTE")):
            fonte = str(linha["_FONTE_LOTE"]).strip()
        if numero is None or ano is None:
            avisos.append({
                "Tipo": "Pedido inválido no lote", "Matrícula": mat_lote,
                "Numero Do Pedido": linha[col_num_lote], "Ano Do Pedido": linha[col_ano_lote],
                "Arquivo Lote": fonte, "Motivo": "Número ou Ano do Pedido inválido no lote",
            })
            continue
        chave = (mat_norm, numero, ano)
        if chave in ja_incluidas:
            continue
        info = indice_backlog.get(chave)
        if info is None:
            candidatos = [v for k, v in indice_backlog.items() if k[0] == mat_norm]
            if len(candidatos) == 1:
                info = candidatos[0]
            else:
                avisos.append({
                    "Tipo": "O.S. não encontrada no backlog", "Matrícula": mat_lote,
                    "Numero Do Pedido": numero, "Ano Do Pedido": ano, "Arquivo Lote": fonte,
                    "Motivo": "Matrícula + Número/Ano não encontrados no backlog de reclamação",
                })
                continue
        motivo = ""
        if fonte and motivos_por_arquivo:
            motivo = str(motivos_por_arquivo.get(fonte, "") or "").strip()
        numero_os = f"{numero} / {ano}"
        resultados.append({
            "Matrícula": info["matricula_original"],
            "Número da O.S. a ser cancelada": numero_os,
            "Bairro": info["bairro"],
            "Motivo do cancelamento": motivo,
            "Arquivo Lote": fonte,
        })
        ja_incluidas.add(chave)

    df_saida = pd.DataFrame(resultados, columns=["Matrícula", "Número da O.S. a ser cancelada", "Bairro", "Motivo do cancelamento", "Arquivo Lote"])
    return df_saida, avisos, len(df_lotes_com_fonte), len(resultados)

def extrair_lista_os(texto_raw):
    if not texto_raw or not str(texto_raw).strip():
        return []
    partes = re.split(r"[,;\s\n]+", str(texto_raw).strip())
    lista = []
    vistos = set()
    for p in partes:
        p = p.strip()
        if not p:
            continue
        chave = normalizar_texto(p)
        if chave in vistos:
            continue
        vistos.add(chave)
        lista.append(p)
    return lista

def cruzar_lista_rapida(df_backlog, lista_os, observacao, modo_atual="API"):
    if df_backlog is None or df_backlog.empty:
        raise ValueError("Backlog vazio ou não carregado para o modo ativo.")
    if not lista_os:
        raise ValueError("Informe ao menos um protocolo/O.S. na lista.")
    col_protocolo = localizar_coluna(df_backlog, "protocolo")
    col_matricula = localizar_coluna(df_backlog, "matricula")
    col_cidade = localizar_coluna(df_backlog, "cidade")
    if col_protocolo is None:
        raise ValueError("Não foi encontrada a coluna 'Cód. Protocolo Origem' no backlog.")
    if col_matricula is None:
        raise ValueError("Não foi encontrada a coluna 'Matrícula' no backlog.")

    indice_por_numero = {}
    indice_por_num_ano = {}
    for _, linha in df_backlog.iterrows():
        protocolo = linha[col_protocolo]
        numero_str, ano_str, numero_int = parse_protocolo(protocolo)
        if numero_int is None:
            texto = str(protocolo).strip() if pd.notna(protocolo) else ""
            m = re.search(r"(\d+)", texto)
            if not m:
                continue
            try:
                numero_int = int(m.group(1))
            except Exception:
                continue
            ano_str = ""
        try:
            ano_int = int(ano_str) if ano_str else None
        except Exception:
            ano_int = None
        if numero_int not in indice_por_numero:
            indice_por_numero[numero_int] = linha
        if ano_int is not None:
            chave = (numero_int, ano_int)
            if chave not in indice_por_num_ano:
                indice_por_num_ano[chave] = linha

    registros = []
    avisos = []
    ja_incluidas = set()
    encontrados = 0
    for item in lista_os:
        numero_str, ano_str, numero_int = parse_protocolo(item)
        if numero_int is None:
            m = re.search(r"(\d+)", str(item))
            if m:
                try:
                    numero_int = int(m.group(1))
                except Exception:
                    numero_int = None
            if numero_int is None:
                avisos.append({"Tipo": "Protocolo inválido na lista", "Protocolo informado": item, "Motivo": "Não foi possível extrair o número do pedido"})
                continue
        try:
            ano_lista = int(ano_str) if ano_str else None
        except Exception:
            ano_lista = None
        linha = None
        if ano_lista is not None:
            linha = indice_por_num_ano.get((numero_int, ano_lista))
        if linha is None:
            linha = indice_por_numero.get(numero_int)
        if linha is None:
            avisos.append({"Tipo": "O.S. não encontrada", "Protocolo informado": item, "Numero Do Pedido": numero_int, "Motivo": "Não encontrada no backlog do modo ativo"})
            continue
        chave_unica = numero_int
        if chave_unica in ja_incluidas:
            continue
        ja_incluidas.add(chave_unica)
        protocolo_back = linha[col_protocolo]
        n_str, a_str, n_int = parse_protocolo(protocolo_back)
        if n_int is None:
            n_int = numero_int
        try:
            ano_pedido = int(a_str) if a_str else (ano_lista if ano_lista else None)
        except Exception:
            ano_pedido = ano_lista
        matricula = linha[col_matricula]
        cidade = linha[col_cidade] if col_cidade else ""
        zona = 1 if modo_atual == "THE" else (obter_zona(cidade) if cidade is not None else None)
        if zona is None and modo_atual != "THE":
            avisos.append({"Tipo": "Cidade sem zona", "Protocolo informado": item, "Cidade": cidade, "Matrícula": matricula, "Motivo": "Cidade não encontrada no MAPA_ZONAS"})
        registros.append({
            "Matricula": matricula, "Zona Ligacao": zona, "Numero Do Pedido": n_int,
            "Ano Do Pedido": ano_pedido, "Tipo Encerramento": 6, "Observações": observacao if observacao else "",
        })
        encontrados += 1

    df_saida = pd.DataFrame(registros, columns=["Matricula", "Zona Ligacao", "Numero Do Pedido", "Ano Do Pedido", "Tipo Encerramento", "Observações"])
    return df_saida, avisos, len(lista_os), encontrados

def identificar_duplicidades(df):
    if df is None or df.empty:
        raise ValueError("Não existem dados consolidados.")
    col_matricula = localizar_coluna(df, "matricula")
    col_data = localizar_coluna(df, "data")
    if col_matricula is None:
        raise ValueError("Não foi encontrada a coluna 'Matrícula'.")
    if col_data is None:
        raise ValueError("Não foi encontrada a coluna 'Início do SLA'.")
    trabalho = df.copy()
    trabalho["_ORDEM_ORIGINAL"] = range(len(trabalho))
    trabalho["_MATRICULA_NORMALIZADA"] = trabalho[col_matricula].map(normalizar_texto)
    sem_matricula = trabalho["_MATRICULA_NORMALIZADA"] == ""
    trabalho_validos = trabalho.loc[~sem_matricula].copy()
    if trabalho_validos.empty:
        raise ValueError("Nenhuma matrícula válida foi encontrada.")
    trabalho_validos["_DATA_SLA"] = converter_datas_robusto(trabalho_validos[col_data])
    contagem = trabalho_validos.groupby("_MATRICULA_NORMALIZADA").size()
    matriculas_duplicadas = contagem[contagem > 1].index
    if len(matriculas_duplicadas) == 0:
        return pd.DataFrame(columns=df.columns), pd.DataFrame(columns=df.columns), 0, 0, [], {}
    candidatos = trabalho_validos[trabalho_validos["_MATRICULA_NORMALIZADA"].isin(matriculas_duplicadas)].copy()
    candidatos["_DATA_INVALIDA"] = candidatos["_DATA_SLA"].isna()
    candidatos = candidatos.sort_values(by=["_MATRICULA_NORMALIZADA", "_DATA_INVALIDA", "_DATA_SLA", "_ORDEM_ORIGINAL"], ascending=[True, True, True, True], kind="stable")
    indices_mantidos = candidatos.groupby("_MATRICULA_NORMALIZADA", sort=False).head(1).index
    indices_duplicidades = candidatos.index.difference(indices_mantidos)
    df_mantidos = candidatos.loc[indices_mantidos].sort_values("_ORDEM_ORIGINAL").drop(columns=["_ORDEM_ORIGINAL", "_MATRICULA_NORMALIZADA", "_DATA_SLA", "_DATA_INVALIDA"], errors="ignore")
    df_duplicidades = candidatos.loc[indices_duplicidades].sort_values("_ORDEM_ORIGINAL").drop(columns=["_ORDEM_ORIGINAL", "_MATRICULA_NORMALIZADA", "_DATA_SLA", "_DATA_INVALIDA"], errors="ignore")
    qtd_matriculas = len(matriculas_duplicadas)
    qtd_duplicidades = len(df_duplicidades)
    col_protocolo = localizar_coluna(candidatos, "protocolo")
    if col_protocolo is None:
        raise ValueError("Não foi encontrada a coluna 'Cód. Protocolo Origem'.")
    protocolos_originais = {}
    for matricula_norm in matriculas_duplicadas:
        linha_original = candidatos[(candidatos["_MATRICULA_NORMALIZADA"] == matricula_norm) & (candidatos.index.isin(indices_mantidos))]
        if not linha_original.empty:
            protocolos_originais[matricula_norm] = linha_original.iloc[0][col_protocolo]
    return df_duplicidades, df_mantidos, qtd_matriculas, qtd_duplicidades, [], protocolos_originais

def obter_valores_unicos(df, coluna):
    if coluna is None or coluna not in df.columns:
        return []
    valores = df[coluna].dropna().astype(str).str.strip()
    valores = [valor for valor in valores if valor and valor.lower() not in ["nan", "none", "null"]]
    unicos = {}
    for valor in valores:
        chave = normalizar_texto(valor)
        if chave and chave not in unicos:
            unicos[chave] = valor
    return sorted(unicos.values(), key=normalizar_texto)

def salvar_lote_excel(df, nome_arquivo=None):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lote")
    return output.getvalue()

# ============================================================
# SESSION STATE
# ============================================================
for key in ["df_api", "df_the", "df_eventos", "df_servicos_api", "df_servicos_the", "lista_lotes", "df_resultado", "df_log", "nome_arquivo_resultado"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "lista_lotes" else []

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### 📦 Gerador de Lotes")
    st.caption(f"Usuário: **{st.session_state.get('usuario_logado', '')}**")
    st.divider()
    if st.button("🏠 Voltar ao Menu de Ferramentas", use_container_width=True):
        st.switch_page("pages/4_Ferramentas_Operacionais.py")
    if st.button("🏠 Voltar ao Hub Principal", use_container_width=True):
        st.switch_page("app.py")

# ============================================================
# INTERFACE PRINCIPAL
# ============================================================
st.title("📦 Gerador de Lotes de Cancelamento")
st.caption("Ferramenta integrada de geração de lotes de cancelamento de O.S.")

# ---------- MODO ----------
modo = st.radio("Modo de operação", ["API", "THE"], horizontal=True, key="modo_operacao")

# ---------- OPERAÇÃO ----------
operacao = st.selectbox(
    "Tipo de operação",
    [
        "FILTRAGEM",
        "DUPLICIDADES",
        "EVENTOS",
        "SERVICOS",
        "ACOMPANHAMENTO",
        "LISTA_RAPIDA"
    ],
    format_func=lambda x: {
        "FILTRAGEM": "1. Filtragem / Cancelamento",
        "DUPLICIDADES": "2. Cancelamento de Duplicidades",
        "EVENTOS": "3. Eventos de Falta de Água",
        "SERVICOS": "4. Serviço em Aberto",
        "ACOMPANHAMENTO": "5. Acompanhamento de Lote",
        "LISTA_RAPIDA": "6. Lista Rápida"
    }[x]
)

st.divider()

# ---------- UPLOADS ----------
st.subheader("📂 Arquivos de entrada")

col_up1, col_up2 = st.columns(2)

with col_up1:
    st.markdown("**Backlog Falta de Água / Reclamação**")
    arquivos_api = st.file_uploader("Upload API (múltiplos)", type=["xlsx", "xlsm"], accept_multiple_files=True, key="up_api")
    arquivos_the = st.file_uploader("Upload THE (múltiplos)", type=["xlsx", "xlsm"], accept_multiple_files=True, key="up_the")

with col_up2:
    st.markdown("**Arquivos auxiliares**")
    arquivo_eventos = st.file_uploader("Planilha de Eventos", type=["xlsx", "xlsm"], key="up_eventos")
    arquivos_serv_api = st.file_uploader("Serviços API", type=["xlsx", "xlsm"], accept_multiple_files=True, key="up_serv_api")
    arquivos_serv_the = st.file_uploader("Serviços THE", type=["xlsx", "xlsm"], accept_multiple_files=True, key="up_serv_the")
    arquivos_lotes = st.file_uploader("Arquivos de Lote (Acompanhamento)", type=["xlsx", "xlsm"], accept_multiple_files=True, key="up_lotes")

# Processar uploads
if arquivos_api:
    dfs = []
    for arq in arquivos_api:
        try:
            dfs.append(ler_excel_bytes(arq.name, arq.read()))
        except Exception as e:
            st.error(f"Erro no arquivo {arq.name}: {e}")
    if dfs:
        st.session_state.df_api, _ = consolidar_lista_dfs(dfs)
        st.success(f"API carregado: {len(st.session_state.df_api)} registros")

if arquivos_the:
    dfs = []
    for arq in arquivos_the:
        try:
            dfs.append(ler_excel_bytes(arq.name, arq.read()))
        except Exception as e:
            st.error(f"Erro no arquivo {arq.name}: {e}")
    if dfs:
        st.session_state.df_the, _ = consolidar_lista_dfs(dfs)
        st.success(f"THE carregado: {len(st.session_state.df_the)} registros")

if arquivo_eventos:
    try:
        st.session_state.df_eventos = ler_excel_bytes(arquivo_eventos.name, arquivo_eventos.read())
        st.success(f"Eventos carregados: {len(st.session_state.df_eventos)} registros")
    except Exception as e:
        st.error(f"Erro eventos: {e}")

if arquivos_serv_api:
    dfs = []
    for arq in arquivos_serv_api:
        try:
            dfs.append(ler_excel_bytes(arq.name, arq.read()))
        except Exception as e:
            st.error(f"Erro: {e}")
    if dfs:
        st.session_state.df_servicos_api, _ = consolidar_lista_dfs(dfs)
        st.success(f"Serviços API: {len(st.session_state.df_servicos_api)} registros")

if arquivos_serv_the:
    dfs = []
    for arq in arquivos_serv_the:
        try:
            dfs.append(ler_excel_bytes(arq.name, arq.read()))
        except Exception as e:
            st.error(f"Erro: {e}")
    if dfs:
        st.session_state.df_servicos_the, _ = consolidar_lista_dfs(dfs)
        st.success(f"Serviços THE: {len(st.session_state.df_servicos_the)} registros")

if arquivos_lotes:
    lista = []
    for arq in arquivos_lotes:
        try:
            df = ler_excel_bytes(arq.name, arq.read())
            lista.append({"nome": arq.name, "df": df})
        except Exception as e:
            st.error(f"Erro lote {arq.name}: {e}")
    if lista:
        st.session_state.lista_lotes = lista
        st.success(f"{len(lista)} arquivo(s) de lote carregado(s)")

# Backlog ativo
df_backlog = st.session_state.df_api if modo == "API" else st.session_state.df_the
df_servicos = st.session_state.df_servicos_api if modo == "API" else st.session_state.df_servicos_the

st.divider()

# ---------- CAMPOS ESPECÍFICOS POR OPERAÇÃO ----------
observacoes = ""
lista_os_texto = ""
motivos_por_arquivo = {}

if operacao in ["FILTRAGEM", "LISTA_RAPIDA"]:
    observacoes = st.text_area("Observações (gravadas no lote)", value="Cancelamento conforme análise operacional.")

if operacao == "LISTA_RAPIDA":
    lista_os_texto = st.text_area("Lista de O.S. / Protocolos (um por linha ou separados por vírgula)")

if operacao == "ACOMPANHAMENTO" and st.session_state.lista_lotes:
    st.markdown("**Motivos por arquivo de lote**")
    for item in st.session_state.lista_lotes:
        motivos_por_arquivo[item["nome"]] = st.text_input(f"Motivo – {item['nome']}", key=f"motivo_{item['nome']}")

# ---------- BOTÃO GERAR ----------
if st.button("📦 Gerar Lote", type="primary", use_container_width=True):
    try:
        if operacao == "EVENTOS":
            if st.session_state.df_eventos is None:
                raise ValueError("Faça o upload da planilha de Eventos.")
            if df_backlog is None or df_backlog.empty:
                raise ValueError(f"Carregue o backlog do modo {modo}.")
            df_saida, avisos, qtd_ev, qtd_os = cruzar_eventos_com_backlog(st.session_state.df_eventos, df_backlog, modo=modo)
            if df_saida.empty:
                st.warning("Nenhuma O.S. identificada pelos eventos.")
            else:
                st.session_state.df_resultado = df_saida
                st.session_state.df_log = pd.DataFrame(avisos) if avisos else None
                st.session_state.nome_arquivo_resultado = f"Lote_Cancelamento_Eventos_{modo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success(f"Lote gerado: {len(df_saida)} O.S.")

        elif operacao == "SERVICOS":
            if df_servicos is None or df_servicos.empty:
                raise ValueError(f"Faça o upload de Serviços do modo {modo}.")
            if df_backlog is None or df_backlog.empty:
                raise ValueError(f"Carregue o backlog de Falta de Água do modo {modo}.")
            df_saida, avisos, qtd_mat, qtd_os = cruzar_falta_com_servicos(df_backlog, df_servicos, modo=modo)
            if df_saida.empty:
                st.warning("Nenhuma O.S. de Falta d'Água com serviço em aberto.")
            else:
                st.session_state.df_resultado = df_saida
                st.session_state.df_log = pd.DataFrame(avisos) if avisos else None
                st.session_state.nome_arquivo_resultado = f"Lote_Cancelamento_ServicoAberto_{modo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success(f"Lote gerado: {len(df_saida)} O.S.")

        elif operacao == "ACOMPANHAMENTO":
            if not st.session_state.lista_lotes:
                raise ValueError("Faça o upload de um ou mais arquivos de Lote.")
            if df_backlog is None or df_backlog.empty:
                raise ValueError(f"Carregue o backlog do modo {modo}.")
            df_lotes_fonte = consolidar_lotes_com_fonte(st.session_state.lista_lotes)
            df_saida, avisos, qtd_lotes, qtd_ok = cruzar_acompanhamento_lote(df_backlog, df_lotes_fonte, motivos_por_arquivo)
            if df_saida.empty:
                st.warning("Nenhuma O.S. do lote encontrada no backlog.")
            else:
                st.session_state.df_resultado = df_saida
                st.session_state.df_log = pd.DataFrame(avisos) if avisos else None
                st.session_state.nome_arquivo_resultado = f"Acompanhamento_Lote_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success(f"Planilha de acompanhamento gerada: {len(df_saida)} O.S.")

        elif operacao == "LISTA_RAPIDA":
            lista_os = extrair_lista_os(lista_os_texto)
            if not lista_os:
                raise ValueError("Cole ao menos um protocolo/O.S.")
            if df_backlog is None or df_backlog.empty:
                raise ValueError(f"Carregue o backlog do modo {modo}.")
            df_saida, avisos, qtd_lista, qtd_ok = cruzar_lista_rapida(df_backlog, lista_os, observacoes, modo_atual=modo)
            if df_saida.empty:
                st.warning("Nenhuma O.S. da lista encontrada no backlog.")
            else:
                st.session_state.df_resultado = df_saida
                st.session_state.df_log = pd.DataFrame(avisos) if avisos else None
                st.session_state.nome_arquivo_resultado = f"Lote_ListaRapida_{modo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success(f"Lote gerado: {len(df_saida)} O.S.")

        elif operacao == "DUPLICIDADES":
            if df_backlog is None or df_backlog.empty:
                raise ValueError(f"Carregue o backlog do modo {modo}.")
            df_duplicidades, df_mantidos, qtd_mat, qtd_dup, avisos_data, protocolos_originais = identificar_duplicidades(df_backlog)
            if df_duplicidades.empty:
                st.success("Nenhuma duplicidade encontrada.")
            else:
                col_protocolo = localizar_coluna(df_duplicidades, "protocolo")
                col_matricula = localizar_coluna(df_duplicidades, "matricula")
                col_cidade = localizar_coluna(df_duplicidades, "cidade")
                registros = []
                for _, linha in df_duplicidades.iterrows():
                    protocolo = linha[col_protocolo]
                    matricula = linha[col_matricula]
                    cidade = linha[col_cidade]
                    mat_norm = normalizar_texto(matricula)
                    protocolo_original = protocolos_originais.get(mat_norm, "")
                    observacao_duplicidade = "Duplicidade com O.S N. " + str(protocolo_original).strip()
                    numero_str, ano_str, numero_int = parse_protocolo(protocolo)
                    zona = 1 if modo == "THE" else obter_zona(cidade)
                    try:
                        ano_pedido = int(ano_str) if ano_str else None
                    except:
                        ano_pedido = None
                    registros.append({
                        "Matricula": matricula, "Zona Ligacao": zona, "Numero Do Pedido": numero_int,
                        "Ano Do Pedido": ano_pedido, "Tipo Encerramento": 6, "Observações": observacao_duplicidade
                    })
                df_saida = pd.DataFrame(registros)
                st.session_state.df_resultado = df_saida
                st.session_state.df_log = None
                st.session_state.nome_arquivo_resultado = f"Lote_Cancelamento_Duplicidades_{modo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                st.success(f"Lote de duplicidades gerado: {len(df_saida)} O.S. (mantidas {len(df_mantidos)} originais)")

        elif operacao == "FILTRAGEM":
            st.info("O módulo de Filtragem completa (com todos os filtros de cidade/bairro/data/hora) será finalizado na próxima etapa. Por enquanto use Lista Rápida ou Duplicidades.")
            # Pode ser expandido depois com os filtros completos

    except Exception as e:
        st.error(f"Erro ao gerar o lote: {e}")

# ---------- RESULTADO E DOWNLOAD ----------
if st.session_state.df_resultado is not None and not st.session_state.df_resultado.empty:
    st.divider()
    st.subheader("📄 Resultado")
    st.dataframe(st.session_state.df_resultado, use_container_width=True)

    excel_bytes = salvar_lote_excel(st.session_state.df_resultado)
    st.download_button(
        label="⬇️ Baixar Lote (Excel)",
        data=excel_bytes,
        file_name=st.session_state.nome_arquivo_resultado or "lote_cancelamento.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    if st.session_state.df_log is not None and not st.session_state.df_log.empty:
        st.markdown("**Log de avisos**")
        st.dataframe(st.session_state.df_log, use_container_width=True)
        log_bytes = salvar_lote_excel(st.session_state.df_log)
        st.download_button(
            label="⬇️ Baixar LOG",
            data=log_bytes,
            file_name=(st.session_state.nome_arquivo_resultado or "lote").replace(".xlsx", "_LOG.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
