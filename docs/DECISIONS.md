# Log de Decisões Arquiteturais

Este arquivo registra as decisões técnicas tomadas no projeto, no
estilo Architecture Decision Records (ADR). Cada entrada tem
**Contexto**, **Decisão**, **Consequências**, e **Data**. Novas
decisões vão sendo adicionadas ao final, mantendo o histórico.

---

## ADR-014: Duas camadas base (OSM + ESRI Satellite) no webmap

**Data**: 2026-10-08

**Contexto**: a Fase D entregou o webmap com uma única camada base
(OpenStreetMap). OSM é excelente para orientação urbana (nomes de ruas,
pontos de referência, limites administrativos), mas não permite
verificar visualmente se os footprints extraídos pelos pipelines
Google/Microsoft batem com as edificações reais vistas de cima. O
autor pediu adicionar a camada ESRI World Imagery (satélite).

**Decisão**: usar `L.control.layers` do Leaflet com duas camadas base
mutuamente exclusivas:

- **OpenStreetMap** — default, mantém o comportamento anterior
- **ESRI World Imagery** —
  `server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
  gratuito para uso não comercial segundo os [termos da Esri](https://www.esri.com/en-us/legal/terms/full-master-agreement),
  attribution preservada

Controle posicionado no canto superior direito (`position: "topright"`,
`collapsed: false` para ficar sempre visível). Estilizado com paleta
dark do painel via CSS override no `.leaflet-control-layers`.

Ajuste colateral no estilo dos footprints: `fillOpacity` reduzida de
`0.55` para `0.5` e `weight` aumentada de `0.5` para `0.7`. Isso dá
melhor contraste sobre a imagem de satélite (fundo escuro em áreas
urbanas) sem comprometer a leitura sobre OSM (fundo claro).

**Consequências**:

- Positivas: usuário pode validar visualmente a qualidade dos
  footprints — vê a edificação real e o polígono extraído sobrepostos
- Positivas: ESRI Imagery é padrão de facto no mundo GIS,
  reconhecido pelos usuários técnicos imediatamente
- Positivas: `L.control.layers` tem UX nativa do Leaflet, não precisa
  JS customizado
- Neutras: adiciona dependência de rede ao tile server da ESRI em
  tempo de visualização. Se ESRI ficar indisponível, OSM continua
  funcionando (fallback natural pelo controle de camadas)
- Neutras: ESRI tiles são servidos sem HTTPS garantido em algumas
  rotas antigas — attribution e termos de uso são responsabilidade
  do deploy final

---

## ADR-013: Encerramento do projeto e checklist de produção

**Data**: 2026-10-08

**Contexto**: após ADR-012 (reformulação do webmap multi-AOI), o
projeto atingiu paridade de qualidade com a visão original (Fase E).
Faltava registrar o conjunto de decisões "finais" que preparam o
projeto para divulgação pública e uso de portfólio: deploy automático,
documentação robusta, visibilidade e manutenibilidade.

**Decisões**:

1. **Deploy automático via GitHub Actions**: workflow
   `.github/workflows/pages.yml` dispara em push para `main` tocando
   em `webmap/**` ou no próprio workflow, usando as actions oficiais
   `configure-pages`, `upload-pages-artifact` e `deploy-pages`.
   Alternativa descartada: Pages a partir de pasta (`/webmap`) exige
   configuração manual no Settings e não documenta a decisão.

2. **CITATION.cff** no formato oficial do GitHub ("Cite this
   repository"), com metadados em pt-BR mas estrutura padrão.
   Inclui referências ao dataset VIDA, Google Open Buildings paper
   (Sirko et al. 2021) e DuckDB (Raasveldt & Mühleisen 2019).

3. **CHANGELOG.md** no formato Keep a Changelog + SemVer, com
   todas as versões 0.1.0 → 0.5.0 referenciando os ADRs que
   justificam cada mudança.

4. **Notebook demonstrativo** `notebooks/01_demonstrativo.ipynb` com
   21 células (8 markdown, 13 código) percorrendo o uso da API
   Python sem passar pela CLI. Para quem quer entender o pipeline
   por dentro ou integrar o projeto em scripts maiores.

5. **Template de post LinkedIn** em `docs/LINKEDIN_POST.md` com três
   variações (curta, técnica, narrativa) + checklist pré-publicação.
   Nenhuma pretende ser publicada tal como está — orienta
   personalização.

6. **Novo subcomando `db-compact`**: `DROP TABLE` do DuckDB não
   devolve espaço ao SO imediatamente (marca páginas como livres).
   `db-compact` cria banco novo via `EXPORT DATABASE` +
   `IMPORT DATABASE`, substitui o original, faz backup `.bak`
   automático. Resolve a reclamação legítima do autor de que
   `dados_br.duckdb` permanecia em 39 GB após `db-prune` bem-sucedido.

7. **Nenhum novo recurso Python além do `db-compact`** — foco da
   Fase E é documentação e visibilidade, não funcionalidade.

**Consequências**:

- Positivas: projeto cruza a linha "código funciona" para "cartão de
  visita profissional" — alguém que chega pelo LinkedIn consegue
  entender valor em 30 segundos
- Positivas: GitHub Actions elimina fricção do deploy — commitar
  recarrega webmap, zero esforço manual
- Positivas: notebook abre caminho para educadores/pesquisadores
  que queiram adaptar o projeto para outras AOIs ou outros países
- Positivas: `db-compact` fecha o loop de gerenciamento de disco
  que era um ponto genuíno de confusão
- Neutras: README cresceu bastante (de ~200 para ~300 linhas),
  mas organização numerada em 14 seções facilita navegação
- Neutras: `.github/workflows/pages.yml` depende da conta GitHub do
  autor; para forks funcionarem é preciso que o fork habilite Pages
  em Settings. Documentado no README.

---

## ADR-001: Repositório separado do monorepo principal

**Data**: 2026-09-23

**Contexto**: o autor já mantém um monorepo `datascience-projects`
com os projetos 01 e 02 da pós-DSA (recomendador agropecuário e rede
neural do zero). Este Projeto 4 (Cap11 da Disciplina 3, DuckDB
geoespacial) foi identificado como tendo potencial excepcional de
portfólio profissional por combinar big data genuíno, stack analítica
moderna (DuckDB), SQL espacial e cloud storage — combinação rara e
altamente valorizada em vagas seniores em 2026.

**Decisão**: criar repositório GitHub separado
`open-buildings-explorer-br` em vez de mais uma pasta no monorepo.

**Consequências**:
- Positivas: visibilidade individual do projeto (recrutadores acham
  mais fácil), README próprio otimizado, GitHub Pages dedicado para o
  webmap, licença própria, versionamento independente
- Negativas: um repo a mais para manter, código de infra
  (Makefile, tasks.ps1, config) duplicado em relação ao monorepo
- Neutras: as convenções técnicas seguem exatamente o padrão dos
  projetos 01 e 02 (pt-BR, sem emojis, CCDS v2, tasks.ps1 + Makefile,
  pyproject.toml com hatchling), então a curva de aprendizado é zero
  para quem vem dos outros repos

---

## ADR-002: Nome do repositório: `open-buildings-explorer-br`

**Data**: 2026-09-23

**Contexto**: precisávamos escolher entre `open-buildings-brasil`
(mais descritivo, SEO forte) e `open-buildings-explorer-br` (sinaliza
que tem webmap interativo). O objetivo era balancear clareza e
sinalização do diferencial visual.

**Decisão**: `open-buildings-explorer-br` no repositório, pacote
Python `obr_explorer`, entry point CLI `obr-explorer`.

**Consequências**:
- A palavra "explorer" ancora a expectativa correta de que há
  interatividade visual, não apenas análise tabular
- Nome mais longo, mas ainda memorável e único no ecossistema
- Sufixo `-br` deixa claro o escopo geográfico

---

## ADR-003: AOIs iniciais: Cambuquira/MG + Uberlândia/MG

**Data**: 2026-09-23

**Contexto**: o projeto DSA original usa um polígono genérico de 3×2
km em Lesoto (África). Precisávamos substituir por AOIs brasileiras
que criassem narrativa comparativa interessante.

**Decisão**: duas AOIs no lançamento — Cambuquira/MG (rural pequena,
~13k habitantes, ~110 km²) e Uberlândia/MG (área urbana consolidada,
~700k habitantes, ~220 km²).

**Consequências**:
- Contraste rural × urbano permite análises comparativas ricas
- Cambuquira sendo a cidade do autor cria assinatura pessoal
- Uberlândia sendo cidade média típica do interior brasileiro
  representa bem o "caso brasileiro médio"
- Estrutura suporta N AOIs (basta adicionar GeoJSON ao diretório),
  mas o lançamento fica com duas para escopo controlado
- Polígonos usados são bounding boxes aproximadas, não limites
  oficiais IBGE — isso está documentado nos properties dos GeoJSONs

---

## ADR-004: Webmap comparativo Google × Microsoft

**Data**: 2026-09-23

**Contexto**: o dataset Open Buildings é uma mesclagem de duas
fontes com metodologias distintas de extração por deep learning. A
coluna `bf_source` marca a procedência de cada footprint, permitindo
comparação empírica. Poderíamos ter:
- (A) webmap simples com uma única camada mesclada
- (B) webmap comparativo com toggle entre camadas Google e Microsoft
- (C) dashboard analítico completo com gráficos + tabelas

**Decisão**: opção B — webmap comparativo com toggle. Google e
Microsoft renderizados em cores distintas, controle de checkbox por
camada, painel lateral com contagens por fonte.

**Consequências**:
- Reflete visualmente a análise-chave do dataset (comparação entre
  fontes) que é o diferencial da versão mesclada
- Escopo maior que opção A mas menor que C, permitindo entrega
  focada
- HTML permanece autocontido, servível via GitHub Pages sem backend
- Cores oficiais das marcas (Google `#4285F4`, Microsoft `#00A4EF`)
  criam associação visual imediata

---

## ADR-005: Sem apostila didática, foco em documentação robusta

**Data**: 2026-09-23

**Contexto**: os Projetos 01 e 02 têm apostilas didáticas em
`docs/apostila/` no estilo `estudos-observabilidade`. Considerou-se
manter o padrão neste projeto.

**Decisão**: **sem apostila didática**. Investir o esforço em
documentação profissional robusta: `README.md` detalhado,
`ARCHITECTURE.md`, este `DECISIONS.md`, docstrings ricas nos módulos,
e notebook demonstrativo. Nada em `docs/apostila/`.

**Consequências**:
- Foco no perfil "portfólio profissional" (recrutador lê README, roda
  a CLI, vê o webmap) em vez de "material didático de curso"
- Reduz escopo em uma fase inteira (E não precisa incluir apostila),
  o que permite investir a Fase E em polimento e benchmark
- README precisa carregar mais peso — feito
- Se depois surgir demanda por apostila, pode ser adicionada sem
  quebrar nada

---

## ADR-012: Webmap multi-AOI com dashboard analítico (reformulação da Fase D)

**Data**: 2026-10-08

**Contexto**: a Fase D entregou um webmap funcional, mas apenas para
uma AOI por vez (cada `obr-explorer webmap` sobrescrevia o
`index.html`). O autor pediu uma reformulação com:

1. Switcher único para alternar entre Cambuquira e Uberlândia
2. Painel lateral mais rico com dashboard analítico
3. Popups com mais informação por footprint
4. Padronização visual inspirada em um projeto anterior do autor
   (visualização CHIRPS de precipitação)

**Decisão**: reformular `webmap.py` em torno da função
`gerar_webmap_multi(con, aois_e_tabelas, output_dir)` que gera um
único HTML carregando todas as AOIs via payload JSON embutido. A
função antiga `gerar_webmap_comparativo` vira wrapper de
compatibilidade (delega para `gerar_webmap_multi` com lista de um
elemento).

**Novo layout do webmap** (inspirado no projeto CHIRPS do autor):

- **Fontes**: Barlow Condensed (impacto) + Karla (corpo) via Google Fonts
- **Paleta dark**: `#060d16` fundo, `#0d1b2a` cards, `#00b4d8` destaque,
  `#1a3347` bordas sutis
- **Header**: logo gradient (azul Google → azul Microsoft) + título +
  badge com total global de edificações
- **Seletor de AOI**: dropdown estilizado no topo do painel
- **Tabs no painel**: Visão Geral / Análise / Detalhe
  - **Visão Geral**: metadata da AOI em stat rows + KPI grid 2×2
    (total, densidade/km², %Google, %Microsoft) + donut Chart.js
    comparando contagens + narrativa interpretativa gerada no cliente
  - **Análise**: histograma Chart.js com 5 buckets de área
    (<50, 50-100, 100-200, 200-500, >=500 m²), áreas médias por fonte,
    tabela comparativa lado a lado entre AOIs
  - **Detalhe**: info do footprint clicado (fonte, área m² e hectares,
    centroide lat/lon, AOI). Clicar em um polígono no mapa troca
    automaticamente para esta tab
- **Popups**: dark theme consistente com painel, chip colorido para
  fonte, rows de "label: valor" para área m²/ha, coordenadas
- **Legenda flutuante** no canto inferior esquerdo do mapa com toggles
  de camada Google/Microsoft

**Enriquecimento dos GeoJSONs exportados**: cada feature agora traz
`area_m2` nas properties (calculada via `ST_Area` convertida de graus²
para m² com ajuste pela latitude média da AOI). Isso alimenta os
popups ricos e o cálculo client-side.

**Novo subcomando CLI** `--aoi` com `action="append"`: pode ser
repetido para incluir múltiplas AOIs no mesmo HTML. Sem `--aoi`, usa
todas as AOIs em `data/external/aois/`.

**Novos subcomandos de gerenciamento de disco** `db-info` e `db-prune`
em resposta à constatação do autor de que `dados_br.duckdb` ocupa
~40 GB. Explicação técnica: 141M registros × ~250 bytes (geometria WKB
+ metadata) = ~35 GB, mais overhead de páginas do DuckDB. É esperado.
`db-prune` remove `footprints_<iso3>` mantendo `recorte_<aoi>`.

**Consequências**:

- Positivas: um único webmap carrega todas as AOIs — melhor UX, menos
  arquivos, mais fácil de compartilhar/hospedar
- Positivas: dashboard analítico eleva o projeto de "mapa interativo"
  para "ferramenta de análise visual" — mais apropriado como peça de
  portfólio profissional
- Positivas: popups ricos com área por footprint dão o "wow factor"
  que faltava
- Positivas: `db-info`/`db-prune` resolvem a preocupação legítima de
  disk space sem forçar o usuário a reinstalar/re-baixar
- Neutras: template HTML cresceu de ~350 linhas para ~985 linhas
  (adiciona Chart.js + payload JSON + três tabs + dashboard). Ainda é
  um único `.replace()` sem Jinja — se crescer muito mais, migrar
- Neutras: GeoJSONs agora têm coluna `area_m2` adicional, +8 bytes
  por footprint. Para 500k footprints = +4 MB. Aceitável.

---

## ADR-011: Webmap como HTML autocontido com Canvas renderer e decimação opcional

**Data**: 2026-10-07

**Contexto**: a Fase D precisava entregar um webmap comparativo
Google × Microsoft como cartão de visita visual do projeto. Três
decisões técnicas se impuseram ao analisar os números reais:

- **Cambuquira**: 12.182 footprints — carregável como GeoJSON direto
- **Uberlândia**: 537.880 footprints — carregamento cru trava navegadores
- Deploy via **GitHub Pages**: zero backend, zero build step

**Decisões**:

1. **HTML autocontido com Leaflet via CDN** (não React/Vite/bundler).
   Um `index.html` + `data/*.geojson` servível por qualquer host estático.
   Zero dependência Node, zero etapa de build. Para o escopo (toggle de
   camadas, popups, painel lateral), isso é suficiente e mais robusto que
   stack moderna que exige CI.

2. **Canvas renderer** (`L.canvas` + `preferCanvas: true`) como default,
   não SVG. Com 500k polígonos, SVG renderer trava — cada polígono vira
   um elemento DOM e o browser engasga no reflow. Canvas renderiza tudo
   num único `<canvas>` com performance 10-100× melhor.

3. **Decimação opcional** via flags CLI `--min-area-m2` e
   `--simplify-tolerance`. Para Cambuquira ambos podem ser `None` (default),
   todos os 12k footprints cabem confortavelmente. Para Uberlândia, 30 m²
   de mínimo descarta anexos pequenos e galpões irrelevantes, mantendo
   edificações significativas. `ST_SimplifyPreserveTopology` com tolerância
   `1e-5` (~1m em WGS84) reduz vértices por polígono.

4. **Flag `--pular-carga` + `--db-path`** para iteração visual rápida.
   Baixar 141M footprints do Brasil leva ~30 min. Com um banco DuckDB
   persistente, o pipeline carrega uma vez e reusa a tabela de recorte
   em todas as iterações seguintes do webmap (ajuste de estilo, de
   decimação, etc.). Essencial para desenvolvimento iterativo.

5. **Cores oficiais das marcas**: Google `#4285F4`, Microsoft `#00A4EF`.
   Isso cria associação visual imediata e preserva significado quando
   o legenda não está visível (ex: screenshots).

**Consequências**:

- Positivas: webmap funciona out-of-the-box em qualquer navegador
  moderno sem build step
- Positivas: `python -m http.server --directory webmap` para preview
  local instantâneo
- Positivas: deploy via GitHub Pages é `git push` sem workflow CI
- Positivas: decimação opcional permite escalar para AOIs grandes
  mantendo UX fluida; AOIs pequenas usam fidelidade total
- Positivas: `--db-path` + `--pular-carga` acelera iteração visual
  de minutos para segundos
- Neutras: Leaflet via CDN depende de unpkg estar online no cliente;
  aceitável porque Leaflet é dependência padrão da indústria
- Neutras: HTML gerado programaticamente usa `.replace()` em vez de
  Jinja para evitar dependência extra; funciona bem para o volume de
  interpolação atual mas se o template crescer muito, migrar para
  Jinja seria incremental

---

## ADR-010: encoding='utf-8' explícito em todas as chamadas .open()

**Data**: 2026-10-01

**Contexto**: ao rodar a suíte de testes no Windows do autor, dois
testes falharam com erro de encoding:

```
assert 'UberlÃ¢ndia' == 'Uberlândia'
```

Causa: o encoding default do ``open()`` no Python depende do sistema
operacional (``locale.getpreferredencoding()``). No Linux/Mac é
UTF-8; no Windows é **cp1252** por padrão. Os GeoJSONs das AOIs são
escritos em UTF-8 (padrão RFC 8259), mas chamadas ``path.open()`` sem
argumento ``encoding`` liam com cp1252 no Windows, corrompendo
caracteres acentuados como "Uberlândia" → "UberlÃ¢ndia".

**Decisão**: adicionar ``encoding="utf-8"`` **explícito** em TODA
chamada ``<path>.open(...)`` em modo texto no código do projeto.
Modo binário (``"rb"``, ``"wb"``) é exceção porque ``encoding`` não
se aplica a bytes.

Além disso, adicionar teste de regressão
``test_regressao_nao_ha_open_sem_encoding`` que usa AST para varrer
``src/`` e ``tests/`` e falhar se encontrar qualquer
``<path>.open()`` em modo texto sem ``encoding=``.

**Consequências**:
- Positivas: comportamento idêntico entre Linux/Mac/Windows,
  elimina classe inteira de bugs sutis de I/O de texto
- Positivas: AST-based regression test pega 100% dos casos, sem
  falsos positivos de strings/comentários (análise sintática, não
  textual)
- Positivas: código fica auto-documentado — leitor vê que o arquivo
  é tratado como UTF-8 sem precisar inferir
- Neutras: um pouco mais verboso que ``open()`` nu, mas é prática
  recomendada por PEP 686 (``PYTHONUTF8=1``) e vai virar default
  em Python 3.15
- Neutras: PEP 686 "Make UTF-8 mode default" vai eliminar esse
  problema automaticamente em versões futuras do Python, mas até
  lá o fix explícito é a solução canônica

---

## ADR-009: Polígonos oficiais IBGE via shapefile local (não via API)

**Data**: 2026-09-29

**Contexto**: durante a Fase C, foram implementadas duas formas de
substituir as bounding boxes iniciais pelos polígonos oficiais IBGE
das AOIs:

- **Via API v3 do IBGE**: comando ``obr-explorer aoi fetch --codigo <IBGE>``.
  Conveniente para adicionar novos municípios sob demanda, mas dependia
  de rede e da estabilidade da API.
- **Via shapefile local**: baixar a malha municipal 2022 (BC250) do
  portal do IBGE, importar no QGIS, exportar cada município como
  shapefile individual e converter para GeoJSON.

Durante a validação da Fase C, dois problemas surgiram com a via API:

1. **Bug de encoding**: a API IBGE retornava payload gzipado sem
   declarar ``Content-Encoding: gzip`` (ou com anti-cache mangling),
   causando ``UnicodeDecodeError`` no parse JSON. Correção requereu
   detectar magic bytes ``0x1f 0x8b`` e descomprimir manualmente.
2. **Código IBGE incorreto no METADATA_PADRAO**: assumimos código
   ``3111606`` para Cambuquira, quando o correto é ``3110707``
   (erro só descoberto ao ler o shapefile oficial). ``3111606``
   pertence a outro município.

**Decisão**: usar os **shapefiles oficiais IBGE 2022 (BC250)**
exportados manualmente do QGIS como fonte primária dos polígonos das
AOIs. O comando CLI ``obr-explorer aoi fetch`` (com bug do gzip
corrigido) permanece disponível para adicionar novos municípios sob
demanda no futuro, mas os polígonos de Cambuquira e Uberlândia ficam
versionados como GeoJSON no repositório para reprodutibilidade total.

Isso também simplifica setup: quem clona o repo tem os polígonos
oficiais imediatamente, sem depender da API IBGE estar online.

**Consequências**:
- Positivas: reprodutibilidade absoluta — polígonos versionados no
  Git, congelados na versão IBGE 2022 usada durante o desenvolvimento
- Positivas: setup zero-dependência para as AOIs padrão
  (Cambuquira e Uberlândia)
- Positivas: metadata rica extraída direto do shapefile
  (região intermediária, região geográfica imediata, código IBGE,
  área km² oficial) — mais que a API v3 devolve
- Positivas: reprojeção controlada (SIRGAS 2000 → WGS84) documentada
  no ``properties.fonte_poligono``
- Neutras: arquivos GeoJSON versionados são maiores (245 KB Cambuquira,
  643 KB Uberlândia). Aceitável para 2 municípios; se subir para 20+
  AOIs, considerar Git LFS ou download on-demand
- Neutras: correção do bug de gzip fica no código como defesa em
  profundidade para uso futuro do ``aoi fetch``

---

## ADR-008: Path-style URLs no cliente S3 (obrigatório para o bucket VIDA)

**Data**: 2026-09-28

**Contexto**: após implementar ADR-007 (certifi para CA bundle), os
testes de rede contra o bucket S3 público VIDA continuaram falhando
no Windows com ``IOException: SSL peer certificate or SSH remote key
was not OK``. Investigação mais profunda revelou a causa raiz: **o
bucket se chama ``us-west-2.opendata.source.coop`` e contém pontos no
nome**.

O DuckDB (como default AWS) usa virtual-hosted-style URLs:
``<bucket>.s3.<region>.amazonaws.com``. Para nosso bucket, isso
resulta em ``us-west-2.opendata.source.coop.s3.us-west-2.amazonaws.com``
— hostname com múltiplos níveis de subdomínio. O certificado SSL
wildcard da AWS é ``*.s3.<region>.amazonaws.com``, que cobre apenas
UM nível de subdomínio. Por isso a validação SSL falha, mesmo com
CA bundle correto.

A própria [documentação AWS](https://docs.aws.amazon.com/AmazonS3/latest/userguide/VirtualHosting.html)
reconhece: *"When a bucket name contains dots, its virtual-hosted-style
URL doesn't work over HTTPS because of SSL certificate mismatch."*
Recomendação oficial: usar path-style URLs
(``s3.<region>.amazonaws.com/<bucket>/<path>``).

**Decisão**: setar ``SET s3_url_style='path'`` por default no
``configurar_s3()``. Adicionar parâmetro opcional ``s3_url_style``
para permitir override (aceita ``"path"`` ou ``"vhost"``, com
validação estrita).

**Consequências**:
- Positivas: resolve definitivamente o erro SSL para o bucket VIDA
  no Windows (a causa raiz, não sintoma); solução alinhada com a
  recomendação oficial AWS
- Positivas: path-style é universalmente compatível — funciona para
  todos os buckets, tenham pontos no nome ou não
- Positivas: mudança é uma linha em configurar_s3(), zero impacto
  em outras partes do código
- Neutras: path-style é considerado "legacy" pela AWS para novos
  buckets, mas continuará suportado indefinidamente (AWS adiou
  planos de deprecation devido a casos exatamente como este)
- Neutras: 3 novos testes garantem que a configuração é aplicada
  corretamente e permite override

**Ordem cronológica dos ADRs 006/007/008**: 006 estabeleceu a stack
técnica; 007 identificou problema SSL parcial resolvido com certifi;
008 identificou a causa raiz real (path-style) que ADR-007 mascarava
mas não resolvia. Ambos os fixes ficam no código — 007 continua
sendo boa prática (defesa em profundidade), 008 é o fix crítico.

---

## ADR-007: Certifi como fonte do CA bundle para DuckDB httpfs (Windows)

**Data**: 2026-09-28

**Contexto**: durante validação da Fase B no ambiente Windows do autor,
os testes de rede contra o bucket S3 público VIDA falharam com
``IOException: SSL peer certificate or SSH remote key was not OK``. A
extensão ``httpfs`` do DuckDB no Windows usa um bundle de CAs interno
(via libcurl compilado) que frequentemente falha em validar a cadeia
SSL da AWS. Problema conhecido da comunidade DuckDB, especialmente
comum em Windows corporativos com proxy mas também em Windows
domésticos com bundle interno desatualizado.

**Decisão**: adicionar ``certifi>=2024.0`` como dependência runtime
explícita e modificar ``configurar_s3()`` para automaticamente detectar
``certifi`` e configurar ``SET ca_cert_file=<path>`` no DuckDB antes
de qualquer request S3. Aceitar parâmetro opcional ``ca_cert_file``
para permitir override (ex: bundle corporativo interno).

**Consequências**:
- Positivas: garante validação SSL saudável mesmo em ambientes
  corporativos com CA store desatualizado
- Positivas: certifi já é dependência transitiva de ``requests``, que
  já estava no projeto — só formalizamos a dependência
- Positivas: aceita path customizado permite compatibilidade com
  ambientes corporativos que exigem bundle interno
- Neutras: adiciona ~250 KB ao venv (tamanho do certifi)
- Neutras: fallback gracioso (só emite AVISO se certifi ausente),
  não quebra em ambientes onde não é necessário
- **Ver ADR-008**: sozinho, este fix não resolvia o erro SSL do
  bucket VIDA porque a causa raiz era virtual-hosted-style URL com
  bucket que tem pontos no nome. ADR-008 completa a solução.

---

## ADR-006: Stack técnica DuckDB + GeoPandas + Leaflet

**Data**: 2026-09-23

**Contexto**: várias combinações de ferramentas resolveriam o
problema. Alternativas consideradas:
- PostgreSQL + PostGIS: requer servidor, complexidade operacional
- Pandas + Shapely puro: sem SQL, sem paralelismo automático
- Spark + Sedona: overkill para o escopo, requer cluster
- QGIS Server: não é biblioteca, foge do escopo Python

**Decisão**:
- **DuckDB** com extensões `httpfs` (S3) e `spatial` (SQL espacial) —
  in-process, zero configuração, performance excelente
- **GeoPandas** para I/O de AOIs e validação geométrica
- **Leaflet** para o webmap (CDN, sem build) em vez de MapLibre GL
  (mais moderno mas requer build para custom styles)

**Consequências**:
- Zero infra externa — `pip install` e roda
- Deploy do webmap via GitHub Pages sem qualquer etapa de build
- Leaflet é biblioteca estável desde 2011, aprendizado amplamente
  disponível
- Se quisermos vetor tiles no futuro, migração para MapLibre GL é
  incremental
