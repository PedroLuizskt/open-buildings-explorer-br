# Template de post LinkedIn — open-buildings-explorer-br

Material pronto para você copiar/adaptar quando quiser anunciar o projeto
no LinkedIn. Três variações: curta (apresentação do projeto), técnica
(explicando o DuckDB), narrativa (destacando o insight do dado).

Escolha a que mais combina com seu tom de voz na rede e **personalize**
antes de postar — número de reações é diretamente proporcional ao quanto
soa como você. Imagens recomendadas: screenshot do webmap com dashboard
visível (tanto Cambuquira quanto Uberlândia funcionam, Uberlândia impressiona
mais pela escala). Até 4 imagens caem bem; alterne entre overview do painel
e zoom em algum bairro.

---

## Opção 1 — Curta (apresentação do projeto)

Novo projeto público no GitHub: **open-buildings-explorer-br** — análise
geoespacial em escala de bilhões de linhas usando DuckDB sobre o dataset
Google-Microsoft Open Buildings direto do S3 público.

O pipeline consulta 141 milhões de edificações do Brasil sem baixar o
dataset localmente, recorta por polígonos IBGE 2022 de municípios de
interesse, e gera um webmap HTML interativo comparando as fontes Google
e Microsoft lado a lado.

Resultados reais em Cambuquira/MG (município rural, 246 km²): **12.182
edificações**, 92,7% Google e 7,3% Microsoft. Em Uberlândia/MG (cidade
média, 4.115 km²): **537.880 edificações**, com densidade 2,7× maior
que Cambuquira por km² — exatamente o que a tipologia urbano/rural
sugere.

Stack: DuckDB (httpfs + spatial), GeoPandas, Leaflet, Chart.js.
Zero infraestrutura externa — tudo in-process.

Repositório, webmap ao vivo e documentação completa:
→ github.com/PedroLuizskt/open-buildings-explorer-br

#DataScience #GIS #DuckDB #Geospatial #OpenData #Python

---

## Opção 2 — Técnica (foco no DuckDB como padrão emergente)

DuckDB virou peça central do meu stack de análise geoespacial em 2026, e
publiquei um projeto no GitHub que explora isso em escala real.

**O desafio**: consultar o Google-Microsoft Open Buildings — 2,5 bilhões
de edificações globais, 141 milhões só no Brasil — sem subir
infraestrutura (Spark, PostGIS em cluster) e sem baixar o dataset inteiro
(dezenas de GB).

**A solução**:

→ DuckDB in-process com extensão `httpfs` lendo Parquet direto do
  bucket S3 público (zero-copy analytics)

→ Extensão `spatial` para SQL geoespacial (`ST_Intersects`,
  `ST_Intersection`) sem precisar de PostGIS

→ Polígonos oficiais da malha municipal IBGE 2022 como áreas de
  interesse, recorte via `ST_Intersection`

→ Webmap HTML autocontido com Leaflet + Chart.js — dashboard
  comparativo Google × Microsoft, popups ricos por footprint,
  servido via GitHub Pages sem build step

Alguns detalhes técnicos que aprendi pelo caminho e documentei em
ADRs no repositório:

→ Bucket S3 com pontos no nome quebra validação SSL em
  virtual-hosted-style URL — solução: `SET s3_url_style='path'`

→ Extensões DuckDB no Windows podem falhar validação de CA bundle —
  solução: `SET ca_cert_file` apontando para `certifi.where()`

→ `encoding='utf-8'` explícito em toda chamada `open()` evita
  corrupção de acentos em GeoJSONs quando rodando no Windows

→ Canvas renderer do Leaflet (`L.canvas` + `preferCanvas: true`) é
  essencial para renderizar centenas de milhares de polígonos sem
  travar o navegador

Repositório, 10+ ADRs documentando cada decisão, 136 testes
automatizados e webmap ao vivo:
→ github.com/PedroLuizskt/open-buildings-explorer-br

#DuckDB #DataEngineering #GIS #Geospatial #Python #OpenData

---

## Opção 3 — Narrativa (insight do dado como gancho)

A diferença de densidade urbana entre uma cidade mineira pequena e uma
cidade mineira média — medida em edificações por km² — é dramática,
mas quantificar isso com rigor exigia infraestrutura ou dinheiro.

Hoje publiquei um projeto no GitHub que faz essa medição em segundos
usando dados públicos abertos:

**Cambuquira/MG** (246 km², ~13 mil habitantes, município rural):
12.182 edificações mapeadas → **49 edif/km²**

**Uberlândia/MG** (4.115 km², ~713 mil habitantes, cidade média):
537.880 edificações mapeadas → **131 edif/km²**

**Densidade urbana 2,7× maior em Uberlândia**, apesar da área ser só
17× maior em km². O município cresce em densidade de edificações mais
rápido que em território — padrão esperado de urbanização consolidada,
agora com evidência numérica concreta.

A fonte: Google-Microsoft Open Buildings (dataset da VIDA mesclando
Google Open Buildings v3 + Microsoft Building Footprints), 2,5
bilhões de footprints globais. A consulta: DuckDB in-process lendo
Parquet direto do S3 público, sem baixar o dataset inteiro.

O webmap interativo tem toggle Google × Microsoft, dashboard com
contagens e áreas por fonte, popups mostrando metros quadrados por
edificação. Compatível com GitHub Pages, zero build step.

Código, documentação e webmap:
→ github.com/PedroLuizskt/open-buildings-explorer-br

#CiênciaDeDados #GIS #DadosAbertos #Brasil #DuckDB

---

## Checklist antes de postar

- [ ] Rodar `obr-explorer webmap --pular-carga --db-path .\dados_br.duckdb` para garantir que o webmap está atualizado
- [ ] Publicar via GitHub Pages (vai aparecer em `https://pedroluizskt.github.io/open-buildings-explorer-br/`)
- [ ] Capturar 2-4 screenshots do webmap: overview das AOIs, dashboard aberto, popup rico, histograma
- [ ] Adicionar link do webmap ao vivo no texto do post (não só do repo)
- [ ] Marcar `@VIDA` ou `@Source.coop` se eles tiverem presença no LinkedIn (atribuição elegante)
- [ ] Revisar hashtags para o seu alcance habitual
