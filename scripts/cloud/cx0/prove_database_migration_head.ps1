[CmdletBinding()]
param(
    [string]$AwsProfile = "topo-admin",
    [string]$AwsRegion = "us-east-1",
    [string]$KubeContext = "topo-golden",
    [string]$Namespace = "topo-system",
    [string]$Deployment = "topo-backend",
    [string]$Container = "backend",
    [string]$OutputPath = "artifacts/cx0/database-migration-head-proof.json",
    [switch]$RequireSourceAuthority,
    [switch]$ContractOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedAccount = "297361542190"
$ExpectedRegion = "us-east-1"
$ExpectedContext = "topo-golden"
$ExpectedNamespace = "topo-system"
$ExpectedDeployment = "topo-backend"
$ExpectedContainer = "backend"
$ExpectedBranch = "feature/cx-0-cost-0-reproducibility-freeze"
$ReviewedAncestor = "09165267b88d73c8e01ba7f550cefdd2bfd6f788"
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$MigrationRoot = Join-Path $RepoRoot "backend/alembic/versions"

function Get-PropertyValue {
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()][object]$Default = $null
    )
    if ($null -eq $InputObject) { return $Default }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}

function Invoke-SafeNative {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$Description
    )
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $ArgumentList) { [void]$startInfo.ArgumentList.Add($argument) }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) { throw "Unable to start $Description." }
        $stdout = $process.StandardOutput.ReadToEnd()
        [void]$process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            # Provider/process stderr is never echoed because it may contain
            # connection details or other sensitive runtime context.
            throw "$Description failed with exit code $($process.ExitCode)."
        }
        return $stdout.Trim()
    }
    finally {
        $process.Dispose()
    }
}

function Get-RepositoryMigrationHeads {
    param([Parameter(Mandatory = $true)][string]$Path)
    $revisions = @{}
    $parents = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $Path -Filter "*.py" -File) {
        $source = Get-Content -LiteralPath $file.FullName -Raw
        $revisionMatch = [regex]::Match($source, '(?m)^revision(?:\s*:\s*str)?\s*=\s*["'']([^"'']+)["'']')
        if (-not $revisionMatch.Success) { continue }
        $revision = $revisionMatch.Groups[1].Value
        $revisions[$revision] = $file.Name
        $parentMatch = [regex]::Match($source, '(?m)^down_revision(?:\s*:[^=]+)?\s*=\s*["'']([^"'']+)["'']')
        if ($parentMatch.Success) { [void]$parents.Add($parentMatch.Groups[1].Value) }
    }
    return @($revisions.Keys | Where-Object { -not $parents.Contains($_) } | Sort-Object)
}

function Resolve-DatabaseMigrationHeadStatus {
    param(
        [AllowEmptyCollection()][string[]]$SourceHeads = @(),
        [AllowEmptyCollection()][string[]]$LiveHeads = @(),
        [bool]$ProbeCompleted = $false
    )
    if (@($SourceHeads).Count -ne 1) {
        return [pscustomobject]@{
            status = "SOURCE_HEADS_NOT_UNIQUE"
            source_count = @($SourceHeads).Count
            live_count = @($LiveHeads).Count
            match = $false
        }
    }
    if (@($LiveHeads).Count -gt 1) {
        return [pscustomobject]@{
            status = "LIVE_HEADS_NOT_UNIQUE"
            source_count = 1
            live_count = @($LiveHeads).Count
            match = $false
        }
    }
    if (@($LiveHeads).Count -eq 1 -and $SourceHeads[0] -cne $LiveHeads[0]) {
        return [pscustomobject]@{
            status = "DIFFERENT"
            source_count = 1
            live_count = 1
            match = $false
        }
    }
    if (-not $ProbeCompleted -or @($LiveHeads).Count -eq 0) {
        return [pscustomobject]@{
            status = "UNKNOWN_REQUIRED"
            source_count = 1
            live_count = @($LiveHeads).Count
            match = $false
        }
    }
    return [pscustomobject]@{
        status = "MATCH"
        source_count = 1
        live_count = 1
        match = $true
    }
}

if ($ContractOnly) { return }

if ($AwsRegion -ne $ExpectedRegion) { throw "STOP: expected AWS region $ExpectedRegion." }
if ($KubeContext -ne $ExpectedContext) { throw "STOP: expected Kubernetes context $ExpectedContext." }
if ($Namespace -ne $ExpectedNamespace) { throw "STOP: expected namespace $ExpectedNamespace." }
if ($Deployment -ne $ExpectedDeployment) { throw "STOP: expected deployment $ExpectedDeployment." }
if ($Container -ne $ExpectedContainer) { throw "STOP: expected container $ExpectedContainer." }

if ($RequireSourceAuthority) {
    $branch = Invoke-SafeNative "git" @("branch", "--show-current") "Git branch read"
    if ($branch -ne $ExpectedBranch) { throw "STOP: source-authority branch differs." }
    [void](Invoke-SafeNative "git" @("merge-base", "--is-ancestor", $ReviewedAncestor, "HEAD") "Git reviewed-ancestor check")
}

$identityText = Invoke-SafeNative "aws" @(
    "--profile", $AwsProfile,
    "--region", $AwsRegion,
    "sts", "get-caller-identity",
    "--output", "json",
    "--no-cli-pager"
) "AWS caller-identity read"
$identity = $identityText | ConvertFrom-Json -Depth 10
if ([string](Get-PropertyValue $identity "Account") -ne $ExpectedAccount) {
    throw "STOP: AWS account differs from reviewed authority."
}

$contextName = Invoke-SafeNative "kubectl" @(
    "--context", $KubeContext,
    "config", "get-contexts", $KubeContext,
    "--output", "name"
) "Kubernetes context lookup"
if ($contextName -ne $ExpectedContext) { throw "STOP: Kubernetes context is unavailable." }

$deploymentText = Invoke-SafeNative "kubectl" @(
    "--context", $KubeContext,
    "--namespace", $Namespace,
    "get", "deployment", $Deployment,
    "--output", "json"
) "Kubernetes Deployment read"
$deploymentObject = $deploymentText | ConvertFrom-Json -Depth 50
$matchLabels = Get-PropertyValue (Get-PropertyValue (Get-PropertyValue $deploymentObject "spec") "selector") "matchLabels"
$selectorPairs = @(
    @($matchLabels.PSObject.Properties) |
        Where-Object { $_.MemberType -eq "NoteProperty" -or $_.MemberType -eq "Property" } |
        Sort-Object Name |
        ForEach-Object { "$($_.Name)=$($_.Value)" }
)
if ($selectorPairs.Count -eq 0) { throw "STOP: Deployment has no matchLabels selector." }
$selector = $selectorPairs -join ","

$podsText = Invoke-SafeNative "kubectl" @(
    "--context", $KubeContext,
    "--namespace", $Namespace,
    "get", "pods",
    "--selector", $selector,
    "--output", "json"
) "Kubernetes backend Pod read"
$pods = $podsText | ConvertFrom-Json -Depth 50
$readyPods = @()
foreach ($pod in @(Get-PropertyValue $pods "items" @())) {
    $status = Get-PropertyValue $pod "status"
    $spec = Get-PropertyValue $pod "spec"
    $containerDefined = @(
        @(Get-PropertyValue $spec "containers" @()) |
            Where-Object { (Get-PropertyValue $_ "name") -eq $ExpectedContainer }
    ).Count -eq 1
    $containerReady = @(
        @(Get-PropertyValue $status "containerStatuses" @()) |
            Where-Object {
                (Get-PropertyValue $_ "name") -eq $ExpectedContainer -and
                (Get-PropertyValue $_ "ready" $false) -eq $true
            }
    ).Count -eq 1
    $podReady = @(
        @(Get-PropertyValue $status "conditions" @()) |
            Where-Object {
                (Get-PropertyValue $_ "type") -eq "Ready" -and
                (Get-PropertyValue $_ "status") -eq "True"
            }
    ).Count -eq 1
    if (
        (Get-PropertyValue $status "phase") -eq "Running" -and
        $containerDefined -and $containerReady -and $podReady
    ) {
        $readyPods += $pod
    }
}
if ($readyPods.Count -eq 0) { throw "STOP: no Running/Ready backend Pod is available." }
$selectedPod = @($readyPods | Sort-Object { (Get-PropertyValue (Get-PropertyValue $_ "metadata") "name") })[0]
$selectedPodName = [string](Get-PropertyValue (Get-PropertyValue $selectedPod "metadata") "name")

$sourceHeads = @(Get-RepositoryMigrationHeads -Path $MigrationRoot)
$sourceStatus = Resolve-DatabaseMigrationHeadStatus -SourceHeads $sourceHeads -LiveHeads @() -ProbeCompleted $false
if ($sourceStatus.status -eq "SOURCE_HEADS_NOT_UNIQUE") {
    throw "STOP: repository migration head is not unique."
}

$databaseProbe = @'
import json
import os
import psycopg

connection = psycopg.connect(os.environ["TOPO_DATABASE_URL"])
heads = []
try:
    with connection.cursor() as cursor:
        cursor.execute("BEGIN READ ONLY")
        cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
        heads = [str(row[0]) for row in cursor.fetchall()]
finally:
    connection.rollback()
    connection.close()

print(json.dumps({
    "credential_environment_variable": "TOPO_DATABASE_URL",
    "driver": "psycopg-v3",
    "heads": heads,
    "row_count": len(heads),
    "query_type": "SELECT_ONLY",
    "transaction_mode": "READ_ONLY",
    "transaction_completion": "ROLLBACK"
}, separators=(",", ":")))
'@

$probeText = Invoke-SafeNative "kubectl" @(
    "--context", $KubeContext,
    "--namespace", $Namespace,
    "exec", $selectedPodName,
    "--container", $Container,
    "--", "python", "-c", $databaseProbe
) "Read-only database migration-head probe"
$databaseEvidence = $probeText | ConvertFrom-Json -Depth 10
$liveHeads = @((Get-PropertyValue $databaseEvidence "heads" @()) | ForEach-Object { [string]$_ })
$status = Resolve-DatabaseMigrationHeadStatus -SourceHeads $sourceHeads -LiveHeads $liveHeads -ProbeCompleted $true
if ($status.status -ne "MATCH") {
    throw "STOP: database migration-head proof did not match source authority ($($status.status))."
}
if (
    (Get-PropertyValue $databaseEvidence "credential_environment_variable") -ne "TOPO_DATABASE_URL" -or
    (Get-PropertyValue $databaseEvidence "driver") -ne "psycopg-v3" -or
    (Get-PropertyValue $databaseEvidence "query_type") -ne "SELECT_ONLY" -or
    (Get-PropertyValue $databaseEvidence "transaction_mode") -ne "READ_ONLY" -or
    (Get-PropertyValue $databaseEvidence "transaction_completion") -ne "ROLLBACK"
) {
    throw "STOP: database probe safety contract differs."
}

$receipt = [pscustomobject]@{
    schema_version = "cx0.database-migration-head-proof.v1"
    probed_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    aws_account_id = $ExpectedAccount
    aws_region = $ExpectedRegion
    kube_context = $ExpectedContext
    namespace = $ExpectedNamespace
    deployment = $ExpectedDeployment
    selector_source = "Deployment.spec.selector.matchLabels"
    selected_pod = $selectedPodName
    container = $ExpectedContainer
    credential_environment_variable = "TOPO_DATABASE_URL"
    driver = "psycopg-v3"
    source_migration_heads = $sourceHeads
    source_migration_head_count = $sourceHeads.Count
    source_migration_head = $sourceHeads[0]
    live_database_migration_heads = $liveHeads
    live_database_migration_head_count = $liveHeads.Count
    live_database_migration_head = $liveHeads[0]
    database_migration_head_status = $status.status
    query_type = "SELECT_ONLY"
    transaction_mode = "READ_ONLY"
    transaction_completion = "ROLLBACK"
    database_secret_printed = $false
    database_secret_written_to_disk = $false
    aws_mutation_performed = $false
    kubernetes_mutation_performed = $false
    database_mutation_performed = $false
}

$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    [System.IO.Path]::GetFullPath($OutputPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputPath))
}
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts/cx0"))
if (-not $resolvedOutput.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "STOP: proof receipt must remain under ignored artifacts/cx0."
}
[void](New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutput) -Force)
[System.IO.File]::WriteAllText(
    $resolvedOutput,
    ($receipt | ConvertTo-Json -Depth 20) + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

@(
    "SOURCE_MIGRATION_HEAD=$($receipt.source_migration_head)"
    "LIVE_DATABASE_MIGRATION_HEAD=$($receipt.live_database_migration_head)"
    "DATABASE_MIGRATION_HEAD=$($receipt.database_migration_head_status)"
    "DATABASE_PROBE_CREDENTIAL_ENVIRONMENT_VARIABLE=$($receipt.credential_environment_variable)"
    "DATABASE_PROBE_DRIVER=$($receipt.driver)"
    "DATABASE_PROBE_ROW_COUNT=$($receipt.live_database_migration_head_count)"
    "DATABASE_PROBE_QUERY_TYPE=$($receipt.query_type)"
    "DATABASE_PROBE_TRANSACTION_MODE=$($receipt.transaction_mode)"
    "DATABASE_PROBE_TRANSACTION_COMPLETION=$($receipt.transaction_completion)"
    "DATABASE_SECRET_PRINTED=NO"
    "DATABASE_SECRET_WRITTEN_TO_DISK=NO"
    "AWS_MUTATION_PERFORMED=NO"
    "KUBERNETES_MUTATION_PERFORMED=NO"
    "DATABASE_MUTATION_PERFORMED=NO"
) | ForEach-Object { Write-Output $_ }
