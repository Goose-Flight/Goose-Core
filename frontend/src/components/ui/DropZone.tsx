import { useState, useCallback, useRef, type DragEvent } from 'react'

interface DropZoneProps {
  onFileDrop: (file: File) => void
  accept?: string // e.g. ".ulg,.bin,.log,.csv"
  className?: string
}

export function DropZone({ onFileDrop, accept = '.ulg,.bin,.log,.csv,.tlog', className = '' }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [fileName, setFileName] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrag = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDragIn = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragOut = useCallback((e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      const file = e.dataTransfer?.files?.[0]
      if (file) {
        setFileName(file.name)
        onFileDrop(file)
      }
    },
    [onFileDrop]
  )

  const handleClick = () => inputRef.current?.click()

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setFileName(file.name)
      onFileDrop(file)
    }
  }

  return (
    <div
      className={`
        relative flex flex-col items-center justify-center gap-3 p-8
        border-2 border-dashed rounded-xl cursor-pointer transition-all duration-200
        ${
          isDragging
            ? 'border-goose-accent bg-goose-accent/5 scale-[1.02]'
            : fileName
              ? 'border-goose-success/50 bg-goose-success/5'
              : 'border-goose-border hover:border-goose-border-subtle hover:bg-goose-surface-hover/50'
        }
        ${className}
      `}
      onDragEnter={handleDragIn}
      onDragLeave={handleDragOut}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={handleClick}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleFileSelect}
        className="hidden"
      />

      {fileName ? (
        <>
          <div className="w-12 h-12 rounded-full bg-goose-success/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-goose-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-goose-text">{fileName}</p>
            <p className="text-xs text-goose-text-muted mt-1">Click or drop to change file</p>
          </div>
        </>
      ) : (
        <>
          <div className="w-12 h-12 rounded-full bg-goose-accent/10 flex items-center justify-center">
            <svg className="w-6 h-6 text-goose-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-goose-text">
              {isDragging ? 'Drop your flight log here' : 'Drag & drop your flight log'}
            </p>
            <p className="text-xs text-goose-text-muted mt-1">
              Supports .ulg (PX4), .bin/.log (ArduPilot), .tlog (MAVLink), .csv
            </p>
          </div>
        </>
      )}
    </div>
  )
}
