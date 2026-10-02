import { Badge } from '@/components/ui/badge'
import type { ProjectStatus } from '@/data/projects'
import { cn } from '@/lib/utils'

export function StatusBadge({ status, className }: { status: ProjectStatus; className?: string }) {
  if (status.tone === 'live') {
    return (
      <Badge variant="outline" className={cn('gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700', className)}>
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
        </span>
        {status.label}
      </Badge>
    )
  }
  if (status.tone === 'open-source') {
    return (
      <Badge variant="outline" className={cn('border-zinc-300 bg-white text-zinc-700', className)}>
        {status.label}
      </Badge>
    )
  }
  return (
    <Badge variant="secondary" className={className}>
      {status.label}
    </Badge>
  )
}
