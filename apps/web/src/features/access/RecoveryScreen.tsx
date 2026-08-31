import { useState } from 'react'

interface RecoveryScreenProps {
  recoveryCode: string
  onContinue: () => void
}

export function RecoveryScreen({ recoveryCode, onContinue }: RecoveryScreenProps) {
  const [confirmed, setConfirmed] = useState(false)

  return (
    <section className="auth-card recovery-card" aria-labelledby="recovery-title">
      <p className="section-kicker">ONE-TIME RECOVERY CODE</p>
      <h2 id="recovery-title">离线保存恢复码</h2>
      <p className="form-intro">
        这是恢复系统管理员权限的唯一离线凭据，只显示这一次。请写入密码管理器或打印保存。
      </p>
      <code className="recovery-code">{recoveryCode}</code>
      <label className="confirmation-row">
        <input
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
          type="checkbox"
        />
        <span>我已经离线保存恢复码</span>
      </label>
      <button className="primary-button" disabled={!confirmed} onClick={onContinue} type="button">
        进入旅行空间
      </button>
    </section>
  )
}
