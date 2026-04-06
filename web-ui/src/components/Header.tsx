import React from 'react'

interface HeaderProps {
  currentPage: 'analyze' | 'plugins' | 'settings'
  onNavigate: (page: 'analyze' | 'plugins' | 'settings') => void
}

export function Header({ currentPage, onNavigate }: HeaderProps) {
  return (
    <header className="bg-blue-600 text-white shadow-md">
      <div className="max-w-7xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Goose Flight Analyzer</h1>
          <nav className="flex gap-6">
            <button
              onClick={() => onNavigate('analyze')}
              className={`px-4 py-2 rounded ${
                currentPage === 'analyze'
                  ? 'bg-white text-blue-600'
                  : 'hover:bg-blue-500'
              }`}
            >
              Analyze
            </button>
            <button
              onClick={() => onNavigate('plugins')}
              className={`px-4 py-2 rounded ${
                currentPage === 'plugins'
                  ? 'bg-white text-blue-600'
                  : 'hover:bg-blue-500'
              }`}
            >
              Plugins
            </button>
            <button
              onClick={() => onNavigate('settings')}
              className={`px-4 py-2 rounded ${
                currentPage === 'settings'
                  ? 'bg-white text-blue-600'
                  : 'hover:bg-blue-500'
              }`}
            >
              Settings
            </button>
          </nav>
        </div>
      </div>
    </header>
  )
}
