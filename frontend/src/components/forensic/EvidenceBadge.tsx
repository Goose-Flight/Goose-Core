import { useState } from 'react'

interface EvidenceBadgeProps {
  hash: string
  algorithm?: 'SHA-256' | 'SHA-512'
  verified?: boolean
  timestamp?: string
  className?: string
}

export function EvidenceBadge({
  hash,
  algorithm = 'SHA-256',
  verified = true,
  timestamp,
  className = '',
}: EvidenceBadgeProps) {
  const [expanded, setExpanded] = useState(false)
  const shortHash = hash.slice(0, 12) + '...'

  return (
    <div className={`inline-flex flex-col ${className}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`
          inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono
          transition-colors cursor-pointer
          ${
            verified
              ? 'bg-goose-success/10 text-goose-success hover:bg-goose-success/15'
              : 'bg-goose-error/10 text-goose-error hover:bg-goose-error/15'
          }
        `}
      >
        {verified ? (
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ) : (
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        )}
        <span>{algorithm}: {shortHash}</span>
        <span>{verified ? 'Verified' : 'Mismatch'}</span>
      </button>

      {expanded && (
        <div className="mt-1 px-3 py-2 rounded-md bg-goose-surface border border-goose-border text-xs font-mono text-goose-text-secondary break-all">
          <div><span className="text-goose-text-muted">Hash:</span> {hash}</div>
          <div><span className="text-goose-text-muted">Algorithm:</span> {algorithm}</div>
          {timestamp && <div><span className="text-goose-text-muted">Ingested:</span> {timestamp}</div>}
          <div>
            <span className="text-goose-text-muted">Status:</span>{' '}
            <span className={verified ? 'text-goose-success' : 'text-goose-error'}>
              {verified ? 'Integrity verified - evidence unmodified' : 'HASH MISMATCH - evidence may be tampered'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
