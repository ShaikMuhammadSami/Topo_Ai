# TopoAI adversarial evaluation harness

This package is outside the product packages and treats TopoAI as a system
under test. It does not import product services or repositories.

## Prerequisites

- Python 3.12 (Python 3.11 or newer is supported by the project)
- Git with complete repository history for frozen-history guards
- `kubectl` only for live evaluations
- a POSIX shell for the container-entrypoint behavior tests (`sh` on
  Linux/macOS or Git for Windows Bash)

Create separate repository-local virtual environments. The live harness never
falls back to an unrelated global Python or `topo-agent` executable.

### Windows PowerShell

```powershell
py -3.12 -m venv backend\.venv
& .\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock "pytest>=8,<10"

py -3.12 -m venv agent\.venv
& .\agent\.venv\Scripts\python.exe -m pip install -e .\agent
```

### Linux/macOS shell

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock 'pytest>=8,<10'

python3.12 -m venv agent/.venv
agent/.venv/bin/python -m pip install -e ./agent
```

By default the harness resolves `backend/.venv/Scripts/python.exe` and
`agent/.venv/Scripts/topo-agent.exe` on Windows, or the corresponding
`.venv/bin/` executables on Linux/macOS. Automation may instead set
`TOPO_EVALUATION_BACKEND_PYTHON` or `TOPO_EVALUATION_AGENT_EXECUTABLE` to an
absolute path. Missing or non-executable paths fail with a prerequisite error;
the harness does not search the global `PATH` for replacements.

## Offline tests

These tests require no cloud credentials, Kubernetes cluster, or provider
access:

```powershell
& .\backend\.venv\Scripts\python.exe -m pytest evaluation\tests
```

```bash
backend/.venv/bin/python -m pytest evaluation/tests
```

Tests backed only by tracked fixtures run normally. Tests that require ignored
historical evidence are individually skipped when that evidence is absent,
with the required path and custody requirement in the skip reason. A skip is a
missing prerequisite, not a passing evaluation.

## Historical provider and database evidence

Some forensic reproductions require externally preserved artifacts that are
intentionally not committed, including:

- `evaluation/results/provider-receipts/32688747741-1/topo-lineage-provider-receipt.json`
- `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`
- `backend/data/topo.db` for the opt-in migration custody assertion

Do not synthesize these files. When an authentic artifact is restored at its
documented path, the original SHA-256, schema, provenance, custody, and causal
evidence assertions run unchanged and fail on a mismatch. PostgreSQL migration
operations additionally require `TOPO_TEST_POSTGRES_URL` pointing to a
disposable PostgreSQL 16 test service; the suite creates separate temporary
databases and never uses the configured database itself.

## Live Kubernetes evaluations (opt-in)

Live runs create and delete a guarded `topo-eval-*` namespace. Select an
explicit disposable context and verify it before running:

```powershell
kubectl config use-context docker-desktop
kubectl config current-context
& .\backend\.venv\Scripts\python.exe -m evaluation run sentinel-a --context docker-desktop
```

```bash
kubectl config use-context docker-desktop
kubectl config current-context
backend/.venv/bin/python -m evaluation run sentinel-a --context docker-desktop
```

Run all four Sentinel scenarios sequentially with:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation run-all --context docker-desktop
```

```bash
backend/.venv/bin/python -m evaluation run-all --context docker-desktop
```

Each live run starts an isolated backend database and agent state, enrolls an
agent scoped to its generated namespace, obtains provider truth through
`kubectl`, observes Topo through existing HTTP APIs, writes ignored results
under `evaluation/results/`, and requests namespace cleanup in a `finally`
block. The context must be explicitly selected and disposable. Do not run the
harness against a production cluster.

Product failures return exit code 1. Missing prerequisites, harness errors, and
inconclusive runs return exit code 2; they are never reported as passing
evaluations.

