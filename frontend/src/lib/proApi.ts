const PRO_BASE = (import.meta.env.VITE_PRO_API_URL as string) ?? 'http://localhost:8765'

async function proRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = localStorage.getItem('goose_pro_token')
  const res = await fetch(`${PRO_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-Auth-Token': token } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  if (res.status === 204) return undefined as T
  return res.json()
}

export const proApi = {
  get: <T>(path: string) => proRequest<T>('GET', path),
  post: <T>(path: string, body?: unknown) => proRequest<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => proRequest<T>('PUT', path, body),
  delete: <T>(path: string) => proRequest<T>('DELETE', path),
}
