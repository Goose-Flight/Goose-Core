import { AnalysisResult, Plugin, UploadResponse } from './types'

export async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/analyze', {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const error = await response.text()
    return { success: false, error }
  }

  const result: AnalysisResult = await response.json()
  return { success: true, result }
}

export async function getPlugins(): Promise<Plugin[]> {
  const response = await fetch('/api/plugins')

  if (!response.ok) {
    throw new Error('Failed to fetch plugins')
  }

  return response.json()
}

export async function getAnalysisHistory(): Promise<AnalysisResult[]> {
  const response = await fetch('/api/history')

  if (!response.ok) {
    throw new Error('Failed to fetch history')
  }

  return response.json()
}
