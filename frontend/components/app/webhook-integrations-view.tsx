"use client"

import {
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
  Send,
  Webhook,
  XCircle,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  createWebhookEndpoint,
  listWebhookDeliveries,
  listWebhookEndpoints,
  testWebhookEndpoint,
  updateWebhookEndpoint,
} from "@/lib/topo-api"
import type {
  WebhookDeliveryView,
  WebhookEndpointView,
  WebhookEventType,
} from "@/lib/topo-types"


const eventOptions: Array<{
  value: WebhookEventType
  label: string
}> = [
  {
    value: "incident.created",
    label: "Incident created",
  },
  {
    value: "incident.status_changed",
    label: "Incident status changed",
  },
  {
    value: "recommendation.generated",
    label: "Recommendation generated",
  },
  {
    value: "recovery.verified",
    label: "Recovery verified",
  },
  {
    value: "recovery.failed",
    label: "Recovery failed",
  },
  {
    value: "recovery.inconclusive",
    label: "Recovery inconclusive",
  },
  {
    value: "change.risk_detected",
    label: "High-risk change detected",
  },
]


export function WebhookIntegrationsView() {
  const [endpoints, setEndpoints] =
    useState<WebhookEndpointView[]>([])

  const [deliveries, setDeliveries] =
    useState<WebhookDeliveryView[]>([])

  const [name, setName] =
    useState("")

  const [url, setUrl] =
    useState("")

  const [secret, setSecret] =
    useState("")

  const [
    selectedEvents,
    setSelectedEvents,
  ] = useState<WebhookEventType[]>(
    eventOptions.map(
      (item) => item.value,
    ),
  )

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  async function refresh() {
    setLoading(true)
    setError(null)

    try {
      const [
        endpointResults,
        deliveryResults,
      ] = await Promise.all([
        listWebhookEndpoints(),
        listWebhookDeliveries({
          limit: 100,
        }),
      ])

      setEndpoints(endpointResults)
      setDeliveries(deliveryResults)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  useEffect(() => {
    void refresh()
  }, [])


  function toggleEvent(
    eventType: WebhookEventType,
  ) {
    setSelectedEvents((current) =>
      current.includes(eventType)
        ? current.filter(
            (value) =>
              value !== eventType,
          )
        : [
            ...current,
            eventType,
          ],
    )
  }


  async function handleCreate() {
    if (
      !name.trim() ||
      !url.trim() ||
      selectedEvents.length === 0
    ) {
      setError(
        "Provide a name, URL and at least one event type.",
      )
      return
    }

    setLoading(true)
    setError(null)

    try {
      await createWebhookEndpoint({
        name: name.trim(),
        url: url.trim(),
        event_types:
          selectedEvents,
        signing_secret:
          secret.trim() || null,
        active: true,
        timeout_seconds: 10,
        max_attempts: 3,
      })

      setName("")
      setUrl("")
      setSecret("")

      await refresh()
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  async function handleTest(
    webhookId: string,
  ) {
    setLoading(true)
    setError(null)

    try {
      await testWebhookEndpoint(
        webhookId,
      )

      await refresh()
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  async function toggleActive(
    endpoint: WebhookEndpointView,
  ) {
    setLoading(true)
    setError(null)

    try {
      await updateWebhookEndpoint(
        endpoint.webhook_id,
        {
          active: !endpoint.active,
        },
      )

      await refresh()
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  return (
    <div className="space-y-6 p-6">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
          workflow integrations
        </p>

        <h1 className="mt-2 font-heading text-3xl font-bold">
          Webhooks
        </h1>

        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Publish incident, recommendation,
          recovery and change-risk events to
          external workflow systems.
        </p>
      </header>


      {error && (
        <div className="flex gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="h-5 w-5 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      <section className="rounded-md border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <Webhook className="h-5 w-5 text-info" />

          <h2 className="font-heading text-lg font-bold">
            Add webhook
          </h2>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <label>
            <FieldLabel>Name</FieldLabel>

            <input
              value={name}
              onChange={(event) =>
                setName(
                  event.target.value,
                )
              }
              placeholder="Operations webhook"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
            />
          </label>

          <label>
            <FieldLabel>URL</FieldLabel>

            <input
              value={url}
              onChange={(event) =>
                setUrl(
                  event.target.value,
                )
              }
              placeholder="https://example.com/topo"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            />
          </label>

          <label className="lg:col-span-2">
            <FieldLabel>
              Signing secret
            </FieldLabel>

            <input
              type="password"
              value={secret}
              onChange={(event) =>
                setSecret(
                  event.target.value,
                )
              }
              placeholder="Optional HMAC secret, minimum 16 characters"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            />
          </label>
        </div>

        <div className="mt-5">
          <FieldLabel>
            Subscribed events
          </FieldLabel>

          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {eventOptions.map(
              (item) => (
                <label
                  key={item.value}
                  className="flex items-center gap-2 rounded-sm border border-border p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={selectedEvents.includes(
                      item.value,
                    )}
                    onChange={() =>
                      toggleEvent(
                        item.value,
                      )
                    }
                  />

                  {item.label}
                </label>
              ),
            )}
          </div>
        </div>

        <Button
          className="mt-5"
          disabled={loading}
          onClick={() =>
            void handleCreate()
          }
        >
          {loading ? (
            <LoaderCircle className="animate-spin" />
          ) : (
            <Webhook />
          )}

          Create webhook
        </Button>
      </section>


      <section className="overflow-hidden rounded-md border border-border bg-card">
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-heading text-lg font-bold">
            Configured endpoints
          </h2>

          <Button
            variant="outline"
            disabled={loading}
            onClick={() =>
              void refresh()
            }
          >
            <RefreshCw
              className={
                loading
                  ? "animate-spin"
                  : ""
              }
            />

            Refresh
          </Button>
        </header>

        {endpoints.length === 0 ? (
          <p className="p-6 font-mono text-xs text-muted-foreground">
            No webhook endpoints configured.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {endpoints.map(
              (endpoint) => (
                <article
                  key={
                    endpoint.webhook_id
                  }
                  className="p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        {endpoint.active ? (
                          <CheckCircle2 className="h-4 w-4 text-ok" />
                        ) : (
                          <XCircle className="h-4 w-4 text-muted-foreground" />
                        )}

                        <h3 className="font-heading font-bold">
                          {endpoint.name}
                        </h3>
                      </div>

                      <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                        {endpoint.url}
                      </p>

                      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                        {
                          endpoint
                            .event_types
                            .length
                        }{" "}
                        events · attempts{" "}
                        {
                          endpoint
                            .max_attempts
                        }{" "}
                        · timeout{" "}
                        {
                          endpoint
                            .timeout_seconds
                        }
                        s
                      </p>
                    </div>

                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        disabled={loading}
                        onClick={() =>
                          void handleTest(
                            endpoint
                              .webhook_id,
                          )
                        }
                      >
                        <Send />
                        Test
                      </Button>

                      <Button
                        variant="outline"
                        disabled={loading}
                        onClick={() =>
                          void toggleActive(
                            endpoint,
                          )
                        }
                      >
                        {endpoint.active
                          ? "Disable"
                          : "Enable"}
                      </Button>
                    </div>
                  </div>
                </article>
              ),
            )}
          </div>
        )}
      </section>


      <section className="overflow-hidden rounded-md border border-border bg-card">
        <header className="border-b border-border px-5 py-4">
          <h2 className="font-heading text-lg font-bold">
            Delivery history
          </h2>
        </header>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border font-mono text-muted-foreground">
              <tr>
                <th className="p-3">
                  Endpoint
                </th>
                <th className="p-3">
                  Event
                </th>
                <th className="p-3">
                  Resource
                </th>
                <th className="p-3">
                  Status
                </th>
                <th className="p-3">
                  Attempts
                </th>
                <th className="p-3">
                  HTTP
                </th>
                <th className="p-3">
                  Time
                </th>
              </tr>
            </thead>

            <tbody>
              {deliveries.map(
                (delivery) => (
                  <tr
                    key={
                      delivery.delivery_id
                    }
                    className="border-b border-border last:border-0"
                  >
                    <td className="p-3">
                      {delivery
                        .webhook_name ??
                        delivery
                          .webhook_id}
                    </td>

                    <td className="p-3 font-mono">
                      {
                        delivery
                          .event_type
                      }
                    </td>

                    <td className="p-3 font-mono">
                      {
                        delivery
                          .resource_type
                      }
                    </td>

                    <td className="p-3">
                      <span
                        className={
                          delivery.status ===
                          "succeeded"
                            ? "text-ok"
                            : "text-danger"
                        }
                      >
                        {
                          delivery
                            .status
                        }
                      </span>
                    </td>

                    <td className="p-3">
                      {
                        delivery
                          .attempt_count
                      }
                    </td>

                    <td className="p-3">
                      {delivery
                        .response_status ??
                        "—"}
                    </td>

                    <td className="p-3 font-mono text-[10px]">
                      {new Date(
                        delivery
                          .requested_at,
                      ).toLocaleString()}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}


function FieldLabel({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      {children}
    </span>
  )
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}