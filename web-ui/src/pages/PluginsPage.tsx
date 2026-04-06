import React, { useEffect, useState } from 'react'
import { getPlugins } from '../lib/api'
import { Plugin } from '../lib/types'

export function PluginsPage() {
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchPlugins = async () => {
      try {
        setLoading(true)
        const data = await getPlugins()
        setPlugins(data)
        setError(null)
      } catch (err) {
        setError('Failed to load plugins')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    fetchPlugins()
  }, [])

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-bold mb-6">Active Plugins</h2>

        {loading && (
          <div className="text-center py-12">
            <p className="text-gray-500">Loading plugins...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-4">
            <p className="text-red-700">{error}</p>
          </div>
        )}

        {!loading && !error && plugins.length === 0 && (
          <div className="text-center py-12">
            <p className="text-gray-500">No plugins available</p>
          </div>
        )}

        {!loading && !error && plugins.length > 0 && (
          <div className="grid gap-4">
            {plugins.map((plugin) => (
              <div
                key={plugin.id}
                className="border rounded-lg p-6 hover:border-blue-400 hover:bg-blue-50 transition"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900">
                      {plugin.name}
                    </h3>
                    {plugin.description && (
                      <p className="text-gray-600 text-sm mt-1">
                        {plugin.description}
                      </p>
                    )}
                    <p className="text-xs text-gray-500 mt-2">
                      v{plugin.version}
                    </p>
                  </div>
                  <div className="ml-4">
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        plugin.enabled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {plugin.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
