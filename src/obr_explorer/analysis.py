"""Análises de negócio sobre footprints recortados por AOI.

Este módulo consome tabelas DuckDB já materializadas (pelas funções
de :mod:`obr_explorer.duckdb_client`) e produz agregações analíticas
que respondem às perguntas centrais do projeto:

- Quantas edificações há na AOI, por fonte?
- Qual a área total edificada?
- Como as fontes Google e Microsoft se comparam entre si?
- Como as AOIs se comparam entre si (densidade, tamanho médio)?

Todas as funções retornam dicionários serializáveis em JSON (não
DataFrames), facilitando consumo pela CLI e pelo webmap sem
depender de pandas na camada de output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import duckdb

from obr_explorer import config

logger = logging.getLogger(__name__)


# =============================================================================
# Validação (compartilhada com duckdb_client, replicada para desacoplar)
# =============================================================================
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validar_identificador(nome: str, contexto: str = "identificador") -> str:
    """Rejeita identificadores SQL não-seguros (protege contra injection)."""
    if not _IDENTIFICADOR_VALIDO.match(nome):
        raise ValueError(
            f"{contexto} invalido: {nome!r}. "
            "Aceita apenas letras, digitos e underscore, comecando com letra ou underscore."
        )
    return nome


# =============================================================================
# Dataclasses de resultado
# =============================================================================
@dataclass
class ResumoAOI:
    """Resumo estatístico completo de uma AOI recortada.

    Attributes
    ----------
    aoi_nome : str
        Nome/slug da AOI.
    tabela : str
        Nome da tabela DuckDB analisada.
    total_footprints : int
        Contagem total de footprints na AOI.
    por_fonte : dict
        ``{"google": n, "microsoft": n}``.
    area_total_m2_por_fonte : dict
        Área somada em m² por fonte. Calculada via ``ST_Area`` do
        DuckDB spatial. Nota: em EPSG:4326 (WGS84), ``ST_Area``
        retorna área em graus quadrados, não m². Convertemos usando
        aproximação equatorial (1 grau ~= 111 km); precisão de área
        para pequenas AOIs é razoável mas não exata. Para precisão
        métrica, reprojetar para UTM local antes de calcular.
    area_media_m2_por_fonte : dict
        Área média por footprint por fonte.
    """

    aoi_nome: str
    tabela: str
    total_footprints: int
    por_fonte: dict[str, int] = field(default_factory=dict)
    area_total_m2_por_fonte: dict[str, float] = field(default_factory=dict)
    area_media_m2_por_fonte: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Retorna representação serializável em JSON."""
        return asdict(self)


@dataclass
class ComparacaoAOIs:
    """Comparação lado a lado de várias AOIs.

    Attributes
    ----------
    resumos : dict
        ``{aoi_nome: ResumoAOI}`` para cada AOI comparada.
    densidade_por_km2 : dict
        Total de footprints por km² da bounding box, para cada AOI.
        Índice grosseiro de urbanização.
    """

    resumos: dict[str, ResumoAOI] = field(default_factory=dict)
    densidade_por_km2: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resumos": {k: v.to_dict() for k, v in self.resumos.items()},
            "densidade_por_km2": self.densidade_por_km2,
        }


# =============================================================================
# Contagens
# =============================================================================
def contar_total(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    """Conta o total de footprints em uma tabela."""
    _validar_identificador(tabela, "nome de tabela")
    r = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
    return int(r[0]) if r else 0


def contar_por_fonte(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna_fonte: str = config.COLUMN_SOURCE,
) -> dict[str, int]:
    """Conta footprints agrupados por fonte (Google/Microsoft).

    Parameters
    ----------
    con : DuckDBPyConnection
    tabela : str
        Tabela recortada por AOI (deve ter ``bf_source`` preservado).
    coluna_fonte : str, default ``"bf_source"``
        Nome da coluna com o valor da fonte.

    Returns
    -------
    dict
        Ex: ``{"google": 1250, "microsoft": 340}``. Fontes ausentes
        na AOI simplesmente não aparecem no dict.
    """
    _validar_identificador(tabela, "nome de tabela")
    _validar_identificador(coluna_fonte, "nome de coluna")

    sql = f"""
        SELECT {coluna_fonte} AS fonte, COUNT(*) AS n
        FROM {tabela}
        GROUP BY {coluna_fonte}
        ORDER BY n DESC
    """
    rows = con.execute(sql).fetchall()
    return {str(fonte): int(n) for fonte, n in rows}


# =============================================================================
# Áreas
# =============================================================================
# Fator de conversão aproximada: 1 grau^2 ~= (111 km)^2 = 12.321 km^2 = 12.321.000.000 m^2
# na linha do equador. Para latitudes fora da linha do equador, multiplicar por cos(lat).
# Para AOIs pequenas (<1 grau em lat/lon), esta aproximação tem erro < 5%.
_GRAU_EM_M2_EQUATORIAL = 111_000.0 * 111_000.0


def area_total_por_fonte(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna_geom: str = "geom",
    coluna_fonte: str = config.COLUMN_SOURCE,
    lat_media: float | None = None,
) -> dict[str, float]:
    """Retorna área total por fonte em metros quadrados (aproximada).

    Usa ``ST_Area`` do DuckDB spatial, que retorna área em graus^2
    quando as coordenadas estão em WGS84. Aproximamos para m²
    multiplicando pelo fator equatorial e ajustando pela latitude
    média da AOI (se fornecida).

    Parameters
    ----------
    con : DuckDBPyConnection
    tabela : str
    coluna_geom : str, default ``"geom"``
        Coluna geométrica (default da tabela produzida por
        :func:`duckdb_client.recortar_por_aoi`).
    coluna_fonte : str, default ``"bf_source"``
    lat_media : float, optional
        Latitude média da AOI para ajuste de projeção. Se ``None``,
        assume equador (superestima área para latitudes altas).
        Para Cambuquira/Uberlândia, passe algo entre -22 e -18.

    Returns
    -------
    dict
        ``{"google": <m²>, "microsoft": <m²>}``
    """
    _validar_identificador(tabela, "nome de tabela")
    _validar_identificador(coluna_geom, "coluna geom")
    _validar_identificador(coluna_fonte, "coluna fonte")

    import math

    fator_lat = math.cos(math.radians(lat_media)) if lat_media is not None else 1.0
    fator_conv = _GRAU_EM_M2_EQUATORIAL * fator_lat

    sql = f"""
        SELECT {coluna_fonte} AS fonte, SUM(ST_Area({coluna_geom})) AS area_graus2
        FROM {tabela}
        GROUP BY {coluna_fonte}
        ORDER BY area_graus2 DESC
    """
    rows = con.execute(sql).fetchall()
    return {
        str(fonte): float(area_graus2 or 0.0) * fator_conv
        for fonte, area_graus2 in rows
    }


# =============================================================================
# Resumo agregado
# =============================================================================
def resumo_aoi(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    aoi_nome: str = "<sem_nome>",
    coluna_geom: str = "geom",
    coluna_fonte: str = config.COLUMN_SOURCE,
    lat_media: float | None = None,
) -> ResumoAOI:
    """Produz um :class:`ResumoAOI` completo para a tabela dada.

    Combina contagens + áreas + médias em uma única chamada. Usado
    pela CLI ``analyze`` e pelo webmap.
    """
    _validar_identificador(tabela, "nome de tabela")

    total = contar_total(con, tabela)
    por_fonte = contar_por_fonte(con, tabela, coluna_fonte=coluna_fonte)
    area_por_fonte = area_total_por_fonte(
        con, tabela,
        coluna_geom=coluna_geom, coluna_fonte=coluna_fonte, lat_media=lat_media,
    )

    area_media = {
        fonte: (area_por_fonte.get(fonte, 0.0) / n) if n > 0 else 0.0
        for fonte, n in por_fonte.items()
    }

    return ResumoAOI(
        aoi_nome=aoi_nome,
        tabela=tabela,
        total_footprints=total,
        por_fonte=por_fonte,
        area_total_m2_por_fonte=area_por_fonte,
        area_media_m2_por_fonte=area_media,
    )


# =============================================================================
# Comparação entre AOIs
# =============================================================================
def comparar_aois(
    con: duckdb.DuckDBPyConnection,
    tabelas_por_aoi: dict[str, str],
    bounds_por_aoi: dict[str, tuple[float, float, float, float]] | None = None,
    coluna_geom: str = "geom",
    coluna_fonte: str = config.COLUMN_SOURCE,
) -> ComparacaoAOIs:
    """Compara métricas entre várias AOIs simultaneamente.

    Parameters
    ----------
    con : DuckDBPyConnection
    tabelas_por_aoi : dict
        Mapa ``{aoi_nome: tabela_duckdb}``. Ex:
        ``{"cambuquira_mg": "obr_cambuquira", "uberlandia_mg": "obr_uberlandia"}``.
    bounds_por_aoi : dict, optional
        Mapa ``{aoi_nome: (minx, miny, maxx, maxy)}`` para calcular
        densidade por km². Se ausente, densidade não é calculada.
    coluna_geom, coluna_fonte : str
        Ver :func:`resumo_aoi`.

    Returns
    -------
    ComparacaoAOIs
    """
    resumos: dict[str, ResumoAOI] = {}
    for nome, tabela in tabelas_por_aoi.items():
        # Latitude média a partir das bounds (se disponível) melhora precisão de área
        lat_media = None
        if bounds_por_aoi and nome in bounds_por_aoi:
            _, miny, _, maxy = bounds_por_aoi[nome]
            lat_media = (miny + maxy) / 2
        resumos[nome] = resumo_aoi(
            con, tabela,
            aoi_nome=nome,
            coluna_geom=coluna_geom,
            coluna_fonte=coluna_fonte,
            lat_media=lat_media,
        )

    densidade = {}
    if bounds_por_aoi:
        import math

        for nome, bounds in bounds_por_aoi.items():
            if nome not in resumos:
                continue
            minx, miny, maxx, maxy = bounds
            lat_media_rad = math.radians((miny + maxy) / 2)
            lat_km = (maxy - miny) * 111.0
            lon_km = (maxx - minx) * 111.0 * math.cos(lat_media_rad)
            area_km2 = abs(lat_km * lon_km)
            densidade[nome] = (
                resumos[nome].total_footprints / area_km2 if area_km2 > 0 else 0.0
            )

    return ComparacaoAOIs(resumos=resumos, densidade_por_km2=densidade)


# =============================================================================
# Formatação legível para stdout / CLI
# =============================================================================
def formatar_resumo_texto(resumo: ResumoAOI) -> str:
    """Formata um :class:`ResumoAOI` como texto plano para exibição.

    Retorna string multilinha pronta para ``print()``. Usada pela
    CLI ``analyze``.
    """
    linhas = [
        f"AOI: {resumo.aoi_nome}",
        f"Tabela DuckDB: {resumo.tabela}",
        f"Total de footprints: {resumo.total_footprints:,}",
        "",
        "Por fonte:",
    ]
    total = resumo.total_footprints or 1  # evita div/0
    for fonte, n in sorted(resumo.por_fonte.items(), key=lambda x: -x[1]):
        pct = 100.0 * n / total
        area_total = resumo.area_total_m2_por_fonte.get(fonte, 0.0)
        area_media = resumo.area_media_m2_por_fonte.get(fonte, 0.0)
        linhas.append(f"  {fonte:12s} {n:>10,} ({pct:5.1f}%)")
        linhas.append(
            f"    area total: {area_total:>15,.0f} m2 "
            f"| media/footprint: {area_media:>8.1f} m2"
        )
    return "\n".join(linhas)


def formatar_comparacao_texto(cmp: ComparacaoAOIs) -> str:
    """Formata uma :class:`ComparacaoAOIs` como tabela texto plano."""
    if not cmp.resumos:
        return "Nenhuma AOI para comparar."

    linhas = ["Comparacao entre AOIs:", ""]
    header = f"{'AOI':<20} {'Total':>10} {'Google':>10} {'MS':>10} {'Dens/km2':>12}"
    linhas.append(header)
    linhas.append("-" * len(header))
    for nome, r in cmp.resumos.items():
        g = r.por_fonte.get(config.SOURCE_GOOGLE, 0)
        m = r.por_fonte.get(config.SOURCE_MICROSOFT, 0)
        dens = cmp.densidade_por_km2.get(nome, 0.0)
        linhas.append(
            f"{nome:<20} {r.total_footprints:>10,} {g:>10,} {m:>10,} {dens:>12,.1f}"
        )
    return "\n".join(linhas)
