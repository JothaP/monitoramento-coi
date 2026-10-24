"""Ambiente de Teste — Consulta Operacional (Teresina).

Página Streamlit única: NÃO precisa de consulta_operacional_teste.py.
Dados SOMENTE LEITURA de dados/matriculas.xls (ou .xlsx), pocos.csv, loggers.csv.
Nenhum dado é gravado; não importa nem executa o antigo Farol V2.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape as html_escape
import math
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

import folium
from folium.plugins import MarkerCluster
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# Habilita importação de auth.py a partir de pages/ mesmo no Streamlit Cloud.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from auth import verificar_autenticacao, tem_acesso_modulo

st.set_page_config(
    page_title="Consulta Operacional | Ambiente de Teste - COI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Exigir tanto sessão válida quanto perfil administrador e permissão de teste.
if not verificar_autenticacao():
    st.error("Sessão não autenticada. Acesse o Hub Central para entrar.")
    st.stop()
if (str(st.session_state.get("perfil", "")).strip().lower() != "admin"
        or not tem_acesso_modulo("teste")):
    st.error("A Consulta Operacional em desenvolvimento é exclusiva do administrador.")
    st.stop()

PASTA_DADOS = RAIZ / "dados"
ARQUIVO_POCOS = PASTA_DADOS / "pocos.csv"
ARQUIVO_LOGGERS = PASTA_DADOS / "loggers.csv"
PASTA_BAIRROS = RAIZ / "geodados" / "municipios"

COLUNAS_MATRICULAS = (
    "CATEGORIA", "NUM_LIGACAO", "BAIRRO",
    "COD_LATITUDE", "COD_LONGITUDE", "END_LIGACAO",
)
COLUNAS_POCOS = (
    "ID_POCO", "IDENTIFICACAO_ATIVO", "NOME_POCO", "MUNICIPIO", "LATITUDE", "LONGITUDE"
)
COLUNAS_LOGGERS = (
    "ID_LOGGER", "IDENTIFICACAO_ATIVO", "ENDERECO", "MUNICIPIO", "LATITUDE", "LONGITUDE"
)


def _arquivo_matriculas() -> Path | None:
    """Aceita .xls legado e .xlsx; retorna só dados realmente presentes."""
    for nome in ("matriculas.xls", "matriculas.xlsx"):
        arquivo = PASTA_DADOS / nome
        if arquivo.is_file():
            return arquivo
    # Evita falhas se o GitHub tiver mantido variação de capitalização.
    if PASTA_DADOS.is_dir():
        for arquivo in sorted(PASTA_DADOS.iterdir()):
            if arquivo.is_file() and arquivo.name.lower() in ("matriculas.xls", "matriculas.xlsx"):
                return arquivo
    return None


def _normalizar_texto(value: object) -> str:
    texto = unicodedata.normalize("NFKD", str(value or "").strip().upper())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _normalizar_cabecalho(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _normalizar_texto(value))


def _matricula(value: object) -> str:
    """Mantém zeros à esquerda; corrige apenas a aparência '123.0' do Excel."""
    valor = str(value if value is not None else "").strip()
    if re.fullmatch(r"\d+\.0+", valor):
        return valor.split(".", 1)[0]
    return valor


def _coordenada(value: object, tipo: str) -> float | None:
    if value is None or pd.isna(value):
        return None
    bruto = str(value).strip().replace(" ", "")
    if not bruto:
        return None
    if "," in bruto and "." in bruto:
        bruto = bruto.replace(".", "").replace(",", ".") if bruto.rfind(",") > bruto.rfind(".") else bruto.replace(",", "")
    else:
        bruto = bruto.replace(",", ".")
    try:
        valor = float(bruto)
    except ValueError:
        return None
    if not math.isfinite(valor) or valor == 0:
        return None
    if tipo == "lat" and not -90 <= valor <= 90:
        return None
    if tipo == "lon" and not -180 <= valor <= 180:
        return None
    return valor


def _assinatura(caminho: Path) -> tuple[str, int, int]:
    stat = caminho.stat()
    return str(caminho), stat.st_size, stat.st_mtime_ns


def _validar_colunas(df: pd.DataFrame, esperadas: tuple[str, ...], origem: str) -> pd.DataFrame:
    mapa = {_normalizar_cabecalho(c): c for c in df.columns}
    faltantes = [c for c in esperadas if _normalizar_cabecalho(c) not in mapa]
    if faltantes:
        raise ValueError(f"{origem}: colunas não encontradas: {', '.join(faltantes)}.")
    selecionadas = [mapa[_normalizar_cabecalho(c)] for c in esperadas]
    resultado = df.loc[:, selecionadas].copy()
    resultado.columns = list(esperadas)
    return resultado.fillna("")


def _preparar_matriculas(df: pd.DataFrame) -> pd.DataFrame:
    dados = _validar_colunas(df, COLUNAS_MATRICULAS, "Cadastro de matrículas")
    dados["NUM_LIGACAO"] = dados["NUM_LIGACAO"].map(_matricula)
    dados["_lat"] = dados["COD_LATITUDE"].map(lambda x: _coordenada(x, "lat"))
    dados["_lon"] = dados["COD_LONGITUDE"].map(lambda x: _coordenada(x, "lon"))
    return dados


@st.cache_data(show_spinner=False, max_entries=3)
def _ler_matriculas_excel(assinatura: tuple[str, int, int]) -> pd.DataFrame:
    """Carrega Excel legado (.xls/xlrd) ou moderno (.xlsx/openpyxl) com cache por mtime."""
    caminho = Path(assinatura[0])
    engine = "xlrd" if caminho.suffix.lower() == ".xls" else "openpyxl"
    try:
        # dtype=str evita converter identificadores em floats e mantém zeros à esquerda
        base = pd.read_excel(caminho, dtype=str, keep_default_na=False, engine=engine)
    except ImportError as erro:
        dependencia = "xlrd>=2.0.1" if engine == "xlrd" else "openpyxl"
        raise RuntimeError(
            f"Falta a dependência {dependencia} para ler {caminho.name}. "
            f"Adicione {dependencia} ao requirements.txt e publique novamente."
        ) from erro
    return _preparar_matriculas(base)


@st.cache_data(show_spinner=False, max_entries=6)
def _ler_ativos_csv(assinatura: tuple[str, int, int], tipo: str) -> pd.DataFrame:
    arquivo = assinatura[0]
    colunas = COLUNAS_POCOS if tipo == "Poço / Ativo" else COLUNAS_LOGGERS
    try:
        df = pd.read_csv(arquivo, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{Path(arquivo).name}: salve o CSV como UTF-8.") from exc
    dados = _validar_colunas(df, colunas, Path(arquivo).name)
    dados["_lat"] = dados["LATITUDE"].map(lambda v: _coordenada(v, "lat"))
    dados["_lon"] = dados["LONGITUDE"].map(lambda v: _coordenada(v, "lon"))
    dados = dados.loc[dados["_lat"].notna() & dados["_lon"].notna()].copy()
    dados["_tipo"] = tipo
    dados["_nome"] = dados["NOME_POCO"] if tipo == "Poço / Ativo" else dados["ENDERECO"]
    return dados


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def _grade_espacial(df: pd.DataFrame, celula: float = 0.01):
    grade: dict[tuple[int, int], list[tuple[int, float, float]]] = defaultdict(list)
    registros = df.to_dict("records")
    for indice, r in enumerate(registros):
        lat, lon = float(r["_lat"]), float(r["_lon"])
        grade[math.floor(lat / celula), math.floor(lon / celula)].append((indice, lat, lon))
    return grade, registros


def _buscar_proximos(grade, registros, lat: float, lon: float, raio_m: float, celula: float = 0.01):
    delta_lat = raio_m / 110000.0 + 1e-8
    cosseno = max(0.000001, math.cos(math.radians(min(89.999, abs(lat) + delta_lat))))
    delta_lon = raio_m / (110000.0 * cosseno) + 1e-8
    for ix in range(math.floor((lat - delta_lat) / celula), math.floor((lat + delta_lat) / celula) + 1):
        for iy in range(math.floor((lon - delta_lon) / celula), math.floor((lon + delta_lon) / celula) + 1):
            for i, alat, alon in grade.get((ix, iy), ()):
                distancia = _distance_m(lat, lon, alat, alon)
                if distancia <= raio_m:
                    yield i, registros[i], distancia


def _consultar_proximidade(clientes: pd.DataFrame, bases: dict[str, pd.DataFrame], raio: int):
    resultados = []
    ids_mapa: set[tuple[str, str, str]] = set()
    ativos_mapa = []
    for tipo, base in bases.items():
        if base.empty:
            continue
        grade, registros = _grade_espacial(base)
        for _, cliente in clientes.iterrows():
            lat, lon = float(cliente["_lat"]), float(cliente["_lon"])
            for _, ativo, distancia in _buscar_proximos(grade, registros, lat, lon, raio):
                identificacao = str(ativo.get("IDENTIFICACAO_ATIVO", "")).strip()
                nome = str(ativo.get("_nome", "")).strip()
                resultados.append({
                    "Matrícula": cliente["NUM_LIGACAO"],
                    "Tipo": tipo,
                    "Identificação": identificacao,
                    "Nome / endereço": nome,
                    "Distância (m)": round(distancia, 1),
                })
                # Mesmo ativo pode ser próximo de várias matrículas; exibir apenas um marcador.
                chave = (tipo, str(ativo.get("ID_POCO") or ativo.get("ID_LOGGER") or identificacao),
                         f"{ativo['_lat']:.6f},{ativo['_lon']:.6f}")
                if chave not in ids_mapa:
                    ids_mapa.add(chave)
                    ativos_mapa.append(ativo)
    resultado_df = pd.DataFrame(resultados,
        columns=["Matrícula", "Tipo", "Identificação", "Nome / endereço", "Distância (m)"])
    if not resultado_df.empty:
        resultado_df = resultado_df.sort_values(["Matrícula", "Distância (m)", "Tipo"], kind="stable")
    return resultado_df, ativos_mapa


def _interpretar_pesquisa(texto: str) -> tuple[list[str], list[str]]:
    valores = re.split(r"[,;\s]+", texto.strip())
    vistos = set()
    matriculas = []
    invalidos = []
    for valor in valores:
        if not valor:
            continue
        numero = _matricula(valor)
        if not numero.isdecimal():
            invalidos.append(valor)
        elif numero not in vistos:
            vistos.add(numero)
            matriculas.append(numero)
    return matriculas, invalidos


def _popup_cliente(linha: pd.Series) -> str:
    campos = [
        ("Matrícula", linha["NUM_LIGACAO"]), ("Categoria", linha["CATEGORIA"]),
        ("Bairro", linha["BAIRRO"]), ("Endereço", linha["END_LIGACAO"]),
        ("Latitude", linha["COD_LATITUDE"]), ("Longitude", linha["COD_LONGITUDE"]),
    ]
    return "<div style='min-width:245px'>" + "".join(
        f"<div><b>{html_escape(str(k))}:</b> {html_escape(str(v))}</div>" for k, v in campos
    ) + "</div>"


def _popup_ativo(ativo: dict) -> str:
    return "<div style='min-width:190px'>" + "".join(
        f"<div><b>{html_escape(k)}:</b> {html_escape(str(v))}</div>"
        for k, v in (("Tipo", ativo.get("_tipo", "")),
                     ("Identificação", ativo.get("IDENTIFICACAO_ATIVO", "")),
                     ("Nome / endereço", ativo.get("_nome", "")))
    ) + "</div>"


def _caminho_bairros_teresina() -> Path | None:
    if not PASTA_BAIRROS.is_dir():
        return None
    candidatos = [p for p in PASTA_BAIRROS.iterdir()
                  if p.is_file() and p.suffix.lower() in {".gpkg", ".kml", ".kmz"}
                  and "TERESINA" in _normalizar_texto(p.stem)]
    prioridade = {".gpkg": 0, ".kmz": 1, ".kml": 2}
    if candidatos:
        return sorted(candidatos, key=lambda p: (prioridade[p.suffix.lower()], p.name))[0]
    legado = RAIZ / "TERESINA.kmz"
    return legado if legado.is_file() else None


@st.cache_data(show_spinner=False, max_entries=2)
def _bairros_geograficos(assinatura: tuple[str, int, int]) -> list[dict]:
    """Lê polígonos de bairro de Teresina; mantém separado do Farol V2."""
    from pyproj import CRS, Transformer
    from shapely import wkb
    from shapely.geometry import Polygon
    from shapely.ops import transform

    caminho = Path(assinatura[0])
    bairros = []
    if caminho.suffix.lower() == ".gpkg":
        with sqlite3.connect(f"file:{caminho}?mode=ro", uri=True) as banco:
            tabelas = banco.execute("SELECT table_name, srs_id FROM gpkg_contents WHERE data_type='features'").fetchall()
            for tabela, srs_id in tabelas:
                campo_geo = banco.execute(
                    "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name=?", (tabela,)
                ).fetchone()
                if not campo_geo:
                    continue
                nomes = [c[1] for c in banco.execute('PRAGMA table_info("' + tabela.replace('"', '""') + '")')]
                campos = {_normalizar_cabecalho(c): c for c in nomes}
                campo_nome = next((campos[c] for c in ("NMBAIRRO", "NOMEBAIRRO", "BAIRRO", "NOME") if c in campos), None)
                campo_municipio = next((campos[c] for c in ("NMMUN", "MUNICIPIO", "NOMEMUNICIPIO", "CIDADE") if c in campos), None)
                if not campo_nome:
                    continue
                nome_geom, srs_geom = campo_geo
                linha_crs = banco.execute(
                    "SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys WHERE srs_id=?",
                    (srs_geom or srs_id,),
                ).fetchone()
                if not linha_crs:
                    continue
                org, cod, wkt_crs = linha_crs
                try:
                    origem = CRS.from_user_input(f"{org}:{cod}") if org and cod else CRS.from_wkt(wkt_crs)
                except Exception:
                    origem = CRS.from_wkt(wkt_crs)
                conversor = None if origem.equals(CRS.from_epsg(4326)) else Transformer.from_crs(origem, 4326, always_xy=True)
                citar = lambda s: '"' + s.replace('"', '""') + '"'
                cols = [nome_geom, campo_nome] + ([campo_municipio] if campo_municipio else [])
                consulta = f"SELECT {', '.join(citar(c) for c in cols)} FROM {citar(tabela)}"
                for registro in banco.execute(consulta):
                    blob, nome, *mun = registro
                    if not blob or not nome or (mun and mun[0] and _normalizar_texto(mun[0]) != "TERESINA"):
                        continue
                    blob = bytes(blob)
                    if blob[:2] != b"GP" or len(blob) < 8:
                        continue
                    envelope = (blob[3] >> 1) & 7
                    tamanhos = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
                    if envelope not in tamanhos:
                        continue
                    geo = wkb.loads(blob[8 + tamanhos[envelope]:])
                    if conversor:
                        geo = transform(conversor.transform, geo)
                    for area in ([geo] if geo.geom_type == "Polygon" else list(geo.geoms) if geo.geom_type == "MultiPolygon" else []):
                        if not area.is_empty:
                            simples = area.simplify(0.00007, preserve_topology=True)
                            visual = simples if simples.geom_type == "Polygon" else area
                            bairros.append({"nome": str(nome), "coords": [(y, x) for x, y in visual.exterior.coords],
                                            "limites": area.bounds, "geometria": area})
    else:
        if caminho.suffix.lower() == ".kmz":
            with zipfile.ZipFile(caminho) as zipado:
                kmls = [n for n in zipado.namelist() if n.lower().endswith(".kml")]
                if not kmls:
                    return []
                xml = zipado.read(kmls[0])
        else:
            xml = caminho.read_bytes()
        root = ET.fromstring(xml)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        for lugar in root.findall(".//k:Placemark", ns):
            el_nome = lugar.find("k:name", ns)
            nome = el_nome.text.strip() if el_nome is not None and el_nome.text else ""
            if not nome:
                continue
            for poligono in lugar.findall(".//k:Polygon", ns):
                ring = poligono.find("k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
                if ring is None or not ring.text:
                    continue
                pontos = []
                for termo in ring.text.split():
                    try:
                        longitude, latitude = (float(x) for x in termo.split(",")[:2])
                        pontos.append((longitude, latitude))
                    except (ValueError, TypeError):
                        continue
                if len(pontos) >= 3:
                    area = Polygon(pontos)
                    if not area.is_empty:
                        simples = area.simplify(0.00007, preserve_topology=True)
                        visual = simples if simples.geom_type == "Polygon" else area
                        bairros.append({"nome": nome, "coords": [(y, x) for x, y in visual.exterior.coords],
                                        "limites": area.bounds, "geometria": area})
    return bairros


def _mapa_consulta(clientes: pd.DataFrame, ativos: list[dict], raio: int,
                   bairros: list[dict], mostrar_bairros: bool) -> folium.Map:
    latitudes = clientes["_lat"].astype(float).tolist()
    longitudes = clientes["_lon"].astype(float).tolist()
    mapa = folium.Map(location=[sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)],
                      zoom_start=14, control_scale=True, tiles="OpenStreetMap")

    if mostrar_bairros and bairros:
        grupo = folium.FeatureGroup(name="Limites de bairros", show=True)
        # Camada é apenas de referência: não confundir bairro com região de influência.
        for bairro in bairros:
            folium.Polygon(
                locations=bairro["coords"], color="#578bba", weight=1.5,
                fill=True, fill_color="#88b8de", fill_opacity=0.06,
                tooltip=f"Bairro: {bairro['nome']}",
            ).add_to(grupo)
        grupo.add_to(mapa)

    grupo_clientes = folium.FeatureGroup(name="Matrículas", show=True)
    aglomerador = MarkerCluster(name="Matrículas", overlay=False, control=False).add_to(grupo_clientes)
    for _, linha in clientes.iterrows():
        lat, lon = float(linha["_lat"]), float(linha["_lon"])
        folium.Marker(
            [lat, lon], tooltip=f"Matrícula: {linha['NUM_LIGACAO']}",
            popup=folium.Popup(_popup_cliente(linha), max_width=370),
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
        ).add_to(aglomerador)
        folium.Circle([lat, lon], radius=raio, color="#227ab6", fill=False,
                      weight=1, opacity=0.30, tooltip=f"Raio de busca: {raio} m").add_to(grupo_clientes)
    grupo_clientes.add_to(mapa)

    for tipo, cor, icone in (("Poço / Ativo", "orange", "tint"), ("Logger", "purple", "signal")):
        grupo = folium.FeatureGroup(name=tipo + " próximo(s)", show=True)
        for ativo in ativos:
            if ativo.get("_tipo") != tipo:
                continue
            folium.Marker(
                [float(ativo["_lat"]), float(ativo["_lon"])],
                tooltip=f"{tipo}: {ativo.get('IDENTIFICACAO_ATIVO', '')}",
                popup=folium.Popup(_popup_ativo(ativo), max_width=360),
                icon=folium.Icon(color=cor, icon=icone, prefix="fa"),
            ).add_to(grupo)
        grupo.add_to(mapa)

    if len(clientes) > 1:
        mapa.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]], padding=(45, 45))
    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def exibir_consulta_operacional() -> None:
    """Página exclusiva da Consulta Operacional — sem Farol V2."""
    if not verificar_autenticacao() or not tem_acesso_modulo("teste") or str(st.session_state.get("perfil", "")).lower() != "admin":
        st.error("A Consulta Operacional em desenvolvimento é exclusiva do administrador.")
        st.stop()

    st.title("🔍 Consulta Operacional")
    st.caption("🧪 Protótipo no Ambiente de Teste • Teresina • Consultas somente leitura • Sem histórico")

    arquivo_matriculas = _arquivo_matriculas()
    if arquivo_matriculas is None:
        st.error(
            "Base de matrículas ausente. Adicione dados/matriculas.xls "
            "(ou dados/matriculas.xlsx) à pasta dados/ em um repositório privado."
        )
        st.stop()
    try:
        with st.spinner("Lendo o cadastro de matrículas..."):
            base = _ler_matriculas_excel(_assinatura(arquivo_matriculas))
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as erro:
        st.error(f"Não foi possível carregar dados/{arquivo_matriculas.name}: {erro}")
        st.stop()
    st.caption(
        f"Base de consulta: dados/{arquivo_matriculas.name} • "
        f"{len(base):,} registros carregados".replace(",", ".")
    )

    with st.form("consulta_operacional_busca"):
        pesquisa = st.text_area("Matrícula(s)", value="12001066\n12002518\n12004227",
                                help="Informe uma ou várias matrículas, separadas por vírgula, espaço ou quebra de linha.",
                                height=105, key="consulta_operacional_entrada")
        c1, c2 = st.columns([2, 1])
        with c1:
            raio = st.number_input("Raio de busca dos ativos e loggers (metros)",
                                   min_value=50, max_value=5000, value=750, step=50,
                                   key="consulta_operacional_raio")
        with c2:
            exibir_bairros = st.checkbox("Exibir limites dos bairros", value=True,
                                        key="consulta_operacional_bairros")
        executar = st.form_submit_button("🔎 Pesquisar matrículas", type="primary", use_container_width=True)

    if executar:
        codigos, invalidos = _interpretar_pesquisa(pesquisa)
        if invalidos:
            st.error("Valores inválidos na pesquisa: " + ", ".join(invalidos[:10]) + ". Use apenas números de matrícula.")
            st.session_state.pop("consulta_operacional_consulta", None)
        elif not codigos:
            st.warning("Informe ao menos uma matrícula para consultar.")
            st.session_state.pop("consulta_operacional_consulta", None)
        elif len(codigos) > 200:
            st.warning("Para manter o mapa responsivo, pesquise até 200 matrículas por consulta nesta versão de testes.")
            st.session_state.pop("consulta_operacional_consulta", None)
        else:
            # Somente a consulta atual fica na sessão do navegador; não grava histórico.
            st.session_state["consulta_operacional_consulta"] = (codigos, int(raio), bool(exibir_bairros))

    consulta = st.session_state.get("consulta_operacional_consulta")
    if not consulta:
        st.info("Informe a(s) matrícula(s) e clique em Pesquisar para visualizar o mapa e os ativos próximos.")
        return

    matriculas, raio_consulta, mostrar_bairros = consulta
    encontrados = base.loc[base["NUM_LIGACAO"].isin(matriculas)].copy()
    presentes = set(encontrados["NUM_LIGACAO"])
    ausentes = [m for m in matriculas if m not in presentes]
    validos = encontrados.loc[encontrados["_lat"].notna() & encontrados["_lon"].notna()].copy()
    invalidos = encontrados.loc[encontrados["_lat"].isna() | encontrados["_lon"].isna()].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Matrículas localizadas", len(presentes))
    c2.metric("Com coordenadas válidas", int(validos["NUM_LIGACAO"].nunique()))
    c3.metric("Não encontradas", len(ausentes))

    if ausentes:
        st.warning("Matrícula(s) não encontrada(s): " + ", ".join(ausentes))
    if not invalidos.empty:
        st.warning("Encontradas sem coordenadas válidas: " + ", ".join(sorted(invalidos["NUM_LIGACAO"].unique())))
    duplicadas = encontrados["NUM_LIGACAO"][encontrados["NUM_LIGACAO"].duplicated(keep=False)].unique()
    if len(duplicadas):
        st.warning("Matrículas com registros duplicados na base: " + ", ".join(duplicadas))

    if not encontrados.empty:
        st.subheader("📋 Dados cadastrais das matrículas")
        st.dataframe(encontrados.loc[:, list(COLUNAS_MATRICULAS)], hide_index=True,
                     use_container_width=True)
    if validos.empty:
        st.info("Nenhuma matrícula com coordenadas geográficas válidas para exibir no mapa.")
        return

    bases: dict[str, pd.DataFrame] = {}
    for tipo, caminho in (("Poço / Ativo", ARQUIVO_POCOS), ("Logger", ARQUIVO_LOGGERS)):
        if not caminho.is_file():
            st.warning(f"{caminho.relative_to(RAIZ)} não encontrado; {tipo.lower()}(s) não serão exibidos.")
            continue
        try:
            bases[tipo] = _ler_ativos_csv(_assinatura(caminho), tipo)
        except (OSError, ValueError, pd.errors.ParserError) as erro:
            st.warning(f"Não foi possível carregar {caminho.name}: {erro}")

    proximidade, ativos_mapa = _consultar_proximidade(validos, bases, raio_consulta)
    qtd_pocos = sum(a.get("_tipo") == "Poço / Ativo" for a in ativos_mapa)
    qtd_loggers = sum(a.get("_tipo") == "Logger" for a in ativos_mapa)
    c4, c5, c6 = st.columns(3)
    c4.metric("Poços / ativos próximos", qtd_pocos)
    c5.metric("Loggers próximos", qtd_loggers)
    c6.metric("Raio de pesquisa", f"{raio_consulta} m")

    bairros = []
    if mostrar_bairros:
        arquivo_bairros = _caminho_bairros_teresina()
        if arquivo_bairros:
            try:
                bairros = _bairros_geograficos(_assinatura(arquivo_bairros))
            except Exception as erro:
                st.warning(f"Não foi possível carregar os limites dos bairros: {erro}")
        else:
            st.caption("Camada de bairros indisponível: nenhum arquivo geográfico de Teresina foi encontrado.")

    st.subheader("🗺️ Contexto geográfico das matrículas")
    st.caption("Azul: matrículas • Laranja: poços / ativos • Roxo: loggers • "
               "Círculos: raio de proximidade. Proximidade não comprova abastecimento pelo ativo.")
    mapa = _mapa_consulta(validos, ativos_mapa, raio_consulta, bairros, mostrar_bairros)
    st_folium(mapa, width=None, height=640,
              returned_objects=[], key="consulta_operacional_mapa")

    st.subheader("📍 Ativos e loggers próximos por matrícula")
    if proximidade.empty:
        st.info(f"Nenhum ativo ou logger encontrado dentro de {raio_consulta} m das matrículas localizadas.")
    else:
        st.dataframe(proximidade, hide_index=True, use_container_width=True)
        st.caption("As distâncias são medidas em linha reta entre coordenadas; "
                   "o mesmo equipamento pode aparecer vinculado a mais de uma matrícula.")

    st.subheader("🌐 Região de influência do abastecimento")
    st.info("Aguardando a base geográfica dos polígonos de influência dos sistemas de abastecimento. "
            "Os limites de bairros não são utilizados como substitutos dessas regiões.")
    st.caption("Cadastro de rede: funcionalidade futura, fora do escopo deste protótipo.")


exibir_consulta_operacional()
