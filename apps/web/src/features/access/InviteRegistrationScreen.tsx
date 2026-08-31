import { type FormEvent, useState } from 'react'

import { registerWithFamilyInvite } from '../../shared/api/access'

interface Props {
  code: string
  onRegistered: (username: string) => void
  onUseExistingAccount: (code: string) => void
}

export function InviteRegistrationScreen({ code, onRegistered, onUseExistingAccount }: Props) {
  const [inviteCode, setInviteCode] = useState(code)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const registeredUsername = await registerWithFamilyInvite({
        code: inviteCode,
        username,
        email,
        display_name: displayName,
        password,
      })
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
      onRegistered(registeredUsername)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '受邀注册失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card compact-auth" aria-labelledby="invite-register-title">
      <p className="section-kicker">FAMILY INVITATION</p>
      <h2 id="invite-register-title">加入旅行家庭</h2>
      <p className="form-intro">邀请码只用于加入指定家庭，不会开放系统公共注册。</p>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>邀请码</span>
          <input required minLength={20} maxLength={64} value={inviteCode} onChange={(event) => setInviteCode(event.target.value.toUpperCase())} />
        </label>
        <label>
          <span>显示名称</span>
          <input required maxLength={80} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>
        <label>
          <span>用户名</span>
          <input autoComplete="username" required minLength={3} maxLength={64} value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          <span>邮箱（可选）</span>
          <input autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          <span>密码</span>
          <input autoComplete="new-password" required minLength={10} type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting} type="submit">{submitting ? '正在创建…' : '创建账号并加入'}</button>
        <button className="text-button" onClick={() => onUseExistingAccount(inviteCode)} type="button">已有账号，先登录</button>
      </form>
    </section>
  )
}
