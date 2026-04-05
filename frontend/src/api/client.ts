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

export async function apiDeleteSite(domain: string) {
  const res = await fetch(`/api/delete/${encodeURIComponent(domain)}`, { method: 'POST' })
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

// === データセット ===

export interface DatasetInfo {
  name: string
  description: string
  created_at: string
  site_count: number
  sites: DatasetSite[]
}

export interface DatasetSite {
  name: string
  file_count: number
  page_count: number
  source: 'crawled' | 'custom'
}

export async function apiListDatasets(): Promise<DatasetInfo[]> {
  const res = await fetch('/api/datasets')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function apiCreateDataset(name: string, description: string = '') {
  const res = await fetch('/api/datasets/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
  return res.json()
}

export async function apiGetDataset(name: string): Promise<DatasetInfo> {
  const res = await fetch(`/api/datasets/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function apiDeleteDataset(name: string) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(name)}/delete`, { method: 'POST' })
  return res.json()
}

export async function apiAddCrawledToDataset(dsName: string, domain: string) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(dsName)}/add-crawled`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain }),
  })
  return res.json()
}

export async function apiAddTemplateSite(dsName: string, formData: FormData) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(dsName)}/add-template`, {
    method: 'POST',
    body: formData,
  })
  return res.json()
}

export async function apiRemoveSiteFromDataset(dsName: string, siteName: string) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(dsName)}/remove-site`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: siteName }),
  })
  return res.json()
}

export async function apiExportDataset(name: string): Promise<Blob> {
  const res = await fetch(`/api/datasets/${encodeURIComponent(name)}/export`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.blob()
}

export async function apiImportDataset(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/datasets/import', { method: 'POST', body: formData })
  return res.json()
}

// === 共有データセット ===

export interface SharedDataset {
  name: string
  filename: string
  size: number
  download_url: string
  description: string
  published_at: string
  tag: string
}

export async function apiListSharedDatasets(): Promise<SharedDataset[]> {
  const res = await fetch('/api/datasets/shared')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function apiDownloadSharedDataset(name: string, url: string) {
  const res = await fetch('/api/datasets/shared/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, url }),
  })
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
