"use client"

import { Fragment, type FormEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react"
import { LoaderCircle, LogOut, Plus } from "lucide-react"
import { createTenant, listTenants, selectApiTenant, subscribeTenantDenied, type TenantView, TopoApiError } from "@/lib/topo-api"
import { Button } from "@/components/ui/button"

export function TenantGate({
  children,
  onLogout,
  logoutError,
  canCreateWorkspace,
}: {
  children: ReactNode
  onLogout: () => Promise<void>
  logoutError: string | null
  canCreateWorkspace: boolean
}) {
  const [tenants, setTenants] = useState<TenantView[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const [loggingOut, setLoggingOut] = useState(false)
  const [workspaceName, setWorkspaceName] = useState("")
  const [creatingWorkspace, setCreatingWorkspace] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)
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

  async function signOut() {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await onLogout()
    } catch {
      // AuthProvider owns the error so it survives this gate being unmounted.
    } finally {
      setLoggingOut(false)
    }
  }

  async function submitWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (creatingWorkspace) return
    if (!workspaceName || workspaceName !== workspaceName.trim()) {
      setWorkspaceError("Enter a workspace name without leading or trailing spaces.")
      return
    }
    if (workspaceName.length > 500) {
      setWorkspaceError("Workspace names must be 500 characters or fewer.")
      return
    }

    setCreatingWorkspace(true)
    setWorkspaceError(null)
    try {
      const created = await createTenant(workspaceName)
      if (!active.current) return
      setTenants((current) => [...current, created])
      setWorkspaceName("")
      choose(created.tenant_id)
    } catch (error) {
      if (!active.current) return
      if (error instanceof TopoApiError && error.status === 422) {
        setWorkspaceError("Enter a valid workspace name without leading or trailing spaces.")
      } else if (error instanceof TopoApiError && error.status === 403) {
        setWorkspaceError("This local identity is not allowed to create a workspace.")
      } else {
        setWorkspaceError("Workspace creation failed. Retry when Topo is available.")
      }
    } finally {
      if (active.current) setCreatingWorkspace(false)
    }
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
        <Button
          variant="ghost"
          size="sm"
          aria-label="Sign out"
          disabled={loggingOut}
          onClick={() => void signOut()}
        >
          <LogOut className="h-3.5 w-3.5" />
          {loggingOut ? "Signing out…" : "Sign out"}
        </Button>
        {logoutError && <span className="text-danger" role="alert">{logoutError}</span>}
      </div>
      {selected ? (
        // Remount all tenant-owned state, including the sidebar and page caches.
        <Fragment key={selected}>{children}</Fragment>
      ) : (
        <main className="space-y-3 p-8">
          <h1 className="text-xl font-semibold">Choose your tenant</h1>
          <p role="status">{message ?? (tenants.length === 0
            ? (canCreateWorkspace
              ? "Create an empty local workspace to start exploring Topo."
              : "No tenant access is available. Ask your administrator to create a tenant or grant membership.")
            : "Select a tenant to load its incidents and topology.")}</p>
          {tenants.length === 0 && canCreateWorkspace && message === null && (
            <form className="max-w-md space-y-3" onSubmit={submitWorkspace}>
              <label className="block space-y-2" htmlFor="workspace-name">
                <span className="text-sm font-medium">Workspace name</span>
                <input
                  id="workspace-name"
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.target.value)}
                  disabled={creatingWorkspace}
                  maxLength={500}
                  autoComplete="off"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:border-primary"
                />
              </label>
              {workspaceError && <p className="text-sm text-danger" role="alert">{workspaceError}</p>}
              <Button type="submit" disabled={creatingWorkspace}>
                {creatingWorkspace
                  ? <LoaderCircle className="h-4 w-4 animate-spin" />
                  : <Plus className="h-4 w-4" />}
                {creatingWorkspace ? "Creating…" : "Create workspace"}
              </Button>
            </form>
          )}
        </main>
      )}
    </>
  )
}
