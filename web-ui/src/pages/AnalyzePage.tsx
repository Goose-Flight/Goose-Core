import React, { useState } from 'react'
import { FileUpload } from '../components/FileUpload'
import { ScoreRing } from '../components/ScoreRing'
import { FindingsTable } from '../components/FindingsTable'
import { AnalysisResult, UploadResponse } from '../lib/types'

export function AnalyzePage() {
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleUploadComplete = (response: UploadResponse) => {
    if (response.success && response.result) {
      setResult(response.result)
      setError(null)
    } else {
      setError(response.error || 'Analysis failed')
      setResult(null)
    }
  }

  return (
    <div className="space-y-8">
      <div className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-bold mb-6">Upload Flight Log</h2>
        <FileUpload onUploadComplete={handleUploadComplete} />
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <h3 className="font-semibold text-red-900 mb-2">Error</h3>
          <p className="text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-8">
            <div className="grid grid-cols-3 gap-8">
              <div className="flex flex-col items-center">
                <ScoreRing score={result.score} label="Flight Score" />
              </div>
              <div className="col-span-2 flex flex-col justify-center">
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-600">File</p>
                    <p className="font-semibold text-gray-900">
                      {result.file_name}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Analysis Time</p>
                    <p className="font-semibold text-gray-900">
                      {new Date(result.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Findings</p>
                    <p className="font-semibold text-gray-900">
                      {result.findings.length} issue{result.findings.length !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {result.findings.length > 0 && (
            <div className="bg-white rounded-lg shadow p-8">
              <h3 className="text-xl font-bold mb-6">Analysis Findings</h3>
              <FindingsTable findings={result.findings} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
