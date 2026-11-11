export const LOGOUT_FAILURE_MESSAGE =
  "Sign out failed. Your browser session may still be active; try again."

type LogoutStatus =
  | "logging-out"
  | "authenticated"
  | "unauthenticated"
  | "expired"

export async function runLogoutLifecycle({
  deleteSession,
  classifyError,
  setStatus,
  clearPrincipal,
  setError,
}: {
  deleteSession: () => Promise<void>
  classifyError: (error: unknown) => string
  setStatus: (status: LogoutStatus) => void
  clearPrincipal: () => void
  setError: (message: string | null) => void
}): Promise<void> {
  setError(null)
  setStatus("logging-out")
  try {
    await deleteSession()
    clearPrincipal()
    setStatus("unauthenticated")
  } catch (error) {
    if (classifyError(error) === "unauthenticated") {
      clearPrincipal()
      setStatus("expired")
    } else {
      // A failed delete does not prove that the server-side session ended.
      setError(LOGOUT_FAILURE_MESSAGE)
      setStatus("authenticated")
    }
    throw error
  }
}
