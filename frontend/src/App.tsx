import { useCallback, useEffect, useState } from 'react'

import { ChatPanel } from '@/components/ChatPanel'
import { JobMatchPanel } from '@/components/JobMatchPanel'
import { LoginDialog } from '@/components/LoginDialog'
import { ProfileSidebar } from '@/components/ProfileSidebar'
import { ProjectsPanel } from '@/components/projects/ProjectsPanel'
import { SummaryPanel } from '@/components/SummaryPanel'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { getAuthStatus, getModels, getProfile, logout, type AuthStatus, type Profile } from '@/lib/api'
import { pickModel, readStoredModel, storeModel, toOptions, type ModelOption } from '@/lib/models'

type Auth = { enabled: boolean; authenticated: boolean; user: AuthStatus['user'] }

// Panels stay mounted (forceMount) so chat history / results survive tab switches.
const PANEL = 'mt-0 min-h-0 flex-col data-[state=active]:flex data-[state=inactive]:hidden'
// Four equal-width triggers fit a 390px screen (compact padding); natural width from sm up.
const TAB = 'min-w-0 px-1.5 text-[13px] sm:flex-none sm:px-4 sm:text-sm'

export default function App() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [auth, setAuth] = useState<Auth>({ enabled: false, authenticated: false, user: null })
  const [loginOpen, setLoginOpen] = useState(false)
  // '' until GET /models answers; the server then uses its default model.
  const [model, setModel] = useState<string>(() => readStoredModel() ?? '')
  const [models, setModels] = useState<ModelOption[] | null>(null)
  const [tab, setTab] = useState('chat')

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p)
        document.title = `${p.name} · 智能简历`
      })
      .catch((e: unknown) => setProfileError(e instanceof Error ? e.message : '加载失败'))

    getAuthStatus()
      .then((s) => {
        if (s.auth_enabled === false) {
          setAuth({ enabled: false, authenticated: false, user: s.user ?? null })
        } else if (s.authenticated) {
          setAuth({ enabled: true, authenticated: true, user: s.user ?? null })
        } else {
          setAuth({ enabled: true, authenticated: false, user: null })
          setLoginOpen(true)
        }
      })
      .catch((error) => console.error('Authentication check failed:', error))

    // The model list is managed in /admin; re-read it when the tab regains focus so
    // admin changes show up without a reload.
    const loadModels = () =>
      getModels().then((data) => {
        if (!data) {
          setModels((prev) => prev ?? [])
          return
        }
        setModels(toOptions(data))
        setModel((current) => storeModel(pickModel(current || readStoredModel(), data)))
      })
    loadModels()
    const onVisible = () => document.visibilityState === 'visible' && loadModels()
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  const ensureAuth = useCallback(() => {
    if (!auth.enabled || auth.authenticated) return true
    setLoginOpen(true)
    return false
  }, [auth])

  const onAuthRequired = useCallback(() => {
    setAuth((a) => ({ ...a, enabled: true, authenticated: false }))
    setLoginOpen(true)
  }, [])

  // Radix's hidden native <select> can report '' while options are still loading.
  const onModelChange = (value: string) => {
    if (value) setModel(storeModel(value))
  }

  const onLogout = async () => {
    try {
      await logout()
      setAuth({ enabled: true, authenticated: false, user: null })
      setLoginOpen(true)
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  if (profileError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6 text-sm text-zinc-500" role="alert">
        {profileError}
      </div>
    )
  }
  if (!profile) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-zinc-400">加载中…</div>
  }

  return (
    <TooltipProvider delayDuration={300}>
      <LoginDialog
        open={loginOpen}
        onSuccess={(user) => {
          setAuth({ enabled: true, authenticated: true, user: user ?? null })
          setLoginOpen(false)
        }}
      />

      <div className="mx-auto flex h-[100dvh] max-w-[1440px] flex-col lg:h-auto lg:min-h-screen lg:flex-row lg:items-start lg:gap-4 lg:p-4">
        <ProfileSidebar profile={profile} />

        <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 p-3 sm:p-4 lg:sticky lg:top-4 lg:h-[calc(100vh-2rem)] lg:p-0">
          {auth.enabled && auth.authenticated && (
            <div className="flex shrink-0 items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-2.5 shadow-sm">
              <span className="text-sm font-medium">欢迎，{auth.user?.company ?? 'Unknown'}</span>
              <Button variant="ghost" size="sm" className="text-zinc-500 hover:text-red-600" onClick={onLogout}>
                退出
              </Button>
            </div>
          )}

          <Tabs value={tab} onValueChange={setTab} className="min-h-0 flex-1 gap-3">
            <TabsList className="w-full shrink-0 sm:w-fit" aria-label="功能">
              <TabsTrigger value="chat" className={TAB}>对话</TabsTrigger>
              <TabsTrigger value="summary" className={TAB}>一键摘要</TabsTrigger>
              <TabsTrigger value="job" className={TAB}>岗位匹配</TabsTrigger>
              <TabsTrigger value="projects" className={TAB}>我的项目</TabsTrigger>
            </TabsList>
            <TabsContent value="chat" forceMount className={PANEL}>
              <ChatPanel
                profile={profile}
                model={model}
                models={models}
                onModelChange={onModelChange}
                ensureAuth={ensureAuth}
                onAuthRequired={onAuthRequired}
              />
            </TabsContent>
            <TabsContent value="summary" forceMount className={PANEL}>
              <SummaryPanel ensureAuth={ensureAuth} />
            </TabsContent>
            <TabsContent value="job" forceMount className={PANEL}>
              <JobMatchPanel profile={profile} ensureAuth={ensureAuth} />
            </TabsContent>
            <TabsContent value="projects" forceMount className={PANEL}>
              <ProjectsPanel model={model} ensureAuth={ensureAuth} onAuthRequired={onAuthRequired} />
            </TabsContent>
          </Tabs>
        </main>
      </div>
    </TooltipProvider>
  )
}
