"""Cliente DuckDB — conexão, extensões e queries base parametrizadas.

**Este módulo será implementado na Fase B.**

Escopo previsto
---------------

- ``criar_conexao(in_memory: bool = True)`` — cria uma conexão DuckDB
  (in-memory por default; opcionalmente persistente em disco) já com
  as extensões ``httpfs`` e ``spatial`` instaladas e carregadas.

- ``carregar_pais(con, country_iso: str, tabela: str)`` — materializa
  em uma tabela DuckDB os footprints de um país inteiro, lidos direto
  do bucket S3 público via ``parquet_scan``. Para o Brasil, isso são
  ~140M linhas; a operação é rápida porque o Parquet permite
  predicate pushdown na leitura.

- ``carregar_pais_particionado(con, country_iso: str, tabela: str)`` —
  variante que usa o particionamento composto por país + célula S2,
  útil quando queremos agregar por partição espacial.

- ``carregar_pais_google_original(con, country_iso: str, tabela: str)`` —
  carrega footprints do bucket Google Open Buildings v3 puro (sem
  mesclagem Microsoft), para permitir comparações "com Microsoft × sem
  Microsoft" que evidenciam o valor agregado da mesclagem.

- ``recortar_por_aoi(con, tabela_footprints: str, geojson_path: Path,
  tabela_aoi: str, tabela_recorte: str)`` — aplica ``ST_Intersection``
  entre footprints e polígono da AOI, criando uma tabela nova com
  apenas os edifícios dentro da área.

Convenções técnicas
-------------------

- Todas as queries usam prepared statements com parâmetros, nunca
  interpolação de strings — evita SQL injection e melhora cache
- Conexões são retornadas para o chamador gerenciar (padrão context
  manager suportado, mas não imposto)
- Erros de rede (S3 indisponível) sobem como ``RuntimeError`` com
  mensagem clara indicando qual URL falhou
- ``INSTALL`` das extensões é feito apenas na primeira execução;
  ``LOAD`` é sempre feito para garantir que estão ativas

Testes previstos
----------------

- Conexão in-memory básica sem rede
- Instalação e carregamento das extensões
- Query de contagem em país pequeno (ex: LSO com ~1M edifícios) via
  ``@pytest.mark.network``
- Recorte espacial contra AOI fixture (polígono minúsculo) via network
- Fallback quando o bucket S3 está inacessível

Referências
-----------

- DuckDB httpfs extension: https://duckdb.org/docs/extensions/httpfs
- DuckDB spatial extension: https://duckdb.org/docs/extensions/spatial
- GeoParquet spec: https://geoparquet.org/
"""

from __future__ import annotations

# Placeholder — implementação virá na Fase B.
# A estrutura de assinaturas permite que módulos dependentes (aoi.py,
# analysis.py, webmap.py) importem estas funções e testes façam mock.


def criar_conexao(in_memory: bool = True):  # pragma: no cover
    """Cria conexão DuckDB com extensões httpfs e spatial. [Fase B]"""
    raise NotImplementedError("Será implementado na Fase B.")
