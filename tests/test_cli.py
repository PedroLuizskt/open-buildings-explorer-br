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

    def test_webmap_aoi_inexistente_retorna_3(self, capsys) -> None:
        rc = cli.main(["webmap", "--aoi", "aoi_ficticia"])
        assert rc == 3

    def test_webmap_sem_aoi_usa_todas_disponiveis(self) -> None:
        """Sem --aoi, webmap usa todas as AOIs em data/external/aois/.

        Nao chamamos cli.main aqui porque o fluxo baixa dados do S3.
        Apenas verifica que o parser aceita omissao de --aoi.
        """
        parser = cli._build_parser()
        args = parser.parse_args(["webmap"])
        # Com action='append' + default=None, args.aoi fica None
        assert args.aoi is None

    def test_webmap_min_area_negativo_retorna_erro(self, capsys, tmp_path) -> None:
        """min-area-m2 negativo levanta ValueError na funcao -> codigo != 0."""
        rc = cli.main([
            "webmap", "--aoi", "cambuquira_mg",
            "--pular-carga", "--db-path", str(tmp_path / "nao_existe.duckdb"),
            "--min-area-m2", "-5",
        ])
        # Pode retornar 1 (ValueError), 3 (tabela nao existe) ou 4 (duckdb)
        # dependendo da ordem de validacao. O importante eh nao ser 0.
        assert rc != 0

    def test_webmap_multiplos_aoi_action_append(self) -> None:
        """--aoi pode ser repetido para incluir multiplas AOIs."""
        parser = cli._build_parser()
        args = parser.parse_args([
            "webmap",
            "--aoi", "cambuquira_mg",
            "--aoi", "uberlandia_mg",
        ])
        assert args.aoi == ["cambuquira_mg", "uberlandia_mg"]


# =============================================================================
# Subcomandos db-info e db-prune
# =============================================================================
class TestDbInfo:
    def test_db_info_sem_arquivo_retorna_3(self, capsys, tmp_path) -> None:
        rc = cli.main(["db-info", "--db-path", str(tmp_path / "nao_existe.duckdb")])
        assert rc == 3

    def test_db_info_banco_vazio_retorna_0(self, tmp_path, capsys) -> None:
        import duckdb

        db_path = tmp_path / "vazio.duckdb"
        con = duckdb.connect(str(db_path))
        con.close()
        rc = cli.main(["db-info", "--db-path", str(db_path)])
        assert rc == 0

    def test_db_info_mostra_tabelas(self, tmp_path, capsys) -> None:
        import duckdb

        db_path = tmp_path / "com_dados.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE recorte_cambuquira_mg AS SELECT 1 AS x;")
        con.execute("CREATE TABLE footprints_bra AS SELECT 2 AS x UNION ALL SELECT 3;")
        con.close()

        rc = cli.main(["db-info", "--db-path", str(db_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "recorte_cambuquira_mg" in out
        assert "footprints_bra" in out


class TestDbPrune:
    def test_db_prune_sem_sim_apenas_lista(self, tmp_path, capsys) -> None:
        import duckdb

        db_path = tmp_path / "db.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE footprints_bra AS SELECT 1 AS x;")
        con.execute("CREATE TABLE recorte_x AS SELECT 1 AS x;")
        con.close()

        rc = cli.main(["db-prune", "--db-path", str(db_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "footprints_bra" in out
        assert "--sim" in out

        # Confirma que a tabela ainda existe (nao foi removida)
        con = duckdb.connect(str(db_path))
        tabelas = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        con.close()
        assert "footprints_bra" in tabelas

    def test_db_prune_com_sim_remove(self, tmp_path, capsys) -> None:
        import duckdb

        db_path = tmp_path / "db.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE footprints_bra AS SELECT 1 AS x;")
        con.execute("CREATE TABLE recorte_cambuquira_mg AS SELECT 1 AS x;")
        con.close()

        rc = cli.main(["db-prune", "--db-path", str(db_path), "--sim"])
        assert rc == 0

        # Confirma que footprints_bra foi removida mas recorte_... foi mantida
        con = duckdb.connect(str(db_path))
        tabelas = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        con.close()
        assert "footprints_bra" not in tabelas
        assert "recorte_cambuquira_mg" in tabelas

    def test_db_prune_sem_tabelas_pesadas(self, tmp_path, capsys) -> None:
        import duckdb

        db_path = tmp_path / "db.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE recorte_x AS SELECT 1 AS x;")
        con.close()

        rc = cli.main(["db-prune", "--db-path", str(db_path), "--sim"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Nenhuma" in out

    def test_db_prune_sem_arquivo_retorna_3(self, tmp_path, capsys) -> None:
        rc = cli.main(["db-prune", "--db-path", str(tmp_path / "nao_existe.duckdb")])
        assert rc == 3


class TestDbCompact:
    def test_db_compact_sem_arquivo_retorna_3(self, tmp_path, capsys) -> None:
        rc = cli.main(["db-compact", "--db-path", str(tmp_path / "nao_existe.duckdb")])
        assert rc == 3

    def test_db_compact_banco_vazio_retorna_0(self, tmp_path, capsys) -> None:
        import duckdb
        db_path = tmp_path / "vazio.duckdb"
        con = duckdb.connect(str(db_path))
        con.close()
        rc = cli.main(["db-compact", "--db-path", str(db_path)])
        assert rc == 0

    def test_db_compact_sem_sim_apenas_mostra_estimativa(
        self, tmp_path, capsys
    ) -> None:
        """Dry-run: lista tabelas e nao modifica nada."""
        import duckdb
        db_path = tmp_path / "db.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE recorte_cambuquira_mg AS SELECT 1 AS x;")
        con.close()

        size_antes = db_path.stat().st_size
        rc = cli.main(["db-compact", "--db-path", str(db_path)])
        assert rc == 0
        assert db_path.stat().st_size == size_antes
        out = capsys.readouterr().out
        assert "--sim" in out
        assert "recorte_cambuquira_mg" in out

    def test_db_compact_com_sim_cria_backup_e_recria(
        self, tmp_path, capsys
    ) -> None:
        """Compactacao de verdade: cria .bak e substitui original."""
        import duckdb
        db_path = tmp_path / "db.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute("CREATE TABLE recorte_x AS SELECT 1 AS v;")
        con.execute("CREATE TABLE recorte_y AS SELECT 2 AS v;")
        con.close()

        rc = cli.main(["db-compact", "--db-path", str(db_path), "--sim"])
        assert rc == 0

        # Original existe, backup foi criado
        assert db_path.exists()
        backup = db_path.with_suffix(db_path.suffix + ".bak")
        assert backup.exists()

        # Novo banco preserva as tabelas
        con2 = duckdb.connect(str(db_path))
        tabelas = {r[0] for r in con2.execute("SHOW TABLES").fetchall()}
        con2.close()
        assert tabelas == {"recorte_x", "recorte_y"}


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
