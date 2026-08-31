import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { listFamilyMembers, type FamilyMember, type FamilySummary, type SessionData } from '../../shared/api/access'
import {
  createTrip,
  deleteTrip,
  getTrip,
  listDeletedTrips,
  listTrips,
  listTripVersions,
  memberIds,
  restoreTrip,
  updateTrip,
  type Trip,
  type TripListItem,
  type TripMutation,
  type TripRequirements,
  type TripVersion,
} from '../../shared/api/trips'
import { ItineraryEditor } from './ItineraryEditor'

interface Props { family: FamilySummary; session: SessionData }

const styleOptions = ['家庭', '亲子', '情侣', '朋友', '独自', '自驾', '休闲', '紧凑', '美食', '摄影']
const transportOptions = ['飞机', '高铁动车火车', '自驾', '网约车出租车', '地铁公交线路', '步行', '轮渡']

function blankRequirements(): TripRequirements {
  return {
    input_mode: 'form', origin: '', destinations: [], start_date: null, end_date: null,
    budget_cents: null, currency: 'CNY', styles: ['休闲'], pace: 'balanced',
    transportation: ['高铁动车火车', '地铁公交线路', '步行'], hard_constraints: [],
    soft_preferences: [], assumptions: [], source_text: '', confirmed: false,
  }
}

function lines(value: string): string[] {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
}

export function TripsWorkspace({ family, session }: Props) {
  const [items, setItems] = useState<TripListItem[]>([])
  const [deletedItems, setDeletedItems] = useState<TripListItem[]>([])
  const [members, setMembers] = useState<FamilyMember[]>([])
  const [selected, setSelected] = useState<Trip | null>(null)
  const [versions, setVersions] = useState<TripVersion[]>([])
  const [showForm, setShowForm] = useState(false)
  const [showDeleted, setShowDeleted] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [visibility, setVisibility] = useState<'private' | 'family'>('private')
  const [requirements, setRequirements] = useState(blankRequirements)
  const [selectedMembers, setSelectedMembers] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const deletedRequest = family.role === 'guest'
      ? Promise.resolve([] as TripListItem[])
      : listDeletedTrips(family.id, controller.signal)
    Promise.all([
      listTrips(family.id, controller.signal),
      listFamilyMembers(family.id, controller.signal),
      deletedRequest,
    ])
      .then(([trips, familyMembers, deleted]) => {
        setItems(trips); setMembers(familyMembers); setDeletedItems(deleted)
      })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message) })
    setSelected(null); setShowForm(false); setError('')
    return () => controller.abort()
  }, [family.id, family.role])

  const totalBudget = useMemo(
    () => requirements.budget_cents === null ? '' : String(requirements.budget_cents / 100),
    [requirements.budget_cents],
  )

  function beginCreate() {
    setSelected(null); setTitle(''); setVisibility('private'); setRequirements(blankRequirements())
    const self = members.find((member) => member.user_id === session.user.id)
    setSelectedMembers(self ? [self.membership_id] : []); setShowForm(true); setVersions([]); setError('')
  }

  async function openTrip(id: string) {
    setError('')
    try {
      const [trip, history] = await Promise.all([getTrip(id), listTripVersions(id)])
      setSelected(trip); setTitle(trip.title); setVisibility(trip.visibility)
      setRequirements(trip.requirements); setSelectedMembers(memberIds(trip, members))
      setVersions(history); setShowForm(false)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '旅行加载失败') }
  }

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const mutation: TripMutation = { title, visibility, requirements, membership_ids: selectedMembers }
      const trip = selected
        ? await updateTrip(selected.id, selected.version, mutation, session.csrf_token)
        : await createTrip(family.id, mutation, session.csrf_token)
      const [nextItems, history] = await Promise.all([listTrips(family.id), listTripVersions(trip.id)])
      setItems(nextItems); setSelected(trip); setVersions(history); setShowForm(false)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败') }
    finally { setSaving(false) }
  }

  async function removeTrip(tripId: string) {
    setSaving(true); setError('')
    try {
      await deleteTrip(tripId, session.csrf_token)
      const [nextItems, deleted] = await Promise.all([
        listTrips(family.id), listDeletedTrips(family.id),
      ])
      setItems(nextItems); setDeletedItems(deleted); setSelected(null)
      setShowForm(false); setDeleteConfirmId(null)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '删除失败') }
    finally { setSaving(false) }
  }

  async function recoverTrip(tripId: string) {
    setSaving(true); setError('')
    try {
      await restoreTrip(tripId, session.csrf_token)
      const [nextItems, deleted] = await Promise.all([
        listTrips(family.id), listDeletedTrips(family.id),
      ])
      setItems(nextItems); setDeletedItems(deleted)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '恢复失败') }
    finally { setSaving(false) }
  }

  function setTextList(key: 'destinations' | 'hard_constraints' | 'soft_preferences' | 'assumptions', value: string) {
    setRequirements((current) => ({ ...current, [key]: lines(value) }))
  }

  function toggleList(key: 'styles' | 'transportation', value: string) {
    setRequirements((current) => ({
      ...current,
      [key]: current[key].includes(value) ? current[key].filter((item) => item !== value) : [...current[key], value],
    }))
  }

  return (
    <section className="panel trips-panel" aria-labelledby="trips-title">
      <div className="section-heading member-heading">
        <span className="section-number">04</span>
        <div><p className="section-kicker">TRIP DRAFTS</p><h2 id="trips-title">旅行计划</h2></div>
        {family.role !== 'guest' && (
          <button className="small-button" onClick={showForm ? () => setShowForm(false) : beginCreate} type="button">
            {showForm ? '收起' : '新建旅行'}
          </button>
        )}
      </div>

      {family.role !== 'guest' && (
        <button className="recycle-toggle" onClick={() => setShowDeleted((value) => !value)} type="button">
          {showDeleted ? '返回当前旅行' : `回收站${deletedItems.length ? `（${deletedItems.length}）` : ''}`}
        </button>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      {showForm && (
        <form className="trip-form" onSubmit={(event) => void save(event)}>
          <div className="trip-form-heading"><strong>{selected ? `编辑 v${selected.version}` : '新旅行草稿'}</strong><span>所有保存都会形成历史版本</span></div>
          <div className="field-grid">
            <label><span>旅行名称 *</span><input required maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
            <label><span>可见范围</span><select value={visibility} onChange={(e) => setVisibility(e.target.value as 'private' | 'family')}><option value="private">仅自己</option><option value="family">家庭可见</option></select></label>
            <label><span>出发地</span><input value={requirements.origin} onChange={(e) => setRequirements({ ...requirements, origin: e.target.value })} /></label>
            <label><span>目的地（逗号分隔）*</span><input required value={requirements.destinations.join('，')} onChange={(e) => setTextList('destinations', e.target.value)} /></label>
            <label><span>开始日期</span><input type="date" value={requirements.start_date ?? ''} onChange={(e) => setRequirements({ ...requirements, start_date: e.target.value || null })} /></label>
            <label><span>结束日期</span><input type="date" value={requirements.end_date ?? ''} onChange={(e) => setRequirements({ ...requirements, end_date: e.target.value || null })} /></label>
            <label><span>总预算（元）</span><input min="0" step="1" type="number" value={totalBudget} onChange={(e) => setRequirements({ ...requirements, budget_cents: e.target.value ? Math.round(Number(e.target.value) * 100) : null })} /></label>
            <label><span>节奏</span><select value={requirements.pace} onChange={(e) => setRequirements({ ...requirements, pace: e.target.value as TripRequirements['pace'] })}><option value="leisure">休闲</option><option value="balanced">均衡</option><option value="compact">紧凑</option><option value="custom">自定义</option></select></label>
          </div>
          <fieldset><legend>旅行风格</legend><div className="choice-grid">{styleOptions.map((value) => <label key={value}><input checked={requirements.styles.includes(value)} onChange={() => toggleList('styles', value)} type="checkbox" />{value}</label>)}</div></fieldset>
          <fieldset><legend>可用交通方式</legend><div className="choice-grid">{transportOptions.map((value) => <label key={value}><input checked={requirements.transportation.includes(value)} onChange={() => toggleList('transportation', value)} type="checkbox" />{value}</label>)}</div></fieldset>
          <fieldset><legend>同行成员</legend><div className="choice-grid">{members.map((member) => <label key={member.membership_id}><input checked={selectedMembers.includes(member.membership_id)} onChange={() => setSelectedMembers((current) => current.includes(member.membership_id) ? current.filter((id) => id !== member.membership_id) : [...current, member.membership_id])} type="checkbox" />{member.display_name}</label>)}</div></fieldset>
          <label><span>必须满足（每行一项）</span><textarea rows={3} value={requirements.hard_constraints.join('\n')} onChange={(e) => setTextList('hard_constraints', e.target.value)} /></label>
          <label><span>偏好建议（每行一项）</span><textarea rows={3} value={requirements.soft_preferences.join('\n')} onChange={(e) => setTextList('soft_preferences', e.target.value)} /></label>
          <label className="confirmation-row"><input checked={requirements.confirmed} onChange={(e) => setRequirements({ ...requirements, confirmed: e.target.checked })} type="checkbox" /><span>我已确认日期、成员、预算与必须满足的约束；后续可交给智能体生成正式计划。</span></label>
          <button className="primary-button" disabled={saving} type="submit">{saving ? '保存中…' : selected ? '保存新版本' : '创建旅行草稿'}</button>
        </form>
      )}

      {!showDeleted && <div className="trip-list">
        {items.length === 0 && !showForm && <p className="muted empty-state">还没有旅行。先建立草稿，再让智能体检索资料并生成路线。</p>}
        {items.map((trip) => (
          <button className="trip-card" key={trip.id} onClick={() => void openTrip(trip.id)} type="button">
            <span className="trip-card-top"><strong>{trip.title}</strong><small>v{trip.version}</small></span>
            <span>{trip.origin || '待定出发地'} → {trip.destinations.join(' · ')}</span>
            <small>{trip.start_date ?? '日期待定'} · {trip.participant_count} 人 · {trip.visibility === 'private' ? '仅自己' : '家庭可见'}</small>
          </button>
        ))}
      </div>}

      {showDeleted && (
        <div className="trip-list recycle-list">
          {deletedItems.length === 0 && <p className="muted empty-state">回收站为空。删除的旅行会保留版本与审计记录，可由本人或家庭管理员恢复。</p>}
          {deletedItems.map((trip) => (
            <div className="trip-card recycle-card" key={trip.id}>
              <span className="trip-card-top"><strong>{trip.title}</strong><small>已删除</small></span>
              <span>{trip.origin || '待定出发地'} → {trip.destinations.join(' · ')}</span>
              <button className="small-button" disabled={saving} onClick={() => void recoverTrip(trip.id)} type="button">恢复旅行</button>
            </div>
          ))}
        </div>
      )}

      {selected && !showForm && !showDeleted && (
        <div className="trip-detail">
          <div><p className="section-kicker">CURRENT FACT SOURCE</p><h3>{selected.title}</h3></div>
          {selected.warnings.map((warning) => <p className="trip-warning" key={warning}>{warning}</p>)}
          <dl><div><dt>路线范围</dt><dd>{selected.requirements.origin || '待定'} → {selected.requirements.destinations.join(' · ')}</dd></div><div><dt>总预算</dt><dd>{selected.requirements.budget_cents === null ? '待定' : `¥${(selected.requirements.budget_cents / 100).toLocaleString()}`}</dd></div><div><dt>参与者</dt><dd>{selected.participants.map((item) => item.display_name).join('、') || '暂未选择'}</dd></div></dl>
          <ItineraryEditor csrfToken={session.csrf_token} tripId={selected.id} />
          <button className="primary-button" onClick={() => setShowForm(true)} type="button">编辑并生成新版本</button>
          {deleteConfirmId !== selected.id ? (
            <button className="danger-button trip-delete-button" onClick={() => setDeleteConfirmId(selected.id)} type="button">移入回收站</button>
          ) : (
            <div className="delete-confirmation">
              <p>旅行将从当前列表移除，但历史版本和审计记录会保留。</p>
              <div><button className="danger-button" disabled={saving} onClick={() => void removeTrip(selected.id)} type="button">确认移入回收站</button><button className="small-button" onClick={() => setDeleteConfirmId(null)} type="button">取消</button></div>
            </div>
          )}
          <div className="version-history"><strong>修改历史</strong>{versions.map((version) => <div key={version.id}><span>v{version.version_no} · {version.summary}</span><small>{new Date(version.created_at).toLocaleString('zh-CN')}</small></div>)}</div>
        </div>
      )}
    </section>
  )
}
