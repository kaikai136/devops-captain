$ErrorActionPreference = 'Stop'

$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $BackendDir
$LocalConfig = Join-Path $RepoRoot 'config\local.app.conf'

function Read-AppConfig {
    param([string]$Path)

    $config = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Local startup config not found: $Path"
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) {
            continue
        }
        $name, $value = $line.Split('=', 2)
        $config[$name.Trim()] = $value.Trim()
    }
    return $config
}

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $resolved = (Resolve-Path -LiteralPath $WindowsPath).Path
    $converted = (& wsl.exe -e wslpath -a $resolved).Trim()
    if (-not $converted) {
        throw "Unable to convert Windows path to WSL path: $WindowsPath"
    }
    return $converted
}

function Convert-ToBashSingleQuoted {
    param([string]$Value)
    return "'" + ($Value -replace "'", "'\''") + "'"
}

$config = Read-AppConfig $LocalConfig
$backendHost = if ($config.ContainsKey('BACKEND_HOST') -and $config['BACKEND_HOST']) { $config['BACKEND_HOST'] } else { '0.0.0.0' }
$backendPort = if ($config.ContainsKey('BACKEND_PORT') -and $config['BACKEND_PORT']) { $config['BACKEND_PORT'] } else { '8001' }

$wslBackendDir = Convert-ToWslPath $BackendDir
$wslConfigPath = Convert-ToWslPath $LocalConfig
$config['APP_CONFIG_FILE'] = $wslConfigPath
$envExports = foreach ($key in ($config.Keys | Sort-Object)) {
    if ($key -match '^[A-Za-z_][A-Za-z0-9_]*$') {
        "export $key=$(Convert-ToBashSingleQuoted $config[$key])"
    }
}
$envScript = $envExports -join '; '

Write-Host "Using local config: $LocalConfig"
Write-Host "Starting backend on ${backendHost}:${backendPort}"

wsl.exe -e bash -lc "export PATH=~/venv-opstool/bin:`$PATH; $envScript; cd '$wslBackendDir' && ~/venv-opstool/bin/python manage.py run_database_transfer_worker --poll-interval 1 >/tmp/database-transfer-worker.log 2>&1 & exec ~/venv-opstool/bin/python -m daphne -b '$backendHost' -p '$backendPort' ops_tool.asgi:application"
