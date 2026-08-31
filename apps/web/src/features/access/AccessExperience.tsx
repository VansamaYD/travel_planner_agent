import { useEffect, useState } from 'react'

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

  if (state.kind === 'loading') return <div className="loading-card">正在读取本地旅行空间…</div>
  if (state.kind === 'error') return <div className="form-error panel">{state.message}</div>
  if (state.kind === 'setup') {
    return (
      <SetupScreen
        onInitialized={(recoveryCode, session) => setState({ kind: 'recovery', recoveryCode, session })}
      />
    )
  }
  if (state.kind === 'login') {
    return <LoginScreen initialLogin={state.initialLogin} onAuthenticated={(session) => setState({ kind: 'authenticated', session })} onUseInvite={() => setState({ kind: 'invite', code: '' })} />
  }
  if (state.kind === 'invite') {
    return <InviteRegistrationScreen code={state.code} onRegistered={(username) => setState({ kind: 'login', initialLogin: username })} onUseExistingAccount={(code) => {
      if (code) window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#invite=${code}`)
      setState({ kind: 'login' })
    }} />
  }
  if (state.kind === 'recovery') {
    return (
      <RecoveryScreen
        recoveryCode={state.recoveryCode}
        onContinue={() => setState({ kind: 'authenticated', session: state.session })}
      />
    )
  }
  return <Dashboard session={state.session} onLoggedOut={() => setState({ kind: 'login' })} onSessionChanged={(session) => setState({ kind: 'authenticated', session })} />
}

function inviteCodeFromHash(): string {
  const match = window.location.hash.match(/^#invite=([A-Z2-7-]{20,64})$/i)
  return match?.[1] ?? ''
}
