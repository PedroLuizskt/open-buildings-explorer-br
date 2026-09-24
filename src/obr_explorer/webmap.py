"""Gerador de webmap HTML interativo com toggle Google vs Microsoft.

**Este módulo será implementado na Fase D.**

Escopo previsto
---------------

- ``gerar_webmap_comparativo(con, tabela: str, aoi, output_html: Path)`` —
  gera HTML autocontido em ``webmap/index.html`` com Leaflet, camada
  base OpenStreetMap, e duas camadas de footprints (Google + Microsoft)
  com controle de toggle. Painel lateral mostra contagens por fonte,
  área total edificada e legenda.

- ``exportar_geojson_para_web(con, tabela: str, output_dir: Path)`` —
  materializa os footprints da AOI como GeoJSON leve em
  ``webmap/data/``, particionado por fonte, servível diretamente pelo
  Leaflet via fetch.

- ``renderizar_template_html(contexto: dict, output: Path)`` — engine
  de template simples (Jinja2 opcional, ou substituição de placeholders)
  que injeta configuração da AOI e caminhos dos dados no HTML final.

Design do webmap
----------------

**Layout**:
- Mapa ocupando toda a viewport (Leaflet fullscreen)
- Painel lateral fixo à direita (largura ~320px):
  * Título da AOI (nome + tipologia)
  * Contagens: total de footprints, breakdown Google/Microsoft
  * Área total edificada em km²
  * Legenda com quadrados coloridos por fonte
  * Controle de toggle (checkbox) para cada camada

**Cores** (mantidas em CSS variável para fácil ajuste):
- Google: ``#4285F4`` (azul característico Google)
- Microsoft: ``#00A4EF`` (azul característico Microsoft)
- Interseção: rendering superposto (transparência 50% em cada)

**Interatividade**:
- Popup ao clicar em cada footprint: fonte, área em m², confidence
- Zoom inicial ajustado à bounding box da AOI
- Botão "reset view" no canto do mapa

**Restrições intencionais**:
- Nenhum backend, tudo estático
- CDNs para Leaflet (nenhum node_modules)
- Compatível com GitHub Pages sem qualquer build step
- Um único HTML autocontido + data/ com GeoJSONs

Estrutura de output
-------------------

::

    webmap/
    ├── index.html                     # HTML autocontido
    ├── data/
    │   ├── cambuquira_mg_google.geojson
    │   ├── cambuquira_mg_microsoft.geojson
    │   ├── uberlandia_mg_google.geojson
    │   └── uberlandia_mg_microsoft.geojson
    └── assets/
        └── style.css                  # opcional, se separarmos CSS

Testes previstos
----------------

- Geração produz HTML válido (parseável por lxml/BeautifulSoup)
- HTML contém os placeholders substituídos corretamente
- GeoJSON exportado é válido e tem estrutura esperada
- Bounding box calculada bate com envelope da AOI
"""

from __future__ import annotations

# Placeholder — implementação virá na Fase D.


def gerar_webmap_comparativo(con, tabela: str, aoi, output_html):  # pragma: no cover
    """Gera webmap HTML interativo com toggle Google/Microsoft. [Fase D]"""
    raise NotImplementedError("Será implementado na Fase D.")
