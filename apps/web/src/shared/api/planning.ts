import type { ItineraryDay } from './itinerary'

export interface PlanningRun {
  id: string
  trip_id: string
  status: 'running' | 'succeeded' | 'failed'
  profile: 'PLAN_STANDARD' | 'PLAN_DEEP'
  current_node: string
  base_trip_version: number
  base_itinerary_version: number
  error: string
  created_at: string
  completed_at: string | null
}

export interface PlanningProposal {
  id: string
  run_id: string
  trip_id: string
  status: 'pending' | 'applied' | 'rejected' | 'expired'
  base_itinerary_version: number
  summary: string
  rationale: string
  days: ItineraryDay[]
  warnings: string[]
  input_tokens: number
  output_tokens: number
  cache_hit_tokens: number
  estimated_cost_microusd: number
  created_at: string
  applied_at: string | null
}

interface StartResult { run: PlanningRun; proposal: PlanningProposal | null }
interface Envelope<T> { data: T }

export async function startPlanning(
  tripId: string,
  profile: PlanningRun['profile'],
  instruction: string,
  csrfToken: string,
): Promise<StartResult> {
  const response = await fetch(`/api/v1/trips/${tripId}/planning-runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ profile, instruction }),
  })
  return (await parse<Envelope<StartResult>>(response)).data
}

export async function listPlanningProposals(
  tripId: string,
  signal?: AbortSignal,
): Promise<PlanningProposal[]> {
  const response = await fetch(`/api/v1/trips/${tripId}/proposals`, { signal })
  return (await parse<Envelope<PlanningProposal[]>>(response)).data
}

export async function applyPlanningProposal(
  proposalId: string,
  csrfToken: string,
): Promise<PlanningProposal> {
  const response = await fetch(`/api/v1/proposals/${proposalId}/apply`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrfToken },
  })
  return (await parse<Envelope<PlanningProposal>>(response)).data
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let detail = `请求失败（${response.status}）`
  try { detail = ((await response.json()) as { detail?: string }).detail ?? detail } catch { /* fallback */ }
  throw new Error(detail)
}
