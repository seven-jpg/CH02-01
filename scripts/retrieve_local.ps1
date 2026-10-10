# Local, offline launcher for scripts/retrieve.py. No activation is required.
# Relative CLI paths are interpreted from the repository root.
# All original arguments are forwarded; only a missing --index-path is added.

$ErrorActionPreference = 'Stop'
[string[]] $ForwardArgs = @($args)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot '.venv-retrieval\Scripts\python.exe'
$EntryPath = Join-Path $ProjectRoot 'scripts\retrieve.py'
$DefaultIndex = Join-Path $ProjectRoot 'search_indices\index_working'
$CacheHome = Join-Path $ProjectRoot 'search_indices\hf_home'
$HubCache = Join-Path $CacheHome 'hub'
$ExitCode = 1
$LocationChanged = $false
$SavedEnvironment = @{}

function Find-CliOption {
    param([string[]] $Arguments, [string] $Name)
    $Found = $false
    $Value = $null
    for ($Position = 0; $Position -lt $Arguments.Count; $Position++) {
        if ($Arguments[$Position] -ceq $Name) {
            $Found = $true
            $Value = if ($Position + 1 -lt $Arguments.Count) { $Arguments[$Position + 1] } else { $null }
        } elseif ($Arguments[$Position].StartsWith($Name + '=', [StringComparison]::Ordinal)) {
            $Found = $true
            $Value = $Arguments[$Position].Substring($Name.Length + 1)
        }
    }
    return [pscustomobject] @{ Found = $Found; Value = $Value }
}

function Assert-LocalFile {
    param([string] $FilePath, [long] $ExpectedBytes = 0)
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "Required local file is missing: $FilePath. Finish the resource download first; this launcher will not download it."
    }
    $Item = Get-Item -LiteralPath $FilePath
    if ($Item.Length -le 0 -or ($ExpectedBytes -gt 0 -and $Item.Length -ne $ExpectedBytes)) {
        throw "Required local file has an unexpected size: $FilePath. Check the resource verification record before running."
    }
}

try {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Retrieval Python is missing: $PythonPath. Complete the separate .venv-retrieval environment first."
    }
    Push-Location -LiteralPath $ProjectRoot
    $LocationChanged = $true

    foreach ($Name in @('HF_HOME', 'HF_HUB_CACHE', 'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'ANONYMIZED_TELEMETRY')) {
        $SavedEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    [Environment]::SetEnvironmentVariable('HF_HOME', $CacheHome, 'Process')
    [Environment]::SetEnvironmentVariable('HF_HUB_CACHE', $HubCache, 'Process')
    [Environment]::SetEnvironmentVariable('HF_HUB_OFFLINE', '1', 'Process')
    [Environment]::SetEnvironmentVariable('TRANSFORMERS_OFFLINE', '1', 'Process')
    [Environment]::SetEnvironmentVariable('ANONYMIZED_TELEMETRY', 'False', 'Process')

    $HelpRequested = ($ForwardArgs -ccontains '--help') -or ($ForwardArgs -ccontains '-h')
    $IndexOption = Find-CliOption -Arguments $ForwardArgs -Name '--index-path'
    if (-not $IndexOption.Found) {
        $ForwardArgs += @('--index-path', $DefaultIndex)
        $LocalIndex = $DefaultIndex
    } else {
        $LocalIndex = $IndexOption.Value
    }

    # --help is available before large resources or heavy dependencies are ready.
    if (-not $HelpRequested) {
        if ([string]::IsNullOrWhiteSpace($LocalIndex) -or $LocalIndex.StartsWith('--')) {
            throw '--index-path needs a directory value. Use --help for the original CLI.'
        }
        $ConfigOption = Find-CliOption -Arguments $ForwardArgs -Name '--config'
        if (-not $ConfigOption.Found -or [string]::IsNullOrWhiteSpace($ConfigOption.Value) -or $ConfigOption.Value.StartsWith('--')) {
            throw '--config is required. Use experiments/m3/retrieval.json for the fixed top_k=5 baseline.'
        }
        $Config = Get-Content -LiteralPath $ConfigOption.Value -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Config.index_repo -cne 'crag-mm-2025/web-search-index-public-test' -or
            $Config.index_revision -cne 'bd32162ffb21626994ad86ab147793561ba8fad2' -or
            $Config.encoder_id -cne 'BAAI/bge-large-en-v1.5' -or
            $Config.encoder_revision -cne 'd4aa6901d3a41ba39fb536a557fa166f842b0e09') {
            throw 'This launcher checks only the pinned M3 Web index and BGE encoder. Use the original CLI for another resource configuration.'
        }

        Assert-LocalFile (Join-Path $LocalIndex 'chroma.sqlite3')
        $Segment = Join-Path $LocalIndex '6fb7c70d-f09f-4f63-ad42-f93256f0288a'
        foreach ($Name in @('data_level0.bin', 'header.bin', 'length.bin', 'link_lists.bin', 'index_metadata.pickle')) {
            Assert-LocalFile (Join-Path $Segment $Name)
        }
        $ModelSnapshot = Join-Path $HubCache 'models--BAAI--bge-large-en-v1.5\snapshots\d4aa6901d3a41ba39fb536a557fa166f842b0e09'
        foreach ($Name in @('config.json', 'tokenizer_config.json', 'tokenizer.json', 'vocab.txt', 'special_tokens_map.json')) {
            Assert-LocalFile (Join-Path $ModelSnapshot $Name)
        }
        Assert-LocalFile (Join-Path $ModelSnapshot 'model.safetensors') 1340616616
    }

    & $PythonPath -X utf8 $EntryPath @ForwardArgs
    $ExitCode = $LASTEXITCODE
} catch {
    [Console]::Error.WriteLine('Local retrieval launcher: ' + $_.Exception.Message)
    $ExitCode = 1
} finally {
    foreach ($Name in $SavedEnvironment.Keys) {
        if ($null -eq $SavedEnvironment[$Name]) {
            [Environment]::SetEnvironmentVariable($Name, [NullString]::Value, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable($Name, $SavedEnvironment[$Name], 'Process')
        }
    }
    if ($LocationChanged) {
        Pop-Location
    }
}
exit $ExitCode
