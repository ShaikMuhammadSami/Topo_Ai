"use client"

import { useRef, useState, useEffect } from "react"

type Line = { type: "in" | "out"; text: string; tone?: "ok" | "warn" | "danger" | "info" | "muted" }

const suggestions = [
  "topo why checkout-api",
  "topo identities",
  "topo diff --since 1h",
  "topo signals checkout-api",
  "topo changes --last 1h",
  "help",
]

function runCommand(raw: string): Line[] {
  const cmd = raw.trim().replace(/^topo\s+/, "").trim()

  if (cmd === "help" || cmd === "") {
    return [
      { type: "out", text: "available commands:", tone: "muted" },
      { type: "out", text: "  why <svc>          ranked hypotheses with evidence" },
      { type: "out", text: "  identities         repo → pod resolution table" },
      { type: "out", text: "  diff --since <dur> temporal graph diff" },
      { type: "out", text: "  signals <svc>      signal stream for a service" },
      { type: "out", text: "  changes --last <dur> recent commits + deploys" },
    ]
  }
  if (cmd.startsWith("why")) {
    return [
      { type: "out", text: "~ pulling temporal graph @ t=14:32:08Z ± 60m", tone: "muted" },
      { type: "out", text: "H1 conf=0.91  Cache removal regression in price_quote()", tone: "danger" },
      { type: "out", text: "   +0.42 diff: removed @lru_cache · +0.31 temporal deploy → spike", tone: "muted" },
      { type: "out", text: "H2 conf=0.74  Memory limit exhaustion (OOMKilled)", tone: "warn" },
      { type: "out", text: "H3 conf=0.18  Upstream pricing-svc latency", tone: "muted" },
      { type: "out", text: "✓ ranked 3 hypotheses with evidence chains in 412ms", tone: "ok" },
    ]
  }
  if (cmd.startsWith("identities")) {
    return [
      { type: "out", text: "REPO                        DEPLOYMENT     SOURCE         CONF", tone: "muted" },
      { type: "out", text: "acme/checkout               checkout-api   LABEL-MATCH    0.99", tone: "ok" },
      { type: "out", text: "acme/pricing                pricing-svc    LABEL-MATCH    0.99", tone: "ok" },
      { type: "out", text: "acme/payments-ledger        ledger         NAMING-HEUR    0.74", tone: "warn" },
      { type: "out", text: "—                           redis-master   MANUAL         1.00", tone: "info" },
    ]
  }
  if (cmd.startsWith("diff")) {
    return [
      { type: "out", text: "~ checkout-api state: ok → blame", tone: "danger" },
      { type: "out", text: "~ pricing-svc state: ok → warn", tone: "warn" },
      { type: "out", text: "+ 0 new nodes · + 0 new edges", tone: "ok" },
    ]
  }
  if (cmd.startsWith("signals")) {
    return [
      { type: "out", text: "14:32:25 DIFF   checkout-api  removed @lru_cache on price_quote()", tone: "warn" },
      { type: "out", text: "14:32:21 POD    checkout-api  9 pods OOMKilled (exit 137)", tone: "danger" },
      { type: "out", text: "14:28:41 DEPLOY checkout-api  PR #2284 merged + auto-deploy", tone: "info" },
    ]
  }
  if (cmd.startsWith("changes")) {
    return [
      { type: "out", text: "9a4f12c #2284 m.solis  perf: drop in-memory cache (SUSPECTED)", tone: "danger" },
      { type: "out", text: "3122f0a #2281 k.lin    feat(auth): extend token TTL to 24h", tone: "muted" },
    ]
  }
  return [{ type: "out", text: `command not found: ${cmd} — try \`help\``, tone: "danger" }]
}

const toneClass: Record<string, string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  muted: "text-muted-foreground",
}

export function CliView() {
  const [lines, setLines] = useState<Line[]>([
    { type: "out", text: "topo CLI · v0.1.0-demo · connected to cluster prod-eu-west-1", tone: "ok" },
    { type: "out", text: "type `help` to list commands · try `topo why checkout-api`", tone: "muted" },
  ])
  const [input, setInput] = useState("")
  const [history, setHistory] = useState<string[]>([])
  const [hIdx, setHIdx] = useState(-1)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [lines])

  function submit(value: string) {
    const v = value.trim()
    if (!v) return
    setHistory((h) => [...h, v])
    setHIdx(-1)
    setLines((l) => [...l, { type: "in", text: v }, ...runCommand(v)])
    setInput("")
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 p-5">
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          cli simulator
        </p>
        <h2 className="font-heading text-4xl font-black tracking-tight">
          topo from your terminal
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          Every action in the web workspace has a CLI equivalent. Type below —
          arrow-up recalls history.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => submit(s)}
            className="rounded-sm border border-border px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            ❯ {s}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
          <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
          <span className="ml-3 font-mono text-[11px] text-muted-foreground">
            topo — zsh — 120×30
          </span>
        </div>
        <div
          ref={scrollRef}
          className="h-[420px] overflow-y-auto p-4 font-mono text-[12px] leading-relaxed"
        >
          {lines.map((l, i) =>
            l.type === "in" ? (
              <p key={i}>
                <span className="text-warn">topo</span>{" "}
                <span className="text-info">❯</span> {l.text}
              </p>
            ) : (
              <p key={i} className={l.tone ? toneClass[l.tone] : ""}>
                {l.text}
              </p>
            ),
          )}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit(input)
          }}
          className="flex items-center gap-2 border-t border-border px-4 py-3"
        >
          <span className="font-mono text-[13px] text-warn">topo</span>
          <span className="font-mono text-[13px] text-info">❯</span>
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowUp") {
                e.preventDefault()
                if (!history.length) return
                const next = hIdx < 0 ? history.length - 1 : Math.max(0, hIdx - 1)
                setHIdx(next)
                setInput(history[next])
              }
              if (e.key === "ArrowDown") {
                e.preventDefault()
                if (hIdx < 0) return
                const next = hIdx + 1
                if (next >= history.length) {
                  setHIdx(-1)
                  setInput("")
                } else {
                  setHIdx(next)
                  setInput(history[next])
                }
              }
            }}
            placeholder="type a command and press enter…"
            className="flex-1 bg-transparent font-mono text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
          />
        </form>
      </div>
    </div>
  )
}
