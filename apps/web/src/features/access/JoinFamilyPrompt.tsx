import { type FormEvent, useState } from 'react'

import { acceptFamilyInvite, getSession, type SessionData } from '../../shared/api/access'

interface Props {
  session: SessionData
  initialCode: string
  onAccepted: (session: SessionData) => void
}

export function JoinFamilyPrompt({ session, initialCode, onAccepted }: Props) {
  const [code, setCode] = useState(initialCode)
  const [joining, setJoining] = useState(false)
  const [error, setError] = useState('')

  async function join(event: FormEvent) {
    event.preventDefault()
    setJoining(true)
    setError('')
    try {
      await acceptFamilyInvite(code, session.csrf_token)
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
      const refreshed = await getSession()
      if (refreshed) onAccepted(refreshed)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加入家庭失败')
    } finally {
      setJoining(false)
    }
  }

  return (
    <section className="panel join-family" aria-labelledby="join-family-title">
      <p className="section-kicker">JOIN A FAMILY</p>
      <h2 id="join-family-title">接受家庭邀请</h2>
      <p className="muted">确认后，此账号会按邀请角色加入对应家庭。</p>
      <form onSubmit={(event) => void join(event)}>
        <input aria-label="邀请码" required value={code} onChange={(event) => setCode(event.target.value)} />
        <button className="primary-button" disabled={joining} type="submit">{joining ? '正在加入…' : '接受邀请'}</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </section>
  )
}
