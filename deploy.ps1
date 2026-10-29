# ==============================================================================
# HealthSlip AI - Production Deployment Automation (PowerShell)
# ==============================================================================

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "🩺 HealthSlip AI Production Deployment Launcher" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Check if Docker is installed
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Host "❌ Docker is not installed or not in PATH." -ForegroundColor Red
    Write-Host "💡 Running directly via Python ASGI server..." -ForegroundColor Yellow
    python -m uvicorn main:app --host 0.0.0.0 --port 8005
    exit
}

# 2. Check docker compose
$composeCmd = "docker compose"
try {
    docker compose version | Out-Null
} catch {
    $composeCmd = "docker-compose"
}

Write-Host "📦 Orchestrating containers via $composeCmd..." -ForegroundColor Green
Invoke-Expression "$composeCmd down --remove-orphans"
Invoke-Expression "$composeCmd build"
Invoke-Expression "$composeCmd up -d"

Write-Host "⏳ Checking service health..." -ForegroundColor Yellow
$maxRetries = 15
$counter = 0
$healthy = $false

while ($counter -lt $maxRetries) {
    Start-Sleep -Seconds 3
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:8005/api/health" -TimeoutSec 3 -ErrorAction Stop
        if ($res.status -eq "online") {
            $healthy = $true
            break
        }
    } catch {
        Write-Host "   Waiting for application to boot... ($($counter + 1)/$maxRetries)"
    }
    $counter++
}

if ($healthy) {
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "✅ HealthSlip AI successfully deployed!" -ForegroundColor Green
    Write-Host "🌐 Application URL: http://localhost:8005" -ForegroundColor Cyan
    Write-Host "📖 Swagger API Docs: http://localhost:8005/docs" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Green
} else {
    Write-Host "⚠️ Could not verify health check. Inspecting logs:" -ForegroundColor Red
    Invoke-Expression "$composeCmd logs --tail=30 app"
}
