export interface Finding {
  plugin: string;
  title: string;
  severity: string;
  score: number;
  description: string;
  evidence?: Record<string, unknown> | null;
  phase?: string | null;
  timestamp_start?: number | null;
  timestamp_end?: number | null;
}

export interface AnalysisResult {
  findings: Finding[];
  plugins_run: string[];
  file_name: string;
}

export interface Plugin {
  name: string;
  description?: string | null;
}

export interface UploadResponse {
  success: boolean;
  result?: AnalysisResult;
  error?: string;
}
