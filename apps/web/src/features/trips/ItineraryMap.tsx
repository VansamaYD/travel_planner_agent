import { useEffect, useMemo, useRef, useState } from 'react'

import { getItineraryMap, type ItineraryMapData } from '../../shared/api/itinerary'

interface Props { tripId: string; selectedDay: number | null }

interface AMapInstance { add(value: object): void; destroy(): void; setFitView(): void }
interface AMapConstructor {
  Map: new (element: HTMLElement, options: object) => AMapInstance
  Marker: new (options: object) => object
  Polyline: new (options: object) => object
}

export function ItineraryMap({ tripId, selectedDay }: Props) {
  const [data, setData] = useState<ItineraryMapData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const elementRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    void getItineraryMap(tripId, selectedDay, controller.signal)
      .then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(messageOf(reason)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [tripId, selectedDay])

  const points = useMemo(
    () => (data?.points ?? []).filter((point) => selectedDay === null || point.day_index === selectedDay),
    [data, selectedDay],
  )

  useEffect(() => {
    const element = elementRef.current
    if (!element || !data?.enabled) return
    const resolved = points.filter((point) => point.longitude !== null && point.latitude !== null)
    if (resolved.length === 0) return
    let map: AMapInstance | null = null
    let cancelled = false
    void loadAmap(data.js_api_key, data.js_security_key).then((AMap) => {
      if (cancelled) return
      const overlays = resolved.map((point, index) => new AMap.Marker({
        position: [point.longitude, point.latitude],
        title: `${index + 1}. ${point.title}`,
        label: { content: String(index + 1), direction: 'top' },
      }))
      if (resolved.length > 1) overlays.push(new AMap.Polyline({
        path: resolved.map((point) => [point.longitude, point.latitude]),
        strokeColor: '#315945', strokeWeight: 5, strokeOpacity: 0.72,
      }))
      map = new AMap.Map(element, { zoom: 12, viewMode: '2D', mapStyle: 'amap://styles/fresh', features: ['bg', 'road', 'point'] })
      for (const overlay of overlays) map.add(overlay)
      map.setFitView()
    }).catch((reason: unknown) => setError(messageOf(reason)))
    return () => { cancelled = true; map?.destroy() }
  }, [data, points])

  return <div className="itinerary-map-view">
    {loading && <p className="muted">正在查询并缓存行程地点…</p>}
    {error && <p className="form-error">{error}</p>}
    {data?.enabled && points.some((point) => point.status === 'resolved') && <div className="amap-canvas" ref={elementRef} />}
    {data && !data.enabled && <p className="map-notice">尚未配置高德 JS API Key，仍可使用下方地点链接在高德地图中打开。</p>}
    <ol className="map-route-list">{points.map((point, index) => <li key={`${point.logical_id}-${index}`}>
      <span>{index + 1}</span><div><strong>{point.title}</strong><small>{point.address || point.place_name} · 第 {point.day_index + 1} 天</small></div><a href={point.map_url} rel="noreferrer" target="_blank">地图</a>
    </li>)}</ol>
    {data && points.length === 0 && <p className="muted">当前日期还没有可显示的地点。</p>}
    {data?.warnings.map((warning) => <p className="map-notice" key={warning}>{warning}</p>)}
  </div>
}

let amapPromise: Promise<AMapConstructor> | null = null

function loadAmap(key: string, securityKey: string): Promise<AMapConstructor> {
  if (amapPromise) return amapPromise
  amapPromise = new Promise((resolve, reject) => {
    const target = window as unknown as { AMap?: AMapConstructor; _AMapSecurityConfig?: { securityJsCode: string } }
    if (target.AMap) { resolve(target.AMap); return }
    target._AMapSecurityConfig = { securityJsCode: securityKey }
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`
    script.async = true
    script.onload = () => target.AMap ? resolve(target.AMap) : reject(new Error('高德地图初始化失败'))
    script.onerror = () => reject(new Error('高德地图脚本加载失败'))
    document.head.appendChild(script)
  })
  return amapPromise
}

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : '地图加载失败'
}
