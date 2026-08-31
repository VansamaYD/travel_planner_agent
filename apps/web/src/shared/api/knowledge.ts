export interface PlaceCard {
  id: string
  entity_type: 'attraction' | 'restaurant' | 'hotel' | 'transport_hub' | 'other'
  name: string
  city: string
  address: string
  intro: string
  details: Record<string, unknown>
  longitude: number | null
  latitude: number | null
  confidence: number
  version: number
  last_verified_at: string | null
  expires_at: string | null
  updated_at: string
}

export interface ImageAnalysis {
  id: string
  model_name: string
  prompt_version: string
  analysis_mode: string
  status: string
  result: Record<string, unknown>
  analyzed_at: string | null
}

interface Envelope<T> { data: T; meta?: { cache_hit?: boolean } }

export async function findPlaceCards(name: string, city: string): Promise<PlaceCard[]> {
  const query = new URLSearchParams({ query: name, city })
  const response = await fetch(`/api/v1/knowledge/places?${query}`)
  return (await parse<Envelope<PlaceCard[]>>(response)).data
}

export async function analyzeImage(
  sourceUrl: string,
  mode: 'auto' | 'guide_page' | 'place_photo',
  csrfToken: string,
): Promise<{ analysis: ImageAnalysis; cacheHit: boolean }> {
  const response = await fetch('/api/v1/knowledge/images/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ source_url: sourceUrl, mode }),
  })
  const value = await parse<Envelope<ImageAnalysis>>(response)
  return { analysis: value.data, cacheHit: value.meta?.cache_hit ?? false }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T
  let detail = `请求失败（${response.status}）`
  try { detail = ((await response.json()) as { detail?: string }).detail ?? detail } catch { /* fallback */ }
  throw new Error(detail)
}
