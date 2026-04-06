import React, { useState } from 'react'
import { Header } from './components/Header'
import { AnalyzePage } from './pages/AnalyzePage'
import { PluginsPage } from './pages/PluginsPage'

type Page = 'analyze' | 'plugins' | 'settings'

function App() {
  const [currentPage, setCurrentPage] = useState<Page>('analyze')

  const renderPage = () => {
    switch (currentPage) {
      case 'analyze':
        return <AnalyzePage />
      case 'plugins':
        return <PluginsPage />
      case 'settings':
        return (
          <div className="bg-white rounded-lg shadow p-8">
            <h2 className="text-2xl font-bold">Settings</h2>
            <p className="text-gray-600 mt-4">Settings page coming soon.</p>
          </div>
        )
      default:
        return <AnalyzePage />
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header currentPage={currentPage} onNavigate={setCurrentPage} />
      <main className="max-w-7xl mx-auto px-6 py-8">
        {renderPage()}
      </main>
    </div>
  )
}

export default App
