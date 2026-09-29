# open-buildings-explorer-br

**Análise geoespacial em escala de bilhões de linhas com DuckDB sobre o dataset Google-Microsoft Open Buildings, com foco em cidades brasileiras e webmap comparativo Google vs Microsoft.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![DuckDB 1.3+](https://img.shields.io/badge/DuckDB-1.3%2B-yellow.svg)](https://duckdb.org/)
[![Status: em desenvolvimento](https://img.shields.io/badge/status-em%20desenvolvimento-orange.svg)]()

---

## O que este projeto faz

Consulta e analisa o **[Google-Microsoft Open Buildings Dataset](https://beta.source.coop/repositories/vida/google-microsoft-open-buildings/description/)** — o mais completo dataset aberto de footprints de edificações do mundo, com **2.534.595.270 edificações** cobrindo 92% das fronteiras administrativas globais — usando **DuckDB** com as extensões `httpfs` (leitura direta de S3) e `spatial` (SQL geoespacial).

Foca em duas cidades brasileiras de tipologias contrastantes — **Cambuquira/MG** (rural, ~13 mil habitantes) e **Uberlândia/MG** (média urbana consolidada, ~700 mil habitantes) — e produz um **webmap comparativo** que permite ao usuário alternar entre a camada Google e a camada Microsoft, com painel lateral mostrando contagens e estatísticas por fonte.

O paradigma central é **zero-copy analytics**: os dados ficam na nuvem (bucket S3 público `us-west-2.opendata.source.coop`), o processamento roda localmente com DuckDB, e nenhum download prévio dos ~140 milhões de edificações do Brasil é necessário — apenas os subconjuntos recortados pelas AOIs de interesse são materializados em disco.

## Por que DuckDB para este problema

Antes do DuckDB, análise geoespacial sobre datasets desse porte exigia uma de duas opções: (a) infraestrutura Spark/PostGIS em cluster, com custo e complexidade operacional altos, ou (b) baixar tudo localmente e processar com GeoPandas, o que consome dezenas de GB de disco e é lento por não usar paralelismo natural. DuckDB muda essa equação:

- **In-process analytics** — biblioteca embutida no Python, sem servidor
- **Vetorização automática** — usa SIMD e paralelismo por padrão
- **Leitura direta de Parquet em S3** via extensão `httpfs`, com predicate pushdown que baixa apenas os blocos relevantes
- **SQL espacial completo** via extensão `spatial` (funções `ST_*` compatíveis com PostGIS)
- **Zero configuração** — `pip install duckdb` e pronto

Uma query que compara cobertura Google vs Microsoft em uma AOI brasileira, sobre os 140 milhões de footprints do Brasil, executa em segundos na máquina local sem baixar o dataset inteiro.

## Estrutura do repositório

```
open-buildings-explorer-br/
├── README.md                     # este arquivo
├── LICENSE                       # MIT
├── pyproject.toml                # metadata, deps, entrypoints, ferramentas
├── Makefile                      # atalhos Unix
├── tasks.ps1                     # atalhos Windows/PowerShell
├── .env.example                  # template de variáveis de ambiente
│
├── src/obr_explorer/             # pacote principal
│   ├── __init__.py               # API pública
│   ├── config.py                 # paths, constantes, env vars
│   ├── duckdb_client.py          # conexão + extensões + queries base   (Fase B)
│   ├── aoi.py                    # gerenciamento de áreas de interesse   (Fase C)
│   ├── analysis.py               # queries de negócio                    (Fase C)
│   ├── webmap.py                 # gerador de HTML Leaflet interativo    (Fase D)
│   └── cli.py                    # interface de linha de comando         (Fase C)
│
├── tests/                        # suíte pytest
│   ├── conftest.py               # fixtures compartilhadas
│   └── test_smoke.py             # testes de estrutura e imports
│
├── data/
│   ├── raw/                      # dados baixados (ignorado no git)
│   ├── processed/                # análises materializadas (ignorado)
│   └── external/aois/            # GeoJSONs das AOIs (versionados)
│       ├── cambuquira_mg.geojson
│       └── uberlandia_mg.geojson
│
├── notebooks/                    # notebook demonstrativo end-to-end     (Fase E)
├── docs/                         # documentação técnica adicional
│   ├── ARCHITECTURE.md
│   └── DECISIONS.md
├── webmap/                       # webmap HTML gerado (servido via Pages)
└── reports/                      # cobertura e outros relatórios
```

## Instalação

**Pré-requisitos**: Python 3.11+ e um dos gerenciadores de venv (venv nativo, conda ou uv).

### Usando venv nativo

```bash
# Clonar
git clone https://github.com/PedroLuizskt/open-buildings-explorer-br.git
cd open-buildings-explorer-br

# Ambiente virtual
python -m venv .venv
source .venv/bin/activate            # Linux/Mac
# .\.venv\Scripts\Activate.ps1       # Windows PowerShell

# Instalação em modo editável com extras dev + notebook
pip install -e ".[dev,notebook]"
```

### Usando os atalhos do projeto

```powershell
# Windows PowerShell
.\tasks.ps1 setup

# Unix/Mac
make setup
```

Ambos criam o venv, instalam o pacote em modo editável com todos os extras, e rodam a suíte inicial para confirmar que a instalação está saudável.

## Uso rápido

*(As seções abaixo serão preenchidas conforme as fases avançam. Marcação `[Fase X]` indica quando cada capacidade fica disponível.)*

### Explorar uma AOI brasileira `[Fase C]`

```bash
# Ver AOIs disponíveis
obr-explorer aoi list

# Executar análise sobre Cambuquira
obr-explorer analyze --aoi cambuquira_mg

# Executar análise sobre Uberlândia
obr-explorer analyze --aoi uberlandia_mg
```

### Gerar webmap comparativo `[Fase D]`

```bash
# Gera o HTML interativo em webmap/index.html
obr-explorer webmap --aoi cambuquira_mg
obr-explorer webmap --aoi uberlandia_mg

# Servir localmente para preview
python -m http.server 8000 --directory webmap
# Abrir http://localhost:8000
```

O webmap resultante inclui:

- Camada base OpenStreetMap
- Toggle entre camadas **Google Open Buildings** e **Microsoft Building Footprints**
- Painel lateral com contagens por fonte e área total edificada
- Popup ao clicar em cada footprint mostrando fonte, área em metros quadrados e confidence score
- Legenda com cor distinta por fonte

### Publicação via GitHub Pages `[Fase E]`

Após gerar o webmap localmente, um push do diretório `webmap/` para a branch `gh-pages` publica automaticamente em `https://pedroluizskt.github.io/open-buildings-explorer-br/`.

## Comandos de desenvolvimento

Todos os comandos abaixo funcionam via `.\tasks.ps1 <cmd>` no Windows ou `make <cmd>` no Unix.

| Comando | Descrição |
|---------|-----------|
| `setup` | Cria venv, instala pacote em modo editável com extras |
| `test` | Roda suíte pytest offline com cobertura |
| `test-network` | Roda testes que dependem de acesso ao S3 público |
| `lint` | Executa ruff check sobre o código |
| `format` | Aplica ruff format |
| `notebook` | Sobe Jupyter Lab na pasta `notebooks/` |
| `clean` | Remove artefatos de build, cache e cobertura |

## O dataset

O **Google-Microsoft Open Buildings** é uma mesclagem publicada pelo VIDA (Vault Institute for Data Analytics) que combina duas fontes:

- **Google Open Buildings v3** — footprints extraídos por deep learning sobre imagens de satélite, cobertura principal em África, Sul da Ásia, Sudeste Asiático e América do Sul
- **Microsoft Building Footprints** — footprints extraídos por deep learning sobre imagens de satélite, cobertura principal em América do Norte, Europa e outras regiões

A mesclagem prioriza Google onde há sobreposição (por decisão do VIDA baseada em análises internas de qualidade). Cada footprint carrega um label `bf_source` indicando de qual fonte veio, permitindo comparação empírica entre as duas.

**Escala**: 2.534.595.270 edificações no total, das quais aproximadamente 140 milhões estão no Brasil.

**Particionamento**: os dados estão particionados por ISO do país (`country_iso=BRA`, `country_iso=USA`, etc.) e opcionalmente por células S2 (grade hexagonal global do Google). O particionamento por país permite consultar apenas o subconjunto brasileiro sem tocar em dados de outros países.

**Formatos disponíveis**: GeoParquet (usado neste projeto pela compatibilidade com DuckDB), FlatGeobuf e PMTiles.

**Bucket público**: `s3://us-west-2.opendata.source.coop/vida/google-microsoft-open-buildings/geoparquet/`

**Descrição oficial**: [source.coop/vida/google-microsoft-open-buildings](https://beta.source.coop/repositories/vida/google-microsoft-open-buildings/description/)

## Áreas de interesse (AOIs)

Duas cidades mineiras foram escolhidas para representar tipologias urbanas brasileiras contrastantes:

### Cambuquira/MG
- **População**: ~13 mil habitantes (IBGE 2022)
- **Área**: ~110 km²
- **Tipologia**: município rural de pequeno porte, sede compacta, extensa área rural com propriedades dispersas
- **Interesse**: verificar cobertura do dataset em contexto rural brasileiro, onde a extração automática por deep learning historicamente enfrenta mais desafios (edificações pequenas, telhado de cor variada, sombra de vegetação)

### Uberlândia/MG
- **População**: ~700 mil habitantes (IBGE 2022)
- **Área urbana consolidada**: ~220 km²
- **Tipologia**: cidade média-grande, malha urbana consolidada, mistura de padrões residenciais horizontais e verticais
- **Interesse**: contraste direto com Cambuquira em densidade e escala, permite comparar cobertura Google vs Microsoft em contexto urbano brasileiro típico

Os polígonos das AOIs estão versionados em `data/external/aois/` como GeoJSON, permitindo reprodutibilidade completa. Novas AOIs podem ser adicionadas ao mesmo diretório e ficam automaticamente disponíveis para a CLI.

## Roadmap

| Fase | Escopo | Status |
|------|--------|--------|
| **A** | Estrutura CCDS, `pyproject.toml`, `Makefile`, `tasks.ps1`, config, testes smoke, README inicial, GeoJSONs das AOIs | Concluída |
| **B** | `duckdb_client.py` — conexão + extensões + queries base parametrizadas por país/AOI | Concluída |
| **C** | `aoi.py` (gerenciamento + download IBGE) + `analysis.py` (queries de negócio) + CLI multi-comando completa | Concluída |
| **D** | `webmap.py` — HTML Leaflet interativo comparativo Google vs Microsoft | A implementar |
| **E** | Documentação robusta final, notebook demonstrativo, benchmark opcional DuckDB vs GeoPandas, GitHub Pages, polimento | A implementar |

### Substituindo bounding boxes por polígonos oficiais IBGE

Os GeoJSONs iniciais das AOIs em `data/external/aois/` foram bounding
boxes aproximadas. A partir da Fase C, o comando `obr-explorer aoi fetch`
baixa o polígono oficial da malha municipal IBGE 2022 e substitui o
arquivo mantendo a metadata editorial:

```bash
obr-explorer aoi fetch --codigo 3111606 --nome cambuquira_mg --sobrescrever
obr-explorer aoi fetch --codigo 3170206 --nome uberlandia_mg --sobrescrever
```

## Convenções técnicas

Este projeto segue o padrão estabelecido no portfólio pessoal do autor:

- **Português brasileiro (pt-BR)** em todo texto (README, docstrings, comentários, logs, mensagens de erro)
- **Estrutura CCDS v2** com `src`-layout (código em `src/pacote/`, testes em `tests/`)
- **Windows/PowerShell como plataforma primária**, Unix como fallback via `Makefile`
- **Sem emojis** em qualquer parte do código, documentação ou logs
- **Marcadores plain-text** `[OK]`, `[AVISO]`, `[ERRO]` em logs de produção
- **Conventional Commits** no histórico git
- **`.env` para credenciais e config**, template em `.env.example` versionado
- **Testes com pytest**, cobertura ≥ 90%, marker `network` para testes que dependem de S3

## Referências

- Sirko, W. et al. *Continental-Scale Building Detection from High Resolution Satellite Imagery*. arXiv:2107.12283, 2021. Paper original do Google Open Buildings.
- Microsoft Bing Maps. *Global ML Building Footprints*. GitHub: [microsoft/GlobalMLBuildingFootprints](https://github.com/microsoft/GlobalMLBuildingFootprints). Documentação oficial do Microsoft Building Footprints.
- Raasveldt, M.; Mühleisen, H. *DuckDB: An Embeddable Analytical Database*. SIGMOD 2019. Paper fundacional do DuckDB.
- OGC. *GeoParquet Specification v1.0*. [geoparquet.org](https://geoparquet.org/). Especificação oficial do formato usado como input.
- VIDA. *Google-Microsoft Open Buildings — A Combined Global Building Dataset*. [source.coop](https://beta.source.coop/repositories/vida/google-microsoft-open-buildings). Documentação da mesclagem.

## Licença

MIT — veja [LICENSE](LICENSE) para o texto completo.

## Autor

**Pedro Luiz Rodrigues Vaz de Melo** — Engenheiro Florestal e Cientista de Dados Geoespacial, atuando na intersecção entre engenharia florestal, análise geoespacial e ciência de dados. Pós-graduando em Ciência de Dados pela Data Science Academy.

- GitHub: [@PedroLuizskt](https://github.com/PedroLuizskt)
- Base: Cambuquira/MG, Brasil
