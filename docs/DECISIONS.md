# Log de Decisões Arquiteturais

Este arquivo registra as decisões técnicas tomadas no projeto, no
estilo Architecture Decision Records (ADR). Cada entrada tem
**Contexto**, **Decisão**, **Consequências**, e **Data**. Novas
decisões vão sendo adicionadas ao final, mantendo o histórico.

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
- Positivas: pipeline S3 funciona out-of-the-box no Windows sem
  intervenção manual; correção elegante que mantém validação SSL
  (mais seguro que desabilitar SSL, que era a alternativa "quick fix"
  mais comum na comunidade)
- Positivas: certifi já é dependência transitiva de ``requests``, que
  já estava no projeto — só formalizamos a dependência
- Positivas: aceita path customizado permite compatibilidade com
  ambientes corporativos que exigem bundle interno
- Neutras: adiciona ~250 KB ao venv (tamanho do certifi)
- Neutras: fallback gracioso (só emite AVISO se certifi ausente),
  não quebra em ambientes onde não é necessário

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
