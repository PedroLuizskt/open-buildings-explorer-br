"""Testes smoke da Fase A.

Estes testes validam apenas a estrutura do projeto e a saúde dos
imports — nada de lógica de negócio, porque a Fase A é setup. Servem
como rede de segurança para detectar quebras estruturais assim que
acontecerem (arquivo movido, dependência quebrada, config
malformada), antes que as fases seguintes acrescentem lógica em cima.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# =============================================================================
# Estrutura de diretórios
# =============================================================================
class TestEstruturaDiretorios:
    """A árvore de diretórios essencial existe."""

    def test_src_obr_explorer_existe(self, repo_root: Path) -> None:
        assert (repo_root / "src" / "obr_explorer").is_dir()

    def test_tests_existe(self, repo_root: Path) -> None:
        assert (repo_root / "tests").is_dir()

    def test_data_external_aois_existe(self, repo_root: Path) -> None:
        assert (repo_root / "data" / "external" / "aois").is_dir()

    def test_docs_existe(self, repo_root: Path) -> None:
        assert (repo_root / "docs").is_dir()

    def test_webmap_existe(self, repo_root: Path) -> None:
        assert (repo_root / "webmap").is_dir()

    @pytest.mark.parametrize(
        "arquivo",
        [
            "README.md",
            "LICENSE",
            "pyproject.toml",
            "Makefile",
            "tasks.ps1",
            ".gitignore",
            ".env.example",
        ],
    )
    def test_arquivos_raiz_existem(self, repo_root: Path, arquivo: str) -> None:
        assert (repo_root / arquivo).is_file(), f"Arquivo ausente: {arquivo}"


# =============================================================================
# Módulos importáveis
# =============================================================================
class TestImports:
    """Os módulos do pacote são importáveis sem side-effects catastróficos."""

    def test_import_pacote_principal(self) -> None:
        import obr_explorer

        assert hasattr(obr_explorer, "__version__")

    def test_versao_valida(self) -> None:
        import obr_explorer

        # Formato semver simples: X.Y.Z
        partes = obr_explorer.__version__.split(".")
        assert len(partes) == 3
        assert all(p.isdigit() for p in partes), (
            f"Versao malformada: {obr_explorer.__version__}"
        )

    def test_import_config(self) -> None:
        from obr_explorer import config

        assert hasattr(config, "ROOT_DIR")
        assert hasattr(config, "S3_BUCKET_URL")
        assert hasattr(config, "DEFAULT_COUNTRY_ISO")

    def test_import_cli(self) -> None:
        from obr_explorer import cli

        assert callable(cli.main)

    def test_import_modulos_placeholder(self) -> None:
        """Módulos vazios das fases futuras devem pelo menos importar."""
        from obr_explorer import aoi, analysis, duckdb_client, webmap  # noqa: F401


# =============================================================================
# Config
# =============================================================================
class TestConfig:
    def test_root_dir_aponta_para_raiz(self, repo_root: Path) -> None:
        from obr_explorer import config

        assert config.ROOT_DIR.resolve() == repo_root.resolve()

    def test_paths_sao_pathlib_path(self) -> None:
        from obr_explorer import config

        for attr in ("ROOT_DIR", "DATA_DIR", "RAW_DATA_DIR", "AOI_DIR", "WEBMAP_DIR"):
            valor = getattr(config, attr)
            assert isinstance(valor, Path), f"{attr} deve ser Path, e nao {type(valor)}"

    def test_s3_urls_bem_formadas(self) -> None:
        from obr_explorer import config

        assert config.S3_BUCKET_URL.startswith("s3://")
        assert config.S3_GOOGLE_URL.startswith("s3://")

    def test_default_country_iso_com_tres_letras(self) -> None:
        from obr_explorer import config

        assert len(config.DEFAULT_COUNTRY_ISO) == 3
        assert config.DEFAULT_COUNTRY_ISO.isupper()

    def test_fontes_validas(self) -> None:
        from obr_explorer import config

        assert config.SOURCE_GOOGLE in config.FONTES_VALIDAS
        assert config.SOURCE_MICROSOFT in config.FONTES_VALIDAS
        assert len(config.FONTES_VALIDAS) == 2

    def test_resumo_config_retorna_dict(self) -> None:
        from obr_explorer import config

        r = config.resumo_config()
        assert isinstance(r, dict)
        assert "ROOT_DIR" in r
        assert "S3_BUCKET_URL" in r

    def test_ensure_data_dirs_idempotente(self, tmp_path, monkeypatch) -> None:
        """Chamar ensure_data_dirs várias vezes não deve quebrar."""
        from obr_explorer import config

        monkeypatch.setattr(config, "RAW_DATA_DIR", tmp_path / "raw")
        monkeypatch.setattr(config, "PROCESSED_DATA_DIR", tmp_path / "processed")
        monkeypatch.setattr(config, "AOI_DIR", tmp_path / "aois")
        monkeypatch.setattr(config, "WEBMAP_DIR", tmp_path / "webmap")
        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")

        config.ensure_data_dirs()
        config.ensure_data_dirs()  # segunda chamada não deve falhar

        assert (tmp_path / "raw").is_dir()
        assert (tmp_path / "processed").is_dir()
        assert (tmp_path / "webmap").is_dir()

    def test_configure_logging_idempotente(self) -> None:
        """Chamar configure_logging duas vezes não deve duplicar handlers."""
        import logging

        from obr_explorer import config

        # Estado inicial: remover handlers para começar limpo
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

        config.configure_logging()
        n_handlers_apos_primeira = len(root.handlers)

        config.configure_logging()
        n_handlers_apos_segunda = len(root.handlers)

        assert n_handlers_apos_primeira == n_handlers_apos_segunda

    def test_configure_logging_aceita_nivel_customizado(self) -> None:
        import logging

        from obr_explorer import config

        # Remove handlers para forçar reconfiguração
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

        config.configure_logging(level="DEBUG")
        assert root.level == logging.DEBUG


# =============================================================================
# GeoJSONs das AOIs
# =============================================================================
class TestAOIs:
    """As AOIs versionadas são GeoJSON válidos com metadata esperada."""

    def test_cambuquira_estrutura_feature_collection(
        self, geojson_cambuquira: dict
    ) -> None:
        assert geojson_cambuquira["type"] == "FeatureCollection"
        assert len(geojson_cambuquira["features"]) == 1

    def test_uberlandia_estrutura_feature_collection(
        self, geojson_uberlandia: dict
    ) -> None:
        assert geojson_uberlandia["type"] == "FeatureCollection"
        assert len(geojson_uberlandia["features"]) == 1

    @pytest.mark.parametrize(
        "fixture_name,nome_esperado,uf_esperada",
        [
            ("geojson_cambuquira", "Cambuquira", "MG"),
            # Nome IBGE oficial de Uberlandia mantem o acento
            ("geojson_uberlandia", "Uberlândia", "MG"),
        ],
    )
    def test_metadata_essencial_presente(
        self, request, fixture_name: str, nome_esperado: str, uf_esperada: str
    ) -> None:
        gj = request.getfixturevalue(fixture_name)
        props = gj["features"][0]["properties"]
        assert props["nome"] == nome_esperado
        assert props["uf"] == uf_esperada
        assert "tipologia" in props
        assert "populacao_2022" in props
        assert "descricao" in props

    def test_regressao_nao_ha_open_sem_encoding(self, repo_root) -> None:
        """Regressao: todos os <path>.open() em codigo real devem ter encoding=.

        No Windows, o encoding default do Python eh cp1252 (nao UTF-8),
        causando corrupcao de caracteres acentuados ao ler GeoJSONs
        gerados com UTF-8. Este teste usa AST para varrer src/ e tests/
        procurando chamadas <path>.open(...) em modo texto sem argumento
        encoding, e falha se encontrar.

        Modo binario ('rb', 'wb', 'ab') eh permitido sem encoding
        (encoding nao se aplica a bytes).
        """
        import ast

        def extrair_mode_arg(call: ast.Call) -> str | None:
            """Retorna o valor do argumento 'mode' da chamada, se for literal."""
            if call.args:
                primeiro = call.args[0]
                if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
                    return primeiro.value
            for kw in call.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    return kw.value.value if isinstance(kw.value.value, str) else None
            return None

        def tem_encoding_arg(call: ast.Call) -> bool:
            return any(kw.arg == "encoding" for kw in call.keywords)

        suspeitos: list[str] = []
        for diretorio in ("src", "tests"):
            for py_file in (repo_root / diretorio).rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"))
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    # Procura por <algo>.open(...)
                    if not (isinstance(func, ast.Attribute) and func.attr == "open"):
                        continue
                    mode = extrair_mode_arg(node)
                    # Modo binario nao precisa de encoding
                    if mode and "b" in mode:
                        continue
                    if tem_encoding_arg(node):
                        continue
                    suspeitos.append(
                        f"{py_file.relative_to(repo_root)}:{node.lineno}"
                    )

        assert not suspeitos, (
            "Encontrados <path>.open(...) sem encoding= explicito. No Windows "
            "isso quebra com caracteres acentuados em GeoJSONs. Adicione "
            "encoding='utf-8':\n  " + "\n  ".join(suspeitos)
        )

    @pytest.mark.parametrize(
        "fixture_name",
        ["geojson_cambuquira", "geojson_uberlandia"],
    )
    def test_geometria_polygon_valida(self, request, fixture_name: str) -> None:
        gj = request.getfixturevalue(fixture_name)
        geom = gj["features"][0]["geometry"]
        assert geom["type"] == "Polygon"
        # Um polígono simples tem coordinates = [ring], onde ring é lista de [lon, lat]
        assert len(geom["coordinates"]) >= 1
        ring = geom["coordinates"][0]
        # Ring fechado: primeiro ponto == último ponto
        assert ring[0] == ring[-1]
        # Pelo menos 4 pontos (3 únicos + 1 repetido para fechar)
        assert len(ring) >= 4

    @pytest.mark.parametrize(
        "fixture_name",
        ["geojson_cambuquira", "geojson_uberlandia"],
    )
    def test_coordenadas_dentro_do_brasil(self, request, fixture_name: str) -> None:
        """Longitude entre -74 e -34, latitude entre -34 e 5 cobre o Brasil."""
        gj = request.getfixturevalue(fixture_name)
        ring = gj["features"][0]["geometry"]["coordinates"][0]
        for lon, lat in ring:
            assert -74 <= lon <= -34, f"Longitude fora do Brasil: {lon}"
            assert -34 <= lat <= 5, f"Latitude fora do Brasil: {lat}"


# =============================================================================
# CLI
# =============================================================================
class TestCLI:
    def test_help_sai_com_zero(self, capsys) -> None:
        """argparse levanta SystemExit(0) em --help."""
        import pytest as _pytest
        from obr_explorer.cli import main

        with _pytest.raises(SystemExit) as excinfo:
            main(["--help"])
        assert excinfo.value.code == 0

    def test_version_imprime_versao(self, capsys) -> None:
        """argparse levanta SystemExit(0) em --version e imprime versao."""
        import pytest as _pytest
        from obr_explorer import __version__
        from obr_explorer.cli import main

        with _pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert __version__ in out

    def test_info_imprime_configuracao(self, capsys) -> None:
        from obr_explorer.cli import main

        assert main(["info"]) == 0
        out = capsys.readouterr().out
        assert "ROOT_DIR" in out
        assert "S3_BUCKET_URL" in out

    def test_subcomando_desconhecido_retorna_erro(self, capsys) -> None:
        """argparse retorna codigo 2 para subcomando desconhecido."""
        import pytest as _pytest
        from obr_explorer.cli import main

        with _pytest.raises(SystemExit):
            main(["comando_inexistente"])

    def test_analyze_sem_aoi_faz_argparse_reclamar(self, capsys) -> None:
        """Sem --aoi obrigatorio, argparse aborta com SystemExit."""
        import pytest as _pytest
        from obr_explorer.cli import main

        with _pytest.raises(SystemExit):
            main(["analyze"])
