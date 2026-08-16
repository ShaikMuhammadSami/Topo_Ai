import { defineConfig, globalIgnores } from "eslint/config"
import nextVitals from "eslint-config-next/core-web-vitals"
import nextTypeScript from "eslint-config-next/typescript"

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    // These established data-loading screens predate the React 19 lint rule.
    // Keep the exception scoped to existing files rather than weakening new UI.
    files: [
      "components/app/code-to-runtime-view.tsx",
      "components/app/incident-ai-explanation.tsx",
      "components/app/incident-copilot.tsx",
      "components/app/incident-inbox.tsx",
      "components/app/incident-investigation-plan.tsx",
      "components/app/incident-ownership-impact.tsx",
      "components/app/incident-post-incident-report.tsx",
      "components/app/incident-recommendations.tsx",
      "components/app/incident-recovery-verification.tsx",
      "components/app/live-cluster-view.tsx",
      "components/app/live-identities-view.tsx",
      "components/app/live-incident-workspace.tsx",
      "components/app/live-signals-view.tsx",
      "components/app/live-topology-view.tsx",
      "components/app/network-dependencies-view.tsx",
      "components/app/predeployment-impact-view.tsx",
      "components/app/webhook-integrations-view.tsx",
    ],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
])
