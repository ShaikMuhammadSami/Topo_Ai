"use client"

import { Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from "react"
import { listTenants, selectApiTenant, subscribeTenantDenied, type TenantView } from "@/lib/topo-api"
import { Button } from "@/components/ui/button"

export function TenantGate({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<TenantView[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const active = useRef(true)
  const selection = useRef<string | null>(null)
  const generation = useRef(0)

  const choose = useCallback((id: string | null) => {
    selection.current = id
    selectApiTenant(id)
    setSelected(id)
  }, [])

  const loadAccess = useCallback(async (autoSelect: boolean) => {
    const request = ++generation.current
    try {
      const available = await listTenants()
      if (!active.current || request !== generation.current) return
      setTenants(available)
      if (autoSelect && available.length === 1) choose(available[0].tenant_id)
      setMessage(null)
    } catch {
      if (!active.current || request !== generation.current) return
      setTenants([])
      setMessage("Tenant access could not be loaded. Retry when Topo is available.")
    } finally {
      if (active.current && request === generation.current) setLoading(false)
    }
  }, [choose])

  function reload() {
    choose(null)
    setLoading(true)
    void loadAccess(false)
  }

  useEffect(() => {
    active.current = true
    const request = ++generation.current
    void listTenants().then((available) => {
      if (!active.current || request !== generation.current) return
      setTenants(available)
      if (available.length === 1) choose(available[0].tenant_id)
      setMessage(null)
      setLoading(false)
    }).catch(() => {
      if (!active.current || request !== generation.current) return
      setMessage("Tenant access could not be loaded. Retry when Topo is available.")
      setLoading(false)
    })
    const unsubscribe = subscribeTenantDenied((requestTenant) => {
      // A late response from an unmounted tenant must not clear a newer one.
      if (requestTenant !== selection.current) return
      choose(null)
      setTenants([])
      setMessage("Access to this tenant is no longer available. Reload your available tenants.")
    })
    return () => {
      active.current = false
      generation.current += 1
      selectApiTenant(null)
      unsubscribe()
    }
  }, [choose])

  if (loading) return <main className="p-8" role="status">Loading your tenant access…</main>

  return (
    <>
      <div className="flex items-center gap-3 border-b border-border bg-background px-4 py-2 text-sm">
        <label htmlFor="topo-tenant">Tenant</label>
        <select
          id="topo-tenant"
          value={selected ?? ""}
          onChange={(event) => choose(event.target.value || null)}
          className="rounded border border-input bg-background px-2 py-1"
        >
          <option value="">Select a tenant</option>
          {tenants.map((tenant) => <option key={tenant.tenant_id} value={tenant.tenant_id}>{tenant.display_name} ({tenant.tenant_id.slice(-8)})</option>)}
        </select>
        <Button variant="ghost" size="sm" onClick={reload}>Reload access</Button>
      </div>
      {selected ? (
        // Remount all tenant-owned state, including the sidebar and page caches.
        <Fragment key={selected}>{children}</Fragment>
      ) : (
        <main className="space-y-3 p-8">
          <h1 className="text-xl font-semibold">Choose your tenant</h1>
          <p role="status">{message ?? (tenants.length === 0
            ? "No tenant access is available. Ask your administrator to create a tenant or grant membership."
            : "Select a tenant to load its incidents and topology.")}</p>
        </main>
      )}
    </>
  )
}
