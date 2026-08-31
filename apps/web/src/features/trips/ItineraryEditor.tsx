import { useEffect, useState } from 'react'

import {
  getItinerary,
  initializeItinerary,
  updateItinerary,
  type ItineraryDay,
  type ItineraryItem,
  type ItineraryPlan,
} from '../../shared/api/itinerary'
import {
  applyPlanningProposal,
  listPlanningProposals,
  startPlanning,
  type PlanningProposal,
  type PlanningRun,
} from '../../shared/api/planning'

interface Props { tripId: string; csrfToken: string }

const emptyItem = (): ItineraryItem => ({
  logical_id: null, item_type: 'place', title: '', place_name: '', start_time: null,
  end_time: null, cost_cents: null, execution_status: 'planned', notes: '', tags: [],
  transport_to_next: null, travel_minutes_to_next: null, travel_cost_cents_to_next: null,
})

export function ItineraryEditor({ tripId, csrfToken }: Props) {
  const [plan, setPlan] = useState<ItineraryPlan | null>(null)
  const [days, setDays] = useState<ItineraryDay[]>([])
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [planning, setPlanning] = useState(false)
  const [applying, setApplying] = useState(false)
  const [profile, setProfile] = useState<PlanningRun['profile']>('PLAN_STANDARD')
  const [instruction, setInstruction] = useState('')
  const [proposal, setProposal] = useState<PlanningProposal | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    Promise.all([getItinerary(tripId, controller.signal), listPlanningProposals(tripId, controller.signal)])
      .then(([value, proposals]) => {
        setPlan(value); setDays(value?.days ?? [])
        setProposal(proposals.find((item) => item.status === 'pending') ?? proposals[0] ?? null)
      })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [tripId])

  async function initialize() {
    setLoading(true); setError('')
    try { const value = await initializeItinerary(tripId, csrfToken); setPlan(value); setDays(value.days) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '初始化失败') }
    finally { setLoading(false) }
  }

  async function save() {
    if (!plan) return
    setLoading(true); setError('')
    try { const value = await updateItinerary(tripId, plan.version, days, csrfToken); setPlan(value); setDays(value.days); setEditing(false) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败') }
    finally { setLoading(false) }
  }

  async function generateProposal() {
    setPlanning(true); setError('')
    try {
      const result = await startPlanning(tripId, profile, instruction.trim(), csrfToken)
      if (result.run.status === 'failed') {
        setError(result.run.error || '智能规划未能完成')
        return
      }
      setProposal(result.proposal)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '智能规划失败') }
    finally { setPlanning(false) }
  }

  async function applyProposal() {
    if (!proposal) return
    setApplying(true); setError('')
    try {
      const applied = await applyPlanningProposal(proposal.id, csrfToken)
      const nextPlan = await getItinerary(tripId)
      setProposal(applied); setPlan(nextPlan); setDays(nextPlan?.days ?? [])
    } catch (reason) { setError(reason instanceof Error ? reason.message : '应用候选方案失败') }
    finally { setApplying(false) }
  }

  function updateDay(index: number, patch: Partial<ItineraryDay>) {
    setDays((current) => current.map((day, dayIndex) => dayIndex === index ? { ...day, ...patch } : day))
  }

  function updateItem(dayIndex: number, itemIndex: number, patch: Partial<ItineraryItem>) {
    setDays((current) => current.map((day, index) => index !== dayIndex ? day : {
      ...day, items: day.items.map((item, position) => position === itemIndex ? { ...item, ...patch } : item),
    }))
  }

  if (loading && !plan) return <p className="muted itinerary-loading">正在读取旅行计划…</p>

  return (
    <section className="itinerary-section" aria-labelledby="itinerary-title">
      <div className="itinerary-heading">
        <div><p className="section-kicker">DAY-BY-DAY ITINERARY</p><h3 id="itinerary-title">按天旅行计划</h3></div>
        {plan && <small>v{plan.version} · 预计 ¥{(plan.estimated_total_cost_cents / 100).toLocaleString()}</small>}
      </div>
      {error && <p className="form-error">{error}</p>}
      <div className="ai-planner">
        <div className="ai-planner-heading">
          <div><strong>AI 候选方案</strong><span>生成后仅预览，不会自动改动正式日程</span></div>
          <span className="ai-status">{planning ? '规划中' : proposal?.status === 'pending' ? '待确认' : proposal?.status === 'applied' ? '已应用' : '尚未生成'}</span>
        </div>
        <label><span>本次调整说明（可选）</span><textarea maxLength={2000} placeholder="例如：每天 9 点后出发，不要连续安排两个园林" rows={3} value={instruction} onChange={(event) => setInstruction(event.target.value)} /></label>
        <div className="ai-planner-controls">
          <select aria-label="规划深度" value={profile} onChange={(event) => setProfile(event.target.value as PlanningRun['profile'])}><option value="PLAN_STANDARD">标准规划</option><option value="PLAN_DEEP">深度规划（更高用量）</option></select>
          <button className="primary-button" disabled={planning || applying} onClick={() => void generateProposal()} type="button">{planning ? '模型正在设计日程…' : proposal?.status === 'pending' ? '重新生成候选方案' : '生成候选方案'}</button>
        </div>
        <p className="ai-disclaimer">当前节点只进行模型规划；价格、营业时间、票务和地图路线仍需后续联网节点核验。</p>
        {proposal && (
          <article className="proposal-preview">
            <header><div><strong>{proposal.summary}</strong><small>{new Date(proposal.created_at).toLocaleString('zh-CN')} · 输入 {proposal.input_tokens.toLocaleString()} / 输出 {proposal.output_tokens.toLocaleString()} tokens · 估算 ${Math.max(proposal.estimated_cost_microusd / 1_000_000, 0).toFixed(4)}</small></div><span>{proposal.days.length} 天</span></header>
            {proposal.rationale && <p>{proposal.rationale}</p>}
            {proposal.warnings.map((warning) => <p className="proposal-warning" key={warning}>{warning}</p>)}
            <div className="proposal-days">{proposal.days.map((day) => <div key={day.local_date}><strong>{day.local_date} · {day.city}</strong><span>{day.summary || '当天安排'} · {day.items.length} 项活动</span></div>)}</div>
            {proposal.status === 'pending' && <button className="proposal-apply" disabled={applying} onClick={() => void applyProposal()} type="button">{applying ? '正在创建日程新版本…' : '确认并应用到正式日程'}</button>}
          </article>
        )}
      </div>
      {!plan ? (
        <div className="itinerary-empty"><p>根据旅行日期建立按天结构，再逐项添加景点、餐厅、住宿、交通和费用。</p><button className="primary-button" disabled={loading} onClick={() => void initialize()} type="button">建立按天计划</button></div>
      ) : (
        <>
          {plan.warnings.map((warning) => <p className="trip-warning" key={warning}>{warning}</p>)}
          <div className="day-list">
            {days.map((day, dayIndex) => (
              <article className="day-card" key={`${day.local_date}-${dayIndex}`}>
                <header><span>DAY {dayIndex + 1}</span><strong>{day.local_date}</strong></header>
                {editing ? <div className="day-fields"><input aria-label={`第 ${dayIndex + 1} 天城市`} value={day.city} onChange={(e) => updateDay(dayIndex, { city: e.target.value })} /><input aria-label={`第 ${dayIndex + 1} 天摘要`} placeholder="当天主题或摘要" value={day.summary} onChange={(e) => updateDay(dayIndex, { summary: e.target.value })} /></div> : <div className="day-title"><strong>{day.city}</strong><span>{day.summary || '当天安排待完善'}</span></div>}
                <div className="itinerary-items">
                  {day.items.map((item, itemIndex) => editing ? (
                    <div className="itinerary-item-edit" key={item.logical_id ?? itemIndex}>
                      <div className="field-grid"><label><span>类型</span><select value={item.item_type} onChange={(e) => updateItem(dayIndex, itemIndex, { item_type: e.target.value as ItineraryItem['item_type'] })}><option value="place">景点</option><option value="restaurant">餐厅</option><option value="hotel">住宿</option><option value="transport">交通</option><option value="rest">休息</option><option value="free_time">自由活动</option><option value="other">其他</option></select></label><label><span>活动名称 *</span><input value={item.title} onChange={(e) => updateItem(dayIndex, itemIndex, { title: e.target.value })} /></label><label><span>地点</span><input value={item.place_name} onChange={(e) => updateItem(dayIndex, itemIndex, { place_name: e.target.value })} /></label><label><span>费用（元）</span><input min="0" type="number" value={item.cost_cents === null ? '' : item.cost_cents / 100} onChange={(e) => updateItem(dayIndex, itemIndex, { cost_cents: e.target.value ? Math.round(Number(e.target.value) * 100) : null })} /></label><label><span>开始</span><input type="time" value={item.start_time ?? ''} onChange={(e) => updateItem(dayIndex, itemIndex, { start_time: e.target.value || null })} /></label><label><span>结束</span><input type="time" value={item.end_time ?? ''} onChange={(e) => updateItem(dayIndex, itemIndex, { end_time: e.target.value || null })} /></label><label><span>前往下一站</span><select value={item.transport_to_next ?? ''} onChange={(e) => updateItem(dayIndex, itemIndex, { transport_to_next: e.target.value || null })}><option value="">无</option><option>步行</option><option>地铁公交线路</option><option>网约车出租车</option><option>自驾</option><option>高铁动车火车</option><option>飞机</option><option>轮渡</option></select></label><label><span>交通分钟</span><input min="0" type="number" value={item.travel_minutes_to_next ?? ''} onChange={(e) => updateItem(dayIndex, itemIndex, { travel_minutes_to_next: e.target.value ? Number(e.target.value) : null })} /></label></div>
                      <button className="danger-button" onClick={() => updateDay(dayIndex, { items: day.items.filter((_, index) => index !== itemIndex) })} type="button">移除活动</button>
                    </div>
                  ) : (
                    <div className="itinerary-item" key={item.logical_id ?? itemIndex}><time>{item.start_time ?? '--:--'}</time><div><strong>{item.title}</strong><span>{item.place_name || '地点待定'}{item.cost_cents === null ? '' : ` · ¥${item.cost_cents / 100}`}</span></div>{item.transport_to_next && <small>下一站：{item.transport_to_next}{item.travel_minutes_to_next ? ` ${item.travel_minutes_to_next} 分钟` : ''}</small>}</div>
                  ))}
                  {!editing && day.items.length === 0 && <p className="muted day-empty">暂无活动</p>}
                </div>
                {editing && <button className="small-button add-item-button" onClick={() => updateDay(dayIndex, { items: [...day.items, emptyItem()] })} type="button">+ 添加活动</button>}
              </article>
            ))}
          </div>
          <div className="itinerary-actions">{editing ? <><button className="primary-button" disabled={loading} onClick={() => void save()} type="button">{loading ? '保存中…' : '保存日程新版本'}</button><button className="small-button" onClick={() => { setDays(plan.days); setEditing(false) }} type="button">取消</button></> : <button className="primary-button" onClick={() => setEditing(true)} type="button">编辑日程</button>}</div>
        </>
      )}
    </section>
  )
}
