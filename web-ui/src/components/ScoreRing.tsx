import React from 'react'

interface ScoreRingProps {
  score: number
  maxScore?: number
  label?: string
}

export function ScoreRing({ score, maxScore = 100, label }: ScoreRingProps) {
  const radius = 45
  const circumference = 2 * Math.PI * radius
  const percentage = Math.min(score, maxScore) / maxScore
  const offset = circumference * (1 - percentage)

  const getColor = () => {
    if (percentage >= 0.8) return '#10b981' // green
    if (percentage >= 0.5) return '#f59e0b' // amber
    return '#ef4444' // red
  }

  return (
    <div className="flex flex-col items-center justify-center">
      <svg width="120" height="120" viewBox="0 0 120 120">
        {/* Background circle */}
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="8"
        />
        {/* Progress circle */}
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={getColor()}
          strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transform: 'rotate(-90deg)', transformOrigin: '60px 60px' }}
        />
        {/* Score text */}
        <text
          x="60"
          y="60"
          textAnchor="middle"
          dy="0.3em"
          className="text-2xl font-bold fill-gray-900"
        >
          {Math.round(score)}
        </text>
      </svg>
      {label && <p className="mt-2 text-sm text-gray-600">{label}</p>}
    </div>
  )
}
