"""Análises de negócio sobre footprints recortados por AOI.

**Este módulo será implementado na Fase C.**

Escopo previsto
---------------

- ``contar_por_fonte(con, tabela: str)`` — retorna dict com contagens
  por ``bf_source`` (Google, Microsoft) para os footprints de uma
  tabela recortada.

- ``area_total_por_fonte(con, tabela: str)`` — retorna dict com área
  total edificada por fonte, em metros quadrados (calculada via
  ``ST_Area``).

- ``resumo_aoi(con, tabela: str)`` — dataclass com o conjunto completo
  de estatísticas de uma AOI: total, por fonte, área média por
  edifício, distribuição de confidence score.

- ``comparar_fontes(con, tabela: str)`` — análise-chave do projeto:
  quantos footprints estão em ambas as fontes, quantos são exclusivos
  de cada, distribuição espacial das diferenças.

- ``comparar_aois(con, tabelas: dict[str, str])`` — compara métricas
  entre AOIs (Cambuquira × Uberlândia): densidade de construções
  por km², área média por edifício, cobertura relativa por fonte.

Convenções técnicas
-------------------

- Todas as funções recebem uma conexão DuckDB já configurada e o nome
  da tabela — não abrem conexão internamente
- Resultados são retornados como dicts serializáveis em JSON (não
  DataFrames), para facilitar consumo pela CLI e webmap
- Nomes de tabela seguem prefixo ``obr_`` para evitar colisão com
  tabelas do usuário no mesmo DuckDB

Testes previstos
----------------

- Contagens sobre fixture com 100 footprints sintéticos
- Área total confere com soma manual
- Comparação entre fontes retorna dict com estrutura esperada
- Comparação entre AOIs lida corretamente com tabelas de tamanhos
  diferentes
"""

from __future__ import annotations

# Placeholder — implementação virá na Fase C.


def contar_por_fonte(con, tabela: str):  # pragma: no cover
    """Conta footprints por fonte (Google/Microsoft). [Fase C]"""
    raise NotImplementedError("Será implementado na Fase C.")


def resumo_aoi(con, tabela: str):  # pragma: no cover
    """Estatísticas descritivas completas de uma AOI. [Fase C]"""
    raise NotImplementedError("Será implementado na Fase C.")
