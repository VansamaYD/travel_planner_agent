import { useState, type FormEvent } from 'react'

import { login, type SessionData } from '../../shared/api/access'

interface LoginScreenProps {
  onAuthenticated: (session: SessionData) => void
}

export function LoginScreen({ onAuthenticated }: LoginScreenProps) {
  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      onAuthenticated(await login(loginName, password))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card compact-auth" aria-labelledby="login-title">
      <p className="section-kicker">WELCOME BACK</p>
      <h2 id="login-title">登录旅行空间</h2>
      <p className="form-intro">使用用户名或邮箱登录。账号不存在与密码错误使用相同提示。</p>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>用户名或邮箱</span>
          <input
            autoComplete="username"
            required
            value={loginName}
            onChange={(event) => setLoginName(event.target.value)}
          />
        </label>
        <label>
          <span>密码</span>
          <input
            autoComplete="current-password"
            required
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting} type="submit">
          {submitting ? '正在登录…' : '登录'}
        </button>
      </form>
    </section>
  )
}
