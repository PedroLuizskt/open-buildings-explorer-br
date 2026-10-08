"""Testes do modulo aoi.

Cobre listagem, carga, validação e o pipeline de fetch IBGE
(testes de rede marcados com @pytest.mark.network).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obr_explorer import aoi


# =============================================================================
# Listagem e carregamento
# =============================================================================
class TestListarAOIs:
    def test_lista_aois_versionadas(self, aoi_dir: Path) -> None:
        aois = aoi.listar_aois(diretorio=aoi_dir)
        nomes = {a["nome"] for a in aois}
        assert "cambuquira_mg" in nomes
        assert "uberlandia_mg" in nomes

    def test_cada_aoi_tem_metadata(self, aoi_dir: Path) -> None:
        aois = aoi.listar_aois(diretorio=aoi_dir)
        for a in aois:
            assert "properties" in a
            assert "nome" in a["properties"]

    def test_diretorio_inexistente_retorna_lista_vazia(self, tmp_path: Path) -> None:
        assert aoi.listar_aois(diretorio=tmp_path / "nao_existe") == []

    def test_arquivo_invalido_e_pulado(self, tmp_path: Path) -> None:
        (tmp_path / "invalido.geojson").write_text("nao eh json")
        (tmp_path / "cambuquira_mg.geojson").write_text(json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"nome": "Cambuquira"},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [-45.36, -21.90], [-45.36, -21.82], [-45.24, -21.82],
                    [-45.24, -21.90], [-45.36, -21.90],
                ]]},
            }],
        }))
        aois = aoi.listar_aois(diretorio=tmp_path)
        assert len(aois) == 1
        assert aois[0]["nome"] == "cambuquira_mg"


class TestCarregarAOI:
    def test_carrega_cambuquira(self, aoi_dir: Path) -> None:
        a = aoi.carregar_aoi("cambuquira_mg", diretorio=aoi_dir)
        assert a.nome == "cambuquira_mg"
        assert a.properties["nome"] == "Cambuquira"
        assert a.properties["uf"] == "MG"
        # Bounds no sul de MG
        minx, miny, maxx, maxy = a.bounds
        assert -46 <= minx < maxx <= -44
        assert -22 <= miny < maxy <= -21

    def test_carrega_uberlandia(self, aoi_dir: Path) -> None:
        a = aoi.carregar_aoi("uberlandia_mg", diretorio=aoi_dir)
        # Nome oficial IBGE mantem acento
        assert a.properties["nome"] == "Uberlândia"

    def test_aoi_inexistente_levanta_file_not_found(
        self, aoi_dir: Path
    ) -> None:
        with pytest.raises(FileNotFoundError, match="aoi_que_nao_existe"):
            aoi.carregar_aoi("aoi_que_nao_existe", diretorio=aoi_dir)

    def test_nome_exibicao(self, aoi_dir: Path) -> None:
        a = aoi.carregar_aoi("cambuquira_mg", diretorio=aoi_dir)
        assert a.nome_exibicao == "Cambuquira/MG"

    def test_area_km2_aproximada_positiva(self, aoi_dir: Path) -> None:
        a = aoi.carregar_aoi("cambuquira_mg", diretorio=aoi_dir)
        assert a.area_km2_aproximada > 0


# =============================================================================
# Validação
# =============================================================================
class TestValidarGeojsonAOI:
    def _make_geojson(self, geom_type: str = "Polygon") -> dict:
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": geom_type,
                    "coordinates": [[
                        [-45.36, -21.90], [-45.36, -21.82], [-45.24, -21.82],
                        [-45.24, -21.90], [-45.36, -21.90],
                    ]],
                },
            }],
        }

    def test_valido_nao_levanta(self) -> None:
        aoi.validar_geojson_aoi(self._make_geojson())

    def test_multipolygon_valido(self) -> None:
        gj = self._make_geojson()
        # Envolve em mais um nivel para virar MultiPolygon
        gj["features"][0]["geometry"]["type"] = "MultiPolygon"
        gj["features"][0]["geometry"]["coordinates"] = [
            gj["features"][0]["geometry"]["coordinates"]
        ]
        aoi.validar_geojson_aoi(gj)

    def test_rejeita_nao_feature_collection(self) -> None:
        with pytest.raises(ValueError, match="FeatureCollection"):
            aoi.validar_geojson_aoi({"type": "Feature", "features": []})

    def test_rejeita_zero_features(self) -> None:
        gj = self._make_geojson()
        gj["features"] = []
        with pytest.raises(ValueError, match="exatamente 1 feature"):
            aoi.validar_geojson_aoi(gj)

    def test_rejeita_multiplas_features(self) -> None:
        gj = self._make_geojson()
        gj["features"] = [gj["features"][0], gj["features"][0]]
        with pytest.raises(ValueError, match="exatamente 1 feature"):
            aoi.validar_geojson_aoi(gj)

    def test_rejeita_geometria_nao_poligonal(self) -> None:
        gj = self._make_geojson()
        gj["features"][0]["geometry"] = {
            "type": "Point", "coordinates": [-45.3, -21.85]
        }
        with pytest.raises(ValueError, match="Polygon ou MultiPolygon"):
            aoi.validar_geojson_aoi(gj)

    def test_rejeita_longitude_fora_do_range(self) -> None:
        gj = self._make_geojson()
        gj["features"][0]["geometry"]["coordinates"] = [[
            [-200, -21.90], [200, -21.90], [200, -21.82],
            [-200, -21.82], [-200, -21.90],
        ]]
        with pytest.raises(ValueError, match="longitude"):
            aoi.validar_geojson_aoi(gj)


# =============================================================================
# Bounds
# =============================================================================
class TestCalcularBounds:
    def test_polygon_simples(self) -> None:
        geom = {
            "type": "Polygon",
            "coordinates": [[
                [-45.36, -21.90], [-45.36, -21.82], [-45.24, -21.82],
                [-45.24, -21.90], [-45.36, -21.90],
            ]],
        }
        b = aoi._calcular_bounds(geom)
        assert b == (-45.36, -21.90, -45.24, -21.82)

    def test_multipolygon(self) -> None:
        geom = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[-46, -22], [-45, -22], [-45, -21], [-46, -21], [-46, -22]]],
                [[[-48, -24], [-47, -24], [-47, -23], [-48, -23], [-48, -24]]],
            ],
        }
        b = aoi._calcular_bounds(geom)
        assert b == (-48.0, -24.0, -45.0, -21.0)

    def test_geometria_vazia_levanta(self) -> None:
        with pytest.raises(ValueError, match="coordenadas"):
            aoi._calcular_bounds({"coordinates": []})


# =============================================================================
# Download IBGE
# =============================================================================
class TestBaixarMalhaIBGE:
    @pytest.mark.parametrize("codigo", ["abc123", "12345", "12345678", "", "31116 06"])
    def test_codigo_invalido_levanta(self, codigo: str) -> None:
        with pytest.raises(ValueError, match="Codigo IBGE"):
            aoi.baixar_malha_ibge(codigo)

    def test_qualidade_invalida_levanta(self) -> None:
        with pytest.raises(ValueError, match="Qualidade"):
            aoi.baixar_malha_ibge("3111606", qualidade="super")

    @pytest.mark.network
    def test_baixa_cambuquira_real(self) -> None:
        """Baixa a malha real de Cambuquira/MG (codigo IBGE 3110707) via API."""
        gj = aoi.baixar_malha_ibge("3110707", qualidade="minima")
        assert gj["type"] == "FeatureCollection"
        assert len(gj["features"]) >= 1
        # Verifica que o poligono esta na regiao esperada (sul de MG)
        geom = gj["features"][0]["geometry"]
        b = aoi._calcular_bounds(geom)
        assert -46 <= b[0] < b[2] <= -44
        assert -22 <= b[1] < b[3] <= -21


class TestSalvarAOIDoIBGE:
    def test_nome_slug_invalido_levanta(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="nome_slug"):
            aoi.salvar_aoi_do_ibge(
                "3111606", "nome com espaco", {}, diretorio=tmp_path,
            )

    def test_arquivo_existente_sem_sobrescrever(self, tmp_path: Path) -> None:
        existente = tmp_path / "cambuquira_mg.geojson"
        existente.write_text("{}")
        with pytest.raises(FileExistsError):
            aoi.salvar_aoi_do_ibge(
                "3110707", "cambuquira_mg", {}, diretorio=tmp_path,
            )

    @pytest.mark.network
    def test_baixa_e_salva_cambuquira(self, tmp_path: Path) -> None:
        """Baixa Cambuquira via API IBGE e salva com metadata padrao."""
        destino = aoi.salvar_aoi_do_ibge(
            codigo_ibge="3110707",
            nome_slug="cambuquira_mg",
            metadata=aoi.METADATA_PADRAO["cambuquira_mg"],
            diretorio=tmp_path,
            qualidade="minima",
            sobrescrever=True,
        )
        assert destino.exists()
        # Verifica que a AOI gerada carrega corretamente
        a = aoi.carregar_aoi("cambuquira_mg", diretorio=tmp_path)
        assert a.properties["nome"] == "Cambuquira"
        assert a.properties["ibge_code"] == "3110707"


class TestMetadataPadrao:
    def test_cambuquira_tem_metadata_padrao(self) -> None:
        m = aoi.METADATA_PADRAO["cambuquira_mg"]
        assert m["nome"] == "Cambuquira"
        assert m["uf"] == "MG"
        # Codigo IBGE correto de Cambuquira/MG: 3110707 (nao 3111606)
        assert m["ibge_code"] == "3110707"
        assert m["area_km2_oficial"] == 246.380

    def test_uberlandia_tem_metadata_padrao(self) -> None:
        m = aoi.METADATA_PADRAO["uberlandia_mg"]
        assert m["nome"] == "Uberlandia"
        assert m["uf"] == "MG"
        assert m["ibge_code"] == "3170206"
        assert m["area_km2_oficial"] == 4115.206
