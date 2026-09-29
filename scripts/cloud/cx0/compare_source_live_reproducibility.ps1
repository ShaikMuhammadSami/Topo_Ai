[CmdletBinding()]
param(
    [string]$InventoryPath = "artifacts/cx0/cx0a-reproducibility-inventory.json",
    [string]$OutputDirectory = "artifacts/cx0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
$ExpectedOrigin = '["https://app.topoai.io"]'
$ImageAuthorityPath = Join-Path $PSScriptRoot "cloud_v1_1b_image_authority.json"
$ImageAuthority = Get-Content -LiteralPath $ImageAuthorityPath -Raw | ConvertFrom-Json -Depth 20
if (
    $ImageAuthority.schema_version -ne "cx0.image-authority.v1" -or
    $ImageAuthority.aws_account_id -ne "297361542190" -or
    $ImageAuthority.region -ne "us-east-1" -or
    $ImageAuthority.repository -ne "topo-golden/topo" -or
    $ImageAuthority.accepted_cloud_head -ne "e676559b3daf586b4dc53041d1638a3d2191910a" -or
    $ImageAuthority.images.backend.publication_source_commit -ne "a6aee9725bea774336704faa9a77980b73bd05cb" -or
    $ImageAuthority.images.backend.publication_source_tree -ne "8154b50bbfb8c46533acf368ba70e3329f497832" -or
    $ImageAuthority.images.backend.repair_commit -ne "537692e7fe9e0b86e30de87ba43c8d4ca7d1c4c4"
) {
    throw "Immutable image authority contract is invalid."
}
$ExpectedRepositoryUri = "$($ImageAuthority.aws_account_id).dkr.ecr.$($ImageAuthority.region).amazonaws.com/$($ImageAuthority.repository)"
$ExpectedBackendImage = "$ExpectedRepositoryUri@$($ImageAuthority.images.backend.digest)"
$ExpectedFrontendImage = "$ExpectedRepositoryUri@$($ImageAuthority.images.frontend.digest)"
$ExpectedObserverImage = "$ExpectedRepositoryUri@$($ImageAuthority.images.observer.digest)"
$ObserverManifestPath = Join-Path $RepoRoot "infrastructure/kubernetes/golden/observer.yaml"
$RecreationAuthorityPath = Join-Path $RepoRoot "docs/operations/cx-0-recreation-authority.md"
$TeardownPlanPath = Join-Path $RepoRoot "docs/operations/cx-0-teardown-plan.md"
$AllowedClassifications = @(
    "MATCH", "CODIFIED_DIFFERENTLY", "LIVE_ONLY_REQUIRED",
    "INTENTIONALLY_DISPOSABLE", "UNKNOWN"
)

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

function Add-Comparison {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.Generic.List[object]]$List,
        [Parameter(Mandatory = $true)][string]$Domain,
        [Parameter(Mandatory = $true)][string]$Classification,
        [Parameter(Mandatory = $true)][bool]$Required,
        [Parameter(Mandatory = $true)][string]$Authority,
        [Parameter(Mandatory = $true)][string]$Rationale
    )
    if ($AllowedClassifications -notcontains $Classification) {
        throw "Unsupported reconciliation classification: $Classification"
    }
    $List.Add([pscustomobject]@{
        domain = $Domain
        classification = $Classification
        required_for_recreation = $Required
        authority = $Authority
        rationale = $Rationale
    })
}

function Resolve-RepoPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
}

$resolvedInventory = Resolve-RepoPath $InventoryPath
if (-not (Test-Path -LiteralPath $resolvedInventory -PathType Leaf)) {
    throw "Inventory receipt not found: $resolvedInventory"
}
$inventory = Get-Content -LiteralPath $resolvedInventory -Raw | ConvertFrom-Json -Depth 100
if ($inventory.schema_version -ne "cx0a.reproducibility.v1") {
    throw "Unsupported inventory schema version."
}
if ($inventory.safety.aws_mutation_performed -or
    $inventory.safety.kubernetes_mutation_performed -or
    $inventory.safety.dns_mutation_performed -or
    $inventory.safety.database_mutation_performed -or
    $inventory.safety.deletion_performed -or
    $inventory.safety.secret_values_emitted) {
    throw "Inventory safety markers do not permit reconciliation."
}

$comparisons = [System.Collections.Generic.List[object]]::new()

$nodeGroups = @($inventory.eks.node_groups)
$nodeGroupShapeMatches = (
    $inventory.eks.cluster.kubernetes_version -eq "1.35" -and
    $nodeGroups.Count -eq 2 -and
    @($nodeGroups | Where-Object {
        $_.instance_types -notcontains "t3.small" -or
        $_.scaling.minSize -ne 1 -or $_.scaling.desiredSize -ne 1 -or $_.scaling.maxSize -ne 1
    }).Count -eq 0
)
Add-Comparison $comparisons "eks_version_and_node_group_shape" `
    $(if ($nodeGroupShapeMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/aws/golden/variables.tf and eks.tf" `
    $(if ($nodeGroupShapeMatches) {
        "Live EKS version and both one-node t3.small node groups match versioned Terraform authority."
    } else {
        "Live EKS/node-group shape differs from the versioned reconstruction contract."
    })

$deploymentMap = @{}
foreach ($deployment in @($inventory.kubernetes.deployments)) { $deploymentMap[$deployment.metadata.name] = $deployment }
$serviceMap = @{}
foreach ($service in @($inventory.kubernetes.services)) { $serviceMap[$service.metadata.name] = $service }
$workloadShapeMatches = (
    $deploymentMap.ContainsKey("topo-backend") -and $deploymentMap["topo-backend"].replicas -eq 2 -and
    $deploymentMap.ContainsKey("topo-frontend") -and $deploymentMap["topo-frontend"].replicas -eq 2 -and
    $deploymentMap.ContainsKey("topo-observer") -and $deploymentMap["topo-observer"].replicas -eq 1
)
Add-Comparison $comparisons "kubernetes_workload_specs" `
    $(if ($workloadShapeMatches) { "CODIFIED_DIFFERENTLY" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/kubernetes/golden plus immutable publication/deployment receipts" `
    $(if ($workloadShapeMatches) {
        "Workload identities, replica shape, probes, environment references, volumes and accepted immutable image references are versioned."
    } else {
        "Live workload shape cannot be reconciled with the accepted Kubernetes source contract."
    })

$nodePorts = @{}
foreach ($service in @($inventory.kubernetes.services)) {
    foreach ($port in @($service.ports)) {
        if ($null -ne $port.node_port) { $nodePorts[$service.metadata.name] = [int]$port.node_port }
    }
}
$serviceMatches = (
    $nodePorts.ContainsKey("topo-backend-edge") -and $nodePorts["topo-backend-edge"] -eq 32080 -and
    $nodePorts.ContainsKey("topo-frontend") -and $nodePorts["topo-frontend"] -eq 32081
)
Add-Comparison $comparisons "services_and_nodeports" `
    $(if ($serviceMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/kubernetes/golden/edge-services.yaml" `
    $(if ($serviceMatches) { "Live edge NodePorts match versioned source." } else { "Required live NodePorts differ from source." })

$origin = $null
foreach ($configMap in @($inventory.kubernetes.config_maps)) {
    if ($configMap.metadata.name -eq "topo-runtime-config") {
        $property = $configMap.values.PSObject.Properties["browser-allowed-origins-json"]
        if ($null -ne $property) { $origin = Get-PropertyValue $property.Value "allowlisted_plaintext" }
    }
}
Add-Comparison $comparisons "configmap_runtime_origin" `
    $(if ($origin -eq $ExpectedOrigin) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/kubernetes/golden/foundation.yaml" `
    $(if ($origin -eq $ExpectedOrigin) { "The live browser origin exactly matches versioned authority." } else { "The live browser origin differs from accepted source." })

$backendImageMatch = ($inventory.images.accepted_backend -eq $ExpectedBackendImage) -and (@($inventory.images.running.image) -contains $ExpectedBackendImage)
$frontendImageMatch = ($inventory.images.accepted_frontend -eq $ExpectedFrontendImage) -and (@($inventory.images.running.image) -contains $ExpectedFrontendImage)
Add-Comparison $comparisons "backend_immutable_image" $(if ($backendImageMatch) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "accepted CLOUD-V1 receipt and ECR digest" $(if ($backendImageMatch) { "Accepted backend digest is running and recorded." } else { "Accepted backend digest is not reproducibly present." })
Add-Comparison $comparisons "frontend_immutable_image" $(if ($frontendImageMatch) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "accepted CLOUD-V1 receipt and ECR digest" $(if ($frontendImageMatch) { "Accepted frontend digest is running and recorded." } else { "Accepted frontend digest is not reproducibly present." })

$observer = Get-PropertyValue $inventory.images "observer" ([pscustomobject]@{})
$ecrContract = Get-PropertyValue $inventory.images "ecr_repository_contract" ([pscustomobject]@{})
$observerDigest = [string]$ImageAuthority.images.observer.digest
$observerManifest = Get-Content -LiteralPath $ObserverManifestPath -Raw
$recreationAuthority = Get-Content -LiteralPath $RecreationAuthorityPath -Raw
$teardownPlan = Get-Content -LiteralPath $TeardownPlanPath -Raw
$observerSourcePinned = $observerManifest.Contains("image: $ExpectedObserverImage")
$observerAuthorityMatches = (
    $inventory.images.accepted_observer -eq $ExpectedObserverImage -and
    $inventory.images.authority.schema_version -eq "cx0.image-authority.v1" -and
    $inventory.images.authority.repository -eq $ImageAuthority.repository -and
    $inventory.images.authority.observer_digest -eq $observerDigest -and
    $inventory.images.authority.authority_class -eq "DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY"
)
$observerLiveMatches = (
    $observer.configured_image -eq $ExpectedObserverImage -and
    $observer.configured_digest -eq $observerDigest -and
    $observer.running_digest -eq $observerDigest -and
    $observer.ready -eq $true
)
$observerEcrMatches = (
    $observer.ecr_digest_exists -eq $true -and
    @($inventory.images.ecr_images | Where-Object { $_.digest -eq $observerDigest }).Count -eq 1 -and
    $ecrContract.registry_id -eq $ImageAuthority.aws_account_id -and
    $ecrContract.repository_name -eq $ImageAuthority.repository
)
$observerRetentionSafe = (
    $observer.retention_safe -eq $true -and
    $ecrContract.accepted_observer_digest_retention_safe -eq $true
)
$observerRetentionDocumented = (
    $recreationAuthority.Contains($ExpectedObserverImage) -and
    $teardownPlan.Contains($ExpectedObserverImage) -and
    $recreationAuthority.Contains("DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY") -and
    $recreationAuthority.Contains("COST_0_RETAIN") -and
    $recreationAuthority.Contains("DO_NOT_DELETE_DURING_CX_0B") -and
    $teardownPlan.Contains("DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY") -and
    $teardownPlan.Contains("COST_0_RETAIN") -and
    $teardownPlan.Contains("DO_NOT_DELETE_DURING_CX_0B")
)
$observerProven = (
    $observerAuthorityMatches -and
    $observerLiveMatches -and
    $observerEcrMatches -and
    $observerSourcePinned -and
    $observerRetentionSafe -and
    $observerRetentionDocumented
)
Add-Comparison $comparisons "observer_immutable_image" `
    $(if ($observerProven) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "scripts/cloud/cx0/cloud_v1_1b_image_authority.json, immutable Kubernetes source, exact ECR digest, retention contract and CX-0 teardown docs" `
    $(if ($observerProven) {
        "The ready live observer, pinned source, machine-readable authority and exact ECR digest agree; repository retention cannot automatically expire it and CX-0B must retain it."
    } else {
        "Observer authority remains open until the ready live image ID, pinned source, exact ECR digest, retention safety and explicit CX-0B retention contract all agree."
    })

$edgeMatches = (
    $inventory.edge.load_balancer.arn -eq "arn:aws:elasticloadbalancing:us-east-1:297361542190:loadbalancer/app/topo-golden-edge/bed4a7ad18a7221c" -and
    @($inventory.edge.listeners | Where-Object { $_.port -eq 80 -and $_.protocol -eq "HTTP" }).Count -eq 1 -and
    @($inventory.edge.listeners | Where-Object { $_.port -eq 443 -and $_.protocol -eq "HTTPS" }).Count -eq 1
)
Add-Comparison $comparisons "alb_listeners_rules_target_groups" $(if ($edgeMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/aws/golden/edge.tf and tls.tf" $(if ($edgeMatches) { "Accepted ALB and HTTP/HTTPS listener identities are present; detailed route fingerprint is retained." } else { "Accepted ALB listener contract differs." })

$securityGroupIds = @($inventory.network.security_groups.id)
$securityGroupMatches = $securityGroupIds -contains "sg-039e2a36df4d18e31" -and $securityGroupIds -contains "sg-071e1b40296d57288"
Add-Comparison $comparisons "security_groups" $(if ($securityGroupMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/aws/golden edge/network/RDS source" $(if ($securityGroupMatches) { "Required edge and worker groups are identified and the normalized rule-set fingerprint is retained." } else { "Required security-group identity is missing or different." })

$wafGroups = @($inventory.waf.rules.managed_group | Where-Object { $_ })
$wafMatches = (
    $inventory.waf.id -eq "133c8085-fb74-43f6-a31c-a93fe3bf3627" -and
    $wafGroups -contains "AWSManagedRulesCommonRuleSet" -and
    $wafGroups -contains "AWSManagedRulesKnownBadInputsRuleSet" -and
    $wafGroups -contains "AWSManagedRulesAmazonIpReputationList"
)
Add-Comparison $comparisons "waf" $(if ($wafMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/aws/golden/waf.tf" $(if ($wafMatches) { "Live WebACL identity and required managed groups match source." } else { "Live WAF contract differs from source." })

$acmMatches = $inventory.acm.arn -eq "arn:aws:acm:us-east-1:297361542190:certificate/85675e1c-205d-4fb1-98f2-f6acf8a5c12d" -and $inventory.acm.status -eq "ISSUED"
Add-Comparison $comparisons "acm_certificate" $(if ($acmMatches) { "MATCH" } else { "UNKNOWN" }) $true `
    "ACM plus durable Porkbun validation record" $(if ($acmMatches) { "The exact certificate is issued and its durable validation record is captured." } else { "Issued certificate authority could not be proven." })

$dnsUnknown = @($inventory.reproducibility.unknowns) -contains "AUTHORITATIVE_DNS_READ_FAILED"
$dnsBlocker = @($inventory.reproducibility.blockers | Where-Object { $_ -like "*CNAME*" -or $_ -eq "AUTHORITATIVE_NAMESERVER_SET_DIFFERS" }).Count -gt 0
$dnsClass = if ($dnsUnknown) { "UNKNOWN" } elseif ($dnsBlocker) { "LIVE_ONLY_REQUIRED" } else { "MATCH" }
Add-Comparison $comparisons "porkbun_dns" $dnsClass $true "Porkbun authoritative DNS and reviewed external-authority contract" `
    $(if ($dnsClass -eq "MATCH") { "Authoritative application and ACM-validation CNAME answers match accepted external authority." } else { "Authoritative DNS evidence is missing or differs." })

$rdsMatches = $inventory.rds.identifier -eq "topo-golden-postgres" -and $inventory.rds.engine -eq "postgres" -and -not $inventory.rds.publicly_accessible
Add-Comparison $comparisons "rds_runtime_requirements" $(if ($rdsMatches) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "infrastructure/aws/golden/rds.tf plus future proven recovery artifact" $(if ($rdsMatches) { "The private PostgreSQL runtime shape matches source; recovery proof remains an independent gate." } else { "Live RDS runtime differs from source requirements." })

$migrationStatus = [string](Get-PropertyValue $inventory.migrations "database_migration_head_status" "UNKNOWN_REQUIRED")
$migrationClass = if (
    $migrationStatus -eq "MATCH" -and
    $inventory.migrations.match -eq $true -and
    $inventory.migrations.database_migration_head_probe_completed -eq $true -and
    $inventory.migrations.source_database_migration_head_count -eq 1 -and
    $inventory.migrations.live_database_migration_head_count -eq 1 -and
    $inventory.migrations.source_database_migration_head -ceq $inventory.migrations.live_database_migration_head -and
    $inventory.migrations.driver -eq "psycopg-v3" -and
    $inventory.migrations.query_type -eq "SELECT_ONLY" -and
    $inventory.migrations.transaction_mode -eq "READ_ONLY" -and
    $inventory.migrations.transaction_completion -eq "ROLLBACK"
) {
    "MATCH"
} elseif ($migrationStatus -eq "UNKNOWN_REQUIRED") {
    "UNKNOWN"
} else {
    "LIVE_ONLY_REQUIRED"
}
Add-Comparison $comparisons "database_migration_head" $migrationClass $true "backend/alembic plus a separately safe live DB revision probe" `
    $(if ($migrationClass -eq "MATCH") {
        "The single live database migration head matches the single source head under a completed psycopg v3 read-only transaction that ended in rollback."
    } elseif ($migrationClass -eq "UNKNOWN") {
        "The repository head is recorded, but the live revision has not been obtained through an accepted secret-safe read-only probe."
    } else {
        "Database migration-head evidence differs or is non-unique; CX-0 authority remains blocked."
    })

$iamMatches = @($inventory.iam.roles).Count -ge 2 -and @($inventory.iam.roles.name) -contains "topo-golden-eks-cluster" -and @($inventory.iam.roles.name) -contains "topo-golden-eks-nodes"
Add-Comparison $comparisons "iam_roles_and_policies" $(if ($iamMatches) { "MATCH" } else { "UNKNOWN" }) $true `
    "infrastructure/aws/golden IAM source" $(if ($iamMatches) { "Required cluster/node roles and sanitized attachments/trust metadata are captured." } else { "Required IAM authority is incomplete." })

$terraformEquivalence = $inventory.terraform.migration_semantic_equivalence
$terraformSourceKinds = Get-PropertyValue $terraformEquivalence "check_results_kinds_source"
$terraformDestinationKinds = Get-PropertyValue $terraformEquivalence "check_results_kinds_destination"
$terraformSourceStatuses = Get-PropertyValue $terraformEquivalence "check_results_statuses_source"
$terraformDestinationStatuses = Get-PropertyValue $terraformEquivalence "check_results_statuses_destination"
$terraformRemoteProven = (
    $inventory.terraform.backend_type -eq "s3" -and
    $inventory.terraform.backend_bucket -eq "topo-tfstate-297361542190-us-east-1" -and
    $inventory.terraform.backend_key -eq "golden/terraform.tfstate" -and
    $inventory.terraform.backend_region -eq "us-east-1" -and
    $inventory.terraform.backend_source_contract_matches -eq $true -and
    $inventory.terraform.backend_source_versioned -eq $true -and
    $inventory.terraform.backend_durable -eq $true -and
    $inventory.terraform.remote_state_authority_class -eq "DURABLE_EXTERNAL_AUTHORITY" -and
    $inventory.terraform.use_lockfile -eq $true -and
    $inventory.terraform.dynamodb_locking_configured -eq $false -and
    $inventory.terraform.bucket_exists -eq $true -and
    $inventory.terraform.bucket_configuration_matches -eq $true -and
    $inventory.terraform.state_object_exists -eq $true -and
    -not [string]::IsNullOrWhiteSpace([string]$inventory.terraform.state_object_version_id) -and
    $inventory.terraform.lock_object_exists -eq $false -and
    $inventory.terraform.workspace -eq "default" -and
    $inventory.terraform.resource_address_count -eq 80 -and
    $inventory.terraform.representative_addresses_present -eq $true -and
    $inventory.terraform.source_state_lineage -eq "13c78cf7-912f-cacc-74eb-15c7ee33112f" -and
    $inventory.terraform.source_state_serial -eq 97 -and
    $inventory.terraform.destination_state_lineage -eq "dc5223d7-8ffe-cacf-e04f-f1f42a8bc584" -and
    $inventory.terraform.destination_state_serial -eq 1 -and
    (Get-PropertyValue $terraformEquivalence "resources_match" $false) -eq $true -and
    (Get-PropertyValue $terraformEquivalence "outputs_match" $false) -eq $true -and
    (Get-PropertyValue $terraformEquivalence "non_check_state_match" $false) -eq $true -and
    (Get-PropertyValue $terraformEquivalence "check_results_unordered_match" $false) -eq $true -and
    (Get-PropertyValue $terraformEquivalence "check_results_count_source" -1) -eq 18 -and
    (Get-PropertyValue $terraformEquivalence "check_results_count_destination" -1) -eq 18 -and
    (Get-PropertyValue $terraformSourceKinds "resource" -1) -eq 1 -and
    (Get-PropertyValue $terraformSourceKinds "var" -1) -eq 17 -and
    (Get-PropertyValue $terraformDestinationKinds "resource" -1) -eq 1 -and
    (Get-PropertyValue $terraformDestinationKinds "var" -1) -eq 17 -and
    (Get-PropertyValue $terraformSourceStatuses "pass" -1) -eq 18 -and
    (Get-PropertyValue $terraformDestinationStatuses "pass" -1) -eq 18 -and
    $inventory.terraform.local_state_authority_class -eq "NON_AUTHORITATIVE_EMPTY_PRIMARY" -and
    $inventory.terraform.local_state_sha256 -eq "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" -and
    $inventory.terraform.local_state_size_bytes -eq 0 -and
    $inventory.terraform.local_backup_present -eq $true -and
    $inventory.terraform.local_backup_authority_class -eq "NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT"
)
$terraformClass = if ($terraformRemoteProven) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }
Add-Comparison $comparisons "terraform_backend_and_state_identity" $terraformClass $true `
    "Terraform source plus durable state-backend identity" $(if ($terraformClass -eq "MATCH") {
        "The versioned native-locking S3 backend is durable authority; all 80 remote addresses and representatives are present, accepted semantic equivalence is recorded across the lineage/serial transition, the empty local primary is non-authoritative, and the retained backup is only a recovery artifact."
    } else {
        "Durable S3 authority is not accepted until its exact configuration and versioned state object, all 80 remote addresses and representatives, complete semantic-equivalence receipt, versioned use_lockfile source, and explicit local-primary/backup demotion are proven."
    })

$secretStoreProven = (
    $inventory.secretstore_recovery.recovery_authority_status -eq "SEPARATELY_PROVEN" -and
    $inventory.secretstore_recovery.location_class -eq "DURABLE_EXTERNAL_AUTHORITY" -and
    $inventory.secretstore_recovery.external_recovery_custody_found -eq $true -and
    $inventory.secretstore_recovery.keyring_fingerprint_match -eq $true -and
    $inventory.secretstore_recovery.active_key_identifier_status -eq "RECORDED" -and
    -not [string]::IsNullOrWhiteSpace([string]$inventory.secretstore_recovery.active_key_identifier) -and
    -not [string]::IsNullOrWhiteSpace([string]$inventory.secretstore_recovery.recovery_secret_arn) -and
    -not [string]::IsNullOrWhiteSpace([string]$inventory.secretstore_recovery.recovery_secret_version_id) -and
    $inventory.secretstore_recovery.recovery_procedure_found -eq $true -and
    $inventory.secretstore_recovery.separation_from_database_backup -eq $true
)
Add-Comparison $comparisons "secretstore_recovery_authority" $(if ($secretStoreProven) { "MATCH" } else { "LIVE_ONLY_REQUIRED" }) $true `
    "AWS Secrets Manager recovery object plus docs/operations/cx-0-rds-recovery-proof-plan.md" $(if ($secretStoreProven) { "The exact live keyring fingerprint matches durable external recovery custody, its active key ID is recorded, and the recovery procedure exists." } else { "Kubernetes runtime delivery alone is not recovery authority; existence, exact fingerprint equality, active key identity, database-backup separation, and the documented procedure must all be proven." })

$loggingKnown = @($inventory.logging.log_groups).Count -gt 0 -and @($inventory.logging.waf_destination).Count -gt 0
Add-Comparison $comparisons "logging_and_evidence_dependencies" $(if ($loggingKnown) { "MATCH" } else { "UNKNOWN" }) $true `
    "Terraform/AWS logging metadata and evidence-retention contracts" $(if ($loggingKnown) { "Required retention metadata is captured without log payloads." } else { "Required evidence logging metadata is incomplete." })

$mappedBlockers = @(
    "SECRETSTORE_RECOVERY_AUTHORITY_NOT_SEPARATELY_PROVEN",
    "TERRAFORM_REMOTE_STATE_NOT_PROVEN",
    "REPOSITORY_MIGRATION_HEAD_NOT_UNIQUE",
    "LIVE_DATABASE_MIGRATION_HEAD_NOT_UNIQUE",
    "DATABASE_MIGRATION_HEAD_DIFFERS"
)
$mappedUnknowns = @("LIVE_DB_MIGRATION_HEAD_NEEDS_SEPARATE_SAFE_PROBE")
foreach ($blocker in @($inventory.reproducibility.blockers)) {
    if ($mappedBlockers -contains $blocker) { continue }
    if (@($comparisons | Where-Object { $_.classification -eq "LIVE_ONLY_REQUIRED" -and $_.rationale -like "*$blocker*" }).Count -eq 0) {
        Add-Comparison $comparisons "inventory_blocker:$blocker" "LIVE_ONLY_REQUIRED" $true "live inventory safety/reproducibility gate" "The inventory emitted blocker $blocker; it must be resolved through reviewed authority before teardown."
    }
}
foreach ($unknown in @($inventory.reproducibility.unknowns)) {
    if ($mappedUnknowns -contains $unknown) { continue }
    if (@($comparisons | Where-Object { $_.classification -eq "UNKNOWN" -and $_.rationale -like "*$unknown*" }).Count -eq 0) {
        Add-Comparison $comparisons "inventory_unknown:$unknown" "UNKNOWN" $true "live inventory completeness gate" "The inventory emitted unknown $unknown; no teardown decision may infer it away."
    }
}

$ordered = @($comparisons | Sort-Object domain)
$liveOnlyRequired = @($ordered | Where-Object { $_.required_for_recreation -and $_.classification -eq "LIVE_ONLY_REQUIRED" })
$unknownRequired = @($ordered | Where-Object { $_.required_for_recreation -and $_.classification -eq "UNKNOWN" })
$report = [pscustomobject]@{
    schema_version = "cx0a.reconciliation.v1"
    reconciled_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    inventory_path = [System.IO.Path]::GetRelativePath($RepoRoot, $resolvedInventory).Replace("\", "/")
    accepted_predecessor_head = $inventory.authority.accepted_predecessor_head
    comparisons = $ordered
    summary = [pscustomobject]@{
        match_count = @($ordered | Where-Object classification -eq "MATCH").Count
        codified_differently_count = @($ordered | Where-Object classification -eq "CODIFIED_DIFFERENTLY").Count
        intentionally_disposable_count = @($ordered | Where-Object classification -eq "INTENTIONALLY_DISPOSABLE").Count
        live_only_required_count = $liveOnlyRequired.Count
        unknown_required_count = $unknownRequired.Count
        release_freeze_ready = $liveOnlyRequired.Count -eq 0 -and $unknownRequired.Count -eq 0
        teardown_authorized = $false
    }
    safety = [pscustomobject]@{
        live_query_performed = $false
        aws_mutation_performed = $false
        kubernetes_mutation_performed = $false
        dns_mutation_performed = $false
        database_mutation_performed = $false
        deletion_performed = $false
        secret_values_emitted = $false
    }
}

$outputRoot = Resolve-RepoPath $OutputDirectory
$allowedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts/cx0"))
if (-not $outputRoot.StartsWith($allowedOutputRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Reconciliation output must remain under ignored artifacts/cx0."
}
[void](New-Item -ItemType Directory -Path $outputRoot -Force)
$jsonPath = Join-Path $outputRoot "cx0a-source-live-reconciliation.json"
$summaryPath = Join-Path $outputRoot "cx0a-source-live-reconciliation-summary.txt"
[System.IO.File]::WriteAllText($jsonPath, ($report | ConvertTo-Json -Depth 100) + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
$summaryLines = @(
    "CX_0A2_SOURCE_LIVE_RECONCILIATION=PASS"
    "MATCH_COUNT=$($report.summary.match_count)"
    "CODIFIED_DIFFERENTLY_COUNT=$($report.summary.codified_differently_count)"
    "LIVE_ONLY_REQUIRED_COUNT=$($report.summary.live_only_required_count)"
    "UNKNOWN_REQUIRED_COUNT=$($report.summary.unknown_required_count)"
    "RELEASE_FREEZE_READY=$(if ($report.summary.release_freeze_ready) { 'YES' } else { 'NO' })"
    "TEARDOWN_AUTHORIZED=NO"
    "AWS_MUTATION_PERFORMED=NO"
    "KUBERNETES_MUTATION_PERFORMED=NO"
    "DNS_MUTATION_PERFORMED=NO"
    "DATABASE_MUTATION_PERFORMED=NO"
    "DELETION_PERFORMED=NO"
    "SECRET_VALUES_EMITTED=NO"
)
[System.IO.File]::WriteAllLines($summaryPath, $summaryLines, [System.Text.UTF8Encoding]::new($false))
$summaryLines | ForEach-Object { Write-Output $_ }
