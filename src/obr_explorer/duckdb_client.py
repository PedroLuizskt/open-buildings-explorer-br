"""Cliente DuckDB — conexão, extensões e queries base parametrizadas.

Este módulo é a camada de acesso ao dataset Google-Microsoft Open
Buildings. Encapsula toda a mecânica de conversar com o DuckDB:
criação de conexão, instalação de extensões, materialização de dados
em tabelas via ``parquet_scan`` sobre o bucket S3 público, e recorte
espacial via ``ST_Intersection``.

Não contém lógica de negócio (contagens, comparações, agregações
analíticas) — esses ficam em :mod:`obr_explorer.analysis`. A separação
segue o princípio de responsabilidade única: aqui é infraestrutura,
lá é interpretação.

Fluxo típico
------------

Uso programático mínimo::

    from obr_explorer import duckdb_client as ddb

    con = ddb.criar_conexao()
    ddb.instalar_extensoes(con)
    ddb.configurar_s3(con)

    ddb.carregar_pais(con, country_iso="BRA", tabela="footprints_brasil")
    ddb.carregar_aoi_geojson(
        con,
        geojson_path="data/external/aois/cambuquira_mg.geojson",
        tabela="aoi_cambuquira",
    )
    ddb.recortar_por_aoi(
        con,
        tabela_footprints="footprints_brasil",
        tabela_aoi="aoi_cambuquira",
        tabela_recorte="footprints_cambuquira",
    )
    n = ddb.contar_registros(con, "footprints_cambuquira")
    print(f"Edificacoes em Cambuquira: {n}")

Convenções técnicas
-------------------

- Conexões são retornadas para o chamador gerenciar (suporta uso
  como context manager, mas não impõe)
- Nomes de tabela são validados para prevenir SQL injection —
  aceita apenas ``[A-Za-z_][A-Za-z0-9_]*``
- Valores literais (paths, códigos ISO) usam prepared statements
  quando possível; nomes de identificadores SQL são interpolados
  após validação
- Logs em nível INFO informam início e fim de cada operação com
  timing; nível DEBUG detalha o SQL executado
- Erros de rede sobem como :class:`RuntimeError` com mensagem clara

Sobre os códigos ISO
--------------------

O dataset VIDA mesclado usa códigos ISO-3 (``BRA``, ``LSO``,
``AUS``). O dataset original do Google usa códigos ISO-2 (``BR``,
``LS``, ``AU``) — diferença herdada dos schemas originais. As
funções que operam sobre cada bucket documentam qual convenção
esperam.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import duckdb

from obr_explorer import config

logger = logging.getLogger(__name__)


# =============================================================================
# Constantes e validação
# =============================================================================
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
"""Regex que aceita identificadores SQL válidos (nomes de tabela)."""

_ISO_3_VALIDO = re.compile(r"^[A-Z]{3}$")
"""Regex que aceita códigos ISO-3 em maiúsculas."""

_ISO_2_VALIDO = re.compile(r"^[A-Z]{2}$")
"""Regex que aceita códigos ISO-2 em maiúsculas."""

EXTENSOES_REQUERIDAS = ("httpfs", "spatial")
"""Extensões DuckDB necessárias para este projeto."""


def _validar_identificador(nome: str, contexto: str = "identificador") -> str:
    """Valida que um nome é identificador SQL seguro.

    Aceita apenas ``[A-Za-z_][A-Za-z0-9_]*`` — bloqueia caracteres
    especiais que permitiriam SQL injection via interpolação de
    string. É a proteção mínima necessária porque DuckDB não
    parametriza nomes de identificadores.

    Parameters
    ----------
    nome : str
        Nome a validar.
    contexto : str
        Descrição do que este nome representa, para mensagens de
        erro claras (ex: "nome de tabela", "coluna alvo").

    Returns
    -------
    str
        O próprio ``nome`` se válido.

    Raises
    ------
    ValueError
        Se ``nome`` não bate com o padrão esperado.
    """
    if not _IDENTIFICADOR_VALIDO.match(nome):
        raise ValueError(
            f"{contexto} invalido: {nome!r}. "
            "Aceita apenas letras, digitos e underscore, comecando com letra ou underscore."
        )
    return nome


def _validar_iso3(iso: str) -> str:
    """Valida código ISO-3 (três letras maiúsculas)."""
    if not _ISO_3_VALIDO.match(iso):
        raise ValueError(
            f"Codigo ISO-3 invalido: {iso!r}. Esperado tres letras maiusculas (ex: BRA, LSO, AUS)."
        )
    return iso


def _validar_iso2(iso: str) -> str:
    """Valida código ISO-2 (duas letras maiúsculas)."""
    if not _ISO_2_VALIDO.match(iso):
        raise ValueError(
            f"Codigo ISO-2 invalido: {iso!r}. Esperado duas letras maiusculas (ex: BR, LS, AU)."
        )
    return iso


# =============================================================================
# Conexão e extensões
# =============================================================================
def criar_conexao(
    in_memory: bool = True,
    database_path: str | Path | None = None,
) -> duckdb.DuckDBPyConnection:
    """Cria uma conexão DuckDB.

    Por default cria conexão in-memory (``:memory:``) — apropriada
    para análises exploratórias e sessões de trabalho. Passe
    ``in_memory=False`` e ``database_path`` para persistir em disco.

    Parameters
    ----------
    in_memory : bool, default=True
        Se ``True``, ignora ``database_path`` e cria in-memory.
    database_path : str or Path, optional
        Caminho para o arquivo ``.duckdb``. Obrigatório se
        ``in_memory=False``. O arquivo é criado se não existir.

    Returns
    -------
    duckdb.DuckDBPyConnection
        Conexão pronta para uso. **Ainda não tem extensões
        carregadas** — chame :func:`instalar_extensoes` em seguida.
    """
    if in_memory:
        alvo = ":memory:"
    else:
        if database_path is None:
            raise ValueError(
                "database_path eh obrigatorio quando in_memory=False."
            )
        alvo = str(database_path)

    logger.info("[CONEXAO] Criando conexao DuckDB em %s", alvo)
    return duckdb.connect(database=alvo)


def instalar_extensoes(
    con: duckdb.DuckDBPyConnection,
    extensoes: tuple[str, ...] = EXTENSOES_REQUERIDAS,
) -> None:
    """Instala e carrega as extensões DuckDB necessárias.

    ``INSTALL`` baixa a extensão do repositório oficial (apenas na
    primeira vez); ``LOAD`` ativa a extensão na conexão atual (sempre
    necessário). A operação é idempotente — chamar múltiplas vezes é
    seguro.

    Extensões requeridas por este projeto:

    - **httpfs**: leitura direta de arquivos HTTP/HTTPS/S3
    - **spatial**: funções ``ST_*`` (compatíveis com PostGIS)

    Parameters
    ----------
    con : DuckDBPyConnection
        Conexão previamente criada por :func:`criar_conexao`.
    extensoes : tuple of str
        Lista de extensões a instalar. Default cobre as requeridas
        por este projeto.

    Raises
    ------
    RuntimeError
        Se ``INSTALL`` falhar (tipicamente por falta de rede na
        primeira execução — depois de instalada, extensão fica no
        cache local e não requer mais rede).
    """
    for ext in extensoes:
        logger.info("[EXTENSAO] Instalando e carregando %r", ext)
        try:
            con.execute(f"INSTALL {ext};")
            con.execute(f"LOAD {ext};")
        except duckdb.Error as e:
            raise RuntimeError(
                f"Falha ao instalar/carregar extensao {ext!r}. "
                f"Verifique conexao com a internet na primeira execucao. Erro original: {e}"
            ) from e


def configurar_s3(
    con: duckdb.DuckDBPyConnection,
    region: str = config.S3_REGION,
    ca_cert_file: str | Path | None = None,
) -> None:
    """Configura o cliente S3 do DuckDB para leitura anônima.

    O bucket VIDA é público, então não é necessária autenticação. Além
    da região AWS, esta função também configura o CA bundle usado para
    validação SSL — passo essencial no Windows.

    Configuração de CA bundle (Windows)
    -----------------------------------

    O ``httpfs`` do DuckDB no Windows usa um bundle interno (via
    libcurl compilado) que frequentemente falha em validar a cadeia
    SSL do S3 da AWS, gerando ``IOException: SSL peer certificate or
    SSH remote key was not OK``. A solução recomendada é apontar
    explicitamente para o bundle mantido pela biblioteca ``certifi``,
    que atualiza CAs com regularidade.

    Se ``ca_cert_file`` for ``None`` (default), tenta importar
    ``certifi`` e usar seu bundle. Se ``certifi`` não estiver
    instalado, emite ``[AVISO]`` e segue sem configurar — pode
    funcionar em Linux/Mac, mas falhará no Windows. Se
    ``ca_cert_file`` for passado explicitamente, usa esse path.

    Parameters
    ----------
    con : DuckDBPyConnection
    region : str, default valor de config.S3_REGION
        Região AWS do bucket.
    ca_cert_file : str, Path or None, default=None
        Caminho para o arquivo CA bundle (formato PEM). Se ``None``,
        tenta usar ``certifi.where()``. Se ``certifi`` não estiver
        disponível, segue sem configurar.
    """
    logger.info("[S3] Configurando cliente S3 para regiao %s", region)
    con.execute(f"SET s3_region='{region}';")

    if ca_cert_file is None:
        try:
            import certifi

            ca_cert_file = certifi.where()
            logger.info("[S3] CA bundle detectado via certifi: %s", ca_cert_file)
        except ImportError:
            logger.warning(
                "[AVISO] certifi nao instalado. No Windows isso pode causar "
                "erro SSL ao acessar S3. Instale com 'pip install certifi' "
                "ou passe ca_cert_file explicitamente."
            )
            return

    ca_cert_str = str(ca_cert_file).replace("\\", "/")
    try:
        con.execute(f"SET ca_cert_file='{ca_cert_str}';")
        logger.info("[S3] CA bundle configurado: %s", ca_cert_str)
    except duckdb.Error as e:
        # Versoes muito antigas do DuckDB podem nao ter esta variavel.
        # Nesse caso, seguimos sem configurar — comportamento pre-fix.
        logger.warning(
            "[AVISO] DuckDB nao aceita ca_cert_file (versao antiga?): %s. "
            "Se ocorrer erro SSL, atualize DuckDB.", e,
        )


# =============================================================================
# Carregamento de dados brutos
# =============================================================================
def carregar_pais(
    con: duckdb.DuckDBPyConnection,
    country_iso: str,
    tabela: str,
    particionamento: str = config.PARTITION_BY_COUNTRY_S2,
    bucket_url: str = config.S3_BUCKET_URL,
) -> int:
    """Materializa footprints de um país inteiro em uma tabela DuckDB.

    Executa ``parquet_scan`` sobre o bucket S3 público VIDA, filtrando
    pela partição ``country_iso``. DuckDB usa predicate pushdown na
    leitura Parquet, então apenas os blocos referentes ao país são
    baixados — para o Brasil (~140M linhas) a operação leva alguns
    segundos, não horas.

    Parameters
    ----------
    con : DuckDBPyConnection
        Conexão com ``httpfs`` já carregado e S3 configurado.
    country_iso : str
        Código ISO-3 do país (``BRA``, ``LSO``, ``AUS``).
    tabela : str
        Nome da tabela a criar (será validado como identificador SQL).
    particionamento : str, default ``by_country_s2``
        Qual particionamento usar: ``by_country`` (mais simples) ou
        ``by_country_s2`` (com sub-particionamento por célula S2 do
        Google — permite paralelismo natural na leitura).
    bucket_url : str, default valor de ``config.S3_BUCKET_URL``
        URL base do bucket. Sobrescrevível apenas para testes.

    Returns
    -------
    int
        Número de linhas carregadas na tabela.
    """
    _validar_identificador(tabela, "nome de tabela")
    _validar_iso3(country_iso)

    if particionamento not in (config.PARTITION_BY_COUNTRY, config.PARTITION_BY_COUNTRY_S2):
        raise ValueError(
            f"Particionamento invalido: {particionamento!r}. "
            f"Aceita: {config.PARTITION_BY_COUNTRY!r} ou {config.PARTITION_BY_COUNTRY_S2!r}."
        )

    caminho = f"{bucket_url}/{particionamento}/country_iso={country_iso}/*.parquet"
    sql = f"""
        CREATE OR REPLACE TABLE {tabela} AS
          SELECT * FROM parquet_scan('{caminho}')
    """

    logger.info(
        "[CARGA] Materializando %s (country_iso=%s, particionamento=%s)",
        tabela, country_iso, particionamento,
    )
    logger.debug("[CARGA] SQL: %s", sql)
    t0 = time.perf_counter()
    con.execute(sql)
    n = contar_registros(con, tabela)
    dt = time.perf_counter() - t0
    logger.info(
        "[OK] %s materializada: %d linhas em %.2fs",
        tabela, n, dt,
    )
    return n


def carregar_pais_google_original(
    con: duckdb.DuckDBPyConnection,
    country_iso_2: str,
    tabela: str,
    bucket_url: str = config.S3_GOOGLE_URL,
) -> int:
    """Materializa footprints do bucket Google Open Buildings v3 puro.

    Diferente de :func:`carregar_pais`, esta função lê do bucket
    original do Google (sem mesclagem Microsoft) e usa código ISO-2
    (``BR``, ``LS``, ``AU`` em vez de ``BRA``, ``LSO``, ``AUS``) —
    convenção herdada do schema original do Google.

    Útil para comparações "com Microsoft × sem Microsoft" que
    evidenciam o valor agregado da mesclagem VIDA.

    Parameters
    ----------
    con : DuckDBPyConnection
    country_iso_2 : str
        Código ISO-2 do país (``BR``, ``LS``, ``AU``).
    tabela : str
        Nome da tabela a criar.
    bucket_url : str, default valor de ``config.S3_GOOGLE_URL``

    Returns
    -------
    int
        Número de linhas carregadas.
    """
    _validar_identificador(tabela, "nome de tabela")
    _validar_iso2(country_iso_2)

    caminho = f"{bucket_url}/country_iso={country_iso_2}/{country_iso_2}.parquet"
    sql = f"""
        CREATE OR REPLACE TABLE {tabela} AS
          SELECT * FROM '{caminho}'
    """

    logger.info(
        "[CARGA] Materializando %s (Google original, country_iso=%s)",
        tabela, country_iso_2,
    )
    logger.debug("[CARGA] SQL: %s", sql)
    t0 = time.perf_counter()
    con.execute(sql)
    n = contar_registros(con, tabela)
    dt = time.perf_counter() - t0
    logger.info(
        "[OK] %s materializada: %d linhas em %.2fs",
        tabela, n, dt,
    )
    return n


# =============================================================================
# AOI e recorte espacial
# =============================================================================
def carregar_aoi_geojson(
    con: duckdb.DuckDBPyConnection,
    geojson_path: str | Path,
    tabela: str,
) -> int:
    """Carrega um GeoJSON de AOI como tabela DuckDB.

    Usa ``ST_Read`` da extensão spatial. A coluna geométrica na
    tabela resultante se chama ``geom`` (convenção da extensão
    spatial), diferente da coluna ``geometry`` das tabelas de
    footprints (convenção do dataset Open Buildings).

    Parameters
    ----------
    con : DuckDBPyConnection
        Conexão com extensão ``spatial`` carregada.
    geojson_path : str or Path
        Caminho para o arquivo GeoJSON local.
    tabela : str
        Nome da tabela a criar.

    Returns
    -------
    int
        Número de features carregadas (tipicamente 1 para AOI).
    """
    _validar_identificador(tabela, "nome de tabela")
    path = Path(geojson_path)
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON nao encontrado: {path}")

    caminho_absoluto = str(path.resolve()).replace("\\", "/")
    sql = f"""
        CREATE OR REPLACE TABLE {tabela} AS
          SELECT * FROM ST_Read('{caminho_absoluto}')
    """

    logger.info("[AOI] Carregando GeoJSON %s -> %s", path.name, tabela)
    con.execute(sql)
    n = contar_registros(con, tabela)
    logger.info("[OK] %s carregada: %d feature(s)", tabela, n)
    return n


def recortar_por_aoi(
    con: duckdb.DuckDBPyConnection,
    tabela_footprints: str,
    tabela_aoi: str,
    tabela_recorte: str,
    coluna_geom_footprints: str = "geometry",
    coluna_geom_aoi: str = "geom",
    preservar_colunas: tuple[str, ...] = (config.COLUMN_SOURCE,),
    crs_alvo: str = "EPSG:4326",
) -> int:
    """Recorta footprints por interseção com a AOI, criando nova tabela.

    Aplica ``ST_Intersection`` entre cada footprint e o polígono da
    AOI, filtrando via ``ST_Intersects``. O resultado é uma tabela
    contendo apenas as edificações dentro da AOI, com a geometria
    eventualmente cortada nas bordas.

    Normalização de CRS
    -------------------

    Versões recentes da extensão DuckDB spatial (>= 1.5) fazem
    validação estrita de CRS entre geometrias em operações binárias.
    Duas geometrias que representam o mesmo sistema físico (WGS84)
    mas foram rotuladas com CRS distintos — como ``EPSG:4326`` (default
    do ``ST_GeomFromText``) e ``OGC:CRS84`` (default do ``ST_Read``
    para GeoJSON, seguindo RFC 7946) — causam ``BinderException`` ao
    ser passadas juntas para ``ST_Intersects``.

    Essa função aplica ``ST_SetCRS(geom, crs_alvo)`` em ambas as
    geometrias antes de qualquer operação, forçando-as ao mesmo
    rótulo. ``ST_SetCRS`` apenas **re-rotula** a geometria (não
    transforma coordenadas), o que é seguro aqui porque
    ``EPSG:4326`` e ``OGC:CRS84`` são o mesmo sistema físico com
    nomes diferentes na registration authority.

    Parameters
    ----------
    con : DuckDBPyConnection
    tabela_footprints : str
        Tabela de origem (carregada por :func:`carregar_pais`).
    tabela_aoi : str
        Tabela da AOI (carregada por :func:`carregar_aoi_geojson`).
    tabela_recorte : str
        Nome da tabela de destino.
    coluna_geom_footprints : str, default ``"geometry"``
        Nome da coluna geométrica na tabela de footprints.
    coluna_geom_aoi : str, default ``"geom"``
        Nome da coluna geométrica na tabela de AOI.
    preservar_colunas : tuple of str, default ``("bf_source",)``
        Colunas adicionais da tabela de footprints a manter no recorte.
        Cada nome é validado como identificador SQL. Por default
        preserva apenas ``bf_source``, que é a coluna essencial para
        a análise comparativa Google × Microsoft.
    crs_alvo : str, default ``"EPSG:4326"``
        CRS a aplicar via ``ST_SetCRS`` em ambas as geometrias antes
        da operação. Como o dataset Open Buildings e os GeoJSONs de
        AOI já estão em WGS84, o default cobre 100% dos casos deste
        projeto. Só mude se souber o que está fazendo.

    Returns
    -------
    int
        Número de footprints no recorte.
    """
    _validar_identificador(tabela_footprints, "nome de tabela de footprints")
    _validar_identificador(tabela_aoi, "nome de tabela de AOI")
    _validar_identificador(tabela_recorte, "nome de tabela de recorte")
    _validar_identificador(coluna_geom_footprints, "coluna de geometria (footprints)")
    _validar_identificador(coluna_geom_aoi, "coluna de geometria (AOI)")
    for col in preservar_colunas:
        _validar_identificador(col, "coluna a preservar")

    # Validação básica do CRS alvo — evita SQL injection e catches erros de digitação.
    # Formato esperado: "EPSG:4326", "OGC:CRS84", etc. — só letras, dígitos e ":"
    if not re.match(r"^[A-Za-z0-9:_-]+$", crs_alvo):
        raise ValueError(
            f"crs_alvo invalido: {crs_alvo!r}. "
            "Esperado formato como 'EPSG:4326' ou 'OGC:CRS84'."
        )

    cols_extras = ", ".join(f"b.{c}" for c in preservar_colunas)
    if cols_extras:
        cols_extras = ", " + cols_extras

    # Normalização de CRS: forca ambas as geometrias ao mesmo rotulo antes
    # da operação binaria. Ver docstring para detalhes.
    geom_b = f"ST_SetCRS(b.{coluna_geom_footprints}, '{crs_alvo}')"
    geom_a = f"ST_SetCRS(a.{coluna_geom_aoi}, '{crs_alvo}')"

    sql = f"""
        CREATE OR REPLACE TABLE {tabela_recorte} AS
          SELECT ST_Intersection({geom_b}, {geom_a}) AS geom{cols_extras}
          FROM {tabela_footprints} b, {tabela_aoi} a
          WHERE ST_Intersects({geom_b}, {geom_a})
    """

    logger.info(
        "[RECORTE] %s x %s -> %s (CRS alvo=%s)",
        tabela_footprints, tabela_aoi, tabela_recorte, crs_alvo,
    )
    logger.debug("[RECORTE] SQL: %s", sql)
    t0 = time.perf_counter()
    con.execute(sql)
    n = contar_registros(con, tabela_recorte)
    dt = time.perf_counter() - t0
    logger.info(
        "[OK] %s materializada: %d footprints em %.2fs",
        tabela_recorte, n, dt,
    )
    return n


# =============================================================================
# Exportação para formatos geoespaciais
# =============================================================================
def exportar_flatgeobuf(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    output_path: str | Path,
    colunas: tuple[str, ...] | None = None,
) -> Path:
    """Exporta uma tabela DuckDB para o formato FlatGeobuf (.fgb).

    FlatGeobuf é o formato preferido pelo dataset original para
    output — leitura sequencial rápida, streamable, suportado por
    QGIS, GDAL, geopandas.

    Parameters
    ----------
    con : DuckDBPyConnection
    tabela : str
        Tabela de origem.
    output_path : str or Path
        Caminho de saída. Extensão ``.fgb`` recomendada.
    colunas : tuple of str, optional
        Subconjunto de colunas a exportar. Se ``None``, exporta
        todas.

    Returns
    -------
    Path
        Caminho absoluto do arquivo gerado.
    """
    _validar_identificador(tabela, "nome de tabela")
    if colunas:
        for col in colunas:
            _validar_identificador(col, "coluna")

    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    select_clause = ", ".join(colunas) if colunas else "*"
    caminho_str = str(path).replace("\\", "/")
    sql = f"""
        COPY (SELECT {select_clause} FROM {tabela})
        TO '{caminho_str}' WITH (FORMAT GDAL, DRIVER 'FlatGeobuf')
    """

    logger.info("[EXPORT] %s -> %s (FlatGeobuf)", tabela, path.name)
    con.execute(sql)
    logger.info("[OK] %s exportada para %s", tabela, path)
    return path


def exportar_geojson(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    output_path: str | Path,
    colunas: tuple[str, ...] | None = None,
) -> Path:
    """Exporta uma tabela DuckDB para GeoJSON.

    GeoJSON é o formato preferido pelo webmap Leaflet — carregável
    diretamente via fetch, sem precisar de tile server. Adequado
    para AOIs pequenas/médias (até algumas dezenas de milhares de
    features); acima disso, considerar PMTiles ou vector tiles.

    Parameters
    ----------
    con : DuckDBPyConnection
    tabela : str
    output_path : str or Path
    colunas : tuple of str, optional

    Returns
    -------
    Path
        Caminho absoluto do arquivo gerado.
    """
    _validar_identificador(tabela, "nome de tabela")
    if colunas:
        for col in colunas:
            _validar_identificador(col, "coluna")

    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    select_clause = ", ".join(colunas) if colunas else "*"
    caminho_str = str(path).replace("\\", "/")
    sql = f"""
        COPY (SELECT {select_clause} FROM {tabela})
        TO '{caminho_str}' WITH (FORMAT GDAL, DRIVER 'GeoJSON')
    """

    logger.info("[EXPORT] %s -> %s (GeoJSON)", tabela, path.name)
    con.execute(sql)
    logger.info("[OK] %s exportada para %s", tabela, path)
    return path


# =============================================================================
# Helpers de introspecção
# =============================================================================
def contar_registros(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
) -> int:
    """Retorna a contagem de linhas de uma tabela."""
    _validar_identificador(tabela, "nome de tabela")
    resultado = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
    return int(resultado[0]) if resultado else 0


def listar_tabelas(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Retorna lista de tabelas existentes na conexão."""
    resultado = con.execute("SHOW TABLES").fetchall()
    return [linha[0] for linha in resultado]


def descrever_tabela(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
) -> list[dict[str, Any]]:
    """Retorna descrição da estrutura de uma tabela.

    Cada elemento do retorno é um dict com chaves ``column_name``,
    ``column_type``, ``null``, ``key``, ``default``, ``extra`` (mesmo
    formato do ``DESCRIBE`` do DuckDB).
    """
    _validar_identificador(tabela, "nome de tabela")
    df = con.execute(f"DESCRIBE {tabela}").fetchdf()
    return df.to_dict(orient="records")


def extensoes_carregadas(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Retorna lista de extensões atualmente carregadas na conexão."""
    resultado = con.execute(
        "SELECT extension_name FROM duckdb_extensions() WHERE loaded=true"
    ).fetchall()
    return [linha[0] for linha in resultado]
