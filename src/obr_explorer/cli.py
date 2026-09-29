"""Interface de linha de comando: ``obr-explorer``.

Subcomandos disponíveis
-----------------------

- ``obr-explorer info`` — versão + configuração
- ``obr-explorer aoi list`` — lista AOIs disponíveis
- ``obr-explorer aoi info --aoi <nome>`` — metadata de uma AOI
- ``obr-explorer aoi fetch --codigo <IBGE> --nome <slug>`` — baixa
  polígono oficial IBGE e salva como GeoJSON de AOI
- ``obr-explorer analyze --aoi <nome>`` — analisa uma AOI end-to-end
  (baixa footprints do país, recorta pela AOI, imprime resumo)
- ``obr-explorer export --aoi <nome> --format <fgb|geojson>`` —
  exporta os footprints recortados no formato solicitado

Códigos de saída
----------------

- ``0`` — sucesso
- ``1`` — erro genérico (uso incorreto, args inválidos)
- ``2`` — erro de rede (S3 inacessível, API IBGE fora do ar)
- ``3`` — AOI ou arquivo não encontrado
- ``4`` — DuckDB / extensão indisponível

Exemplos
--------

::

    obr-explorer info
    obr-explorer aoi list
    obr-explorer aoi fetch --codigo 3111606 --nome cambuquira_mg --sobrescrever
    obr-explorer analyze --aoi cambuquira_mg
    obr-explorer export --aoi cambuquira_mg --format geojson --output out.geojson
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from obr_explorer import __version__, config


# =============================================================================
# Entry point
# =============================================================================
def main(argv: list[str] | None = None) -> int:
    """Entry point da CLI ``obr-explorer``.

    Parameters
    ----------
    argv : list of str, optional
        Argumentos passados. Se ``None``, usa ``sys.argv[1:]``.

    Returns
    -------
    int
        Código de saída (0=OK, 1-4=erros específicos, ver docstring
        do módulo).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    config.configure_logging(level=args.log_level if hasattr(args, "log_level") else None)
    logger = logging.getLogger("obr_explorer.cli")

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except FileNotFoundError as e:
        logger.error("[ERRO] Arquivo nao encontrado: %s", e)
        return 3
    except (ConnectionError, TimeoutError) as e:
        logger.error("[ERRO] Falha de rede: %s", e)
        return 2
    except RuntimeError as e:
        # Distingue erros de rede (mensagens contêm 'rede', 'HTTP', 'S3')
        # de erros DuckDB / infra
        msg = str(e).lower()
        if any(w in msg for w in ("rede", "http", "s3", "api")):
            logger.error("[ERRO] Falha de rede/API: %s", e)
            return 2
        logger.error("[ERRO] Falha DuckDB: %s", e)
        return 4
    except ValueError as e:
        logger.error("[ERRO] Argumento invalido: %s", e)
        return 1
    except KeyboardInterrupt:
        logger.warning("[AVISO] Interrompido pelo usuario")
        return 1


# =============================================================================
# Parser
# =============================================================================
def _build_parser() -> argparse.ArgumentParser:
    """Constrói o parser argparse principal com subcomandos."""
    parser = argparse.ArgumentParser(
        prog="obr-explorer",
        description=(
            "Open Buildings Explorer para cidades brasileiras. "
            "Analise geoespacial com DuckDB sobre o dataset Google-Microsoft "
            "Open Buildings, com webmap comparativo Google vs Microsoft."
        ),
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--log-level",
        default=config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Nivel de log (default: {config.LOG_LEVEL}).",
    )

    subparsers = parser.add_subparsers(
        title="comandos", dest="command", metavar="<comando>",
    )

    # ---- info -------------------------------------------------------------
    p_info = subparsers.add_parser("info", help="Mostra versao e configuracao atual")
    p_info.set_defaults(func=_cmd_info)

    # ---- aoi --------------------------------------------------------------
    p_aoi = subparsers.add_parser("aoi", help="Gerencia areas de interesse (AOIs)")
    aoi_subs = p_aoi.add_subparsers(dest="aoi_cmd", metavar="<subcomando>")

    p_aoi_list = aoi_subs.add_parser("list", help="Lista AOIs disponiveis")
    p_aoi_list.set_defaults(func=_cmd_aoi_list)

    p_aoi_info = aoi_subs.add_parser("info", help="Mostra metadata de uma AOI")
    p_aoi_info.add_argument("--aoi", required=True, help="Nome (slug) da AOI")
    p_aoi_info.set_defaults(func=_cmd_aoi_info)

    p_aoi_fetch = aoi_subs.add_parser(
        "fetch",
        help="Baixa poligono oficial IBGE e salva como AOI",
    )
    p_aoi_fetch.add_argument(
        "--codigo", required=True,
        help="Codigo IBGE de 7 digitos do municipio (ex: 3111606)",
    )
    p_aoi_fetch.add_argument(
        "--nome", required=True,
        help="Nome/slug da AOI (ex: cambuquira_mg)",
    )
    p_aoi_fetch.add_argument(
        "--qualidade",
        default="maxima",
        choices=["minima", "intermediaria", "maxima"],
        help="Nivel de detalhe geometrico da malha IBGE (default: maxima)",
    )
    p_aoi_fetch.add_argument(
        "--sobrescrever", action="store_true",
        help="Sobrescreve o arquivo se ja existir",
    )
    p_aoi_fetch.set_defaults(func=_cmd_aoi_fetch)

    # ---- analyze ----------------------------------------------------------
    p_analyze = subparsers.add_parser(
        "analyze", help="Analisa uma AOI (baixa, recorta, resume)",
    )
    p_analyze.add_argument("--aoi", required=True, help="Nome (slug) da AOI")
    p_analyze.add_argument(
        "--country-iso", default=config.DEFAULT_COUNTRY_ISO,
        help=f"Codigo ISO-3 do pais (default: {config.DEFAULT_COUNTRY_ISO})",
    )
    p_analyze.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Formato de saida (default: text)",
    )
    p_analyze.set_defaults(func=_cmd_analyze)

    # ---- export -----------------------------------------------------------
    p_export = subparsers.add_parser(
        "export", help="Exporta footprints recortados por AOI",
    )
    p_export.add_argument("--aoi", required=True, help="Nome (slug) da AOI")
    p_export.add_argument(
        "--country-iso", default=config.DEFAULT_COUNTRY_ISO,
        help=f"Codigo ISO-3 do pais (default: {config.DEFAULT_COUNTRY_ISO})",
    )
    p_export.add_argument(
        "--format", choices=["geojson", "fgb"], default="geojson",
        help="Formato de saida (default: geojson)",
    )
    p_export.add_argument(
        "--output", type=Path, default=None,
        help="Caminho do arquivo de saida (default: data/processed/<aoi>.<ext>)",
    )
    p_export.set_defaults(func=_cmd_export)

    return parser


# =============================================================================
# Handlers dos subcomandos
# =============================================================================
def _cmd_info(args: argparse.Namespace) -> int:
    """Mostra versão e configuração atual."""
    print(f"obr-explorer {__version__}")
    print()
    print("Configuracao atual:")
    for chave, valor in config.resumo_config().items():
        print(f"  {chave:<25} = {valor}")
    return 0


def _cmd_aoi_list(args: argparse.Namespace) -> int:
    """Lista AOIs disponíveis."""
    from obr_explorer import aoi as aoi_mod

    aois = aoi_mod.listar_aois()
    if not aois:
        print(f"Nenhuma AOI encontrada em {config.AOI_DIR}")
        print()
        print("Adicione GeoJSONs manualmente ou use:")
        print("  obr-explorer aoi fetch --codigo <IBGE> --nome <slug>")
        return 0

    print(f"AOIs disponiveis ({len(aois)}):")
    print()
    for a in aois:
        props = a["properties"]
        nome_exib = props.get("nome", a["nome"])
        uf = props.get("uf", "")
        pop = props.get("populacao_2022", "?")
        tipo = props.get("tipologia", "?")
        print(f"  {a['nome']}")
        print(f"    Nome:        {nome_exib}{'/' + uf if uf else ''}")
        print(f"    Tipologia:   {tipo}")
        print(f"    Populacao:   {pop}")
    return 0


def _cmd_aoi_info(args: argparse.Namespace) -> int:
    """Mostra metadata detalhada de uma AOI."""
    from obr_explorer import aoi as aoi_mod

    a = aoi_mod.carregar_aoi(args.aoi)
    print(f"AOI: {a.nome_exibicao}")
    print(f"Slug: {a.nome}")
    print(f"Arquivo: {a.path}")
    print(f"Bounds (WGS84): {tuple(round(x, 4) for x in a.bounds)}")
    print(f"Area aproximada (bbox): {a.area_km2_aproximada:.1f} km2")
    print()
    print("Metadata:")
    for k, v in a.properties.items():
        print(f"  {k}: {v}")
    return 0


def _cmd_aoi_fetch(args: argparse.Namespace) -> int:
    """Baixa polígono oficial IBGE e salva como AOI."""
    from obr_explorer import aoi as aoi_mod

    # Se o nome_slug bate com uma AOI padrão configurada, usa metadata dela
    metadata = aoi_mod.METADATA_PADRAO.get(args.nome, {
        "nome": args.nome,
        "ibge_code": args.codigo,
    })
    metadata["ibge_code"] = args.codigo  # sempre reflete o codigo passado

    destino = aoi_mod.salvar_aoi_do_ibge(
        codigo_ibge=args.codigo,
        nome_slug=args.nome,
        metadata=metadata,
        qualidade=args.qualidade,
        sobrescrever=args.sobrescrever,
    )
    print(f"[OK] AOI salva em: {destino}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Analisa uma AOI end-to-end."""
    from obr_explorer import analysis
    from obr_explorer import aoi as aoi_mod
    from obr_explorer import duckdb_client as ddb

    # 1. Carregar AOI
    a = aoi_mod.carregar_aoi(args.aoi)

    # 2. Setup DuckDB
    con = ddb.criar_conexao()
    ddb.instalar_extensoes(con)
    ddb.configurar_s3(con)

    # 3. Carregar footprints do país
    tabela_pais = f"footprints_{args.country_iso.lower()}"
    ddb.carregar_pais(con, country_iso=args.country_iso, tabela=tabela_pais)

    # 4. Carregar AOI e recortar
    tabela_aoi = f"aoi_{args.aoi}"
    tabela_recorte = f"recorte_{args.aoi}"
    ddb.carregar_aoi_geojson(con, a.path, tabela_aoi)
    ddb.recortar_por_aoi(
        con,
        tabela_footprints=tabela_pais,
        tabela_aoi=tabela_aoi,
        tabela_recorte=tabela_recorte,
    )

    # 5. Resumir
    _, miny, _, maxy = a.bounds
    lat_media = (miny + maxy) / 2
    resumo = analysis.resumo_aoi(
        con, tabela_recorte, aoi_nome=a.nome_exibicao, lat_media=lat_media,
    )

    # 6. Saida
    if args.format == "json":
        print(json.dumps(resumo.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(analysis.formatar_resumo_texto(resumo))

    con.close()
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Exporta footprints recortados em formato geoespacial."""
    from obr_explorer import aoi as aoi_mod
    from obr_explorer import duckdb_client as ddb

    a = aoi_mod.carregar_aoi(args.aoi)

    # Resolver output path
    if args.output is None:
        config.ensure_data_dirs()
        ext = "geojson" if args.format == "geojson" else "fgb"
        output = config.PROCESSED_DATA_DIR / f"{args.aoi}.{ext}"
    else:
        output = args.output

    # Pipeline
    con = ddb.criar_conexao()
    ddb.instalar_extensoes(con)
    ddb.configurar_s3(con)

    tabela_pais = f"footprints_{args.country_iso.lower()}"
    ddb.carregar_pais(con, country_iso=args.country_iso, tabela=tabela_pais)

    tabela_aoi = f"aoi_{args.aoi}"
    tabela_recorte = f"recorte_{args.aoi}"
    ddb.carregar_aoi_geojson(con, a.path, tabela_aoi)
    ddb.recortar_por_aoi(
        con,
        tabela_footprints=tabela_pais,
        tabela_aoi=tabela_aoi,
        tabela_recorte=tabela_recorte,
    )

    # Export
    if args.format == "geojson":
        path = ddb.exportar_geojson(con, tabela_recorte, output)
    else:
        path = ddb.exportar_flatgeobuf(con, tabela_recorte, output)

    print(f"[OK] Exportado para: {path}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
