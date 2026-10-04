param(
    [Parameter(Mandatory = $false)]
    [string]$FilePath,

    [Parameter(Mandatory = $false)]
    [string]$PfxPath,

    [Parameter(Mandatory = $false)]
    [string]$PfxPassword,

    [Parameter(Mandatory = $false)]
    [string]$TimestampUrl,

    [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (-not (Test-Path $kitsRoot)) {
        throw "Windows SDK bin directory not found: $kitsRoot"
    }

    $candidates = Get-ChildItem -Path $kitsRoot -Filter signtool.exe -Recurse |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending

    $candidate = $candidates | Select-Object -First 1
    if ($null -eq $candidate) {
        throw "signtool.exe was not found in the Windows SDK"
    }
    return $candidate.FullName
}

$signtool = Find-SignTool
Write-Host "signtool=$signtool"

if ($ProbeOnly) {
    exit 0
}

if ([string]::IsNullOrWhiteSpace($FilePath)) {
    throw "FilePath is required"
}
if ([string]::IsNullOrWhiteSpace($PfxPath)) {
    throw "PfxPath is required"
}
if ([string]::IsNullOrWhiteSpace($PfxPassword)) {
    throw "PfxPassword is required"
}
if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    throw "TimestampUrl is required"
}
if (-not (Test-Path $FilePath)) {
    throw "File to sign does not exist: $FilePath"
}
if (-not (Test-Path $PfxPath)) {
    throw "PFX file does not exist: $PfxPath"
}

& $signtool sign `
    /f $PfxPath `
    /p $PfxPassword `
    /fd SHA256 `
    /tr $TimestampUrl `
    /td SHA256 `
    $FilePath

if ($LASTEXITCODE -ne 0) {
    throw "signtool sign failed with exit code $LASTEXITCODE"
}

& $signtool verify /pa /all /v $FilePath
if ($LASTEXITCODE -ne 0) {
    throw "signtool verification failed with exit code $LASTEXITCODE"
}

$signature = Get-AuthenticodeSignature -FilePath $FilePath
if ($signature.Status -ne "Valid") {
    throw "Windows Authenticode status is $($signature.Status), expected Valid"
}

Write-Host "Authenticode signature verified: $FilePath"
