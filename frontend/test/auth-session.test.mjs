import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  TopoApiError,
  apiRequest,
  downloadApiFile,
  createBrowserSession,
  csrfCookieValue,
  subscribeAuthTransport,
  selectApiTenant,
  subscribeTenantDenied,
} from "../lib/topo-api.ts"


async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}

test("central tenant selection is explicit, switches headers, and never overrides auth", async () => {
  const originalFetch = globalThis.fetch
  const seen = []
  globalThis.fetch = async (_, init) => {
    seen.push(init.headers.get("X-Topo-Tenant-ID"))
    return Response.json({ ok: true })
  }
  try {
    selectApiTenant("tenant:a")
    await apiRequest("/api/v1/incidents", { headers: { "X-Topo-Tenant-ID": "spoofed" } })
    selectApiTenant("tenant:b")
    await apiRequest("/api/v1/incidents")
    await apiRequest("/api/v1/auth/session")
    selectApiTenant(null)
    await apiRequest("/api/v1/incidents")
    assert.deepEqual(seen, ["tenant:a", "tenant:b", null, null])
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
  }
})

test("tenant access denial is bounded and distinct from authentication and generic forbidden", async () => {
  const originalFetch = globalThis.fetch
  const authEvents = []
  const tenantEvents = []
  const stopAuth = subscribeAuthTransport((event) => authEvents.push(event.kind))
  const stopTenant = subscribeTenantDenied((id) => tenantEvents.push(id))
  let release
  globalThis.fetch = () => new Promise((resolve) => { release = resolve })
  try {
    selectApiTenant("tenant:a")
    const pending = apiRequest("/api/v1/incidents")
    selectApiTenant("tenant:b")
    release(Response.json({ detail: "TENANT_ACCESS_DENIED" }, { status: 403 }))
    await assert.rejects(pending, (error) => error.kind === "tenant-access-denied")
    assert.deepEqual(tenantEvents, ["tenant:a"])
    assert.deepEqual(authEvents, [])
  } finally {
    selectApiTenant(null)
    stopAuth()
    stopTenant()
    globalThis.fetch = originalFetch
  }
})

test("a successful response from the previous tenant is discarded", async () => {
  const originalFetch = globalThis.fetch
  let release
  globalThis.fetch = () => new Promise((resolve) => { release = resolve })
  try {
    selectApiTenant("tenant:a")
    const pending = apiRequest("/api/v1/incidents")
    selectApiTenant("tenant:b")
    release(Response.json({ private: "tenant a" }))
    await assert.rejects(pending, /Tenant selection changed/)
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
  }
})

test("PH-3G discards JSON when tenant switches during body consumption", async () => {
  const originalFetch = globalThis.fetch
  let releaseBody
  let bodyStarted
  const started = new Promise((resolve) => { bodyStarted = resolve })
  const body = new Promise((resolve) => { releaseBody = resolve })
  globalThis.fetch = async () => {
    const response = Response.json({})
    response.json = async () => { bodyStarted(); return body }
    return response
  }
  try {
    selectApiTenant("tenant:a")
    const pending = apiRequest("/api/v1/incidents")
    await started
    selectApiTenant("tenant:b")
    releaseBody({ private: "tenant a" })
    await assert.rejects(pending, /Tenant selection changed/)
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
  }
})

test("PH-3G prevents old-tenant download after delayed response body", async () => {
  const originalFetch = globalThis.fetch
  const originalDocument = globalThis.document
  let releaseBody
  let bodyStarted
  let clicked = false
  const started = new Promise((resolve) => { bodyStarted = resolve })
  const body = new Promise((resolve) => { releaseBody = resolve })
  globalThis.document = { createElement: () => ({ click() { clicked = true } }) }
  globalThis.fetch = async () => {
    const response = new Response("")
    response.blob = async () => { bodyStarted(); return body }
    return response
  }
  try {
    selectApiTenant("tenant:a")
    const pending = downloadApiFile("/api/v1/incidents/shared/reports/shared/export", "report.md")
    await started
    selectApiTenant("tenant:b")
    releaseBody(new Blob(["A private report"]))
    await assert.rejects(pending, /Tenant selection changed/)
    assert.equal(clicked, false)
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
    globalThis.document = originalDocument
  }
})

test("report downloads use the tenant-scoped transport, not a direct API anchor", async () => {
  const originalFetch = globalThis.fetch
  const originalDocument = globalThis.document
  let observed
  const link = { click() { this.clicked = true } }
  globalThis.document = { createElement: () => link }
  globalThis.fetch = async (url, init) => {
    observed = { url, init }
    return new Response("# Tenant report", { headers: { "Content-Type": "text/markdown" } })
  }
  try {
    selectApiTenant("tenant:a")
    await downloadApiFile("/api/v1/incidents/incident%3Aa/reports/report%3Aa/export", "report.md")
    assert.equal(observed.init.headers.get("X-Topo-Tenant-ID"), "tenant:a")
    assert.equal(observed.init.credentials, "same-origin")
    assert.doesNotMatch(observed.url, /\?/)
    assert.equal(link.download, "report.md")
    assert.equal(link.clicked, true)
    assert.match(link.href, /^blob:/)
    const component = await source("components/app/incident-post-incident-report.tsx")
    assert.match(component, /downloadApiFile\(/)
    assert.doesNotMatch(component, /href=\{exportUrl/)
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
    globalThis.document = originalDocument
  }
})

test("tenant gate precedes domain rendering and remounts tenant-owned state on switch", async () => {
  const gate = await source("components/auth/tenant-boundary.tsx")
  assert.match(await source("components/auth/auth-boundary.tsx"), /<TenantGate>\{children\}<\/TenantGate>/)
  assert.match(gate, /available\.length === 1/)
  assert.match(gate, /Fragment key=\{selected\}/)
  assert.match(gate, /requestTenant !== selection\.current/)
  assert.match(gate, /No tenant access is available/)
  assert.doesNotMatch(gate, /localStorage|sessionStorage/)
})

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


test("credential-shaped backend detail is not exposed by browser errors", async () => {
  const originalFetch = globalThis.fetch
  const marker = "topo_api_" + "SYNTHETIC_FRONTEND_ERROR_1234567890"
  globalThis.fetch = async () => Response.json(
    { detail: `Authorization: Bearer ${marker}` },
    { status: 500 },
  )
  try {
    await assert.rejects(
      apiRequest("/api/v1/example"),
      (error) => {
        assert.equal(error instanceof TopoApiError, true)
        assert.doesNotMatch(String(error), new RegExp(marker))
        return true
      },
    )
  } finally {
    globalThis.fetch = originalFetch
  }
})


test("browser credential state has no persistent storage or URL authority", () => {
  for (const value of [boundarySource, apiSource]) {
    assert.doesNotMatch(value, /localStorage|sessionStorage|indexedDB/)
  }
  assert.match(boundarySource, /setCredential\(""\)/)
  assert.doesNotMatch(apiSource, /[?&](?:token|credential|api_key)=/i)
  assert.match(configSource, /parsed\.username \|\| parsed\.password \|\| parsed\.search \|\| parsed\.hash/)
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
