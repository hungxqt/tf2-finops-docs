[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$serviceRoot = Split-Path -Parent $PSScriptRoot
$buildDirectory = Join-Path $serviceRoot "build"
$stagingDirectory = Join-Path $buildDirectory "package"
$sourceDirectory = Join-Path $serviceRoot "src"
$requirementsPath = Join-Path $serviceRoot "requirements.txt"
$zipPath = Join-Path $buildDirectory "state-lambda.zip"

function Find-Python314 {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $runtimes = & py -0p
        foreach ($line in $runtimes) {
            if ($line -match '3\.14[^ ]*\s+(.+python\.exe)$') {
                return $Matches[1].Trim()
            }
        }
    }

    foreach ($name in @("python3.14", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            continue
        }
        $version = & $command.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.14") {
            return $command.Source
        }
    }

    throw "Python 3.14 is required. Install it and ensure it appears in 'py -0p' or PATH."
}

$python = Find-Python314
$version = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne "3.14") {
    throw "Python 3.14 is required. Detected: $version"
}

if (Test-Path -LiteralPath $buildDirectory) {
    Remove-Item -LiteralPath $buildDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingDirectory -Force | Out-Null

try {
    & $python -m pip install `
        --requirement $requirementsPath `
        --target $stagingDirectory `
        --disable-pip-version-check `
        --no-compile
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE"
    }

    Copy-Item -LiteralPath (Join-Path $sourceDirectory "lambda_function.py") -Destination $stagingDirectory
    Copy-Item -LiteralPath (Join-Path $sourceDirectory "service.py") -Destination $stagingDirectory
    Copy-Item -LiteralPath (Join-Path $sourceDirectory "s3_store.py") -Destination $stagingDirectory

    $stagingForPython = $stagingDirectory.Replace("\", "\\")
    & $python -c "import sys; sys.path.insert(0, r'$stagingForPython'); import lambda_function; assert callable(lambda_function.lambda_handler)"
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged Lambda import check failed with exit code $LASTEXITCODE"
    }

    Compress-Archive `
        -Path (Join-Path $stagingDirectory "*") `
        -DestinationPath $zipPath `
        -CompressionLevel Optimal

    $zip = Get-Item -LiteralPath $zipPath
    $hash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256

    [pscustomobject]@{
        Artifact  = $zip.FullName
        Runtime   = "python3.14"
        SizeBytes = $zip.Length
        SHA256    = $hash.Hash
    }
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
    }
}
