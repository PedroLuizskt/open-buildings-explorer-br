"""Testes do modulo analysis.

Usa a fixture ``mini_dataset_parquet`` (do conftest) + AOI Cambuquira
para exercitar todo o pipeline de análise offline.
"""

from __future__ import annotations

import pytest

from obr_explorer import analysis
from obr_explorer import duckdb_client as ddb


@pytest.fixture
def tabela_recorte(duckdb_conn, mini_dataset_parquet, path_geojson_cambuquira):
    """Prepara tabela 'recorte' pronta para os testes de analysis.

    Carrega mini_dataset + AOI Cambuquira e faz recorte espacial.
    Retorna o nome da tabela ('recorte').
    """
    caminho = str(mini_dataset_parquet).replace("\\", "/")
    duckdb_conn.execute(f"CREATE TABLE footprints AS SELECT * FROM '{caminho}'")
    ddb.carregar_aoi_geojson(duckdb_conn, path_geojson_cambuquira, "aoi")
    ddb.recortar_por_aoi(
        duckdb_conn,
        tabela_footprints="footprints",
        tabela_aoi="aoi",
        tabela_recorte="recorte",
    )
    return "recorte"


# =============================================================================
# Validação de identificadores
# =============================================================================
class TestValidacao:
    def test_rejeita_nome_invalido(self) -> None:
        with pytest.raises(ValueError, match="invalido"):
            analysis._validar_identificador("1abc")


# =============================================================================
# Contagens
# =============================================================================
class TestContagens:
    def test_contar_total(self, duckdb_conn, tabela_recorte) -> None:
        n = analysis.contar_total(duckdb_conn, tabela_recorte)
        assert n == 20

    def test_contar_por_fonte(self, duckdb_conn, tabela_recorte) -> None:
        por = analysis.contar_por_fonte(duckdb_conn, tabela_recorte)
        # Mini-dataset tem 10 google + 10 microsoft
        assert por == {"google": 10, "microsoft": 10}

    def test_contar_valida_tabela(self, duckdb_conn) -> None:
        with pytest.raises(ValueError):
            analysis.contar_total(duckdb_conn, "1invalid")


# =============================================================================
# Áreas
# =============================================================================
class TestAreas:
    def test_area_total_por_fonte(self, duckdb_conn, tabela_recorte) -> None:
        areas = analysis.area_total_por_fonte(
            duckdb_conn, tabela_recorte, lat_media=-21.88,
        )
        assert "google" in areas
        assert "microsoft" in areas
        # Ambas as fontes devem ter area positiva
        assert areas["google"] > 0
        assert areas["microsoft"] > 0
        # Sanidade: 10 quadrados de ~110m x 110m = ~120.000 m² totais
        # Em graus^2, cada quadrado tem 1e-6 -> total ~1e-5 graus^2
        # Convertido: 1e-5 * (111000)^2 * cos(21.88°) ~= 100.000 a 150.000 m²
        assert 10_000 < areas["google"] < 1_000_000


# =============================================================================
# Resumo
# =============================================================================
class TestResumo:
    def test_resumo_estrutura_completa(self, duckdb_conn, tabela_recorte) -> None:
        r = analysis.resumo_aoi(
            duckdb_conn, tabela_recorte, aoi_nome="teste", lat_media=-21.88,
        )
        assert r.aoi_nome == "teste"
        assert r.total_footprints == 20
        assert r.por_fonte == {"google": 10, "microsoft": 10}
        assert "google" in r.area_total_m2_por_fonte
        assert "google" in r.area_media_m2_por_fonte

    def test_resumo_to_dict_serializavel_em_json(
        self, duckdb_conn, tabela_recorte
    ) -> None:
        import json

        r = analysis.resumo_aoi(duckdb_conn, tabela_recorte, aoi_nome="teste")
        # Deve ser serializavel sem erro
        s = json.dumps(r.to_dict())
        assert '"total_footprints": 20' in s


# =============================================================================
# Comparação entre AOIs
# =============================================================================
class TestComparacaoAOIs:
    def test_comparar_uma_unica_aoi(self, duckdb_conn, tabela_recorte) -> None:
        cmp = analysis.comparar_aois(
            duckdb_conn,
            tabelas_por_aoi={"teste": tabela_recorte},
        )
        assert "teste" in cmp.resumos
        assert cmp.resumos["teste"].total_footprints == 20

    def test_comparar_com_bounds_calcula_densidade(
        self, duckdb_conn, tabela_recorte
    ) -> None:
        # Bounds pequenos: ~1 km² total
        bounds = {"teste": (-45.34, -21.88, -45.33, -21.87)}
        cmp = analysis.comparar_aois(
            duckdb_conn,
            tabelas_por_aoi={"teste": tabela_recorte},
            bounds_por_aoi=bounds,
        )
        assert "teste" in cmp.densidade_por_km2
        assert cmp.densidade_por_km2["teste"] > 0


# =============================================================================
# Formatação texto
# =============================================================================
class TestFormatacao:
    def test_formatar_resumo_texto_produz_string_multilinha(
        self, duckdb_conn, tabela_recorte
    ) -> None:
        r = analysis.resumo_aoi(duckdb_conn, tabela_recorte, aoi_nome="Cambuquira/MG")
        s = analysis.formatar_resumo_texto(r)
        assert "Cambuquira/MG" in s
        assert "google" in s.lower()
        assert "microsoft" in s.lower()
        assert "\n" in s

    def test_formatar_comparacao_texto(self, duckdb_conn, tabela_recorte) -> None:
        cmp = analysis.comparar_aois(
            duckdb_conn,
            tabelas_por_aoi={"teste": tabela_recorte},
            bounds_por_aoi={"teste": (-45.34, -21.88, -45.33, -21.87)},
        )
        s = analysis.formatar_comparacao_texto(cmp)
        assert "teste" in s
        assert "Google" in s or "google" in s.lower()

    def test_formatar_comparacao_vazia(self) -> None:
        s = analysis.formatar_comparacao_texto(analysis.ComparacaoAOIs())
        assert "Nenhuma" in s
