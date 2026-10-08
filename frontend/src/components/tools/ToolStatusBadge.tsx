import { STATUS_LABEL, type ToolStatus } from '@/data/tools'
import { cn } from '@/lib/utils'

/** Visible 设计中 / 规划中 marker. Implemented items (no status / 'done') render nothing. */
export function ToolStatusBadge({ status, className }: { status?: ToolStatus; className?: string }) {
  if (!status || status === 'done') return null
  return (
    <span
      data-tool-status={status}
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-1.5 py-px text-[10.5px] leading-4 font-medium whitespace-nowrap text-amber-800',
        className,
      )}
    >
      <span className="size-1.5 rounded-full bg-amber-500" aria-hidden="true" />
      {STATUS_LABEL[status]}
    </span>
  )
}
