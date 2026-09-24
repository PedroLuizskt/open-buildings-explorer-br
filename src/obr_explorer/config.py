"""Configuração central: paths, constantes, variáveis de ambiente.

Este módulo é o único lugar do pacote que resolve paths absolutos e lê
variáveis de ambiente. Todos os outros módulos importam daqui, para
manter a fonte da verdade única e facilitar override via ``.env``.

Convenções
----------

- Todas as constantes que podem ser sobrescritas por env var seguem o
  prefixo ``OBR_`` (Open Buildings Explorer)
- Paths são objetos :class:`pathlib.Path` (nunca strings)
- Diretórios de output são criados on-demand por ``ensure_data_dirs()``,
  nunca no import — para evitar side-effects em testes
- ``.env`` é carregado se presente na raiz do projeto, mas nada é
  obrigatório: todos os valores têm defaults sensatos
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# =============================================================================
# Raiz do projeto e .env
# =============================================================================
# ROOT_DIR aponta para a raiz do projeto (dois níveis acima deste arquivo:
# src/obr_explorer/config.py -> src/obr_explorer -> src -> raiz).
ROOT_DIR: Path = Path(__file__).resolve().parents[2]

# Carrega .env da raiz se existir. Silencioso se ausente.
_ENV_FILE = ROOT_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)


# =============================================================================
# Diretórios de dados
# =============================================================================
DATA_DIR: Path = ROOT_DIR / "data"
RAW_DATA_DIR: Path = Path(os.getenv("OBR_DATA_RAW_DIR", DATA_DIR / "raw"))
PROCESSED_DATA_DIR: Path = Path(os.getenv("OBR_DATA_PROCESSED_DIR", DATA_DIR / "processed"))
EXTERNAL_DATA_DIR: Path = DATA_DIR / "external"
AOI_DIR: Path = EXTERNAL_DATA_DIR / "aois"

# Diretório de output do webmap
WEBMAP_DIR: Path = Path(os.getenv("OBR_WEBMAP_DIR", ROOT_DIR / "webmap"))

# Diretório de reports (cobertura, benchmark, etc.)
REPORTS_DIR: Path = ROOT_DIR / "reports"


# =============================================================================
# S3 e endereços do dataset
# =============================================================================
S3_BUCKET_URL: str = os.getenv(
    "OBR_S3_BUCKET_URL",
    "s3://us-west-2.opendata.source.coop/vida/google-microsoft-open-buildings/geoparquet",
)
"""URL base do bucket VIDA com o dataset Google-Microsoft mesclado."""

S3_GOOGLE_URL: str = os.getenv(
    "OBR_S3_GOOGLE_URL",
    "s3://us-west-2.opendata.source.coop/google-research-open-buildings/geoparquet-by-country",
)
"""URL base do bucket Google Open Buildings v3 original (para comparações)."""

S3_REGION: str = os.getenv("OBR_S3_REGION", "us-west-2")
"""Região AWS do bucket público."""


# =============================================================================
# Particionamento do dataset
# =============================================================================
PARTITION_BY_COUNTRY: str = "by_country"
"""Particionamento simples por país (country_iso=XXX)."""

PARTITION_BY_COUNTRY_S2: str = "by_country_s2"
"""Particionamento composto por país + célula S2 (grade hexagonal do Google)."""


# =============================================================================
# Defaults de execução
# =============================================================================
DEFAULT_COUNTRY_ISO: str = os.getenv("OBR_DEFAULT_COUNTRY_ISO", "BRA")
"""Código ISO do país usado como default nas queries."""

DEFAULT_AOI: str = os.getenv("OBR_DEFAULT_AOI", "cambuquira_mg")
"""Nome da AOI usada como default quando a CLI não recebe --aoi."""


# =============================================================================
# Coluna de fonte no dataset
# =============================================================================
# Todo footprint no dataset mesclado tem uma coluna bf_source com o
# valor 'google' ou 'microsoft', que é o que permite a comparação
# central deste projeto.
COLUMN_SOURCE: str = "bf_source"
SOURCE_GOOGLE: str = "google"
SOURCE_MICROSOFT: str = "microsoft"
FONTES_VALIDAS: tuple[str, ...] = (SOURCE_GOOGLE, SOURCE_MICROSOFT)


# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL: str = os.getenv("OBR_LOG_LEVEL", "INFO").upper()
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
LOG_DATE_FORMAT: str = "%H:%M:%S"


def configure_logging(level: str | None = None) -> None:
    """Configura logging root do pacote.

    Idempotente — chamadas repetidas não duplicam handlers. Chamado
    automaticamente pela CLI; se você usa o pacote como biblioteca,
    chame explicitamente uma vez no início do seu script se quiser
    os logs formatados.

    Parameters
    ----------
    level : str, optional
        Nível de log. Se ``None``, usa ``LOG_LEVEL`` (default INFO).
    """
    root_logger = logging.getLogger()
    # Evita duplicar handler em chamadas repetidas
    if any(
        isinstance(h, logging.StreamHandler)
        and h.formatter is not None
        and h.formatter._fmt == LOG_FORMAT
        for h in root_logger.handlers
    ):
        return

    logging.basicConfig(
        level=level or LOG_LEVEL,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
    )


# =============================================================================
# Helpers de criação de diretórios
# =============================================================================
def ensure_data_dirs() -> None:
    """Cria os diretórios de dados se não existirem.

    Chamado on-demand pela CLI e por funções que escrevem em disco.
    Não é chamado no import para evitar side-effects em testes.
    """
    for d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, AOI_DIR, WEBMAP_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Introspecção — útil para CLI 'obr-explorer info' e para debug
# =============================================================================
def resumo_config() -> dict[str, str]:
    """Retorna dict com as configurações atuais, para exibição/debug."""
    return {
        "ROOT_DIR": str(ROOT_DIR),
        "RAW_DATA_DIR": str(RAW_DATA_DIR),
        "PROCESSED_DATA_DIR": str(PROCESSED_DATA_DIR),
        "AOI_DIR": str(AOI_DIR),
        "WEBMAP_DIR": str(WEBMAP_DIR),
        "S3_BUCKET_URL": S3_BUCKET_URL,
        "S3_GOOGLE_URL": S3_GOOGLE_URL,
        "S3_REGION": S3_REGION,
        "DEFAULT_COUNTRY_ISO": DEFAULT_COUNTRY_ISO,
        "DEFAULT_AOI": DEFAULT_AOI,
        "LOG_LEVEL": LOG_LEVEL,
    }
