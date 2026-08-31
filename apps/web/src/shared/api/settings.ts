export interface IntegrationSetting {
  key: string
  label: string
  group: string
  kind: 'text' | 'password' | 'url' | 'boolean' | 'number'
  secret: boolean
  configured: boolean
  value: string | number | boolean | null
  source: 'environment' | 'settings'
  implemented: boolean
}

interface Envelope {
  data: IntegrationSetting[]
  meta: { restart_required: boolean; message?: string }
}

export async function listIntegrationSettings(signal?: AbortSignal): Promise<IntegrationSetting[]> {
  const response = await fetch('/api/v1/settings/integrations', { signal })
  return (await parse(response)).data
}

export async function updateIntegrationSettings(
  values: Record<string, string | number | boolean | null>,
  csrfToken: string,
): Promise<Envelope> {
  const response = await fetch('/api/v1/settings/integrations', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ values }),
  })
  return await parse(response)
}

async function parse(response: Response): Promise<Envelope> {
  if (response.ok) return (await response.json()) as Envelope
  let detail = `请求失败（${response.status}）`
  try { detail = ((await response.json()) as { detail?: string }).detail ?? detail } catch { /* fallback */ }
  throw new Error(detail)
}
