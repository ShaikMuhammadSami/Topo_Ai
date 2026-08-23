"use client"

import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  Bot,
  LoaderCircle,
  MessageSquarePlus,
  Send,
  User,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"
import {
  createIncidentCopilotSession,
  getIncidentCopilotSession,
  listIncidentCopilotSessions,
  sendIncidentCopilotMessage,
} from "@/lib/topo-api"
import type {
  CopilotMessageView,
  CopilotSessionDetail,
} from "@/lib/topo-types"


const initialQuestions = [
  "Why did this incident happen?",
  "Which services and entities are affected?",
  "Who owns the affected workload?",
  "What should the responder check first?",
  "Has recovery been verified?",
]


export function IncidentCopilot({
  incidentId,
}: {
  incidentId: string
}) {
  const [
    copilotSession,
    setCopilotSession,
  ] = useState<
    CopilotSessionDetail | null
  >(null)

  const [question, setQuestion] =
    useState("")

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  useEffect(() => {
    if (!incidentId) {
      setCopilotSession(null)
      return
    }

    let cancelled = false

    async function loadLatest() {
      setLoading(true)
      setError(null)

      try {
        const sessions =
          await listIncidentCopilotSessions(
            incidentId,
          )

        if (
          cancelled ||
          sessions.length === 0
        ) {
          if (!cancelled) {
            setCopilotSession(null)
          }

          return
        }

        const detail =
          await getIncidentCopilotSession(
            incidentId,
            sessions[0].session_id,
          )

        if (!cancelled) {
          setCopilotSession(detail)
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            errorMessage(requestError),
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadLatest()

    return () => {
      cancelled = true
    }
  }, [incidentId])


  const suggestedQuestions =
    useMemo(() => {
      const assistantMessages =
        copilotSession?.messages.filter(
          (message) =>
            message.role === "assistant",
        ) ?? []

      const latest =
        assistantMessages[
          assistantMessages.length - 1
        ]

      return (
        latest?.suggested_questions
          .length
          ? latest.suggested_questions
          : initialQuestions
      )
    }, [copilotSession])


  async function createSession() {
    const created =
      await createIncidentCopilotSession(
        incidentId,
        {
          provider: "auto",
        },
      )

    setCopilotSession(created)

    return created
  }


  async function handleNewSession() {
    setLoading(true)
    setError(null)

    try {
      await createSession()
      setQuestion("")
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  async function handleAsk(
    suppliedQuestion?: string,
  ) {
    const value = (
      suppliedQuestion ?? question
    ).trim()

    if (!value) {
      return
    }

    setLoading(true)
    setError(null)

    try {
      let activeSession =
        copilotSession

      if (!activeSession) {
        activeSession =
          await createSession()
      }

      const response =
        await sendIncidentCopilotMessage(
          incidentId,
          activeSession.session_id,
          value,
        )

      setCopilotSession(
        (current) => ({
          ...(current ?? activeSession),
          messages: [
            ...(
              current?.messages ??
              activeSession.messages
            ),
            response.user_message,
            response.assistant_message,
          ],
          message_count:
            (
              current?.message_count ??
              activeSession.message_count
            ) + 2,
          updated_at:
            response
              .assistant_message
              .created_at,
        }),
      )

      setQuestion("")
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            incident intelligence
          </p>

          <div className="mt-2 flex items-center gap-2">
            <Bot className="h-5 w-5 text-info" />

            <h3 className="font-heading text-lg font-bold">
              Incident Copilot
            </h3>
          </div>

          {copilotSession && (
            <p className="mt-2 font-mono text-[10px] uppercase text-muted-foreground">
              {copilotSession.provider}
              {copilotSession.model_name
                ? ` · ${copilotSession.model_name}`
                : ""}
              {" · "}
              {copilotSession.message_count}
              {" messages"}
            </p>
          )}
        </div>

        <Button
          variant="outline"
          disabled={loading}
          onClick={() =>
            void handleNewSession()
          }
        >
          <MessageSquarePlus className="h-4 w-4" />

          New chat
        </Button>
      </header>


      {error && (
        <div className="m-5 flex gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="h-5 w-5 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      <div className="max-h-[600px] space-y-4 overflow-y-auto p-5">
        {!copilotSession?.messages
          .length && (
          <div>
            <p className="text-sm text-muted-foreground">
              Ask questions about this
              incident’s RCA, blast radius,
              ownership, recovery and network
              evidence.
            </p>

            <div className="mt-4 flex flex-wrap gap-2">
              {initialQuestions.map(
                (item) => (
                  <button
                    key={item}
                    type="button"
                    disabled={loading}
                    onClick={() =>
                      void handleAsk(item)
                    }
                    className="rounded-md border border-border bg-card px-3 py-2 text-left text-xs hover:bg-muted"
                  >
                    {item}
                  </button>
                ),
              )}
            </div>
          </div>
        )}


        {copilotSession?.messages.map(
          (message) => (
            <CopilotMessage
              key={message.message_id}
              message={message}
            />
          ),
        )}


        {loading && (
          <div className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <LoaderCircle className="h-4 w-4 animate-spin" />

            Analyzing incident evidence…
          </div>
        )}
      </div>


      {copilotSession?.messages
        .length ? (
        <div className="border-t border-border px-5 py-3">
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Suggested questions
          </p>

          <div className="mt-2 flex flex-wrap gap-2">
            {suggestedQuestions.map(
              (item) => (
                <button
                  key={item}
                  type="button"
                  disabled={loading}
                  onClick={() =>
                    void handleAsk(item)
                  }
                  className="rounded-sm border border-border px-2 py-1 text-left text-[11px] text-muted-foreground hover:text-foreground"
                >
                  {item}
                </button>
              ),
            )}
          </div>
        </div>
      ) : null}


      <div className="border-t border-border p-5">
        <div className="flex gap-3">
          <textarea
            value={question}
            onChange={(event) =>
              setQuestion(
                event.target.value,
              )
            }
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey
              ) {
                event.preventDefault()

                void handleAsk()
              }
            }}
            placeholder="Ask about this incident…"
            rows={3}
            disabled={loading}
            className="min-h-[84px] flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm"
          />

          <Button
            disabled={
              loading ||
              !question.trim()
            }
            onClick={() =>
              void handleAsk()
            }
          >
            {loading ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}

            Send
          </Button>
        </div>

        <p className="mt-2 font-mono text-[9px] text-muted-foreground">
          Copilot answers are limited to
          available Topo AI evidence and do
          not execute remediation actions.
        </p>
      </div>
    </section>
  )
}


function CopilotMessage({
  message,
}: {
  message: CopilotMessageView
}) {
  const isAssistant =
    message.role === "assistant"

  return (
    <article
      className={
        isAssistant
          ? (
              "mr-8 rounded-md border "
              + "border-border bg-card p-4"
            )
          : (
              "ml-8 rounded-md border "
              + "border-info/30 bg-info/5 p-4"
            )
      }
    >
      <div className="flex items-center gap-2">
        {isAssistant ? (
          <Bot className="h-4 w-4 text-info" />
        ) : (
          <User className="h-4 w-4" />
        )}

        <p className="font-mono text-[10px] uppercase tracking-widest">
          {isAssistant
            ? "Topo Copilot"
            : "Operator"}
        </p>

        {message.provider && (
          <span className="rounded-sm border border-border px-2 py-0.5 font-mono text-[9px] uppercase text-muted-foreground">
            {message.provider}
          </span>
        )}

        {message.answer_status && (
          <span className="rounded-sm border border-border px-2 py-0.5 font-mono text-[9px] uppercase text-muted-foreground">
            {message.answer_status}
          </span>
        )}
      </div>


      <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
        {message.content}
      </p>


      {message.confidence !== null && (
        <p className="mt-3 font-mono text-[10px] text-muted-foreground">
          Generated answer self-score: {message.confidence.toFixed(2)} (uncalibrated)
        </p>
      )}


      {message.evidence_ids.length >
        0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {message.evidence_ids.map(
            (evidenceId) => (
              <span
                key={evidenceId}
                title={evidenceId}
                className="max-w-[260px] truncate rounded-sm border border-border px-2 py-1 font-mono text-[9px] text-muted-foreground"
              >
                {evidenceId}
              </span>
            ),
          )}
        </div>
      )}


      {message.warning && (
        <div className="mt-3 rounded-sm border border-warn/40 bg-warn/10 p-2 font-mono text-[10px] text-warn">
          {message.warning}
        </div>
      )}
    </article>
  )
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : (
        "Unable to process the "
        + "copilot request."
      )
}
