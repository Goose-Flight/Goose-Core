export interface AnalysisResult {
  score: number;
  findings: Finding[];
  file_name: string;
  timestamp: string;
}

export interface Finding {
  id: string;
  type: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  line?: number;
  details?: string;
}

export interface Plugin {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  description?: string;
}

export interface UploadResponse {
  success: boolean;
  result?: AnalysisResult;
  error?: string;
}
