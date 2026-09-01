import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

import {
  selectApiTenant,
  updateWebhookEndpoint,
} from "../lib/topo-api.ts"


async function source(path) {
  return readFile(new URL(`../${path}`, import.meta.url), "utf8")
}


test("webhook credential replacement is transient and carries a stable request operation key", async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return Response.json({
      webhook_id: "webhook:a/b",
      name: "Secure",
      url: "https://example.test/topo",
      event_types: ["incident.created"],
      has_signing_secret: true,
      has_protected_headers: false,
      protected_header_names: [],
      active: true,
      timeout_seconds: 10,
      max_attempts: 3,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    })
  }
  try {
    selectApiTenant("tenant:test")
    await updateWebhookEndpoint("webhook:a/b", {
      signing_secret: "transient-ui-marker",
    })
    assert.equal(calls.length, 1)
    assert.match(String(calls[0].url), /webhook%3Aa%2Fb$/)
    assert.equal(calls[0].init.method, "PATCH")
    assert.match(calls[0].init.headers.get("Idempotency-Key"), /^[0-9a-f-]{36}$/i)
    assert.deepEqual(JSON.parse(calls[0].init.body), {
      signing_secret: "transient-ui-marker",
    })
  } finally {
    selectApiTenant(null)
    globalThis.fetch = originalFetch
  }
})


test("webhook UI keeps raw values in password inputs and never browser storage", async () => {
  const ui = await source("components/app/webhook-integrations-view.tsx")
  assert.match(ui, /type="password"/)
  assert.match(ui, /Values are write-only and encrypted/)
  assert.match(ui, /protected_header_names/)
  assert.doesNotMatch(ui, /localStorage|sessionStorage|indexedDB/)
})


test("normal webhook read types expose metadata but no SecretStore reference", async () => {
  const types = await source("lib/topo-types.ts")
  const view = types.slice(
    types.indexOf("export type WebhookEndpointView"),
    types.indexOf("export type WebhookDeliveryView"),
  )
  assert.match(view, /has_signing_secret: boolean/)
  assert.match(view, /protected_header_names: string\[\]/)
  assert.doesNotMatch(view, /secret_ref|header.*value/i)
})
