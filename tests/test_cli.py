"""Testes da CLI expandida.

Foco em: parser aceita todos os subcomandos, handlers offline (que
nao precisam de S3) funcionam ponta a ponta, codigos de saida
distintos para tipos de erro.
"""

from __future__ import annotations

import pytest

from obr_explorer import cli


# =============================================================================
# Parser
# =============================================================================
class TestParser:
    def test_help_sem_argumentos_retorna_zero(self, capsys) -> None:
        # main sem args exibe help e retorna 0
        assert cli.main([]) == 0

    def test_version_flag(self, capsys) -> None:
        import pytest as _pytest

        with _pytest.raises(SystemExit) as excinfo:
            cli.main(["--version"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "obr-explorer" in out

    def test_info(self, capsys) -> None:
        assert cli.main(["info"]) == 0
        out = capsys.readouterr().out
        assert "ROOT_DIR" in out
        assert "S3_BUCKET_URL" in out


# =============================================================================
# Subcomando: aoi
# =============================================================================
class TestAoiSubcomandos:
    def test_aoi_list(self, capsys) -> None:
        assert cli.main(["aoi", "list"]) == 0
        out = capsys.readouterr().out
        assert "cambuquira_mg" in out or "AOIs" in out

    def test_aoi_info_cambuquira(self, capsys) -> None:
        assert cli.main(["aoi", "info", "--aoi", "cambuquira_mg"]) == 0
        out = capsys.readouterr().out
        assert "Cambuquira" in out

    def test_aoi_info_aoi_inexistente_retorna_3(self, capsys) -> None:
        """Codigo 3 = arquivo/AOI nao encontrado."""
        assert cli.main(["aoi", "info", "--aoi", "aoi_ficticia"]) == 3

    def test_aoi_fetch_sem_argumentos_argparse_reclama(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["aoi", "fetch"])

    def test_aoi_fetch_codigo_invalido_retorna_1(self, capsys) -> None:
        """Codigo IBGE malformado retorna 1 (ValueError)."""
        rc = cli.main(["aoi", "fetch", "--codigo", "abc", "--nome", "teste"])
        assert rc == 1

    def test_aoi_fetch_qualidade_invalida_argparse_reclama(self) -> None:
        with pytest.raises(SystemExit):
            cli.main([
                "aoi", "fetch",
                "--codigo", "3111606",
                "--nome", "teste",
                "--qualidade", "super",
            ])


# =============================================================================
# Subcomando: analyze / export
# =============================================================================
class TestAnalyzeExport:
    def test_analyze_sem_aoi_argparse_reclama(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["analyze"])

    def test_analyze_aoi_inexistente_retorna_3(self, capsys) -> None:
        rc = cli.main(["analyze", "--aoi", "aoi_ficticia"])
        assert rc == 3

    def test_export_aoi_inexistente_retorna_3(self, capsys) -> None:
        rc = cli.main(["export", "--aoi", "aoi_ficticia"])
        assert rc == 3

    def test_analyze_formato_invalido_argparse_reclama(self) -> None:
        with pytest.raises(SystemExit):
            cli.main([
                "analyze", "--aoi", "cambuquira_mg",
                "--format", "yaml",  # invalido
            ])


# =============================================================================
# Codigos de saida
# =============================================================================
class TestCodigosDeSaida:
    def test_valueerror_retorna_1(self, capsys) -> None:
        """Codigo IBGE invalido no aoi fetch -> ValueError -> 1."""
        rc = cli.main(["aoi", "fetch", "--codigo", "invalido", "--nome", "x"])
        assert rc == 1

    def test_file_not_found_retorna_3(self, capsys) -> None:
        rc = cli.main(["aoi", "info", "--aoi", "nao_existe"])
        assert rc == 3
