# Add oxidized-ssh/id_rsa.pub as a Gitea deploy key (write access).
# Usage:
#   $env:GITEA_TOKEN = "your_token"
#   .\scripts\add_gitea_deploy_key.ps1
#
# Token: Gitea → Settings → Applications → Generate New Token (scope: write:repository)

param(
    [string]$GiteaUrl = "http://10.216.40.65:3000",
    [string]$Owner = "Oxidized",
    [string]$Repo = "sat_backup",
    [string]$KeyFile = (Join-Path $PSScriptRoot "..\oxidized-ssh\id_rsa.pub"),
    [string]$Title = "oxidized-backup"
)

$token = $env:GITEA_TOKEN
if (-not $token) {
    Write-Error "Set GITEA_TOKEN first (Gitea → Settings → Applications → Generate New Token, scope write:repository)."
    exit 1
}

if (-not (Test-Path $KeyFile)) {
    Write-Error "Public key not found: $KeyFile"
    exit 1
}

$pubKey = (Get-Content $KeyFile -Raw).Trim()
$fingerprint = (ssh-keygen -lf $KeyFile 2>$null)
Write-Host "Key file: $KeyFile"
Write-Host "Fingerprint: $fingerprint"

$uri = "$GiteaUrl/api/v1/repos/$Owner/$Repo/keys"
$body = @{
    key        = $pubKey
    title      = $Title
    read_only  = $false
} | ConvertTo-Json

try {
    $existing = Invoke-RestMethod -Uri $uri -Headers @{ Authorization = "token $token" }
    foreach ($k in $existing) {
        if ($k.key.Trim() -eq $pubKey) {
            Write-Host "Deploy key already exists (id=$($k.id), read_only=$($k.read_only))."
            if ($k.read_only) {
                Write-Warning "Key is read-only. Delete it in Gitea and re-run this script."
                exit 1
            }
            exit 0
        }
    }
} catch {
    Write-Warning "Could not list existing keys: $($_.Exception.Message)"
}

try {
    $result = Invoke-RestMethod -Uri $uri -Method Post `
        -Headers @{ Authorization = "token $token"; "Content-Type" = "application/json" } `
        -Body $body
    Write-Host "Deploy key added (id=$($result.id), read_only=$($result.read_only))."
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    $detail = $_.ErrorDetails.Message
    Write-Error "Failed ($status): $detail"
    exit 1
}

Write-Host ""
Write-Host "Verify:"
Write-Host "  docker exec -u oxidized oxidized ssh -T git@10.216.40.65"
