import { useLocation, useNavigate } from 'react-router-dom'
import { useUIStore } from '@/stores/uiStore'
import { useAnalysisStore } from '@/stores/analysisStore'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  section?: string
  color?: string
}

// Simple SVG icon components
const Icon = ({ d, className = '' }: { d: string; className?: string }) => (
  <svg className={`w-5 h-5 ${className}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={d} />
  </svg>
)

const mainNav: NavItem[] = [
  { path: '/', label: 'Dashboard', section: 'ANALYSIS', icon: <Icon d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /> },
  { path: '/analyze', label: 'Quick Analysis', icon: <Icon d="M13 10V3L4 14h7v7l9-11h-7z" /> },
]

const subsystemNav: (Omit<NavItem, 'path'> & { subpath: string })[] = [
  { subpath: '', label: 'Overview', section: 'RESULTS', icon: <Icon d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />, color: 'text-goose-accent' },
  { subpath: '/motors', label: 'Motors', icon: <span className="text-base">⚙️</span>, color: 'text-goose-chart-1' },
  { subpath: '/battery', label: 'Battery', icon: <span className="text-base">🔋</span>, color: 'text-goose-chart-3' },
  { subpath: '/gps', label: 'GPS / Nav', icon: <span className="text-base">📡</span>, color: 'text-goose-chart-7' },
  { subpath: '/vibration', label: 'Vibration', icon: <span className="text-base">📳</span>, color: 'text-goose-chart-4' },
  { subpath: '/control', label: 'Control', icon: <span className="text-base">🎮</span>, color: 'text-goose-chart-5' },
  { subpath: '/environment', label: 'Environment', icon: <span className="text-base">🌬️</span>, color: 'text-goose-chart-2' },
  { subpath: '/flight-path', label: 'Flight Path', icon: <span className="text-base">🗺️</span>, color: 'text-goose-accent' },
  { subpath: '/timeline', label: 'Timeline', icon: <span className="text-base">📊</span>, color: 'text-goose-chart-6' },
]

const proNav: NavItem[] = [
  { path: '/pro/campaigns', label: 'Campaigns', section: 'VALIDATION', icon: <Icon d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /> },
  { path: '/pro/fleet', label: 'Nav Systems', icon: <Icon d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /> },
  { path: '/pro/reports', label: 'Reports', section: 'REPORTING', icon: <Icon d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /> },
  { path: '/pro/users', label: 'Users', section: 'ADMIN', icon: <Icon d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" /> },
  { path: '/pro/audit', label: 'Audit Trail', icon: <Icon d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" /> },
]

const campaignSubNav: (Omit<NavItem, 'path'> & { subpath: string })[] = [
  { subpath: '', label: 'Overview', section: 'CAMPAIGN', icon: <Icon d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />, color: 'text-goose-accent' },
  { subpath: '/accuracy', label: 'Accuracy', icon: <span className="text-base">🎯</span>, color: 'text-goose-chart-1' },
  { subpath: '/trajectory', label: 'Trajectory', icon: <span className="text-base">🗺️</span>, color: 'text-goose-chart-2' },
  { subpath: '/gps-denial', label: 'GPS Denial', icon: <span className="text-base">📡</span>, color: 'text-goose-chart-7' },
]

const bottomNav: NavItem[] = [
  { path: '/cases', label: 'Cases', section: 'INVESTIGATION', icon: <Icon d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /> },
  { path: '/fleet', label: 'Drone Fleet', section: 'FLEET', icon: <Icon d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /> },
  { path: '/settings', label: 'Settings', section: 'UTILITIES', icon: <Icon d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /> },
]

function NavButton({ item, isActive, collapsed, onClick }: {
  item: NavItem
  isActive: boolean
  collapsed: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer mb-0.5
        ${isActive
          ? 'bg-goose-accent/10 text-goose-accent'
          : 'text-goose-text-secondary hover:bg-goose-surface-hover hover:text-goose-text'
        }
      `}
      title={collapsed ? item.label : undefined}
    >
      <span className="shrink-0 w-5 h-5 flex items-center justify-center">{item.icon}</span>
      {!collapsed && <span className="truncate">{item.label}</span>}
    </button>
  )
}

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { sidebarCollapsed, toggleSidebar } = useUIStore()
  const { currentAnalysis } = useAnalysisStore()

  // Detect if we're in an analysis context
  const analysisMatch = location.pathname.match(/^\/analyze\/([^/]+)/)
  const analysisId = analysisMatch?.[1] || currentAnalysis?.quick_analysis_id
  const hasAnalysis = !!analysisId

  // Detect if we're in a campaign context
  const campaignMatch = location.pathname.match(/^\/pro\/campaigns\/([^/]+)/)
  const campaignId = campaignMatch?.[1]
  const hasCampaign = !!campaignId

  let lastSection = ''

  const renderSection = (section: string) => {
    if (section === lastSection || sidebarCollapsed) return null
    lastSection = section
    return (
      <div className="px-3 pt-4 pb-1 text-[10px] font-semibold text-goose-text-muted uppercase tracking-widest">
        {section}
      </div>
    )
  }

  return (
    <aside
      className={`
        flex flex-col h-screen bg-goose-surface border-r border-goose-border
        transition-all duration-200 shrink-0
        ${sidebarCollapsed ? 'w-16' : 'w-56'}
      `}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-14 border-b border-goose-border shrink-0">
        <div
          className="w-8 h-8 rounded-lg bg-goose-accent/20 flex items-center justify-center shrink-0 cursor-pointer"
          onClick={() => navigate('/')}
        >
          <span className="text-lg">🪿</span>
        </div>
        {!sidebarCollapsed && (
          <div className="cursor-pointer" onClick={() => navigate('/')}>
            <div className="text-sm font-bold text-goose-text tracking-tight">GOOSE</div>
            <div className="text-[10px] text-goose-text-muted">Flight Forensics</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {/* Main nav */}
        {mainNav.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path === '/analyze' && location.pathname.startsWith('/analyze'))
          return (
            <div key={item.path}>
              {item.section && renderSection(item.section)}
              <NavButton
                item={item}
                isActive={isActive && !hasAnalysis}
                collapsed={sidebarCollapsed}
                onClick={() => navigate(item.path)}
              />
            </div>
          )
        })}

        {/* Subsystem nav — only when analysis is loaded */}
        {hasAnalysis && (
          <>
            {!sidebarCollapsed && (
              <div className="px-3 pt-4 pb-1 text-[10px] font-semibold text-goose-text-muted uppercase tracking-widest">
                RESULTS
              </div>
            )}
            {sidebarCollapsed && <div className="my-2 mx-2 border-t border-goose-border" />}
            {subsystemNav.map((item) => {
              const fullPath = `/analyze/${analysisId}${item.subpath}`
              const isActive = item.subpath === ''
                ? location.pathname === fullPath
                : location.pathname.startsWith(fullPath)
              return (
                <NavButton
                  key={item.subpath || 'overview'}
                  item={{ ...item, path: fullPath }}
                  isActive={isActive}
                  collapsed={sidebarCollapsed}
                  onClick={() => navigate(fullPath)}
                />
              )
            })}
          </>
        )}

        {/* Separator */}
        <div className="my-2 mx-2 border-t border-goose-border" />

        {/* Pro sections */}
        {(() => { lastSection = '' })()}
        {proNav.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path))
          return (
            <div key={item.path}>
              {item.section && renderSection(item.section)}
              <NavButton
                item={item}
                isActive={isActive}
                collapsed={sidebarCollapsed}
                onClick={() => navigate(item.path)}
              />
            </div>
          )
        })}

        {/* Campaign subsystem nav — only when in a campaign */}
        {hasCampaign && (
          <>
            {!sidebarCollapsed && (
              <div className="px-3 pt-4 pb-1 text-[10px] font-semibold text-goose-text-muted uppercase tracking-widest">
                CAMPAIGN
              </div>
            )}
            {campaignSubNav.map((item) => {
              const fullPath = `/pro/campaigns/${campaignId}${item.subpath}`
              const isActive = item.subpath === ''
                ? location.pathname === fullPath
                : location.pathname.startsWith(fullPath)
              return (
                <NavButton
                  key={item.subpath || 'campaign-overview'}
                  item={{ ...item, path: fullPath }}
                  isActive={isActive}
                  collapsed={sidebarCollapsed}
                  onClick={() => navigate(fullPath)}
                />
              )
            })}
          </>
        )}

        {/* Bottom nav */}
        {bottomNav.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path !== '/' && location.pathname.startsWith(item.path))
          return (
            <div key={item.path}>
              {item.section && renderSection(item.section)}
              <NavButton
                item={item}
                isActive={isActive}
                collapsed={sidebarCollapsed}
                onClick={() => navigate(item.path)}
              />
            </div>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-goose-border shrink-0">
        {!sidebarCollapsed && (
          <div className="text-[10px] text-goose-text-muted text-center">
            Goose v1.3.5 &middot; <span className="text-goose-accent font-semibold">PRO</span>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="w-full mt-2 flex items-center justify-center p-1.5 rounded-lg text-goose-text-muted hover:bg-goose-surface-hover transition-colors cursor-pointer"
        >
          <svg className={`w-4 h-4 transition-transform ${sidebarCollapsed ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
          </svg>
        </button>
      </div>
    </aside>
  )
}
