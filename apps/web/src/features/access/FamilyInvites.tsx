import { type FormEvent, useEffect, useState } from 'react'

import {
  createFamilyInvite,
  type FamilyInvite,
  type FamilySummary,
  listFamilyInvites,
  revokeFamilyInvite,
  type SessionData,
} from '../../shared/api/access'

interface Props {
  family: FamilySummary
  session: SessionData
}

const roleLabels = { admin: '管理员', member: '成员', guest: '访客' }
const statusLabels = { active: '待使用', accepted: '已接受', revoked: '已撤销', expired: '已过期' }

export function FamilyInvites({ family, session }: Props) {
  const [invites, setInvites] = useState<FamilyInvite[]>([])
  const [role, setRole] = useState<'admin' | 'member' | 'guest'>('member')
  const [days, setDays] = useState(7)
  const [latestLink, setLatestLink] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function refresh(signal?: AbortSignal) {
    try {
      setInvites(await listFamilyInvites(family.id, signal))
      setError('')
    } catch (reason) {
      if (!signal?.aborted) setError(reason instanceof Error ? reason.message : '邀请读取失败')
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [family.id])

  async function create(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setCopied(false)
    try {
      const issue = await createFamilyInvite(family.id, role, days, session.csrf_token)
      setLatestLink(`${window.location.origin}/#invite=${issue.code}`)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '邀请创建失败')
    } finally {
      setSaving(false)
    }
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(latestLink)
      setCopied(true)
    } catch {
      setError('无法自动复制，请长按选择下方链接。')
    }
  }

  async function revoke(inviteId: string) {
    try {
      await revokeFamilyInvite(family.id, inviteId, session.csrf_token)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '撤销失败')
    }
  }

  return (
    <section className="panel" aria-labelledby="invite-title">
      <div className="section-heading">
        <span className="section-number">03</span>
        <div>
          <p className="section-kicker">FAMILY INVITATIONS</p>
          <h2 id="invite-title">邀请加入家庭</h2>
        </div>
      </div>
      <form className="invite-form" onSubmit={(event) => void create(event)}>
        <label><span>加入后的角色</span><select value={role} onChange={(event) => setRole(event.target.value as typeof role)}>{family.role === 'owner' && <option value="admin">管理员</option>}<option value="member">成员</option><option value="guest">访客</option></select></label>
        <label><span>有效期</span><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={1}>1 天</option><option value={3}>3 天</option><option value={7}>7 天</option><option value={14}>14 天</option><option value={30}>30 天</option></select></label>
        <button className="primary-button" disabled={saving} type="submit">{saving ? '生成中…' : '生成单次邀请'}</button>
      </form>
      {latestLink && (
        <div className="invite-link-box">
          <p>链接只显示在本次页面，请发送给指定成员。</p>
          <code>{latestLink}</code>
          <button className="small-button" onClick={() => void copyLink()} type="button">{copied ? '已复制' : '复制邀请链接'}</button>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}
      <ul className="invite-list">
        {invites.map((invite) => (
          <li key={invite.id}>
            <div><strong>{roleLabels[invite.role]}邀请</strong><small>{statusLabels[invite.status]} · {new Date(invite.expires_at).toLocaleDateString('zh-CN')} 到期</small></div>
            {invite.status === 'active' && <button className="danger-button" onClick={() => void revoke(invite.id)} type="button">撤销</button>}
          </li>
        ))}
      </ul>
    </section>
  )
}
