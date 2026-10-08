"""Gerador de webmap HTML interativo multi-AOI com dashboard analitico.

Produz ``webmap/index.html`` autocontido com:

- Mapa Leaflet com camadas Google e Microsoft (toggle)
- Seletor dropdown para alternar entre AOIs sem recarregar a pagina
- Painel lateral com tabs: Visao Geral, Analise, Detalhe
- KPIs, graficos Chart.js (donut + histograma), narrativa comparativa
- Popups ricos com fonte, area em m2 e hectares
- Estilo visual: Barlow Condensed + Karla, paleta escura rica

Fluxo de geracao
----------------

::

    gerar_webmap_multi(con, aois_e_tabelas, output_dir)
    |
    |-- para cada AOI:
    |     exporta GeoJSON por fonte com area_m2 por footprint
    |     em webmap/data/<aoi_slug>_<fonte>.geojson
    |
    |-- para cada AOI: computa ResumoAOI
    |
    |-- renderiza webmap/index.html com todas as AOIs
    |   no mesmo arquivo (switcher dropdown no painel)

Diferencas vs versao anterior
-----------------------------

- **Multi-AOI**: um unico HTML carrega todas as AOIs e permite
  alternar via dropdown (nao precisa regenerar)
- **Dashboard**: tabs no painel lateral com KPIs, graficos Chart.js
  e narrativa comparativa
- **Popups ricos**: cada footprint tem area_m2 e hectares nos
  properties, mostrado no popup com formato legivel
- **Estilo**: paleta inspirada no projeto CHIRPS do autor
  (Barlow Condensed + Karla, fundo escuro, tabs azuladas)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import duckdb

from obr_explorer import analysis, config
from obr_explorer import duckdb_client as ddb
from obr_explorer.aoi import AOI

logger = logging.getLogger(__name__)


# =============================================================================
# Cores oficiais das fontes
# =============================================================================
COR_GOOGLE: str = "#4285F4"
"""Azul caracteristico do Google (brand hex)."""

COR_MICROSOFT: str = "#00A4EF"
"""Azul caracteristico da Microsoft (brand hex)."""

CORES_FONTE: dict[str, str] = {
    config.SOURCE_GOOGLE: COR_GOOGLE,
    config.SOURCE_MICROSOFT: COR_MICROSOFT,
}


# =============================================================================
# Validacao
# =============================================================================
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validar_identificador(nome: str, contexto: str = "identificador") -> str:
    if not _IDENTIFICADOR_VALIDO.match(nome):
        raise ValueError(
            f"{contexto} invalido: {nome!r}. "
            "Aceita apenas letras, digitos e underscore, comecando com letra ou underscore."
        )
    return nome


# =============================================================================
# Fator de conversao graus^2 -> m^2 (equatorial)
# =============================================================================
_GRAU_EM_M2_EQUATORIAL = 111_000.0 * 111_000.0


# =============================================================================
# API publica — compatibilidade com versao anterior (uma AOI)
# =============================================================================
def gerar_webmap_comparativo(
    con: duckdb.DuckDBPyConnection,
    tabela_recorte: str,
    aoi: AOI,
    output_dir: Path | None = None,
    min_area_m2: float | None = None,
    simplify_tolerance: float | None = None,
    coluna_geom: str = "geom",
    coluna_fonte: str = config.COLUMN_SOURCE,
) -> Path:
    """Gera webmap para uma unica AOI (compatibilidade).

    Delegacao para :func:`gerar_webmap_multi` com uma unica AOI.
    Para novos usos, prefira ``gerar_webmap_multi`` diretamente.
    """
    return gerar_webmap_multi(
        con,
        aois_e_tabelas=[(aoi, tabela_recorte)],
        output_dir=output_dir,
        min_area_m2=min_area_m2,
        simplify_tolerance=simplify_tolerance,
        coluna_geom=coluna_geom,
        coluna_fonte=coluna_fonte,
    )


# =============================================================================
# API publica — webmap multi-AOI
# =============================================================================
def gerar_webmap_multi(
    con: duckdb.DuckDBPyConnection,
    aois_e_tabelas: list[tuple[AOI, str]],
    output_dir: Path | None = None,
    min_area_m2: float | None = None,
    simplify_tolerance: float | None = None,
    coluna_geom: str = "geom",
    coluna_fonte: str = config.COLUMN_SOURCE,
) -> Path:
    """Gera webmap HTML unico com switcher para multiplas AOIs.

    Parameters
    ----------
    con : DuckDBPyConnection
    aois_e_tabelas : list of (AOI, str)
        Lista de tuplas ``(aoi, nome_tabela_recorte)`` para cada AOI
        a incluir no webmap.
    output_dir : Path, optional
        Diretorio de output. Default: ``config.WEBMAP_DIR``.
    min_area_m2 : float, optional
        Filtro de area minima aplicado uniformemente a todas as AOIs.
    simplify_tolerance : float, optional
        Simplificacao geometrica aplicada uniformemente.
    coluna_geom, coluna_fonte : str

    Returns
    -------
    Path
        Caminho do ``index.html`` gerado.
    """
    if not aois_e_tabelas:
        raise ValueError("aois_e_tabelas vazia — passe pelo menos uma AOI.")

    output_dir = Path(output_dir) if output_dir else config.WEBMAP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # Para cada AOI: exporta GeoJSONs enriquecidos + computa resumo
    aois_payload: list[dict[str, Any]] = []
    for aoi, tabela_recorte in aois_e_tabelas:
        _validar_identificador(tabela_recorte, "nome de tabela")
        logger.info("[WEBMAP] Processando AOI %s", aoi.nome)

        arquivos_fonte: dict[str, str] = {}
        for fonte in (config.SOURCE_GOOGLE, config.SOURCE_MICROSOFT):
            tabela_fonte = f"{tabela_recorte}_fonte_{fonte}"
            _criar_subset_por_fonte_enriquecido(
                con,
                tabela_recorte=tabela_recorte,
                tabela_destino=tabela_fonte,
                fonte=fonte,
                coluna_geom=coluna_geom,
                coluna_fonte=coluna_fonte,
                lat_media=(aoi.bounds[1] + aoi.bounds[3]) / 2,
                min_area_m2=min_area_m2,
                simplify_tolerance=simplify_tolerance,
            )
            caminho = data_dir / f"{aoi.nome}_{fonte}.geojson"
            # Exporta com todas as colunas (geom + area_m2) para popups ricos
            ddb.exportar_geojson(
                con, tabela_fonte, caminho,
                colunas=("geom", "area_m2"),
            )
            arquivos_fonte[fonte] = f"data/{caminho.name}"

        # Resumo estatistico
        _, miny, _, maxy = aoi.bounds
        lat_media = (miny + maxy) / 2
        resumo = analysis.resumo_aoi(
            con, tabela_recorte,
            aoi_nome=aoi.nome_exibicao,
            coluna_geom=coluna_geom,
            coluna_fonte=coluna_fonte,
            lat_media=lat_media,
        )

        # Histograma de areas (buckets fixos)
        histograma = _computar_histograma_areas(
            con, tabela_recorte, coluna_geom=coluna_geom,
            coluna_fonte=coluna_fonte, lat_media=lat_media,
        )

        aois_payload.append({
            "slug": aoi.nome,
            "nome_exibicao": aoi.nome_exibicao,
            "properties": _properties_para_json(aoi.properties),
            "bounds_sw": [miny, aoi.bounds[0]],
            "bounds_ne": [maxy, aoi.bounds[2]],
            "arquivos_fonte": arquivos_fonte,
            "resumo": resumo.to_dict(),
            "histograma": histograma,
            "area_km2_oficial": float(
                aoi.properties.get("area_km2_oficial", aoi.area_km2_aproximada)
            ),
        })

    # Renderiza HTML unico com todas as AOIs
    contexto = {
        "aois": aois_payload,
        "cor_google": COR_GOOGLE,
        "cor_microsoft": COR_MICROSOFT,
        "min_area_m2": min_area_m2,
        "simplify_tolerance": simplify_tolerance,
    }
    html = _renderizar_template_multi(contexto)
    output_html = output_dir / "index.html"
    output_html.write_text(html, encoding="utf-8")

    logger.info("[OK] Webmap multi-AOI gerado: %s (%d AOIs)", output_html, len(aois_payload))
    return output_html


def _properties_para_json(props: dict[str, Any]) -> dict[str, Any]:
    """Converte properties da AOI para formato serializavel (floats puros)."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, (int, str, bool)) or v is None:
            out[k] = v
        else:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = str(v)
    return out


# =============================================================================
# Subset enriquecido com area_m2 por footprint
# =============================================================================
def _criar_subset_por_fonte_enriquecido(
    con: duckdb.DuckDBPyConnection,
    tabela_recorte: str,
    tabela_destino: str,
    fonte: str,
    coluna_geom: str,
    coluna_fonte: str,
    lat_media: float,
    min_area_m2: float | None,
    simplify_tolerance: float | None,
) -> int:
    """Cria subset por fonte com coluna ``area_m2`` adicional.

    A area e calculada via ``ST_Area`` (que retorna graus^2 em WGS84)
    e convertida para m^2 usando aproximacao equatorial ajustada pela
    latitude media da AOI. Precisao de area para AOIs no Brasil: ~2%.
    """
    _validar_identificador(tabela_destino, "tabela destino")
    if fonte not in config.FONTES_VALIDAS:
        raise ValueError(
            f"Fonte invalida: {fonte!r}. Aceita: {config.FONTES_VALIDAS}"
        )

    import math

    fator = _GRAU_EM_M2_EQUATORIAL * math.cos(math.radians(lat_media))

    # Geometria base, opcionalmente simplificada
    if simplify_tolerance is not None:
        if simplify_tolerance <= 0:
            raise ValueError(
                f"simplify_tolerance deve ser positivo: {simplify_tolerance!r}"
            )
        geom_expr = (
            f"ST_SimplifyPreserveTopology({coluna_geom}, {simplify_tolerance})"
        )
    else:
        geom_expr = coluna_geom

    where_clauses = [f"{coluna_fonte} = '{fonte}'"]
    if min_area_m2 is not None:
        if min_area_m2 <= 0:
            raise ValueError(
                f"min_area_m2 deve ser positivo: {min_area_m2!r}"
            )
        min_graus2 = float(min_area_m2) / fator
        where_clauses.append(f"ST_Area({coluna_geom}) >= {min_graus2}")

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        CREATE OR REPLACE TABLE {tabela_destino} AS
          SELECT
            {geom_expr} AS geom,
            ROUND(ST_Area({coluna_geom}) * {fator}, 2) AS area_m2
          FROM {tabela_recorte}
          WHERE {where_sql}
    """
    logger.info(
        "[WEBMAP] Criando subset %s (fonte=%s, min_area=%s, simplify=%s)",
        tabela_destino, fonte, min_area_m2, simplify_tolerance,
    )
    con.execute(sql)
    n = ddb.contar_registros(con, tabela_destino)
    logger.info("[OK] %s: %d footprints", tabela_destino, n)
    return n


# Manter a antiga funcao como compat (sem area_m2) para quem usar via API
def _criar_subset_por_fonte(
    con: duckdb.DuckDBPyConnection,
    tabela_recorte: str,
    tabela_destino: str,
    fonte: str,
    coluna_geom: str,
    coluna_fonte: str,
    min_area_m2: float | None,
    simplify_tolerance: float | None,
) -> int:
    """Compat: cria subset por fonte sem coluna area_m2 (versao antiga)."""
    _validar_identificador(tabela_destino, "tabela destino")
    if fonte not in config.FONTES_VALIDAS:
        raise ValueError(
            f"Fonte invalida: {fonte!r}. Aceita: {config.FONTES_VALIDAS}"
        )

    if simplify_tolerance is not None:
        if simplify_tolerance <= 0:
            raise ValueError(
                f"simplify_tolerance deve ser positivo: {simplify_tolerance!r}"
            )
        geom_expr = (
            f"ST_SimplifyPreserveTopology({coluna_geom}, {simplify_tolerance})"
        )
    else:
        geom_expr = coluna_geom

    where_clauses = [f"{coluna_fonte} = '{fonte}'"]
    if min_area_m2 is not None:
        if min_area_m2 <= 0:
            raise ValueError(
                f"min_area_m2 deve ser positivo: {min_area_m2!r}"
            )
        min_graus2 = float(min_area_m2) / 1.2321e10
        where_clauses.append(f"ST_Area({coluna_geom}) >= {min_graus2}")

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        CREATE OR REPLACE TABLE {tabela_destino} AS
          SELECT {geom_expr} AS geom
          FROM {tabela_recorte}
          WHERE {where_sql}
    """
    con.execute(sql)
    return ddb.contar_registros(con, tabela_destino)


# =============================================================================
# Histograma de areas por fonte
# =============================================================================
def _computar_histograma_areas(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna_geom: str,
    coluna_fonte: str,
    lat_media: float,
) -> dict[str, dict[str, int]]:
    """Computa histograma de areas por fonte em buckets fixos.

    Buckets: <50m2, 50-100, 100-200, 200-500, >=500

    Returns
    -------
    dict
        ``{fonte: {bucket_label: contagem}}``.
    """
    import math

    fator = _GRAU_EM_M2_EQUATORIAL * math.cos(math.radians(lat_media))

    sql = f"""
        SELECT
          {coluna_fonte} AS fonte,
          CASE
            WHEN ST_Area({coluna_geom}) * {fator} < 50 THEN '<50'
            WHEN ST_Area({coluna_geom}) * {fator} < 100 THEN '50-100'
            WHEN ST_Area({coluna_geom}) * {fator} < 200 THEN '100-200'
            WHEN ST_Area({coluna_geom}) * {fator} < 500 THEN '200-500'
            ELSE '>=500'
          END AS bucket,
          COUNT(*) AS n
        FROM {tabela}
        GROUP BY fonte, bucket
    """
    rows = con.execute(sql).fetchall()
    buckets_ordem = ["<50", "50-100", "100-200", "200-500", ">=500"]
    out: dict[str, dict[str, int]] = {
        config.SOURCE_GOOGLE: dict.fromkeys(buckets_ordem, 0),
        config.SOURCE_MICROSOFT: dict.fromkeys(buckets_ordem, 0),
    }
    for fonte, bucket, n in rows:
        if fonte in out and bucket in out[fonte]:
            out[fonte][bucket] = int(n)
    return out


# =============================================================================
# Renderizacao do template HTML multi-AOI
# =============================================================================
def _renderizar_template_multi(ctx: dict[str, Any]) -> str:
    """Interpola o contexto no template HTML.

    O template usa marcadores ``__NOME__`` em vez de f-string para
    evitar conflito com chaves ``{ }`` de CSS/JS. O payload de AOIs
    e injetado como JSON na variavel ``window.AOIS``.
    """
    # Serializa AOIs como JSON para o JavaScript ler
    aois_json = json.dumps(ctx["aois"], ensure_ascii=False)

    nota_decimacao_items: list[str] = []
    if ctx.get("min_area_m2") is not None:
        nota_decimacao_items.append(f"min_area_m2 = {ctx['min_area_m2']:g} m²")
    if ctx.get("simplify_tolerance") is not None:
        nota_decimacao_items.append(f"simplify_tolerance = {ctx['simplify_tolerance']:g}°")
    nota_decimacao = " / ".join(nota_decimacao_items) if nota_decimacao_items else ""

    return _TEMPLATE_HTML \
        .replace("__AOIS_JSON__", aois_json) \
        .replace("__COR_GOOGLE__", ctx["cor_google"]) \
        .replace("__COR_MICROSOFT__", ctx["cor_microsoft"]) \
        .replace("__NOTA_DECIMACAO__", nota_decimacao)


# =============================================================================
# Template HTML (multi-AOI com dashboard)
# =============================================================================
_TEMPLATE_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Open Buildings Explorer BR</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
        crossorigin=""></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=Karla:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --bg:            #060d16;
    --bg-card:       #0d1b2a;
    --bg-card2:      #122032;
    --bg-elem:       #091521;
    --border:        #1a3347;
    --border2:       #254460;
    --blue:          #00b4d8;
    --blue-dim:      #0077b6;
    --cor-google:    __COR_GOOGLE__;
    --cor-microsoft: __COR_MICROSOFT__;
    --amber:         #f4a261;
    --green:         #52b788;
    --red:           #ef233c;
    --txt:           #caf0f8;
    --txt-dim:       #6e8fa8;
    --txt-muted:     #3d5a72;
    --font-head:     'Barlow Condensed', sans-serif;
    --font-body:     'Karla', sans-serif;
  }

  body {
    font-family: var(--font-body);
    background: var(--bg);
    color: var(--txt);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* HEADER */
  #header {
    background: linear-gradient(90deg, #040b14 0%, #0d1b2a 60%, #0a1520 100%);
    border-bottom: 1px solid var(--border);
    padding: 0 20px;
    height: 56px;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-shrink: 0;
    box-shadow: 0 2px 16px rgba(0,0,0,.5);
    z-index: 500;
  }
  .hdr-logo {
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--cor-google), var(--cor-microsoft));
    border-radius: 8px;
  }
  .hdr-logo svg { width: 18px; height: 18px; fill: #fff; }
  .hdr-text h1 {
    font-family: var(--font-head);
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #e0f4ff;
    line-height: 1.1;
  }
  .hdr-text p {
    font-size: 11px;
    color: var(--txt-dim);
    margin-top: 2px;
  }
  .hdr-tag {
    margin-left: auto;
    background: var(--bg-elem);
    border: 1px solid var(--border2);
    color: var(--blue);
    padding: 5px 14px;
    border-radius: 20px;
    font-family: var(--font-head);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  /* LAYOUT */
  #main { display: flex; flex: 1; overflow: hidden; }
  #map  { flex: 1; position: relative; background: #e8ecef; }

  /* PAINEL LATERAL */
  #panel {
    width: 420px;
    min-width: 420px;
    background: var(--bg-card);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: -6px 0 24px rgba(0,0,0,.4);
  }

  /* SELETOR DE AOI */
  #aoi-selector-wrap {
    padding: 14px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-elem);
  }
  #aoi-selector-wrap label {
    display: block;
    font-family: var(--font-head);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--txt-dim);
    margin-bottom: 6px;
  }
  #aoi-select {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border2);
    color: var(--txt);
    padding: 10px 12px;
    border-radius: 7px;
    font-family: var(--font-head);
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    outline: none;
    transition: border-color .2s;
  }
  #aoi-select:focus { border-color: var(--blue); }

  /* TABS */
  #tabs {
    display: flex;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .tab {
    flex: 1;
    padding: 12px 6px;
    text-align: center;
    font-family: var(--font-head);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    color: var(--txt-dim);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all .2s;
    user-select: none;
  }
  .tab.active {
    color: var(--blue);
    border-bottom-color: var(--blue);
    background: rgba(0,180,216,.04);
  }
  .tab:hover:not(.active) { color: #a0cfe8; }

  /* CONTENT */
  .tab-content {
    flex: 1;
    overflow-y: auto;
    display: none;
    flex-direction: column;
    gap: 12px;
    padding: 14px 16px;
  }
  .tab-content.active { display: flex; }
  .tab-content::-webkit-scrollbar { width: 4px; }
  .tab-content::-webkit-scrollbar-track { background: var(--bg); }
  .tab-content::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

  /* CARDS */
  .card {
    background: var(--bg-card2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    flex-shrink: 0;
  }
  .card h4 {
    font-family: var(--font-head);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.9px;
    text-transform: uppercase;
    color: var(--txt-dim);
    margin-bottom: 11px;
  }

  /* NARRATIVA */
  .narrative {
    padding: 11px 13px;
    border-left: 3px solid var(--blue);
    border-radius: 0 8px 8px 0;
    background: rgba(0,180,216,.07);
    font-size: 12px;
    line-height: 1.6;
    color: #a0d4ee;
  }

  /* KPI GRID */
  .kpi-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .kpi {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 11px 12px;
    text-align: center;
  }
  .kpi-val {
    font-family: var(--font-head);
    font-size: 22px;
    font-weight: 800;
    color: var(--blue);
    letter-spacing: 0.5px;
    line-height: 1;
  }
  .kpi-val.google    { color: var(--cor-google); }
  .kpi-val.microsoft { color: var(--cor-microsoft); }
  .kpi-val.amber     { color: var(--amber); }
  .kpi-val.green     { color: var(--green); }
  .kpi-lbl {
    font-size: 9px;
    color: var(--txt-dim);
    margin-top: 5px;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    font-weight: 500;
  }

  /* STAT ROWS */
  .stat-row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }
  .stat-row:last-child { border-bottom: none; }
  .stat-lbl { color: var(--txt-dim); font-size: 11px; }
  .stat-val {
    font-family: var(--font-head);
    font-weight: 700;
    color: #c8e8ff;
    font-size: 14px;
  }
  .stat-val.google    { color: var(--cor-google); }
  .stat-val.microsoft { color: var(--cor-microsoft); }

  /* CHART WRAPPERS */
  .chart-wrap { position: relative; }
  .chart-wrap canvas { max-width: 100%; }
  .h-160 { height: 160px; }
  .h-200 { height: 200px; }
  .h-220 { height: 220px; }

  /* COMPARACAO LADO A LADO */
  .cmp-tbl {
    display: grid;
    grid-template-columns: 1.4fr repeat(var(--n-aois), 1fr);
    gap: 4px;
    font-size: 11px;
  }
  .cmp-tbl .cmp-head {
    font-family: var(--font-head);
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: var(--txt-dim);
    padding: 4px;
    border-bottom: 2px solid var(--border2);
  }
  .cmp-tbl .cmp-cell {
    padding: 7px 4px;
    border-bottom: 1px solid var(--border);
    text-align: right;
    font-family: var(--font-head);
    font-weight: 600;
    color: #c8e8ff;
  }
  .cmp-tbl .cmp-cell.lbl { text-align: left; color: var(--txt-dim); font-family: var(--font-body); font-weight: 400; }
  .cmp-tbl .cmp-cell.hi { color: var(--amber); }

  /* FOOTPRINT DETAIL */
  #detalhe-placeholder {
    text-align: center;
    color: var(--txt-muted);
    font-size: 11px;
    padding: 24px 12px;
    font-style: italic;
    line-height: 1.6;
  }
  .fp-swatch {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 2px;
    margin-right: 5px;
    vertical-align: middle;
  }

  /* LEGEND NO MAPA */
  #legend {
    position: absolute;
    bottom: 24px;
    left: 12px;
    z-index: 800;
    background: rgba(6,13,22,.92);
    border: 1px solid var(--border2);
    border-radius: 10px;
    padding: 10px 13px;
    backdrop-filter: blur(6px);
    box-shadow: 0 4px 16px rgba(0,0,0,.4);
    font-size: 11px;
    color: var(--txt);
  }
  #legend h5 {
    font-family: var(--font-head);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--txt-dim);
    margin-bottom: 7px;
  }
  .legend-item {
    display: flex; align-items: center; gap: 8px;
    margin-top: 5px;
  }
  .legend-item .swatch {
    width: 14px; height: 14px;
    border-radius: 3px;
    border: 1px solid rgba(255,255,255,.1);
  }

  /* CONTROLE DE CAMADAS BASE (canto superior direito do mapa) */
  .leaflet-control-layers {
    background: rgba(6, 13, 22, .92) !important;
    border: 1px solid var(--border2) !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,.4) !important;
    backdrop-filter: blur(6px);
    color: var(--txt) !important;
    font-family: var(--font-body) !important;
    font-size: 12px !important;
    padding: 6px 10px !important;
  }
  .leaflet-control-layers-expanded {
    padding: 8px 12px !important;
  }
  .leaflet-control-layers-base label {
    color: var(--txt) !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 4px 0 !important;
    cursor: pointer !important;
  }
  .leaflet-control-layers input[type="radio"] {
    accent-color: var(--blue) !important;
    margin: 0 !important;
  }
  .leaflet-control-layers-separator {
    border-top: 1px solid var(--border) !important;
  }

  /* POPUP STYLE */
  .leaflet-popup-content-wrapper {
    background: #0a1520 !important;
    color: var(--txt) !important;
    border-radius: 8px !important;
    border: 1px solid var(--border2) !important;
    box-shadow: 0 6px 18px rgba(0,0,0,.6) !important;
  }
  .leaflet-popup-tip { background: #0a1520 !important; }
  .leaflet-popup-close-button { color: var(--txt-dim) !important; }
  .popup-content { font-family: var(--font-body); font-size: 12px; min-width: 180px; }
  .popup-fonte {
    display: inline-block;
    padding: 3px 9px;
    border-radius: 4px;
    font-family: var(--font-head);
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: #fff;
    margin-bottom: 8px;
  }
  .popup-row {
    display: flex; justify-content: space-between;
    padding: 4px 0; border-bottom: 1px solid var(--border);
    font-size: 11px;
  }
  .popup-row:last-child { border-bottom: none; }
  .popup-lbl { color: var(--txt-dim); }
  .popup-val { font-family: var(--font-head); font-weight: 700; color: #c8e8ff; }

  /* FOOTER */
  .panel-footer {
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    font-size: 10px;
    color: var(--txt-muted);
    line-height: 1.6;
    background: var(--bg-elem);
    flex-shrink: 0;
  }
  .panel-footer a { color: var(--txt-dim); text-decoration: none; }
  .panel-footer a:hover { color: var(--blue); text-decoration: underline; }

  /* LOADING */
  #loading {
    position: fixed; inset: 0; background: var(--bg);
    display: flex; align-items: center; justify-content: center;
    z-index: 9999; flex-direction: column; gap: 14px;
  }
  .spinner {
    width: 42px; height: 42px;
    border: 3px solid var(--border);
    border-top-color: var(--blue);
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  #loading p {
    font-size: 13px;
    color: var(--txt-dim);
    letter-spacing: 0.3px;
    font-family: var(--font-head);
    font-weight: 600;
  }

  /* MOBILE */
  @media (max-width: 760px) {
    #main { flex-direction: column; }
    #panel { width: 100%; min-width: 0; max-height: 50vh; border-left: none; border-top: 1px solid var(--border); }
    #map { height: 50vh; }
    #legend { bottom: 10px; left: 10px; }
  }
</style>
</head>
<body>

<div id="loading">
  <div class="spinner"></div>
  <p>Carregando dados do dataset Open Buildings...</p>
</div>

<div id="header">
  <div class="hdr-logo">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2L2 7v12l10 5 10-5V7L12 2zm0 2.3l7.6 3.8L12 11.9 4.4 8.1 12 4.3zM4 9.8l7 3.5v7.4l-7-3.5V9.8zm9 10.9v-7.4l7-3.5v7.4l-7 3.5z"/></svg>
  </div>
  <div class="hdr-text">
    <h1>Open Buildings Explorer BR</h1>
    <p>Dataset VIDA Google-Microsoft &middot; Analise com DuckDB sobre S3 publico</p>
  </div>
  <div class="hdr-tag" id="hdr-total">— edificacoes</div>
</div>

<div id="main">
  <div id="map" role="application" aria-label="Mapa interativo de edificacoes"></div>

  <div id="panel">
    <!-- Seletor de AOI -->
    <div id="aoi-selector-wrap">
      <label for="aoi-select">Area de interesse</label>
      <select id="aoi-select"></select>
    </div>

    <!-- Tabs -->
    <div id="tabs">
      <div class="tab active" data-tab="geral">Visao geral</div>
      <div class="tab" data-tab="analise">Analise</div>
      <div class="tab" data-tab="detalhe">Detalhe</div>
    </div>

    <!-- Tab Visao Geral -->
    <div id="tab-geral" class="tab-content active">
      <div class="card">
        <h4>Area de interesse</h4>
        <div class="stat-row"><span class="stat-lbl">Codigo IBGE</span>  <span class="stat-val" id="ov-ibge">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Area oficial</span> <span class="stat-val" id="ov-area">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Populacao 2022</span> <span class="stat-val" id="ov-pop">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Tipologia</span>   <span class="stat-val" id="ov-tipo">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Regiao intermediaria</span> <span class="stat-val" id="ov-rint">—</span></div>
      </div>

      <div class="card">
        <h4>Indicadores</h4>
        <div class="kpi-grid">
          <div class="kpi"><div class="kpi-val" id="kpi-total">—</div><div class="kpi-lbl">edificacoes</div></div>
          <div class="kpi"><div class="kpi-val amber" id="kpi-dens">—</div><div class="kpi-lbl">edif. / km&sup2;</div></div>
          <div class="kpi"><div class="kpi-val google" id="kpi-google">—</div><div class="kpi-lbl">google %</div></div>
          <div class="kpi"><div class="kpi-val microsoft" id="kpi-microsoft">—</div><div class="kpi-lbl">microsoft %</div></div>
        </div>
      </div>

      <div class="card">
        <h4>Distribuicao Google &times; Microsoft</h4>
        <div class="chart-wrap h-160"><canvas id="chart-donut"></canvas></div>
      </div>

      <div class="narrative" id="narrative-geral">—</div>
    </div>

    <!-- Tab Analise -->
    <div id="tab-analise" class="tab-content">
      <div class="card">
        <h4>Distribuicao de areas por footprint</h4>
        <div class="chart-wrap h-200"><canvas id="chart-hist"></canvas></div>
        <div class="stat-row" style="margin-top: 8px;"><span class="stat-lbl">Area media Google</span>    <span class="stat-val google" id="an-media-g">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Area media Microsoft</span> <span class="stat-val microsoft" id="an-media-m">—</span></div>
        <div class="stat-row"><span class="stat-lbl">Area total edificada</span> <span class="stat-val" id="an-area-tot">—</span></div>
      </div>

      <div class="card">
        <h4>Comparacao entre AOIs</h4>
        <div id="cmp-wrap"></div>
      </div>

      <div class="narrative" id="narrative-analise">—</div>
    </div>

    <!-- Tab Detalhe -->
    <div id="tab-detalhe" class="tab-content">
      <div class="card" id="detalhe-card">
        <h4>Edificacao selecionada</h4>
        <div id="detalhe-placeholder">
          Clique em uma edificacao no mapa para ver detalhes.
        </div>
        <div id="detalhe-corpo" style="display: none;">
          <div class="stat-row"><span class="stat-lbl">Fonte</span>           <span class="stat-val" id="dt-fonte">—</span></div>
          <div class="stat-row"><span class="stat-lbl">Area</span>            <span class="stat-val" id="dt-area">—</span></div>
          <div class="stat-row"><span class="stat-lbl">Area (hectares)</span> <span class="stat-val" id="dt-ha">—</span></div>
          <div class="stat-row"><span class="stat-lbl">Centroide (lat)</span> <span class="stat-val" id="dt-lat">—</span></div>
          <div class="stat-row"><span class="stat-lbl">Centroide (lon)</span> <span class="stat-val" id="dt-lon">—</span></div>
          <div class="stat-row"><span class="stat-lbl">Posicao na AOI</span>  <span class="stat-val" id="dt-pos">—</span></div>
        </div>
      </div>

      <div class="narrative">
        Cada footprint foi extraido por deep learning sobre imagens de
        satelite por Google ou Microsoft. A mesclagem VIDA prioriza
        Google quando ha sobreposicao entre as duas fontes.
      </div>
    </div>

    <div class="panel-footer">
      Dados: VIDA Google-Microsoft Open Buildings &middot; Poligonos IBGE 2022.
      Pipeline: DuckDB sobre S3 publico. __NOTA_DECIMACAO__
      <br>
      <a href="https://github.com/PedroLuizskt/open-buildings-explorer-br" target="_blank" rel="noopener">
        github.com/PedroLuizskt/open-buildings-explorer-br
      </a>
    </div>
  </div>
</div>

<div id="legend">
  <h5>Camadas</h5>
  <label class="legend-item" style="cursor: pointer;">
    <input type="checkbox" id="toggle-google" checked>
    <span class="swatch" style="background: var(--cor-google);"></span>
    <span>Google</span>
  </label>
  <label class="legend-item" style="cursor: pointer;">
    <input type="checkbox" id="toggle-microsoft" checked>
    <span class="swatch" style="background: var(--cor-microsoft);"></span>
    <span>Microsoft</span>
  </label>
</div>

<script>
// =============================================================================
// Dados injetados pelo backend
// =============================================================================
window.AOIS = __AOIS_JSON__;
const COR_GOOGLE = "__COR_GOOGLE__";
const COR_MICROSOFT = "__COR_MICROSOFT__";

// =============================================================================
// Helpers
// =============================================================================
const fmt = {
  int: (n) => (typeof n !== "number" || isNaN(n)) ? "—" : n.toLocaleString("pt-BR"),
  pct: (n) => (typeof n !== "number" || isNaN(n)) ? "—" : n.toFixed(1) + "%",
  area_m2: (n) => (typeof n !== "number" || isNaN(n)) ? "—" : Math.round(n).toLocaleString("pt-BR") + " m²",
  area_ha: (n) => (typeof n !== "number" || isNaN(n)) ? "—" : (n / 10000).toFixed(4) + " ha",
  area_km2: (n) => (typeof n !== "number" || isNaN(n)) ? "—" : n.toFixed(1) + " km²",
  float: (n, d) => (typeof n !== "number" || isNaN(n)) ? "—" : n.toFixed(d),
};

// =============================================================================
// Setup do mapa
// =============================================================================
const canvasRenderer = L.canvas({ padding: 0.5 });

const map = L.map("map", {
  renderer: canvasRenderer,
  preferCanvas: true,
  zoomControl: true,
});
L.control.zoom({ position: "topleft" });

// Duas camadas base: OpenStreetMap (default, bom para orientacao com nomes
// de ruas) e ESRI World Imagery (satelite, melhor para ver as edificacoes
// sobre a imagem real). Usuario alterna via controle no canto superior direito.
const baseOSM = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19,
});
const baseEsri = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    maxZoom: 19,
  }
);

// OSM eh o default — adiciona ao mapa inicialmente
baseOSM.addTo(map);

// Controle de camadas base no canto superior direito
L.control.layers(
  {
    "OpenStreetMap": baseOSM,
    "ESRI Satellite": baseEsri,
  },
  null,  // sem overlays (os toggles Google/Microsoft estao no painel lateral)
  { position: "topright", collapsed: false }
).addTo(map);

// =============================================================================
// Camadas por AOI
// =============================================================================
const camadasPorAOI = {};  // { slug: { google: L.GeoJSON|null, microsoft: L.GeoJSON|null, bbox: L.LatLngBounds } }
let aoiAtual = null;
let chartDonut = null;
let chartHist = null;

function estiloFootprint(cor) {
  // weight 0.7 e fillOpacity 0.5 funcionam bem em ambas camadas base
  // (OSM clara e satelite escura) sem esconder detalhes relevantes.
  return { color: cor, weight: 0.7, fillColor: cor, fillOpacity: 0.5 };
}

function popupFootprint(fonte, cor, feature, layer) {
  const label = fonte === "google" ? "Google" : "Microsoft";
  const area_m2 = feature.properties ? feature.properties.area_m2 : null;
  const bounds = layer.getBounds();
  const center = bounds.getCenter();

  const html =
    '<div class="popup-content">' +
      '<div class="popup-fonte" style="background: ' + cor + ';">' + label + '</div>' +
      '<div class="popup-row"><span class="popup-lbl">Area</span> <span class="popup-val">' + fmt.area_m2(area_m2) + '</span></div>' +
      '<div class="popup-row"><span class="popup-lbl">Hectares</span> <span class="popup-val">' + fmt.area_ha(area_m2) + '</span></div>' +
      '<div class="popup-row"><span class="popup-lbl">Lat</span> <span class="popup-val">' + fmt.float(center.lat, 5) + '</span></div>' +
      '<div class="popup-row"><span class="popup-lbl">Lon</span> <span class="popup-val">' + fmt.float(center.lng, 5) + '</span></div>' +
    '</div>';

  layer.bindPopup(html);
  layer.on("click", () => {
    atualizarDetalheFootprint(label, cor, area_m2, center.lat, center.lng);
    // Troca para tab detalhe se o usuario clicou em um footprint
    switchTab("detalhe");
  });
}

function carregarCamada(url, cor, fonte) {
  return fetch(url)
    .then(r => r.json())
    .then(gj => L.geoJSON(gj, {
      renderer: canvasRenderer,
      style: () => estiloFootprint(cor),
      onEachFeature: (feature, layer) => popupFootprint(fonte, cor, feature, layer),
    }));
}

function carregarCamadasAOI(aoi) {
  if (camadasPorAOI[aoi.slug]) {
    return Promise.resolve(camadasPorAOI[aoi.slug]);
  }
  const promises = [];
  const resultado = { google: null, microsoft: null };
  for (const fonte of ["google", "microsoft"]) {
    const url = aoi.arquivos_fonte[fonte];
    const cor = fonte === "google" ? COR_GOOGLE : COR_MICROSOFT;
    if (url) {
      promises.push(carregarCamada(url, cor, fonte).then(layer => {
        resultado[fonte] = layer;
      }));
    }
  }
  return Promise.all(promises).then(() => {
    camadasPorAOI[aoi.slug] = resultado;
    return resultado;
  });
}

// =============================================================================
// Troca de AOI
// =============================================================================
function trocarAOI(slug) {
  const aoi = window.AOIS.find(a => a.slug === slug);
  if (!aoi) return;

  // Remove camadas da AOI anterior
  if (aoiAtual) {
    const anterior = camadasPorAOI[aoiAtual.slug];
    if (anterior) {
      if (anterior.google && map.hasLayer(anterior.google)) map.removeLayer(anterior.google);
      if (anterior.microsoft && map.hasLayer(anterior.microsoft)) map.removeLayer(anterior.microsoft);
    }
  }

  aoiAtual = aoi;

  // Ajusta bounds
  map.fitBounds([aoi.bounds_sw, aoi.bounds_ne]);

  // Carrega camadas (ou reusa se ja carregou) e aplica toggles atuais
  carregarCamadasAOI(aoi).then(camadas => {
    const togG = document.getElementById("toggle-google").checked;
    const togM = document.getElementById("toggle-microsoft").checked;
    if (camadas.google && togG) camadas.google.addTo(map);
    if (camadas.microsoft && togM) camadas.microsoft.addTo(map);
  });

  // Atualiza painel
  atualizarPainel(aoi);
  resetarDetalhe();
}

// =============================================================================
// Atualizacao do painel lateral
// =============================================================================
function atualizarPainel(aoi) {
  const p = aoi.properties;
  const r = aoi.resumo;
  const total = r.total_footprints;
  const g = r.por_fonte.google || 0;
  const m = r.por_fonte.microsoft || 0;
  const pctG = total > 0 ? (100 * g / total) : 0;
  const pctM = total > 0 ? (100 * m / total) : 0;
  const areaG = r.area_total_m2_por_fonte.google || 0;
  const areaM = r.area_total_m2_por_fonte.microsoft || 0;
  const mediaG = r.area_media_m2_por_fonte.google || 0;
  const mediaM = r.area_media_m2_por_fonte.microsoft || 0;
  const densidade = aoi.area_km2_oficial > 0 ? total / aoi.area_km2_oficial : 0;

  // Header
  document.getElementById("hdr-total").textContent = fmt.int(total) + " edificacoes";

  // Tab Visao Geral
  document.getElementById("ov-ibge").textContent = p.ibge_code || "—";
  document.getElementById("ov-area").textContent = fmt.area_km2(aoi.area_km2_oficial);
  document.getElementById("ov-pop").textContent = fmt.int(p.populacao_2022) + " hab.";
  document.getElementById("ov-tipo").textContent = p.tipologia || "—";
  document.getElementById("ov-rint").textContent = p.regiao_intermediaria || "—";

  document.getElementById("kpi-total").textContent = fmt.int(total);
  document.getElementById("kpi-dens").textContent = densidade.toFixed(1);
  document.getElementById("kpi-google").textContent = fmt.pct(pctG);
  document.getElementById("kpi-microsoft").textContent = fmt.pct(pctM);

  // Narrativa Geral
  const narrGeral = gerarNarrativaGeral(aoi, total, pctG, densidade);
  document.getElementById("narrative-geral").textContent = narrGeral;

  // Donut
  renderDonut(g, m);

  // Tab Analise
  document.getElementById("an-media-g").textContent = fmt.area_m2(mediaG);
  document.getElementById("an-media-m").textContent = fmt.area_m2(mediaM);
  document.getElementById("an-area-tot").textContent = fmt.area_m2(areaG + areaM);

  renderHist(aoi.histograma);
  renderComparacao(aoi.slug);

  const narrAnalise = gerarNarrativaAnalise(aoi, mediaG, mediaM);
  document.getElementById("narrative-analise").textContent = narrAnalise;
}

function gerarNarrativaGeral(aoi, total, pctG, densidade) {
  const partes = [];
  partes.push(aoi.nome_exibicao + " possui " + fmt.int(total) + " edificacoes mapeadas, ");
  partes.push("com densidade de " + densidade.toFixed(1) + " por km² de area oficial. ");
  if (pctG >= 90) {
    partes.push("Google domina a cobertura (" + fmt.pct(pctG) + "), tipico em areas com maior qualidade de imagens de satelite por deep learning do Google.");
  } else if (pctG >= 70) {
    partes.push("Google cobre " + fmt.pct(pctG) + " das edificacoes, com participacao significativa da Microsoft.");
  } else {
    partes.push("Microsoft tem participacao proeminente, cobrindo " + fmt.pct(100 - pctG) + " das edificacoes.");
  }
  return partes.join("");
}

function gerarNarrativaAnalise(aoi, mediaG, mediaM) {
  const diferenca = Math.abs(mediaG - mediaM);
  const partes = [];
  if (mediaG > mediaM) {
    partes.push("As edificacoes do Google tem area media " + fmt.area_m2(diferenca) + " maior que as da Microsoft, ");
    partes.push("sugerindo que a Microsoft captura estruturas menores (anexos, galpoes rurais) que o Google frequentemente nao detecta.");
  } else {
    partes.push("Microsoft e Google produzem edificacoes de tamanho medio similar nesta AOI.");
  }
  return partes.join("");
}

// =============================================================================
// Chart.js — Donut Google vs Microsoft
// =============================================================================
function renderDonut(g, m) {
  const canvas = document.getElementById("chart-donut");
  if (chartDonut) chartDonut.destroy();
  chartDonut = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Google", "Microsoft"],
      datasets: [{
        data: [g, m],
        backgroundColor: [COR_GOOGLE, COR_MICROSOFT],
        borderColor: "#0d1b2a",
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "60%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#caf0f8",
            font: { family: "Karla", size: 11 },
            padding: 10,
            boxWidth: 12,
          },
        },
        tooltip: {
          backgroundColor: "#07111d",
          titleColor: "#caf0f8",
          bodyColor: "#caf0f8",
          borderColor: "#254460",
          borderWidth: 1,
          callbacks: {
            label: (ctx) => ctx.label + ": " + fmt.int(ctx.parsed) + " (" + (100 * ctx.parsed / (g + m)).toFixed(1) + "%)",
          },
        },
      },
    },
  });
}

// =============================================================================
// Chart.js — Histograma de areas por bucket
// =============================================================================
function renderHist(histograma) {
  const canvas = document.getElementById("chart-hist");
  if (chartHist) chartHist.destroy();
  const buckets = ["<50", "50-100", "100-200", "200-500", ">=500"];
  const dadosG = buckets.map(b => (histograma.google && histograma.google[b]) || 0);
  const dadosM = buckets.map(b => (histograma.microsoft && histograma.microsoft[b]) || 0);

  chartHist = new Chart(canvas, {
    type: "bar",
    data: {
      labels: buckets.map(b => b + " m²"),
      datasets: [
        { label: "Google",    data: dadosG, backgroundColor: COR_GOOGLE, borderWidth: 0 },
        { label: "Microsoft", data: dadosM, backgroundColor: COR_MICROSOFT, borderWidth: 0 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#6e8fa8", font: { family: "Karla", size: 10 } }, grid: { color: "#1a3347" } },
        y: { ticks: { color: "#6e8fa8", font: { family: "Karla", size: 10 } }, grid: { color: "#1a3347" } },
      },
      plugins: {
        legend: { position: "top", labels: { color: "#caf0f8", font: { family: "Karla", size: 11 }, boxWidth: 12 } },
        tooltip: {
          backgroundColor: "#07111d",
          titleColor: "#caf0f8",
          bodyColor: "#caf0f8",
          borderColor: "#254460",
          borderWidth: 1,
          callbacks: {
            label: (ctx) => ctx.dataset.label + ": " + fmt.int(ctx.parsed.y),
          },
        },
      },
    },
  });
}

// =============================================================================
// Tabela comparativa entre AOIs
// =============================================================================
function renderComparacao(slugAtual) {
  const wrap = document.getElementById("cmp-wrap");
  wrap.innerHTML = "";
  const tbl = document.createElement("div");
  tbl.className = "cmp-tbl";
  tbl.style.setProperty("--n-aois", window.AOIS.length);

  // Header
  const h0 = document.createElement("div"); h0.className = "cmp-head"; h0.textContent = "Metrica"; tbl.appendChild(h0);
  for (const a of window.AOIS) {
    const h = document.createElement("div");
    h.className = "cmp-head";
    h.textContent = a.nome_exibicao;
    h.style.textAlign = "right";
    tbl.appendChild(h);
  }

  const linhas = [
    { lbl: "Total",         valor: a => fmt.int(a.resumo.total_footprints) },
    { lbl: "Google",        valor: a => fmt.int(a.resumo.por_fonte.google || 0) },
    { lbl: "Microsoft",     valor: a => fmt.int(a.resumo.por_fonte.microsoft || 0) },
    { lbl: "Area km²",      valor: a => fmt.area_km2(a.area_km2_oficial) },
    { lbl: "Densidade/km²", valor: a => (a.resumo.total_footprints / a.area_km2_oficial).toFixed(1) },
  ];

  for (const linha of linhas) {
    const l = document.createElement("div"); l.className = "cmp-cell lbl"; l.textContent = linha.lbl; tbl.appendChild(l);
    for (const a of window.AOIS) {
      const c = document.createElement("div");
      c.className = "cmp-cell" + (a.slug === slugAtual ? " hi" : "");
      c.textContent = linha.valor(a);
      tbl.appendChild(c);
    }
  }

  wrap.appendChild(tbl);
}

// =============================================================================
// Detalhe de footprint
// =============================================================================
function atualizarDetalheFootprint(fonte, cor, area_m2, lat, lng) {
  document.getElementById("detalhe-placeholder").style.display = "none";
  document.getElementById("detalhe-corpo").style.display = "block";

  const fonteHtml = '<span class="fp-swatch" style="background:' + cor + '"></span>' + fonte;
  document.getElementById("dt-fonte").innerHTML = fonteHtml;
  document.getElementById("dt-area").textContent  = fmt.area_m2(area_m2);
  document.getElementById("dt-ha").textContent    = fmt.area_ha(area_m2);
  document.getElementById("dt-lat").textContent   = fmt.float(lat, 6);
  document.getElementById("dt-lon").textContent   = fmt.float(lng, 6);
  document.getElementById("dt-pos").textContent   = aoiAtual ? aoiAtual.nome_exibicao : "—";
}

function resetarDetalhe() {
  document.getElementById("detalhe-placeholder").style.display = "block";
  document.getElementById("detalhe-corpo").style.display = "none";
}

// =============================================================================
// Tabs
// =============================================================================
function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach(t => {
    t.classList.toggle("active", t.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-content").forEach(c => {
    c.classList.toggle("active", c.id === "tab-" + tabName);
  });
}

document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => switchTab(t.dataset.tab));
});

// =============================================================================
// Setup inicial — popular dropdown e carregar primeira AOI
// =============================================================================
const sel = document.getElementById("aoi-select");
for (const a of window.AOIS) {
  const opt = document.createElement("option");
  opt.value = a.slug;
  opt.textContent = a.nome_exibicao;
  sel.appendChild(opt);
}
sel.addEventListener("change", (e) => trocarAOI(e.target.value));

// Toggles de camada no legend
document.getElementById("toggle-google").addEventListener("change", (e) => {
  if (!aoiAtual) return;
  const cam = camadasPorAOI[aoiAtual.slug];
  if (!cam || !cam.google) return;
  if (e.target.checked) cam.google.addTo(map);
  else map.removeLayer(cam.google);
});
document.getElementById("toggle-microsoft").addEventListener("change", (e) => {
  if (!aoiAtual) return;
  const cam = camadasPorAOI[aoiAtual.slug];
  if (!cam || !cam.microsoft) return;
  if (e.target.checked) cam.microsoft.addTo(map);
  else map.removeLayer(cam.microsoft);
});

// Inicia com a primeira AOI
if (window.AOIS.length > 0) {
  sel.value = window.AOIS[0].slug;
  trocarAOI(window.AOIS[0].slug);
}

// Esconde loading quando tudo pronto
window.addEventListener("load", () => {
  setTimeout(() => {
    const l = document.getElementById("loading");
    if (l) l.style.display = "none";
  }, 300);
});
</script>
</body>
</html>
"""
