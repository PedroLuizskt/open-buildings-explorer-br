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
