import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  TopoApiError,
  apiRequest,
  createBrowserSession,
  csrfCookieValue,
  subscribeAuthTransport,
} from "../lib/topo-api.ts"


async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}

const [boundarySource, layoutSource, apiSource, configSource, reportSource] =
  await Promise.all([
    source("components/auth/auth-boundary.tsx"),
    source("app/app/layout.tsx"),
    source("lib/topo-api.ts"),
    source("next.config.mjs"),
    source("components/app/incident-post-incident-report.tsx"),
  ])


test("CSRF cookie parsing is bounded to the dedicated readable cookie", () => {
  assert.equal(
    csrfCookieValue("other=value; topo_csrf=csrf%2Dvalue; final=x"),
    "csrf-value",
  )
  assert.equal(csrfCookieValue("topo_session=secret"), null)
})


test("central API transport stays same-origin and injects CSRF for unsafe calls", async () => {
  const originalFetch = globalThis.fetch
  const originalDocument = globalThis.document
  let observed
  globalThis.document = { cookie: "topo_csrf=test-csrf" }
  globalThis.fetch = async (url, init) => {
    observed = { url, init }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })
  }
  try {
    assert.deepEqual(
      await apiRequest("/api/v1/example", { method: "POST" }),
      { ok: true },
    )
  } finally {
    globalThis.fetch = originalFetch
    globalThis.document = originalDocument
  }

  assert.equal(observed.url, "/api/v1/example")
  assert.equal(observed.init.credentials, "same-origin")
  assert.equal(observed.init.headers.get("X-Topo-CSRF"), "test-csrf")
})


test("browser login sends the transient credential only as Authorization", async () => {
  const originalFetch = globalThis.fetch
  const originalDocument = globalThis.document
  const credential = "transient-test-credential"
  let observed
  globalThis.document = { cookie: "" }
  globalThis.fetch = async (url, init) => {
    observed = { url, init }
    return new Response(
      JSON.stringify({
        subject: "test:user",
        display_name: "Test User",
        roles: ["viewer"],
        authentication_type: "session",
        absolute_expires_at: "2026-08-28T20:00:00Z",
      }),
      { status: 201, headers: { "Content-Type": "application/json" } },
    )
  }
  try {
    await createBrowserSession(credential)
  } finally {
    globalThis.fetch = originalFetch
    globalThis.document = originalDocument
  }

  assert.equal(observed.url, "/api/v1/auth/session")
  assert.equal(observed.init.headers.get("Authorization"), `Bearer ${credential}`)
  assert.equal(observed.init.body, undefined)
})


test("401, 403 and backend failures remain distinct transport states", async () => {
  const originalFetch = globalThis.fetch
  const events = []
  const unsubscribe = subscribeAuthTransport((event) => events.push(event.kind))
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: "Authentication is required." }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    )
    await assert.rejects(
      apiRequest("/api/v1/example"),
      (error) => error instanceof TopoApiError && error.kind === "unauthenticated",
    )

    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: "Forbidden." }),
      { status: 403, headers: { "Content-Type": "application/json" } },
    )
    await assert.rejects(
      apiRequest("/api/v1/example"),
      (error) => error instanceof TopoApiError && error.kind === "forbidden",
    )

    globalThis.fetch = async () => {
      throw new TypeError("network down")
    }
    await assert.rejects(
      apiRequest("/api/v1/example"),
      (error) =>
        error instanceof TopoApiError && error.kind === "backend-unavailable",
    )
  } finally {
    unsubscribe()
    globalThis.fetch = originalFetch
  }
  assert.deepEqual(events, ["unauthenticated", "forbidden", "backend-unavailable"])
})


test("the app gate resolves authentication before product components mount", () => {
  assert.match(layoutSource, /<AuthProvider>[\s\S]*<AuthGate>[\s\S]*<AppSidebar \/>/)
  assert.match(boundarySource, /getBrowserSession\(\)/)
  assert.match(boundarySource, /status === "authenticated" \|\| auth\.status === "forbidden"/)
  assert.match(boundarySource, /"authenticating"[\s\S]*"expired"[\s\S]*"forbidden"[\s\S]*"logging-out"[\s\S]*"backend-unavailable"/)
})


test("login clears component credential memory and never uses browser storage", () => {
  assert.match(boundarySource, /setCredential\(""\)/)
  assert.doesNotMatch(boundarySource, /localStorage|sessionStorage/)
  assert.doesNotMatch(apiSource, /localStorage|sessionStorage/)
  assert.doesNotMatch(apiSource, /NEXT_PUBLIC_TOPO_API_URL/)
})


test("same-origin rewrite and report exports contain no query credential", () => {
  assert.match(configSource, /process\.env\.TOPO_BACKEND_URL/)
  assert.match(configSource, /source: "\/api\/:path\*"/)
  assert.doesNotMatch(configSource, /NEXT_PUBLIC_TOPO_API_URL/)
  assert.match(reportSource, /`\/api\/v1\/incidents\//)
  assert.doesNotMatch(reportSource, /\?(?:token|api_key|session)=/)
  assert.doesNotMatch(reportSource, /NEXT_PUBLIC_TOPO_API_URL/)
})
