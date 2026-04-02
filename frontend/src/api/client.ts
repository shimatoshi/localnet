/** API client — Flask バックエンドとの通信 */

export interface SiteInfo {
  domain: string
  file_count: number
  has_catalog: boolean
  page_count: number
}

export interface JobInfo {
  job_id: string
  status: 'pending' | 'running' | 'done' | 'error'
  domain: string | null
  error: string | null
  page_count: number
}

export interface SearchResult {
  url: string
  title: string
  path: string
  domain: string
}

// === 検索 ===

export async function apiSearch(query: string, limit = 50): Promise<SearchResult[]> {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// === サイト ===

export async function apiGetSites(): Promise<SiteInfo[]> {
  const res = await fetch('/api/sites')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// === カタログ ===

export async function apiGetCatalog(domain: string): Promise<{ url: string; title: string; path: string }[]> {
  const res = await fetch(`/api/catalog/${encodeURIComponent(domain)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// === キャッシュ ===

export async function apiGetCachePage(domain: string, path: string) {
  return fetch(`/api/cache/${domain}/${path}`)
}

// === クロール ===

export async function apiCrawl(url: string, depth: number, delay: number, exclude: string[]): Promise<JobInfo> {
  const res = await fetch('/api/crawl', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, depth, delay, exclude }),
  })
  return res.json()
}

export async function apiResume(domain: string): Promise<JobInfo> {
  const res = await fetch(`/api/resume/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiRecrawl(domain: string): Promise<JobInfo> {
  const res = await fetch(`/api/recrawl/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiBuild(domain: string): Promise<JobInfo> {
  const res = await fetch(`/api/build/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiStopJob(jobId: string) {
  const res = await fetch(`/api/jobs/${jobId}/stop`, { method: 'POST' })
  return res.json()
}

export async function apiGetJob(jobId: string): Promise<JobInfo> {
  const res = await fetch(`/api/jobs/${jobId}`)
  return res.json()
}

export async function apiGetActiveJobs(): Promise<JobInfo[]> {
  const res = await fetch('/api/jobs/active')
  return res.json()
}

// === エクスポート ===

export async function apiExport(domain: string): Promise<Blob> {
  const res = await fetch(`/api/export/${encodeURIComponent(domain)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.blob()
}

// === インポート ===

export async function apiImport(file: File): Promise<JobInfo> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/import', { method: 'POST', body: formData })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}
