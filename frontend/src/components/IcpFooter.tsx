import { cn } from '@/lib/utils'

// ICP filing number required by MIIT for sites served from mainland China.
const ICP_NUMBER = '豫ICP备2026014582号-2'
const ICP_URL = 'https://beian.miit.gov.cn/'

export function IcpFooter({ className }: { className?: string }) {
  return (
    <footer className={cn('shrink-0 text-center text-[11px] leading-none text-zinc-400', className)}>
      <a href={ICP_URL} target="_blank" rel="noopener noreferrer" className="hover:text-zinc-600 hover:underline underline-offset-2">
        {ICP_NUMBER}
      </a>
    </footer>
  )
}
