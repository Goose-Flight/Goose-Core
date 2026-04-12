import type { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padding?: 'none' | 'sm' | 'md' | 'lg'
  hover?: boolean
}

const paddings = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
}

export function Card({ children, padding = 'md', hover, className = '', ...props }: CardProps) {
  return (
    <div
      className={`
        bg-goose-surface border border-goose-border rounded-xl
        ${hover ? 'hover:border-goose-border-subtle hover:bg-goose-surface-hover transition-colors cursor-pointer' : ''}
        ${paddings[padding]} ${className}
      `}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`flex items-center justify-between mb-3 ${className}`}>{children}</div>
}

export function CardTitle({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <h3 className={`text-sm font-semibold text-goose-text ${className}`}>{children}</h3>
}

export function CardDescription({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <p className={`text-xs text-goose-text-muted ${className}`}>{children}</p>
}
