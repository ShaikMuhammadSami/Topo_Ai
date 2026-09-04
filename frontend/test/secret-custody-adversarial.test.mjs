import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import { selectApiTenant, updateWebhookEndpoint } from "../lib/topo-api.ts"


async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}


test("PH-4E secret form material uses only the authorized request body", async () => {
  const marker = `WEBHOOK_FORM_${crypto.randomUUID()}`
  const originalFetch = globalThis.fetch
  const writes = []
  globalThis.localStorage = { setItem: (...args) => writes.push(["local", ...args]) }
  globalThis.sessionStorage = { setItem: (...args) => writes.push(["session", ...args]) }
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: String(init.body), tenant: init.headers.get("X-Topo-Tenant-ID") })
    return Response.json({
      webhook_id: "webhook:ph4e",
      name: "PH-4E",
      url: "https://example.test/topo",
      event_types: ["incident.created"],
      has_signing_secret: true,
      has_protected_headers: false,
      protected_header_names: [],
      active: true,
      timeout_seconds: 10,
      max_attempts: 1,
      created_at: "2026-09-04T00:00:00Z",
      updated_at: "2026-09-04T00:00:00Z",
    })
  }
  try {
    selectApiTenant("tenant:ph4e-a")
    await updateWebhookEndpoint("webhook:ph4e", { signing_secret: marker })
    assert.equal(calls.length, 1)
    assert.equal(calls[0].tenant, "tenant:ph4e-a")
    assert.equal((calls[0].body.match(new RegExp(marker, "g")) || []).length, 1)
    assert.deepEqual(writes, [])
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
    delete globalThis.localStorage
    delete globalThis.sessionStorage
  }
})


test("PH-4E webhook UI clears secret state and cannot persist it across tenants", async () => {
  const ui = await source("components/app/webhook-integrations-view.tsx")
  const tenantGate = await source("components/auth/tenant-boundary.tsx")
  assert.match(ui, /setSecret\(""\)/)
  assert.match(ui, /setProtectedHeaders\(""\)/)
  assert.match(ui, /setReplacementSecrets\(\(current\).*webhook_id.*""/s)
  assert.match(ui, /setReplacementHeaders\(\(current\).*webhook_id.*""/s)
  assert.match(tenantGate, /<Fragment key=\{selected\}>\{children\}<\/Fragment>/)
  assert.doesNotMatch(ui, /localStorage|sessionStorage|indexedDB/)
})


test("PH-4E normal response types remain metadata-only", async () => {
  const types = await source("lib/topo-types.ts")
  const view = types.slice(
    types.indexOf("export type WebhookEndpointView"),
    types.indexOf("export type WebhookDeliveryView"),
  )
  assert.match(view, /has_signing_secret: boolean/)
  assert.match(view, /has_protected_headers: boolean/)
  assert.match(view, /protected_header_names: string\[\]/)
  assert.doesNotMatch(view, /secret_ref|header.*value|signing_secret\?:/i)
})
