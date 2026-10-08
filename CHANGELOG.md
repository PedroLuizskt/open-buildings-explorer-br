# Changelog

Todas as mudanças notáveis neste projeto são documentadas aqui, no formato
inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

O projeto segue versionamento semântico ([SemVer](https://semver.org/lang/pt-BR/)):
- **MAJOR** (`X.0.0`): mudanças incompatíveis na API pública
- **MINOR** (`0.X.0`): novas funcionalidades mantendo compatibilidade
- **PATCH** (`0.0.X`): correções de bug mantendo compatibilidade

## [0.5.0] — 2026-10-08

### Adicionado
- Webmap reformulado como **multi-AOI** com switcher dropdown no painel lateral,
  tabs (Visão Geral / Análise / Detalhe), KPIs, gráficos Chart.js (donut
  Google × Microsoft, histograma de áreas por bucket), narrativa interpretativa
  gerada no cliente e popups ricos com área em m²/hectares (ADR-012)
- Novo subcomando `obr-explorer webmap` com flag `--aoi` repetível (ou sem
  flag para incluir todas as AOIs disponíveis em um único HTML)
- Novo subcomando `obr-explorer db-info` mostra tamanho e tabelas do banco DuckDB
- Novo subcomando `obr-explorer db-prune` descarta tabelas pesadas
  `footprints_<iso>` mantendo recortes (libera ~35-40 GB)
- Novo subcomando `obr-explorer db-compact` compacta banco após prune,
  recuperando espaço em disco que `DROP TABLE` marcou como livre mas não
  devolveu ao SO
- GeoJSONs exportados agora enriquecidos com `area_m2` por feature
- Design visual: fontes Barlow Condensed + Karla, paleta dark rica,
  loading screen com spinner
- Workflow GitHub Actions `.github/workflows/pages.yml` para deploy
  automático do webmap em GitHub Pages
- Notebook demonstrativo `notebooks/01_demonstrativo.ipynb` percorrendo
  a API Python sem passar pela CLI
- `CHANGELOG.md`, `CITATION.cff` e seção de template de post LinkedIn
  em `docs/LINKEDIN_POST.md`

### Alterado
- README reorganizado com badges, screenshots embutidos, seções de
  gerenciamento de disco e instruções GitHub Pages
- `_criar_subset_por_fonte` evoluiu para `_criar_subset_por_fonte_enriquecido`
  que inclui coluna `area_m2` calculada via `ST_Area` ajustada por latitude

### Documentação
- ADR-012: Webmap multi-AOI com dashboard analítico
- ADR-013: Encerramento do projeto e checklist de produção

## [0.4.0] — 2026-10-07

### Adicionado
- Módulo `webmap.py` original com Leaflet autocontido, Canvas renderer
  para performance, decimação opcional via `--min-area-m2` e
  `--simplify-tolerance` (ADR-011)
- Flags `--pular-carga` e `--db-path` no `webmap` para iteração visual
  rápida reusando banco DuckDB persistente

## [0.3.0] — 2026-09-29

### Adicionado
- Módulo `aoi.py` completo: `AOI` dataclass, `listar_aois`, `carregar_aoi`,
  `validar_geojson_aoi`, `baixar_malha_ibge` (API v3 IBGE),
  `salvar_aoi_do_ibge` com `METADATA_PADRAO`
- Módulo `analysis.py`: dataclasses `ResumoAOI` e `ComparacaoAOIs`,
  funções `contar_total`, `contar_por_fonte`, `area_total_por_fonte`,
  `resumo_aoi`, `comparar_aois` + formatação texto para CLI
- CLI expandida com subcomandos `info`, `aoi list/info/fetch`, `analyze`,
  `export`
- Substituição das bounding boxes iniciais pelos **polígonos oficiais
  IBGE 2022 (BC250)** extraídos dos shapefiles via QGIS, reprojetados
  SIRGAS 2000 → WGS84 (ADR-009)
- Correção do bug de gzip em `baixar_malha_ibge` (API IBGE retorna
  payload comprimido sem declarar `Content-Encoding`)
- `encoding='utf-8'` explícito em todas as chamadas `.open()`
  com teste de regressão AST-based (ADR-010)

### Corrigido
- `METADATA_PADRAO`: código IBGE de Cambuquira era `3111606` (errado),
  correto é `3110707`

## [0.2.0] — 2026-09-28

### Adicionado
- Módulo `duckdb_client.py` completo: conexão + extensões (`httpfs` +
  `spatial`) + queries base parametrizadas por país/AOI, recorte espacial,
  exportação FlatGeobuf/GeoJSON, introspecção
- `configurar_s3` com `s3_url_style='path'` por default (resolve problema
  SSL de bucket com pontos no nome — ADR-008)
- Normalização de CRS via `ST_SetCRS` em `recortar_por_aoi` (resolve
  conflito EPSG:4326 vs OGC:CRS84 em versões recentes da extensão spatial)
- Dependência explícita `certifi>=2024.0` + configuração automática de
  `ca_cert_file` para validação SSL no Windows (ADR-007)

## [0.1.0] — 2026-09-23

### Adicionado
- Estrutura inicial CCDS v2 com `src`-layout
- `pyproject.toml` com hatchling, entry point `obr-explorer`
- Configuração `config.py`, `Makefile` + `tasks.ps1`
- Documentação inicial: `README.md`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md` (ADRs 001-006)
- GeoJSONs bounding box iniciais de Cambuquira/MG e Uberlândia/MG
- Testes smoke validando estrutura, imports, config, GeoJSONs, CLI
