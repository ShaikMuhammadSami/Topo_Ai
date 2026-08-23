"use client"

import { useState } from "react"
import { Sparkles, Send } from "lucide-react"

type Msg = { role: "user" | "topo"; node: React.ReactNode }

const prompts = [
  "Why is checkout slow right now?",
  "Has this happened before?",
  "What's the blast radius if I roll back pricing-svc?",
  "Summarize the last 6 incidents in payments.",
]

const firstAnswer = (
  <>
    <p className="leading-relaxed">
      Most likely cause (demo heuristic rank <span className="font-bold text-warn">0.91</span>)
      - regression in checkout-api from{" "}
      <code className="rounded-sm bg-secondary px-1 text-info">PR #2284</code> merged at
      14:28 UTC. The diff removed{" "}
      <code className="rounded-sm bg-secondary px-1 text-warn">
        @lru_cache(maxsize=4096)
      </code>{" "}
      on <code className="rounded-sm bg-secondary px-1 text-warn">price_quote()</code>,
      which now issues a synchronous DB query on every checkout. Two corroborating
      signals: (1) DB query rate on{" "}
      <code className="rounded-sm bg-secondary px-1 text-info">pricing.quotes</code>{" "}
      rose 18× immediately after the deploy, (2) 9 of 11 checkout-api pods OOMKilled
      within 4m of the deploy.
    </p>
    <p className="mt-3 leading-relaxed">
      Suggested action: revert PR #2284 or raise checkout-api memory limit to 1Gi.
    </p>
  </>
)

const citations = [
  "graph://deploy/checkout-api@9a4f12c",
  "git://acme/checkout/pull/2284",
  "signal://k8s.event/OOMKilled/checkout-api-*",
  "metric://db.queries.pricing.quotes",
]

export function AskView() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "user", node: "Why is checkout slow right now?" },
    {
      role: "topo",
      node: (
        <>
          {firstAnswer}
          <div className="mt-4 border-t border-border pt-3">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Citations
            </p>
            <ul className="mt-2 space-y-1 font-mono text-[11px] text-info">
              {citations.map((c) => (
                <li key={c}>❯ {c}</li>
              ))}
            </ul>
          </div>
        </>
      ),
    },
  ])
  const [input, setInput] = useState("")

  function send(text: string) {
    const v = text.trim()
    if (!v) return
    setMessages((m) => [
      ...m,
      { role: "user", node: v },
      {
        role: "topo",
        node: (
          <p className="leading-relaxed text-muted-foreground">
            This is a demo - topo answers are mocked. In production this query runs
            against the on-prem llama-3.1-70b model with RAG over /runbooks and
            /incidents, and every answer cites the exact graph nodes, diffs and
            signals it relied on.
          </p>
        ),
      },
    ])
    setInput("")
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-5">
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          reasoning layer
        </p>
        <h2 className="flex items-center gap-2 font-heading text-4xl font-black tracking-tight">
          <Sparkles className="h-7 w-7 text-warn" /> Ask topo
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          Natural language over the graph. Answers cite the exact nodes, diffs and
          signals they relied on - so you can verify them, not just trust them.
        </p>
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          running on-prem · llama-3.1-70b via ollama · RAG over /runbooks + /incidents ·{" "}
          <span className="text-warn">MOCKED IN DEMO</span>
        </p>
      </div>

      <div className="space-y-4">
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-lg rounded-md border border-border bg-card px-4 py-3">
                <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  You
                </p>
                <p className="mt-1 text-sm">{m.node}</p>
              </div>
            </div>
          ) : (
            <div key={i} className="rounded-md border border-warn/40 bg-warn/[0.04] p-5">
              <p className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-warn">
                <Sparkles className="h-3 w-3" /> topo
              </p>
              <div className="text-sm">{m.node}</div>
            </div>
          ),
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {prompts.map((p) => (
          <button
            key={p}
            onClick={() => send(p)}
            className="rounded-sm border border-border px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            ❯ {p}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
        className="flex items-center gap-2 rounded-md border border-border bg-card px-4 py-3"
      >
        <Sparkles className="h-4 w-4 text-warn" />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="ask in natural language…"
          className="flex-1 bg-transparent font-mono text-sm outline-none placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 rounded-sm bg-primary px-3 py-1.5 font-mono text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          send <Send className="h-3 w-3" />
        </button>
      </form>
    </div>
  )
}
