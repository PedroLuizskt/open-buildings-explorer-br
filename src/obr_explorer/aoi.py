"""Gerenciamento de áreas de interesse (AOIs).

**Este módulo será implementado na Fase C.**

Escopo previsto
---------------

- ``listar_aois()`` — retorna lista de dicts com metadata das AOIs
  disponíveis em ``data/external/aois/`` (nome, arquivo, bounding box,
  área aproximada em km²).

- ``carregar_aoi(nome: str)`` — carrega um GeoJSON de AOI e retorna
  como :class:`geopandas.GeoDataFrame` em EPSG:4326.

- ``validar_aoi(gdf: GeoDataFrame)`` — verifica que a AOI é um polígono
  válido em coordenadas geográficas, com uma única feature, sem
  geometria auto-intersectante.

- ``AOI`` dataclass — encapsula nome, arquivo, GeoDataFrame carregado,
  bounding box e metadata descritiva; usado como tipo de retorno
  por ``carregar_aoi``.

Convenções técnicas
-------------------

- Nome de AOI segue snake_case: ``cambuquira_mg``, ``uberlandia_mg``
- Arquivo GeoJSON tem o mesmo nome do AOI: ``cambuquira_mg.geojson``
- Toda AOI tem que estar em WGS84 (EPSG:4326) — dataset Open Buildings
  também está em WGS84, então operações espaciais funcionam direto
- Uma AOI = uma feature (um polígono ou multipolígono só)
- Propriedades opcionais mas recomendadas no GeoJSON: ``nome``,
  ``descricao``, ``area_km2``, ``populacao_2022``

AOIs incluídas nesta fase
-------------------------

- ``cambuquira_mg`` — Cambuquira/MG, ~110 km², rural pequena
- ``uberlandia_mg`` — Uberlândia/MG (área urbana consolidada),
  ~220 km², cidade média-grande

Testes previstos
----------------

- Listagem retorna as duas AOIs configuradas
- Carregamento produz GeoDataFrame válido em EPSG:4326
- Erro descritivo ao pedir AOI inexistente
- Validação detecta geometria auto-intersectante
"""

from __future__ import annotations

# Placeholder — implementação virá na Fase C.


def listar_aois():  # pragma: no cover
    """Lista AOIs disponíveis em data/external/aois/. [Fase C]"""
    raise NotImplementedError("Será implementado na Fase C.")


def carregar_aoi(nome: str):  # pragma: no cover
    """Carrega uma AOI por nome, retorna GeoDataFrame em EPSG:4326. [Fase C]"""
    raise NotImplementedError("Será implementado na Fase C.")
