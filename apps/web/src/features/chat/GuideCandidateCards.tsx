import { useEffect, useMemo, useState } from 'react'

import type { SessionData } from '../../shared/api/access'
import type { GuideCandidateArtifactItem, MessageArtifact } from '../../shared/api/conversations'
import { importGuides, listGuides } from '../../shared/api/guides'

interface Props {
  artifact: MessageArtifact
  session: SessionData
  onOpenLibrary: () => void
}

export function GuideCandidateCards({ artifact, session, onOpenLibrary }: Props) {
  const guides = useMemo(() => artifact.guides ?? [], [artifact.guides])
  const [selected, setSelected] = useState(() => new Set<string>())
  const [statuses, setStatuses] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)
  const [summary, setSummary] = useState('')
  const orderedGuides = useMemo(() => [...guides].sort((left, right) => {
    const leftReady = left.status === 'ready' || statuses[left.candidate_id] === '本地已有'
    const rightReady = right.status === 'ready' || statuses[right.candidate_id] === '本地已有'
    return Number(leftReady) - Number(rightReady)
  }), [guides, statuses])

  useEffect(() => {
    const controller = new AbortController()
    void listGuides(controller.signal).then((saved) => {
      const ids = new Set(saved.map((guide) => guide.id))
      setStatuses(Object.fromEntries(guides.filter((guide) => ids.has(guide.candidate_id)).map((guide) => [guide.candidate_id, '本地已有'])))
    }).catch(() => { /* The cards remain usable when library status cannot be loaded. */ })
    return () => controller.abort()
  }, [guides])

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  async function save() {
    const ids = [...selected]
    if (!ids.length || running) return
    setRunning(true); setSummary('正在建立下载任务…')
    try {
      await importGuides(ids, session.csrf_token, (event) => {
        if (event.guide_id) {
          setStatuses((values) => ({ ...values, [event.guide_id!]: event.event === 'guide.completed' ? '本地已有' : event.event === 'guide.failed' ? '失败' : '更新中' }))
        }
        if (event.label) setSummary(event.label)
      })
    } catch (reason) {
      setSummary(reason instanceof Error ? reason.message : '保存攻略失败')
    } finally { setRunning(false) }
  }

  if (!guides.length) return null
  return <section className="guide-candidate-module">
    <header><div><strong>小红书攻略候选</strong><small>勾选后读取原文、图片和部分评论</small></div><span>{guides.length} 篇</span></header>
    <div className="guide-candidate-scroll">{orderedGuides.map((guide, index) => <GuideChoice
      checked={selected.has(guide.candidate_id)}
      guide={guide}
      index={index}
      key={guide.candidate_id}
      onToggle={() => toggle(guide.candidate_id)}
      status={statuses[guide.candidate_id]}
    />)}</div>
    <footer><button disabled={!selected.size || running} onClick={() => void save()} type="button">{running ? '正在逐篇下载或更新…' : `保存或更新所选 ${selected.size || ''} 篇`}</button>{summary && <small>{summary}</small>}{Object.values(statuses).includes('本地已有') && <button className="text-button" onClick={onOpenLibrary} type="button">进入攻略库查看</button>}</footer>
  </section>
}

function GuideChoice({ guide, index, checked, onToggle, status }: {
  guide: GuideCandidateArtifactItem
  index: number
  checked: boolean
  onToggle: () => void
  status?: string
}) {
  const local = status === '本地已有' || guide.status === 'ready'
  return <label className={`guide-choice ${checked ? 'is-selected' : ''} ${local ? 'is-local' : ''}`}>
    <input checked={checked} onChange={onToggle} type="checkbox" />
    <span className="guide-choice-number">{index + 1}</span>
    <div><strong>{guide.title}</strong><small>{guide.author || '社区用户'} · {status || (local ? '本地已有' : '未下载')}</small><p>{guide.summary || '打开原文查看详情'}</p><a href={guide.url} onClick={(event) => event.stopPropagation()} rel="noreferrer" target="_blank">查看小红书原文 ↗</a></div>
  </label>
}
