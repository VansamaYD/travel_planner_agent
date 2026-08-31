import { useState, type FormEvent } from 'react'

import { initializeSystem, type InitializeInput, type SessionData } from '../../shared/api/access'

interface SetupScreenProps {
  onInitialized: (recoveryCode: string, session: SessionData) => void
}

const initialForm: InitializeInput = {
  username: '',
  email: '',
  display_name: '',
  password: '',
  family_name: '',
}

export function SetupScreen({ onInitialized }: SetupScreenProps) {
  const [form, setForm] = useState(initialForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const result = await initializeSystem(form)
      onInitialized(result.recoveryCode, result.session)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '初始化失败')
    } finally {
      setSubmitting(false)
    }
  }

  function update(field: keyof InitializeInput, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return (
    <section className="auth-card" aria-labelledby="setup-title">
      <p className="section-kicker">FIRST RUN · SECURE SETUP</p>
      <h2 id="setup-title">建立你的旅行空间</h2>
      <p className="form-intro">创建首位系统管理员和默认家庭。公开注册默认保持关闭。</p>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label>
          <span>用户名</span>
          <input
            autoComplete="username"
            minLength={3}
            maxLength={64}
            required
            value={form.username}
            onChange={(event) => update('username', event.target.value)}
            placeholder="例如：vansama"
          />
        </label>
        <label>
          <span>显示名称</span>
          <input
            autoComplete="name"
            maxLength={80}
            required
            value={form.display_name}
            onChange={(event) => update('display_name', event.target.value)}
            placeholder="在家庭中显示的名称"
          />
        </label>
        <label>
          <span>邮箱（可选）</span>
          <input
            autoComplete="email"
            inputMode="email"
            type="email"
            value={form.email}
            onChange={(event) => update('email', event.target.value)}
            placeholder="用于登录和后续找回"
          />
        </label>
        <label>
          <span>家庭名称</span>
          <input
            maxLength={80}
            required
            value={form.family_name}
            onChange={(event) => update('family_name', event.target.value)}
            placeholder="例如：我们的旅行家庭"
          />
        </label>
        <label>
          <span>管理员密码</span>
          <input
            autoComplete="new-password"
            minLength={10}
            maxLength={256}
            required
            type="password"
            value={form.password}
            onChange={(event) => update('password', event.target.value)}
            placeholder="至少 10 个字符"
          />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button" disabled={submitting} type="submit">
          {submitting ? '正在安全初始化…' : '创建管理员并继续'}
        </button>
      </form>
    </section>
  )
}
