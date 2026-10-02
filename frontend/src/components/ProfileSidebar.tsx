import { useState } from 'react'
import { ChevronDown, Download } from 'lucide-react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import type { Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

const EXTERNAL = new Set(['github', 'linkedin', 'scholar'])

function SkillBadges({ skills, className }: { skills: string[]; className?: string }) {
  if (!skills.length) return null
  return (
    <ul className={cn('flex flex-wrap gap-1.5', className)} aria-label="核心技能" data-skills>
      {skills.map((s) => (
        <li key={s}>
          <Badge variant="secondary" className="rounded-md border border-zinc-200 bg-zinc-50 font-medium text-zinc-700">
            {s}
          </Badge>
        </li>
      ))}
    </ul>
  )
}

/** Left column: sticky full-height card on lg+, compact top bar with a contact toggle below lg. */
export function ProfileSidebar({ profile }: { profile: Profile }) {
  const [open, setOpen] = useState(false)

  return (
    <aside className="shrink-0 lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)] lg:w-[320px]">
      <div className="flex flex-col border-b border-zinc-200 bg-white lg:h-full lg:overflow-y-auto lg:rounded-xl lg:border lg:shadow-sm">
        <div className="flex items-center gap-3 px-4 py-3 lg:flex-col lg:items-start lg:gap-0 lg:p-6 lg:pb-0">
          <Avatar className="size-10 ring-1 ring-zinc-200 lg:size-20 lg:ring-offset-2">
            <AvatarImage src={profile.avatar_url} alt={profile.name} />
            <AvatarFallback>{profile.name.slice(0, 1)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1 lg:mt-4">
            <h1 className="truncate text-base font-semibold tracking-tight lg:text-xl lg:whitespace-normal">{profile.name}</h1>
            {profile.headline && (
              <p className="truncate text-xs text-zinc-500 lg:mt-1 lg:text-sm lg:leading-snug lg:whitespace-normal">{profile.headline}</p>
            )}
            <SkillBadges skills={profile.skills ?? []} className="mt-3 hidden lg:flex" />
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-xs lg:hidden"
            aria-expanded={open}
            aria-controls="profile-details"
            onClick={() => setOpen((v) => !v)}
          >
            联系方式 / 简历
            <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden="true" />
          </Button>
        </div>

        <div
          id="profile-details"
          className={cn(
            'max-h-[60dvh] flex-col gap-4 overflow-y-auto px-4 pb-4 lg:flex lg:max-h-none lg:flex-1 lg:overflow-visible lg:p-6 lg:pt-5',
            open ? 'flex' : 'hidden',
          )}
        >
          <SkillBadges skills={profile.skills ?? []} className="lg:hidden" />
          <nav className="flex flex-col gap-2 text-sm text-zinc-600" aria-label="联系方式">
            {profile.contacts.map((c) => (
              <div key={c.type} className="flex gap-2 break-all">
                <span className="w-14 shrink-0 text-zinc-400">{c.label}</span>
                <a
                  href={c.href}
                  className="min-w-0 text-zinc-900 underline-offset-4 hover:underline"
                  {...(EXTERNAL.has(c.type) ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                >
                  {c.value}
                </a>
              </div>
            ))}
          </nav>

          <Button asChild className="w-full">
            <a href={profile.cv_url} download={profile.cv_download_name}>
              <Download aria-hidden="true" />
              下载简历 PDF
            </a>
          </Button>

          <Separator />

          <div className="space-y-1.5">
            <p className="text-sm font-semibold tracking-tight">{profile.intro_title}</p>
            <p className="text-sm leading-relaxed text-zinc-500">{profile.intro}</p>
          </div>
          <p className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-500">{profile.disclaimer}</p>
        </div>
      </div>
    </aside>
  )
}
