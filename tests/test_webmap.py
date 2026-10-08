"""Testes do modulo webmap (multi-AOI com dashboard).

Usa a fixture ``mini_dataset_parquet`` + AOI Cambuquira para exercitar
geracao end-to-end offline — nao requerem acesso ao S3 real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obr_explorer import duckdb_client as ddb
from obr_explorer import webmap
from obr_explorer.aoi import carregar_aoi


@pytest.fixture
def tabela_recorte_para_webmap(
    duckdb_conn, mini_dataset_parquet, path_geojson_cambuquira
):
    """Prepara tabela 'recorte_test' pronta para gerar webmap."""
    caminho = str(mini_dataset_parquet).replace("\\", "/")
    duckdb_conn.execute(f"CREATE TABLE fps AS SELECT * FROM '{caminho}'")
    ddb.carregar_aoi_geojson(duckdb_conn, path_geojson_cambuquira, "aoi_test")
    ddb.recortar_por_aoi(
        duckdb_conn,
        tabela_footprints="fps",
        tabela_aoi="aoi_test",
        tabela_recorte="recorte_test",
    )
    return "recorte_test"


@pytest.fixture
def aoi_cambuquira(aoi_dir):
    """Carrega a AOI de Cambuquira a partir dos GeoJSONs versionados."""
    return carregar_aoi("cambuquira_mg", diretorio=aoi_dir)


# =============================================================================
# Constantes do modulo
# =============================================================================
class TestConstantes:
    def test_cores_google_microsoft_brand_hex(self) -> None:
        assert webmap.COR_GOOGLE == "#4285F4"
        assert webmap.COR_MICROSOFT == "#00A4EF"

    def test_cores_fonte_mapping_completo(self) -> None:
        from obr_explorer import config

        assert webmap.CORES_FONTE[config.SOURCE_GOOGLE] == webmap.COR_GOOGLE
        assert webmap.CORES_FONTE[config.SOURCE_MICROSOFT] == webmap.COR_MICROSOFT


# =============================================================================
# Validacao
# =============================================================================
class TestValidacao:
    def test_rejeita_identificador_invalido(self) -> None:
        with pytest.raises(ValueError, match="invalido"):
            webmap._validar_identificador("1invalid")


# =============================================================================
# Subset por fonte
# =============================================================================
class TestCriarSubsetPorFonte:
    def test_subset_google_contem_apenas_google(
        self, duckdb_conn, tabela_recorte_para_webmap
    ) -> None:
        from obr_explorer import config

        n = webmap._criar_subset_por_fonte(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            tabela_destino="subset_google",
            fonte=config.SOURCE_GOOGLE,
            coluna_geom="geom",
            coluna_fonte=config.COLUMN_SOURCE,
            min_area_m2=None,
            simplify_tolerance=None,
        )
        # mini_dataset tem 10 google
        assert n == 10

    def test_subset_microsoft_contem_apenas_microsoft(
        self, duckdb_conn, tabela_recorte_para_webmap
    ) -> None:
        from obr_explorer import config

        n = webmap._criar_subset_por_fonte(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            tabela_destino="subset_microsoft",
            fonte=config.SOURCE_MICROSOFT,
            coluna_geom="geom",
            coluna_fonte=config.COLUMN_SOURCE,
            min_area_m2=None,
            simplify_tolerance=None,
        )
        assert n == 10

    def test_fonte_invalida_levanta(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="Fonte invalida"):
            webmap._criar_subset_por_fonte(
                duckdb_conn,
                tabela_recorte="t",
                tabela_destino="d",
                fonte="apple",
                coluna_geom="geom",
                coluna_fonte="bf_source",
                min_area_m2=None,
                simplify_tolerance=None,
            )

    def test_min_area_negativo_levanta(
        self, duckdb_conn, tabela_recorte_para_webmap
    ) -> None:
        from obr_explorer import config

        with pytest.raises(ValueError, match="min_area_m2"):
            webmap._criar_subset_por_fonte(
                duckdb_conn,
                tabela_recorte=tabela_recorte_para_webmap,
                tabela_destino="sub",
                fonte=config.SOURCE_GOOGLE,
                coluna_geom="geom",
                coluna_fonte=config.COLUMN_SOURCE,
                min_area_m2=-10,
                simplify_tolerance=None,
            )

    def test_simplify_tolerance_negativo_levanta(
        self, duckdb_conn, tabela_recorte_para_webmap
    ) -> None:
        from obr_explorer import config

        with pytest.raises(ValueError, match="simplify_tolerance"):
            webmap._criar_subset_por_fonte(
                duckdb_conn,
                tabela_recorte=tabela_recorte_para_webmap,
                tabela_destino="sub",
                fonte=config.SOURCE_GOOGLE,
                coluna_geom="geom",
                coluna_fonte=config.COLUMN_SOURCE,
                min_area_m2=None,
                simplify_tolerance=-1,
            )


# =============================================================================
# Geracao do webmap end-to-end
# =============================================================================
class TestGerarWebmap:
    def test_gera_html_e_geojsons(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        assert output_html.exists()
        assert output_html.name == "index.html"
        assert output_html.suffix == ".html"

        # GeoJSONs por fonte
        data_dir = tmp_path / "data"
        assert data_dir.exists()
        assert (data_dir / f"{aoi_cambuquira.nome}_google.geojson").exists()
        assert (data_dir / f"{aoi_cambuquira.nome}_microsoft.geojson").exists()

    def test_geojsons_sao_feature_collections_validas(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )

        for fonte in ("google", "microsoft"):
            caminho = tmp_path / "data" / f"{aoi_cambuquira.nome}_{fonte}.geojson"
            with caminho.open(encoding="utf-8") as f:
                gj = json.load(f)
            assert gj["type"] == "FeatureCollection"
            assert len(gj["features"]) == 10  # mini_dataset: 10 por fonte

    def test_html_contem_nome_aoi(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert "Cambuquira" in conteudo
        # Cores das fontes
        assert webmap.COR_GOOGLE in conteudo
        assert webmap.COR_MICROSOFT in conteudo
        # Leaflet CDN
        assert "leaflet@1.9.4" in conteudo or "leaflet.js" in conteudo

    def test_html_contem_bounds_para_fitBounds(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        """No multi-AOI, bounds vem no payload JSON por AOI, nao em constantes globais."""
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert "bounds_sw" in conteudo  # chave no payload JSON
        assert "bounds_ne" in conteudo
        assert "fitBounds" in conteudo

    def test_html_contem_canvas_renderer(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        """Regressao: canvas renderer eh critico para performance com muitos poligonos."""
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert "L.canvas" in conteudo
        assert "preferCanvas: true" in conteudo

    def test_html_tem_toggles_de_camada(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert 'id="toggle-google"' in conteudo
        assert 'id="toggle-microsoft"' in conteudo

    def test_html_tem_meta_viewport_responsivo(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert 'name="viewport"' in conteudo
        assert "width=device-width" in conteudo

    def test_html_tem_charset_utf8(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert 'charset="UTF-8"' in conteudo

    def test_min_area_decimacao_aplica(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        """Com min_area_m2 alto, deve descartar todos os footprints sinteticos
        (que tem ~12k m2 cada)."""
        webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
            min_area_m2=1_000_000,  # 1 km2 — grande demais para os quadrados sinteticos
        )
        for fonte in ("google", "microsoft"):
            caminho = tmp_path / "data" / f"{aoi_cambuquira.nome}_{fonte}.geojson"
            with caminho.open(encoding="utf-8") as f:
                gj = json.load(f)
            # Todos devem ter sido filtrados
            assert len(gj["features"]) == 0

    def test_nota_decimacao_aparece_quando_aplica(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
            min_area_m2=50,
            simplify_tolerance=1e-5,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert "min_area_m2 = 50" in conteudo
        assert "simplify_tolerance" in conteudo


# =============================================================================
# Multi-AOI: gerar_webmap_multi + payload JSON
# =============================================================================
class TestGerarWebmapMulti:
    def test_rejeita_lista_vazia(self, duckdb_conn, tmp_path) -> None:
        with pytest.raises(ValueError, match="vazia"):
            webmap.gerar_webmap_multi(
                duckdb_conn,
                aois_e_tabelas=[],
                output_dir=tmp_path,
            )

    def test_gera_html_com_uma_aoi(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        output = webmap.gerar_webmap_multi(
            duckdb_conn,
            aois_e_tabelas=[(aoi_cambuquira, tabela_recorte_para_webmap)],
            output_dir=tmp_path,
        )
        assert output.exists()
        conteudo = output.read_text(encoding="utf-8")
        # Payload AOIS como JSON
        assert "window.AOIS" in conteudo
        # Chart.js carregado
        assert "chart.js" in conteudo.lower() or "chart.umd" in conteudo
        # Fontes Google
        assert "Barlow+Condensed" in conteudo
        # Seletor de AOI
        assert 'id="aoi-select"' in conteudo
        # Tabs
        assert 'data-tab="geral"' in conteudo
        assert 'data-tab="analise"' in conteudo
        assert 'data-tab="detalhe"' in conteudo

    def test_html_contem_payload_json_valido(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        import re as _re

        output = webmap.gerar_webmap_multi(
            duckdb_conn,
            aois_e_tabelas=[(aoi_cambuquira, tabela_recorte_para_webmap)],
            output_dir=tmp_path,
        )
        conteudo = output.read_text(encoding="utf-8")
        # Extrai o payload JSON da linha "window.AOIS = ...;"
        match = _re.search(r"window\.AOIS\s*=\s*(\[.*?\]);", conteudo, _re.DOTALL)
        assert match is not None, "Payload window.AOIS nao encontrado no HTML"
        payload = json.loads(match.group(1))
        assert isinstance(payload, list)
        assert len(payload) == 1
        aoi0 = payload[0]
        assert aoi0["slug"] == "cambuquira_mg"
        assert "resumo" in aoi0
        assert "histograma" in aoi0
        assert "arquivos_fonte" in aoi0
        assert "area_km2_oficial" in aoi0

    def test_geojsons_exportados_tem_area_m2(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        """Regressao: GeoJSONs exportados devem ter area_m2 por feature
        para alimentar popups ricos no webmap."""
        webmap.gerar_webmap_multi(
            duckdb_conn,
            aois_e_tabelas=[(aoi_cambuquira, tabela_recorte_para_webmap)],
            output_dir=tmp_path,
        )
        caminho = tmp_path / "data" / f"{aoi_cambuquira.nome}_google.geojson"
        with caminho.open(encoding="utf-8") as f:
            gj = json.load(f)
        assert gj["features"]
        props = gj["features"][0]["properties"]
        assert "area_m2" in props
        assert isinstance(props["area_m2"], (int, float))
        assert props["area_m2"] > 0


class TestHistogramaAreas:
    def test_histograma_retorna_buckets_fixos(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
    ) -> None:
        from obr_explorer import config

        hist = webmap._computar_histograma_areas(
            duckdb_conn,
            tabela=tabela_recorte_para_webmap,
            coluna_geom="geom",
            coluna_fonte=config.COLUMN_SOURCE,
            lat_media=-21.88,
        )
        # Estrutura: {fonte: {bucket: contagem}}
        assert "google" in hist
        assert "microsoft" in hist
        buckets_esperados = {"<50", "50-100", "100-200", "200-500", ">=500"}
        assert set(hist["google"].keys()) == buckets_esperados
        assert set(hist["microsoft"].keys()) == buckets_esperados


class TestPropertiesParaJson:
    def test_tipos_primitivos_passam(self) -> None:
        props = {
            "nome": "Cambuquira",
            "pop": 12609,
            "ativo": True,
            "nulo": None,
        }
        out = webmap._properties_para_json(props)
        assert out == props

    def test_float_numpy_vira_float_puro(self) -> None:
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy indisponivel")
        out = webmap._properties_para_json({"area": np.float64(246.38)})
        assert isinstance(out["area"], float)
        assert out["area"] == pytest.approx(246.38)


class TestCompatComAPIAnterior:
    def test_gerar_webmap_comparativo_ainda_funciona(
        self,
        duckdb_conn,
        tabela_recorte_para_webmap,
        aoi_cambuquira,
        tmp_path,
    ) -> None:
        """Backward-compat: gerar_webmap_comparativo delega para gerar_webmap_multi."""
        output = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        assert output.exists()
        assert output.name == "index.html"
