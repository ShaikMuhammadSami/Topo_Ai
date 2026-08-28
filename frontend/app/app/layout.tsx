import type { ReactNode } from "react"
import { AppSidebar } from "@/components/app/app-sidebar"
import {
  AuthGate,
  AuthProvider,
} from "@/components/auth/auth-boundary"

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>
        <div className="flex min-h-screen bg-background">
          <AppSidebar />
          <div className="flex min-w-0 flex-1 flex-col">{children}</div>
        </div>
      </AuthGate>
    </AuthProvider>
  )
}
