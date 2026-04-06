import React, { useState } from 'react'
import { Finding } from '../lib/types'

interface FindingsTableProps {
  findings: Finding[]
}

type SortField = 'plugin' | 'severity' | 'title'
type SortOrder = 'asc' | 'desc'

export function FindingsTable({ findings }: FindingsTableProps) {
  const [sortField, setSortField] = useState<SortField>('severity' as SortField)
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'text-red-600 bg-red-50'
      case 'warning':
        return 'text-amber-600 bg-amber-50'
      case 'info':
        return 'text-blue-600 bg-blue-50'
      default:
        return 'text-gray-600 bg-gray-50'
    }
  }

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('asc')
    }
  }

  const sortedFindings = [...findings].sort((a, b) => {
    const aVal = a[sortField]
    const bVal = b[sortField]

    if (sortField === 'severity') {
      const severityOrder = { critical: 0, warning: 1, info: 2 }
      const aScore = severityOrder[a.severity as keyof typeof severityOrder] ?? 3
      const bScore = severityOrder[b.severity as keyof typeof severityOrder] ?? 3
      return sortOrder === 'asc' ? aScore - bScore : bScore - aScore
    }

    const comparison = String(aVal).localeCompare(String(bVal))
    return sortOrder === 'asc' ? comparison : -comparison
  })

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span className="ml-1 text-gray-400">↕</span>
    return <span className="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-gray-100 border-b">
            <th className="text-left p-4">
              <button
                onClick={() => handleSort('plugin')}
                className="font-semibold hover:text-blue-600"
              >
                Plugin <SortIcon field="plugin" />
              </button>
            </th>
            <th className="text-left p-4">
              <button
                onClick={() => handleSort('severity')}
                className="font-semibold hover:text-blue-600"
              >
                Severity <SortIcon field="severity" />
              </button>
            </th>
            <th className="text-left p-4">Score</th>
            <th className="text-left p-4">
              <button
                onClick={() => handleSort('title')}
                className="font-semibold hover:text-blue-600"
              >
                Title <SortIcon field="title" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedFindings.length === 0 ? (
            <tr>
              <td colSpan={4} className="p-4 text-center text-gray-500 italic">
                No findings
              </td>
            </tr>
          ) : (
            sortedFindings.map((finding, idx) => (
              <tr key={`${finding.plugin}-${idx}`} className="border-b hover:bg-gray-50">
                <td className="p-4 font-medium text-gray-900">{finding.plugin}</td>
                <td className={`p-4 font-semibold ${getSeverityColor(finding.severity)}`}>
                  {finding.severity}
                </td>
                <td className="p-4 text-gray-700">{finding.score}</td>
                <td className="p-4 text-gray-700">
                  <div className="font-medium">{finding.title}</div>
                  <div className="text-sm text-gray-500">{finding.description}</div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
