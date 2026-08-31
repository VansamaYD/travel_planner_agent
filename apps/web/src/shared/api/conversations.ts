export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface AgentStreamEvent {
  event: string
  label?: string
  node?: string
  text?: string
  run_id?: string
  message_id?: string
}

interface Envelope<T> { data: T }

export async function createConversation(csrfToken: string): Promise<Conversation> {
  const response = await fetch('/api/v1/conversations', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  return (await parse<Envelope<Conversation>>(response)).data
}

export async function listConversations(signal?: AbortSignal): Promise<Conversation[]> {
  const response = await fetch('/api/v1/conversations', { signal })
  return (await parse<Envelope<Conversation[]>>(response)).data
}

export async function listMessages(
  conversationId: string,
  signal?: AbortSignal,
): Promise<ChatMessage[]> {
  const response = await fetch(`/api/v1/conversations/${conversationId}/messages`, { signal })
  return (await parse<Envelope<ChatMessage[]>>(response)).data
}

export async function streamConversationMessage(
  conversationId: string,
  content: string,
  csrfToken: string,
  onEvent: (event: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/v1/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ content }),
    signal,
  })
  if (!response.ok) await throwProblem(response)
  if (response.body === null) throw new Error('浏览器不支持流式响应。')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) emitFrame(frame, onEvent)
    if (done) break
  }
  if (buffer.trim()) emitFrame(buffer, onEvent)
}

function emitFrame(frame: string, onEvent: (event: AgentStreamEvent) => void) {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  if (data) onEvent(JSON.parse(data) as AgentStreamEvent)
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  return await throwProblem(response)
}

async function throwProblem(response: Response): Promise<never> {
  let detail = `请求失败（${response.status}）`
  try { detail = ((await response.json()) as { detail?: string }).detail ?? detail } catch { /* fallback */ }
  throw new Error(detail)
}
