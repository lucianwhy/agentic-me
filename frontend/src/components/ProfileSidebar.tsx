import { useState } from 'react'
import { ChevronDown, Download } from 'lucide-react'

import { ResumeSections } from '@/components/ResumeSections'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import type { Profile } from '@/lib/api'
import { cn } from '@/lib/utils'
import { IcpFooter } from '@/components/IcpFooter'

const EXTERNAL = new Set(['github', 'linkedin', 'scholar'])

type Props = {
  profile: Profile
  /** Prefill the chat input with a preset question (switches to the 对话 tab). */
  onAsk: (question: string) => void
}

/**
 * Left column. lg+: sticky full-height card — basic info (name, contacts, PDF) is pinned at the
 * top and the structured resume scrolls underneath it. Below lg: compact top bar whose 简历
 * toggle opens a drawer with contacts, PDF and the same resume entries.
 */
export function ProfileSidebar({ profile, onAsk }: Props) {
  const [open, setOpen] = useState(false)
  const resume = profile.resume

  const ask = (question: string) => {
    setOpen(false) // mobile: close the drawer so the chat input is visible
    onAsk(question)
  }

  return (
    <aside className="relative z-10 shrink-0 lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)] lg:w-[340px] xl:w-[360px]">
      <div className="flex flex-col border-b border-zinc-200 bg-white lg:h-full lg:overflow-hidden lg:rounded-xl lg:border lg:shadow-sm">
        <div className="flex items-center gap-3 px-4 py-3 lg:px-5 lg:pt-5 lg:pb-0">
          <Avatar className="size-10 ring-1 ring-zinc-200 lg:size-14 lg:ring-offset-2">
            <AvatarImage src={profile.avatar_url} alt={profile.name} />
            <AvatarFallback>{profile.name.slice(0, 1)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold tracking-tight lg:text-xl">{profile.name}</h1>
            {profile.headline && <p className="truncate text-xs text-zinc-500 lg:mt-0.5 lg:text-sm">{profile.headline}</p>}
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
            简历
            <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden="true" />
          </Button>
        </div>

        <div
          id="profile-details"
          className={cn(
            // Mobile drawer: one scroll container. lg: fixed basic info + independently scrolling resume.
            'max-h-[72dvh] flex-col overflow-y-auto overscroll-contain border-t border-zinc-100 lg:flex lg:max-h-none lg:min-h-0 lg:flex-1 lg:overflow-hidden lg:border-t-0',
            open ? 'flex' : 'hidden',
          )}
        >
          <div className="flex shrink-0 flex-col gap-3 px-4 pt-3 pb-4 lg:px-5 lg:pt-4" data-basic-info>
            <nav className="flex flex-col gap-1.5 text-[13px] text-zinc-600" aria-label="联系方式">
              {profile.contacts.map((c) => (
                <div key={c.type} className="flex gap-2 break-all">
                  <span className="w-12 shrink-0 text-zinc-400">{c.label}</span>
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
            <Button asChild size="sm" className="w-full">
              <a href={profile.cv_url} download={profile.cv_download_name}>
                <Download aria-hidden="true" />
                下载简历 PDF
              </a>
            </Button>
          </div>

          <div className="border-t border-zinc-200 bg-zinc-50/60 px-4 py-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain lg:px-5 lg:[scrollbar-width:thin]">
            {resume && <ResumeSections resume={resume} onAsk={ask} />}
            <p className="mt-5 text-[11px] leading-relaxed text-zinc-400">{profile.disclaimer}</p>
          </div>
        </div>
        {/* Desktop: pinned to the bottom of the left column. Mobile renders it at the page bottom (App). */}
        <IcpFooter className="hidden border-t border-zinc-100 py-2.5 lg:block" />
      </div>
    </aside>
  )
}
