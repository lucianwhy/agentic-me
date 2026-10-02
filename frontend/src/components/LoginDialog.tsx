import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { login, type AuthStatus } from '@/lib/api'

/** Invite-code gate; only opened when the backend reports auth_enabled and no session. Not dismissable. */
export function LoginDialog({ open, onSuccess }: { open: boolean; onSuccess: (user: AuthStatus['user']) => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const result = await login(code.trim())
    setBusy(false)
    if (result.success) {
      setError(null)
      onSuccess(result.user)
    } else {
      setError(result.error ?? '邀请码无效')
    }
  }

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        className="sm:max-w-md"
      >
        <DialogHeader className="items-center text-center">
          <DialogTitle className="text-xl font-semibold tracking-tight">需要邀请码</DialogTitle>
          <DialogDescription>请输入邀请码后访问这份智能简历</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            id="invite-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="邀请码"
            maxLength={50}
            pattern="[A-Za-z0-9\-_]+"
            required
            autoComplete="off"
            className="h-10 text-center font-mono"
          />
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            进入
          </Button>
        </form>
        {error && (
          <p className="text-center text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
