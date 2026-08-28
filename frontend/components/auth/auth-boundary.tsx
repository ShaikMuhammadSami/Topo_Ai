"use client"

import {
  createContext,
  type FormEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { AlertTriangle, LoaderCircle, LogIn, RefreshCw } from "lucide-react"

import { TopoLogo } from "@/components/topo-logo"
import { Button } from "@/components/ui/button"
import {
  type BrowserSession,
  TopoApiError,
  createBrowserSession,
  deleteBrowserSession,
  getBrowserSession,
  subscribeAuthTransport,
} from "@/lib/topo-api"


export type AuthStatus =
  | "authenticating"
  | "authenticated"
  | "unauthenticated"
  | "expired"
  | "forbidden"
  | "logging-out"
  | "backend-unavailable"

type AuthContextValue = {
  status: AuthStatus
  principal: BrowserSession | null
  login: (credential: string) => Promise<void>
  logout: () => Promise<void>
  retry: () => Promise<void>
  dismissForbidden: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)


function apiFailureKind(error: unknown) {
  return error instanceof TopoApiError
    ? error.kind
    : "backend-unavailable"
}


export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("authenticating")
  const [principal, setPrincipal] = useState<BrowserSession | null>(null)

  const resolveSession = useCallback(async () => {
    setStatus("authenticating")
    try {
      const value = await getBrowserSession()
      setPrincipal(value)
      setStatus("authenticated")
    } catch (error) {
      setPrincipal(null)
      setStatus(
        apiFailureKind(error) === "backend-unavailable"
          ? "backend-unavailable"
          : "unauthenticated",
      )
    }
  }, [])

  useEffect(() => {
    let active = true
    const unsubscribe = subscribeAuthTransport((event) => {
      if (!active) return
      if (event.kind === "unauthenticated") {
        setPrincipal(null)
        setStatus((current) =>
          current === "authenticating" ? "unauthenticated" : "expired",
        )
      } else if (event.kind === "forbidden") {
        setStatus((current) =>
          current === "authenticated" ? "forbidden" : current,
        )
      } else {
        setStatus("backend-unavailable")
      }
    })

    void getBrowserSession()
      .then((value) => {
        if (!active) return
        setPrincipal(value)
        setStatus("authenticated")
      })
      .catch((error: unknown) => {
        if (!active) return
        setPrincipal(null)
        setStatus(
          apiFailureKind(error) === "backend-unavailable"
            ? "backend-unavailable"
            : "unauthenticated",
        )
      })
    return () => {
      active = false
      unsubscribe()
    }
  }, [resolveSession])

  const login = useCallback(async (credential: string) => {
    setStatus("authenticating")
    try {
      const value = await createBrowserSession(credential)
      setPrincipal(value)
      setStatus("authenticated")
    } catch (error) {
      setPrincipal(null)
      setStatus(
        apiFailureKind(error) === "backend-unavailable"
          ? "backend-unavailable"
          : "unauthenticated",
      )
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    setStatus("logging-out")
    try {
      await deleteBrowserSession()
      setPrincipal(null)
      setStatus("unauthenticated")
    } catch (error) {
      setStatus(
        apiFailureKind(error) === "backend-unavailable"
          ? "backend-unavailable"
          : "expired",
      )
      throw error
    }
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    status,
    principal,
    login,
    logout,
    retry: resolveSession,
    dismissForbidden: () => setStatus("authenticated"),
  }), [status, principal, login, logout, resolveSession])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}


export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider")
  }
  return value
}


export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth()

  if (auth.status === "authenticated" || auth.status === "forbidden") {
    return (
      <>
        {auth.status === "forbidden" && (
          <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-3 border-b border-warning/40 bg-warning/10 px-4 py-2 text-xs text-warning backdrop-blur">
            <AlertTriangle className="h-4 w-4" />
            Your identity is valid, but it is not allowed to perform that action.
            <button
              type="button"
              className="font-mono underline underline-offset-2"
              onClick={auth.dismissForbidden}
            >
              Dismiss
            </button>
          </div>
        )}
        {children}
      </>
    )
  }

  if (auth.status === "authenticating" || auth.status === "logging-out") {
    return (
      <AuthFrame>
        <LoaderCircle className="h-6 w-6 animate-spin text-primary" />
        <p className="font-mono text-xs text-muted-foreground">
          {auth.status === "logging-out"
            ? "Ending the browser session…"
            : "Establishing the browser session…"}
        </p>
      </AuthFrame>
    )
  }

  if (auth.status === "backend-unavailable") {
    return (
      <AuthFrame>
        <AlertTriangle className="h-6 w-6 text-warning" />
        <h1 className="font-heading text-xl font-bold">Topo is unavailable</h1>
        <p className="max-w-md text-center text-sm text-muted-foreground">
          The authentication service could not be reached. No incident or
          topology data was requested.
        </p>
        <Button variant="outline" onClick={() => void auth.retry()}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </AuthFrame>
    )
  }

  return <LoginForm expired={auth.status === "expired"} onLogin={auth.login} />
}


function LoginForm({
  expired,
  onLogin,
}: {
  expired: boolean
  onLogin: (credential: string) => Promise<void>
}) {
  const [credential, setCredential] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const submittedCredential = credential
    setSubmitting(true)
    setError(null)
    try {
      await onLogin(submittedCredential)
    } catch {
      setError("Authentication failed. Check the credential and deployment access policy.")
    } finally {
      setCredential("")
      setSubmitting(false)
    }
  }

  return (
    <AuthFrame>
      <div className="mb-2"><TopoLogo version="secure browser" /></div>
      <h1 className="font-heading text-2xl font-bold">Sign in to Topo</h1>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        Exchange an operator credential for an opaque, server-side browser session.
        The credential is cleared after this request and is never stored by the UI.
      </p>
      {expired && (
        <p className="rounded-md border border-warning/40 bg-warning/10 px-4 py-2 text-xs text-warning">
          Your browser session expired. Sign in again to continue.
        </p>
      )}
      <form className="w-full max-w-md space-y-3" onSubmit={submit}>
        <label className="block space-y-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Operator / API credential
          </span>
          <input
            type="password"
            required
            autoComplete="off"
            value={credential}
            onChange={(event) => setCredential(event.target.value)}
            className="h-11 w-full rounded-md border border-input bg-background px-3 font-mono text-sm outline-none focus:border-primary"
            aria-label="Operator or API credential"
          />
        </label>
        {error && (
          <p className="text-xs text-danger" role="alert">{error}</p>
        )}
        <Button className="w-full" type="submit" disabled={submitting}>
          {submitting
            ? <LoaderCircle className="h-4 w-4 animate-spin" />
            : <LogIn className="h-4 w-4" />}
          {submitting ? "Signing in…" : "Create browser session"}
        </Button>
      </form>
    </AuthFrame>
  )
}


function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 bg-background px-6 text-foreground">
      {children}
    </main>
  )
}
