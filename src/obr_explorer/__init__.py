"""obr_explorer — Open Buildings Explorer para cidades brasileiras.

Análise geoespacial em escala de bilhões de linhas com DuckDB sobre o dataset
Google-Microsoft Open Buildings, com foco em cidades brasileiras e geração de
webmap comparativo entre as fontes Google e Microsoft.

Ponto de entrada principal
--------------------------

O uso típico deste pacote é através da CLI, disponível como comando
``obr-explorer`` após instalação com ``pip install -e .``::

    obr-explorer aoi list                       # ver AOIs disponíveis
    obr-explorer analyze --aoi cambuquira_mg    # analisar uma AOI
    obr-explorer webmap --aoi cambuquira_mg     # gerar webmap HTML

A CLI é implementada em :mod:`obr_explorer.cli` (Fase C).

Uso programático
----------------

Também é possível usar o pacote como biblioteca::

    from obr_explorer import config
    from obr_explorer.duckdb_client import criar_conexao         # (Fase B)
    from obr_explorer.aoi import carregar_aoi                    # (Fase C)
    from obr_explorer.analysis import comparar_fontes            # (Fase C)
    from obr_explorer.webmap import gerar_webmap_comparativo     # (Fase D)

Módulos
-------

- ``obr_explorer.config`` — paths, constantes, variáveis de ambiente
- ``obr_explorer.duckdb_client`` — conexão DuckDB + extensões + queries base (Fase B)
- ``obr_explorer.aoi`` — gerenciamento de áreas de interesse (Fase C)
- ``obr_explorer.analysis`` — queries analíticas de negócio (Fase C)
- ``obr_explorer.webmap`` — gerador de HTML Leaflet interativo (Fase D)
- ``obr_explorer.cli`` — interface de linha de comando (Fase C)
"""

__version__ = "0.6.1"

# Reexporta dataclasses e funcoes principais para permitir
#   from obr_explorer import AOI, ResumoAOI
from obr_explorer.aoi import AOI  # noqa: E402
from obr_explorer.analysis import ComparacaoAOIs, ResumoAOI  # noqa: E402

__all__ = ["__version__", "AOI", "ResumoAOI", "ComparacaoAOIs"]
