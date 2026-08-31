import { useState } from 'react'

import { findPlaceCards, type PlaceCard } from '../../shared/api/knowledge'

export function PlaceKnowledgeButton({ name, city }: { name: string; city: string }) {
  const [card, setCard] = useState<PlaceCard | null>(null)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  async function toggle() {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (card || loading) return
    setLoading(true)
    try { setCard((await findPlaceCards(name, city))[0] ?? null) } finally { setLoading(false) }
  }

  return <div className="place-knowledge-control"><button onClick={() => void toggle()} type="button">{open ? '收起资料' : '资料卡'}</button>{open && <aside className="place-knowledge-popover">{loading ? <span>正在读取知识库…</span> : card ? <PlaceSummary card={card} /> : <span>暂无资料卡；打开地图或让模型查询后会自动建立。</span>}</aside>}</div>
}

function PlaceSummary({ card }: { card: PlaceCard }) {
  const detailRows = Object.entries(card.details).filter(([, value]) => value !== null && value !== '' && (!Array.isArray(value) || value.length))
  return <><header><div><strong>{card.name}</strong><small>{typeLabel(card.entity_type)} · v{card.version}</small></div><span>{Math.round(card.confidence * 100)}%</span></header><p>{card.intro || card.address || '介绍信息待模型与用户共同完善。'}</p><dl>{detailRows.slice(0, 8).map(([key, value]) => <div key={key}><dt>{detailLabel(key)}</dt><dd>{printValue(value)}</dd></div>)}</dl><small>更新：{new Date(card.updated_at).toLocaleString('zh-CN')}</small></>
}

function typeLabel(value: PlaceCard['entity_type']): string {
  return { attraction: '景点', restaurant: '餐厅', hotel: '酒店', transport_hub: '交通枢纽', other: '地点' }[value]
}

function detailLabel(value: string): string {
  return ({ tags: '标签', rating: '评分', average_cost: '人均', opening_hours: '营业时间', reservation: '预约', must_do: '推荐必玩', foods: '美食', prices: '价格' } as Record<string, string>)[value] ?? value
}

function printValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}
