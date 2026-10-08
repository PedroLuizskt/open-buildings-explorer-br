# Screenshots do webmap

Imagens referenciadas no `README.md` principal. Para preencher:

1. Rode o webmap localmente: `obr-explorer webmap --pular-carga --db-path .\dados_br.duckdb --min-area-m2 30 --simplify-tolerance 1e-5`
2. Serve local: `python -m http.server 8000 --directory webmap`
3. Abra `http://localhost:8000`
4. Capture (Windows: `Win+Shift+S`) as duas imagens abaixo e salve neste diretorio

## Imagens esperadas pelo README

| Arquivo | Conteúdo recomendado |
|---------|---------------------|
| `webmap_uberlandia.png` | Vista geral de Uberlândia/MG com camadas Google e Microsoft visíveis, zoom cobrindo área urbana consolidada. Ideal: 1600×900 px |
| `webmap_dashboard.png` | Painel lateral aberto na tab "Visão Geral" ou "Análise" mostrando KPIs, donut e metadata IBGE. Zoom pode mostrar bairro específico. Ideal: 1600×900 px |

## Opcionais (não referenciadas no README atualmente)

- `webmap_popup.png` — popup rico aberto em uma edificação específica
- `webmap_detalhe.png` — tab "Detalhe" com info do footprint selecionado
- `webmap_cambuquira.png` — mesma composição para a AOI de Cambuquira
- `cli_analyze.png` — screenshot da CLI rodando `obr-explorer analyze`

Formatos aceitos: PNG (preferido para capturas de interface), JPG (para fotos).
Ignorar tamanhos excessivos — o GitHub comprime automaticamente, mas prefira
arquivos abaixo de 2 MB cada para carregamento rápido no README.
