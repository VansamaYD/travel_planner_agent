import { useEffect, useState, type ReactNode } from 'react'

import { getSession, getSetupStatus, type SessionData } from '../../shared/api/access'
import { Dashboard } from './Dashboard'
import { LoginScreen } from './LoginScreen'
import { InviteRegistrationScreen } from './InviteRegistrationScreen'
import { RecoveryScreen } from './RecoveryScreen'
import { SetupScreen } from './SetupScreen'

type AccessState =
  | { kind: 'loading' }
  | { kind: 'setup' }
  | { kind: 'login'; initialLogin?: string }
  | { kind: 'invite'; code: string }
  | { kind: 'recovery'; recoveryCode: string; session: SessionData }
  | { kind: 'authenticated'; session: SessionData }
  | { kind: 'error'; message: string }

export function AccessExperience() {
  const [state, setState] = useState<AccessState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void getSetupStatus(controller.signal)
      .then(async (initialized) => {
        if (!initialized) return setState({ kind: 'setup' })
        const session = await getSession(controller.signal)
        const inviteCode = inviteCodeFromHash()
        setState(session ? { kind: 'authenticated', session } : inviteCode ? { kind: 'invite', code: inviteCode } : { kind: 'login' })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ kind: 'error', message: error instanceof Error ? error.message : '服务不可用' })
        }
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') return <PublicFrame><div className="loading-card">正在读取本地旅行空间…</div></PublicFrame>
  if (state.kind === 'error') return <PublicFrame><div className="form-error panel">{state.message}</div></PublicFrame>
  if (state.kind === 'setup') {
    return <PublicFrame>{(
      <SetupScreen
        onInitialized={(recoveryCode, session) => setState({ kind: 'recovery', recoveryCode, session })}
      />
    )}</PublicFrame>
  }
  if (state.kind === 'login') {
    return <PublicFrame><LoginScreen initialLogin={state.initialLogin} onAuthenticated={(session) => setState({ kind: 'authenticated', session })} onUseInvite={() => setState({ kind: 'invite', code: '' })} /></PublicFrame>
  }
  if (state.kind === 'invite') {
    return <PublicFrame><InviteRegistrationScreen code={state.code} onRegistered={(username) => setState({ kind: 'login', initialLogin: username })} onUseExistingAccount={(code) => {
      if (code) window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#invite=${code}`)
      setState({ kind: 'login' })
    }} /></PublicFrame>
  }
  if (state.kind === 'recovery') {
    return <PublicFrame>{(
      <RecoveryScreen
        recoveryCode={state.recoveryCode}
        onContinue={() => setState({ kind: 'authenticated', session: state.session })}
      />
    )}</PublicFrame>
  }
  return <Dashboard session={state.session} onLoggedOut={() => setState({ kind: 'login' })} onSessionChanged={(session) => setState({ kind: 'authenticated', session })} />
}

function PublicFrame({ children }: { children: ReactNode }) {
  return <main className="app-shell"><header className="hero"><p className="eyebrow">SELF-HOSTED · PRIVATE BY DEFAULT</p><h1>旅行规划助手</h1><p className="hero-copy">为个人与家庭准备的自主部署旅行空间。账号、家庭和每次修改都留在你的系统中。</p></header>{children}</main>
}

function inviteCodeFromHash(): string {
  const match = window.location.hash.match(/^#invite=([A-Z2-7-]{20,64})$/i)
  return match?.[1] ?? ''
}
