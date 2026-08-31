export interface GuideComment { author: string; content: string; likes: number | null }

export interface Guide {
  id: string
  provider: string
  title: string
  url: string
  author: string
  summary: string
  city: string
  source_query: string
  status: 'discovered' | 'downloading' | 'ready' | 'failed'
  pinned: boolean
  content: string
  images: string[]
  comments: GuideComment[]
  tags: string[]
  metadata: Record<string, unknown>
  user_notes: string
  fetched_at: string
  expires_at: string
  detail_fetched_at: string | null
  detail_expires_at: string | null
  stale: boolean
}

export interface GuideImportEvent {
  event: string
  guide_id?: string
  index?: number
  total?: number
  completed?: number
  failed?: number
  label?: string
  guide?: Guide
}

interface Envelope<T> { data: T }

export async function listGuides(signal?: AbortSignal): Promise<Guide[]> {
  const response = await fetch('/api/v1/guides?scope=library&limit=100', { signal })
  return (await parse<Envelope<Guide[]>>(response)).data
}

export async function importGuides(
  ids: string[],
  csrfToken: string,
  onEvent: (event: GuideImportEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/v1/guides/import/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ guide_ids: ids }),
    signal,
  })
  if (!response.ok) await throwProblem(response)
  if (!response.body) throw new Error('浏览器不支持流式下载进度。')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split(/\r?\n/).find((item) => item.startsWith('data:'))
      if (line) onEvent(JSON.parse(line.slice(5).trim()) as GuideImportEvent)
    }
    if (done) break
  }
}

export async function updateGuide(
  id: string,
  changes: Partial<Pick<Guide, 'title' | 'city' | 'content' | 'user_notes' | 'pinned'>>,
  csrfToken: string,
): Promise<Guide> {
  const response = await fetch(`/api/v1/guides/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify(changes),
  })
  return (await parse<Envelope<Guide>>(response)).data
}

export async function deleteGuide(id: string, csrfToken: string): Promise<void> {
  const response = await fetch(`/api/v1/guides/${id}`, {
    method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) await throwProblem(response)
}

export async function refreshGuideComments(id: string, csrfToken: string): Promise<Guide> {
  const response = await fetch(`/api/v1/guides/${id}/comments/refresh`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrfToken },
  })
  return (await parse<Envelope<Guide>>(response)).data
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
