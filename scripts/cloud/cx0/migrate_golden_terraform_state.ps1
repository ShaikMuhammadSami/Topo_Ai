[CmdletBinding()]
param(
    [ValidateSet("PRECHECK", "EXECUTE")]
    [string]$Mode = "PRECHECK",
    [switch]$ExecuteMigration,
    [string]$Confirmation = "",
    [string]$AwsProfile = "topo-admin",
    [string]$AwsRegion = "us-east-1",
    [string]$PythonExecutable = "",
    [string]$OutputDirectory = "artifacts/cx0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedAccount = "297361542190"
$ExpectedRegion = "us-east-1"
$ExpectedBranch = "feature/cx-0-cost-0-reproducibility-freeze"
$ExpectedWorkspace = "default"
$ExpectedTerraformMinimum = [version]"1.10.0"
$ExpectedResourceCount = 80
$ExpectedLocalStateSha256 = "b3321648facd8506f322b7f91ad3ad04dd8b1a017ba89124c5f382e4abd48994"
$BackendBucket = "topo-tfstate-297361542190-us-east-1"
$BackendKey = "golden/terraform.tfstate"
$LockKey = "$BackendKey.tflock"
$RequiredConfirmation = "MIGRATE_GOLDEN_STATE_TO_S3"
$RepresentativeAddresses = @(
    "aws_vpc.golden",
    "aws_eks_cluster.golden",
    "aws_db_instance.postgres",
    "aws_lb.edge",
    "aws_ecr_repository.topo"
)

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$TerraformRoot = Join-Path $RepoRoot "infrastructure/aws/golden"
$VersionsPath = Join-Path $TerraformRoot "versions.tf"
$LocalStatePath = Join-Path $TerraformRoot "terraform.tfstate"
$LocalStateInspector = Join-Path $PSScriptRoot "inspect_local_terraform_state.py"
$TerraformWorkspaceMetadataPath = Join-Path $TerraformRoot ".terraform/environment"
$ExpectedRoot = [System.IO.Path]::GetFullPath("C:\Topo-ai\infrastructure\aws\golden")
$RepositoryPython = Join-Path $RepoRoot "backend/.venv/Scripts/python.exe"
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = if (Test-Path -LiteralPath $RepositoryPython -PathType Leaf) {
        $RepositoryPython
    } else {
        "python"
    }
}

# Terraform receives the same named credential-chain selection as the bounded
# AWS metadata checks. No credential value is read, printed, or persisted.
$env:AWS_PROFILE = $AwsProfile
$env:AWS_REGION = $AwsRegion
$env:AWS_DEFAULT_REGION = $AwsRegion

function Invoke-NativeSafe {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )
    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if ($process.ExitCode -ne 0) {
            throw "$Description failed (exit $($process.ExitCode)); captured output was suppressed."
        }
        return Get-Content -LiteralPath $stdout -Raw
    }
    finally {
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-AwsJson {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Operation,
        [string[]]$Arguments = @()
    )
    $allowed = @(
        "sts get-caller-identity",
        "s3api get-bucket-location",
        "s3api get-bucket-versioning",
        "s3api get-public-access-block",
        "s3api get-bucket-encryption",
        "s3api get-bucket-ownership-controls",
        "s3api get-bucket-tagging",
        "s3api get-bucket-lifecycle-configuration",
        "s3api get-bucket-policy",
        "s3api list-objects-v2",
        "s3api head-object"
    )
    $operationKey = "$Service $Operation"
    if ($allowed -notcontains $operationKey) {
        throw "STOP: AWS operation is outside the migration read-only allowlist: $operationKey"
    }
    $allArguments = @(
        "--profile", $AwsProfile,
        "--region", $AwsRegion,
        $Service, $Operation
    ) + $Arguments + @("--output", "json", "--no-cli-pager")
    $raw = Invoke-NativeSafe "aws" $allArguments "AWS $operationKey"
    if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
    return $raw | ConvertFrom-Json -Depth 30
}

function Get-AwsLifecycleConfigurationSafe {
    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()
    $arguments = @(
        "--profile", $AwsProfile,
        "--region", $AwsRegion,
        "s3api", "get-bucket-lifecycle-configuration",
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount,
        "--output", "json",
        "--no-cli-pager"
    )
    try {
        $process = Start-Process -FilePath "aws" -ArgumentList $arguments -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if ($process.ExitCode -ne 0) {
            $errorText = Get-Content -LiteralPath $stderr -Raw
            if ($errorText -match 'NoSuchLifecycleConfiguration') {
                return [pscustomobject]@{ Rules = @() }
            }
            throw "AWS lifecycle metadata read failed (exit $($process.ExitCode)); captured output was suppressed."
        }
        $raw = Get-Content -LiteralPath $stdout -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{ Rules = @() } }
        return $raw | ConvertFrom-Json -Depth 20
    }
    finally {
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Test-BackendSourceContract {
    $source = Get-Content -LiteralPath $VersionsPath -Raw
    $patterns = @(
        'required_version\s*=\s*">= 1\.10, < 2\.0"',
        'backend\s+"s3"',
        'bucket\s*=\s*"topo-tfstate-297361542190-us-east-1"',
        'key\s*=\s*"golden/terraform\.tfstate"',
        'region\s*=\s*"us-east-1"',
        'encrypt\s*=\s*true',
        'use_lockfile\s*=\s*true'
    )
    foreach ($pattern in $patterns) {
        if ($source -notmatch $pattern) {
            throw "STOP: versioned S3 backend source contract is incomplete."
        }
    }
    if ($source -match '(?m)^\s*(dynamodb_table|profile|access_key|secret_key)\s*=') {
        throw "STOP: forbidden backend authority is present in source."
    }
}

function Get-BucketContract {
    $locationResult = Invoke-AwsJson "s3api" "get-bucket-location" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    $location = if ($null -eq $locationResult.LocationConstraint) { "us-east-1" } else { [string]$locationResult.LocationConstraint }
    if ($location -ne $ExpectedRegion) { throw "STOP: backend bucket region differs." }

    $versioning = Invoke-AwsJson "s3api" "get-bucket-versioning" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    if ([string]$versioning.Status -ne "Enabled") { throw "STOP: backend versioning is not enabled." }

    $public = Invoke-AwsJson "s3api" "get-public-access-block" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    $publicConfig = $public.PublicAccessBlockConfiguration
    if (
        $publicConfig.BlockPublicAcls -ne $true -or
        $publicConfig.IgnorePublicAcls -ne $true -or
        $publicConfig.BlockPublicPolicy -ne $true -or
        $publicConfig.RestrictPublicBuckets -ne $true
    ) { throw "STOP: backend public-access block is incomplete." }

    $encryption = Invoke-AwsJson "s3api" "get-bucket-encryption" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    $algorithms = @($encryption.ServerSideEncryptionConfiguration.Rules | ForEach-Object {
        $_.ApplyServerSideEncryptionByDefault.SSEAlgorithm
    })
    if ($algorithms -notcontains "AES256") { throw "STOP: backend SSE-S3 encryption is not configured." }

    $ownership = Invoke-AwsJson "s3api" "get-bucket-ownership-controls" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    if (@($ownership.OwnershipControls.Rules.ObjectOwnership) -notcontains "BucketOwnerEnforced") {
        throw "STOP: backend object ownership is not BucketOwnerEnforced."
    }

    $tagsResponse = Invoke-AwsJson "s3api" "get-bucket-tagging" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    $tags = @{}
    foreach ($tag in @($tagsResponse.TagSet)) { $tags[[string]$tag.Key] = [string]$tag.Value }
    if (
        $tags["authority"] -ne "DURABLE_EXTERNAL_AUTHORITY" -or
        $tags["cost0-retain"] -ne "true" -or
        $tags["cx0b-delete"] -ne "forbidden"
    ) { throw "STOP: backend retention/authority tags differ." }

    $policyResponse = Invoke-AwsJson "s3api" "get-bucket-policy" @(
        "--bucket", $BackendBucket,
        "--expected-bucket-owner", $ExpectedAccount
    )
    $policy = [string]$policyResponse.Policy | ConvertFrom-Json -Depth 20
    $nonTlsDeny = @($policy.Statement | Where-Object {
        $_.Effect -eq "Deny" -and $_.Condition.Bool.'aws:SecureTransport' -eq "false"
    }).Count -gt 0
    if (-not $nonTlsDeny) { throw "STOP: backend non-TLS deny policy is absent." }

    $lifecycle = Get-AwsLifecycleConfigurationSafe
    foreach ($rule in @($lifecycle.Rules)) {
        if ($null -ne $rule.Expiration -or $null -ne $rule.NoncurrentVersionExpiration) {
            throw "STOP: backend state expiration is forbidden."
        }
    }

    return [pscustomobject]@{
        region = $location
        versioning_enabled = $true
        public_access_blocked = $true
        encryption = "AES256"
        object_ownership = "BucketOwnerEnforced"
        non_tls_denied = $true
        retain_classification = "COST_0_RETAIN"
    }
}

function Get-BackendObjects {
    $response = Invoke-AwsJson "s3api" "list-objects-v2" @(
        "--bucket", $BackendBucket,
        "--prefix", $BackendKey,
        "--max-keys", "10",
        "--expected-bucket-owner", $ExpectedAccount
    )
    return @($response.Contents)
}

function Invoke-Precheck {
    param([bool]$RequireStateAbsent)

    if ([System.IO.Path]::GetFullPath($TerraformRoot) -ne $ExpectedRoot) {
        throw "STOP: Terraform root is not the approved golden root."
    }
    if ($AwsRegion -ne $ExpectedRegion) { throw "STOP: AWS region differs." }
    if ((Invoke-NativeSafe "git" @("-C", $RepoRoot, "branch", "--show-current") "Git branch read").Trim() -ne $ExpectedBranch) {
        throw "STOP: current branch differs from the approved migration branch."
    }
    if (-not [string]::IsNullOrWhiteSpace((Invoke-NativeSafe "git" @("-C", $RepoRoot, "status", "--porcelain", "--untracked-files=all") "Git worktree read"))) {
        throw "STOP: migration requires a clean reviewed worktree."
    }
    Test-BackendSourceContract

    $identity = Invoke-AwsJson "sts" "get-caller-identity"
    if ([string]$identity.Account -ne $ExpectedAccount) { throw "STOP: AWS account differs." }

    $versionResult = Invoke-NativeSafe "terraform" @("-chdir=$TerraformRoot", "version", "-json") "Terraform version read"
    $terraformVersion = [version](($versionResult | ConvertFrom-Json -Depth 10).terraform_version)
    if ($terraformVersion -lt $ExpectedTerraformMinimum -or $terraformVersion.Major -ge 2) {
        throw "STOP: Terraform version is outside the approved range."
    }

    if (-not (Test-Path -LiteralPath $LocalStatePath -PathType Leaf)) { throw "STOP: approved local state is absent." }
    if (-not (Test-Path -LiteralPath $LocalStateInspector -PathType Leaf)) { throw "STOP: bounded local-state inspector is absent." }
    $localStateMetadata = (
        Invoke-NativeSafe $PythonExecutable @($LocalStateInspector) "Bounded local Terraform state metadata read"
    ) | ConvertFrom-Json -Depth 20
    if ([string]$localStateMetadata.local_state_sha256 -ne $ExpectedLocalStateSha256) {
        throw "STOP: local state fingerprint differs."
    }
    if ([int]$localStateMetadata.resource_address_count -ne $ExpectedResourceCount) {
        throw "STOP: local state resource count differs."
    }
    if ($localStateMetadata.all_representative_addresses_present -ne $true) {
        throw "STOP: representative local resource addresses are incomplete."
    }
    if (
        $localStateMetadata.raw_state_emitted -ne $false -or
        $localStateMetadata.resource_attributes_emitted -ne $false -or
        $localStateMetadata.outputs_emitted -ne $false
    ) { throw "STOP: local-state inspector exceeded its safe metadata projection." }

    # The accepted local authority is the default workspace. Terraform writes
    # a workspace name to .terraform/environment only for a non-default local
    # selection; absence therefore resolves to default without consulting the
    # newly declared backend.
    $workspace = $ExpectedWorkspace
    if (Test-Path -LiteralPath $TerraformWorkspaceMetadataPath -PathType Leaf) {
        $workspace = (Get-Content -LiteralPath $TerraformWorkspaceMetadataPath -Raw).Trim()
    }
    if ($workspace -ne $ExpectedWorkspace) { throw "STOP: accepted local workspace metadata is not default." }
    $localState = Get-Item -LiteralPath $LocalStatePath

    $bucket = Get-BucketContract
    $objects = Get-BackendObjects
    $stateExists = @($objects | Where-Object { $_.Key -eq $BackendKey }).Count -gt 0
    $lockExists = @($objects | Where-Object { $_.Key -eq $LockKey }).Count -gt 0
    if ($lockExists) { throw "STOP: an unexpected Terraform lock object exists." }
    if ($RequireStateAbsent -and $stateExists) { throw "STOP: backend state object already exists before first migration." }

    return [pscustomobject]@{
        aws_account = $ExpectedAccount
        region = $bucket.region
        root_module = $TerraformRoot
        workspace = $workspace
        terraform_version = $terraformVersion.ToString()
        local_state_path = $LocalStatePath
        local_state_sha256 = [string]$localStateMetadata.local_state_sha256
        local_state_size_bytes = $localState.Length
        local_state_format_version = [int]$localStateMetadata.state_format_version
        local_state_terraform_version = [string]$localStateMetadata.terraform_version
        local_state_lineage = [string]$localStateMetadata.lineage
        local_state_serial = [int]$localStateMetadata.serial
        resource_address_count = [int]$localStateMetadata.resource_address_count
        representative_addresses_present = $localStateMetadata.representative_addresses_present
        backend_bucket = $BackendBucket
        backend_key = $BackendKey
        backend_state_exists = $stateExists
        lock_object_exists = $lockExists
        mode = "PRECHECK"
        mutation_performed = $false
    }
}

function Invoke-PostMigrationVerification {
    param([Parameter(Mandatory = $true)][object]$Precheck)

    & terraform "-chdir=$TerraformRoot" init
    if ($LASTEXITCODE -ne 0) { throw "STOP: post-migration Terraform initialization failed." }

    $workspace = (Invoke-NativeSafe "terraform" @("-chdir=$TerraformRoot", "workspace", "show") "Remote workspace read").Trim()
    if ($workspace -ne $ExpectedWorkspace) { throw "STOP: migrated workspace differs." }
    $addresses = @(
        (Invoke-NativeSafe "terraform" @("-chdir=$TerraformRoot", "state", "list") "Remote address read") -split "`r?`n" |
            Where-Object { $_ }
    )
    if ($addresses.Count -ne $ExpectedResourceCount) { throw "STOP: migrated resource count differs." }
    foreach ($address in $RepresentativeAddresses) {
        if ($addresses -notcontains $address) { throw "STOP: representative migrated resource address is missing." }
    }

    $bucket = Get-BucketContract
    $head = Invoke-AwsJson "s3api" "head-object" @(
        "--bucket", $BackendBucket,
        "--key", $BackendKey,
        "--expected-bucket-owner", $ExpectedAccount
    )
    if ([string]::IsNullOrWhiteSpace([string]$head.VersionId) -or [string]$head.VersionId -eq "null") {
        throw "STOP: migrated backend state has no durable S3 VersionId."
    }
    $objects = Get-BackendObjects
    if (@($objects | Where-Object { $_.Key -eq $LockKey }).Count -gt 0) {
        throw "STOP: Terraform lock object remained after migration."
    }

    return [pscustomobject]@{
        migrated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        backend_type = "s3"
        backend_bucket = $BackendBucket
        backend_key = $BackendKey
        backend_region = $bucket.region
        locking_model = "S3_NATIVE_USE_LOCKFILE"
        workspace = $workspace
        resource_address_count = $addresses.Count
        representative_addresses = $RepresentativeAddresses
        state_object_version_id = [string]$head.VersionId
        state_object_etag = [string]$head.ETag
        state_object_modified_at = [string]$head.LastModified
        state_object_size_bytes = [long]$head.ContentLength
        local_recovery_copy_classification = "NON_AUTHORITATIVE_LOCAL_RECOVERY_COPY"
        local_recovery_copy_path = [string]$Precheck.local_state_path
        local_recovery_copy_original_sha256 = [string]$Precheck.local_state_sha256
        local_state_lineage = [string]$Precheck.local_state_lineage
        local_state_pre_migration_serial = [int]$Precheck.local_state_serial
        local_recovery_copy_deleted = $false
        state_values_read = $false
    }
}

if ($Mode -eq "PRECHECK") {
    if ($ExecuteMigration -or -not [string]::IsNullOrWhiteSpace($Confirmation)) {
        throw "STOP: PRECHECK accepts no execution flag or confirmation."
    }
    Invoke-Precheck -RequireStateAbsent $true | ConvertTo-Json -Depth 10
    exit 0
}

if (-not $ExecuteMigration -or $Confirmation -ne $RequiredConfirmation) {
    throw "STOP: EXECUTE requires -ExecuteMigration and the exact confirmation value."
}

$precheck = Invoke-Precheck -RequireStateAbsent $true

# Preserve operator control of Terraform's own migration confirmation by
# invoking the native command directly without non-interactive flags.
& terraform "-chdir=$TerraformRoot" init -migrate-state
if ($LASTEXITCODE -ne 0) { throw "STOP: Terraform native backend migration failed." }

$receipt = Invoke-PostMigrationVerification -Precheck $precheck
$safeOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts/cx0"))
$requestedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
if ($requestedOutputRoot -ne $safeOutputRoot) { throw "STOP: migration receipt path must remain artifacts/cx0." }
New-Item -ItemType Directory -Path $safeOutputRoot -Force | Out-Null
$receiptPath = Join-Path $safeOutputRoot "terraform-state-migration-receipt.json"
$receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $receiptPath -Encoding utf8NoBOM
Write-Host "TERRAFORM_STATE_MIGRATION=VERIFIED"
Write-Host "MIGRATION_RECEIPT=$receiptPath"
