"""Gerador de webmap HTML interativo comparativo Google vs Microsoft.

Produz um ``index.html`` autocontido em ``webmap/`` com camada base
OpenStreetMap, duas camadas de footprints (Google + Microsoft) com
toggle via controle de camadas Leaflet, painel lateral com
estatísticas por fonte e popups por footprint. Compatível com
GitHub Pages sem build step — carrega Leaflet via CDN e os
GeoJSONs são servidos como arquivos estáticos em ``webmap/data/``.

Fluxo de geração
----------------

::

    gerar_webmap_comparativo(con, tabela_recorte, aoi, output_dir)
    |
    |-- exporta GeoJSON por fonte em webmap/data/
    |   (<aoi_slug>_google.geojson, <aoi_slug>_microsoft.geojson)
    |
    |-- computa resumo via analysis.resumo_aoi()
    |
    |-- renderiza webmap/index.html a partir do template
    |   com contexto injetado:
    |   - nome e tipologia da AOI
    |   - bounds para fitBounds inicial
    |   - URLs dos GeoJSONs
    |   - contagens e areas por fonte

Design intencional do HTML
--------------------------

- **Zero build step**: Leaflet via unpkg CDN, estilos inline, nada
  de bundler, nada de ``node_modules``
- **Canvas renderer** por default (``L.canvas``) para suportar
  dezenas de milhares de footprints sem travar o navegador
- **Cores oficiais**: Google ``#4285F4``, Microsoft ``#00A4EF``
- **Painel lateral** fixo com estatísticas da AOI, legenda e
  controles de camada
- **Responsivo** no mobile (painel colapsa em breakpoint estreito)

Decimação para AOIs grandes
---------------------------

Uberlândia tem ~538k footprints — carregar todos como GeoJSON
individuais trava navegadores. Para AOIs grandes, use os
parâmetros opcionais:

- ``min_area_m2``: descarta footprints menores que N m² antes de
  exportar (reduz volume mantendo as construções significativas)
- ``simplify_tolerance``: aplica ``ST_SimplifyPreserveTopology``
  reduzindo vértices por polígono

Para Cambuquira (12k footprints), ambos podem ser ``None`` — todos
os footprints cabem confortavelmente no navegador.
"""

from __future__ import annotations

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
"""Azul característico do Google (brand hex)."""

COR_MICROSOFT: str = "#00A4EF"
"""Azul característico da Microsoft (brand hex)."""

CORES_FONTE: dict[str, str] = {
    config.SOURCE_GOOGLE: COR_GOOGLE,
    config.SOURCE_MICROSOFT: COR_MICROSOFT,
}


# =============================================================================
# Validação (compartilhada com duckdb_client)
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
# Geração do webmap
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
    """Gera o webmap HTML interativo comparativo Google vs Microsoft.

    Produz ``<output_dir>/index.html`` + ``<output_dir>/data/*.geojson``,
    um servível diretamente por qualquer host estático (GitHub Pages,
    Netlify, S3, ``python -m http.server``).

    Parameters
    ----------
    con : DuckDBPyConnection
        Conexão com tabela de recorte já materializada.
    tabela_recorte : str
        Nome da tabela DuckDB com footprints recortados pela AOI
        (criada por :func:`obr_explorer.duckdb_client.recortar_por_aoi`).
    aoi : AOI
        Dataclass da AOI, usada para contexto editorial e bounds iniciais.
    output_dir : Path, optional
        Diretório onde salvar. Default: ``config.WEBMAP_DIR``.
    min_area_m2 : float, optional
        Se passado, descarta footprints com área menor que este valor
        (em m²). Útil para AOIs grandes (Uberlândia). Default: sem filtro.
    simplify_tolerance : float, optional
        Se passado, aplica ``ST_SimplifyPreserveTopology`` com esta
        tolerância em graus (para WGS84, 1e-5 ~= 1 m). Útil para
        reduzir número de vértices em polígonos complexos.
    coluna_geom, coluna_fonte : str
        Nomes das colunas na ``tabela_recorte``.

    Returns
    -------
    Path
        Caminho do arquivo ``index.html`` gerado.
    """
    _validar_identificador(tabela_recorte, "nome de tabela")
    _validar_identificador(coluna_geom, "coluna geom")
    _validar_identificador(coluna_fonte, "coluna fonte")

    output_dir = Path(output_dir) if output_dir else config.WEBMAP_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # 1. Exportar GeoJSONs por fonte (uma camada por fonte, para toggle)
    arquivos_fonte: dict[str, Path] = {}
    for fonte in (config.SOURCE_GOOGLE, config.SOURCE_MICROSOFT):
        tabela_fonte = f"{tabela_recorte}_fonte_{fonte}"
        _criar_subset_por_fonte(
            con,
            tabela_recorte=tabela_recorte,
            tabela_destino=tabela_fonte,
            fonte=fonte,
            coluna_geom=coluna_geom,
            coluna_fonte=coluna_fonte,
            min_area_m2=min_area_m2,
            simplify_tolerance=simplify_tolerance,
        )
        caminho = data_dir / f"{aoi.nome}_{fonte}.geojson"
        ddb.exportar_geojson(con, tabela_fonte, caminho)
        arquivos_fonte[fonte] = caminho

    # 2. Computar resumo estatistico
    _, miny, _, maxy = aoi.bounds
    lat_media = (miny + maxy) / 2
    resumo = analysis.resumo_aoi(
        con, tabela_recorte,
        aoi_nome=aoi.nome_exibicao,
        coluna_geom=coluna_geom,
        coluna_fonte=coluna_fonte,
        lat_media=lat_media,
    )

    # 3. Renderizar HTML com contexto injetado
    contexto = _montar_contexto_html(
        aoi=aoi,
        resumo=resumo,
        arquivos_fonte={
            fonte: f"data/{caminho.name}"
            for fonte, caminho in arquivos_fonte.items()
        },
        min_area_m2=min_area_m2,
        simplify_tolerance=simplify_tolerance,
    )
    html = _renderizar_template(contexto)
    output_html = output_dir / "index.html"
    output_html.write_text(html, encoding="utf-8")

    logger.info("[OK] Webmap gerado: %s", output_html)
    return output_html


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
    """Cria tabela derivada contendo apenas footprints de uma fonte,
    aplicando filtros opcionais de área mínima e simplificação."""
    _validar_identificador(tabela_destino, "tabela destino")
    if fonte not in config.FONTES_VALIDAS:
        raise ValueError(
            f"Fonte invalida: {fonte!r}. Aceita: {config.FONTES_VALIDAS}"
        )

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

    # Filtro de area minima em m2 — ST_Area retorna em graus^2 em WGS84,
    # usamos conversao aproximada equatorial. Para AOIs no Brasil, erro < 5%.
    where_clauses = [f"{coluna_fonte} = '{fonte}'"]
    if min_area_m2 is not None:
        if min_area_m2 <= 0:
            raise ValueError(
                f"min_area_m2 deve ser positivo: {min_area_m2!r}"
            )
        # 1 grau^2 ~= (111 km)^2 = 1.2321e10 m2 (equatorial)
        min_graus2 = float(min_area_m2) / 1.2321e10
        where_clauses.append(f"ST_Area({coluna_geom}) >= {min_graus2}")

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        CREATE OR REPLACE TABLE {tabela_destino} AS
          SELECT {geom_expr} AS geom
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


# =============================================================================
# Template HTML — contexto e renderização
# =============================================================================
def _montar_contexto_html(
    aoi: AOI,
    resumo: analysis.ResumoAOI,
    arquivos_fonte: dict[str, str],
    min_area_m2: float | None,
    simplify_tolerance: float | None,
) -> dict[str, Any]:
    """Monta dict de contexto usado pelo template HTML."""
    minx, miny, maxx, maxy = aoi.bounds
    total = resumo.total_footprints or 1
    n_google = resumo.por_fonte.get(config.SOURCE_GOOGLE, 0)
    n_microsoft = resumo.por_fonte.get(config.SOURCE_MICROSOFT, 0)
    area_google = resumo.area_total_m2_por_fonte.get(config.SOURCE_GOOGLE, 0.0)
    area_microsoft = resumo.area_total_m2_por_fonte.get(config.SOURCE_MICROSOFT, 0.0)

    nota_decimacao_items: list[str] = []
    if min_area_m2 is not None:
        nota_decimacao_items.append(
            f"min_area_m2 = {min_area_m2:g} m2"
        )
    if simplify_tolerance is not None:
        nota_decimacao_items.append(
            f"simplify_tolerance = {simplify_tolerance:g} graus"
        )
    nota_decimacao = (
        " / ".join(nota_decimacao_items) if nota_decimacao_items else ""
    )

    return {
        "aoi_nome": aoi.nome_exibicao,
        "aoi_slug": aoi.nome,
        "aoi_tipologia": aoi.properties.get("tipologia", "n/a"),
        "aoi_populacao": aoi.properties.get("populacao_2022", "n/a"),
        "aoi_area_km2": aoi.properties.get(
            "area_km2_oficial", aoi.area_km2_aproximada
        ),
        "aoi_ibge_code": aoi.properties.get("ibge_code", "n/a"),
        "bounds_sw": [miny, minx],  # [lat, lon] para Leaflet
        "bounds_ne": [maxy, maxx],
        "total_footprints": resumo.total_footprints,
        "n_google": n_google,
        "n_microsoft": n_microsoft,
        "pct_google": 100.0 * n_google / total,
        "pct_microsoft": 100.0 * n_microsoft / total,
        "area_google_m2": area_google,
        "area_microsoft_m2": area_microsoft,
        "url_google": arquivos_fonte.get(config.SOURCE_GOOGLE, ""),
        "url_microsoft": arquivos_fonte.get(config.SOURCE_MICROSOFT, ""),
        "cor_google": COR_GOOGLE,
        "cor_microsoft": COR_MICROSOFT,
        "nota_decimacao": nota_decimacao,
    }


def _renderizar_template(ctx: dict[str, Any]) -> str:
    """Renderiza o template HTML interpolando o contexto.

    Template é um f-string Python puro (sem Jinja) para evitar
    dependência extra. Tudo que é interpolado passa por format
    cuidadoso para evitar interferência com { } de CSS/JS.
    """
    # Formatacao de numeros em pt-BR (separador de milhares)
    fmt_int = lambda n: f"{int(n):,}".replace(",", ".")
    fmt_m2 = lambda n: f"{float(n):,.0f} m²".replace(",", ".")

    return _TEMPLATE_HTML.replace("__AOI_NOME__", ctx["aoi_nome"]) \
        .replace("__AOI_SLUG__", ctx["aoi_slug"]) \
        .replace("__AOI_TIPOLOGIA__", str(ctx["aoi_tipologia"])) \
        .replace("__AOI_POPULACAO__", fmt_int(ctx["aoi_populacao"]) if isinstance(ctx["aoi_populacao"], (int, float)) else str(ctx["aoi_populacao"])) \
        .replace("__AOI_AREA_KM2__", f"{float(ctx['aoi_area_km2']):.1f}") \
        .replace("__AOI_IBGE__", str(ctx["aoi_ibge_code"])) \
        .replace("__BOUNDS_SW__", str(ctx["bounds_sw"])) \
        .replace("__BOUNDS_NE__", str(ctx["bounds_ne"])) \
        .replace("__TOTAL_FOOTPRINTS__", fmt_int(ctx["total_footprints"])) \
        .replace("__N_GOOGLE__", fmt_int(ctx["n_google"])) \
        .replace("__N_MICROSOFT__", fmt_int(ctx["n_microsoft"])) \
        .replace("__PCT_GOOGLE__", f"{ctx['pct_google']:.1f}") \
        .replace("__PCT_MICROSOFT__", f"{ctx['pct_microsoft']:.1f}") \
        .replace("__AREA_GOOGLE__", fmt_m2(ctx["area_google_m2"])) \
        .replace("__AREA_MICROSOFT__", fmt_m2(ctx["area_microsoft_m2"])) \
        .replace("__URL_GOOGLE__", ctx["url_google"]) \
        .replace("__URL_MICROSOFT__", ctx["url_microsoft"]) \
        .replace("__COR_GOOGLE__", ctx["cor_google"]) \
        .replace("__COR_MICROSOFT__", ctx["cor_microsoft"]) \
        .replace("__NOTA_DECIMACAO__", ctx["nota_decimacao"])


# =============================================================================
# Template HTML (string literal, interpolacao por .replace)
# =============================================================================
# Usa marcadores __NOME__ em vez de f-string para evitar conflito com
# chaves { } de CSS e JavaScript. O arquivo e autocontido: HTML + CSS
# + JS inline, Leaflet via CDN, GeoJSONs via fetch relativo.
_TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Open Buildings Explorer — __AOI_NOME__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
      crossorigin=""/>
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1a1a1a;
    background: #0b1220;
  }

  #app {
    display: flex;
    height: 100vh;
    width: 100vw;
  }

  #map {
    flex: 1;
    height: 100%;
    background: #e8ecef;
  }

  aside {
    width: 340px;
    min-width: 340px;
    background: #0f172a;
    color: #e2e8f0;
    overflow-y: auto;
    padding: 24px;
    border-left: 1px solid #1e293b;
  }

  aside h1 {
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 4px 0;
    color: #f8fafc;
  }

  aside .subtitulo {
    font-size: 13px;
    color: #94a3b8;
    margin: 0 0 20px 0;
  }

  .secao {
    margin-bottom: 24px;
    padding-bottom: 20px;
    border-bottom: 1px solid #1e293b;
  }

  .secao:last-child { border-bottom: none; }

  .secao h2 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #64748b;
    font-weight: 600;
    margin: 0 0 12px 0;
  }

  .meta-grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 12px;
    font-size: 13px;
  }

  .meta-grid dt { color: #94a3b8; }
  .meta-grid dd { margin: 0; color: #e2e8f0; }

  .stat-fonte {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 14px;
  }
  .stat-fonte:last-child { margin-bottom: 0; }

  .stat-swatch {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    margin-top: 4px;
    flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.1);
  }

  .stat-corpo { flex: 1; }

  .stat-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #94a3b8;
    margin-bottom: 2px;
  }

  .stat-num {
    font-size: 22px;
    font-weight: 600;
    color: #f8fafc;
    line-height: 1.1;
  }

  .stat-pct {
    font-size: 13px;
    color: #94a3b8;
    margin-left: 6px;
    font-weight: 400;
  }

  .stat-area {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 4px;
  }

  .camadas-ctrl label {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    cursor: pointer;
    border-radius: 6px;
    font-size: 13px;
    transition: background 0.15s;
  }

  .camadas-ctrl label:hover { background: #1e293b; }

  .camadas-ctrl input[type="checkbox"] {
    accent-color: #3b82f6;
    width: 16px;
    height: 16px;
    cursor: pointer;
  }

  .camadas-ctrl .swatch {
    width: 12px;
    height: 12px;
    border-radius: 2px;
    border: 1px solid rgba(255,255,255,0.1);
  }

  footer {
    font-size: 11px;
    color: #64748b;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #1e293b;
    line-height: 1.5;
  }
  footer a {
    color: #94a3b8;
    text-decoration: none;
  }
  footer a:hover { color: #e2e8f0; text-decoration: underline; }

  .popup-fonte {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: 600;
    font-size: 11px;
    color: white;
  }

  @media (max-width: 720px) {
    #app { flex-direction: column; }
    aside { width: 100%; min-width: 0; max-height: 45vh; border-left: none; border-top: 1px solid #1e293b; }
    #map { height: 55vh; }
  }
</style>
</head>
<body>
<div id="app">
  <div id="map" role="application" aria-label="Mapa interativo de edificacoes"></div>
  <aside>
    <h1>__AOI_NOME__</h1>
    <p class="subtitulo">Open Buildings Explorer BR</p>

    <div class="secao">
      <h2>Area de interesse</h2>
      <dl class="meta-grid">
        <dt>Codigo IBGE</dt><dd>__AOI_IBGE__</dd>
        <dt>Area oficial</dt><dd>__AOI_AREA_KM2__ km&sup2;</dd>
        <dt>Populacao 2022</dt><dd>__AOI_POPULACAO__ hab.</dd>
        <dt>Tipologia</dt><dd>__AOI_TIPOLOGIA__</dd>
      </dl>
    </div>

    <div class="secao">
      <h2>Edificacoes (__TOTAL_FOOTPRINTS__ no total)</h2>

      <div class="stat-fonte">
        <div class="stat-swatch" style="background: __COR_GOOGLE__"></div>
        <div class="stat-corpo">
          <div class="stat-label">Google Open Buildings</div>
          <div class="stat-num">__N_GOOGLE__<span class="stat-pct">__PCT_GOOGLE__%</span></div>
          <div class="stat-area">__AREA_GOOGLE__ edificados</div>
        </div>
      </div>

      <div class="stat-fonte">
        <div class="stat-swatch" style="background: __COR_MICROSOFT__"></div>
        <div class="stat-corpo">
          <div class="stat-label">Microsoft Building Footprints</div>
          <div class="stat-num">__N_MICROSOFT__<span class="stat-pct">__PCT_MICROSOFT__%</span></div>
          <div class="stat-area">__AREA_MICROSOFT__ edificados</div>
        </div>
      </div>
    </div>

    <div class="secao">
      <h2>Camadas</h2>
      <div class="camadas-ctrl">
        <label>
          <input type="checkbox" id="toggle-google" checked>
          <span class="swatch" style="background: __COR_GOOGLE__"></span>
          <span>Google</span>
        </label>
        <label>
          <input type="checkbox" id="toggle-microsoft" checked>
          <span class="swatch" style="background: __COR_MICROSOFT__"></span>
          <span>Microsoft</span>
        </label>
      </div>
    </div>

    <footer>
      Dados: VIDA Google-Microsoft Open Buildings &middot; Poligono IBGE 2022.
      Analise: DuckDB sobre S3 publico. __NOTA_DECIMACAO__
      <br><br>
      <a href="https://github.com/PedroLuizskt/open-buildings-explorer-br" target="_blank" rel="noopener">
        github.com/PedroLuizskt/open-buildings-explorer-br
      </a>
    </footer>
  </aside>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
        crossorigin=""></script>
<script>
  // Configuracao vinda do backend
  const BOUNDS_SW = __BOUNDS_SW__;  // [lat, lon]
  const BOUNDS_NE = __BOUNDS_NE__;
  const URL_GOOGLE = "__URL_GOOGLE__";
  const URL_MICROSOFT = "__URL_MICROSOFT__";
  const COR_GOOGLE = "__COR_GOOGLE__";
  const COR_MICROSOFT = "__COR_MICROSOFT__";

  // Canvas renderer: critico para performance com muitos poligonos
  const canvasRenderer = L.canvas({ padding: 0.5 });

  const map = L.map("map", {
    renderer: canvasRenderer,
    preferCanvas: true,
    zoomControl: true,
  });

  // Tile layer OSM
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  // Ajusta ao bounds da AOI
  map.fitBounds([BOUNDS_SW, BOUNDS_NE]);

  function estiloFootprint(cor) {
    return {
      color: cor,
      weight: 0.5,
      fillColor: cor,
      fillOpacity: 0.55,
    };
  }

  function popupFootprint(fonte, cor) {
    return function(feature, layer) {
      const label = fonte === "google" ? "Google" : "Microsoft";
      layer.bindPopup(
        '<div style="font-family: sans-serif; font-size: 12px;">' +
        '<div style="margin-bottom: 4px;">' +
        '<span class="popup-fonte" style="background: ' + cor + ';">' + label + '</span>' +
        '</div>' +
        'Fonte: ' + label +
        '</div>'
      );
    };
  }

  let camadaGoogle = null;
  let camadaMicrosoft = null;

  function carregarCamada(url, cor, fonte, callback) {
    if (!url) { callback(null); return; }
    fetch(url)
      .then(r => r.json())
      .then(gj => {
        const layer = L.geoJSON(gj, {
          renderer: canvasRenderer,
          style: () => estiloFootprint(cor),
          onEachFeature: popupFootprint(fonte, cor),
        });
        callback(layer);
      })
      .catch(err => {
        console.error("Erro ao carregar " + fonte + ":", err);
        callback(null);
      });
  }

  // Carrega as duas camadas em paralelo
  carregarCamada(URL_GOOGLE, COR_GOOGLE, "google", (layer) => {
    camadaGoogle = layer;
    if (layer) layer.addTo(map);
  });
  carregarCamada(URL_MICROSOFT, COR_MICROSOFT, "microsoft", (layer) => {
    camadaMicrosoft = layer;
    if (layer) layer.addTo(map);
  });

  // Toggles do painel lateral
  document.getElementById("toggle-google").addEventListener("change", (e) => {
    if (!camadaGoogle) return;
    if (e.target.checked) camadaGoogle.addTo(map);
    else map.removeLayer(camadaGoogle);
  });
  document.getElementById("toggle-microsoft").addEventListener("change", (e) => {
    if (!camadaMicrosoft) return;
    if (e.target.checked) camadaMicrosoft.addTo(map);
    else map.removeLayer(camadaMicrosoft);
  });
</script>
</body>
</html>
"""
