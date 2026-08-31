import { useState } from 'react'

import { logout, type SessionData } from '../../shared/api/access'
import { SystemStatus } from '../system-status'
import { FamilyMembers } from './FamilyMembers'

interface DashboardProps {
  session: SessionData
  onLoggedOut: () => void
}

const roleLabels = { owner: '家庭所有者', admin: '家庭管理员', member: '成员', guest: '访客' }

export function Dashboard({ session, onLoggedOut }: DashboardProps) {
  const [loggingOut, setLoggingOut] = useState(false)
  const [activeFamilyId, setActiveFamilyId] = useState(session.families[0]?.id ?? '')
  const activeFamily = session.families.find((family) => family.id === activeFamilyId)

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
    <>
      <section className="welcome-panel panel" aria-labelledby="welcome-title">
        <div>
          <p className="section-kicker">YOUR TRAVEL SPACE</p>
          <h2 id="welcome-title">你好，{session.user.display_name}</h2>
          <p className="muted">账号与家庭基础已经就绪，可以开始创建旅行。</p>
        </div>
        <button className="text-button" disabled={loggingOut} onClick={() => void signOut()} type="button">
          {loggingOut ? '退出中…' : '退出登录'}
        </button>
      </section>

      <section className="panel" aria-labelledby="family-title">
        <div className="section-heading">
          <span className="section-number">01</span>
          <div>
            <p className="section-kicker">FAMILY CONTEXT</p>
            <h2 id="family-title">我的家庭</h2>
          </div>
        </div>
        <ul className="family-list">
          {session.families.map((family) => (
            <li className={family.id === activeFamilyId ? 'is-active' : ''} key={family.id}>
              <div>
                <strong>{family.name}</strong>
                <small>{roleLabels[family.role]}</small>
              </div>
              <button className="family-switch" onClick={() => setActiveFamilyId(family.id)} type="button">{family.id === activeFamilyId ? '当前' : '切换'}</button>
            </li>
          ))}
        </ul>
      </section>

      {activeFamily && <FamilyMembers family={activeFamily} session={session} />}

      <section className="panel next-action" aria-labelledby="next-action-title">
        <p className="section-kicker">NEXT VERTICAL SLICE</p>
        <h2 id="next-action-title">创建第一趟旅行</h2>
        <p className="muted">成员与偏好档案已经就绪，下一步接入旅行草稿、参与者快照和版本历史。</p>
        <button className="primary-button" disabled type="button">即将开放</button>
      </section>

      <SystemStatus />
    </>
  )
}
