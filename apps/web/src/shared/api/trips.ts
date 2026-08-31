import type { FamilyMember } from './access'

export interface TripRequirements {
  input_mode: 'form' | 'chat' | 'import'
  origin: string
  destinations: string[]
  start_date: string | null
  end_date: string | null
  budget_cents: number | null
  currency: string
  styles: string[]
  pace: 'leisure' | 'balanced' | 'compact' | 'custom'
  transportation: string[]
  hard_constraints: string[]
  soft_preferences: string[]
  assumptions: string[]
  source_text: string
  confirmed: boolean
}

export interface TripParticipant {
  id: string
  source_membership_id: string | null
  display_name: string
  member_type: string
  birth_year: number | null
  discount_eligibilities: string[]
  dietary_restrictions: string[]
  allergies: string[]
  health_notes: string
  mobility_notes: string
  travel_preferences: string[]
  is_temporary: boolean
}

export interface Trip {
  id: string
  family_id: string
  owner_user_id: string
  title: string
  status: 'draft'
  visibility: 'private' | 'family'
  version: number
  requirements: TripRequirements
  participants: TripParticipant[]
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface TripListItem {
  id: string
  family_id: string
  owner_user_id: string
  title: string
  status: 'draft'
  visibility: 'private' | 'family'
  version: number
  origin: string
  destinations: string[]
  start_date: string | null
  end_date: string | null
  participant_count: number
  updated_at: string
}

export interface TripVersion {
  id: string
  trip_id: string
  version_no: number
  change_type: string
  summary: string
  created_by_user_id: string
  created_at: string
  snapshot: Trip | null
}

export interface TripMutation {
  title: string
  visibility: 'private' | 'family'
  membership_ids: string[]
  requirements: TripRequirements
}

interface Envelope<T> { data: T }

export async function listTrips(familyId: string, signal?: AbortSignal): Promise<TripListItem[]> {
  const response = await fetch(`/api/v1/trips?family_id=${encodeURIComponent(familyId)}`, { signal })
  return (await parse<Envelope<TripListItem[]>>(response)).data
}

export async function listDeletedTrips(
  familyId: string,
  signal?: AbortSignal,
): Promise<TripListItem[]> {
  const response = await fetch(`/api/v1/trips/deleted?family_id=${encodeURIComponent(familyId)}`, { signal })
  return (await parse<Envelope<TripListItem[]>>(response)).data
}

export async function getTrip(tripId: string, signal?: AbortSignal): Promise<Trip> {
  const response = await fetch(`/api/v1/trips/${tripId}`, { signal })
  return (await parse<Envelope<Trip>>(response)).data
}

export async function createTrip(
  familyId: string,
  input: TripMutation,
  csrfToken: string,
): Promise<Trip> {
  const response = await fetch('/api/v1/trips', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ ...input, family_id: familyId }),
  })
  return (await parse<Envelope<Trip>>(response)).data
}

export async function updateTrip(
  tripId: string,
  version: number,
  input: TripMutation,
  csrfToken: string,
): Promise<Trip> {
  const response = await fetch(`/api/v1/trips/${tripId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ ...input, expected_version: version }),
  })
  return (await parse<Envelope<Trip>>(response)).data
}

export async function deleteTrip(tripId: string, csrfToken: string): Promise<void> {
  const response = await fetch(`/api/v1/trips/${tripId}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) await parse<never>(response)
}

export async function restoreTrip(tripId: string, csrfToken: string): Promise<Trip> {
  const response = await fetch(`/api/v1/trips/${tripId}/restore`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  return (await parse<Envelope<Trip>>(response)).data
}

export async function listTripVersions(tripId: string, signal?: AbortSignal): Promise<TripVersion[]> {
  const response = await fetch(`/api/v1/trips/${tripId}/versions`, { signal })
  return (await parse<Envelope<TripVersion[]>>(response)).data
}

export function memberIds(trip: Trip, members: FamilyMember[]): string[] {
  const available = new Set(members.map((member) => member.membership_id))
  return trip.participants
    .map((participant) => participant.source_membership_id)
    .filter((id): id is string => id !== null && available.has(id))
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let detail = `请求失败（${response.status}）`
  try {
    const problem = (await response.json()) as { detail?: string }
    detail = problem.detail ?? detail
  } catch {
    // Keep the stable local fallback.
  }
  throw new Error(detail)
}
