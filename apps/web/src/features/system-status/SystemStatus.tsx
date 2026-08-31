import { useEffect, useState } from 'react'

import { getReadiness, type HealthResponse } from '../../shared/api/health'
import { formatHealthLabel } from './formatHealthLabel'

type LoadState =
  | { status: 'loading' }
  | { status: 'loaded'; data: HealthResponse }
  | { status: 'error'; message: string }

export function SystemStatus() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void getReadiness(controller.signal)
      .then((data) => setState({ status: 'loaded', data }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            message: error instanceof Error ? error.message : '无法连接服务',
          })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <section className="panel status-panel" aria-labelledby="status-title" aria-live="polite">
      <div className="section-heading">
        <span className="section-number">01</span>
        <div>
          <p className="section-kicker">SYSTEM STATUS</p>
          <h2 id="status-title">服务状态</h2>
        </div>
      </div>

      {state.status === 'loading' && <p className="muted">正在检查服务……</p>}
      {state.status === 'error' && (
        <div className="status-summary is-error">
          <strong>API 尚未连接</strong>
          <span>{state.message}</span>
        </div>
      )}
      {state.status === 'loaded' && (
        <>
          <div className={`status-summary ${state.data.status === 'ready' ? 'is-ready' : 'is-error'}`}>
            <strong>{state.data.status === 'ready' ? '系统可以开始工作' : '系统需要处理配置'}</strong>
            <span>API {state.data.version}</span>
          </div>
          <ul className="check-grid">
            {state.data.checks.map((check) => (
              <li key={check.name}>
                <span className={`status-dot status-${check.status}`} aria-hidden="true" />
                <div>
                  <strong>{formatHealthLabel(check.name)}</strong>
                  <small>{check.detail ?? check.status}</small>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
