import { AccessExperience } from './features/access'

export function App() {
  return (
    <main className="app-shell">
      <header className="hero">
        <p className="eyebrow">SELF-HOSTED · PRIVATE BY DEFAULT</p>
        <h1>旅行规划助手</h1>
        <p className="hero-copy">
          为个人与家庭准备的自主部署旅行空间。账号、家庭和每次修改都留在你的系统中。
        </p>
      </header>
      <AccessExperience />
    </main>
  )
}
