# tasks.ps1 — atalhos de desenvolvimento para Windows/PowerShell.
# Equivalente Unix/Mac esta em Makefile.
#
# Uso: .\tasks.ps1 <comando>
# Exemplos:
#   .\tasks.ps1 setup
#   .\tasks.ps1 test
#   .\tasks.ps1 lint

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'test', 'test-network', 'lint', 'format', 'notebook', 'clean')]
    [string]$Command = 'help'
)

$ErrorActionPreference = 'Stop'

$VenvDir = ".venv"
$PythonExe = ".\$VenvDir\Scripts\python.exe"
$PipExe = ".\$VenvDir\Scripts\pip.exe"

function Show-Help {
    Write-Host "Comandos disponiveis:"
    Write-Host "  setup         - Cria venv, instala pacote em modo editavel com extras dev+notebook"
    Write-Host "  test          - Roda suite pytest offline com cobertura"
    Write-Host "  test-network  - Roda testes que dependem de acesso ao S3 publico"
    Write-Host "  lint          - Executa ruff check sobre o codigo"
    Write-Host "  format        - Aplica ruff format"
    Write-Host "  notebook      - Sobe Jupyter Lab na pasta notebooks/"
    Write-Host "  clean         - Remove artefatos de build, cache e cobertura"
    Write-Host ""
    Write-Host "Exemplo: .\tasks.ps1 setup"
}

function Invoke-Setup {
    Write-Host "[SETUP] Criando ambiente virtual em $VenvDir\"
    if (-not (Test-Path $VenvDir)) {
        python -m venv $VenvDir
    } else {
        Write-Host "[AVISO] $VenvDir\ ja existe, pulando criacao"
    }

    & $PipExe install --upgrade pip
    & $PipExe install -e ".[dev,notebook]"

    Write-Host ""
    Write-Host "[OK] Setup concluido."
    Write-Host "[OK] Ative com: .\$VenvDir\Scripts\Activate.ps1"
    Write-Host ""
    Write-Host "[OK] Rodando suite inicial para confirmar instalacao..."
    & $PythonExe -m pytest tests/ -q
}

function Invoke-Test {
    & $PythonExe -m pytest tests/
}

function Invoke-TestNetwork {
    & $PythonExe -m pytest tests/ -m network
}

function Invoke-Lint {
    & $PythonExe -m ruff check src/ tests/
}

function Invoke-Format {
    & $PythonExe -m ruff format src/ tests/
}

function Invoke-Notebook {
    & $PythonExe -m jupyter lab --notebook-dir=notebooks/
}

function Invoke-Clean {
    Write-Host "[CLEAN] Removendo artefatos de build e cache..."

    $toRemove = @(
        'build', 'dist', '.pytest_cache', '.ruff_cache', '.coverage',
        'htmlcov', 'reports\coverage'
    )
    foreach ($item in $toRemove) {
        if (Test-Path $item) {
            Remove-Item -Recurse -Force $item -ErrorAction SilentlyContinue
        }
    }

    Get-ChildItem -Path . -Include '*.egg-info' -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Get-ChildItem -Path . -Include '__pycache__' -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Get-ChildItem -Path . -Include '.ipynb_checkpoints' -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host "[OK] Limpeza concluida."
}

switch ($Command) {
    'help'         { Show-Help }
    'setup'        { Invoke-Setup }
    'test'         { Invoke-Test }
    'test-network' { Invoke-TestNetwork }
    'lint'         { Invoke-Lint }
    'format'       { Invoke-Format }
    'notebook'     { Invoke-Notebook }
    'clean'        { Invoke-Clean }
}
