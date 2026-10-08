"""Testes do modulo webmap.

Usa a fixture ``mini_dataset_parquet`` + AOI Cambuquira para exercitar
geracao end-to-end (recorte -> export GeoJSONs por fonte -> HTML).
Testes offline — nao requerem acesso ao S3 real.
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
    """Prepara tabela 'recorte_test' pronta para gerar webmap.

    Reusa o mini_dataset_parquet + AOI Cambuquira para ter uma tabela
    com footprints Google e Microsoft dentro de um poligono real.
    """
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
        output_html = webmap.gerar_webmap_comparativo(
            duckdb_conn,
            tabela_recorte=tabela_recorte_para_webmap,
            aoi=aoi_cambuquira,
            output_dir=tmp_path,
        )
        conteudo = output_html.read_text(encoding="utf-8")
        assert "BOUNDS_SW" in conteudo
        assert "BOUNDS_NE" in conteudo
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
# Contexto do template
# =============================================================================
class TestMontarContextoHtml:
    def test_contexto_tem_todas_chaves_esperadas(
        self, aoi_cambuquira
    ) -> None:
        from obr_explorer.analysis import ResumoAOI

        resumo = ResumoAOI(
            aoi_nome="Cambuquira/MG",
            tabela="t",
            total_footprints=12182,
            por_fonte={"google": 11298, "microsoft": 884},
            area_total_m2_por_fonte={"google": 1_093_409, "microsoft": 50_902},
            area_media_m2_por_fonte={"google": 96.8, "microsoft": 57.6},
        )
        ctx = webmap._montar_contexto_html(
            aoi=aoi_cambuquira,
            resumo=resumo,
            arquivos_fonte={
                "google": "data/x_google.geojson",
                "microsoft": "data/x_microsoft.geojson",
            },
            min_area_m2=None,
            simplify_tolerance=None,
        )
        chaves_esperadas = {
            "aoi_nome", "aoi_slug", "aoi_tipologia", "aoi_populacao",
            "aoi_area_km2", "aoi_ibge_code", "bounds_sw", "bounds_ne",
            "total_footprints", "n_google", "n_microsoft",
            "pct_google", "pct_microsoft",
            "area_google_m2", "area_microsoft_m2",
            "url_google", "url_microsoft",
            "cor_google", "cor_microsoft",
            "nota_decimacao",
        }
        assert chaves_esperadas.issubset(ctx.keys())
        assert ctx["pct_google"] == pytest.approx(11298 / 12182 * 100, rel=1e-3)

    def test_bounds_formato_leaflet(self, aoi_cambuquira) -> None:
        from obr_explorer.analysis import ResumoAOI

        resumo = ResumoAOI(
            aoi_nome="x", tabela="t", total_footprints=0,
            por_fonte={}, area_total_m2_por_fonte={}, area_media_m2_por_fonte={},
        )
        ctx = webmap._montar_contexto_html(
            aoi=aoi_cambuquira, resumo=resumo,
            arquivos_fonte={}, min_area_m2=None, simplify_tolerance=None,
        )
        # Leaflet espera [lat, lon], nao [lon, lat]
        assert len(ctx["bounds_sw"]) == 2
        assert len(ctx["bounds_ne"]) == 2
        # Latitude de Cambuquira esta em torno de -21.9
        assert -22 < ctx["bounds_sw"][0] < -21
        assert -22 < ctx["bounds_ne"][0] < -21
