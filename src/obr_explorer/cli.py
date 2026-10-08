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

    # ---- webmap -----------------------------------------------------------
    p_webmap = subparsers.add_parser(
        "webmap",
        help="Gera webmap HTML multi-AOI com dashboard (dropdown switcher)",
    )
    p_webmap.add_argument(
        "--aoi", action="append", default=None,
        help=(
            "Nome (slug) da AOI. Repita o flag para incluir multiplas AOIs no "
            "mesmo webmap (ex: --aoi cambuquira_mg --aoi uberlandia_mg). "
            "Se omitido, usa todas as AOIs em data/external/aois/."
        ),
    )
    p_webmap.add_argument(
        "--country-iso", default=config.DEFAULT_COUNTRY_ISO,
        help=f"Codigo ISO-3 do pais (default: {config.DEFAULT_COUNTRY_ISO})",
    )
    p_webmap.add_argument(
        "--output-dir", type=Path, default=None,
        help="Diretorio de saida (default: ./webmap/)",
    )
    p_webmap.add_argument(
        "--min-area-m2", type=float, default=None,
        help=(
            "Descarta footprints menores que N m2 antes de exportar. "
            "Recomendado para AOIs grandes (ex: --min-area-m2 30 para Uberlandia)."
        ),
    )
    p_webmap.add_argument(
        "--simplify-tolerance", type=float, default=None,
        help=(
            "Tolerancia de simplificacao geometrica em graus (ex: 1e-5 ~= 1m). "
            "Reduz vertices por poligono. Opcional."
        ),
    )
    p_webmap.add_argument(
        "--pular-carga",
        action="store_true",
        help=(
            "Pula download+recorte e reusa tabelas 'recorte_<aoi>' ja "
            "existentes em arquivo DuckDB persistente. Usar com --db-path."
        ),
    )
    p_webmap.add_argument(
        "--db-path", type=Path, default=None,
        help=(
            "Caminho para arquivo .duckdb persistente. Se passado, usa esse "
            "banco em vez de in-memory. Util para evitar re-baixar o pais a "
            "cada regeneracao do webmap durante iteracao visual."
        ),
    )
    p_webmap.set_defaults(func=_cmd_webmap)

    # ---- db-info ----------------------------------------------------------
    p_db_info = subparsers.add_parser(
        "db-info",
        help="Mostra tamanho do banco DuckDB e tabelas disponiveis",
    )
    p_db_info.add_argument(
        "--db-path", type=Path, required=True,
        help="Caminho para arquivo .duckdb",
    )
    p_db_info.set_defaults(func=_cmd_db_info)

    # ---- db-prune ---------------------------------------------------------
    p_db_prune = subparsers.add_parser(
        "db-prune",
        help=(
            "Descarta tabelas pesadas (footprints_<pais>) mantendo recortes "
            "e AOIs. Reduz drasticamente o tamanho do banco."
        ),
    )
    p_db_prune.add_argument(
        "--db-path", type=Path, required=True,
        help="Caminho para arquivo .duckdb",
    )
    p_db_prune.add_argument(
        "--sim", action="store_true",
        help="Confirmacao explicita. Sem este flag, apenas lista o que seria removido.",
    )
    p_db_prune.set_defaults(func=_cmd_db_prune)

    # ---- db-compact -------------------------------------------------------
    p_db_compact = subparsers.add_parser(
        "db-compact",
        help=(
            "Compacta banco DuckDB apos db-prune. Copia tabelas restantes "
            "para novo arquivo e substitui o original. Recupera o espaco em "
            "disco que DROP TABLE marcou como livre mas nao devolveu ao SO."
        ),
    )
    p_db_compact.add_argument(
        "--db-path", type=Path, required=True,
        help="Caminho para arquivo .duckdb a compactar",
    )
    p_db_compact.add_argument(
        "--sim", action="store_true",
        help=(
            "Confirmacao explicita. Sem este flag, apenas estima o ganho "
            "de espaco e nao modifica nada."
        ),
    )
    p_db_compact.set_defaults(func=_cmd_db_compact)

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


def _cmd_webmap(args: argparse.Namespace) -> int:
    """Gera webmap HTML multi-AOI com dashboard analitico.

    Fluxo:

    1. Resolve lista de AOIs (de ``--aoi`` repetido ou de todas disponiveis)
    2. Setup DuckDB (in-memory ou persistente)
    3. [opcional, pode pular com --pular-carga] baixa footprints + recorta
       cada AOI
    4. Chama webmap.gerar_webmap_multi com todas as AOIs juntas

    Com ``--db-path`` + ``--pular-carga``, reusa tabelas de recorte existentes
    em banco DuckDB persistente — essencial para iteracao visual sem
    re-baixar 141M footprints a cada run.
    """
    from obr_explorer import aoi as aoi_mod
    from obr_explorer import duckdb_client as ddb
    from obr_explorer import webmap as webmap_mod

    # Resolve lista de AOIs
    if args.aoi:
        slugs = args.aoi
    else:
        disponiveis = aoi_mod.listar_aois()
        slugs = [a["nome"] for a in disponiveis]
        if not slugs:
            print("[ERRO] Nenhuma AOI em data/external/aois/", file=sys.stderr)
            return 3

    aois_carregadas = [aoi_mod.carregar_aoi(slug) for slug in slugs]

    # Conexao
    if args.db_path:
        con = ddb.criar_conexao(in_memory=False, database_path=args.db_path)
    else:
        con = ddb.criar_conexao()
    ddb.instalar_extensoes(con)
    ddb.configurar_s3(con)

    tabela_pais = f"footprints_{args.country_iso.lower()}"

    # Fase 1: carrega pais uma unica vez (se nao pular-carga)
    if not args.pular_carga:
        ddb.carregar_pais(con, country_iso=args.country_iso, tabela=tabela_pais)

    # Fase 2: para cada AOI, carrega + recorta (ou verifica se ja existe)
    aois_e_tabelas = []
    for a in aois_carregadas:
        tabela_aoi = f"aoi_{a.nome}"
        tabela_recorte = f"recorte_{a.nome}"

        if not args.pular_carga:
            ddb.carregar_aoi_geojson(con, a.path, tabela_aoi)
            ddb.recortar_por_aoi(
                con,
                tabela_footprints=tabela_pais,
                tabela_aoi=tabela_aoi,
                tabela_recorte=tabela_recorte,
            )
        else:
            tabelas = ddb.listar_tabelas(con)
            if tabela_recorte not in tabelas:
                print(
                    f"[ERRO] --pular-carga foi passado mas a tabela "
                    f"{tabela_recorte!r} nao existe no banco {args.db_path}. "
                    f"Rode uma vez sem --pular-carga para popular.",
                    file=sys.stderr,
                )
                con.close()
                return 3

        aois_e_tabelas.append((a, tabela_recorte))

    # Fase 3: gera webmap unico com todas as AOIs
    output_html = webmap_mod.gerar_webmap_multi(
        con,
        aois_e_tabelas=aois_e_tabelas,
        output_dir=args.output_dir,
        min_area_m2=args.min_area_m2,
        simplify_tolerance=args.simplify_tolerance,
    )

    print(f"[OK] Webmap gerado: {output_html}")
    print(f"     AOIs incluidas: {', '.join(a.nome_exibicao for a in aois_carregadas)}")
    print(f"     Abra no navegador ou sirva com:")
    print(f"       python -m http.server 8000 --directory {output_html.parent}")
    con.close()
    return 0


def _cmd_db_info(args: argparse.Namespace) -> int:
    """Mostra tamanho do banco DuckDB e tabelas disponiveis.

    Util para entender o que esta ocupando os GBs do arquivo .duckdb.
    O cache do pais (footprints_<iso>) sozinho pode ocupar 30-40 GB.
    """
    from obr_explorer import duckdb_client as ddb

    db_path = args.db_path
    if not db_path.exists():
        print(f"[ERRO] Banco DuckDB nao encontrado: {db_path}", file=sys.stderr)
        return 3

    size_bytes = db_path.stat().st_size
    size_gb = size_bytes / (1024 ** 3)

    print(f"Banco DuckDB: {db_path}")
    print(f"Tamanho em disco: {size_gb:.2f} GB ({size_bytes:,} bytes)")
    print()

    con = ddb.criar_conexao(in_memory=False, database_path=db_path)
    tabelas = ddb.listar_tabelas(con)
    if not tabelas:
        print("Banco vazio (nenhuma tabela).")
        con.close()
        return 0

    print(f"Tabelas ({len(tabelas)}):")
    for t in sorted(tabelas):
        try:
            n = ddb.contar_registros(con, t)
            print(f"  {t:<40} {n:>15,} linhas")
        except Exception as e:
            print(f"  {t:<40} (erro: {e})")

    print()
    pesadas = [t for t in tabelas if t.startswith("footprints_") and not t.startswith("footprints_cambuquira") and not t.startswith("footprints_uberlandia")]
    if pesadas:
        print(f"Para liberar espaco, descarte tabelas pesadas (footprints_<pais>):")
        print(f"  obr-explorer db-prune --db-path {db_path} --sim")
    con.close()
    return 0


def _cmd_db_prune(args: argparse.Namespace) -> int:
    """Remove tabelas pesadas (footprints_<pais>) mantendo recortes.

    O cache do pais inteiro (ex: footprints_bra com 141M linhas) ocupa
    30-40 GB. As tabelas de recorte (recorte_<aoi>) ocupam alguns MB e
    sao suficientes para re-gerar o webmap sem re-baixar o pais.

    Padrao de nomes:
    - footprints_<iso3>  : REMOVIDO (ex: footprints_bra)
    - aoi_<slug>         : mantido (poligono da AOI)
    - recorte_<slug>     : mantido (footprints recortados pela AOI)
    - recorte_<slug>_fonte_<fonte> : mantido (subset por fonte)
    """
    from obr_explorer import duckdb_client as ddb

    db_path = args.db_path
    if not db_path.exists():
        print(f"[ERRO] Banco DuckDB nao encontrado: {db_path}", file=sys.stderr)
        return 3

    con = ddb.criar_conexao(in_memory=False, database_path=db_path)
    tabelas = ddb.listar_tabelas(con)

    # Identifica tabelas pesadas: footprints_<iso3> com 2 ou 3 letras
    # (BRA, LSO, AUS, USA etc). Nao remove recortes nem aoi.
    import re as _re
    padrao = _re.compile(r"^footprints_[a-z]{2,3}$")
    alvos = [t for t in tabelas if padrao.match(t)]

    if not alvos:
        print("Nenhuma tabela pesada (footprints_<iso>) para remover.")
        con.close()
        return 0

    print(f"Tabelas que seriam removidas ({len(alvos)}):")
    for t in alvos:
        try:
            n = ddb.contar_registros(con, t)
            print(f"  {t:<40} {n:>15,} linhas")
        except Exception as e:
            print(f"  {t:<40} (erro: {e})")

    if not args.sim:
        print()
        print(f"Esta operacao e destrutiva. Para confirmar, rode novamente com --sim:")
        print(f"  obr-explorer db-prune --db-path {db_path} --sim")
        con.close()
        return 0

    print()
    print("Removendo tabelas...")
    for t in alvos:
        con.execute(f"DROP TABLE IF EXISTS {t};")
        print(f"  [OK] {t} removida")

    # DuckDB nao libera disco automaticamente apos DROP — precisamos de VACUUM/CHECKPOINT
    print()
    print("Executando CHECKPOINT para liberar espaco em disco...")
    con.execute("CHECKPOINT;")
    con.close()

    size_bytes = db_path.stat().st_size
    print(f"[OK] Tamanho final do banco: {size_bytes / (1024**3):.2f} GB")
    print(f"     Para pequenos reducoes, considere refazer o banco do zero.")
    return 0


def _cmd_db_compact(args: argparse.Namespace) -> int:
    """Compacta banco DuckDB apos db-prune.

    DuckDB nao devolve espaco ao SO apos DROP TABLE — marca paginas como
    livres mas o arquivo mantem o tamanho. Para liberar de verdade,
    copiamos as tabelas restantes para um novo arquivo e substituimos
    o original.

    Fluxo:
    1. Lista tabelas do banco original
    2. Estima ganho de espaco (dry-run) OU
       cria novo arquivo com EXPORT DATABASE + IMPORT DATABASE
    3. Substitui o original pelo novo (apenas com --sim)
    """
    import shutil
    import tempfile

    from obr_explorer import duckdb_client as ddb

    db_path = args.db_path
    if not db_path.exists():
        print(f"[ERRO] Banco DuckDB nao encontrado: {db_path}", file=sys.stderr)
        return 3

    size_antes = db_path.stat().st_size
    size_antes_gb = size_antes / (1024 ** 3)

    con = ddb.criar_conexao(in_memory=False, database_path=db_path)
    tabelas = ddb.listar_tabelas(con)
    con.close()

    if not tabelas:
        print(f"Banco vazio ({size_antes_gb:.2f} GB). Nada para compactar.")
        return 0

    print(f"Banco atual: {db_path}")
    print(f"Tamanho antes: {size_antes_gb:.2f} GB")
    print(f"Tabelas a preservar ({len(tabelas)}):")
    for t in sorted(tabelas):
        print(f"  {t}")
    print()

    if not args.sim:
        print(f"Para compactar de verdade, rode novamente com --sim:")
        print(f"  obr-explorer db-compact --db-path {db_path} --sim")
        print()
        print(f"Operacao: criar novo banco, copiar tabelas acima via")
        print(f"EXPORT/IMPORT DATABASE, substituir arquivo original.")
        print(f"Backup e feito automaticamente em {db_path}.bak")
        return 0

    # Gera NOME de arquivo temporario sem criar — DuckDB nao aceita abrir
    # arquivo preexistente que nao seja banco valido. Usa uuid para unicidade.
    import uuid
    novo_path = db_path.parent / f"__compact_{uuid.uuid4().hex[:8]}.duckdb"
    export_dir = Path(tempfile.mkdtemp(prefix="duckdb_export_", dir=db_path.parent))

    try:
        # Exporta tudo do banco original para o diretorio temporario
        print(f"[1/4] Exportando dados do banco original...")
        con_orig = ddb.criar_conexao(in_memory=False, database_path=db_path)
        con_orig.execute(f"EXPORT DATABASE '{str(export_dir).replace(chr(92), '/')}' (FORMAT PARQUET)")
        con_orig.close()

        # Importa para novo banco
        print(f"[2/4] Importando para novo banco compactado...")
        con_novo = ddb.criar_conexao(in_memory=False, database_path=novo_path)
        con_novo.execute(f"IMPORT DATABASE '{str(export_dir).replace(chr(92), '/')}'")
        con_novo.close()

        size_novo = novo_path.stat().st_size
        size_novo_gb = size_novo / (1024 ** 3)

        # Backup e substitui
        backup_path = db_path.with_suffix(db_path.suffix + ".bak")
        print(f"[3/4] Fazendo backup do original em {backup_path.name}...")
        if backup_path.exists():
            backup_path.unlink()
        shutil.move(str(db_path), str(backup_path))

        print(f"[4/4] Substituindo original pelo compactado...")
        shutil.move(str(novo_path), str(db_path))

        print()
        print(f"[OK] Compactacao concluida.")
        print(f"     Antes:   {size_antes_gb:.2f} GB")
        print(f"     Depois:  {size_novo_gb:.2f} GB")
        print(f"     Ganho:   {(size_antes - size_novo) / (1024**3):.2f} GB")
        print()
        print(f"     Backup do original em: {backup_path}")
        print(f"     Se tudo funcionar, pode remover o backup:")
        print(f"       Remove-Item {backup_path}")
    finally:
        # Limpa diretorio de export
        if export_dir.exists():
            shutil.rmtree(export_dir, ignore_errors=True)
        # Limpa novo_path se ainda existir (falha antes de mover)
        if novo_path.exists():
            try:
                novo_path.unlink()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
