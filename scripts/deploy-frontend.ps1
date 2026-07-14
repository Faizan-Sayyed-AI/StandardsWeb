<#
.SYNOPSIS
    Build and deploy the React frontend to S3 + CloudFront with correct MIME types.

.DESCRIPTION
    S3 stores whatever Content-Type is set at upload time (default: binary/octet-stream),
    and browsers refuse to execute ES module scripts served with the wrong MIME type.
    This script uploads .js and .css with explicit Content-Type headers and then
    invalidates the CloudFront cache so the fixed headers are actually served.

.EXAMPLE
    .\scripts\deploy-frontend.ps1 -BucketName ists-frontend-prod -ApiUrl https://api.yourdomain.com -DistributionId E1ABCDEF23456

.EXAMPLE
    .\scripts\deploy-frontend.ps1 -BucketName ists-frontend-prod -ApiUrl https://api.yourdomain.com -SkipBuild -DryRun
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$BucketName,

    [Parameter(Mandatory = $true)]
    [string]$ApiUrl,

    # CloudFront distribution to invalidate. Omit only for S3-website-only hosting.
    [string]$DistributionId,

    # Reuse the existing frontend/dist instead of rebuilding.
    [switch]$SkipBuild,

    # Pass --dryrun to all aws s3 sync commands (no invalidation is created either).
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "frontend"
$distDir = Join-Path $frontendDir "dist"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI not found on PATH. Install it and run 'aws configure' first."
}

# --- 1. Build -----------------------------------------------------------
if (-not $SkipBuild) {
    Write-Host "Building frontend (VITE_API_URL=$ApiUrl)..." -ForegroundColor Cyan
    Push-Location $frontendDir
    try {
        $env:VITE_API_URL = $ApiUrl
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
    }
    finally {
        Remove-Item env:VITE_API_URL -ErrorAction SilentlyContinue
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $distDir "index.html"))) {
    throw "No build output at $distDir. Run without -SkipBuild."
}

$dryRunFlag = @()
if ($DryRun) { $dryRunFlag = @("--dryrun") }

# --- 2. Upload with explicit MIME types ----------------------------------
# Everything except js/css first (aws cli guesses most of these correctly),
# then js/css with forced Content-Type. --delete prunes old hashed bundles.
Write-Host "Syncing assets to s3://$BucketName ..." -ForegroundColor Cyan
aws s3 sync $distDir "s3://$BucketName/" --delete --exclude "*.js" --exclude "*.css" @dryRunFlag
if ($LASTEXITCODE -ne 0) { throw "s3 sync (general assets) failed" }

aws s3 sync $distDir "s3://$BucketName/" --exclude "*" --include "*.js" --content-type "text/javascript" @dryRunFlag
if ($LASTEXITCODE -ne 0) { throw "s3 sync (js) failed" }

aws s3 sync $distDir "s3://$BucketName/" --exclude "*" --include "*.css" --content-type "text/css" @dryRunFlag
if ($LASTEXITCODE -ne 0) { throw "s3 sync (css) failed" }

# --- 3. Invalidate CloudFront ---------------------------------------------
# Required: CloudFront caches responses *including* Content-Type headers.
if ($DistributionId -and -not $DryRun) {
    Write-Host "Invalidating CloudFront distribution $DistributionId ..." -ForegroundColor Cyan
    aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*"
    if ($LASTEXITCODE -ne 0) { throw "CloudFront invalidation failed" }
}
elseif (-not $DistributionId) {
    Write-Host "No -DistributionId given - skipping CloudFront invalidation." -ForegroundColor Yellow
}

# --- 4. Verify ------------------------------------------------------------
if (-not $DryRun) {
    $jsKey = (Get-ChildItem (Join-Path $distDir "assets") -Filter "*.js" | Select-Object -First 1).Name
    $contentType = aws s3api head-object --bucket $BucketName --key "assets/$jsKey" --query "ContentType" --output text
    if ($contentType -ne "text/javascript") {
        throw "Verification FAILED: assets/$jsKey has Content-Type '$contentType' (expected text/javascript)"
    }
    Write-Host "Verified: assets/$jsKey served as text/javascript" -ForegroundColor Green
}

Write-Host "Deploy complete." -ForegroundColor Green
