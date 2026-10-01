param(
    [switch]$SkipImageChecks,
    [string]$ImageName = 'devops-tools:config-file-test'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$deployDir = Join-Path $root 'deploy'
$defaultConfig = Join-Path $deployDir 'config\app.conf'
$compose = Join-Path $deployDir 'docker-compose.yml'
$dockerfile = Join-Path $deployDir 'Dockerfile'
$entrypoint = Join-Path $deployDir 'docker\entrypoint.sh'
$settings = Join-Path $root 'backend\ops_tool\settings.py'
$requirements = Join-Path $root 'backend\requirements.txt'
$readme = Join-Path $root 'README.md'
$gitignore = Join-Path $root '.gitignore'
$gitattributes = Join-Path $root '.gitattributes'
$composeUp = Join-Path $deployDir 'scripts\compose-up.sh'
$buildImage = Join-Path $deployDir 'scripts\build-image.sh'
$deployRemote = Join-Path $deployDir 'scripts\deploy-remote.sh'
$entrypointLifecycleTest = Join-Path $deployDir 'scripts\tests\test-entrypoint-secret.sh'
$remoteConfigTest = Join-Path $deployDir 'scripts\tests\test-deploy-remote-env.sh'
$k8sConfigMap = Join-Path $deployDir 'k8s\configmap.yaml'
$k8sDeploymentApp = Join-Path $deployDir 'k8s\deployment-app.yaml'
$k8sDeploymentSshGateway = Join-Path $deployDir 'k8s\deployment-ssh-gateway.yaml'
$k8sService = Join-Path $deployDir 'k8s\service.yaml'
$k8sPvc = Join-Path $deployDir 'k8s\pvc.yaml'

function Assert-Match {
    param([string]$Text, [string]$Pattern, [string]$Message)
    if ($Text -notmatch $Pattern) { throw $Message }
}

function Invoke-Docker {
    param([string[]]$Arguments)
    $output = & docker @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }
    return @($output)
}

foreach ($rootDeployFile in @('docker-compose.yml', 'Dockerfile', '.env', 'docker\entrypoint.sh', 'scripts\compose-up.sh', 'scripts\build-image.sh', 'scripts\deploy-remote.sh')) {
    if (Test-Path (Join-Path $root $rootDeployFile)) { throw "Deployment artifact remains outside deploy/: $rootDeployFile" }
}

if (-not (Test-Path $defaultConfig)) { throw 'Tracked deploy/config/app.conf is missing.' }
$configText = Get-Content -Raw -Encoding UTF8 $defaultConfig
Assert-Match $configText '(?m)^DJANGO_SECRET_KEY=\r?$' 'Default config secret must be empty.'
Assert-Match $configText '(?m)^DJANGO_SECRET_KEY_FILE=/app/data/django-secret-key\r?$' 'Default config secret file path is missing.'
Assert-Match $configText '(?m)^DJANGO_ALLOWED_HOSTS=\*\r?$' 'Default hosts must support zero-setup startup.'
Assert-Match $configText '(?m)^DATABASE_ENGINE=(mysql|sqlite|sqlite3)\r?$' 'Default deployment config must choose mysql or sqlite.'
Assert-Match $configText '(?m)^DATABASE_HOST=(?!mysql\r?$).+\r?$' 'Default deployment config must point at a remote MySQL host, not a Compose mysql service.'
Assert-Match $configText '(?m)^DATABASE_PORT=3306\r?$' 'Default deployment config must use the MySQL port.'
Assert-Match $configText '(?m)^DATABASE_NAME=devops_tools\r?$' 'Default deployment config must define the MySQL database name.'
Assert-Match $configText '(?m)^DATABASE_USER=devops_tools\r?$' 'Default deployment config must define the MySQL app user.'
Assert-Match $configText '(?m)^DATABASE_PASSWORD=' 'Default deployment config must define the MySQL app password.'
if ($configText -match '(?m)^DATABASE_ROOT_PASSWORD=') { throw 'Default config still contains local MySQL root initialization settings.' }
foreach ($suffix in @('ENABLED', 'HOST', 'PORT', 'PASSWORD', 'DB', 'KEY_PREFIX')) {
    $forbidden = "RE" + "DIS_$suffix"
    if ($configText -match [regex]::Escape($forbidden)) { throw "Default deployment config must not include removed cache service settings: $forbidden" }
}

$gitignoreText = Get-Content -Raw -Encoding UTF8 $gitignore
if ($gitignoreText -match '(?m)^!/.env\r?$') { throw 'Root .env is still explicitly allowed by .gitignore.' }
Assert-Match $gitignoreText '(?m)^\.env\r?$' '.gitignore must continue to ignore private env files.'
Assert-Match $gitignoreText '(?m)^deploy/config/\*\.local\.conf\r?$' '.gitignore must ignore private deploy config overrides.'

if (-not (Test-Path $gitattributes)) { throw '.gitattributes is missing; shell scripts may be checked out with CRLF.' }
$gitattributesText = Get-Content -Raw -Encoding UTF8 $gitattributes
Assert-Match $gitattributesText '(?m)^\*\.sh text eol=lf\r?$' 'Shell scripts are not pinned to LF line endings.'
foreach ($shellScript in @($entrypoint, $composeUp, $buildImage, $deployRemote, $entrypointLifecycleTest, $remoteConfigTest)) {
    $shellBytes = [IO.File]::ReadAllBytes($shellScript)
    if ([Text.Encoding]::UTF8.GetString($shellBytes).Contains("`r")) { throw "Shell script contains CR line endings: $shellScript" }
}

$composeText = Get-Content -Raw -Encoding UTF8 $compose
if ($composeText -match '(?m)^\s*environment:\s*$') { throw 'Compose still injects environment variables.' }
if ($composeText -match '(?m)^\s*env_file:\s*$') { throw 'Compose still reads env files.' }
if ($composeText -match '\$\{') { throw 'Compose still interpolates host environment variables.' }
if ($composeText -match '(?m)^\s*configs:\s*$|app_config:|source:\s*app_config|target:\s*/app/config/app.conf') { throw 'Compose still mounts app.conf with configs instead of volumes.' }
foreach ($required in @('context: ..', 'dockerfile: deploy/Dockerfile', '../data:/app')) {
    if ($composeText -notmatch [regex]::Escape($required)) { throw "Compose is missing config-file deployment wiring: $required" }
}
foreach ($forbidden in @('./config/app.conf:/app/config/app.conf:ro', './config:/app/config:ro', '../data:/app/data', '../media:/app/media', '../rdp_recordings:/app/rdp_recordings', '/app/rdp_recordings', 'image: mysql:8.4', 'container_name: devops-tools-mysql', 'mysql_data:/var/lib/mysql', 'mysqladmin ping', 'docker-compose.mysql.yml', ('image: re' + 'dis:'), ('container_name: devops-tools-re' + 'dis'), ('re' + 'dis_data:/data'))) {
    if ($composeText -match [regex]::Escape($forbidden)) { throw "Base Compose should not require local database or removed cache service: $forbidden" }
}
$removedCacheService = 're' + 'dis'
if ($composeText -match "(?m)^  $removedCacheService`:\s*$") { throw 'Base Compose should not start the removed cache service.' }
if ($composeText -match '(?m)^\s*-\s+rdp_recordings:/app/rdp_recordings') { throw 'Compose still uses a named volume for RDP recordings.' }
if ($composeText -match '(?m)^  rdp_recordings:\s*$') { throw 'Compose still defines the RDP recordings named volume.' }

$dockerfileText = Get-Content -Raw -Encoding UTF8 $dockerfile
Assert-Match $dockerfileText 'COPY deploy/docker/entrypoint\.sh /entrypoint\.sh' 'Dockerfile does not copy the moved entrypoint.'
Assert-Match $dockerfileText 'WORKDIR /opt/devops-tools' 'Dockerfile must keep application code outside /app because /app is a runtime bind mount.'

$entrypointText = Get-Content -Raw -Encoding UTF8 $entrypoint
foreach ($required in @('APP_CONFIG_FILE', 'read_config_value', 'wait_for_database', 'DATABASE_ENGINE', 'DATABASE_HOST', 'DATABASE_PORT', 'Using DJANGO_SECRET_KEY from the config file.', 'DJANGO_SECRET_KEY_FILE', 'secrets.token_urlsafe', 'umask 077', 'chmod 600')) {
    if ($entrypointText -notmatch [regex]::Escape($required)) { throw "Entrypoint is missing: $required" }
}
if ($entrypointText -match 'export DJANGO_SECRET_KEY') { throw 'Entrypoint still exports DJANGO_SECRET_KEY.' }
if ($entrypointText -match 'database_host="mysql"') { throw 'Entrypoint still defaults MySQL host to a Compose service name.' }

$settingsText = Get-Content -Raw -Encoding UTF8 $settings
foreach ($required in @('load_config_file', 'APP_CONFIG_FILE', 'APP_CONFIG', 'config_value', 'config_bool', 'config_int', 'config_path', 'database_config', 'django.db.backends.mysql', 'pymysql.install_as_MySQLdb')) {
    if ($settingsText -notmatch [regex]::Escape($required)) { throw "Django settings are missing config-file loading: $required" }
}
foreach ($required in @('django.core.cache.backends.locmem.LocMemCache', 'django.contrib.sessions.backends.db', 'channels_redis.core.RedisChannelLayer')) {
    if ($settingsText -notmatch [regex]::Escape($required)) { throw "Django settings are missing local runtime config: $required" }
}
$removedKeys = @('ENABLED', 'HOST', 'PORT', 'PASSWORD', 'DB', 'KEY_PREFIX', 'URL') | ForEach-Object { "RE" + "DIS_$_" }
foreach ($forbidden in @($removedKeys + @('channels_' + ('re' + 'dis') + '.core.' + ('Re' + 'dis') + 'ChannelLayer', 'django.core.cache.backends.' + ('re' + 'dis') + '.' + ('Re' + 'dis') + 'Cache', '172.16.0.99', 'uLwHDyYr'))) {
    if ($settingsText -match [regex]::Escape($forbidden)) { throw "Django settings must not include removed cache service config: $forbidden" }
}

$requirementsText = Get-Content -Raw -Encoding UTF8 $requirements
Assert-Match $requirementsText '(?m)^PyMySQL>=1\.1,<2\.0\r?$' 'requirements.txt must include the MySQL driver.'
foreach ($forbidden in @(('re' + 'dis>='), ('channels-' + ('re' + 'dis')))) {
    if ($requirementsText -match [regex]::Escape($forbidden)) { throw "requirements.txt must not include removed cache service dependencies: $forbidden" }
}

$composeUpText = Get-Content -Raw -Encoding UTF8 $composeUp
if ($composeUpText -match '\.env|APP_PORT|IMAGE_NAME') { throw 'compose-up.sh still depends on environment-style deployment config.' }
foreach ($forbidden in @('read_config_value', 'DATABASE_ENGINE', 'docker-compose.mysql.yml', 'compose_files')) {
    if ($composeUpText -match [regex]::Escape($forbidden)) { throw "compose-up.sh still contains local MySQL Compose selection: $forbidden" }
}
foreach ($required in @('docker compose -f "$DEPLOY_DIR/docker-compose.yml" up -d --build', 'docker compose -f "$DEPLOY_DIR/docker-compose.yml" ps')) {
    if ($composeUpText -notmatch [regex]::Escape($required)) { throw "compose-up.sh is missing single Compose-file startup: $required" }
}
foreach ($required in @('"$REPO_ROOT/data/config"', '"$REPO_ROOT/data/data"', '"$REPO_ROOT/data/media"', '"$REPO_ROOT/data/recordings"', '$REPO_ROOT/data/config/app.conf')) {
    if ($composeUpText -notmatch [regex]::Escape($required)) { throw "compose-up.sh is missing runtime data-root handling: $required" }
}

$buildImageText = Get-Content -Raw -Encoding UTF8 $buildImage
Assert-Match $buildImageText 'IMAGE_NAME="\$\{1:-devops-tools:latest\}"' 'build-image.sh should accept image name as an argument, not an environment variable.'
Assert-Match $buildImageText 'docker build -f "\$DEPLOY_DIR/Dockerfile" -t "\$IMAGE_NAME" "\$REPO_ROOT"' 'build-image.sh does not use the moved Dockerfile.'

$deployRemoteText = Get-Content -Raw -Encoding UTF8 $deployRemote
foreach ($required in @('CONFIG_PATH="data/config/app.conf"', 'CONFIG_BACKUP', 'mktemp', 'cp "$APP_DIR/$CONFIG_PATH" "$CONFIG_BACKUP"', 'cp "$CONFIG_BACKUP" "$CONFIG_PATH"', 'mkdir -p data/config data/data data/media data/recordings', '"${COMPOSE[@]}" -f deploy/docker-compose.yml up -d --build', '"${COMPOSE[@]}" -f deploy/docker-compose.yml ps')) {
    if ($deployRemoteText -notmatch [regex]::Escape($required)) { throw "deploy-remote.sh is missing private config preservation: $required" }
}
if ($deployRemoteText -match [regex]::Escape('git -C "$APP_DIR" checkout -- "$CONFIG_PATH"')) { throw 'deploy-remote.sh should not treat runtime data/config/app.conf as a tracked Git file.' }
foreach ($forbidden in @('read_config_value', 'DATABASE_ENGINE', 'docker-compose.mysql.yml', 'compose_files')) {
    if ($deployRemoteText -match [regex]::Escape($forbidden)) { throw "deploy-remote.sh still contains local MySQL Compose selection: $forbidden" }
}
if ($deployRemoteText -match 'APP_PORT_OVERRIDE|cp "\$ENV_BACKUP" \.env|--env-file|cat > \.env') { throw 'deploy-remote.sh still preserves or injects env-file deployment config.' }

$readmeText = Get-Content -Raw -Encoding UTF8 $readme
foreach ($required in @('deploy/docker-compose.yml', 'deploy/config/app.conf', 'deploy/scripts/compose-up.sh', 'data/config/app.conf', '/app/config/app.conf', '/app/data/django-secret-key', '/app/recordings', 'DATABASE_ENGINE=mysql', 'DATABASE_ENGINE=sqlite', 'mysql.example.com')) {
    if ($readmeText -notmatch [regex]::Escape($required)) { throw "README is missing: $required" }
}
foreach ($forbidden in @('deploy/docker-compose.mysql.yml', 'mysql_data:/var/lib/mysql', 'DATABASE_ROOT_PASSWORD')) {
    if ($readmeText -match [regex]::Escape($forbidden)) { throw "README still documents local MySQL deployment: $forbidden" }
}

$k8sConfigMapText = Get-Content -Raw -Encoding UTF8 $k8sConfigMap
foreach ($required in @('kind: ConfigMap', 'name: devops-tools-config', 'app.conf: |', 'DATABASE_ENGINE=sqlite', 'DATABASE_HOST=mysql.example.com', 'DJANGO_CSRF_TRUSTED_ORIGINS=', 'GUACD_HOST=guacd', 'RDP_RECORDING_ROOT=/app/recordings', 'SSH_GATEWAY_PORT=2222', 'SSH_GATEWAY_PUBLIC_HOST=')) {
    if ($k8sConfigMapText -notmatch [regex]::Escape($required)) { throw "Kubernetes ConfigMap is missing app.conf config: $required" }
}
foreach ($suffix in @('ENABLED', 'HOST', 'PORT', 'PASSWORD', 'DB', 'KEY_PREFIX')) {
    $forbidden = "RE" + "DIS_$suffix"
    if ($k8sConfigMapText -match [regex]::Escape($forbidden)) { throw "Kubernetes ConfigMap must not include removed cache service settings: $forbidden" }
}
foreach ($forbidden in @('APP_PORT:', 'DATABASE_ROOT_PASSWORD', 'mysql_data', 'docker-compose.mysql.yml')) {
    if ($k8sConfigMapText -match [regex]::Escape($forbidden)) { throw "Kubernetes ConfigMap still contains non-compose deployment config: $forbidden" }
}

$k8sDeploymentText = (Get-Content -Raw -Encoding UTF8 $k8sDeploymentApp) + [Environment]::NewLine + (Get-Content -Raw -Encoding UTF8 $k8sDeploymentSshGateway)
foreach ($forbidden in @('envFrom:', 'secretRef:', 'configMapRef:', 'name: devops-tools-secret', 'command: ["python", "manage.py", "run_ssh_gateway"]', 'containerPort: 32751', 'port: 32751', 'mountPath: /app/data', 'mountPath: /app/media', 'mountPath: /app/rdp_recordings', 'image: mysql', 'mysql_data', 'name: NODE_IP', 'name: DJANGO_CSRF_TRUSTED_ORIGINS', 'name: SSH_GATEWAY_PUBLIC_HOST')) {
    if ($k8sDeploymentText -match [regex]::Escape($forbidden)) { throw "Kubernetes Deployment is not aligned with Compose config-file deployment: $forbidden" }
}
foreach ($required in @('name: devops-tools-app', 'name: devops-tools-ssh-gateway', 'image: harbor.xunsiya.com:7891/devops/devops-tools:latest', 'containerPort: 8001', 'containerPort: 2222', 'args: ["python", "manage.py", "run_ssh_gateway"]', 'initContainers:', 'mkdir -p /app/config /app/data /app/media /app/recordings', 'mountPath: /app', 'mountPath: /app/config/app.conf', 'subPath: app.conf', 'readOnly: true', 'claimName: devops-tools-runtime-pvc', 'name: app-config', 'configMap:', 'name: devops-tools-config')) {
    if ($k8sDeploymentText -notmatch [regex]::Escape($required)) { throw "Kubernetes Deployment is missing Compose-aligned wiring: $required" }
}

$k8sServiceText = Get-Content -Raw -Encoding UTF8 $k8sService
foreach ($required in @('name: devops-tools-app', 'type: NodePort', 'port: 8001', 'targetPort: http', 'nodePort: 30271', 'name: devops-tools-ssh-gateway', 'port: 2222', 'targetPort: ssh', 'nodePort: 30222')) {
    if ($k8sServiceText -notmatch [regex]::Escape($required)) { throw "Kubernetes Service is missing Compose-aligned ports: $required" }
}
foreach ($forbidden in @('port: 32751', 'targetPort: 32751', 'port: 22022', 'nodePort: 30001')) {
    if ($k8sServiceText -match [regex]::Escape($forbidden)) { throw "Kubernetes Service still contains old port mapping: $forbidden" }
}

$k8sPvcText = Get-Content -Raw -Encoding UTF8 $k8sPvc
foreach ($required in @('name: devops-tools-runtime-pvc', 'ReadWriteMany')) {
    if ($k8sPvcText -notmatch [regex]::Escape($required)) { throw "Kubernetes PVC is missing shared volume claim: $required" }
}
foreach ($forbidden in @('name: devops-tools-data-pvc', 'name: devops-tools-media-pvc', 'name: devops-tools-recordings-pvc')) {
    if ($k8sPvcText -match [regex]::Escape($forbidden)) { throw "Kubernetes PVC still uses split runtime claims: $forbidden" }
}

Write-Host 'Static deployment contract checks passed.'
if ($SkipImageChecks) { Write-Host 'Image lifecycle checks skipped.'; exit 0 }

& docker image inspect $ImageName *> $null
if ($LASTEXITCODE -ne 0) { throw "Image '$ImageName' is not available. Build it before running image checks." }

$explicitSecret = 'explicit-test-secret'
$runtimeConfigDir = Join-Path ([IO.Path]::GetTempPath()) "devops-tools-config-test-$([Guid]::NewGuid().ToString('N'))"
$runtimeRoot = Join-Path $runtimeConfigDir 'runtime'
$runtimeConfig = Join-Path $runtimeRoot 'config\app.conf'
$explicitRuntimeConfig = Join-Path $runtimeConfigDir 'explicit.conf'
$assertCommand = 'import os; from pathlib import Path; import ops_tool.settings as settings; path=Path("/app/data/django-secret-key"); assert path.is_file(); persisted=path.read_text(encoding="utf-8").strip(); assert persisted; assert settings.SECRET_KEY == persisted; assert not os.environ.get("DJANGO_SECRET_KEY")'
$explicitCommand = 'import os; from pathlib import Path; import ops_tool.settings as settings; path=Path("/app/data/django-secret-key"); assert path.is_file(); assert settings.SECRET_KEY == "explicit-test-secret"; assert path.read_text(encoding="utf-8").strip() != settings.SECRET_KEY; assert not os.environ.get("DJANGO_SECRET_KEY")'

try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $runtimeConfig) | Out-Null
    Set-Content -Path $runtimeConfig -Encoding UTF8 -NoNewline -Value "DJANGO_SECRET_KEY=`nDJANGO_SECRET_KEY_FILE=/app/data/django-secret-key`n"
    Set-Content -Path $explicitRuntimeConfig -Encoding UTF8 -NoNewline -Value "DJANGO_SECRET_KEY=$explicitSecret`nDJANGO_SECRET_KEY_FILE=/app/data/django-secret-key`n"
    $firstLogs = Invoke-Docker @('run', '--rm', '-v', "${runtimeRoot}:/app", $ImageName, 'python', '-c', $assertCommand)
    $secret = (Invoke-Docker @('run', '--rm', '--entrypoint', 'python', '-v', "${runtimeRoot}:/app", $ImageName, '-c', 'from pathlib import Path; print(Path("/app/data/django-secret-key").read_text().strip())') -join '').Trim()
    if (-not $secret) { throw 'Generated secret file is empty.' }
    if (($firstLogs -join "`n") -match [regex]::Escape($secret)) { throw 'Generated secret leaked into container logs.' }
    if (($firstLogs -join "`n") -notmatch 'Generated and persisted a new Django secret key') { throw 'First run did not report generated secret source.' }

    $firstHash = (Invoke-Docker @('run', '--rm', '--entrypoint', 'python', '-v', "${runtimeRoot}:/app", $ImageName, '-c', 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("/app/data/django-secret-key").read_bytes()).hexdigest())') -join '').Trim()
    $mode = (Invoke-Docker @('run', '--rm', '--entrypoint', 'python', '-v', "${runtimeRoot}:/app", $ImageName, '-c', 'from pathlib import Path; print(oct(Path("/app/data/django-secret-key").stat().st_mode & 0o777))') -join '').Trim()
    if ($mode -ne '0o600') { throw "Generated secret mode is $mode instead of 0o600." }

    $secondLogs = Invoke-Docker @('run', '--rm', '-v', "${runtimeRoot}:/app", $ImageName, 'python', '-c', $assertCommand)
    $secondHash = (Invoke-Docker @('run', '--rm', '--entrypoint', 'python', '-v', "${runtimeRoot}:/app", $ImageName, '-c', 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("/app/data/django-secret-key").read_bytes()).hexdigest())') -join '').Trim()
    if ($secondHash -ne $firstHash) { throw 'Persisted secret changed on the second start.' }
    if (($secondLogs -join "`n") -notmatch 'Using the persisted Django secret key') { throw 'Second run did not report persisted secret source.' }
    if (($secondLogs -join "`n") -match [regex]::Escape($secret)) { throw 'Persisted secret leaked into container logs.' }

    Copy-Item -LiteralPath $explicitRuntimeConfig -Destination $runtimeConfig -Force
    $explicitLogs = Invoke-Docker @('run', '--rm', '-v', "${runtimeRoot}:/app", $ImageName, 'python', '-c', $explicitCommand)
    if (($explicitLogs -join "`n") -notmatch 'Using DJANGO_SECRET_KEY from the config file') { throw 'Explicit config secret did not take precedence.' }
    if (($explicitLogs -join "`n") -match [regex]::Escape($explicitSecret)) { throw 'Explicit secret leaked into container logs.' }

    $finalHash = (Invoke-Docker @('run', '--rm', '--entrypoint', 'python', '-v', "${runtimeRoot}:/app", $ImageName, '-c', 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("/app/data/django-secret-key").read_bytes()).hexdigest())') -join '').Trim()
    if ($finalHash -ne $firstHash) { throw 'Explicit config secret modified the persisted secret file.' }
    Write-Host 'Image secret lifecycle checks passed.'
}
finally {
    Remove-Item -Recurse -Force -LiteralPath $runtimeConfigDir -ErrorAction SilentlyContinue
}
