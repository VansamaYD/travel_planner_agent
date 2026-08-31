export interface FamilySummary {
  id: string
  name: string
  role: 'owner' | 'admin' | 'member' | 'guest'
}

export interface SessionData {
  user: {
    id: string
    username: string
    email: string | null
    display_name: string
    system_role: 'admin' | 'member'
  }
  csrf_token: string
  expires_at: string
  families: FamilySummary[]
}

interface Envelope<T> {
  data: T
  meta: { request_id: string }
}

interface Problem {
  detail?: string
  code?: string
}

export interface InitializeInput {
  username: string
  email: string
  display_name: string
  password: string
  family_name: string
}

export async function getSetupStatus(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch('/api/v1/setup/status', { signal })
  const body = await parse<Envelope<{ initialized: boolean }>>(response)
  return body.data.initialized
}

export async function initializeSystem(
  input: InitializeInput,
): Promise<{ recoveryCode: string; session: SessionData }> {
  const response = await fetch('/api/v1/setup/initialize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...input, email: input.email || null }),
  })
  const body = await parse<Envelope<{ recovery_code: string; session: SessionData }>>(response)
  return { recoveryCode: body.data.recovery_code, session: body.data.session }
}

export async function login(loginName: string, password: string): Promise<SessionData> {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login: loginName, password }),
  })
  return (await parse<Envelope<SessionData>>(response)).data
}

export async function getSession(signal?: AbortSignal): Promise<SessionData | null> {
  const response = await fetch('/api/v1/auth/session', { signal })
  if (response.status === 401) return null
  return (await parse<Envelope<SessionData>>(response)).data
}

export async function logout(csrfToken: string): Promise<void> {
  const response = await fetch('/api/v1/auth/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) await throwProblem(response)
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) await throwProblem(response)
  return (await response.json()) as T
}

async function throwProblem(response: Response): Promise<never> {
  let problem: Problem = {}
  try {
    problem = (await response.json()) as Problem
  } catch {
    // A stable local fallback is safer than exposing raw upstream content.
  }
  throw new Error(problem.detail ?? `请求失败（${response.status}）`)
}
