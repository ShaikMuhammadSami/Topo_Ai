# TopoAI adversarial evaluation harness

This package is intentionally outside `backend/app`, `agent/src`, `frontend`,
and `cli/src`. It treats Topo as a system under test and never imports product
services or repositories.

Run one real Kubernetes Sentinel from the repository root:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation run sentinel-a --context docker-desktop
```

Run all four sequentially:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation run-all --context docker-desktop
```

Each run starts an isolated backend database and isolated agent state, enrolls
an agent scoped to a guarded disposable namespace, obtains provider truth with
`kubectl`, observes Topo through existing HTTP APIs, writes a result under the
ignored `evaluation/results/` directory, and requests namespace cleanup in a
`finally` block. Product failures return exit code 1; harness errors or
inconclusive runs return exit code 2. A product failure is a useful evaluation
result and must not be “fixed” in this package.

Prerequisites are a reachable Kubernetes current context, `kubectl`, working
backend and agent virtual environments, and permission to create/delete only
the generated `topo-eval-[a-d]-<run>` namespace.

