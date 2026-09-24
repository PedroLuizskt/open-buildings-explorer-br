# Arquitetura Técnica

Este documento descreve as decisões arquiteturais do
`open-buildings-explorer-br` e o fluxo de dados entre componentes.
Complementa o `README.md` (visão do usuário) com detalhes de
implementação úteis para quem lê ou modifica o código.

## Visão de alto nível

```
   +------------------+
   | S3 publico VIDA  |  (2,5 bilhoes de footprints, GeoParquet)
   +--------+---------+
            |
            | httpfs (leitura direta, predicate pushdown)
            v
   +------------------+
   |   DuckDB local   |  (in-process, in-memory ou file)
   |   + spatial ext  |
   +--------+---------+
            |
      +-----+------+
      |            |
      v            v
   analysis     webmap
   (dicts)      (HTML + GeoJSON)
      |            |
      v            v
   stdout       webmap/
   /JSON        index.html
```

Toda a stack é in-process: DuckDB roda embutido no Python via
`import duckdb`, sem servidor separado. Os dados brutos ficam no S3;
apenas os subconjuntos recortados pelas AOIs são materializados
localmente (em `data/processed/`).

## Componentes

### `config.py`

Fonte única da verdade para paths, constantes e leitura de env vars.
Todos os outros módulos importam daqui. Carrega `.env` da raiz se
presente, mas nada é obrigatório: defaults sensatos permitem uso
out-of-the-box.

### `duckdb_client.py` (Fase B)

Camada de acesso ao dataset. Responsabilidades:

- Criar conexão DuckDB (in-memory por default)
- Instalar e carregar extensões `httpfs` e `spatial`
- Executar queries base parametrizadas (por país, por partição)
- Aplicar recortes espaciais via `ST_Intersection` contra AOIs

**Não** contém lógica de negócio — só a mecânica de conversar com o
DuckDB. Análises ficam em `analysis.py`.

### `aoi.py` (Fase C)

Gerencia as áreas de interesse. Lê GeoJSONs de
`data/external/aois/`, valida, expõe como `GeoDataFrame` em EPSG:4326
(mesmo CRS do dataset Open Buildings). AOI é uma feature com metadata
descritiva no `properties` (nome, tipologia, população, área).

Adicionar uma nova AOI é uma operação de arquivo: colocar
`nome_novo.geojson` no diretório e passa a estar disponível para a
CLI. Nenhuma alteração de código.

### `analysis.py` (Fase C)

Análises de negócio: contagem por fonte, área total edificada,
comparação entre fontes (Google × Microsoft), comparação entre AOIs.
Retorna dicts serializáveis em JSON (não `DataFrame`) para facilitar
consumo pela CLI e pelo webmap.

### `webmap.py` (Fase D)

Gera HTML autocontido com Leaflet, camada base OpenStreetMap e duas
camadas de footprints (Google + Microsoft) com toggle. Painel lateral
mostra estatísticas por fonte. Compatível com GitHub Pages sem build
step — CDN para Leaflet, GeoJSONs em `webmap/data/`.

Design intencional: **zero build tool, zero backend**. Um HTML,
alguns GeoJSONs, servível de qualquer host estático.

### `cli.py` (Fase C)

Interface de linha de comando via `argparse`. Subcomandos: `info`,
`aoi list`, `aoi info`, `analyze`, `export`, `webmap`. Códigos de
saída distintos para tipos de erro (0 sucesso, 1 uso, 2 rede, 3
arquivo, 4 DuckDB).

## Fluxo de dados

### Uso típico: gerar webmap de Cambuquira

```
1. usuario:   obr-explorer webmap --aoi cambuquira_mg
2. cli.py:    resolve o comando, chama webmap.gerar_webmap_comparativo
3. aoi.py:    carrega data/external/aois/cambuquira_mg.geojson
              -> GeoDataFrame em EPSG:4326
4. duckdb_client: cria conexao, carrega extensoes httpfs+spatial
5. duckdb_client: parquet_scan sobre S3 filtrando country_iso=BRA
              (predicate pushdown baixa apenas metadata inicial)
6. duckdb_client: ST_Intersects entre footprints_BRA e AOI Cambuquira
              -> tabela dsa_cambuquira_footprints (~milhares de linhas)
7. analysis:  contar_por_fonte, area_total, etc.
8. webmap:    exporta GeoJSON por fonte em webmap/data/
9. webmap:    renderiza webmap/index.html com contexto injetado
10. usuario:  abre webmap/index.html no navegador ou publica em Pages
```

## Convenções de teste

- Testes offline por default (`pytest tests/`)
- Testes que dependem de rede/S3 marcados com `@pytest.mark.network`,
  rodados apenas com `pytest -m network`
- Fixtures em `tests/conftest.py`
- Fixtures grandes (dados sintéticos) usam `tmp_path` para
  isolamento
- Cobertura mínima alvo: 90%

## Deploy do webmap

O diretório `webmap/` é auto-contido: HTML + `data/*.geojson` + CSS
opcional. Publicação via GitHub Pages:

```bash
# Uma opcao: subir webmap/ como raiz de gh-pages
git subtree push --prefix webmap origin gh-pages

# Outra: configurar Pages para servir a partir de /webmap na branch main
# Repository Settings > Pages > Source: Deploy from a branch
#   Branch: main, Folder: /webmap
```

Nenhuma etapa de build. Nenhum servidor.

## Dependências externas críticas

| Pacote | Versão mínima | Papel | Alternativas descartadas |
|--------|---------------|-------|--------------------------|
| duckdb | 1.3 | Engine analítica | PostgreSQL/PostGIS (requer servidor), pandas puro (sem SQL) |
| geopandas | 1.0 | I/O de AOIs, validação geométrica | Shapely puro (sem I/O), Fiona (mais baixo nível) |
| pyarrow | 15.0 | Backend Parquet | fastparquet (menos maturidade) |
| pyogrio | 0.10 | Leitura GeoJSON rápida | fiona (mais lento) |
| shapely | 2.1 | Operações geométricas | — (dep transitiva de geopandas) |
| pyproj | 3.7 | Reprojeções | — (dep transitiva de geopandas) |

## O que este projeto não faz (e por quê)

- **Não** faz cálculos em CRSs métricos (UTM) para áreas — usa
  `ST_Area` do DuckDB spatial em EPSG:4326 (menos precisa, mas
  consistente com o dataset original que também está em WGS84). Para
  análises de precisão métrica, reprojetar seria trivial adicionar
- **Não** processa tiles em PMTiles — o webmap serve GeoJSON direto,
  o que é adequado para AOIs pequenas/médias. Para AOIs de cidade
  inteira grande, GeoJSON pode ficar lento; nesse caso, converter
  para PMTiles seria a próxima evolução (fora do escopo desta versão)
- **Não** compara com dados oficiais de edificações do IBGE — o
  dataset Open Buildings é a fonte única. Comparação com IBGE ou CAR
  poderia ser uma extensão interessante
- **Não** faz autenticação AWS — o bucket é público, `httpfs` acessa
  anonimamente
