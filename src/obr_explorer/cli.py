"""Interface de linha de comando: ``obr-explorer``.

**Este módulo será implementado na Fase C.** O esqueleto abaixo já
registra os subcomandos previstos para que o entry point declarado
em ``pyproject.toml`` (``[project.scripts]``) resolva sem erro.

Subcomandos previstos
---------------------

- ``obr-explorer info`` — exibe versão do pacote, configuração atual,
  disponibilidade das extensões DuckDB
- ``obr-explorer aoi list`` — lista AOIs disponíveis em
  ``data/external/aois/``
- ``obr-explorer aoi info --aoi <nome>`` — mostra metadata detalhada
  de uma AOI específica (bounding box, área, população)
- ``obr-explorer analyze --aoi <nome>`` — executa análise completa
  sobre uma AOI, imprime relatório em stdout ou JSON
- ``obr-explorer export --aoi <nome> --format <fgb|geojson|parquet>`` —
  exporta os footprints recortados no formato solicitado
- ``obr-explorer webmap --aoi <nome>`` — gera webmap HTML em
  ``webmap/index.html``

Códigos de saída
----------------

- ``0`` — sucesso
- ``1`` — erro genérico (uso incorreto, etc.)
- ``2`` — erro de rede (S3 inacessível)
- ``3`` — AOI ou arquivo não encontrado
- ``4`` — DuckDB / extensão indisponível

Exemplos
--------

::

    obr-explorer info
    obr-explorer aoi list
    obr-explorer analyze --aoi cambuquira_mg
    obr-explorer analyze --aoi uberlandia_mg --format json > relatorio.json
    obr-explorer webmap --aoi cambuquira_mg
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point da CLI ``obr-explorer``.

    Na Fase A, apenas responde ao subcomando ``info`` mostrando que o
    pacote está instalado corretamente. Os demais subcomandos serão
    implementados a partir da Fase C.
    """
    argv = argv if argv is not None else sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        _print_help()
        return 0

    if argv[0] in ("-v", "--version"):
        from obr_explorer import __version__

        print(f"obr-explorer {__version__}")
        return 0

    if argv[0] == "info":
        return _cmd_info()

    # Subcomandos previstos mas ainda não implementados
    if argv[0] in ("aoi", "analyze", "export", "webmap"):
        print(
            f"[AVISO] Subcomando '{argv[0]}' sera implementado a partir da Fase C. "
            "Este projeto esta atualmente na Fase A (estrutura + esqueleto).",
            file=sys.stderr,
        )
        return 1

    print(f"[ERRO] Subcomando desconhecido: {argv[0]!r}", file=sys.stderr)
    _print_help()
    return 1


def _cmd_info() -> int:
    """Exibe versão do pacote e configuração atual."""
    from obr_explorer import __version__, config

    print(f"obr-explorer {__version__}")
    print()
    print("Configuracao atual:")
    for chave, valor in config.resumo_config().items():
        print(f"  {chave:<25} = {valor}")
    return 0


def _print_help() -> None:
    """Exibe help básico da CLI."""
    print(
        """obr-explorer — Open Buildings Explorer para cidades brasileiras.

Uso:
    obr-explorer <comando> [opcoes]

Comandos:
    info                    Mostra versao e configuracao atual
    aoi list                Lista AOIs disponiveis          (Fase C)
    aoi info --aoi NOME     Mostra metadata de uma AOI      (Fase C)
    analyze --aoi NOME      Executa analise sobre AOI       (Fase C)
    export --aoi NOME ...   Exporta footprints recortados   (Fase C)
    webmap --aoi NOME       Gera webmap HTML                (Fase D)

Flags globais:
    -h, --help              Mostra esta ajuda
    -v, --version           Mostra versao do pacote
"""
    )


if __name__ == "__main__":
    sys.exit(main())
