import { useEffect, useRef, useState, type FormEvent } from 'react'

import type { SessionData } from '../../shared/api/access'
import {
  createConversation,
  listConversations,
  listMessages,
  streamConversationMessage,
  type AgentStreamEvent,
  type ChatMessage,
  type Conversation,
} from '../../shared/api/conversations'
import { GuideCandidateCards } from './GuideCandidateCards'

interface ChatWorkspaceProps { session: SessionData; onOpenLibrary: () => void }
interface ActivityStep { key: string; label: string; status: 'active' | 'done' | 'failed' }

const suggestions = [
  ['规划一次新旅行', '我想规划一次新旅行，请逐步询问日期、出发地、目的地、人数和偏好。'],
  ['优化旅游路线', '请帮我优化一份现有行程，先询问我现有的地点和限制。'],
  ['分析预算', '请帮我估算旅行预算，并区分交通、住宿、餐饮、门票和机动费用。'],
  ['整理攻略', '我有多份旅游攻略需要整理，请先告诉我如何提供资料。'],
] as const

export function ChatWorkspace({ session, onOpenLibrary }: ChatWorkspaceProps) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activity, setActivity] = useState<ActivityStep[]>([])
  const [activityKey, setActivityKey] = useState(0)
  const endRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void listConversations(controller.signal).then(async (items) => {
      setConversations(items)
      if (items[0]) {
        setConversationId(items[0].id)
        setMessages(await listMessages(items[0].id, controller.signal))
      }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(messageOf(reason))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, activity])

  async function selectConversation(id: string) {
    if (sending) return
    setError('')
    if (!id) {
      setConversationId(null)
      setMessages([])
      setActivity([])
      return
    }
    setConversationId(id)
    setLoading(true)
    try { setMessages(await listMessages(id)) } catch (reason) { setError(messageOf(reason)) }
    finally { setLoading(false) }
  }

  async function submit(event?: FormEvent, suggested?: string) {
    event?.preventDefault()
    const content = (suggested ?? draft).trim()
    if (!content || sending) return
    setSending(true)
    setDraft('')
    setError('')
    setActivity([])
    setActivityKey((value) => value + 1)
    const localUserId = `local-user-${Date.now()}`
    const localAssistantId = `local-assistant-${Date.now()}`
    setMessages((items) => [...items, localMessage(localUserId, 'user', content), localMessage(localAssistantId, 'assistant', '')])
    const controller = new AbortController()
    abortRef.current = controller
    let activeId = conversationId
    try {
      if (activeId === null) {
        const created = await createConversation(session.csrf_token)
        activeId = created.id
        setConversationId(created.id)
        setConversations((items) => [created, ...items])
      }
      await streamConversationMessage(activeId, content, session.csrf_token, (streamEvent) => {
        handleEvent(streamEvent, localAssistantId)
      }, controller.signal)
      setConversations(await listConversations())
    } catch (reason) {
      if (!controller.signal.aborted) {
        const detail = messageOf(reason)
        setError(detail)
        setMessages((items) => items.map((item) => item.id === localAssistantId && !item.content
          ? { ...item, content: `抱歉，${detail}` } : item))
        failActivity(detail)
      }
    } finally {
      abortRef.current = null
      setSending(false)
    }
  }

  function handleEvent(event: AgentStreamEvent, assistantId: string) {
    if (event.event === 'assistant.delta' && event.text) {
      setMessages((items) => items.map((item) => item.id === assistantId
        ? { ...item, content: item.content + event.text } : item))
      return
    }
    if (event.event === 'run.failed') {
      const label = event.label ?? '模型请求失败'
      setError(label)
      setMessages((items) => items.map((item) => item.id === assistantId && !item.content
        ? { ...item, content: `抱歉，${label}` } : item))
      failActivity(label)
      return
    }
    if (event.event === 'artifact.guides' && event.artifact) {
      setMessages((items) => items.map((item) => item.id === assistantId
        ? { ...item, artifacts: [...item.artifacts, event.artifact!] } : item))
      return
    }
    if (event.label) {
      const status: ActivityStep['status'] = event.event.endsWith('.failed')
        ? 'failed' : event.event.endsWith('.completed') ? 'done' : 'active'
      setActivity((steps) => [
        ...steps.map((step) => step.status === 'active' ? { ...step, status: 'done' as const } : step),
        { key: `${event.event}-${steps.length}`, label: event.label!, status },
      ])
    }
  }

  function failActivity(label: string) {
    setActivity((steps) => [
      ...steps.map((step) => step.status === 'active' ? { ...step, status: 'done' as const } : step),
      { key: `failed-${steps.length}`, label, status: 'failed' },
    ])
  }

  const hasMessages = messages.length > 0
  return <section className="chat-workspace">
    <div className="conversation-toolbar">
      <select aria-label="选择对话" disabled={sending} onChange={(event) => void selectConversation(event.target.value)} value={conversationId ?? ''}>
        <option value="">新对话</option>
        {conversations.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      <button disabled={sending} onClick={() => void selectConversation('')} type="button">+新对话</button>
    </div>

    <div className={`chat-scroll ${hasMessages ? 'has-messages' : ''}`}>
      {!hasMessages && !loading && <div className="chat-empty">
        <div className="chat-welcome"><span className="chat-mark">旅</span><h1>今天想计划什么？</h1><p>规划旅行、分析预算、优化路线，或帮你整理现有资料。</p></div>
        <div className="prompt-grid">{suggestions.map(([label, prompt]) => <button disabled={sending} key={label} onClick={() => void submit(undefined, prompt)} type="button"><strong>{label}</strong><span>{prompt.slice(0, 28)}…</span></button>)}</div>
      </div>}
      {loading && <p className="chat-loading">正在读取对话…</p>}
      {messages.map((message) => <article className={`chat-message is-${message.role}`} key={message.id}>
        <span>{message.role === 'assistant' ? '旅' : session.user.display_name.slice(0, 1)}</span>
        <div>{message.content ? <MessageContent content={message.content} /> : <i className="typing-dot">●●●</i>}{message.artifacts.map((artifact, index) => artifact.type === 'guide_candidates'
          ? <GuideCandidateCards artifact={artifact} key={`${message.id}-${index}`} onOpenLibrary={onOpenLibrary} session={session} /> : null)}</div>
      </article>)}
      {activity.length > 0 && <details className="agent-activity" key={activityKey} open={sending || undefined}>
        <summary><span className={sending ? 'activity-pulse' : ''} />{sending ? activity.at(-1)?.label : '本次执行详情'}<small>{sending ? '进行中' : '已完成'}</small></summary>
        <ol>{activity.map((step) => <li className={`is-${step.status}`} key={step.key}><span />{step.label}</li>)}</ol>
        <p>仅展示可审计的执行阶段和工具摘要，不展示模型隐式思维链。</p>
      </details>}
      <div ref={endRef} />
    </div>

    {error && <p className="chat-error" role="alert">{error}</p>}
    <form className="chat-composer" onSubmit={(event) => void submit(event)}>
      <button aria-label="添加附件（即将支持）" disabled title="附件将在后续版本接入" type="button">+</button>
      <textarea aria-label="发送消息" disabled={sending} maxLength={8000} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
        if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() }
      }} placeholder="向旅行助手发送消息…" rows={1} value={draft} />
      <button aria-label={sending ? '正在回复' : '发送'} disabled={sending || !draft.trim()} type="submit">{sending ? '···' : '↑'}</button>
    </form>
  </section>
}

function localMessage(id: string, role: ChatMessage['role'], content: string): ChatMessage {
  return { id, role, content, created_at: new Date().toISOString(), artifacts: [] }
}

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : '未知错误'
}

function MessageContent({ content }: { content: string }) {
  return <>{content.split(/(https?:\/\/[^\s]+)/g).map((part, index) => part.startsWith('http')
    ? <a href={part} key={`${part}-${index}`} rel="noreferrer" target="_blank">{part}</a>
    : part)}</>
}
