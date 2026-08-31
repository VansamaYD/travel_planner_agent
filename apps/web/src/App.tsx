import { SystemStatus } from './features/system-status'

const nextSlices = [
  '初始化、登录与家庭',
  '旅行草稿与版本历史',
  '地图、路线与天气连接',
  '智能体提案与确认',
]

export function App() {
  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">SELF-HOSTED · SLICE 0</p>
        <h1>旅行规划助手</h1>
        <p className="hero-copy">
          工程底座已经运行。接下来会在同一套版本、审计和授权机制上逐步增加旅行规划能力。
        </p>
      </header>

      <SystemStatus />

      <section className="panel" aria-labelledby="next-title">
        <div className="section-heading">
          <span className="section-number">02</span>
          <div>
            <p className="section-kicker">IMPLEMENTATION ROADMAP</p>
            <h2 id="next-title">下一批纵向切片</h2>
          </div>
        </div>
        <ol className="slice-list">
          {nextSlices.map((slice, index) => (
            <li key={slice}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              {slice}
            </li>
          ))}
        </ol>
      </section>
    </main>
  )
}
