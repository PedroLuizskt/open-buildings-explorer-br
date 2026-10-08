"""Testes do módulo duckdb_client.

Testes offline usam um mini-dataset Parquet sintético gerado pela
fixture ``mini_dataset_parquet``, permitindo exercitar todo o
pipeline (carga → recorte espacial → export) sem depender do S3
real. Testes que requerem acesso ao bucket público VIDA são
marcados com ``@pytest.mark.network`` e usam Lesoto (LSO) como AOI
de teste rápido — país pequeno com ~1M edifícios, executa em
poucos segundos.

Nota sobre extensões DuckDB: a extensão ``spatial`` precisa ser
baixada do CDN oficial do DuckDB na primeira execução. A fixture
``duckdb_conn`` faz esse download de forma silenciosa e pula os
testes com pytest.skip se o ambiente bloquear o CDN. Testes que
explicitamente exercitam a instalação de extensões são marcados
como ``network`` porque dependem de acesso HTTP.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from obr_explorer import config
from obr_explorer import duckdb_client as ddb


# =============================================================================
# Validadores
# =============================================================================
class TestValidarIdentificador:
    """A validação de identificadores SQL protege contra injection."""

    @pytest.mark.parametrize(
        "nome",
        ["tabela", "minha_tabela", "T1", "_privado", "obr_recorte_2026"],
    )
    def test_identificadores_validos_passam(self, nome: str) -> None:
        assert ddb._validar_identificador(nome) == nome

    @pytest.mark.parametrize(
        "nome",
        [
            "",
            "1tabela",  # começa com dígito
            "com espaco",
            "tabela;DROP TABLE users",  # tentativa de injection
            "tabela--comment",
            "tabela'quote",
            "tabela.esquema",  # ponto não permitido
            "tabela-hifen",
        ],
    )
    def test_identificadores_invalidos_levantam_erro(self, nome: str) -> None:
        with pytest.raises(ValueError, match="invalido"):
            ddb._validar_identificador(nome)


class TestValidarIsoCodes:
    @pytest.mark.parametrize("iso", ["BRA", "LSO", "AUS", "USA"])
    def test_iso3_validos(self, iso: str) -> None:
        assert ddb._validar_iso3(iso) == iso

    @pytest.mark.parametrize("iso", ["br", "BR", "BRAS", "12A", ""])
    def test_iso3_invalidos_levantam_erro(self, iso: str) -> None:
        with pytest.raises(ValueError, match="ISO-3 invalido"):
            ddb._validar_iso3(iso)

    @pytest.mark.parametrize("iso", ["BR", "LS", "AU", "US"])
    def test_iso2_validos(self, iso: str) -> None:
        assert ddb._validar_iso2(iso) == iso

    @pytest.mark.parametrize("iso", ["br", "BRA", "1B", ""])
    def test_iso2_invalidos_levantam_erro(self, iso: str) -> None:
        with pytest.raises(ValueError, match="ISO-2 invalido"):
            ddb._validar_iso2(iso)


# =============================================================================
# Conexão
# =============================================================================
class TestConexao:
    def test_criar_conexao_in_memory_default(self) -> None:
        con = ddb.criar_conexao()
        assert isinstance(con, duckdb.DuckDBPyConnection)
        # Deve responder a queries simples
        assert con.execute("SELECT 1").fetchone()[0] == 1
        con.close()

    def test_criar_conexao_persistente_requer_path(self) -> None:
        with pytest.raises(ValueError, match="database_path"):
            ddb.criar_conexao(in_memory=False)

    def test_criar_conexao_persistente_em_arquivo(self, tmp_path: Path) -> None:
        db_path = tmp_path / "teste.duckdb"
        con = ddb.criar_conexao(in_memory=False, database_path=db_path)
        con.execute("CREATE TABLE t AS SELECT 1 AS x;")
        con.close()
        # Arquivo deve existir em disco
        assert db_path.exists()

        # Reconectar e ler
        con2 = ddb.criar_conexao(in_memory=False, database_path=db_path)
        assert con2.execute("SELECT x FROM t").fetchone()[0] == 1
        con2.close()


# =============================================================================
# Extensões — instalação precisa de rede (CDN oficial DuckDB)
# =============================================================================
class TestExtensoes:
    @pytest.mark.network
    def test_instalar_extensoes_carrega_spatial(self) -> None:
        """Instalar spatial baixa do CDN oficial; marcado como network."""
        con = ddb.criar_conexao()
        ddb.instalar_extensoes(con, extensoes=("spatial",))
        carregadas = ddb.extensoes_carregadas(con)
        assert "spatial" in carregadas
        con.close()

    @pytest.mark.network
    def test_instalar_extensoes_idempotente(self) -> None:
        """Chamar instalar múltiplas vezes não deve falhar."""
        con = ddb.criar_conexao()
        ddb.instalar_extensoes(con, extensoes=("spatial",))
        ddb.instalar_extensoes(con, extensoes=("spatial",))
        assert "spatial" in ddb.extensoes_carregadas(con)
        con.close()

    def test_instalar_extensao_inexistente_vira_runtime_error(self) -> None:
        """Nome de extensão inválido deve virar RuntimeError com mensagem clara.

        Este teste não requer rede — DuckDB rejeita nomes desconhecidos
        antes de tentar baixar do CDN.
        """
        con = ddb.criar_conexao()
        with pytest.raises(RuntimeError, match="Falha ao instalar"):
            ddb.instalar_extensoes(con, extensoes=("extensao_que_nao_existe_xyz",))
        con.close()

    def test_configurar_s3_nao_levanta(self, duckdb_conn) -> None:
        """Configurar S3 é operação idempotente e não requer rede em si."""
        ddb.configurar_s3(duckdb_conn)
        r = duckdb_conn.execute("SELECT current_setting('s3_region')").fetchone()
        assert r[0] == config.S3_REGION

    def test_configurar_s3_seta_ca_cert_file_via_certifi(self, duckdb_conn) -> None:
        """Regressao: no Windows sem CA bundle configurado, requests S3
        falham com SSL error. configurar_s3 deve automaticamente detectar
        certifi e setar ca_cert_file no DuckDB.
        """
        import certifi

        ddb.configurar_s3(duckdb_conn)
        r = duckdb_conn.execute("SELECT current_setting('ca_cert_file')").fetchone()
        # DuckDB retorna path com forward slashes; normalizamos para comparar
        ca_configurado = r[0].replace("\\", "/")
        ca_esperado = certifi.where().replace("\\", "/")
        assert ca_configurado == ca_esperado

    def test_configurar_s3_aceita_ca_cert_file_customizado(
        self, duckdb_conn, tmp_path
    ) -> None:
        """Chamador pode passar path customizado (ex: bundle corporativo)."""
        custom_ca = tmp_path / "meu_bundle.pem"
        custom_ca.write_text("# fake bundle for test")
        ddb.configurar_s3(duckdb_conn, ca_cert_file=custom_ca)

        r = duckdb_conn.execute("SELECT current_setting('ca_cert_file')").fetchone()
        assert r[0].replace("\\", "/") == str(custom_ca).replace("\\", "/")

    def test_configurar_s3_usa_path_style_por_default(self, duckdb_conn) -> None:
        """Regressao: bucket VIDA contem pontos no nome, o que quebra
        virtual-hosted-style URLs sob HTTPS (SSL wildcard nao cobre
        multiplos niveis de subdominio). Path-style resolve isso.
        """
        ddb.configurar_s3(duckdb_conn)
        r = duckdb_conn.execute("SELECT current_setting('s3_url_style')").fetchone()
        assert r[0] == "path"

    def test_configurar_s3_aceita_vhost_explicito(self, duckdb_conn) -> None:
        """Chamador pode forcar virtual-hosted-style se souber o que faz."""
        ddb.configurar_s3(duckdb_conn, s3_url_style="vhost")
        r = duckdb_conn.execute("SELECT current_setting('s3_url_style')").fetchone()
        assert r[0] == "vhost"

    def test_configurar_s3_rejeita_url_style_invalido(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="s3_url_style"):
            ddb.configurar_s3(duckdb_conn, s3_url_style="virtual-hosted")


# =============================================================================
# Carregamento — testes offline com Parquet sintético
# =============================================================================
class TestCarregarPais:
    def test_valida_iso_antes_de_query(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="ISO-3 invalido"):
            ddb.carregar_pais(duckdb_conn, country_iso="brasil", tabela="t")

    def test_valida_tabela_antes_de_query(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="tabela"):
            ddb.carregar_pais(duckdb_conn, country_iso="BRA", tabela="1invalid")

    def test_valida_particionamento(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="Particionamento"):
            ddb.carregar_pais(
                duckdb_conn, country_iso="BRA", tabela="t", particionamento="by_region"
            )

    def test_carrega_de_bucket_local_simulado(
        self, duckdb_conn, mini_dataset_parquet, tmp_path
    ) -> None:
        """Simula um bucket local reorganizando o Parquet sintético
        no layout esperado (by_country_s2/country_iso=XXX/*.parquet)."""
        bucket = tmp_path / "bucket"
        partition_dir = bucket / "by_country_s2" / "country_iso=BRA"
        partition_dir.mkdir(parents=True)
        destino = partition_dir / "part-0.parquet"
        destino.write_bytes(mini_dataset_parquet.read_bytes())

        n = ddb.carregar_pais(
            duckdb_conn,
            country_iso="BRA",
            tabela="footprints_teste",
            bucket_url=str(bucket).replace("\\", "/"),
        )
        assert n == 20

        cols = [c["column_name"] for c in ddb.descrever_tabela(duckdb_conn, "footprints_teste")]
        assert "geometry" in cols
        assert "bf_source" in cols


class TestCarregarPaisGoogleOriginal:
    def test_valida_iso2(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="ISO-2 invalido"):
            ddb.carregar_pais_google_original(
                duckdb_conn, country_iso_2="BRA", tabela="t"
            )

    def test_valida_tabela(self, duckdb_conn) -> None:
        with pytest.raises(ValueError, match="tabela"):
            ddb.carregar_pais_google_original(
                duckdb_conn, country_iso_2="BR", tabela="1invalid"
            )


# =============================================================================
# AOI: carregamento de GeoJSON
# =============================================================================
class TestCarregarAOIGeoJSON:
    def test_carrega_cambuquira(
        self, duckdb_conn, path_geojson_cambuquira
    ) -> None:
        n = ddb.carregar_aoi_geojson(
            duckdb_conn, path_geojson_cambuquira, "aoi_cambuquira"
        )
        assert n == 1

        tabelas = ddb.listar_tabelas(duckdb_conn)
        assert "aoi_cambuquira" in tabelas
        cols = [c["column_name"] for c in ddb.descrever_tabela(duckdb_conn, "aoi_cambuquira")]
        assert "geom" in cols

    def test_arquivo_inexistente_levanta_erro(self, duckdb_conn, tmp_path) -> None:
        with pytest.raises(FileNotFoundError, match="nao encontrado"):
            ddb.carregar_aoi_geojson(
                duckdb_conn, tmp_path / "nao_existe.geojson", "aoi"
            )

    def test_valida_nome_tabela(self, duckdb_conn, path_geojson_cambuquira) -> None:
        with pytest.raises(ValueError, match="tabela"):
            ddb.carregar_aoi_geojson(duckdb_conn, path_geojson_cambuquira, "1invalid")


# =============================================================================
# Recorte espacial
# =============================================================================
class TestRecortarPorAOI:
    def test_recorta_intersecao_esperada(
        self,
        duckdb_conn,
        mini_dataset_parquet,
        path_geojson_cambuquira,
    ) -> None:
        """Mini-dataset está DENTRO da AOI Cambuquira, então recorte
        deve preservar todos os 20 footprints."""
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"""
            CREATE TABLE footprints AS
              SELECT * FROM '{caminho}'
        """)

        ddb.carregar_aoi_geojson(duckdb_conn, path_geojson_cambuquira, "aoi")

        n = ddb.recortar_por_aoi(
            duckdb_conn,
            tabela_footprints="footprints",
            tabela_aoi="aoi",
            tabela_recorte="recorte",
        )
        # Todos os 20 footprints devem estar dentro (bbox foi projetada assim)
        assert n == 20

        # Tabela de recorte tem geom + bf_source (preservada por default)
        cols = [c["column_name"] for c in ddb.descrever_tabela(duckdb_conn, "recorte")]
        assert "geom" in cols
        assert "bf_source" in cols

    def test_recorta_com_aoi_pequena_reduz_contagem(
        self,
        duckdb_conn,
        mini_dataset_parquet,
        tmp_path,
    ) -> None:
        """AOI minúscula que só cobre parte dos footprints reduz a contagem."""
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"CREATE TABLE footprints AS SELECT * FROM '{caminho}'")

        # AOI cobre apenas a metade sul do grid sintético
        aoi_geojson = tmp_path / "aoi_pequena.geojson"
        aoi_geojson.write_text('''
        {
          "type": "FeatureCollection",
          "features": [{
            "type": "Feature",
            "properties": {"nome": "pequena"},
            "geometry": {
              "type": "Polygon",
              "coordinates": [[
                [-45.34, -21.88],
                [-45.32, -21.88],
                [-45.32, -21.877],
                [-45.34, -21.877],
                [-45.34, -21.88]
              ]]
            }
          }]
        }
        ''')

        ddb.carregar_aoi_geojson(duckdb_conn, aoi_geojson, "aoi_p")
        n = ddb.recortar_por_aoi(
            duckdb_conn,
            tabela_footprints="footprints",
            tabela_aoi="aoi_p",
            tabela_recorte="recorte_p",
        )
        # Deve ser menor que 20 (recorte reduz a contagem)
        assert 0 < n < 20

    def test_valida_todos_os_nomes(self, duckdb_conn) -> None:
        """Todos os identificadores devem ser validados."""
        with pytest.raises(ValueError):
            ddb.recortar_por_aoi(
                duckdb_conn, "1invalid", "aoi", "recorte"
            )
        with pytest.raises(ValueError):
            ddb.recortar_por_aoi(
                duckdb_conn, "fp", "1invalid", "recorte"
            )
        with pytest.raises(ValueError):
            ddb.recortar_por_aoi(
                duckdb_conn, "fp", "aoi", "1invalid"
            )

    def test_valida_crs_alvo(self, duckdb_conn) -> None:
        """CRS invalido deve ser rejeitado antes de qualquer query."""
        with pytest.raises(ValueError, match="crs_alvo"):
            ddb.recortar_por_aoi(
                duckdb_conn, "fp", "aoi", "recorte", crs_alvo="'; DROP TABLE"
            )

    def test_normaliza_crs_entre_epsg4326_e_ogccrs84(
        self,
        duckdb_conn,
        mini_dataset_parquet,
        path_geojson_cambuquira,
    ) -> None:
        """Regressao: o bug original ocorria porque ST_GeomFromText produz
        geometrias com CRS EPSG:4326 e ST_Read do GeoJSON produz OGC:CRS84.
        Versoes recentes da extensao spatial rejeitam a operacao. A funcao
        deve normalizar ambas via ST_SetCRS antes do ST_Intersects.

        Este teste reproduz o cenario exato: mini_dataset via ST_GeomFromText
        + AOI via ST_Read + recorte. Sem a normalizacao, quebra com
        BinderException; com a normalizacao, funciona.
        """
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"CREATE TABLE fps AS SELECT * FROM '{caminho}'")
        ddb.carregar_aoi_geojson(duckdb_conn, path_geojson_cambuquira, "aoi_norm")

        # Nao deve levantar BinderException nem qualquer outro erro
        n = ddb.recortar_por_aoi(
            duckdb_conn,
            tabela_footprints="fps",
            tabela_aoi="aoi_norm",
            tabela_recorte="rec_norm",
        )
        assert n == 20


# =============================================================================
# Exportação
# =============================================================================
class TestExport:
    def test_exportar_geojson(
        self, duckdb_conn, mini_dataset_parquet, tmp_path
    ) -> None:
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"CREATE TABLE t AS SELECT * FROM '{caminho}'")

        output = tmp_path / "saida.geojson"
        path_final = ddb.exportar_geojson(duckdb_conn, "t", output)

        assert path_final.exists()
        assert path_final.stat().st_size > 0

        import json

        with path_final.open(encoding="utf-8") as f:
            gj = json.load(f)
        assert gj["type"] == "FeatureCollection"
        assert len(gj["features"]) == 20

    def test_exportar_flatgeobuf(
        self, duckdb_conn, mini_dataset_parquet, tmp_path
    ) -> None:
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"CREATE TABLE t AS SELECT * FROM '{caminho}'")

        output = tmp_path / "saida.fgb"
        path_final = ddb.exportar_flatgeobuf(duckdb_conn, "t", output)

        assert path_final.exists()
        # FlatGeobuf tem magic bytes 'fgb' no inicio
        assert path_final.read_bytes()[:3] == b"fgb"

    def test_export_com_subconjunto_de_colunas(
        self, duckdb_conn, mini_dataset_parquet, tmp_path
    ) -> None:
        caminho = str(mini_dataset_parquet).replace("\\", "/")
        duckdb_conn.execute(f"CREATE TABLE t AS SELECT * FROM '{caminho}'")

        output = tmp_path / "saida_reduzida.geojson"
        ddb.exportar_geojson(
            duckdb_conn, "t", output,
            colunas=("geometry", "bf_source"),  # sem area/confidence
        )

        import json

        with output.open(encoding="utf-8") as f:
            gj = json.load(f)
        # Cada feature deve ter apenas bf_source em properties
        props = gj["features"][0]["properties"]
        assert "bf_source" in props
        assert "area_in_meters" not in props


# =============================================================================
# Helpers de introspecção
# =============================================================================
class TestIntrospeccao:
    def test_contar_registros(self, duckdb_conn) -> None:
        duckdb_conn.execute("CREATE TABLE t AS SELECT 1 AS x UNION ALL SELECT 2;")
        assert ddb.contar_registros(duckdb_conn, "t") == 2

    def test_listar_tabelas(self, duckdb_conn) -> None:
        duckdb_conn.execute("CREATE TABLE a AS SELECT 1;")
        duckdb_conn.execute("CREATE TABLE b AS SELECT 2;")
        tabelas = ddb.listar_tabelas(duckdb_conn)
        assert "a" in tabelas
        assert "b" in tabelas

    def test_descrever_tabela(self, duckdb_conn) -> None:
        duckdb_conn.execute("CREATE TABLE t (id INTEGER, nome VARCHAR);")
        desc = ddb.descrever_tabela(duckdb_conn, "t")
        colunas = {d["column_name"] for d in desc}
        assert colunas == {"id", "nome"}

    def test_extensoes_carregadas_inclui_spatial(self, duckdb_conn) -> None:
        # duckdb_conn fixture ja carrega spatial
        assert "spatial" in ddb.extensoes_carregadas(duckdb_conn)


# =============================================================================
# Testes de rede — S3 real, Lesoto como AOI rápida
# =============================================================================
class TestNetworkS3:
    """Testes que atingem o bucket S3 público VIDA.

    Excluídos por default (marker network). Rodar com:
        pytest -m network
    """

    @pytest.mark.network
    def test_fixture_completa_tem_path_style_aplicado(
        self, duckdb_conn_completa
    ) -> None:
        """Sanidade: garante que a fixture duckdb_conn_completa aplicou
        path-style URL via configurar_s3(). Se este teste falhar, a fixture
        regrediu para setar SQL cru e ignorar o path-style — os testes de
        carga real vao falhar com SSL error de novo.
        """
        r = duckdb_conn_completa.execute(
            "SELECT current_setting('s3_url_style')"
        ).fetchone()
        assert r[0] == "path", (
            f"Fixture nao aplicou path-style. Valor atual: {r[0]!r}. "
            "Verifique que duckdb_conn_completa em conftest.py chama "
            "ddb.configurar_s3(con)."
        )

    @pytest.mark.network
    def test_contar_lesoto_via_s3(self, duckdb_conn_completa) -> None:
        """Lesoto tem ~1M edifícios, carga leva alguns segundos."""
        n = ddb.carregar_pais(
            duckdb_conn_completa,
            country_iso="LSO",
            tabela="footprints_lso",
        )
        # Lesoto tem entre 500k e 3M edificações no dataset mesclado
        assert 500_000 < n < 3_000_000

    @pytest.mark.network
    def test_lesoto_tem_google_como_fonte(self, duckdb_conn_completa) -> None:
        """Confirma que a coluna bf_source existe e tem valor 'google'."""
        ddb.carregar_pais(
            duckdb_conn_completa,
            country_iso="LSO",
            tabela="footprints_lso",
        )
        r = duckdb_conn_completa.execute(
            "SELECT DISTINCT bf_source FROM footprints_lso ORDER BY 1"
        ).fetchall()
        fontes = {linha[0] for linha in r}
        # Google e sempre a mais comum; Microsoft pode ou nao estar em paises pequenos
        assert "google" in fontes
