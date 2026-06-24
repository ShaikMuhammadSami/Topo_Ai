// Shared mock data for the topo ai demo incident INC-4419

export type SignalKind =
  | "ALERT"
  | "DEPLOY"
  | "DIFF"
  | "POD"
  | "METRIC"
  | "SCALE"
  | "CONFIG"

export const incident = {
  id: "INC-4419",
  sev: "SEV-2",
  status: "INVESTIGATING",
  title: "checkout-api: elevated 5xx + latency",
  summary:
    "Error-rate on checkout-api crossed 3.2% (baseline 0.1%) at 14:32 UTC. p99 latency rose from 220ms to 1.4s. Auto-investigation started.",
  svc: "checkout-api",
  ns: "payments-prod",
  owner: "payments-platform",
  detected: "2026-02-14T14:32:08Z",
  cluster: "prod-eu-west-1",
  snapshot: "14:32:08Z",
  sha: "9a4f12c",
}

export const timeline = [
  {
    kind: "alert" as const,
    time: "14:32:08",
    title: "Alert fired",
    body: "PagerDuty: checkout-api error-rate 3.2% > threshold 1.0%",
  },
  {
    kind: "topo" as const,
    time: "14:32:12",
    title: "topo detected the alert, started correlation",
    body: "Pulling temporal graph snapshot t=14:32:08 ± 60m",
  },
  {
    kind: "signal" as const,
    time: "14:32:18",
    title: "Signal: deploy event",
    body: "checkout-api deployment rollout @ 14:28:41 (4m before alert)",
  },
  {
    kind: "signal" as const,
    time: "14:32:21",
    title: "Signal: pods OOMKilled",
    body: "9 pods OOMKilled (exit 137) in payments-prod",
  },
  {
    kind: "topo" as const,
    time: "14:32:25",
    title: "Diff isolated on checkout-api",
    body: "git sha 9a4f12c removed @lru_cache on price_quote()",
  },
]

export const hypotheses = [
  {
    rank: "H1",
    confidence: 0.91,
    title: "Cache removal regression in price_quote()",
    detail:
      "PR #2284 removed @lru_cache(maxsize=4096) on price_quote(), issuing a synchronous DB query on every checkout.",
    evidence: [
      { weight: 0.42, label: "diff: payments/checkout.py removed @lru_cache" },
      { weight: 0.31, label: "temporal: deploy @ 14:28:41 — spike 14:32:08 (Δ+3m27s)" },
      { weight: 0.18, label: "signal: pricing.quotes db queries ↑ 18× (1.2/s → 58/s)" },
    ],
    counter: [{ weight: 0.05, label: "counter: 2/11 pods show healthy memory" }],
  },
  {
    rank: "H2",
    confidence: 0.74,
    title: "Memory limit exhaustion (OOMKilled)",
    detail:
      "9 of 11 checkout-api pods are within 35Mi of the 512Mi memory limit and OOMKilled under increased load.",
    evidence: [
      { weight: 0.4, label: "signal: 9 pods OOMKilled (exit 137)" },
      { weight: 0.22, label: "metric: rss approaching limit on 9/11 pods" },
    ],
    counter: [{ weight: 0.08, label: "counter: restart loop stabilizes after 90s" }],
  },
  {
    rank: "H3",
    confidence: 0.18,
    title: "Upstream pricing-svc latency",
    detail:
      "pricing-svc p99 latency rose, but timing precedes the deploy and is likely a downstream effect.",
    evidence: [{ weight: 0.18, label: "metric: pricing-svc p99 90ms → 410ms" }],
    counter: [{ weight: 0.3, label: "counter: pricing-svc latency follows checkout deploy" }],
  },
]

export const recovery = [
  { label: "error-rate", from: "3.20%", to: "0.14%", baseline: "0.10%" },
  { label: "p99 latency", from: "1.4s", to: "240ms", baseline: "220ms" },
  { label: "pod restarts/5m", from: "11", to: "0", baseline: "0" },
]

export type NodeState = "healthy" | "elevated" | "failing"
export type GraphNode = {
  id: string
  label: string
  kind: string
  x: number
  y: number
  state: NodeState
}
export type GraphEdge = { from: string; to: string; state: "rpc" | "failing" | "low" }

export const graphNodes: GraphNode[] = [
  { id: "auth", label: "auth-api", kind: "svc", x: 30, y: 18, state: "healthy" },
  { id: "pricing", label: "pricing-svc", kind: "svc", x: 62, y: 26, state: "elevated" },
  { id: "ingress", label: "ingress-gw", kind: "edge", x: 12, y: 52, state: "healthy" },
  { id: "checkout", label: "checkout-api", kind: "svc", x: 45, y: 50, state: "failing" },
  { id: "redis", label: "redis", kind: "store", x: 80, y: 50, state: "healthy" },
  { id: "ledger", label: "ledger", kind: "svc", x: 62, y: 64, state: "healthy" },
  { id: "cart", label: "cart-svc", kind: "svc", x: 30, y: 74, state: "healthy" },
  { id: "notify", label: "notify-worker", kind: "svc", x: 47, y: 86, state: "healthy" },
  { id: "pg", label: "pg-orders", kind: "store", x: 80, y: 78, state: "healthy" },
]

export const graphEdges: GraphEdge[] = [
  { from: "ingress", to: "checkout", state: "failing" },
  { from: "auth", to: "checkout", state: "rpc" },
  { from: "checkout", to: "pricing", state: "rpc" },
  { from: "checkout", to: "redis", state: "rpc" },
  { from: "checkout", to: "ledger", state: "rpc" },
  { from: "ingress", to: "cart", state: "rpc" },
  { from: "cart", to: "ledger", state: "rpc" },
  { from: "ledger", to: "pg", state: "rpc" },
  { from: "checkout", to: "notify", state: "low" },
  { from: "pricing", to: "redis", state: "rpc" },
]

export const signals: { time: string; kind: SignalKind; svc: string; text: string }[] = [
  { time: "14:32:25", kind: "DIFF", svc: "checkout-api", text: "git: sha 9a4f12c · removed @lru_cache on price_quote()" },
  { time: "14:32:21", kind: "POD", svc: "checkout-api", text: "9 pods OOMKilled (exit 137) in payments-prod" },
  { time: "14:32:18", kind: "DEPLOY", svc: "checkout-api", text: "ArgoCD rollout completed · revision r-118" },
  { time: "14:32:08", kind: "ALERT", svc: "checkout-api", text: "PagerDuty: error-rate 3.2% > 1.0%" },
  { time: "14:31:40", kind: "METRIC", svc: "pricing-svc", text: "p99 latency rose 90ms → 410ms (rps ↑ 18×)" },
  { time: "14:28:41", kind: "DEPLOY", svc: "checkout-api", text: "Deploy: PR #2284 merged + auto-deploy (sha 9a4f12c)" },
  { time: "14:14:02", kind: "DIFF", svc: "auth-api", text: "git: sha 3122f0a · bump token TTL 30m → 24h" },
  { time: "13:58:11", kind: "SCALE", svc: "cart-svc", text: "HPA scaled 6 → 9 replicas (cpu 78%)" },
  { time: "13:42:00", kind: "CONFIG", svc: "ingress-gw", text: "configmap update: rate-limit 1000 → 1500 rps" },
]

export const commits = [
  { repo: "checkout", time: "14:25:02", suspected: true, msg: "perf: drop in-memory cache on price_quote (use pricing-svc)", sha: "9a4f12c", pr: "#2284", by: "m.solis" },
  { repo: "auth", time: "14:14:02", msg: "feat(auth): extend token TTL to 24h for mobile clients", sha: "3122f0a", pr: "#2281", by: "k.lin" },
  { repo: "cart", time: "13:01:18", msg: "chore: bump deps + bugfix in /api/cart/sync", sha: "d33ee01", pr: "#1907", by: "r.patel" },
  { repo: "pricing", time: "11:42:55", msg: "feat: add caching layer (LRU 8k) for /quote endpoint", sha: "c10a44b", pr: "#812", by: "y.tanaka" },
]

export const identities = [
  { repo: "github.com/acme/checkout", image: "checkout-api:9a4f12c", helm: "checkout@2.18.3", deployment: "checkout-api", pod: "checkout-api-7df-*", cidr: "10.42.118/24", source: "LABEL-MATCH", conf: 0.99 },
  { repo: "github.com/acme/pricing", image: "pricing-svc:c10a44b", helm: "pricing@1.4.0", deployment: "pricing-svc", pod: "pricing-svc-5b6-*", cidr: "10.42.119/24", source: "LABEL-MATCH", conf: 0.99 },
  { repo: "github.com/acme/cart", image: "cart-svc:d33ee01", helm: "cart@0.9.12", deployment: "cart-svc", pod: "cart-svc-6cd-*", cidr: "10.42.120/24", source: "LABEL-MATCH", conf: 0.97 },
  { repo: "github.com/acme/auth", image: "auth-api:3122f0a", helm: "auth@3.0.1", deployment: "auth-api", pod: "auth-api-4ab-*", cidr: "10.42.121/24", source: "LABEL-MATCH", conf: 0.92 },
  { repo: "github.com/acme/payments-ledger", image: "ledger:e88e201", helm: "ledger@0.4.0", deployment: "ledger", pod: "ledger-2ee-*", cidr: "10.42.122/24", source: "NAMING-HEURISTIC", conf: 0.74 },
  { repo: "github.com/acme/notifications", image: "notify:b91c40e", helm: "notify@1.0.0", deployment: "notify-worker", pod: "notify-worker-1aa-*", cidr: "10.42.123/24", source: "NAMING-HEURISTIC", conf: 0.71 },
  { repo: "—", image: "redis:7.2.4", helm: "redis@17.11.3", deployment: "redis-master", pod: "redis-master-0", cidr: "10.42.124/24", source: "MANUAL-OVERRIDE", conf: 1.0 },
]

export const timeScrubber = ["13:00", "13:30", "14:00", "14:25", "14:28", "14:32", "14:35", "14:39"]
