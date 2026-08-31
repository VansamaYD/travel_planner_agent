import { useEffect, useMemo, useState } from 'react'

import type { SessionData } from '../../shared/api/access'
import { deleteGuide, listGuides, updateGuide, type Guide } from '../../shared/api/guides'
import { analyzeImage } from '../../shared/api/knowledge'

export function GuideLibrary({ session }: { session: SessionData }) {
  const [guides, setGuides] = useState<Guide[]>([])
  const [city, setCity] = useState('全部')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState<Record<string, string>>({})
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void listGuides(controller.signal).then(setGuides).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(messageOf(reason))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  const cities = useMemo(() => ['全部', ...new Set(guides.map((guide) => guide.city || '未分类'))], [guides])
  const visible = guides.filter((guide) => city === '全部' || guide.city === city)

  async function patch(id: string, changes: Partial<Pick<Guide, 'title' | 'city' | 'content' | 'user_notes' | 'pinned'>>) {
    try {
      const value = await updateGuide(id, changes, session.csrf_token)
      setGuides((items) => items.map((item) => item.id === id ? value : item))
    } catch (reason) { setError(messageOf(reason)) }
  }

  async function remove(guide: Guide) {
    if (!window.confirm(`删除《${guide.title}》？此操作不会影响原平台内容。`)) return
    try {
      await deleteGuide(guide.id, session.csrf_token)
      setGuides((items) => items.filter((item) => item.id !== guide.id))
    } catch (reason) { setError(messageOf(reason)) }
  }

  async function analyzeGuideImages(guide: Guide) {
    const images = guide.images.slice(0, 12)
    if (!images.length || !window.confirm(`将按需调用视觉模型分析 ${images.length} 张图片；已识别过的图片会直接复用记录。是否继续？`)) return
    const notes: string[] = []
    setAnalyzing((value) => ({ ...value, [guide.id]: `0/${images.length}` }))
    try {
      for (let index = 0; index < images.length; index += 1) {
        const source = images[index]
        if (!source) continue
        const { analysis, cacheHit } = await analyzeImage(source, 'auto', session.csrf_token)
        const result = analysis.result
        const transcription = typeof result.transcription === 'string' ? result.transcription.trim() : ''
        const description = typeof result.description === 'string' ? result.description.trim() : ''
        const filename = typeof result.suggested_filename === 'string' ? result.suggested_filename : `图片${index + 1}`
        if (transcription || description) notes.push(`### ${filename}${cacheHit ? '（复用识别）' : ''}\n${transcription || description}`)
        setAnalyzing((value) => ({ ...value, [guide.id]: `${index + 1}/${images.length}` }))
      }
      const merged = [guide.user_notes, notes.length ? `【图片识别整理】\n${notes.join('\n\n')}` : ''].filter(Boolean).join('\n\n')
      await patch(guide.id, { user_notes: merged })
      setAnalyzing((value) => ({ ...value, [guide.id]: '完成' }))
    } catch (reason) {
      setError(messageOf(reason)); setAnalyzing((value) => ({ ...value, [guide.id]: '失败' }))
    }
  }

  return <section className="guide-library-page">
    <header className="page-title-row"><div><p className="section-kicker">KNOWLEDGE LIBRARY</p><h2>攻略库</h2><p>已下载的原文快照按城市整理，可编辑、置顶并供模型检索。</p></div><span>{guides.length} 篇</span></header>
    <nav className="city-filter" aria-label="攻略城市">{cities.map((value) => <button className={city === value ? 'is-active' : ''} key={value} onClick={() => setCity(value)} type="button">{value}</button>)}</nav>
    {error && <p className="form-error">{error}</p>}
    {loading && <p className="muted">正在读取攻略库…</p>}
    {!loading && !visible.length && <div className="panel page-empty"><h3>还没有已保存的攻略</h3><p>回到助手页搜索攻略，勾选感兴趣的内容后保存。</p></div>}
    <div className="guide-library-grid">{visible.map((guide) => <article className={`guide-library-card ${guide.pinned ? 'is-pinned' : ''}`} key={guide.id}>
      {guide.images[0] && <img alt={`${guide.title}封面`} loading="lazy" referrerPolicy="no-referrer" src={guide.images[0]} />}
      <div className="guide-library-body"><header><div><small>{guide.city} · {guide.author || '社区用户'}</small><h3>{guide.title}</h3></div><button aria-label={guide.pinned ? '取消置顶' : '置顶'} onClick={() => void patch(guide.id, { pinned: !guide.pinned })} type="button">{guide.pinned ? '★' : '☆'}</button></header>
      <p>{guide.content || guide.summary}</p>
      <div className="guide-meta"><span>{guide.images.length} 张图</span><span>{guide.comments.length} 条参考评论</span><span>{guide.stale ? '建议刷新' : '详情已缓存'}</span></div>
      {expanded === guide.id && <div className="guide-detail">
        {guide.images.length > 1 && <div className="guide-image-strip">{guide.images.map((image, index) => <img alt={`${guide.title}图片${index + 1}`} key={image} loading="lazy" referrerPolicy="no-referrer" src={image} />)}</div>}
        <div className="guide-full-text">{guide.content || guide.summary}</div>
        {guide.comments.length > 0 && <section><h4>部分评论参考</h4>{guide.comments.map((comment, index) => <blockquote key={`${comment.author}-${index}`}><strong>{comment.author || '用户'}</strong>{comment.content}</blockquote>)}</section>}
        {guide.user_notes && <aside><strong>我的备注</strong><p>{guide.user_notes}</p></aside>}
      </div>}
      {editing === guide.id && <GuideEditor guide={guide} onCancel={() => setEditing(null)} onSave={(changes) => { void patch(guide.id, changes); setEditing(null) }} />}
      <footer><button onClick={() => setExpanded((value) => value === guide.id ? null : guide.id)} type="button">{expanded === guide.id ? '收起' : '查看详情'}</button><button onClick={() => setEditing((value) => value === guide.id ? null : guide.id)} type="button">编辑</button>{guide.images.length > 0 && <button disabled={Boolean(analyzing[guide.id] && analyzing[guide.id] !== '完成' && analyzing[guide.id] !== '失败')} onClick={() => void analyzeGuideImages(guide)} type="button">识图 {analyzing[guide.id] ?? ''}</button>}<a href={guide.url} rel="noreferrer" target="_blank">原文</a><button className="danger-link" onClick={() => void remove(guide)} type="button">删除</button></footer>
      </div>
    </article>)}</div>
  </section>
}

function GuideEditor({ guide, onCancel, onSave }: { guide: Guide; onCancel: () => void; onSave: (changes: Partial<Guide>) => void }) {
  const [title, setTitle] = useState(guide.title)
  const [city, setCity] = useState(guide.city)
  const [content, setContent] = useState(guide.content)
  const [notes, setNotes] = useState(guide.user_notes)
  return <div className="guide-editor"><label>标题<input maxLength={300} onChange={(event) => setTitle(event.target.value)} value={title} /></label><label>城市<input maxLength={100} onChange={(event) => setCity(event.target.value)} value={city} /></label><label>整理正文<textarea maxLength={24000} onChange={(event) => setContent(event.target.value)} rows={8} value={content} /></label><label>我的备注<textarea maxLength={8000} onChange={(event) => setNotes(event.target.value)} rows={3} value={notes} /></label><div><button onClick={onCancel} type="button">取消</button><button className="primary-button" disabled={!title.trim()} onClick={() => onSave({ title: title.trim(), city: city.trim(), content, user_notes: notes })} type="button">保存修改</button></div></div>
}

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : '攻略库操作失败'
}
