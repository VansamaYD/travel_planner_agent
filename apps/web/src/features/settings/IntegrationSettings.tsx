import { useEffect, useMemo, useState } from 'react'

import type { SessionData } from '../../shared/api/access'
import { listIntegrationSettings, updateIntegrationSettings, type IntegrationSetting } from '../../shared/api/settings'

export function IntegrationSettings({ session }: { session: SessionData }) {
  const [settings, setSettings] = useState<IntegrationSetting[]>([])
  const [changes, setChanges] = useState<Record<string, string | number | boolean | null>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void listIntegrationSettings(controller.signal).then(setSettings).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '读取连接设置失败')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  const groups = useMemo(() => [...new Set(settings.map((item) => item.group))], [settings])

  async function save() {
    if (!Object.keys(changes).length || saving) return
    setSaving(true); setError(''); setMessage('')
    try {
      const response = await updateIntegrationSettings(changes, session.csrf_token)
      setSettings(response.data)
      setChanges({})
      setMessage(response.meta.message ?? '配置已保存。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存连接设置失败')
    } finally { setSaving(false) }
  }

  if (loading) return <section className="panel"><p className="muted">正在读取外部连接设置…</p></section>
  return <section className="panel integration-settings" aria-labelledby="integration-settings-title">
    <div className="section-heading"><span className="section-number">04</span><div><p className="section-kicker">INTEGRATIONS</p><h2 id="integration-settings-title">模型与外部连接</h2><p className="muted">密钥加密保存在独立 config 目录；空白密钥表示保留现值。</p></div></div>
    {groups.map((group) => <fieldset key={group}><legend>{group}</legend><div className="integration-fields">{settings.filter((item) => item.group === group).map((item) => <IntegrationInput changes={changes} item={item} key={item.key} onChange={(value) => setChanges((current) => ({ ...current, [item.key]: value }))} />)}</div></fieldset>)}
    {error && <p className="form-error">{error}</p>}
    {message && <p className="settings-notice">{message}</p>}
    <footer><button className="primary-button" disabled={saving || !Object.keys(changes).length} onClick={() => void save()} type="button">{saving ? '保存中…' : '加密保存配置'}</button><small>保存后执行一次容器重启即可应用，无需修改 .env。</small></footer>
  </section>
}

function IntegrationInput({ item, changes, onChange }: {
  item: IntegrationSetting
  changes: Record<string, string | number | boolean | null>
  onChange: (value: string | number | boolean | null) => void
}) {
  const changed = Object.hasOwn(changes, item.key)
  const current = changed ? changes[item.key] : item.value
  return <label className={item.implemented ? '' : 'is-future'}><span>{item.label}{!item.implemented && <em>预留</em>}</span>{item.kind === 'boolean'
    ? <input checked={Boolean(current)} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
    : <div><input inputMode={item.kind === 'number' ? 'numeric' : undefined} onChange={(event) => onChange(item.kind === 'number' ? Number(event.target.value) : event.target.value)} placeholder={item.secret && item.configured ? '已配置；输入新值可替换' : ''} type={item.kind === 'password' ? 'password' : item.kind === 'url' ? 'url' : item.kind === 'number' ? 'number' : 'text'} value={typeof current === 'string' || typeof current === 'number' ? current : ''} />{item.secret && item.configured && <button onClick={() => onChange(null)} type="button">清除</button>}</div>}<small>{item.configured ? `已配置 · ${item.source === 'settings' ? '设置页' : '环境变量'}` : '未配置'}</small></label>
}
