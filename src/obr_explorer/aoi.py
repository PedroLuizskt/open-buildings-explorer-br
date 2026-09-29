"""Gerenciamento de áreas de interesse (AOIs) brasileiras.

Este módulo cuida de três coisas:

1. **Listar e carregar AOIs versionadas** em ``data/external/aois/`` — cada
   AOI é um GeoJSON com metadata rica (nome, tipologia, população,
   descrição) no ``properties`` da feature única.

2. **Baixar polígonos oficiais IBGE** via API v3 de malhas municipais.
   Substitui bounding boxes por limites administrativos reais quando o
   usuário roda ``obr-explorer aoi fetch --codigo <IBGE_ID>``.

3. **Validar AOIs** — verifica que estão em EPSG:4326, têm feature única,
   geometria válida (não auto-intersectante), etc.

Modelo de dados
---------------

Uma AOI é um GeoJSON ``FeatureCollection`` com exatamente uma feature
poligonal. O ``properties`` da feature carrega metadata editorial:

::

    {
      "type": "FeatureCollection",
      "name": "cambuquira_mg",
      "features": [{
        "type": "Feature",
        "properties": {
          "nome": "Cambuquira",
          "uf": "MG",
          "ibge_code": "3111606",
          "tipologia": "municipio_rural_pequeno",
          "populacao_2022": 12609,
          "descricao": "...",
          "fonte_poligono": "..."
        },
        "geometry": { "type": "Polygon", "coordinates": [...] }
      }]
    }

Convenções
----------

- Nome de AOI segue snake_case: ``cambuquira_mg``, ``uberlandia_mg``
- Arquivo GeoJSON tem o mesmo nome do AOI: ``cambuquira_mg.geojson``
- CRS obrigatório: WGS84 (EPSG:4326 ou OGC:CRS84, ambos equivalentes)
- Uma AOI = uma feature (Polygon ou MultiPolygon)
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from obr_explorer import config

logger = logging.getLogger(__name__)


# =============================================================================
# API IBGE
# =============================================================================
IBGE_MALHAS_URL_BASE = "https://servicodados.ibge.gov.br/api/v3/malhas/municipios"
"""Endpoint base da API v3 de malhas do IBGE."""

QUALIDADES_IBGE = ("minima", "intermediaria", "maxima")
"""Níveis de detalhe geométrico aceitos pela API IBGE (mais detalhe = arquivo maior)."""


# =============================================================================
# Dataclass principal
# =============================================================================
@dataclass
class AOI:
    """Representação carregada de uma AOI.

    Attributes
    ----------
    nome : str
        Slug snake_case da AOI (ex: ``"cambuquira_mg"``).
    path : Path
        Caminho absoluto do arquivo GeoJSON.
    geojson : dict
        Conteúdo bruto do arquivo GeoJSON.
    bounds : tuple of float
        Bounding box (minx, miny, maxx, maxy) em WGS84.
    properties : dict
        Metadata editorial (``nome``, ``uf``, ``ibge_code``, etc.)
        extraída de ``features[0].properties``.
    """

    nome: str
    path: Path
    geojson: dict[str, Any] = field(repr=False)
    bounds: tuple[float, float, float, float]
    properties: dict[str, Any]

    @property
    def nome_exibicao(self) -> str:
        """Nome amigável para exibir (ex: 'Cambuquira/MG')."""
        n = self.properties.get("nome", self.nome)
        uf = self.properties.get("uf")
        return f"{n}/{uf}" if uf else n

    @property
    def area_km2_aproximada(self) -> float:
        """Área aproximada em km² calculada da bounding box.

        Aproximação grosseira apenas — não é a área real do polígono,
        mas útil para ordem de grandeza. Para área real, use
        ``geopandas`` sobre o próprio polígono após reprojeção métrica.
        """
        minx, miny, maxx, maxy = self.bounds
        # Aproximação: 1 grau lat ~= 111 km; 1 grau lon ~= 111 * cos(lat)
        import math

        lat_media_rad = math.radians((miny + maxy) / 2)
        lat_km = (maxy - miny) * 111.0
        lon_km = (maxx - minx) * 111.0 * math.cos(lat_media_rad)
        return abs(lat_km * lon_km)


# =============================================================================
# Listagem e carregamento
# =============================================================================
def listar_aois(diretorio: Path | None = None) -> list[dict[str, Any]]:
    """Lista todas as AOIs disponíveis no diretório configurado.

    Parameters
    ----------
    diretorio : Path, optional
        Diretório onde procurar GeoJSONs de AOI. Default:
        ``config.AOI_DIR``.

    Returns
    -------
    list of dict
        Lista ordenada por nome. Cada elemento tem chaves:
        ``nome``, ``arquivo``, ``properties`` (dict com metadata
        do primeiro feature).
    """
    diretorio = Path(diretorio) if diretorio else config.AOI_DIR
    if not diretorio.exists():
        logger.warning("[AOI] Diretorio de AOIs nao existe: %s", diretorio)
        return []

    aois = []
    for arquivo in sorted(diretorio.glob("*.geojson")):
        try:
            with arquivo.open() as f:
                gj = json.load(f)
            props = gj.get("features", [{}])[0].get("properties", {})
            aois.append({
                "nome": arquivo.stem,
                "arquivo": str(arquivo),
                "properties": props,
            })
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.warning("[AVISO] Ignorando %s (formato invalido): %s", arquivo.name, e)

    return aois


def carregar_aoi(nome: str, diretorio: Path | None = None) -> AOI:
    """Carrega uma AOI por nome.

    Parameters
    ----------
    nome : str
        Slug da AOI (ex: ``"cambuquira_mg"``) — sem extensão.
    diretorio : Path, optional
        Diretório de busca. Default: ``config.AOI_DIR``.

    Returns
    -------
    AOI
        Dataclass carregada e validada.

    Raises
    ------
    FileNotFoundError
        Se o arquivo ``<nome>.geojson`` não existe.
    ValueError
        Se o arquivo existe mas o conteúdo não é uma AOI válida
        (não é FeatureCollection com exatamente uma feature poligonal).
    """
    diretorio = Path(diretorio) if diretorio else config.AOI_DIR
    path = diretorio / f"{nome}.geojson"

    if not path.exists():
        disponiveis = sorted(p.stem for p in diretorio.glob("*.geojson"))
        raise FileNotFoundError(
            f"AOI {nome!r} nao encontrada em {diretorio}. "
            f"Disponiveis: {disponiveis or 'nenhuma'}"
        )

    with path.open() as f:
        gj = json.load(f)

    validar_geojson_aoi(gj, nome=nome)

    feature = gj["features"][0]
    properties = feature.get("properties", {})
    bounds = _calcular_bounds(feature["geometry"])

    logger.info("[AOI] Carregada %s (bounds=%s)", nome, tuple(round(x, 4) for x in bounds))

    return AOI(
        nome=nome,
        path=path,
        geojson=gj,
        bounds=bounds,
        properties=properties,
    )


def validar_geojson_aoi(gj: dict[str, Any], nome: str = "<aoi>") -> None:
    """Valida a estrutura de um GeoJSON como AOI válida.

    Regras:

    - Deve ser ``FeatureCollection``
    - Deve ter exatamente uma feature
    - A feature deve ter geometria ``Polygon`` ou ``MultiPolygon``
    - Coordenadas devem estar em WGS84 (long em [-180, 180],
      lat em [-90, 90])

    Raises
    ------
    ValueError
        Com mensagem descritiva quando alguma regra é violada.
    """
    if gj.get("type") != "FeatureCollection":
        raise ValueError(
            f"AOI {nome!r} nao eh FeatureCollection (type={gj.get('type')!r})"
        )

    features = gj.get("features", [])
    if len(features) != 1:
        raise ValueError(
            f"AOI {nome!r} deve ter exatamente 1 feature; encontradas {len(features)}"
        )

    geom = features[0].get("geometry", {})
    geom_type = geom.get("type")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            f"AOI {nome!r} deve ser Polygon ou MultiPolygon; encontrado {geom_type!r}"
        )

    # Sanidade de coordenadas WGS84
    bounds = _calcular_bounds(geom)
    minx, miny, maxx, maxy = bounds
    if not (-180 <= minx <= 180 and -180 <= maxx <= 180):
        raise ValueError(
            f"AOI {nome!r} tem longitude fora de [-180, 180]: bounds={bounds}"
        )
    if not (-90 <= miny <= 90 and -90 <= maxy <= 90):
        raise ValueError(
            f"AOI {nome!r} tem latitude fora de [-90, 90]: bounds={bounds}"
        )


def _calcular_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """Calcula bounding box de uma geometria GeoJSON Polygon/MultiPolygon."""
    coords_flat: list[tuple[float, float]] = []

    def _extrair_coords(coords):
        # Coords vem em profundidades variaveis: Polygon [[[x,y],...]],
        # MultiPolygon [[[[x,y],...]]]. Achatamos recursivamente ate
        # encontrar pares [x,y].
        if isinstance(coords, (list, tuple)) and coords:
            if (
                isinstance(coords[0], (int, float))
                and isinstance(coords[1] if len(coords) > 1 else 0, (int, float))
            ):
                coords_flat.append((float(coords[0]), float(coords[1])))
            else:
                for sub in coords:
                    _extrair_coords(sub)

    _extrair_coords(geometry.get("coordinates", []))

    if not coords_flat:
        raise ValueError("Geometria sem coordenadas.")

    xs = [c[0] for c in coords_flat]
    ys = [c[1] for c in coords_flat]
    return (min(xs), min(ys), max(xs), max(ys))


# =============================================================================
# Download de malha oficial IBGE
# =============================================================================
def baixar_malha_ibge(
    codigo_ibge: str | int,
    qualidade: str = "maxima",
    timeout: int = 30,
) -> dict[str, Any]:
    """Baixa a malha oficial de um município via API v3 do IBGE.

    Retorna o GeoJSON bruto (sem metadata editorial adicionada).
    Para gerar um GeoJSON completo pronto para uso como AOI, use
    :func:`salvar_aoi_do_ibge`.

    Parameters
    ----------
    codigo_ibge : str or int
        Código IBGE de 7 dígitos do município (ex: ``3111606`` para
        Cambuquira/MG, ``3170206`` para Uberlândia/MG).
    qualidade : str, default ``"maxima"``
        Nível de detalhe geométrico. Aceita ``"minima"``,
        ``"intermediaria"`` ou ``"maxima"``. Máxima gera arquivos
        maiores (~50 KB a alguns MB) mas com bordas fiéis.
    timeout : int, default 30
        Timeout em segundos para a request HTTP.

    Returns
    -------
    dict
        GeoJSON ``FeatureCollection`` retornado pela API.

    Raises
    ------
    ValueError
        Se qualidade inválida.
    RuntimeError
        Se a API retornar erro HTTP ou payload inválido.
    """
    codigo = str(codigo_ibge).strip()
    if not codigo.isdigit() or len(codigo) != 7:
        raise ValueError(
            f"Codigo IBGE invalido: {codigo!r}. Esperado 7 digitos numericos "
            "(ex: '3111606' para Cambuquira/MG)."
        )

    if qualidade not in QUALIDADES_IBGE:
        raise ValueError(
            f"Qualidade invalida: {qualidade!r}. Aceita: {QUALIDADES_IBGE}."
        )

    params = urllib.parse.urlencode({
        "formato": "application/vnd.geo+json",
        "qualidade": qualidade,
    })
    url = f"{IBGE_MALHAS_URL_BASE}/{codigo}?{params}"

    logger.info("[IBGE] Baixando malha %s (qualidade=%s)", codigo, qualidade)
    logger.debug("[IBGE] URL: %s", url)

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"API IBGE retornou HTTP {e.code} para codigo {codigo!r}. "
            f"Verifique se o codigo eh valido em servicodados.ibge.gov.br."
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Falha de rede ao acessar API IBGE: {e}. "
            "Verifique conexao e proxy."
        ) from e

    try:
        gj = json.loads(payload)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"API IBGE retornou payload nao-JSON para codigo {codigo!r}: {e}"
        ) from e

    if gj.get("type") != "FeatureCollection":
        raise RuntimeError(
            f"API IBGE retornou payload inesperado (type={gj.get('type')!r}). "
            "Formato pode ter mudado."
        )

    logger.info(
        "[OK] Malha baixada: %d feature(s), %d bytes",
        len(gj.get("features", [])), len(payload),
    )
    return gj


def salvar_aoi_do_ibge(
    codigo_ibge: str | int,
    nome_slug: str,
    metadata: dict[str, Any],
    diretorio: Path | None = None,
    qualidade: str = "maxima",
    sobrescrever: bool = False,
) -> Path:
    """Baixa a malha IBGE de um município e salva como GeoJSON de AOI.

    Combina o polígono oficial do IBGE com metadata editorial
    (nome, tipologia, população, etc.) e persiste em
    ``<diretorio>/<nome_slug>.geojson``.

    Parameters
    ----------
    codigo_ibge : str or int
        Código IBGE de 7 dígitos do município.
    nome_slug : str
        Slug snake_case para o arquivo (ex: ``"cambuquira_mg"``).
    metadata : dict
        Metadata editorial que vai para ``properties`` da feature.
        Convenção: incluir ``nome``, ``uf``, ``ibge_code``,
        ``tipologia``, ``populacao_2022``, ``descricao``.
        ``ibge_code`` é preenchido automaticamente se ausente.
    diretorio : Path, optional
        Onde salvar. Default: ``config.AOI_DIR``.
    qualidade : str, default ``"maxima"``
    sobrescrever : bool, default False
        Se False e o arquivo já existir, levanta ``FileExistsError``.

    Returns
    -------
    Path
        Caminho absoluto do GeoJSON salvo.
    """
    if not nome_slug.replace("_", "").isalnum():
        raise ValueError(
            f"nome_slug invalido: {nome_slug!r}. Use apenas letras, digitos e underscore."
        )

    diretorio = Path(diretorio) if diretorio else config.AOI_DIR
    diretorio.mkdir(parents=True, exist_ok=True)
    destino = diretorio / f"{nome_slug}.geojson"

    if destino.exists() and not sobrescrever:
        raise FileExistsError(
            f"AOI ja existe em {destino}. Use sobrescrever=True para substituir."
        )

    gj_ibge = baixar_malha_ibge(codigo_ibge, qualidade=qualidade)

    # Injeta metadata editorial no properties da feature
    if not gj_ibge.get("features"):
        raise RuntimeError("Malha IBGE veio sem features.")

    metadata_final = dict(metadata)
    metadata_final.setdefault("ibge_code", str(codigo_ibge))
    metadata_final.setdefault("fonte_poligono", f"IBGE API v3 (qualidade={qualidade})")

    gj_ibge["features"][0]["properties"] = metadata_final
    gj_ibge["name"] = nome_slug

    with destino.open("w", encoding="utf-8") as f:
        json.dump(gj_ibge, f, ensure_ascii=False, indent=2)

    logger.info(
        "[OK] AOI %s salva em %s (%d bytes)",
        nome_slug, destino, destino.stat().st_size,
    )
    return destino


# =============================================================================
# Metadata padrão das AOIs deste projeto
# =============================================================================
METADATA_PADRAO: dict[str, dict[str, Any]] = {
    "cambuquira_mg": {
        "nome": "Cambuquira",
        "uf": "MG",
        "ibge_code": "3111606",
        "tipologia": "municipio_rural_pequeno",
        "populacao_2022": 12609,
        "descricao": (
            "Municipio do sul de Minas Gerais, conhecido pelas aguas minerais. "
            "Sede urbana compacta cercada por extensa area rural com propriedades "
            "dispersas. Poligono oficial da malha municipal IBGE 2022."
        ),
    },
    "uberlandia_mg": {
        "nome": "Uberlandia",
        "uf": "MG",
        "ibge_code": "3170206",
        "tipologia": "cidade_media_urbana_consolidada",
        "populacao_2022": 713224,
        "descricao": (
            "Cidade media-grande do Triangulo Mineiro, malha urbana consolidada com "
            "mistura de padroes residenciais horizontais e verticais. Poligono oficial "
            "da malha municipal IBGE 2022 (municipio inteiro, inclui area rural)."
        ),
    },
}
"""Metadata editorial padrão para as AOIs configuradas no projeto.

Uso: ``salvar_aoi_do_ibge(codigo, slug, METADATA_PADRAO[slug])``.
"""
