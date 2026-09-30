[CmdletBinding()]
param(
    [string]$AwsProfile = "topo-admin",
    [string]$AwsRegion = "us-east-1",
    [string]$ClusterName = "topo-golden",
    [string]$Namespace = "topo-system",
    [string]$PythonExecutable = "",
    [string]$OutputDirectory = "artifacts/cx0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedAccount = "297361542190"
$ExpectedRegion = "us-east-1"
$ExpectedCluster = "topo-golden"
$ExpectedNamespace = "topo-system"
$ExpectedBranch = "feature/cx-0-cost-0-reproducibility-freeze"
$AcceptedHead = "e676559b3daf586b4dc53041d1638a3d2191910a"
$AcceptedTree = "c4389d7613afeb7f908e87ed5c4e6c04e599fc0c"
$AcceptedOrigin = '["https://app.topoai.io"]'
$AcceptedAlbArn = "arn:aws:elasticloadbalancing:us-east-1:297361542190:loadbalancer/app/topo-golden-edge/bed4a7ad18a7221c"
$AcceptedCertificateArn = "arn:aws:acm:us-east-1:297361542190:certificate/85675e1c-205d-4fb1-98f2-f6acf8a5c12d"
$AcceptedValidationOwner = "_ae02df53f40f7c96b34bc6e98fb69e1d.app.topoai.io."
$AcceptedValidationValue = "_fd79c652992203959600f955507f54f4.wzccmgtwzk.acm-validations.aws."
$AcceptedAlbSecurityGroup = "sg-039e2a36df4d18e31"
$AcceptedWorkerSecurityGroup = "sg-071e1b40296d57288"
$AcceptedVpc = "vpc-00dc74e72bd7f0129"

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$ImageAuthorityPath = Join-Path $PSScriptRoot "cloud_v1_1b_image_authority.json"
if (-not (Test-Path -LiteralPath $ImageAuthorityPath -PathType Leaf)) {
    throw "STOP: immutable image authority is missing"
}
$ImageAuthority = Get-Content -LiteralPath $ImageAuthorityPath -Raw | ConvertFrom-Json -Depth 20
if (
    $ImageAuthority.schema_version -ne "cx0.image-authority.v1" -or
    $ImageAuthority.aws_account_id -ne $ExpectedAccount -or
    $ImageAuthority.region -ne $ExpectedRegion -or
    $ImageAuthority.accepted_cloud_head -ne $AcceptedHead -or
    [string]::IsNullOrWhiteSpace([string]$ImageAuthority.repository)
) {
    throw "STOP: immutable image authority contract is invalid"
}
$EcrRepository = [string]$ImageAuthority.repository
$EcrRepositoryUri = "$ExpectedAccount.dkr.ecr.$ExpectedRegion.amazonaws.com/$EcrRepository"
$AcceptedBackendImage = "$EcrRepositoryUri@$($ImageAuthority.images.backend.digest)"
$AcceptedFrontendImage = "$EcrRepositoryUri@$($ImageAuthority.images.frontend.digest)"
$AcceptedObserverImage = "$EcrRepositoryUri@$($ImageAuthority.images.observer.digest)"
$TerraformRoot = Join-Path $RepoRoot "infrastructure/aws/golden"
$KubernetesRoot = Join-Path $RepoRoot "infrastructure/kubernetes/golden"
$SchemaPath = Join-Path $PSScriptRoot "reproducibility_inventory.schema.json"
$SecretStoreRecoveryTool = Join-Path $PSScriptRoot "escrow_secretstore_keyring.py"
$SecretStoreRecoveryProcedure = Join-Path $RepoRoot "docs/operations/cx-0-rds-recovery-proof-plan.md"
$TerraformBackendBootstrap = Join-Path $PSScriptRoot "bootstrap_terraform_state_backend.py"
$KubernetesContractTool = Join-Path $PSScriptRoot "kubernetes_reproducibility_contract.py"
$TerraformMigrationReceipt = Join-Path $RepoRoot "artifacts/cx0/terraform-state-migration-receipt.json"
$DatabaseMigrationProof = Join-Path $RepoRoot "artifacts/cx0/database-migration-head-proof.json"
$RepositoryPython = Join-Path $RepoRoot "backend/.venv/Scripts/python.exe"
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = if (Test-Path -LiteralPath $RepositoryPython -PathType Leaf) {
        $RepositoryPython
    } else {
        "python"
    }
}

if ($AwsRegion -ne $ExpectedRegion) {
    throw "STOP: expected us-east-1"
}
if ($ClusterName -ne $ExpectedCluster) {
    throw "STOP: expected topo-golden"
}
if ($Namespace -ne $ExpectedNamespace) {
    throw "STOP: expected topo-system"
}

$script:AwsReadOnlyOperations = @(
    "acm describe-certificate",
    "autoscaling describe-auto-scaling-groups",
    "cloudtrail describe-trails",
    "ec2 describe-addresses",
    "ec2 describe-instances",
    "ec2 describe-internet-gateways",
    "ec2 describe-nat-gateways",
    "ec2 describe-network-acls",
    "ec2 describe-route-tables",
    "ec2 describe-security-groups",
    "ec2 describe-subnets",
    "ec2 describe-vpc-endpoints",
    "ec2 describe-vpcs",
    "ecr describe-images",
    "ecr describe-repositories",
    "ecr get-lifecycle-policy",
    "eks describe-cluster",
    "eks describe-nodegroup",
    "eks list-nodegroups",
    "elbv2 describe-listeners",
    "elbv2 describe-load-balancers",
    "elbv2 describe-rules",
    "elbv2 describe-target-groups",
    "elbv2 describe-target-health",
    "iam get-role",
    "iam list-attached-role-policies",
    "iam list-role-policies",
    "iam list-roles",
    "logs describe-log-groups",
    "rds describe-db-instances",
    "rds describe-db-snapshots",
    "s3api list-buckets",
    "sts get-caller-identity",
    "wafv2 get-logging-configuration",
    "wafv2 get-web-acl-for-resource"
)

$script:KubernetesReadOnlyOperations = @(
    "config current-context",
    "config view",
    "get resources",
    "version client"
)

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$SafeDescription,
        [string]$AllowedEmptyErrorMarker = "",
        [hashtable]$Environment = @{}
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $ArgumentList) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    foreach ($name in $Environment.Keys) {
        $startInfo.Environment[[string]$name] = [string]$Environment[$name]
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Unable to start $SafeDescription."
        }
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            if (
                -not [string]::IsNullOrWhiteSpace($AllowedEmptyErrorMarker) -and
                $stderr.Contains($AllowedEmptyErrorMarker, [System.StringComparison]::Ordinal)
            ) {
                return ""
            }
            # Captured stderr is deliberately not echoed because provider errors can
            # contain caller/environment details that do not belong in receipts.
            throw "$SafeDescription failed with exit code $($process.ExitCode)."
        }
        return $stdout.Trim()
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-NativeStatus {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$SafeDescription,
        [hashtable]$Environment = @{}
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    foreach ($argument in $ArgumentList) {
        [void]$startInfo.ArgumentList.Add($argument)
    }
    foreach ($name in $Environment.Keys) {
        $startInfo.Environment[[string]$name] = [string]$Environment[$name]
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        if (-not $process.Start()) {
            throw "Unable to start $SafeDescription."
        }
        # Output is consumed but deliberately not emitted or persisted. Terraform
        # diagnostics can contain environment-specific details.
        [void]$process.StandardOutput.ReadToEnd()
        [void]$process.StandardError.ReadToEnd()
        $process.WaitForExit()
        return $process.ExitCode
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-AwsReadOnlyJson {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Operation,
        [string[]]$Arguments = @(),
        [string]$AllowedEmptyErrorMarker = ""
    )

    $key = "$Service $Operation"
    if ($script:AwsReadOnlyOperations -notcontains $key) {
        throw "AWS operation is not in the CX-0A read-only allowlist: $key"
    }
    $base = @(
        "--profile", $AwsProfile,
        "--region", $AwsRegion,
        $Service, $Operation
    ) + $Arguments + @("--output", "json", "--no-cli-pager")
    $json = Invoke-NativeCapture -FilePath "aws" -ArgumentList $base -SafeDescription "AWS read-only $key" -AllowedEmptyErrorMarker $AllowedEmptyErrorMarker
    if ([string]::IsNullOrWhiteSpace($json)) {
        return [pscustomobject]@{}
    }
    return $json | ConvertFrom-Json -Depth 100
}

function Invoke-KubectlReadOnlyText {
    param(
        [Parameter(Mandatory = $true)][string]$OperationKey,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    if ($script:KubernetesReadOnlyOperations -notcontains $OperationKey) {
        throw "Kubernetes operation is not in the CX-0A read-only allowlist: $OperationKey"
    }
    $contextBoundArguments = @("--context", $ExpectedCluster) + $Arguments
    return Invoke-NativeCapture -FilePath "kubectl" -ArgumentList $contextBoundArguments -SafeDescription "Kubernetes read-only $OperationKey"
}

function Invoke-KubectlGetJson {
    param(
        [Parameter(Mandatory = $true)][string]$Resource,
        [switch]$ClusterScoped
    )
    $arguments = @("get", $Resource)
    if (-not $ClusterScoped) {
        $arguments += @("--namespace", $Namespace)
    }
    $arguments += @("--output", "json")
    $text = Invoke-KubectlReadOnlyText -OperationKey "get resources" -Arguments $arguments
    return $text | ConvertFrom-Json -Depth 100
}

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

function Test-TerraformMigrationReceiptContract {
    param([AllowNull()][object]$Receipt)

    $semantic = Get-PropertyValue $Receipt "migration_semantic_equivalence"
    $sourceKinds = Get-PropertyValue $semantic "check_results_kinds_source"
    $destinationKinds = Get-PropertyValue $semantic "check_results_kinds_destination"
    $sourceStatuses = Get-PropertyValue $semantic "check_results_statuses_source"
    $destinationStatuses = Get-PropertyValue $semantic "check_results_statuses_destination"
    $representatives = @(Get-PropertyValue $Receipt "representative_addresses" @())
    return (
        (Get-PropertyValue $Receipt "schema_version") -eq "cx0a.terraform-migration-receipt.v2" -and
        (Get-PropertyValue $Receipt "backend_type") -eq "s3" -and
        (Get-PropertyValue $Receipt "backend_bucket") -eq "topo-tfstate-297361542190-us-east-1" -and
        (Get-PropertyValue $Receipt "backend_key") -eq "golden/terraform.tfstate" -and
        (Get-PropertyValue $Receipt "backend_region") -eq "us-east-1" -and
        (Get-PropertyValue $Receipt "locking_model") -eq "S3_NATIVE_USE_LOCKFILE" -and
        (Get-PropertyValue $Receipt "remote_state_authority") -eq "DURABLE_EXTERNAL_AUTHORITY" -and
        (Get-PropertyValue $Receipt "workspace") -eq "default" -and
        (Get-PropertyValue $Receipt "resource_address_count" -1) -eq 80 -and
        @($representatives | Where-Object { $_ -in @(
            "aws_vpc.golden", "aws_eks_cluster.golden", "aws_db_instance.postgres",
            "aws_lb.edge", "aws_ecr_repository.topo"
        ) }).Count -eq 5 -and
        -not [string]::IsNullOrWhiteSpace([string](Get-PropertyValue $Receipt "state_object_version_id")) -and
        (Get-PropertyValue $Receipt "state_object_encryption") -eq "AES256" -and
        (Get-PropertyValue $Receipt "source_state_lineage") -eq "13c78cf7-912f-cacc-74eb-15c7ee33112f" -and
        (Get-PropertyValue $Receipt "source_state_serial" -1) -eq 97 -and
        (Get-PropertyValue $Receipt "destination_state_lineage") -eq "dc5223d7-8ffe-cacf-e04f-f1f42a8bc584" -and
        (Get-PropertyValue $Receipt "destination_state_serial" -1) -eq 1 -and
        (Get-PropertyValue $Receipt "state_payloads_stored" $true) -eq $false -and
        (Get-PropertyValue $Receipt "secret_values_stored" $true) -eq $false -and
        (Get-PropertyValue $semantic "resources_match" $false) -eq $true -and
        (Get-PropertyValue $semantic "outputs_match" $false) -eq $true -and
        (Get-PropertyValue $semantic "non_check_state_match" $false) -eq $true -and
        (Get-PropertyValue $semantic "check_results_unordered_match" $false) -eq $true -and
        (Get-PropertyValue $semantic "check_results_count_source" -1) -eq 18 -and
        (Get-PropertyValue $semantic "check_results_count_destination" -1) -eq 18 -and
        (Get-PropertyValue $sourceKinds "resource" -1) -eq 1 -and
        (Get-PropertyValue $sourceKinds "var" -1) -eq 17 -and
        (Get-PropertyValue $destinationKinds "resource" -1) -eq 1 -and
        (Get-PropertyValue $destinationKinds "var" -1) -eq 17 -and
        (Get-PropertyValue $sourceStatuses "pass" -1) -eq 18 -and
        (Get-PropertyValue $destinationStatuses "pass" -1) -eq 18
    )
}

function Get-Sha256Text {
    param([AllowEmptyString()][string]$Text)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function ConvertTo-CanonicalValue {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [string] -or $Value -is [ValueType]) { return $Value }
    if ($Value -is [System.Collections.IDictionary]) {
        $ordered = [ordered]@{}
        foreach ($key in @($Value.Keys | ForEach-Object { [string]$_ } | Sort-Object)) {
            $ordered[$key] = ConvertTo-CanonicalValue $Value[$key]
        }
        return [pscustomobject]$ordered
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        return @($Value | ForEach-Object { ConvertTo-CanonicalValue $_ })
    }
    $properties = [ordered]@{}
    foreach ($property in @($Value.PSObject.Properties | Sort-Object Name)) {
        $properties[$property.Name] = ConvertTo-CanonicalValue $property.Value
    }
    return [pscustomobject]$properties
}

function Get-ObjectFingerprint {
    param([AllowNull()][object]$Value)
    $canonical = ConvertTo-CanonicalValue $Value
    return Get-Sha256Text ($canonical | ConvertTo-Json -Depth 100 -Compress)
}

function Get-SourceSet {
    param([Parameter(Mandatory = $true)][System.IO.FileInfo[]]$Files)
    $entries = @(
        $Files |
            Sort-Object FullName |
            ForEach-Object {
                $relative = [System.IO.Path]::GetRelativePath($RepoRoot, $_.FullName).Replace("\", "/")
                [pscustomobject]@{ path = $relative; sha256 = Get-FileSha256 $_.FullName }
            }
    )
    return [pscustomobject]@{
        files = $entries
        sha256 = Get-ObjectFingerprint $entries
    }
}

function Get-SafeMetadata {
    param([AllowNull()][object]$Metadata)
    $safeLabels = [ordered]@{}
    $labels = Get-PropertyValue $Metadata "labels"
    if ($null -ne $labels) {
        foreach ($property in $labels.PSObject.Properties | Sort-Object Name) {
            if ($property.Name -like "app.kubernetes.io/*" -or $property.Name -like "topo.ai/*") {
                $safeLabels[$property.Name] = [string]$property.Value
            }
        }
    }
    $annotationKeys = @()
    $annotations = Get-PropertyValue $Metadata "annotations"
    if ($null -ne $annotations) {
        $annotationKeys = @($annotations.PSObject.Properties.Name | Sort-Object)
    }
    return [pscustomobject]@{
        name = [string](Get-PropertyValue $Metadata "name" "")
        namespace = [string](Get-PropertyValue $Metadata "namespace" "")
        labels = [pscustomobject]$safeLabels
        annotation_keys = $annotationKeys
    }
}

function Convert-EnvironmentEntry {
    param([Parameter(Mandatory = $true)][object]$Entry)
    $name = [string](Get-PropertyValue $Entry "name" "")
    $valueFrom = Get-PropertyValue $Entry "valueFrom"
    $literalAllowlist = @(
        "TOPO_AUTH_MODE", "TOPO_SECRET_STORE_BACKEND", "TOPO_SECRET_KEYRING_FILE",
        "TOPO_BACKEND_URL", "TOPO_AGENT_NAME", "TOPO_ENABLED_PLUGINS",
        "TOPO_CHANGE_WATCH_KUBERNETES", "TOPO_CHANGE_WATCH_AWS",
        "TOPO_CHANGE_WATCH_AZURE", "TOPO_CHANGE_WATCH_GCP",
        "TOPO_COLLECTION_INTERVAL", "TOPO_CHANGE_WATCH_INTERVAL",
        "TOPO_HEARTBEAT_INTERVAL", "TOPO_AGENT_HOME", "TMPDIR"
    )
    $reference = $null
    if ($null -ne $valueFrom) {
        foreach ($kind in @("configMapKeyRef", "secretKeyRef", "fieldRef", "resourceFieldRef")) {
            $candidate = Get-PropertyValue $valueFrom $kind
            if ($null -ne $candidate) {
                $reference = [pscustomobject]@{
                    kind = $kind
                    name = Get-PropertyValue $candidate "name"
                    key = Get-PropertyValue $candidate "key"
                    field_path = Get-PropertyValue $candidate "fieldPath"
                }
                break
            }
        }
    }
    $literalPresent = $null -ne $Entry.PSObject.Properties["value"]
    $literal = $null
    if ($literalPresent -and $literalAllowlist -contains $name) {
        $literal = [string](Get-PropertyValue $Entry "value" "")
    }
    return [pscustomobject]@{
        name = $name
        value_from = $reference
        literal_env_value_present = $literalPresent
        allowlisted_literal_value = $literal
    }
}

function Convert-ContainerContract {
    param([Parameter(Mandatory = $true)][object]$Container)
    return [pscustomobject]@{
        name = Get-PropertyValue $Container "name"
        image = Get-PropertyValue $Container "image"
        command = @(Get-PropertyValue $Container "command" @())
        args = @(Get-PropertyValue $Container "args" @())
        ports = @(
            @(Get-PropertyValue $Container "ports" @()) | ForEach-Object {
                [pscustomobject]@{
                    name = Get-PropertyValue $_ "name"
                    container_port = Get-PropertyValue $_ "containerPort"
                    protocol = Get-PropertyValue $_ "protocol"
                }
            }
        )
        env = @(
            @(Get-PropertyValue $Container "env" @()) |
                ForEach-Object { Convert-EnvironmentEntry $_ } |
                Sort-Object name
        )
        resources = Get-PropertyValue $Container "resources" ([pscustomobject]@{})
        startup_probe = Get-PropertyValue $Container "startupProbe"
        liveness_probe = Get-PropertyValue $Container "livenessProbe"
        readiness_probe = Get-PropertyValue $Container "readinessProbe"
        volume_mounts = @(
            @(Get-PropertyValue $Container "volumeMounts" @()) | ForEach-Object {
                [pscustomobject]@{
                    name = Get-PropertyValue $_ "name"
                    mount_path = Get-PropertyValue $_ "mountPath"
                    read_only = [bool](Get-PropertyValue $_ "readOnly" $false)
                }
            }
        )
    }
}

function Convert-VolumeContract {
    param([Parameter(Mandatory = $true)][object]$Volume)
    $kind = "unknown"
    $reference = $null
    foreach ($candidate in @("secret", "configMap", "emptyDir", "persistentVolumeClaim", "projected", "hostPath")) {
        $value = Get-PropertyValue $Volume $candidate
        if ($null -ne $value) {
            $kind = $candidate
            if ($candidate -eq "secret") { $reference = Get-PropertyValue $value "secretName" }
            if ($candidate -eq "configMap") { $reference = Get-PropertyValue $value "name" }
            if ($candidate -eq "persistentVolumeClaim") { $reference = Get-PropertyValue $value "claimName" }
            if ($candidate -eq "emptyDir") {
                $reference = [pscustomobject]@{
                    medium = Get-PropertyValue $value "medium"
                    size_limit = Get-PropertyValue $value "sizeLimit"
                }
            }
            break
        }
    }
    return [pscustomobject]@{
        name = Get-PropertyValue $Volume "name"
        type = $kind
        reference = $reference
    }
}

function Convert-PodTemplateContract {
    param([Parameter(Mandatory = $true)][object]$Template)
    $spec = Get-PropertyValue $Template "spec" ([pscustomobject]@{})
    return [pscustomobject]@{
        labels = (Get-SafeMetadata (Get-PropertyValue $Template "metadata")).labels
        service_account_name = Get-PropertyValue $spec "serviceAccountName"
        containers = @(
            @(Get-PropertyValue $spec "containers" @()) |
                ForEach-Object { Convert-ContainerContract $_ } |
                Sort-Object name
        )
        init_containers = @(
            @(Get-PropertyValue $spec "initContainers" @()) |
                ForEach-Object { Convert-ContainerContract $_ } |
                Sort-Object name
        )
        volumes = @(
            @(Get-PropertyValue $spec "volumes" @()) |
                ForEach-Object { Convert-VolumeContract $_ } |
                Sort-Object name
        )
    }
}

function Convert-DeploymentContract {
    param([Parameter(Mandatory = $true)][object]$Item)
    $spec = Get-PropertyValue $Item "spec" ([pscustomobject]@{})
    return [pscustomobject]@{
        metadata = Get-SafeMetadata (Get-PropertyValue $Item "metadata")
        replicas = Get-PropertyValue $spec "replicas"
        selector = Get-PropertyValue $spec "selector"
        strategy = Get-PropertyValue $spec "strategy"
        pod_template = Convert-PodTemplateContract (Get-PropertyValue $spec "template")
    }
}

function Convert-ServiceContract {
    param([Parameter(Mandatory = $true)][object]$Item)
    $spec = Get-PropertyValue $Item "spec" ([pscustomobject]@{})
    return [pscustomobject]@{
        metadata = Get-SafeMetadata (Get-PropertyValue $Item "metadata")
        type = Get-PropertyValue $spec "type"
        selector = Get-PropertyValue $spec "selector"
        external_traffic_policy = Get-PropertyValue $spec "externalTrafficPolicy"
        ports = @(
            @(Get-PropertyValue $spec "ports" @()) | ForEach-Object {
                [pscustomobject]@{
                    name = Get-PropertyValue $_ "name"
                    protocol = Get-PropertyValue $_ "protocol"
                    port = Get-PropertyValue $_ "port"
                    target_port = Get-PropertyValue $_ "targetPort"
                    node_port = Get-PropertyValue $_ "nodePort"
                }
            }
        )
    }
}

function Convert-RbacContract {
    param([Parameter(Mandatory = $true)][object]$Item)
    return [pscustomobject]@{
        kind = Get-PropertyValue $Item "kind"
        metadata = Get-SafeMetadata (Get-PropertyValue $Item "metadata")
        rules = @(Get-PropertyValue $Item "rules" @())
        role_ref = Get-PropertyValue $Item "roleRef"
        subjects = @(Get-PropertyValue $Item "subjects" @())
    }
}

function Get-SecretMetadataContracts {
    # The template iterates map keys but never renders map values.
    $template = '{{range .items}}{{.metadata.name}}{{"\t"}}{{.type}}{{"\t"}}{{if .immutable}}{{.immutable}}{{else}}false{{end}}{{"\t"}}{{range $k,$v := .data}}{{$k}}{{","}}{{end}}{{"\t"}}{{range $k,$v := .metadata.labels}}{{$k}}={{$v}},{{end}}{{"\t"}}{{range $k,$v := .metadata.annotations}}{{$k}},{{end}}{{"\n"}}{{end}}'
    $text = Invoke-KubectlReadOnlyText -OperationKey "get resources" -Arguments @(
        "get", "secrets", "--namespace", $Namespace, "--output", "go-template=$template"
    )
    $results = @()
    foreach ($line in @($text -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })) {
        $parts = $line -split "`t", 6
        $labelMap = [ordered]@{}
        if ($parts.Count -ge 5) {
            foreach ($pair in @($parts[4] -split "," | Where-Object { $_ -match "=" })) {
                $name, $value = $pair -split "=", 2
                if ($name -like "app.kubernetes.io/*" -or $name -like "topo.ai/*") {
                    $labelMap[$name] = $value
                }
            }
        }
        $results += [pscustomobject]@{
            name = $parts[0]
            type = if ($parts.Count -gt 1) { $parts[1] } else { "" }
            immutable = if ($parts.Count -gt 2) { $parts[2] -eq "true" } else { $false }
            key_names = if ($parts.Count -gt 3) { @($parts[3] -split "," | Where-Object { $_ } | Sort-Object) } else { @() }
            labels = [pscustomobject]$labelMap
            annotation_keys = if ($parts.Count -gt 5) { @($parts[5] -split "," | Where-Object { $_ } | Sort-Object) } else { @() }
        }
    }
    return @($results | Sort-Object name)
}

function Convert-SecurityGroupRules {
    param([AllowNull()][object[]]$Permissions)
    $rules = @()
    foreach ($permission in @($Permissions)) {
        $base = [ordered]@{
            protocol = Get-PropertyValue $permission "IpProtocol"
            from_port = Get-PropertyValue $permission "FromPort"
            to_port = Get-PropertyValue $permission "ToPort"
        }
        foreach ($pair in @(Get-PropertyValue $permission "UserIdGroupPairs" @())) {
            $rules += [pscustomobject]($base + [ordered]@{
                source_type = "security_group"
                source = Get-PropertyValue $pair "GroupId"
                description = Get-PropertyValue $pair "Description"
            })
        }
        foreach ($range in @(Get-PropertyValue $permission "IpRanges" @())) {
            $rules += [pscustomobject]($base + [ordered]@{
                source_type = "ipv4_cidr"
                source = Get-PropertyValue $range "CidrIp"
                description = Get-PropertyValue $range "Description"
            })
        }
        foreach ($range in @(Get-PropertyValue $permission "Ipv6Ranges" @())) {
            $rules += [pscustomobject]($base + [ordered]@{
                source_type = "ipv6_cidr"
                source = Get-PropertyValue $range "CidrIpv6"
                description = Get-PropertyValue $range "Description"
            })
        }
        foreach ($prefix in @(Get-PropertyValue $permission "PrefixListIds" @())) {
            $rules += [pscustomobject]($base + [ordered]@{
                source_type = "prefix_list"
                source = Get-PropertyValue $prefix "PrefixListId"
                description = Get-PropertyValue $prefix "Description"
            })
        }
        if (
            @(Get-PropertyValue $permission "UserIdGroupPairs" @()).Count -eq 0 -and
            @(Get-PropertyValue $permission "IpRanges" @()).Count -eq 0 -and
            @(Get-PropertyValue $permission "Ipv6Ranges" @()).Count -eq 0 -and
            @(Get-PropertyValue $permission "PrefixListIds" @()).Count -eq 0
        ) {
            $rules += [pscustomobject]($base + [ordered]@{
                source_type = "none"
                source = $null
                description = $null
            })
        }
    }
    return @($rules | Sort-Object protocol, from_port, to_port, source_type, source)
}

function Convert-IamTrustPolicy {
    param([AllowNull()][object]$Policy)
    if ($null -eq $Policy) { return $null }
    return [pscustomobject]@{
        version = Get-PropertyValue $Policy "Version"
        statements = @(
            @(Get-PropertyValue $Policy "Statement" @()) | ForEach-Object {
                $condition = Get-PropertyValue $_ "Condition"
                $conditionKeys = @()
                if ($null -ne $condition) {
                    foreach ($operator in $condition.PSObject.Properties) {
                        foreach ($key in $operator.Value.PSObject.Properties.Name) {
                            $conditionKeys += "$($operator.Name):$key"
                        }
                    }
                }
                [pscustomobject]@{
                    effect = Get-PropertyValue $_ "Effect"
                    action = @(Get-PropertyValue $_ "Action" @())
                    principal = Get-PropertyValue $_ "Principal"
                    condition_keys = @($conditionKeys | Sort-Object -Unique)
                }
            }
        )
    }
}

function Add-UniqueText {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.Generic.List[string]]$List,
        [Parameter(Mandatory = $true)][string]$Value
    )
    if (-not $List.Contains($Value)) { $List.Add($Value) }
}

function Get-RepositoryMigrationHeads {
    $revisions = @{}
    $parents = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $RepoRoot "backend/alembic/versions") -Filter "*.py" -File) {
        $text = Get-Content -LiteralPath $file.FullName -Raw
        $revisionMatch = [regex]::Match($text, '(?m)^revision(?:\s*:\s*str)?\s*=\s*["'']([^"'']+)["'']')
        if (-not $revisionMatch.Success) { continue }
        $revision = $revisionMatch.Groups[1].Value
        $revisions[$revision] = $file.Name
        $parentMatch = [regex]::Match($text, '(?m)^down_revision(?:\s*:[^=]+)?\s*=\s*["'']([^"'']+)["'']')
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
    if (@($SourceHeads).Count -ne 1) { return "SOURCE_HEADS_NOT_UNIQUE" }
    if (@($LiveHeads).Count -gt 1) { return "LIVE_HEADS_NOT_UNIQUE" }
    if (@($LiveHeads).Count -eq 1 -and $SourceHeads[0] -cne $LiveHeads[0]) { return "DIFFERENT" }
    if (-not $ProbeCompleted -or @($LiveHeads).Count -eq 0) { return "UNKNOWN_REQUIRED" }
    return "MATCH"
}

function Assert-ReceiptShape {
    param([Parameter(Mandatory = $true)][object]$Receipt)
    $required = @(
        "schema_version", "captured_at_utc", "tool_versions", "authority", "environment",
        "source", "eks", "kubernetes", "images", "network", "edge", "waf", "acm",
        "dns", "rds", "migrations", "secretstore_recovery", "terraform", "iam",
        "logging", "cost_relevant_resources", "reproducibility", "fingerprints", "safety"
    )
    foreach ($name in $required) {
        if ($null -eq $Receipt.PSObject.Properties[$name]) {
            throw "Inventory schema requirement missing: $name"
        }
    }
    if ($Receipt.schema_version -ne "cx0a.reproducibility.v1") { throw "Inventory schema version mismatch." }
    if ($Receipt.environment.aws_account_id -ne $ExpectedAccount) { throw "Inventory account mismatch." }
    foreach ($name in @(
        "aws_mutation_performed", "kubernetes_mutation_performed", "dns_mutation_performed",
        "database_mutation_performed", "deletion_performed", "secret_values_emitted"
    )) {
        if ([bool](Get-PropertyValue $Receipt.safety $name $true)) {
            throw "Inventory safety marker must remain false: $name"
        }
    }
}

$blockers = [System.Collections.Generic.List[string]]::new()
$unknowns = [System.Collections.Generic.List[string]]::new()

# Source authority is captured before network access.
$currentBranch = Invoke-NativeCapture "git" @("branch", "--show-current") "Git branch read"
$currentHead = Invoke-NativeCapture "git" @("rev-parse", "HEAD") "Git HEAD read"
$currentTree = Invoke-NativeCapture "git" @("rev-parse", "HEAD^{tree}") "Git tree read"
$originMain = Invoke-NativeCapture "git" @("rev-parse", "refs/remotes/origin/main") "Git origin/main read"
$gitStatus = Invoke-NativeCapture "git" @("status", "--porcelain=v1", "--untracked-files=all") "Git status read"
$remoteUrl = Invoke-NativeCapture "git" @("remote", "get-url", "origin") "Git remote read"
$remoteUrl = $remoteUrl -replace '^(https?://)[^/@]+@', '$1REDACTED@'

if ($currentBranch -ne $ExpectedBranch) {
    throw "STOP: expected branch $ExpectedBranch"
}

$architectureFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $RepoRoot "docs/architecture") -Filter "cloud-v1-*.md" -File
    Get-Item -LiteralPath (Join-Path $RepoRoot "docs/architecture/cx-0-cost-0-reproducibility-freeze-v1.md")
)
$terraformFiles = @(Get-ChildItem -LiteralPath $TerraformRoot -Filter "*.tf" -File)
$kubernetesFiles = @(Get-ChildItem -LiteralPath $KubernetesRoot -File -Recurse)
$migrationFiles = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot "backend/alembic") -File -Recurse)

$source = [pscustomobject]@{
    remote_url_sanitized = $remoteUrl
    origin_main_head = $originMain
    git_status_clean = [string]::IsNullOrWhiteSpace($gitStatus)
    git_status_paths = @($gitStatus -split "`r?`n" | Where-Object { $_ })
    architecture = Get-SourceSet $architectureFiles
    terraform = Get-SourceSet $terraformFiles
    kubernetes = Get-SourceSet $kubernetesFiles
    migrations = Get-SourceSet $migrationFiles
}

# Fail closed on the exact live identity before any broad inventory query.
$identity = Invoke-AwsReadOnlyJson "sts" "get-caller-identity"
if ([string](Get-PropertyValue $identity "Account") -ne $ExpectedAccount) {
    throw "STOP: expected AWS account 297361542190"
}

$kubeConfig = (Invoke-KubectlReadOnlyText "config view" @("config", "view", "--minify", "--output", "json")) | ConvertFrom-Json -Depth 50
$kubeContext = [string](Get-PropertyValue $kubeConfig "current-context")
if ($kubeContext -ne $ExpectedCluster) { throw "STOP: expected topo-golden" }

$clusterResponse = Invoke-AwsReadOnlyJson "eks" "describe-cluster" @("--name", $ClusterName)
$cluster = Get-PropertyValue $clusterResponse "cluster"
$clusterEndpoint = [string](Get-PropertyValue $cluster "endpoint")
$kubeServer = [string](Get-PropertyValue @((Get-PropertyValue $kubeConfig "clusters" @()))[0].cluster "server")
if ($clusterEndpoint -ne $kubeServer) {
    throw "STOP: Kubernetes context endpoint does not match the accepted EKS cluster."
}

$nodeGroupNames = @((Get-PropertyValue (Invoke-AwsReadOnlyJson "eks" "list-nodegroups" @("--cluster-name", $ClusterName)) "nodegroups" @()) | Sort-Object)
$nodeGroups = @()
foreach ($nodeGroupName in $nodeGroupNames) {
    $nodeGroup = Get-PropertyValue (Invoke-AwsReadOnlyJson "eks" "describe-nodegroup" @(
        "--cluster-name", $ClusterName, "--nodegroup-name", [string]$nodeGroupName
    )) "nodegroup"
    $nodeGroups += [pscustomobject]@{
        name = Get-PropertyValue $nodeGroup "nodegroupName"
        arn = Get-PropertyValue $nodeGroup "nodegroupArn"
        status = Get-PropertyValue $nodeGroup "status"
        capacity_type = Get-PropertyValue $nodeGroup "capacityType"
        ami_type = Get-PropertyValue $nodeGroup "amiType"
        instance_types = @(Get-PropertyValue $nodeGroup "instanceTypes" @())
        scaling = Get-PropertyValue $nodeGroup "scalingConfig"
        subnets = @((Get-PropertyValue $nodeGroup "subnets" @()) | Sort-Object)
        node_role_arn = Get-PropertyValue $nodeGroup "nodeRole"
        launch_template = Get-PropertyValue $nodeGroup "launchTemplate"
        labels = Get-PropertyValue $nodeGroup "labels"
        taints = @(Get-PropertyValue $nodeGroup "taints" @())
        kubernetes_version = Get-PropertyValue $nodeGroup "version"
        release_version = Get-PropertyValue $nodeGroup "releaseVersion"
    }
}

$eks = [pscustomobject]@{
    cluster = [pscustomobject]@{
        name = Get-PropertyValue $cluster "name"
        arn = Get-PropertyValue $cluster "arn"
        kubernetes_version = Get-PropertyValue $cluster "version"
        platform_version = Get-PropertyValue $cluster "platformVersion"
        status = Get-PropertyValue $cluster "status"
        endpoint_public_access = Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "endpointPublicAccess"
        endpoint_private_access = Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "endpointPrivateAccess"
        vpc_id = Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "vpcId"
        cluster_security_group_id = Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "clusterSecurityGroupId"
        security_group_ids = @((Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "securityGroupIds" @()) | Sort-Object)
        subnet_ids = @((Get-PropertyValue (Get-PropertyValue $cluster "resourcesVpcConfig") "subnetIds" @()) | Sort-Object)
        oidc_issuer = Get-PropertyValue (Get-PropertyValue (Get-PropertyValue $cluster "identity") "oidc") "issuer"
        control_plane_log_types = @(
            @(Get-PropertyValue (Get-PropertyValue $cluster "logging") "clusterLogging" @()) |
                Where-Object { Get-PropertyValue $_ "enabled" $false } |
                ForEach-Object { @(Get-PropertyValue $_ "types" @()) } |
                Sort-Object -Unique
        )
        encryption = @(
            @(Get-PropertyValue $cluster "encryptionConfig" @()) | ForEach-Object {
                [pscustomobject]@{
                    resources = @(Get-PropertyValue $_ "resources" @())
                    key_arn = Get-PropertyValue (Get-PropertyValue $_ "provider") "keyArn"
                }
            }
        )
    }
    node_groups = @($nodeGroups | Sort-Object name)
}

# Kubernetes inventory uses explicit safe projections. Secret values are never requested.
$deploymentItems = @(Get-PropertyValue (Invoke-KubectlGetJson "deployments") "items" @())
$podItems = @(Get-PropertyValue (Invoke-KubectlGetJson "pods") "items" @())
$serviceItems = @(Get-PropertyValue (Invoke-KubectlGetJson "services") "items" @())
$configMapItems = @(Get-PropertyValue (Invoke-KubectlGetJson "configmaps") "items" @())
$serviceAccountItems = @(Get-PropertyValue (Invoke-KubectlGetJson "serviceaccounts") "items" @())
$roleItems = @(Get-PropertyValue (Invoke-KubectlGetJson "roles") "items" @())
$roleBindingItems = @(Get-PropertyValue (Invoke-KubectlGetJson "rolebindings") "items" @())
$jobItems = @(Get-PropertyValue (Invoke-KubectlGetJson "jobs") "items" @())
$cronJobItems = @(Get-PropertyValue (Invoke-KubectlGetJson "cronjobs") "items" @())
$pvcItems = @(Get-PropertyValue (Invoke-KubectlGetJson "persistentvolumeclaims") "items" @())
$clusterRoleItems = @(
    @(Get-PropertyValue (Invoke-KubectlGetJson "clusterroles" -ClusterScoped) "items" @()) |
        Where-Object {
            (Get-PropertyValue (Get-PropertyValue $_ "metadata") "name" "") -like "topo-*" -or
            (Get-PropertyValue (Get-PropertyValue (Get-PropertyValue $_ "metadata") "labels") "app.kubernetes.io/part-of" "") -eq "topo-ai"
        }
)
$clusterRoleBindingItems = @(
    @(Get-PropertyValue (Invoke-KubectlGetJson "clusterrolebindings" -ClusterScoped) "items" @()) |
        Where-Object {
            (Get-PropertyValue (Get-PropertyValue $_ "metadata") "name" "") -like "topo-*" -or
            (Get-PropertyValue (Get-PropertyValue (Get-PropertyValue $_ "metadata") "labels") "app.kubernetes.io/part-of" "") -eq "topo-ai"
        }
)

$configMaps = @()
$plaintextConfigMapKeys = @("browser-allowed-origins-json", "cluster-name", "environment", "installation-id")
foreach ($item in $configMapItems) {
    $values = [ordered]@{}
    $data = Get-PropertyValue $item "data"
    if ($null -ne $data) {
        foreach ($property in $data.PSObject.Properties | Sort-Object Name) {
            $entry = [ordered]@{ sha256 = Get-Sha256Text ([string]$property.Value) }
            if ($plaintextConfigMapKeys -contains $property.Name) {
                $entry["allowlisted_plaintext"] = [string]$property.Value
            }
            $values[$property.Name] = [pscustomobject]$entry
        }
    }
    $configMaps += [pscustomobject]@{
        metadata = Get-SafeMetadata (Get-PropertyValue $item "metadata")
        keys = @($values.Keys)
        values = [pscustomobject]$values
    }
}

$deployments = @($deploymentItems | ForEach-Object { Convert-DeploymentContract $_ } | Sort-Object { $_.metadata.name })
$services = @($serviceItems | ForEach-Object { Convert-ServiceContract $_ } | Sort-Object { $_.metadata.name })
$kubernetesSourceContract = (
    Invoke-NativeCapture $PythonExecutable @(
        $KubernetesContractTool,
        "source",
        "--manifest-root", $KubernetesRoot,
        "--backend-image", $AcceptedBackendImage
    ) "Kubernetes source reconstruction contract"
) | ConvertFrom-Json -Depth 100
if (
    (Get-PropertyValue $kubernetesSourceContract "schema_version") -ne "cx0.kubernetes-source-contract.v1" -or
    (Get-PropertyValue $kubernetesSourceContract "secret_values_emitted" $true) -ne $false
) {
    throw "Kubernetes source reconstruction contract is invalid."
}
$kubernetes = [pscustomobject]@{
    context = $kubeContext
    server = $kubeServer
    namespace = $Namespace
    deployments = $deployments
    services = $services
    source_contract = $kubernetesSourceContract
    config_maps = @($configMaps | Sort-Object { $_.metadata.name })
    secrets = @(Get-SecretMetadataContracts)
    service_accounts = @($serviceAccountItems | ForEach-Object { Get-SafeMetadata (Get-PropertyValue $_ "metadata") } | Sort-Object name)
    roles = @($roleItems | ForEach-Object { Convert-RbacContract $_ } | Sort-Object { $_.metadata.name })
    role_bindings = @($roleBindingItems | ForEach-Object { Convert-RbacContract $_ } | Sort-Object { $_.metadata.name })
    cluster_roles = @($clusterRoleItems | ForEach-Object { Convert-RbacContract $_ } | Sort-Object { $_.metadata.name })
    cluster_role_bindings = @($clusterRoleBindingItems | ForEach-Object { Convert-RbacContract $_ } | Sort-Object { $_.metadata.name })
    jobs = @($jobItems | ForEach-Object {
        [pscustomobject]@{
            metadata = Get-SafeMetadata (Get-PropertyValue $_ "metadata")
            pod_template = Convert-PodTemplateContract (Get-PropertyValue (Get-PropertyValue $_ "spec") "template")
        }
    } | Sort-Object { $_.metadata.name })
    cron_jobs = @($cronJobItems | ForEach-Object {
        [pscustomobject]@{
            metadata = Get-SafeMetadata (Get-PropertyValue $_ "metadata")
            schedule = Get-PropertyValue (Get-PropertyValue $_ "spec") "schedule"
            pod_template = Convert-PodTemplateContract (
                Get-PropertyValue (Get-PropertyValue (Get-PropertyValue (Get-PropertyValue $_ "spec") "jobTemplate") "spec") "template"
            )
        }
    } | Sort-Object { $_.metadata.name })
    persistent_volume_claims = @($pvcItems | ForEach-Object {
        [pscustomobject]@{
            metadata = Get-SafeMetadata (Get-PropertyValue $_ "metadata")
            storage_class_name = Get-PropertyValue (Get-PropertyValue $_ "spec") "storageClassName"
            access_modes = @(Get-PropertyValue (Get-PropertyValue $_ "spec") "accessModes" @())
            resources = Get-PropertyValue (Get-PropertyValue $_ "spec") "resources"
        }
    } | Sort-Object { $_.metadata.name })
}

$originConfig = $null
foreach ($configMap in $kubernetes.config_maps) {
    if ($configMap.metadata.name -eq "topo-runtime-config") {
        $originProperty = $configMap.values.PSObject.Properties["browser-allowed-origins-json"]
        if ($null -ne $originProperty) {
            $originConfig = Get-PropertyValue $originProperty.Value "allowlisted_plaintext"
        }
    }
}
if ($originConfig -ne $AcceptedOrigin) {
    throw "STOP: accepted browser-origin contract differs"
}

$runningImages = @()
foreach ($deployment in $deployments) {
    foreach ($container in @($deployment.pod_template.init_containers) + @($deployment.pod_template.containers)) {
        $runningImages += [pscustomobject]@{
            deployment = $deployment.metadata.name
            container = $container.name
            image = $container.image
            digest = if ([string]$container.image -match '@(sha256:[0-9a-f]{64})$') { $Matches[1] } else { $null }
        }
    }
}
$podImageStatuses = @()
foreach ($pod in $podItems) {
    $podMetadata = Get-PropertyValue $pod "metadata" ([pscustomobject]@{})
    $podSpec = Get-PropertyValue $pod "spec" ([pscustomobject]@{})
    $podStatus = Get-PropertyValue $pod "status" ([pscustomobject]@{})
    $containerStatuses = @{}
    foreach ($status in @(Get-PropertyValue $podStatus "containerStatuses" @())) {
        $containerStatuses[[string](Get-PropertyValue $status "name")] = $status
    }
    foreach ($container in @(Get-PropertyValue $podSpec "containers" @())) {
        $containerName = [string](Get-PropertyValue $container "name")
        $status = if ($containerStatuses.ContainsKey($containerName)) {
            $containerStatuses[$containerName]
        } else {
            $null
        }
        $imageId = [string](Get-PropertyValue $status "imageID")
        $podLabels = Get-PropertyValue $podMetadata "labels" ([pscustomobject]@{})
        $podImageStatuses += [pscustomobject]@{
            pod = Get-PropertyValue $podMetadata "name"
            workload_name = Get-PropertyValue $podLabels "app.kubernetes.io/name"
            container = $containerName
            configured_image = Get-PropertyValue $container "image"
            running_image_id = $imageId
            running_digest = if ($imageId -match '@(sha256:[0-9a-f]{64})$') { $Matches[1] } else { $null }
            ready = [bool](Get-PropertyValue $status "ready" $false)
        }
    }
}
$ecrResponse = Invoke-AwsReadOnlyJson "ecr" "describe-images" @("--repository-name", $EcrRepository)
$ecrImages = @(
    @(Get-PropertyValue $ecrResponse "imageDetails" @()) | ForEach-Object {
        [pscustomobject]@{
            repository = $EcrRepository
            registry_id = Get-PropertyValue $_ "registryId"
            digest = Get-PropertyValue $_ "imageDigest"
            media_type = Get-PropertyValue $_ "imageManifestMediaType"
            artifact_media_type = Get-PropertyValue $_ "artifactMediaType"
            size_bytes = Get-PropertyValue $_ "imageSizeInBytes"
            pushed_at = Get-PropertyValue $_ "imagePushedAt"
            tags = @((Get-PropertyValue $_ "imageTags" @()) | Sort-Object)
        }
    } | Sort-Object digest
)
$ecrRepositoryResponse = Invoke-AwsReadOnlyJson "ecr" "describe-repositories" @("--repository-names", $EcrRepository)
$ecrRepositoryDetails = @((Get-PropertyValue $ecrRepositoryResponse "repositories" @()))[0]
$lifecycleResponse = Invoke-AwsReadOnlyJson "ecr" "get-lifecycle-policy" @(
    "--repository-name", $EcrRepository
) -AllowedEmptyErrorMarker "LifecyclePolicyNotFoundException"
$lifecyclePolicyText = [string](Get-PropertyValue $lifecycleResponse "lifecyclePolicyText")
$lifecyclePolicyExists = -not [string]::IsNullOrWhiteSpace($lifecyclePolicyText)
$lifecyclePolicyRuleCount = 0
if ($lifecyclePolicyExists) {
    $lifecyclePolicy = $lifecyclePolicyText | ConvertFrom-Json -Depth 20
    $lifecyclePolicyRuleCount = @(Get-PropertyValue $lifecyclePolicy "rules" @()).Count
}
# Fail closed: any lifecycle policy requires a separate rule-level retention
# review before an accepted digest can be treated as durable authority.
$observerImageRetentionSafe = -not $lifecyclePolicyExists
$ecrDigests = @($ecrImages.digest)
$backendDigest = ($AcceptedBackendImage -split "@", 2)[1]
$frontendDigest = ($AcceptedFrontendImage -split "@", 2)[1]
$observerDigest = ($AcceptedObserverImage -split "@", 2)[1]
if ($runningImages.image -notcontains $AcceptedBackendImage) { Add-UniqueText $blockers "ACCEPTED_BACKEND_IMAGE_NOT_RUNNING" }
if ($runningImages.image -notcontains $AcceptedFrontendImage) { Add-UniqueText $blockers "ACCEPTED_FRONTEND_IMAGE_NOT_RUNNING" }
if ($ecrDigests -notcontains $backendDigest) { Add-UniqueText $blockers "ACCEPTED_BACKEND_DIGEST_MISSING_FROM_ECR" }
if ($ecrDigests -notcontains $frontendDigest) { Add-UniqueText $blockers "ACCEPTED_FRONTEND_DIGEST_MISSING_FROM_ECR" }
$observerConfiguredImage = @($runningImages | Where-Object { $_.deployment -eq "topo-observer" -and $_.container -eq "observer" } | Select-Object -First 1)
$observerPodImage = @($podImageStatuses | Where-Object { $_.workload_name -eq "topo-observer" -and $_.container -eq "observer" } | Select-Object -First 1)
$observerSourceManifest = Join-Path $KubernetesRoot "observer.yaml"
$observerSourcePinned = (
    (Test-Path -LiteralPath $observerSourceManifest -PathType Leaf) -and
    (Get-Content -LiteralPath $observerSourceManifest -Raw).Contains("image: $AcceptedObserverImage")
)
$observerEcrImage = @($ecrImages | Where-Object { $_.digest -eq $observerDigest } | Select-Object -First 1)
if ($observerConfiguredImage.Count -eq 0 -or $observerConfiguredImage[0].image -ne $AcceptedObserverImage) {
    Add-UniqueText $blockers "ACCEPTED_OBSERVER_IMAGE_NOT_CONFIGURED"
}
if (
    $observerPodImage.Count -eq 0 -or
    $observerPodImage[0].running_digest -ne $observerDigest -or
    $observerPodImage[0].ready -ne $true
) {
    Add-UniqueText $blockers "ACCEPTED_OBSERVER_IMAGE_NOT_RUNNING_READY"
}
if ($observerEcrImage.Count -eq 0) { Add-UniqueText $blockers "ACCEPTED_OBSERVER_DIGEST_MISSING_FROM_ECR" }
if (-not $observerSourcePinned) { Add-UniqueText $blockers "ACCEPTED_OBSERVER_IMAGE_NOT_PINNED_IN_SOURCE" }
if (-not $observerImageRetentionSafe) { Add-UniqueText $blockers "ACCEPTED_OBSERVER_DIGEST_RETENTION_NOT_PROVEN" }

$images = [pscustomobject]@{
    authority = [pscustomobject]@{
        schema_version = $ImageAuthority.schema_version
        aws_account_id = $ImageAuthority.aws_account_id
        region = $ImageAuthority.region
        repository = $ImageAuthority.repository
        accepted_cloud_head = $ImageAuthority.accepted_cloud_head
        backend_digest = $ImageAuthority.images.backend.digest
        backend_publication_source_commit = $ImageAuthority.images.backend.publication_source_commit
        backend_publication_source_tree = $ImageAuthority.images.backend.publication_source_tree
        backend_repair_commit = $ImageAuthority.images.backend.repair_commit
        frontend_digest = $ImageAuthority.images.frontend.digest
        observer_digest = $ImageAuthority.images.observer.digest
        authority_class = "DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY"
    }
    accepted_backend = $AcceptedBackendImage
    accepted_frontend = $AcceptedFrontendImage
    accepted_observer = $AcceptedObserverImage
    observer = [pscustomobject]@{
        workload = "topo-observer"
        container = "observer"
        configured_image = if ($observerConfiguredImage.Count -gt 0) { $observerConfiguredImage[0].image } else { $null }
        configured_digest = if ($observerConfiguredImage.Count -gt 0) { $observerConfiguredImage[0].digest } else { $null }
        running_image_id = if ($observerPodImage.Count -gt 0) { $observerPodImage[0].running_image_id } else { $null }
        running_digest = if ($observerPodImage.Count -gt 0) { $observerPodImage[0].running_digest } else { $null }
        ready = if ($observerPodImage.Count -gt 0) { $observerPodImage[0].ready } else { $false }
        source_pinned = $observerSourcePinned
        ecr_digest_exists = $observerEcrImage.Count -gt 0
        retention_safe = $observerImageRetentionSafe
    }
    running = @($runningImages | Sort-Object deployment, container)
    running_pods = @($podImageStatuses | Sort-Object pod, container)
    ecr_repository = $EcrRepository
    ecr_images = $ecrImages
    ecr_repository_contract = [pscustomobject]@{
        registry_id = Get-PropertyValue $ecrRepositoryDetails "registryId"
        repository_name = Get-PropertyValue $ecrRepositoryDetails "repositoryName"
        repository_arn = Get-PropertyValue $ecrRepositoryDetails "repositoryArn"
        repository_uri = Get-PropertyValue $ecrRepositoryDetails "repositoryUri"
        tag_mutability = Get-PropertyValue $ecrRepositoryDetails "imageTagMutability"
        scan_on_push = Get-PropertyValue (Get-PropertyValue $ecrRepositoryDetails "imageScanningConfiguration") "scanOnPush"
        encryption_type = Get-PropertyValue (Get-PropertyValue $ecrRepositoryDetails "encryptionConfiguration") "encryptionType"
        lifecycle_policy_exists = $lifecyclePolicyExists
        lifecycle_policy_rule_count = $lifecyclePolicyRuleCount
        lifecycle_policy_sha256 = if ($lifecyclePolicyExists) { Get-Sha256Text $lifecyclePolicyText } else { $null }
        accepted_observer_digest_retention_safe = $observerImageRetentionSafe
    }
}

# RDS is queried before security groups so its exact private boundary can be included.
$rdsResponse = Invoke-AwsReadOnlyJson "rds" "describe-db-instances" @("--db-instance-identifier", "topo-golden-postgres")
$db = @((Get-PropertyValue $rdsResponse "DBInstances" @()))[0]
$rdsSecurityGroups = @(
    @(Get-PropertyValue $db "VpcSecurityGroups" @()) |
        ForEach-Object { Get-PropertyValue $_ "VpcSecurityGroupId" } |
        Sort-Object
)
$rds = [pscustomobject]@{
    identifier = Get-PropertyValue $db "DBInstanceIdentifier"
    arn = Get-PropertyValue $db "DBInstanceArn"
    status = Get-PropertyValue $db "DBInstanceStatus"
    engine = Get-PropertyValue $db "Engine"
    engine_version = Get-PropertyValue $db "EngineVersion"
    instance_class = Get-PropertyValue $db "DBInstanceClass"
    storage_type = Get-PropertyValue $db "StorageType"
    allocated_storage_gib = Get-PropertyValue $db "AllocatedStorage"
    max_allocated_storage_gib = Get-PropertyValue $db "MaxAllocatedStorage"
    storage_encrypted = Get-PropertyValue $db "StorageEncrypted"
    kms_key_arn = Get-PropertyValue $db "KmsKeyId"
    multi_az = Get-PropertyValue $db "MultiAZ"
    availability_zone = Get-PropertyValue $db "AvailabilityZone"
    secondary_availability_zone = Get-PropertyValue $db "SecondaryAvailabilityZone"
    subnet_group = Get-PropertyValue (Get-PropertyValue $db "DBSubnetGroup") "DBSubnetGroupName"
    subnet_ids = @(
        @(Get-PropertyValue (Get-PropertyValue $db "DBSubnetGroup") "Subnets" @()) |
            ForEach-Object { Get-PropertyValue (Get-PropertyValue $_ "SubnetIdentifier") "Value" (Get-PropertyValue $_ "SubnetIdentifier") }
    )
    vpc_security_group_ids = $rdsSecurityGroups
    parameter_groups = @(
        @(Get-PropertyValue $db "DBParameterGroups" @()) | ForEach-Object { Get-PropertyValue $_ "DBParameterGroupName" }
    )
    option_groups = @(
        @(Get-PropertyValue $db "OptionGroupMemberships" @()) | ForEach-Object { Get-PropertyValue $_ "OptionGroupName" }
    )
    backup_retention_days = Get-PropertyValue $db "BackupRetentionPeriod"
    backup_window = Get-PropertyValue $db "PreferredBackupWindow"
    maintenance_window = Get-PropertyValue $db "PreferredMaintenanceWindow"
    deletion_protection = Get-PropertyValue $db "DeletionProtection"
    publicly_accessible = Get-PropertyValue $db "PubliclyAccessible"
    endpoint_address = Get-PropertyValue (Get-PropertyValue $db "Endpoint") "Address"
    port = Get-PropertyValue (Get-PropertyValue $db "Endpoint") "Port"
    performance_insights_enabled = Get-PropertyValue $db "PerformanceInsightsEnabled"
    monitoring_interval = Get-PropertyValue $db "MonitoringInterval"
    monitoring_role_arn = Get-PropertyValue $db "MonitoringRoleArn"
    ca_certificate_identifier = Get-PropertyValue $db "CACertificateIdentifier"
    iam_database_authentication_enabled = Get-PropertyValue $db "IAMDatabaseAuthenticationEnabled"
    latest_restorable_time = Get-PropertyValue $db "LatestRestorableTime"
    master_secret_arn = Get-PropertyValue @((Get-PropertyValue $db "MasterUserSecret" @()))[0] "SecretArn"
}
$snapshotResponse = Invoke-AwsReadOnlyJson "rds" "describe-db-snapshots" @("--db-instance-identifier", "topo-golden-postgres")
$rds | Add-Member -NotePropertyName snapshots -NotePropertyValue @(
    @(Get-PropertyValue $snapshotResponse "DBSnapshots" @()) | ForEach-Object {
        [pscustomobject]@{
            identifier = Get-PropertyValue $_ "DBSnapshotIdentifier"
            arn = Get-PropertyValue $_ "DBSnapshotArn"
            type = Get-PropertyValue $_ "SnapshotType"
            status = Get-PropertyValue $_ "Status"
            encrypted = Get-PropertyValue $_ "Encrypted"
            kms_key_arn = Get-PropertyValue $_ "KmsKeyId"
            created_at = Get-PropertyValue $_ "SnapshotCreateTime"
        }
    } | Sort-Object created_at
)

# Edge and target health.
$loadBalancer = @((Get-PropertyValue (Invoke-AwsReadOnlyJson "elbv2" "describe-load-balancers" @("--load-balancer-arns", $AcceptedAlbArn)) "LoadBalancers" @()))[0]
$listenersRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "elbv2" "describe-listeners" @("--load-balancer-arn", $AcceptedAlbArn)) "Listeners" @())
$listeners = @()
foreach ($listener in $listenersRaw) {
    $listenerArn = [string](Get-PropertyValue $listener "ListenerArn")
    $rulesRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "elbv2" "describe-rules" @("--listener-arn", $listenerArn)) "Rules" @())
    $listeners += [pscustomobject]@{
        arn = $listenerArn
        port = Get-PropertyValue $listener "Port"
        protocol = Get-PropertyValue $listener "Protocol"
        ssl_policy = Get-PropertyValue $listener "SslPolicy"
        certificate_arns = @(
            @(Get-PropertyValue $listener "Certificates" @()) | ForEach-Object { Get-PropertyValue $_ "CertificateArn" }
        )
        default_actions = @(Get-PropertyValue $listener "DefaultActions" @())
        rules = @(
            $rulesRaw | ForEach-Object {
                [pscustomobject]@{
                    arn = Get-PropertyValue $_ "RuleArn"
                    priority = Get-PropertyValue $_ "Priority"
                    conditions = @(Get-PropertyValue $_ "Conditions" @())
                    actions = @(Get-PropertyValue $_ "Actions" @())
                }
            } | Sort-Object priority
        )
    }
}
$targetGroupsRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "elbv2" "describe-target-groups" @("--load-balancer-arn", $AcceptedAlbArn)) "TargetGroups" @())
$targetGroups = @()
foreach ($targetGroup in $targetGroupsRaw) {
    $targetGroupArn = [string](Get-PropertyValue $targetGroup "TargetGroupArn")
    $health = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "elbv2" "describe-target-health" @("--target-group-arn", $targetGroupArn)) "TargetHealthDescriptions" @())
    $targetGroups += [pscustomobject]@{
        arn = $targetGroupArn
        name = Get-PropertyValue $targetGroup "TargetGroupName"
        target_type = Get-PropertyValue $targetGroup "TargetType"
        protocol = Get-PropertyValue $targetGroup "Protocol"
        port = Get-PropertyValue $targetGroup "Port"
        vpc_id = Get-PropertyValue $targetGroup "VpcId"
        health_check = [pscustomobject]@{
            protocol = Get-PropertyValue $targetGroup "HealthCheckProtocol"
            port = Get-PropertyValue $targetGroup "HealthCheckPort"
            path = Get-PropertyValue $targetGroup "HealthCheckPath"
            interval_seconds = Get-PropertyValue $targetGroup "HealthCheckIntervalSeconds"
            timeout_seconds = Get-PropertyValue $targetGroup "HealthCheckTimeoutSeconds"
            healthy_threshold = Get-PropertyValue $targetGroup "HealthyThresholdCount"
            unhealthy_threshold = Get-PropertyValue $targetGroup "UnhealthyThresholdCount"
            matcher = Get-PropertyValue (Get-PropertyValue $targetGroup "Matcher") "HttpCode"
        }
        registered_targets = @(
            $health | ForEach-Object {
                [pscustomobject]@{
                    id = Get-PropertyValue (Get-PropertyValue $_ "Target") "Id"
                    port = Get-PropertyValue (Get-PropertyValue $_ "Target") "Port"
                    state = Get-PropertyValue (Get-PropertyValue $_ "TargetHealth") "State"
                }
            } | Sort-Object id, port
        )
        health_summary = @(
            $health |
                Group-Object { Get-PropertyValue (Get-PropertyValue $_ "TargetHealth") "State" } |
                ForEach-Object { [pscustomobject]@{ state = $_.Name; count = $_.Count } } |
                Sort-Object state
        )
    }
}
$edge = [pscustomobject]@{
    load_balancer = [pscustomobject]@{
        arn = Get-PropertyValue $loadBalancer "LoadBalancerArn"
        name = Get-PropertyValue $loadBalancer "LoadBalancerName"
        scheme = Get-PropertyValue $loadBalancer "Scheme"
        type = Get-PropertyValue $loadBalancer "Type"
        state = Get-PropertyValue (Get-PropertyValue $loadBalancer "State") "Code"
        dns_name = Get-PropertyValue $loadBalancer "DNSName"
        canonical_hosted_zone_id = Get-PropertyValue $loadBalancer "CanonicalHostedZoneId"
        security_groups = @((Get-PropertyValue $loadBalancer "SecurityGroups" @()) | Sort-Object)
        subnets = @(
            @(Get-PropertyValue $loadBalancer "AvailabilityZones" @()) | ForEach-Object {
                [pscustomobject]@{
                    availability_zone = Get-PropertyValue $_ "ZoneName"
                    subnet_id = Get-PropertyValue $_ "SubnetId"
                }
            } | Sort-Object availability_zone
        )
        ip_address_type = Get-PropertyValue $loadBalancer "IpAddressType"
    }
    listeners = @($listeners | Sort-Object port)
    target_groups = @($targetGroups | Sort-Object name)
}

# Network, routes, security groups, and continuous-cost candidates.
$securityGroupIds = @($AcceptedAlbSecurityGroup, $AcceptedWorkerSecurityGroup) + $rdsSecurityGroups | Sort-Object -Unique
$securityGroupArguments = @("--group-ids") + @($securityGroupIds)
$securityGroupsRaw = @(
    Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-security-groups" $securityGroupArguments) "SecurityGroups" @()
)
$securityGroups = @(
    $securityGroupsRaw | ForEach-Object {
        [pscustomobject]@{
            id = Get-PropertyValue $_ "GroupId"
            name = Get-PropertyValue $_ "GroupName"
            vpc_id = Get-PropertyValue $_ "VpcId"
            ingress = @(Convert-SecurityGroupRules @(Get-PropertyValue $_ "IpPermissions" @()))
            egress = @(Convert-SecurityGroupRules @(Get-PropertyValue $_ "IpPermissionsEgress" @()))
        }
    } | Sort-Object id
)
$workerGroup = @($securityGroups | Where-Object { $_.id -eq $AcceptedWorkerSecurityGroup } | Select-Object -First 1)
foreach ($port in @(32080, 32081)) {
    foreach ($rule in @($workerGroup.ingress)) {
        $from = if ($null -eq $rule.from_port) { -1 } else { [int]$rule.from_port }
        $to = if ($null -eq $rule.to_port) { -1 } else { [int]$rule.to_port }
        if ($from -le $port -and $to -ge $port) {
            if ($rule.source_type -ne "security_group" -or $rule.source -ne $AcceptedAlbSecurityGroup) {
                Add-UniqueText $blockers "WORKER_NODEPORT_${port}_HAS_UNEXPECTED_SOURCE"
            }
        }
    }
}

$vpc = @((Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-vpcs" @("--vpc-ids", $AcceptedVpc)) "Vpcs" @()))[0]
$subnetsRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-subnets" @("--filters", "Name=vpc-id,Values=$AcceptedVpc")) "Subnets" @())
$routeTablesRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-route-tables" @("--filters", "Name=vpc-id,Values=$AcceptedVpc")) "RouteTables" @())
$internetGatewaysRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-internet-gateways" @("--filters", "Name=attachment.vpc-id,Values=$AcceptedVpc")) "InternetGateways" @())
$natGatewaysRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-nat-gateways" @("--filter", "Name=vpc-id,Values=$AcceptedVpc")) "NatGateways" @())
$vpcEndpointsRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-vpc-endpoints" @("--filters", "Name=vpc-id,Values=$AcceptedVpc")) "VpcEndpoints" @())
$networkAclsRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-network-acls" @("--filters", "Name=vpc-id,Values=$AcceptedVpc")) "NetworkAcls" @())
$addressesRaw = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "ec2" "describe-addresses" @("--filters", "Name=domain,Values=vpc")) "Addresses" @())

$network = [pscustomobject]@{
    vpc = [pscustomobject]@{
        id = Get-PropertyValue $vpc "VpcId"
        cidr = Get-PropertyValue $vpc "CidrBlock"
        state = Get-PropertyValue $vpc "State"
    }
    subnets = @(
        $subnetsRaw | ForEach-Object {
            [pscustomobject]@{
                id = Get-PropertyValue $_ "SubnetId"
                cidr = Get-PropertyValue $_ "CidrBlock"
                availability_zone = Get-PropertyValue $_ "AvailabilityZone"
                map_public_ip_on_launch = Get-PropertyValue $_ "MapPublicIpOnLaunch"
            }
        } | Sort-Object id
    )
    route_tables = @(
        $routeTablesRaw | ForEach-Object {
            [pscustomobject]@{
                id = Get-PropertyValue $_ "RouteTableId"
                associations = @(
                    @(Get-PropertyValue $_ "Associations" @()) | ForEach-Object {
                        [pscustomobject]@{
                            subnet_id = Get-PropertyValue $_ "SubnetId"
                            main = Get-PropertyValue $_ "Main"
                        }
                    }
                )
                routes = @(
                    @(Get-PropertyValue $_ "Routes" @()) | ForEach-Object {
                        [pscustomobject]@{
                            destination_ipv4 = Get-PropertyValue $_ "DestinationCidrBlock"
                            destination_ipv6 = Get-PropertyValue $_ "DestinationIpv6CidrBlock"
                            gateway_id = Get-PropertyValue $_ "GatewayId"
                            nat_gateway_id = Get-PropertyValue $_ "NatGatewayId"
                            transit_gateway_id = Get-PropertyValue $_ "TransitGatewayId"
                            vpc_peering_connection_id = Get-PropertyValue $_ "VpcPeeringConnectionId"
                            state = Get-PropertyValue $_ "State"
                        }
                    }
                )
            }
        } | Sort-Object id
    )
    internet_gateways = @($internetGatewaysRaw | ForEach-Object { Get-PropertyValue $_ "InternetGatewayId" } | Sort-Object)
    nat_gateways = @(
        $natGatewaysRaw | ForEach-Object {
            [pscustomobject]@{
                id = Get-PropertyValue $_ "NatGatewayId"
                state = Get-PropertyValue $_ "State"
                subnet_id = Get-PropertyValue $_ "SubnetId"
                allocation_ids = @(
                    @(Get-PropertyValue $_ "NatGatewayAddresses" @()) | ForEach-Object { Get-PropertyValue $_ "AllocationId" }
                )
            }
        } | Sort-Object id
    )
    vpc_endpoints = @(
        $vpcEndpointsRaw | ForEach-Object {
            [pscustomobject]@{
                id = Get-PropertyValue $_ "VpcEndpointId"
                service_name = Get-PropertyValue $_ "ServiceName"
                type = Get-PropertyValue $_ "VpcEndpointType"
                state = Get-PropertyValue $_ "State"
                route_table_ids = @((Get-PropertyValue $_ "RouteTableIds" @()) | Sort-Object)
                subnet_ids = @((Get-PropertyValue $_ "SubnetIds" @()) | Sort-Object)
            }
        } | Sort-Object id
    )
    network_acls = @(
        $networkAclsRaw | ForEach-Object {
            [pscustomobject]@{
                id = Get-PropertyValue $_ "NetworkAclId"
                is_default = Get-PropertyValue $_ "IsDefault"
                subnet_ids = @(
                    @(Get-PropertyValue $_ "Associations" @()) | ForEach-Object { Get-PropertyValue $_ "SubnetId" } | Sort-Object
                )
            }
        } | Sort-Object id
    )
    elastic_addresses = @(
        $addressesRaw | Where-Object {
            $allocationId = Get-PropertyValue $_ "AllocationId"
            $natGatewaysRaw.NatGatewayAddresses.AllocationId -contains $allocationId
        } | ForEach-Object {
            [pscustomobject]@{
                allocation_id = Get-PropertyValue $_ "AllocationId"
                association_id = Get-PropertyValue $_ "AssociationId"
                network_interface_id = Get-PropertyValue $_ "NetworkInterfaceId"
            }
        }
    )
    security_groups = $securityGroups
}

# WAF projection deliberately excludes request/log payloads.
$wafResponse = Invoke-AwsReadOnlyJson "wafv2" "get-web-acl-for-resource" @("--resource-arn", $AcceptedAlbArn)
$webAcl = Get-PropertyValue $wafResponse "WebACL"
$wafLoggingResponse = Invoke-AwsReadOnlyJson "wafv2" "get-logging-configuration" @(
    "--resource-arn", [string](Get-PropertyValue $webAcl "ARN")
)
$wafLogging = Get-PropertyValue $wafLoggingResponse "LoggingConfiguration"
$waf = [pscustomobject]@{
    id = Get-PropertyValue $webAcl "Id"
    arn = Get-PropertyValue $webAcl "ARN"
    name = Get-PropertyValue $webAcl "Name"
    scope = "REGIONAL"
    default_action = Get-PropertyValue $webAcl "DefaultAction"
    rules = @(
        @(Get-PropertyValue $webAcl "Rules" @()) | ForEach-Object {
            $statement = Get-PropertyValue $_ "Statement"
            $managed = Get-PropertyValue $statement "ManagedRuleGroupStatement"
            $rate = Get-PropertyValue $statement "RateBasedStatement"
            [pscustomobject]@{
                name = Get-PropertyValue $_ "Name"
                priority = Get-PropertyValue $_ "Priority"
                action = Get-PropertyValue $_ "Action"
                override_action = Get-PropertyValue $_ "OverrideAction"
                managed_vendor = Get-PropertyValue $managed "VendorName"
                managed_group = Get-PropertyValue $managed "Name"
                rate_limit = Get-PropertyValue $rate "Limit"
                evaluation_window_seconds = Get-PropertyValue $rate "EvaluationWindowSec"
                aggregate_key_type = Get-PropertyValue $rate "AggregateKeyType"
                visibility = Get-PropertyValue $_ "VisibilityConfig"
            }
        } | Sort-Object priority
    )
    association_resource_arn = $AcceptedAlbArn
    logging = [pscustomobject]@{
        destinations = @(Get-PropertyValue $wafLogging "LogDestinationConfigs" @())
        redacted_field_names = @(
            @(Get-PropertyValue $wafLogging "RedactedFields" @()) | ForEach-Object {
                Get-PropertyValue (Get-PropertyValue $_ "SingleHeader") "Name"
            } | Where-Object { $_ } | Sort-Object
        )
        filter = Get-PropertyValue $wafLogging "LoggingFilter"
    }
}
$wafManagedNames = @($waf.rules.managed_group | Where-Object { $_ })
foreach ($requiredRule in @(
    "AWSManagedRulesCommonRuleSet",
    "AWSManagedRulesKnownBadInputsRuleSet",
    "AWSManagedRulesAmazonIpReputationList"
)) {
    if ($wafManagedNames -notcontains $requiredRule) { Add-UniqueText $blockers "WAF_REQUIRED_RULE_MISSING_$requiredRule" }
}
$rateRule = @($waf.rules | Where-Object { $_.name -eq "SourceIpRateLimit" } | Select-Object -First 1)
if ($rateRule.Count -eq 0 -or $rateRule[0].rate_limit -ne 2000 -or $rateRule[0].evaluation_window_seconds -ne 300) {
    Add-UniqueText $blockers "WAF_RATE_CONTRACT_DIFFERS"
}

# ACM and read-only authoritative DNS.
$certificate = Get-PropertyValue (Invoke-AwsReadOnlyJson "acm" "describe-certificate" @("--certificate-arn", $AcceptedCertificateArn)) "Certificate"
$validationOptions = @(
    @(Get-PropertyValue $certificate "DomainValidationOptions" @()) | ForEach-Object {
        $record = Get-PropertyValue $_ "ResourceRecord"
        [pscustomobject]@{
            domain = Get-PropertyValue $_ "DomainName"
            validation_domain = Get-PropertyValue $_ "ValidationDomain"
            method = Get-PropertyValue $_ "ValidationMethod"
            status = Get-PropertyValue $_ "ValidationStatus"
            owner = Get-PropertyValue $record "Name"
            type = Get-PropertyValue $record "Type"
            value = Get-PropertyValue $record "Value"
        }
    }
)
$acm = [pscustomobject]@{
    arn = Get-PropertyValue $certificate "CertificateArn"
    domain = Get-PropertyValue $certificate "DomainName"
    subject_alternative_names = @((Get-PropertyValue $certificate "SubjectAlternativeNames" @()) | Sort-Object)
    status = Get-PropertyValue $certificate "Status"
    type = Get-PropertyValue $certificate "Type"
    renewal_eligibility = Get-PropertyValue $certificate "RenewalEligibility"
    renewal_summary = Get-PropertyValue $certificate "RenewalSummary"
    in_use_by = @((Get-PropertyValue $certificate "InUseBy" @()) | Sort-Object)
    not_before = Get-PropertyValue $certificate "NotBefore"
    not_after = Get-PropertyValue $certificate "NotAfter"
    validation = $validationOptions
    validation_record_classification = "DURABLE_EXTERNAL_AUTHORITY"
    validation_record_retention = "DO_NOT_REMOVE_DURING_COST_TEARDOWN_UNLESS_CERTIFICATE_STRATEGY_IS_INTENTIONALLY_ABANDONED"
}
if ($acm.status -ne "ISSUED") { Add-UniqueText $blockers "ACM_CERTIFICATE_NOT_ISSUED" }

$dns = [pscustomobject]@{
    authoritative_nameservers = @()
    authoritative_observations = @()
    expected_application_name = "app.topoai.io"
    expected_application_target = "topo-golden-edge-823808315.us-east-1.elb.amazonaws.com."
    expected_validation_owner = $AcceptedValidationOwner
    expected_validation_value = $AcceptedValidationValue
}
try {
    $nameServers = @(
        Resolve-DnsName -Name "topoai.io" -Type NS -DnsOnly -ErrorAction Stop |
            Where-Object { $_.Type -eq "NS" } |
            ForEach-Object { $_.NameHost.TrimEnd(".").ToLowerInvariant() } |
            Sort-Object -Unique
    )
    $observations = @()
    foreach ($nameServer in $nameServers) {
        $applicationTargets = @(
            Resolve-DnsName -Name "app.topoai.io" -Type CNAME -Server $nameServer -DnsOnly -ErrorAction Stop |
                Where-Object { $_.Type -eq "CNAME" } |
                ForEach-Object { $_.NameHost.TrimEnd(".").ToLowerInvariant() } |
                Sort-Object -Unique
        )
        $validationTargets = @(
            Resolve-DnsName -Name $AcceptedValidationOwner.TrimEnd(".") -Type CNAME -Server $nameServer -DnsOnly -ErrorAction Stop |
                Where-Object { $_.Type -eq "CNAME" } |
                ForEach-Object { $_.NameHost.TrimEnd(".").ToLowerInvariant() } |
                Sort-Object -Unique
        )
        $observations += [pscustomobject]@{
            nameserver = $nameServer
            application_cname_targets = $applicationTargets
            validation_cname_targets = $validationTargets
        }
    }
    $dns.authoritative_nameservers = $nameServers
    $dns.authoritative_observations = $observations
    $expectedNs = @(
        "curitiba.ns.porkbun.com", "fortaleza.ns.porkbun.com",
        "maceio.ns.porkbun.com", "salvador.ns.porkbun.com"
    ) | Sort-Object
    if ((@($nameServers) -join "|") -ne (@($expectedNs) -join "|")) { Add-UniqueText $blockers "AUTHORITATIVE_NAMESERVER_SET_DIFFERS" }
    foreach ($observation in $observations) {
        if ($observation.application_cname_targets -notcontains "topo-golden-edge-823808315.us-east-1.elb.amazonaws.com") {
            Add-UniqueText $blockers "APPLICATION_CNAME_DIFFERS_AT_$($observation.nameserver)"
        }
        if ($observation.validation_cname_targets -notcontains $AcceptedValidationValue.TrimEnd(".").ToLowerInvariant()) {
            Add-UniqueText $blockers "ACM_VALIDATION_CNAME_DIFFERS_AT_$($observation.nameserver)"
        }
    }
}
catch {
    Add-UniqueText $unknowns "AUTHORITATIVE_DNS_READ_FAILED"
}

# Repository migration head is authoritative. The general inventory never reads
# database credentials; it consumes only the sanitized receipt emitted by the
# separately bounded read-only migration-head probe.
$repositoryHeads = @(Get-RepositoryMigrationHeads)
$migrationProof = $null
if (Test-Path -LiteralPath $DatabaseMigrationProof -PathType Leaf) {
    try {
        $migrationProof = Get-Content -LiteralPath $DatabaseMigrationProof -Raw | ConvertFrom-Json -Depth 20
    }
    catch {
        $migrationProof = $null
    }
}
$liveMigrationHeads = @(
    @(Get-PropertyValue $migrationProof "live_database_migration_heads" @()) |
        ForEach-Object { [string]$_ }
)
$proofSourceHeads = @(
    @(Get-PropertyValue $migrationProof "source_migration_heads" @()) |
        ForEach-Object { [string]$_ }
)
$proofCompleted = (
    $null -ne $migrationProof -and
    (Get-PropertyValue $migrationProof "schema_version") -eq "cx0.database-migration-head-proof.v1" -and
    (Get-PropertyValue $migrationProof "aws_account_id") -eq $ExpectedAccount -and
    (Get-PropertyValue $migrationProof "aws_region") -eq $ExpectedRegion -and
    (Get-PropertyValue $migrationProof "kube_context") -eq $ExpectedCluster -and
    (Get-PropertyValue $migrationProof "namespace") -eq $ExpectedNamespace -and
    (Get-PropertyValue $migrationProof "deployment") -eq "topo-backend" -and
    (Get-PropertyValue $migrationProof "container") -eq "backend" -and
    (Get-PropertyValue $migrationProof "selector_source") -eq "Deployment.spec.selector.matchLabels" -and
    (Get-PropertyValue $migrationProof "credential_environment_variable") -eq "TOPO_DATABASE_URL" -and
    (Get-PropertyValue $migrationProof "driver") -eq "psycopg-v3" -and
    (Get-PropertyValue $migrationProof "query_type") -eq "SELECT_ONLY" -and
    (Get-PropertyValue $migrationProof "transaction_mode") -eq "READ_ONLY" -and
    (Get-PropertyValue $migrationProof "transaction_completion") -eq "ROLLBACK" -and
    (Get-PropertyValue $migrationProof "database_secret_printed" $true) -eq $false -and
    (Get-PropertyValue $migrationProof "database_secret_written_to_disk" $true) -eq $false -and
    (Get-PropertyValue $migrationProof "aws_mutation_performed" $true) -eq $false -and
    (Get-PropertyValue $migrationProof "kubernetes_mutation_performed" $true) -eq $false -and
    (Get-PropertyValue $migrationProof "database_mutation_performed" $true) -eq $false -and
    (@($proofSourceHeads) -join "|") -ceq (@($repositoryHeads) -join "|") -and
    (Get-PropertyValue $migrationProof "source_migration_head_count" -1) -eq @($repositoryHeads).Count -and
    (Get-PropertyValue $migrationProof "live_database_migration_head_count" -1) -eq @($liveMigrationHeads).Count -and
    (Get-PropertyValue $migrationProof "database_migration_head_status") -eq "MATCH"
)
$migrationStatus = Resolve-DatabaseMigrationHeadStatus `
    -SourceHeads $repositoryHeads -LiveHeads $liveMigrationHeads -ProbeCompleted $proofCompleted
$migrations = [pscustomobject]@{
    source_database_migration_heads = $repositoryHeads
    source_database_migration_head_count = $repositoryHeads.Count
    source_database_migration_head = if ($repositoryHeads.Count -eq 1) { $repositoryHeads[0] } else { $null }
    live_database_migration_heads = $liveMigrationHeads
    live_database_migration_head_count = $liveMigrationHeads.Count
    live_database_migration_head = if ($liveMigrationHeads.Count -eq 1) { $liveMigrationHeads[0] } else { $null }
    database_migration_head_status = $migrationStatus
    database_migration_head_probe_mode = "KUBERNETES_EXEC_PSYCO_PG3_READ_ONLY"
    database_migration_head_probe_completed = $proofCompleted
    credential_environment_variable = "TOPO_DATABASE_URL"
    driver = "psycopg-v3"
    query_type = "SELECT_ONLY"
    transaction_mode = "READ_ONLY"
    transaction_completion = "ROLLBACK"
    proof_receipt_path = "artifacts/cx0/database-migration-head-proof.json"
    match = $migrationStatus -eq "MATCH"
}
if ($migrationStatus -eq "SOURCE_HEADS_NOT_UNIQUE") {
    Add-UniqueText $blockers "REPOSITORY_MIGRATION_HEAD_NOT_UNIQUE"
} elseif ($migrationStatus -eq "LIVE_HEADS_NOT_UNIQUE") {
    Add-UniqueText $blockers "LIVE_DATABASE_MIGRATION_HEAD_NOT_UNIQUE"
} elseif ($migrationStatus -eq "DIFFERENT") {
    Add-UniqueText $blockers "DATABASE_MIGRATION_HEAD_DIFFERS"
} elseif ($migrationStatus -eq "UNKNOWN_REQUIRED") {
    Add-UniqueText $unknowns "LIVE_DB_MIGRATION_HEAD_NEEDS_SEPARATE_SAFE_PROBE"
}

# The general inventory remains metadata-only.  This one recovery verifier is a
# separately bounded exception: it reads exactly the keyring and active-key ID
# into child-process memory, compares the existing escrow, and emits safe hashes
# and identity metadata only.  No create flag is supplied by inventory.
$backendSecret = @($kubernetes.secrets | Where-Object { $_.name -eq "topo-backend-runtime" } | Select-Object -First 1)
$secretstore = [pscustomobject]@{
    custody_mechanism = "KUBERNETES_SECRET_RUNTIME_DELIVERY_ONLY"
    runtime_secret_name = if ($backendSecret.Count -gt 0) { $backendSecret[0].name } else { $null }
    key_names = if ($backendSecret.Count -gt 0) { $backendSecret[0].key_names } else { @() }
    active_key_identifier = $null
    active_key_identifier_status = "NOT_VERIFIED"
    live_keyring_sha256 = $null
    recovery_secret_name = "topo/golden/recovery/secret-store-keyring-v1"
    recovery_secret_arn = $null
    recovery_secret_version_id = $null
    recovery_keyring_sha256 = $null
    keyring_fingerprint_match = $false
    external_recovery_custody_found = $false
    recovery_procedure_found = $false
    location_class = "LIVE_CLUSTER_SECRET"
    recovery_procedure_reference = "docs/operations/cx-0-rds-recovery-proof-plan.md"
    separation_from_database_backup = $false
    recovery_authority_status = "NOT_SEPARATELY_PROVEN"
}
try {
    if (-not (Test-Path -LiteralPath $SecretStoreRecoveryTool -PathType Leaf)) {
        throw "SecretStore recovery verifier is missing."
    }
    $verificationJson = Invoke-NativeCapture -FilePath $PythonExecutable -ArgumentList @(
        $SecretStoreRecoveryTool,
        "--aws-profile", $AwsProfile,
        "--aws-region", $AwsRegion,
        "--recovery-procedure", $SecretStoreRecoveryProcedure,
        "--output-format", "json"
    ) -SafeDescription "SecretStore recovery verification"
    $verifiedSecretStore = $verificationJson | ConvertFrom-Json -Depth 20
    if (
        (Get-PropertyValue $verifiedSecretStore "recovery_authority_status") -ne "SEPARATELY_PROVEN" -or
        (Get-PropertyValue $verifiedSecretStore "keyring_fingerprint_match" $false) -ne $true -or
        (Get-PropertyValue $verifiedSecretStore "recovery_procedure_found" $false) -ne $true
    ) {
        throw "SecretStore recovery verification did not satisfy the contract."
    }
    $secretstore = $verifiedSecretStore
}
catch {
    Add-UniqueText $blockers "SECRETSTORE_RECOVERY_AUTHORITY_NOT_SEPARATELY_PROVEN"
}

# Terraform inspection never reads state values or bulk outputs. The historical
# migration receipt is loaded before S3 inspection so its immutable VersionId can
# be checked for retention independently of the current state head.
$terraformVersion = $null
$terraformProviders = $null
$terraformWorkspace = $null
$terraformAddresses = @()
$terraformBackendInitSucceeded = $false
$terraformRemoteStateReadable = $false
$terraformPostApplyPlanExitCode = $null
$terraformPostApplyDrift = "UNKNOWN"
$versionsSource = Get-Content -LiteralPath (Join-Path $TerraformRoot "versions.tf") -Raw
$backendMatch = [regex]::Match($versionsSource, 'backend\s+"([^"]+)"')
$backendType = if ($backendMatch.Success) { $backendMatch.Groups[1].Value } else { "local" }
$lockPath = Join-Path $TerraformRoot ".terraform.lock.hcl"
$localStatePath = Join-Path $TerraformRoot "terraform.tfstate"
$localBackupStatePath = Join-Path $TerraformRoot "terraform.tfstate.backup"
$backendBucket = "topo-tfstate-297361542190-us-east-1"
$backendKey = "golden/terraform.tfstate"
$backendRegion = "us-east-1"
$backendSourceContract = (
    $backendType -eq "s3" -and
    $versionsSource -match 'required_version\s*=\s*">= 1\.10, < 2\.0"' -and
    $versionsSource -match 'bucket\s*=\s*"topo-tfstate-297361542190-us-east-1"' -and
    $versionsSource -match 'key\s*=\s*"golden/terraform\.tfstate"' -and
    $versionsSource -match 'region\s*=\s*"us-east-1"' -and
    $versionsSource -match 'encrypt\s*=\s*true' -and
    $versionsSource -match 'use_lockfile\s*=\s*true' -and
    $versionsSource -notmatch '(?m)^\s*(dynamodb_table|profile|access_key|secret_key)\s*='
)
$backendSourceVersioned = $false
try {
    $trackedBackendSource = Invoke-NativeCapture "git" @(
        "ls-files", "--error-unmatch", "infrastructure/aws/golden/versions.tf"
    ) "Terraform backend source tracking read"
    [void](Invoke-NativeCapture "git" @(
        "diff", "--quiet", "--", "infrastructure/aws/golden/versions.tf"
    ) "Terraform backend unstaged-diff read")
    [void](Invoke-NativeCapture "git" @(
        "diff", "--cached", "--quiet", "--", "infrastructure/aws/golden/versions.tf"
    ) "Terraform backend staged-diff read")
    $backendSourceVersioned = $trackedBackendSource -eq "infrastructure/aws/golden/versions.tf"
}
catch {
    Add-UniqueText $unknowns "TERRAFORM_BACKEND_SOURCE_NOT_VERSIONED"
}

$migrationReceipt = $null
if (Test-Path -LiteralPath $TerraformMigrationReceipt -PathType Leaf) {
    try {
        $migrationReceipt = Get-Content -LiteralPath $TerraformMigrationReceipt -Raw | ConvertFrom-Json -Depth 30
    }
    catch {
        Add-UniqueText $unknowns "TERRAFORM_MIGRATION_RECEIPT_INVALID"
    }
}
$semanticEquivalence = Get-PropertyValue $migrationReceipt "migration_semantic_equivalence"
$receiptContractProven = Test-TerraformMigrationReceiptContract $migrationReceipt
$migrationStateVersionId = Get-PropertyValue $migrationReceipt "state_object_version_id"

$backendInspection = $null
if ($backendType -eq "s3" -and (Test-Path -LiteralPath $TerraformBackendBootstrap -PathType Leaf)) {
    try {
        $backendInspection = (
            Invoke-NativeCapture $PythonExecutable @(
                $TerraformBackendBootstrap,
                "--mode", "PRECHECK",
                "--profile", $AwsProfile,
                "--migration-version-id", ([string]$migrationStateVersionId)
            ) "Terraform backend metadata inspection"
        ) | ConvertFrom-Json -Depth 30
    }
    catch {
        Add-UniqueText $unknowns "TERRAFORM_BACKEND_METADATA_READ_FAILED"
    }
}

$terraformEnvironment = @{
    AWS_PROFILE = $AwsProfile
    AWS_REGION = $AwsRegion
    AWS_DEFAULT_REGION = $AwsRegion
}
try {
    $terraformVersion = (
        Invoke-NativeCapture "terraform" @("-chdir=$TerraformRoot", "version", "-json") `
            "Terraform version read" -Environment $terraformEnvironment
    ) | ConvertFrom-Json -Depth 20
    $initExitCode = Invoke-NativeStatus "terraform" @(
        "-chdir=$TerraformRoot", "init", "-input=false", "-no-color"
    ) "Terraform remote backend initialization" -Environment $terraformEnvironment
    $terraformBackendInitSucceeded = $initExitCode -eq 0
    if (-not $terraformBackendInitSucceeded) {
        throw "Terraform remote backend initialization failed."
    }
    $terraformProviders = Invoke-NativeCapture "terraform" @(
        "-chdir=$TerraformRoot", "providers"
    ) "Terraform provider read" -Environment $terraformEnvironment
    $terraformWorkspace = Invoke-NativeCapture "terraform" @(
        "-chdir=$TerraformRoot", "workspace", "show"
    ) "Terraform workspace read" -Environment $terraformEnvironment
    $terraformAddresses = @(
        (Invoke-NativeCapture "terraform" @(
            "-chdir=$TerraformRoot", "state", "list"
        ) "Terraform resource-address read" -Environment $terraformEnvironment) -split "`r?`n" |
            Where-Object { $_ } |
            Sort-Object
    )
    $terraformRemoteStateReadable = $terraformWorkspace -eq "default" -and $terraformAddresses.Count -gt 0
    $terraformPostApplyPlanExitCode = Invoke-NativeStatus "terraform" @(
        "-chdir=$TerraformRoot",
        "plan",
        "-detailed-exitcode",
        "-input=false",
        "-no-color",
        "-var=edge_https_enabled=true",
        "-var=edge_waf_enabled=true",
        "-var=edge_waf_mode=block",
        "-var=edge_public_ingress_enabled=true"
    ) "Terraform post-apply continuity plan" -Environment $terraformEnvironment
    $terraformPostApplyDrift = if ($terraformPostApplyPlanExitCode -eq 0) {
        "NONE"
    } elseif ($terraformPostApplyPlanExitCode -eq 2) {
        "DETECTED"
    } else {
        "UNKNOWN"
    }
}
catch {
    Add-UniqueText $unknowns "TERRAFORM_STATE_IDENTITY_READ_FAILED"
}
$localPrimaryReceipt = Get-PropertyValue $migrationReceipt "local_primary"
$localBackupReceipt = Get-PropertyValue $migrationReceipt "local_backup"
$localPrimaryExists = Test-Path -LiteralPath $localStatePath -PathType Leaf
$localBackupExists = Test-Path -LiteralPath $localBackupStatePath -PathType Leaf
$localPrimarySize = if ($localPrimaryExists) { (Get-Item -LiteralPath $localStatePath).Length } else { $null }
$localPrimarySha256 = if ($localPrimaryExists) { Get-FileSha256 $localStatePath } else { $null }
$localBackupSha256 = if ($localBackupExists) { Get-FileSha256 $localBackupStatePath } else { $null }
$localStateNonAuthoritative = (
    $receiptContractProven -and
    $localPrimaryExists -and
    $localPrimarySize -eq 0 -and
    $localPrimarySha256 -eq "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" -and
    (Get-PropertyValue $localPrimaryReceipt "classification") -eq "NON_AUTHORITATIVE_EMPTY_PRIMARY" -and
    (Get-PropertyValue $localPrimaryReceipt "authoritative" $true) -eq $false -and
    (Get-PropertyValue $localPrimaryReceipt "sha256") -eq $localPrimarySha256 -and
    (Get-PropertyValue $localPrimaryReceipt "deleted" $true) -eq $false -and
    $localBackupExists -and
    (Get-PropertyValue $localBackupReceipt "classification") -eq "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT" -and
    (Get-PropertyValue $localBackupReceipt "authoritative" $true) -eq $false -and
    (Get-PropertyValue $localBackupReceipt "sha256") -eq $localBackupSha256 -and
    (Get-PropertyValue $localBackupReceipt "deleted" $true) -eq $false
)
$representativeAddresses = @(
    "aws_vpc.golden",
    "aws_eks_cluster.golden",
    "aws_db_instance.postgres",
    "aws_lb.edge",
    "aws_ecr_repository.topo"
)
$representativeAddressesPresent = @(
    $representativeAddresses | Where-Object { $terraformAddresses -contains $_ }
).Count -eq $representativeAddresses.Count
$currentStateVersionId = if ($null -ne $backendInspection) {
    Get-PropertyValue $backendInspection "state_object_version_id"
} else {
    $null
}
$migrationVersionRetained = (
    $null -ne $backendInspection -and
    (Get-PropertyValue $backendInspection "migration_version_retained" $false) -eq $true
)
$currentStateIsLatest = (
    $null -ne $backendInspection -and
    (Get-PropertyValue $backendInspection "current_state_version_is_latest" $false) -eq $true
)
$currentEqualsMigrationVersion = (
    -not [string]::IsNullOrWhiteSpace([string]$currentStateVersionId) -and
    -not [string]::IsNullOrWhiteSpace([string]$migrationStateVersionId) -and
    $currentStateVersionId -eq $migrationStateVersionId
)
$remoteStateProven = (
    $receiptContractProven -and
    $backendSourceContract -and
    $backendSourceVersioned -and
    $null -ne $backendInspection -and
    (Get-PropertyValue $backendInspection "exists" $false) -eq $true -and
    (Get-PropertyValue $backendInspection "configuration_matches" $false) -eq $true -and
    (Get-PropertyValue $backendInspection "versioning_enabled" $false) -eq $true -and
    (Get-PropertyValue $backendInspection "state_object_exists" $false) -eq $true -and
    -not [string]::IsNullOrWhiteSpace([string]$currentStateVersionId) -and
    $migrationVersionRetained -and
    $currentStateIsLatest -and
    (Get-PropertyValue $backendInspection "lock_object_exists" $true) -eq $false -and
    $terraformBackendInitSucceeded -and
    $terraformRemoteStateReadable -and
    $terraformWorkspace -eq "default" -and
    $terraformAddresses.Count -eq 80 -and
    $representativeAddressesPresent -and
    $terraformPostApplyPlanExitCode -eq 0 -and
    $terraformPostApplyDrift -eq "NONE" -and
    $localStateNonAuthoritative
)
$terraform = [pscustomobject]@{
    version = $terraformVersion
    providers_text_sha256 = if ($null -ne $terraformProviders) { Get-Sha256Text $terraformProviders } else { $null }
    provider_lock_sha256 = if (Test-Path -LiteralPath $lockPath) { Get-FileSha256 $lockPath } else { $null }
    backend_type = $backendType
    backend_source_file = "infrastructure/aws/golden/versions.tf"
    backend_location_class = if ($remoteStateProven) { "DURABLE_EXTERNAL_AUTHORITY" } elseif ($backendType -eq "local") { "LOCAL_WORKING_COPY" } else { "UNPROVEN_REMOTE_AUTHORITY" }
    backend_durable = $remoteStateProven
    remote_state_authority_class = if ($remoteStateProven) { "DURABLE_EXTERNAL_AUTHORITY" } else { "UNPROVEN_REMOTE_AUTHORITY" }
    backend_bucket = $backendBucket
    backend_key = $backendKey
    backend_region = $backendRegion
    backend_source_contract_matches = $backendSourceContract
    backend_source_versioned = $backendSourceVersioned
    use_lockfile = $versionsSource -match 'use_lockfile\s*=\s*true'
    dynamodb_locking_configured = $versionsSource -match '(?m)^\s*dynamodb_table\s*='
    bucket_exists = if ($null -ne $backendInspection) { Get-PropertyValue $backendInspection "exists" $false } else { $false }
    bucket_configuration_matches = if ($null -ne $backendInspection) { Get-PropertyValue $backendInspection "configuration_matches" $false } else { $false }
    state_object_exists = if ($null -ne $backendInspection) { Get-PropertyValue $backendInspection "state_object_exists" $false } else { $false }
    state_object_version_id = $currentStateVersionId
    migration_state_version_id = $migrationStateVersionId
    current_state_version_id = $currentStateVersionId
    current_equals_migration_version = $currentEqualsMigrationVersion
    migration_version_retained = $migrationVersionRetained
    current_state_is_latest = $currentStateIsLatest
    current_remote_state_proven = $remoteStateProven
    lock_object_exists = if ($null -ne $backendInspection) { Get-PropertyValue $backendInspection "lock_object_exists" $false } else { $false }
    backend_init_succeeded = $terraformBackendInitSucceeded
    remote_state_readable = $terraformRemoteStateReadable
    terraform_post_apply_plan_exit_code = $terraformPostApplyPlanExitCode
    terraform_post_apply_drift = $terraformPostApplyDrift
    local_state_file_present = $localPrimaryExists
    local_state_authority_class = if ($localStateNonAuthoritative) { "NON_AUTHORITATIVE_EMPTY_PRIMARY" } else { "UNRECONCILED_LOCAL_AUTHORITY" }
    local_state_sha256 = $localPrimarySha256
    local_state_size_bytes = $localPrimarySize
    local_backup_present = $localBackupExists
    local_backup_authority_class = if ($localStateNonAuthoritative) { "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT" } else { "UNRECONCILED_LOCAL_AUTHORITY" }
    local_backup_sha256 = $localBackupSha256
    source_state_lineage = Get-PropertyValue $migrationReceipt "source_state_lineage"
    source_state_serial = Get-PropertyValue $migrationReceipt "source_state_serial"
    destination_state_lineage = Get-PropertyValue $migrationReceipt "destination_state_lineage"
    destination_state_serial = Get-PropertyValue $migrationReceipt "destination_state_serial"
    migration_semantic_equivalence = $semanticEquivalence
    migration_receipt_present = $null -ne $migrationReceipt
    workspace = $terraformWorkspace
    resource_addresses = $terraformAddresses
    resource_address_count = $terraformAddresses.Count
    representative_addresses_present = $representativeAddressesPresent
    state_values_read = $false
    source = $source.terraform
}
if ($terraformAddresses.Count -eq 0) { Add-UniqueText $unknowns "TERRAFORM_RESOURCE_ADDRESS_LIST_EMPTY_OR_UNAVAILABLE" }
if ($terraformPostApplyPlanExitCode -eq 2) { Add-UniqueText $blockers "TERRAFORM_POST_APPLY_DRIFT_DETECTED" }
if ($null -ne $terraformPostApplyPlanExitCode -and $terraformPostApplyPlanExitCode -notin @(0, 2)) {
    Add-UniqueText $unknowns "TERRAFORM_POST_APPLY_PLAN_FAILED"
}
if (-not $remoteStateProven) { Add-UniqueText $blockers "TERRAFORM_REMOTE_STATE_NOT_PROVEN" }

# Topo-owned IAM roles. Condition values are omitted from trust-policy projection.
$rolesResponse = Invoke-AwsReadOnlyJson "iam" "list-roles"
$roleNames = @(
    @(Get-PropertyValue $rolesResponse "Roles" @()) |
        ForEach-Object { Get-PropertyValue $_ "RoleName" } |
        Where-Object { $_ -like "topo-golden*" } |
        Sort-Object
)
$iamRoles = @()
foreach ($roleName in $roleNames) {
    $role = Get-PropertyValue (Invoke-AwsReadOnlyJson "iam" "get-role" @("--role-name", [string]$roleName)) "Role"
    $attached = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "iam" "list-attached-role-policies" @("--role-name", [string]$roleName)) "AttachedPolicies" @())
    $inline = @(Get-PropertyValue (Invoke-AwsReadOnlyJson "iam" "list-role-policies" @("--role-name", [string]$roleName)) "PolicyNames" @())
    $iamRoles += [pscustomobject]@{
        name = $roleName
        arn = Get-PropertyValue $role "Arn"
        trust_policy = Convert-IamTrustPolicy (Get-PropertyValue $role "AssumeRolePolicyDocument")
        attached_managed_policy_arns = @($attached | ForEach-Object { Get-PropertyValue $_ "PolicyArn" } | Sort-Object)
        inline_policy_names = @($inline | Sort-Object)
        permissions_boundary_arn = Get-PropertyValue (Get-PropertyValue $role "PermissionsBoundary") "PermissionsBoundaryArn"
        tags = @(
            @(Get-PropertyValue $role "Tags" @()) | ForEach-Object {
                [pscustomobject]@{ key = Get-PropertyValue $_ "Key"; value = Get-PropertyValue $_ "Value" }
            } | Sort-Object key
        )
    }
}
$iam = [pscustomobject]@{ roles = @($iamRoles | Sort-Object name) }

# Metadata only: no log events or S3 object payloads are read.
$logGroups = @()
foreach ($prefix in @("/aws/eks/topo-golden", "aws-waf-logs-topo-golden-edge")) {
    $logGroups += @(
        Get-PropertyValue (Invoke-AwsReadOnlyJson "logs" "describe-log-groups" @("--log-group-name-prefix", $prefix)) "logGroups" @()
    )
}
$trails = @(
    @(Get-PropertyValue (Invoke-AwsReadOnlyJson "cloudtrail" "describe-trails" @("--include-shadow-trails")) "trailList" @()) |
        Where-Object { (Get-PropertyValue $_ "Name" "") -like "*topo*" } |
        ForEach-Object {
            [pscustomobject]@{
                name = Get-PropertyValue $_ "Name"
                arn = Get-PropertyValue $_ "TrailARN"
                s3_bucket_name = Get-PropertyValue $_ "S3BucketName"
                cloudwatch_log_group_arn = Get-PropertyValue $_ "CloudWatchLogsLogGroupArn"
                multi_region = Get-PropertyValue $_ "IsMultiRegionTrail"
            }
        }
)
$buckets = @(
    @(Get-PropertyValue (Invoke-AwsReadOnlyJson "s3api" "list-buckets") "Buckets" @()) |
        Where-Object { (Get-PropertyValue $_ "Name" "") -like "*topo*" } |
        ForEach-Object { [pscustomobject]@{ name = Get-PropertyValue $_ "Name"; created_at = Get-PropertyValue $_ "CreationDate" } }
)
$logging = [pscustomobject]@{
    log_groups = @(
        $logGroups | ForEach-Object {
            [pscustomobject]@{
                name = Get-PropertyValue $_ "logGroupName"
                arn = Get-PropertyValue $_ "arn"
                retention_days = Get-PropertyValue $_ "retentionInDays"
                stored_bytes = Get-PropertyValue $_ "storedBytes"
            }
        } | Sort-Object name -Unique
    )
    waf_destination = @($waf.logging.destinations)
    eks_control_plane_categories = @($eks.cluster.control_plane_log_types)
    cloudtrail_trails = $trails
    retained_s3_buckets = $buckets
    raw_log_payloads_read = $false
}

$costResources = [System.Collections.Generic.List[object]]::new()
$costResources.Add([pscustomobject]@{ resource_type = "EKS_CONTROL_PLANE"; identifier = $ClusterName; billing_class = "LIKELY_CONTINUOUS_COST" })
foreach ($nodeGroup in $nodeGroups) { $costResources.Add([pscustomobject]@{ resource_type = "EKS_NODE_GROUP"; identifier = $nodeGroup.name; billing_class = "LIKELY_CONTINUOUS_COST" }) }
foreach ($natGateway in $network.nat_gateways) { $costResources.Add([pscustomobject]@{ resource_type = "NAT_GATEWAY"; identifier = $natGateway.id; billing_class = "LIKELY_CONTINUOUS_COST" }) }
$costResources.Add([pscustomobject]@{ resource_type = "APPLICATION_LOAD_BALANCER"; identifier = $edge.load_balancer.arn; billing_class = "LIKELY_CONTINUOUS_COST" })
$costResources.Add([pscustomobject]@{ resource_type = "RDS_INSTANCE"; identifier = $rds.arn; billing_class = "LIKELY_CONTINUOUS_COST" })
$costResources.Add([pscustomobject]@{ resource_type = "WAF_WEB_ACL"; identifier = $waf.arn; billing_class = "LIKELY_CONTINUOUS_COST" })
foreach ($endpoint in $network.vpc_endpoints) {
    $class = if ($endpoint.type -eq "Gateway") { "NO_MEANINGFUL_RUNTIME_COST" } else { "LIKELY_CONTINUOUS_COST" }
    $costResources.Add([pscustomobject]@{ resource_type = "VPC_ENDPOINT"; identifier = $endpoint.id; billing_class = $class })
}
foreach ($address in $network.elastic_addresses) { $costResources.Add([pscustomobject]@{ resource_type = "ELASTIC_IP"; identifier = $address.allocation_id; billing_class = "UNKNOWN" }) }
foreach ($logGroup in $logging.log_groups) { $costResources.Add([pscustomobject]@{ resource_type = "CLOUDWATCH_LOG_GROUP"; identifier = $logGroup.name; billing_class = "LOW_OR_STORAGE_COST" }) }
foreach ($image in $ecrImages) { $costResources.Add([pscustomobject]@{ resource_type = "ECR_IMAGE"; identifier = "$EcrRepository@$($image.digest)"; billing_class = "LOW_OR_STORAGE_COST" }) }
foreach ($snapshot in $rds.snapshots) { $costResources.Add([pscustomobject]@{ resource_type = "RDS_SNAPSHOT"; identifier = $snapshot.arn; billing_class = "LOW_OR_STORAGE_COST" }) }
foreach ($bucket in $buckets) { $costResources.Add([pscustomobject]@{ resource_type = "S3_BUCKET"; identifier = $bucket.name; billing_class = "LOW_OR_STORAGE_COST" }) }

$toolVersions = [pscustomobject]@{
    powershell = $PSVersionTable.PSVersion.ToString()
    git = Invoke-NativeCapture "git" @("--version") "Git version read"
    aws_cli = Invoke-NativeCapture -FilePath "aws" -ArgumentList @("--version") -SafeDescription "AWS CLI version read"
    kubectl_client = (
        (Invoke-KubectlReadOnlyText "version client" @("version", "--client=true", "--output=json")) |
            ConvertFrom-Json -Depth 20
    ).clientVersion.gitVersion
    terraform = if ($null -ne $terraformVersion) { Get-PropertyValue $terraformVersion "terraform_version" } else { $null }
}

$fingerprints = [pscustomobject]@{
    kubernetes_workload_contract = Get-ObjectFingerprint ([pscustomobject]@{ deployments = $deployments; services = $services })
    security_group_rule_set = Get-ObjectFingerprint $securityGroups
    alb_route_contract = Get-ObjectFingerprint ([pscustomobject]@{ listeners = $edge.listeners; target_groups = $edge.target_groups })
    waf_rule_contract = Get-ObjectFingerprint $waf
    terraform_source_set = $source.terraform.sha256
    kubernetes_source_set = $source.kubernetes.sha256
    migration_source_set = $source.migrations.sha256
}

$receipt = [pscustomobject]@{
    schema_version = "cx0a.reproducibility.v1"
    captured_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    tool_versions = $toolVersions
    authority = [pscustomobject]@{
        accepted_predecessor_head = $AcceptedHead
        accepted_predecessor_tree = $AcceptedTree
        current_branch = $currentBranch
        current_head = $currentHead
        current_tree = $currentTree
    }
    environment = [pscustomobject]@{
        aws_account_id = [string](Get-PropertyValue $identity "Account")
        caller_arn = Get-PropertyValue $identity "Arn"
        aws_profile = $AwsProfile
        region = $AwsRegion
        eks_cluster = $ClusterName
        namespace = $Namespace
    }
    source = $source
    eks = $eks
    kubernetes = $kubernetes
    images = $images
    network = $network
    edge = $edge
    waf = $waf
    acm = $acm
    dns = $dns
    rds = $rds
    migrations = $migrations
    secretstore_recovery = $secretstore
    terraform = $terraform
    iam = $iam
    logging = $logging
    cost_relevant_resources = @($costResources)
    reproducibility = [pscustomobject]@{
        blockers = @($blockers | Sort-Object)
        unknowns = @($unknowns | Sort-Object)
    }
    fingerprints = $fingerprints
    safety = [pscustomobject]@{
        aws_mutation_performed = $false
        kubernetes_mutation_performed = $false
        dns_mutation_performed = $false
        database_mutation_performed = $false
        deletion_performed = $false
        secret_values_emitted = $false
    }
}

Assert-ReceiptShape $receipt
if (-not (Test-Path -LiteralPath $SchemaPath)) { throw "Inventory JSON schema is missing." }

$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
}
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts/cx0"))
if (-not $outputRoot.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Inventory output must remain under ignored artifacts/cx0."
}
[void](New-Item -ItemType Directory -Path $outputRoot -Force)

$jsonPath = Join-Path $outputRoot "cx0a-reproducibility-inventory.json"
$summaryPath = Join-Path $outputRoot "cx0a-reproducibility-summary.txt"
$json = $receipt | ConvertTo-Json -Depth 100
[System.IO.File]::WriteAllText($jsonPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

$summary = @(
    "CX_0A1_SOURCE_CONTRACT=PASS"
    "CX_0A1_STATIC_SAFETY=PASS"
    "CX_0A1_INVENTORY_SCHEMA=PASS"
    "CX_0A1_REPRODUCIBILITY_INVENTORY=PASS"
    "AWS_ACCOUNT=$ExpectedAccount"
    "AWS_REGION=$ExpectedRegion"
    "KUBERNETES_CONTEXT=$kubeContext"
    "INVENTORY_JSON=$jsonPath"
    "REPRODUCIBILITY_BLOCKERS=$($receipt.reproducibility.blockers.Count)"
    "REPRODUCIBILITY_UNKNOWNS=$($receipt.reproducibility.unknowns.Count)"
    "AWS_MUTATION_PERFORMED=NO"
    "KUBERNETES_MUTATION_PERFORMED=NO"
    "DNS_MUTATION_PERFORMED=NO"
    "DATABASE_MUTATION_PERFORMED=NO"
    "DELETION_PERFORMED=NO"
    "SECRET_VALUES_EMITTED=NO"
    "TEARDOWN_AUTHORIZED=NO"
    "COST_0_A_REPRODUCIBILITY_INVENTORY_COMPLETE=PASS"
)
[System.IO.File]::WriteAllLines($summaryPath, $summary, [System.Text.UTF8Encoding]::new($false))
$summary | ForEach-Object { Write-Output $_ }
