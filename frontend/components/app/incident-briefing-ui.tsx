import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { humanizeToken } from "@/lib/incident-briefing"

export function SectionHeading({
  icon: Icon,
  eyebrow,
  title,
}: {
  icon: LucideIcon
  eyebrow: string
  title: string
}) {
  return (
    <div>
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        <Icon className="h-3.5 w-3.5 text-info" />
        {eyebrow}
      </div>
      <h2 className="mt-1 font-heading text-xl font-bold">
        {title}
      </h2>
    </div>
  )
}

export function Eyebrow({
  icon: Icon,
  children,
}: {
  icon: LucideIcon
  children: string
}) {
  return (
    <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      <Icon className="h-3.5 w-3.5 text-info" />
      {children}
    </p>
  )
}

export function ImmediateDatum({
  id,
  icon: Icon,
  label,
  value,
  emphasize = false,
}: {
  id?: string
  icon: LucideIcon
  label: string
  value: string
  emphasize?: boolean
}) {
  return (
    <div
      id={id}
      className="border-b border-border p-4 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
    >
      <p className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </p>
      <p
        className={cn(
          "mt-2 text-sm font-semibold",
          emphasize && "text-primary",
        )}
      >
        {value}
      </p>
    </div>
  )
}

export function StatusBadge({
  value,
  tone,
}: {
  value: string
  tone: "danger" | "warn" | "ok" | "info"
}) {
  const styles = {
    danger: "border-danger/35 bg-danger/10 text-danger",
    warn: "border-warn/35 bg-warn/10 text-warn",
    ok: "border-ok/35 bg-ok/10 text-ok",
    info: "border-info/35 bg-info/10 text-info",
  }

  return (
    <span
      className={cn(
        "inline-flex rounded-sm border px-2 py-1 font-mono text-[9px] uppercase tracking-wide",
        styles[tone],
      )}
    >
      {humanizeToken(value)}
    </span>
  )
}

export function Metric({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="bg-card p-4 text-center">
      <p className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-heading text-xl font-bold">
        {value}
      </p>
    </div>
  )
}

export function Datum({
  label,
  value,
  link = false,
}: {
  label: string
  value: string | null | undefined
  link?: boolean
}) {
  return (
    <div>
      <dt className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-semibold">
        {!value ? (
          <span className="font-normal text-muted-foreground">Not available</span>
        ) : link ? (
          <a
            href={value}
            target="_blank"
            rel="noreferrer"
            className="text-info hover:underline"
          >
            {value}
          </a>
        ) : (
          value
        )}
      </dd>
    </div>
  )
}

export function PreviewDatum({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div>
      <p className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xs leading-relaxed">
        {value}
      </p>
    </div>
  )
}

export function BusinessDatum({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <div className="border-b border-border p-5 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <p className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 font-heading text-lg font-bold">
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {detail}
      </p>
    </div>
  )
}

export function BulletList({
  title,
  items,
  empty,
}: {
  title: string
  items: string[]
  empty: string
}) {
  return (
    <div>
      <p className="font-mono text-[9px] uppercase tracking-widest text-foreground">
        {title}
      </p>
      <ul className="mt-2 space-y-1.5">
        {items.length === 0 ? (
          <li>{empty}</li>
        ) : items.map((item) => (
          <li key={item}>• {item}</li>
        ))}
      </ul>
    </div>
  )
}

export function DegradedState({
  icon: Icon,
  text,
}: {
  icon: LucideIcon
  text: string
}) {
  return (
    <div className="mt-5 flex items-start gap-3 rounded-sm border border-dashed border-border bg-background/50 p-4 text-muted-foreground">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="text-xs leading-relaxed">{text}</p>
    </div>
  )
}

export function riskTone(
  risk: "low" | "medium" | "high",
): "danger" | "warn" | "ok" {
  if (risk === "high") {
    return "danger"
  }

  return risk === "medium" ? "warn" : "ok"
}
