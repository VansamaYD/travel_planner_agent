import { type FormEvent, type ReactNode, useEffect, useState } from 'react'

import {
  changeFamilyRole,
  createFamilyMember,
  listFamilyMembers,
  removeFamilyMember,
  type CreateMemberInput,
  type FamilyMember,
  type FamilySummary,
  type SessionData,
  type TravelerProfile,
  updateTravelerProfile,
} from '../../shared/api/access'

interface Props {
  family: FamilySummary
  session: SessionData
}

const roleLabels = { owner: '所有者', admin: '管理员', member: '成员', guest: '访客' }
const memberTypeLabels = { adult: '成人', child: '儿童', senior: '老人', other: '其他' }

const emptyProfile: Omit<TravelerProfile, 'version'> = {
  nickname: '',
  member_type: 'adult',
  birth_year: null,
  discount_eligibilities: [],
  dietary_restrictions: [],
  allergies: [],
  health_notes: '',
  mobility_notes: '',
  travel_preferences: [],
  sensitive_visibility: 'family',
}

const emptyMember: CreateMemberInput = {
  username: '',
  email: '',
  display_name: '',
  password: '',
  role: 'member',
  profile: emptyProfile,
}

export function FamilyMembers({ family, session }: Props) {
  const [members, setMembers] = useState<FamilyMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const canManage = family.role === 'owner' || family.role === 'admin'

  async function refresh(signal?: AbortSignal) {
    setLoading(true)
    try {
      setMembers(await listFamilyMembers(family.id, signal))
      setError('')
    } catch (reason) {
      if (!signal?.aborted) setError(reason instanceof Error ? reason.message : '成员读取失败')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [family.id])

  async function changeRole(member: FamilyMember, role: 'admin' | 'member' | 'guest') {
    try {
      await changeFamilyRole(family.id, member.membership_id, role, session.csrf_token)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '角色修改失败')
    }
  }

  async function remove(member: FamilyMember) {
    if (!window.confirm(`确认将“${member.profile.nickname}”移出当前家庭？历史审计记录会保留。`)) return
    try {
      await removeFamilyMember(family.id, member.membership_id, session.csrf_token)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '移除失败')
    }
  }

  return (
    <section className="panel" aria-labelledby="member-title">
      <div className="section-heading member-heading">
        <span className="section-number">02</span>
        <div>
          <p className="section-kicker">TRAVELER PROFILES</p>
          <h2 id="member-title">家庭成员</h2>
        </div>
        {canManage && (
          <button className="small-button" onClick={() => setCreating((value) => !value)} type="button">
            {creating ? '收起' : '添加成员'}
          </button>
        )}
      </div>

      {creating && <CreateMemberForm familyId={family.id} session={session} onCreated={async () => {
        setCreating(false)
        await refresh()
      }} />}
      {error && <p className="form-error">{error}</p>}
      {loading ? <p className="muted">正在读取成员档案…</p> : (
        <div className="member-list">
          {members.map((member) => {
            const isSelf = member.user_id === session.user.id
            const canEdit = isSelf || canManage
            const canChange = canManage && member.role !== 'owner' && !isSelf
            return (
              <article className="member-card" key={member.membership_id}>
                <div className="member-summary">
                  <div className="member-avatar">{member.profile.nickname.slice(0, 1)}</div>
                  <div>
                    <strong>{member.profile.nickname}</strong>
                    <small>{memberTypeLabels[member.profile.member_type]} · {roleLabels[member.role]}{isSelf ? ' · 我' : ''}</small>
                  </div>
                  {member.profile.sensitive_visibility === 'private' && <span className="privacy-badge">私密</span>}
                </div>
                <div className="profile-tags">
                  {[...member.profile.discount_eligibilities, ...member.profile.dietary_restrictions, ...member.profile.travel_preferences]
                    .slice(0, 5).map((item) => <span key={item}>{item}</span>)}
                  {member.profile.version === 0 && <span>待完善</span>}
                </div>
                <div className="member-actions">
                  {canEdit && <button className="text-button" onClick={() => setEditing(editing === member.membership_id ? null : member.membership_id)} type="button">{editing === member.membership_id ? '取消编辑' : '编辑档案'}</button>}
                  {canChange && (
                    <select aria-label={`修改${member.profile.nickname}的角色`} value={member.role} onChange={(event) => void changeRole(member, event.target.value as 'admin' | 'member' | 'guest')}>
                      {family.role === 'owner' && <option value="admin">管理员</option>}
                      <option value="member">成员</option>
                      <option value="guest">访客</option>
                    </select>
                  )}
                  {canChange && <button className="danger-button" onClick={() => void remove(member)} type="button">移出</button>}
                </div>
                {editing === member.membership_id && (
                  <ProfileForm member={member} familyId={family.id} csrfToken={session.csrf_token} onSaved={async () => {
                    setEditing(null)
                    await refresh()
                  }} />
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

function CreateMemberForm({ familyId, session, onCreated }: { familyId: string; session: SessionData; onCreated: () => Promise<void> }) {
  const [input, setInput] = useState<CreateMemberInput>(emptyMember)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await createFamilyMember(familyId, { ...input, profile: { ...input.profile, nickname: input.profile.nickname || input.display_name } }, session.csrf_token)
      await onCreated()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="member-form" onSubmit={(event) => void submit(event)}>
      <h3>直接创建成员账号</h3>
      <p className="muted">成员稍后可使用此用户名和初始密码登录。</p>
      <div className="field-grid">
        <Field label="显示名称"><input required maxLength={80} value={input.display_name} onChange={(event) => setInput({ ...input, display_name: event.target.value })} /></Field>
        <Field label="用户名"><input required minLength={3} maxLength={64} value={input.username} onChange={(event) => setInput({ ...input, username: event.target.value })} /></Field>
        <Field label="邮箱（可选）"><input type="email" value={input.email} onChange={(event) => setInput({ ...input, email: event.target.value })} /></Field>
        <Field label="初始密码"><input required minLength={10} type="password" value={input.password} onChange={(event) => setInput({ ...input, password: event.target.value })} /></Field>
        <Field label="成员类型"><select value={input.profile.member_type} onChange={(event) => setInput({ ...input, profile: { ...input.profile, member_type: event.target.value as TravelerProfile['member_type'] } })}>{Object.entries(memberTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field label="家庭角色"><select value={input.role} onChange={(event) => setInput({ ...input, role: event.target.value as CreateMemberInput['role'] })}>{session.families.find((item) => item.id === familyId)?.role === 'owner' && <option value="admin">管理员</option>}<option value="member">成员</option><option value="guest">访客</option></select></Field>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button" disabled={saving} type="submit">{saving ? '创建中…' : '创建成员'}</button>
    </form>
  )
}

function ProfileForm({ member, familyId, csrfToken, onSaved }: { member: FamilyMember; familyId: string; csrfToken: string; onSaved: () => Promise<void> }) {
  const [profile, setProfile] = useState(member.profile)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function list(value: string) { return value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) }
  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await updateTravelerProfile(familyId, member.membership_id, profile, csrfToken)
      await onSaved()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="profile-form" onSubmit={(event) => void submit(event)}>
      <div className="field-grid">
        <Field label="旅行昵称"><input required value={profile.nickname} onChange={(event) => setProfile({ ...profile, nickname: event.target.value })} /></Field>
        <Field label="成员类型"><select value={profile.member_type} onChange={(event) => setProfile({ ...profile, member_type: event.target.value as TravelerProfile['member_type'] })}>{Object.entries(memberTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        <Field label="出生年份（可选）"><input inputMode="numeric" min="1900" max={new Date().getFullYear()} type="number" value={profile.birth_year ?? ''} onChange={(event) => setProfile({ ...profile, birth_year: event.target.value ? Number(event.target.value) : null })} /></Field>
        <Field label="优惠资格（逗号分隔）"><input value={profile.discount_eligibilities.join('，')} onChange={(event) => setProfile({ ...profile, discount_eligibilities: list(event.target.value) })} /></Field>
        <Field label="饮食要求（逗号分隔）"><input value={profile.dietary_restrictions.join('，')} onChange={(event) => setProfile({ ...profile, dietary_restrictions: list(event.target.value) })} /></Field>
        <Field label="旅行偏好（逗号分隔）"><input value={profile.travel_preferences.join('，')} onChange={(event) => setProfile({ ...profile, travel_preferences: list(event.target.value) })} /></Field>
        <Field label="过敏信息"><input value={profile.allergies.join('，')} onChange={(event) => setProfile({ ...profile, allergies: list(event.target.value) })} /></Field>
        <Field label="敏感信息可见范围"><select value={profile.sensitive_visibility} onChange={(event) => setProfile({ ...profile, sensitive_visibility: event.target.value as TravelerProfile['sensitive_visibility'] })}><option value="family">家庭可见</option><option value="private">仅本人可见</option></select></Field>
      </div>
      <Field label="健康与作息备注"><textarea rows={3} value={profile.health_notes} onChange={(event) => setProfile({ ...profile, health_notes: event.target.value })} /></Field>
      <Field label="行动能力备注"><textarea rows={3} value={profile.mobility_notes} onChange={(event) => setProfile({ ...profile, mobility_notes: event.target.value })} /></Field>
      {profile.sensitive_visibility === 'private' && !profile.health_notes && <p className="privacy-note">敏感内容可能由成员设为仅本人可见；空白保存不会清除被隐藏的信息。</p>}
      {error && <p className="form-error">{error}</p>}
      <button className="primary-button" disabled={saving} type="submit">{saving ? '保存中…' : '保存档案'}</button>
    </form>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label><span>{label}</span>{children}</label>
}
