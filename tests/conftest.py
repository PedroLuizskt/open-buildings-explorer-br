"""Fixtures compartilhadas para toda a suíte de testes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


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
