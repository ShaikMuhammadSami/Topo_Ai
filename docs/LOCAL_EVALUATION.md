# Evaluate Topo AI locally

This guide is for an independent SRE or DevOps engineer evaluating Topo AI on
a workstation. Start with the synthetic Docker demo. The optional Kubernetes
path uses a dedicated disposable namespace on Docker Desktop.

Topo AI is read-only incident decision support. It collects evidence and helps
an operator investigate and verify recovery; it does not change or remediate
infrastructure.

## Requirements

- Git
- Docker Desktop or Docker Engine with Docker Compose 2.20+
- Python 3.11+
- For Path B only: Docker Desktop Kubernetes and `kubectl`

## Path A: Docker demo (recommended first)

The local configuration binds the Web UI and API to localhost, uses SQLite,
and disables authentication for development. Do not expose it to a shared or
public network.

### 1. Clone, configure, start, and seed

Bash:

```bash
git clone https://github.com/ShaikMuhammadSami/Topo_Ai.git
cd Topo_Ai
cp .env.example .env
docker compose up --build --detach --wait
docker compose exec backend python -m app.demo_seed
curl -fsS http://localhost:8000/ready
python3 scripts/smoke/local_demo.py
```

Windows PowerShell:

```powershell
git clone https://github.com/ShaikMuhammadSami/Topo_Ai.git
Set-Location Topo_Ai
Copy-Item .env.example .env
docker compose up --build --detach --wait
docker compose exec backend python -m app.demo_seed
Invoke-RestMethod http://localhost:8000/ready
python scripts/smoke/local_demo.py
```

Open [http://localhost:3000/app](http://localhost:3000/app). Select **Topo AI
Local Demo** in the tenant selector if it is not selected automatically, then
open **Incidents**, **Signals & Changes**, and **Topology**.

The seed records three ordered topology states:

1. healthy `payment-service:v1` baseline;
2. Deployment image changed to `payment-service:v2`;
3. a later Pod `CrashLoopBackOff` failure.

The scenario is synthetic historical evidence. It intentionally retains a
failure state and has no live agent collecting current recovery evidence, so
**Check & Resolve is not expected to pass** for this incident.

### 2. Install and use the real CLI

Install the repository's terminal CLI:

```bash
python3 -m pip install -e ./cli
```

```powershell
python -m pip install -e .\cli
```

The `/app/cli` page is an illustrative in-browser simulator with fixed sample
values. The `topo` executable below is the actual CLI and reads the running
backend.

Bash:

```bash
TENANT=$(curl -fsS http://localhost:8000/api/v1/tenants | python3 -c "import json,sys; print(next(t['tenant_id'] for t in json.load(sys.stdin) if t['display_name']=='Topo AI Local Demo'))")
topo --tenant "$TENANT" incidents list
INCIDENT=$(topo --tenant "$TENANT" --output json incidents list | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['incident_id'])")
topo --tenant "$TENANT" incidents get "$INCIDENT"
topo --tenant "$TENANT" causal-rca latest "$INCIDENT"
topo --tenant "$TENANT" incidents blast-radius "$INCIDENT"
topo --tenant "$TENANT" snapshots list
```

Windows PowerShell:

```powershell
$TENANT = ((Invoke-RestMethod http://localhost:8000/api/v1/tenants) | Where-Object { $_.display_name -eq "Topo AI Local Demo" }).tenant_id
topo --tenant $TENANT incidents list
$INCIDENT = (topo --tenant $TENANT --output json incidents list | Out-String | ConvertFrom-Json)[0].incident_id
topo --tenant $TENANT incidents get $INCIDENT
topo --tenant $TENANT causal-rca latest $INCIDENT
topo --tenant $TENANT incidents blast-radius $INCIDENT
topo --tenant $TENANT snapshots list
```

The RCA output is an evidence-backed hypothesis under the current model, not a
guaranteed or calibrated root-cause probability.

To stop the demo without deleting its database volume:

```bash
docker compose down
```

Do not add `--volumes` if you want to preserve the evaluation data.

## Path B: Real Docker Desktop Kubernetes (optional)

This path creates and mutates only a new disposable namespace. It uses manual
`topo-agent collect` calls so each evidence checkpoint is explicit. Keep the
Path A backend running and install both local packages:

```bash
python3 -m pip install -e ./cli -e ./agent
```

```powershell
python -m pip install -e .\cli -e .\agent
```

If this is a new terminal, select the demo tenant again:

```bash
TENANT=$(curl -fsS http://localhost:8000/api/v1/tenants | python3 -c "import json,sys; print(next(t['tenant_id'] for t in json.load(sys.stdin) if t['display_name']=='Topo AI Local Demo'))")
```

```powershell
$TENANT = ((Invoke-RestMethod http://localhost:8000/api/v1/tenants) | Where-Object { $_.display_name -eq "Topo AI Local Demo" }).tenant_id
```

### 1. Guard the context and create a dedicated namespace

Bash:

```bash
CTX=docker-desktop
NS=topo-local-eval
test "$(kubectl config current-context)" = "$CTX"
if kubectl --context "$CTX" get namespace "$NS" >/dev/null 2>&1; then
  echo "Namespace $NS already exists; choose a different disposable name."
  exit 1
fi
kubectl --context "$CTX" create namespace "$NS"
```

Windows PowerShell:

```powershell
$Context = "docker-desktop"
$Namespace = "topo-local-eval"
if ((kubectl config current-context) -ne $Context) { throw "docker-desktop is not the active context" }
kubectl --context $Context get namespace $Namespace 2>$null
if ($LASTEXITCODE -eq 0) { throw "Namespace already exists; choose a different disposable name" }
kubectl --context $Context create namespace $Namespace
```

Every remaining `kubectl` command includes both `--context` and `--namespace`.

### 2. Create a healthy workload and enroll the existing agent

Bash:

```bash
kubectl --context "$CTX" --namespace "$NS" create deployment payment-service --image=nginx:1.27-alpine --replicas=1
kubectl --context "$CTX" --namespace "$NS" rollout status deployment/payment-service --timeout=120s
topo --tenant "$TENANT" agents create-token --label docker-desktop-eval --output-token-stdout \
  | topo-agent enroll --server http://localhost:8000 --name docker-desktop-eval \
      --cluster docker-desktop --environment local --namespace "$NS" \
      --plugin kubernetes --kube-context "$CTX" --collection-interval 30 --token-stdin
```

Windows PowerShell:

```powershell
kubectl --context $Context --namespace $Namespace create deployment payment-service --image=nginx:1.27-alpine --replicas=1
kubectl --context $Context --namespace $Namespace rollout status deployment/payment-service --timeout=120s
topo --tenant $TENANT agents create-token --label docker-desktop-eval --output-token-stdout |
  topo-agent enroll --server http://localhost:8000 --name docker-desktop-eval `
    --cluster docker-desktop --environment local --namespace $Namespace `
    --plugin kubernetes --kube-context $Context --collection-interval 30 --token-stdin
```

Enrollment stores the agent credential in the operating system's secure
credential store. It does not print the agent credential. Confirm connectivity,
scope, and Kubernetes read permissions:

```bash
topo-agent doctor
topo-agent plugins doctor --plugin kubernetes
topo-agent heartbeat
topo --tenant "$TENANT" agents list
topo-agent collect --plugin kubernetes
```

In PowerShell, use the same commands with `$TENANT` instead of `"$TENANT"`.
The final `collect` is the healthy baseline.

### 3. Record an invalid-image change, then the failure

Bash:

```bash
kubectl --context "$CTX" --namespace "$NS" rollout pause deployment/payment-service
kubectl --context "$CTX" --namespace "$NS" set image deployment/payment-service payment-service=nginx:topo-ai-invalid-evaluation
topo-agent collect --plugin kubernetes
kubectl --context "$CTX" --namespace "$NS" rollout resume deployment/payment-service
kubectl --context "$CTX" --namespace "$NS" get pods
topo-agent collect --plugin kubernetes
```

Windows PowerShell:

```powershell
kubectl --context $Context --namespace $Namespace rollout pause deployment/payment-service
kubectl --context $Context --namespace $Namespace set image deployment/payment-service payment-service=nginx:topo-ai-invalid-evaluation
topo-agent collect --plugin kubernetes
kubectl --context $Context --namespace $Namespace rollout resume deployment/payment-service
kubectl --context $Context --namespace $Namespace get pods
topo-agent collect --plugin kubernetes
```

Pausing the rollout first lets the agent record the Deployment template
mutation while the existing healthy Pod remains running, before a new Pod is
created. After the first collection, resume the rollout and wait for the new
Pod to show `ErrImagePull` or `ImagePullBackOff`; repeat only the read-only
`get pods` command if necessary, then perform the second collection.
If you stop the test mid-sequence, resume the paused rollout before restoring
the valid image. These explicit checkpoints make the causal demonstration
more reproducible, but Topo must still rely on observed evidence rather than
assuming the newest event caused the failure.

### 4. Investigate, restore, verify, and resolve

Bash:

```bash
topo --tenant "$TENANT" incidents list
INCIDENT=$(topo --tenant "$TENANT" --output json incidents list --all | python3 -c "import json,sys; ns=sys.argv[1]; print(next(i['incident_id'] for i in json.load(sys.stdin) if i.get('cluster_name')=='docker-desktop' and i.get('namespace')==ns))" "$NS")
topo --tenant "$TENANT" incidents get "$INCIDENT"
topo --tenant "$TENANT" causal-rca latest "$INCIDENT"
topo --tenant "$TENANT" incidents blast-radius "$INCIDENT"
topo --tenant "$TENANT" snapshots list

kubectl --context "$CTX" --namespace "$NS" set image deployment/payment-service payment-service=nginx:1.27-alpine
kubectl --context "$CTX" --namespace "$NS" rollout status deployment/payment-service --timeout=120s
topo-agent collect --plugin kubernetes
```

Windows PowerShell:

```powershell
topo --tenant $TENANT incidents list
$INCIDENT = ((topo --tenant $TENANT --output json incidents list --all | Out-String | ConvertFrom-Json) | Where-Object { $_.cluster_name -eq "docker-desktop" -and $_.namespace -eq $Namespace } | Select-Object -First 1).incident_id
topo --tenant $TENANT incidents get $INCIDENT
topo --tenant $TENANT causal-rca latest $INCIDENT
topo --tenant $TENANT incidents blast-radius $INCIDENT
topo --tenant $TENANT snapshots list

kubectl --context $Context --namespace $Namespace set image deployment/payment-service payment-service=nginx:1.27-alpine
kubectl --context $Context --namespace $Namespace rollout status deployment/payment-service --timeout=120s
topo-agent collect --plugin kubernetes
```

Open the incident at `http://localhost:3000/app`, choose **Check & Resolve**, and
review every scoped read-only check. Topo uses the fresh persisted agent
snapshot; it does not open a remote shell or request an on-demand Kubernetes
command. If every required check passes, explicitly confirm **Mark Resolved**.
If evidence is stale, missing, mismatched, failing, or unknown, leave the
incident unresolved and collect again.

Confirm the final status with the real CLI:

```bash
topo --tenant "$TENANT" incidents get "$INCIDENT"
```

```powershell
topo --tenant $TENANT incidents get $INCIDENT
```

After evaluation, you may delete only the disposable namespace you created:

```bash
kubectl --context "$CTX" delete namespace "$NS"
```

```powershell
kubectl --context $Context delete namespace $Namespace
```

## Current limitations

- The demo's Kubernetes and change evidence is synthetic; it does not claim
  provider-authentic Git or CI/CD provenance.
- Check & Resolve uses a sufficiently fresh, tenant/cluster/namespace/workload-
  scoped persisted snapshot. It cannot command the agent to collect live and
  does not run `kubectl` remotely.
- Agent enrollment requires an operating-system credential store. Headless
  Linux environments without one will fail closed rather than save a plaintext
  token.
- Fast Kubernetes transitions can combine the Deployment mutation and failure
  symptom in one collection. Topo reports the evidence it observed and should
  not manufacture a causal conclusion.
