import { useState, type ReactNode } from 'react'

interface Tab {
  id: string
  label: string
  icon?: ReactNode
  badge?: string | number
}

interface TabsProps {
  tabs: Tab[]
  defaultTab?: string
  onChange?: (tabId: string) => void
  children: (activeTab: string) => ReactNode
  className?: string
}

export function Tabs({ tabs, defaultTab, onChange, children, className = '' }: TabsProps) {
  const [active, setActive] = useState(defaultTab || tabs[0]?.id || '')

  const handleChange = (tabId: string) => {
    setActive(tabId)
    onChange?.(tabId)
  }

  return (
    <div className={className}>
      <div className="flex gap-1 border-b border-goose-border mb-4 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleChange(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap
              border-b-2 transition-colors cursor-pointer
              ${
                active === tab.id
                  ? 'border-goose-accent text-goose-accent'
                  : 'border-transparent text-goose-text-muted hover:text-goose-text hover:border-goose-border-subtle'
              }
            `}
          >
            {tab.icon}
            {tab.label}
            {tab.badge !== undefined && (
              <span className="ml-1 px-1.5 py-0.5 text-[10px] rounded-full bg-goose-surface-hover">
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>
      {children(active)}
    </div>
  )
}
