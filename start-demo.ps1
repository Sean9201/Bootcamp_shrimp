# Bootcamp_shrimp demo launcher: starts backend (8000) and frontend (5500) in new windows, then opens the browser.
# Usage (PowerShell, repo root):  powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
# Prerequisites: ai/artifacts (trained model + baselines), data_pipeline/data/synthetic/mock_v1 (demo samples),
#                frontend/node_modules (npm ci), backend/.env (Gemini key, optional).
$root = $PSScriptRoot
$py = Join-Path $root "..\.venv\Scripts\python.exe"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; & '$py' -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "Waiting for backend (model loading takes a few seconds)..."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2 | Out-Null; $ok = $true; break }
    catch { Start-Sleep -Seconds 1 }
}
if ($ok) { Write-Host "Backend ready."; Start-Process "http://localhost:5500/analyze" }
else { Write-Host "Backend did not start. Check the backend window for errors." }
