import { cn } from "@/lib/utils"

export function TopoLogo({
  className,
  version,
}: {
  className?: string
  version?: string
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-primary font-heading text-base font-black leading-none text-primary-foreground">
        t
      </span>
      <span className="font-heading text-lg font-extrabold tracking-tight">
        topo<span className="text-warn"> ai</span>
      </span>
      {version ? (
        <span className="font-mono text-[10px] text-muted-foreground">{version}</span>
      ) : null}
    </div>
  )
}
