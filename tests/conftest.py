"""Fixtures compartilhadas para toda a suíte de testes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# =============================================================================
# Paths e GeoJSONs versionados
# =============================================================================
@pytest.fixture
def repo_root() -> Path:
    """Caminho absoluto para a raiz do repositório."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def aoi_dir(repo_root) -> Path:
    """Diretório com os GeoJSONs das AOIs versionadas."""
    return repo_root / "data" / "external" / "aois"


@pytest.fixture
def geojson_cambuquira(aoi_dir) -> dict:
    """Carrega o GeoJSON de Cambuquira/MG como dict."""
    with (aoi_dir / "cambuquira_mg.geojson").open() as f:
        return json.load(f)


@pytest.fixture
def geojson_uberlandia(aoi_dir) -> dict:
    """Carrega o GeoJSON de Uberlândia/MG como dict."""
    with (aoi_dir / "uberlandia_mg.geojson").open() as f:
        return json.load(f)


@pytest.fixture
def path_geojson_cambuquira(aoi_dir) -> Path:
    """Caminho absoluto do GeoJSON de Cambuquira."""
    return aoi_dir / "cambuquira_mg.geojson"


# =============================================================================
# DuckDB — fixtures que exigem duckdb
# =============================================================================
@pytest.fixture
def duckdb_conn():
    """Conexão DuckDB in-memory com extensão spatial já carregada.

    A extensão spatial é baixada do CDN oficial do DuckDB na primeira
    execução (depois fica em cache local em ~/.duckdb/extensions/).
    Se o ambiente não permitir esse download inicial (sandbox sem
    internet, firewall corporativo), o teste é pulado com pytest.skip
    em vez de falhar — o desenvolvedor consegue rodar a suite offline
    depois de ter baixado a extensao uma vez.
    """
    import duckdb

    con = duckdb.connect(":memory:")
    try:
        con.execute("INSTALL spatial;")
        con.execute("LOAD spatial;")
    except duckdb.Error as e:
        con.close()
        pytest.skip(f"Extensao spatial indisponivel neste ambiente: {e}")
    yield con
    con.close()


@pytest.fixture
def duckdb_conn_completa():
    """Conexão DuckDB in-memory com extensões httpfs + spatial + S3 configurado.

    Use apenas em testes marcados com ``@pytest.mark.network`` — a
    primeira execução baixa a extensão httpfs, o que requer rede.
    """
    import duckdb

    con = duckdb.connect(":memory:")
    for ext in ("httpfs", "spatial"):
        con.execute(f"INSTALL {ext};")
        con.execute(f"LOAD {ext};")
    con.execute("SET s3_region='us-west-2';")
    yield con
    con.close()


@pytest.fixture
def mini_dataset_parquet(tmp_path, duckdb_conn):
    """Gera um mini-dataset Parquet local com estrutura similar ao Open Buildings.

    Retorna o caminho para o arquivo Parquet. Contém 20 footprints
    sintéticos (10 Google + 10 Microsoft) em polígonos WGS84 dentro
    de uma bounding box pequena no sul de MG (perto de Cambuquira),
    permitindo testar recorte espacial sem depender do S3 real.

    Estrutura da tabela:

    - ``geometry`` (POLYGON, WGS84)
    - ``bf_source`` ('google' ou 'microsoft')
    - ``area_in_meters`` (float, area do footprint)
    - ``confidence`` (float, score de confianca do extractor)
    """
    caminho = tmp_path / "mini_footprints.parquet"

    # Gera 20 quadrados pequenos (~110m x 110m) espalhados numa grade
    # dentro da bounding box (-45.34 a -45.325, -21.879 a -21.872)
    # que é subset da AOI Cambuquira.
    linhas_sql = []
    lat_base = -21.88
    lon_base = -45.34
    delta = 0.001  # ~110m em latitude

    for i in range(20):
        lat = lat_base + (i // 5) * delta * 2
        lon = lon_base + (i % 5) * delta * 2
        # Polígono quadrado fechado (5 pontos)
        wkt = (
            f"POLYGON(("
            f"{lon} {lat}, "
            f"{lon + delta} {lat}, "
            f"{lon + delta} {lat + delta}, "
            f"{lon} {lat + delta}, "
            f"{lon} {lat}"
            f"))"
        )
        fonte = "google" if i < 10 else "microsoft"
        area = 12100.0 + i * 100  # ~100m x 100m, variando
        confidence = 0.85 + (i % 10) * 0.01
        linhas_sql.append(
            f"(ST_GeomFromText('{wkt}'), '{fonte}', {area}, {confidence})"
        )

    values_clause = ",\n".join(linhas_sql)
    duckdb_conn.execute(f"""
        CREATE OR REPLACE TABLE mini_footprints AS
        SELECT * FROM (VALUES
            {values_clause}
        ) AS t(geometry, bf_source, area_in_meters, confidence);
    """)

    caminho_str = str(caminho).replace("\\", "/")
    duckdb_conn.execute(f"COPY mini_footprints TO '{caminho_str}' (FORMAT PARQUET);")

    return caminho
