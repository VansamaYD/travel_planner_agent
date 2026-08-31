export interface ItineraryItem {
  logical_id: string | null
  item_type: 'place' | 'restaurant' | 'hotel' | 'rest' | 'transport' | 'free_time' | 'other'
  title: string
  place_name: string
  start_time: string | null
  end_time: string | null
  cost_cents: number | null
  execution_status: 'candidate' | 'planned' | 'confirmed' | 'booked' | 'completed' | 'skipped' | 'cancelled'
  notes: string
  tags: string[]
  transport_to_next: string | null
  travel_minutes_to_next: number | null
  travel_cost_cents_to_next: number | null
}

export interface ItineraryDay {
  id: string | null
  local_date: string
  city: string
  summary: string
  items: ItineraryItem[]
}

export interface ItineraryPlan {
  id: string
  trip_id: string
  version: number
  days: ItineraryDay[]
  currency: string
  estimated_total_cost_cents: number
  warnings: string[]
  created_by_user_id: string
  created_at: string
}

interface Envelope<T> { data: T }

export async function getItinerary(tripId: string, signal?: AbortSignal): Promise<ItineraryPlan | null> {
  const response = await fetch(`/api/v1/trips/${tripId}/itinerary`, { signal })
  if (response.status === 404) return null
  return (await parse<Envelope<ItineraryPlan>>(response)).data
}

export async function initializeItinerary(tripId: string, csrfToken: string): Promise<ItineraryPlan> {
  const response = await fetch(`/api/v1/trips/${tripId}/itinerary/initialize`, {
    method: 'POST', headers: { 'X-CSRF-Token': csrfToken },
  })
  return (await parse<Envelope<ItineraryPlan>>(response)).data
}

export async function updateItinerary(
  tripId: string,
  version: number,
  days: ItineraryDay[],
  csrfToken: string,
): Promise<ItineraryPlan> {
  const response = await fetch(`/api/v1/trips/${tripId}/itinerary`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ expected_version: version, days }),
  })
  return (await parse<Envelope<ItineraryPlan>>(response)).data
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let detail = `请求失败（${response.status}）`
  try { detail = ((await response.json()) as { detail?: string }).detail ?? detail } catch { /* fallback */ }
  throw new Error(detail)
}
