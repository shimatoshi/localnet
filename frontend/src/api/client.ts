/** API client — Flask バックエンドとの通信 */

// === リモートサーバー設定 ===

const REMOTE_KEY = 'localnet_remote_server'

export function getRemoteServer(): string {
  return localStorage.getItem(REMOTE_KEY) || ''
}

export function setRemoteServer(url: string) {
  const trimmed = url.replace(/\s+/g, '').replace(/\/+$/, '')
  if (trimmed) localStorage.setItem(REMOTE_KEY, trimmed)
  else localStorage.removeItem(REMOTE_KEY)
}

/** リモートサーバーが設定されていればそのURLベース、なければローカル */
export function remoteBase(): string {
  return getRemoteServer() || ''
}

/** リトライ付きfetch（Cloudflareトンネルの間欠503対策） */
async function fetchRetry(input: RequestInfo | URL, init?: RequestInit, retries = 2): Promise<Response> {
  for (let i = 0; i <= retries; i++) {
    const res = await fetch(input, init)
    if (res.ok || res.status < 500 || i === retries) return res
    await new Promise(r => setTimeout(r, 1000 * (i + 1)))
  }
  return fetch(input, init) // unreachable but satisfies TS
}

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

// --- クロール系: リモートサーバーに向ける ---

export async function apiCrawl(url: string, depth: number, delay: number, exclude: string[]): Promise<JobInfo> {
  const res = await fetchRetry(`${remoteBase()}/api/crawl`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, depth, delay, exclude }),
  })
  return res.json()
}

export async function apiResume(domain: string): Promise<JobInfo> {
  const res = await fetchRetry(`${remoteBase()}/api/resume/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiRecrawl(domain: string): Promise<JobInfo> {
  const res = await fetchRetry(`${remoteBase()}/api/recrawl/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiStopJob(jobId: string) {
  const res = await fetchRetry(`${remoteBase()}/api/jobs/${jobId}/stop`, { method: 'POST' })
  return res.json()
}

export async function apiGetJob(jobId: string): Promise<JobInfo> {
  const res = await fetchRetry(`${remoteBase()}/api/jobs/${jobId}`)
  return res.json()
}

export async function apiGetActiveJobs(): Promise<JobInfo[]> {
  const res = await fetchRetry(`${remoteBase()}/api/jobs/active`)
  return res.json()
}

/** リモートサーバーのサイト一覧（成果物取り込み用） */
export async function apiGetRemoteSites(): Promise<SiteInfo[]> {
  const base = remoteBase()
  if (!base) return []
  const res = await fetchRetry(`${base}/api/sites`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/** リモートサーバーからエクスポート→ローカルにインポート */
export async function apiPullSite(domain: string): Promise<JobInfo> {
  const base = remoteBase()
  if (!base) throw new Error('リモートサーバーが設定されていません')
  const exportRes = await fetch(`${base}/api/export/${encodeURIComponent(domain)}`)
  if (!exportRes.ok) throw new Error(`エクスポート失敗: HTTP ${exportRes.status}`)
  const blob = await exportRes.blob()
  const file = new File([blob], `${domain}.tar.gz`, { type: 'application/gzip' })
  return apiImport(file)
}

// --- ローカル専用 ---

export async function apiBuild(domain: string): Promise<JobInfo> {
  const res = await fetch(`/api/build/${encodeURIComponent(domain)}`, { method: 'POST' })
  return res.json()
}

export async function apiDeleteSite(domain: string) {
  const res = await fetch(`/api/delete/${encodeURIComponent(domain)}`, { method: 'POST' })
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

export async function apiGetSitePages(dsName: string, siteName: string) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(dsName)}/site/${encodeURIComponent(siteName)}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
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

export async function apiUploadDataset(name: string) {
  const res = await fetch(`/api/datasets/${encodeURIComponent(name)}/upload`, { method: 'POST' })
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

export async function apiRefreshSharedDatasets() {
  const res = await fetch('/api/datasets/shared/refresh', { method: 'POST' })
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
