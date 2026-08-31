export interface HealthCheck {
  name: string
  status: string
  detail: string | null
}

export interface HealthResponse {
  status: 'ready' | 'not_ready'
  version: string
  checks: HealthCheck[]
}

export async function getReadiness(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/health/ready', {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok && response.status !== 503) {
    throw new Error(`服务返回 ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}
