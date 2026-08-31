import { useState } from 'react'

import { logout, type SessionData } from '../../shared/api/access'
import { SystemStatus } from '../system-status'
import { FamilyMembers } from './FamilyMembers'
import { FamilyInvites } from './FamilyInvites'
import { JoinFamilyPrompt } from './JoinFamilyPrompt'
import { TripsWorkspace } from '../trips/TripsWorkspace'

interface DashboardProps {
  session: SessionData
  onLoggedOut: () => void
  onSessionChanged: (session: SessionData) => void
}

const roleLabels = { owner: '家庭所有者', admin: '家庭管理员', member: '成员', guest: '访客' }

export function Dashboard({ session, onLoggedOut, onSessionChanged }: DashboardProps) {
  const [page, setPage] = useState<'chat' | 'trips' | 'today' | 'settings'>('chat')
  const [loggingOut, setLoggingOut] = useState(false)
  const [activeFamilyId, setActiveFamilyId] = useState(session.families[0]?.id ?? '')
  const activeFamily = session.families.find((family) => family.id === activeFamilyId) ?? session.families[0]
  const selectedFamilyId = activeFamily?.id ?? ''
  const inviteCode = window.location.hash.match(/^#invite=([A-Z2-7-]{20,64})$/i)?.[1] ?? ''
  const [joinCode, setJoinCode] = useState<string | null>(inviteCode || null)

  async function signOut() {
    setLoggingOut(true)
    try {
      await logout(session.csrf_token)
      onLoggedOut()
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <main className="workspace-shell">
      {joinCode !== null && <JoinFamilyPrompt initialCode={joinCode} session={session} onAccepted={(updated) => {
        setJoinCode(null)
        onSessionChanged(updated)
      }} />}
      <header className="workspace-header"><div><strong>旅行助手</strong><span>{activeFamily?.name ?? '个人空间'}</span></div><button aria-label="打开设置" onClick={() => setPage('settings')} type="button">{session.user.display_name.slice(0, 1)}</button></header>

      <div className="workspace-content">
      {page === 'chat' && <section className="chat-home"><div className="chat-welcome"><span className="chat-mark">旅</span><h1>今天想计划什么？</h1><p>可以规划新旅行、优化路线、查询天气、分析预算，或处理现有行程。</p></div><div className="prompt-grid"><button onClick={() => setPage('trips')} type="button"><strong>规划一次新旅行</strong><span>从日期、人数和偏好开始</span></button><button onClick={() => setPage('trips')} type="button"><strong>优化已有日程</strong><span>减少折返、步行或预算</span></button><button disabled type="button"><strong>查询地图与天气</strong><span>在线工具正在接入</span></button><button disabled type="button"><strong>导入订单或攻略</strong><span>支持文字、链接和截图</span></button></div><div className="chat-composer is-upcoming"><button aria-label="添加附件" disabled type="button">+</button><span>实时对话运行时将在下一个切片启用</span><button disabled type="button">↑</button></div></section>}

      {page === 'today' && <section className="page-empty panel"><p className="section-kicker">TODAY</p><h2>今日行程</h2><p>旅行开始后，这里只显示当前事项、下一站、导航、票据和风险提醒。</p><button className="primary-button" onClick={() => setPage('trips')} type="button">查看旅行</button></section>}

      {page === 'trips' && activeFamily && <TripsWorkspace family={activeFamily} session={session} />}

      {page === 'settings' && <div className="settings-page"><section className="welcome-panel panel" aria-labelledby="welcome-title"><div><p className="section-kicker">ACCOUNT</p><h2 id="welcome-title">你好，{session.user.display_name}</h2><p className="muted">在这里管理家庭、连接和系统设置。</p></div><button className="text-button" disabled={loggingOut} onClick={() => void signOut()} type="button">{loggingOut ? '退出中…' : '退出登录'}</button></section>

      <section className="panel" aria-labelledby="family-title">
        <div className="section-heading">
          <span className="section-number">01</span>
          <div>
            <p className="section-kicker">FAMILY CONTEXT</p>
            <h2 id="family-title">我的家庭</h2>
          </div>
          <button className="small-button family-join-button" onClick={() => setJoinCode((value) => value === null ? '' : null)} type="button">{joinCode === null ? '输入邀请码' : '收起'}</button>
        </div>
        <ul className="family-list">
          {session.families.map((family) => (
            <li className={family.id === selectedFamilyId ? 'is-active' : ''} key={family.id}>
              <div>
                <strong>{family.name}</strong>
                <small>{roleLabels[family.role]}</small>
              </div>
              <button className="family-switch" onClick={() => setActiveFamilyId(family.id)} type="button">{family.id === selectedFamilyId ? '当前' : '切换'}</button>
            </li>
          ))}
        </ul>
      </section>

      {activeFamily && <FamilyMembers family={activeFamily} session={session} />}
      {activeFamily && (activeFamily.role === 'owner' || activeFamily.role === 'admin') && <FamilyInvites family={activeFamily} session={session} />}
      <SystemStatus />
      </div>}
      </div>
      <nav className="bottom-nav" aria-label="主导航">{([['chat','助手','◇'],['trips','行程','▤'],['today','今日','○'],['settings','我的','☰']] as const).map(([value,label,icon]) => <button className={page === value ? 'is-active' : ''} key={value} onClick={() => setPage(value)} type="button"><span>{icon}</span>{label}</button>)}</nav>
    </main>
  )
}
