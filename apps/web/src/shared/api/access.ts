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

export interface TravelerProfile {
  nickname: string
  member_type: 'adult' | 'child' | 'senior' | 'other'
  birth_year: number | null
  discount_eligibilities: string[]
  dietary_restrictions: string[]
  allergies: string[]
  health_notes: string
  mobility_notes: string
  travel_preferences: string[]
  sensitive_visibility: 'family' | 'private'
  version: number
}

export interface FamilyMember {
  membership_id: string
  user_id: string
  username: string
  email: string | null
  display_name: string
  role: FamilySummary['role']
  joined_at: string
  profile: TravelerProfile
}

export interface CreateMemberInput {
  username: string
  email: string
  display_name: string
  password: string
  role: 'admin' | 'member' | 'guest'
  profile: Omit<TravelerProfile, 'version'>
}

export interface FamilyInvite {
  id: string
  family_id: string
  role: 'admin' | 'member' | 'guest'
  status: 'active' | 'accepted' | 'revoked' | 'expired'
  created_by_user_id: string
  created_at: string
  expires_at: string
  accepted_by_user_id: string | null
}

export interface InviteRegistrationInput {
  code: string
  username: string
  email: string
  display_name: string
  password: string
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

export async function renameFamily(
  familyId: string,
  name: string,
  csrfToken: string,
): Promise<SessionData> {
  const response = await fetch(`/api/v1/families/${familyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ name }),
  })
  return (await parse<Envelope<SessionData>>(response)).data
}

export async function listFamilyMembers(familyId: string, signal?: AbortSignal): Promise<FamilyMember[]> {
  const response = await fetch(`/api/v1/families/${familyId}/members`, { signal })
  return (await parse<Envelope<FamilyMember[]>>(response)).data
}

export async function createFamilyMember(
  familyId: string,
  input: CreateMemberInput,
  csrfToken: string,
): Promise<string> {
  const response = await fetch(`/api/v1/families/${familyId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ ...input, email: input.email || null }),
  })
  return (await parse<Envelope<{ id: string }>>(response)).data.id
}

export async function updateTravelerProfile(
  familyId: string,
  membershipId: string,
  profile: TravelerProfile,
  csrfToken: string,
): Promise<TravelerProfile> {
  const response = await fetch(`/api/v1/families/${familyId}/members/${membershipId}/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ ...profile, expected_version: profile.version }),
  })
  return (await parse<Envelope<TravelerProfile>>(response)).data
}

export async function changeFamilyRole(
  familyId: string,
  membershipId: string,
  role: 'admin' | 'member' | 'guest',
  csrfToken: string,
): Promise<void> {
  const response = await fetch(`/api/v1/families/${familyId}/members/${membershipId}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ role }),
  })
  if (!response.ok) await throwProblem(response)
}

export async function removeFamilyMember(
  familyId: string,
  membershipId: string,
  csrfToken: string,
): Promise<void> {
  const response = await fetch(`/api/v1/families/${familyId}/members/${membershipId}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) await throwProblem(response)
}

export async function listFamilyInvites(
  familyId: string,
  signal?: AbortSignal,
): Promise<FamilyInvite[]> {
  const response = await fetch(`/api/v1/families/${familyId}/invites`, { signal })
  return (await parse<Envelope<FamilyInvite[]>>(response)).data
}

export async function createFamilyInvite(
  familyId: string,
  role: 'admin' | 'member' | 'guest',
  expiresInDays: number,
  csrfToken: string,
): Promise<{ invite: FamilyInvite; code: string }> {
  const response = await fetch(`/api/v1/families/${familyId}/invites`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ role, expires_in_days: expiresInDays }),
  })
  return (await parse<Envelope<{ invite: FamilyInvite; code: string }>>(response)).data
}

export async function revokeFamilyInvite(
  familyId: string,
  inviteId: string,
  csrfToken: string,
): Promise<void> {
  const response = await fetch(`/api/v1/families/${familyId}/invites/${inviteId}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) await throwProblem(response)
}

export async function acceptFamilyInvite(code: string, csrfToken: string): Promise<string> {
  const response = await fetch('/api/v1/family-invites/accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ code }),
  })
  return (await parse<Envelope<{ family_id: string }>>(response)).data.family_id
}

export async function registerWithFamilyInvite(input: InviteRegistrationInput): Promise<string> {
  const response = await fetch('/api/v1/family-invites/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...input, email: input.email || null }),
  })
  return (await parse<Envelope<{ username: string }>>(response)).data.username
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
