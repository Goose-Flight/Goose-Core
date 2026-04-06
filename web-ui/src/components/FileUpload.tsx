import React, { useState } from 'react'
import { uploadFile } from '../lib/api'
import { UploadResponse } from '../lib/types'

interface FileUploadProps {
  onUploadComplete: (result: UploadResponse) => void
}

export function FileUpload({ onUploadComplete }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const acceptedFormats = ['.ulg', '.bin', '.tlog', '.csv']

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFile(files[0])
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0])
    }
  }

  const handleFile = async (file: File) => {
    setError(null)

    const hasValidExtension = acceptedFormats.some(format =>
      file.name.toLowerCase().endsWith(format)
    )

    if (!hasValidExtension) {
      setError(`Invalid file format. Accepted: ${acceptedFormats.join(', ')}`)
      return
    }

    setIsLoading(true)
    try {
      const result = await uploadFile(file)
      onUploadComplete(result)
    } catch (err) {
      setError('Failed to upload file. Please try again.')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="w-full">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-12 text-center transition ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <input
          type="file"
          id="file-input"
          onChange={handleFileSelect}
          disabled={isLoading}
          accept={acceptedFormats.join(',')}
          className="hidden"
        />
        <label htmlFor="file-input" className="cursor-pointer block">
          <div className="text-lg font-semibold text-gray-700 mb-2">
            {isLoading ? 'Uploading...' : 'Drag and drop your flight log'}
          </div>
          <div className="text-sm text-gray-500 mb-4">
            or click to browse
          </div>
          <div className="text-xs text-gray-400">
            Supported formats: {acceptedFormats.join(', ')}
          </div>
        </label>
      </div>
      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded text-red-700">
          {error}
        </div>
      )}
    </div>
  )
}
