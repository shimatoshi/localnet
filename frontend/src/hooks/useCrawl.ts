import { useState, useEffect, useRef, useCallback } from 'react'
import { useSSE } from './useSSE'
import {
  apiGetSites, apiCrawl, apiResume, apiRecrawl, apiBuild,
  apiStopJob, apiExport, apiImport, apiGetActiveJobs, apiDeleteSite,
  type SiteInfo, type JobInfo,
} from '../api/client'

export function useCrawl(online: boolean) {
  const { logs, addLog, clearLogs, listen } = useSSE()
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [crawling, setCrawling] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const [importStatus, setImportStatus] = useState('')
  const currentJobIdRef = useRef<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const loadSites = useCallback(async () => {
    try { setSites(await apiGetSites()) } catch { /* ignore */ }
  }, [])

  const onJobFinish = useCallback(() => {
    setCrawling(false)
    currentJobIdRef.current = null
    clearInterval(pollRef.current)
    loadSites()
  }, [loadSites])

  const startListening = useCallback((job: JobInfo) => {
    currentJobIdRef.current = job.job_id
    setCrawling(true)
    setShowLog(true)
    listen(job.job_id, onJobFinish)
  }, [listen, onJobFinish])

  useEffect(() => {
    if (!online) return
    loadSites()
    // 実行中ジョブに再接続
    if (!currentJobIdRef.current) {
      apiGetActiveJobs().then((jobs) => {
        if (jobs.length > 0) {
          const job = jobs[0]
          addLog(`実行中のジョブに再接続: ${job.job_id} (${job.domain || ''})`)
          addLog(`現在: ${job.page_count || 0} 件取得済み`)
          startListening(job)
        }
      }).catch(() => {})
    }
    return () => clearInterval(pollRef.current)
  }, [online]) // eslint-disable-line react-hooks/exhaustive-deps

  async function doCrawl(targetUrl: string, depth: number, delay: number, exclude: string) {
    if (!targetUrl) return
    const excludeList = exclude ? exclude.split(',').map((s) => s.trim()).filter(Boolean) : []
    clearLogs()
    try {
      const data = await apiCrawl(targetUrl, depth, delay, excludeList)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`クロール開始: ${data.job_id} (深さ: ${depth === 0 ? '無制限' : depth})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doResume(domain: string) {
    clearLogs()
    try {
      const data = await apiResume(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`再開: ${data.job_id} (${domain})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doRecrawl(domain: string) {
    if (!confirm(`${domain} を再クロールしますか？\n既存のキャッシュは上書きされます。`)) return
    clearLogs()
    try {
      const data = await apiRecrawl(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`再クロール開始: ${data.job_id} (${domain})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doBuild(domain: string) {
    clearLogs()
    setShowLog(true)
    try {
      const data = await apiBuild(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`カタログ生成: ${data.job_id}`)
      listen(data.job_id, () => loadSites())
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function stopCrawl() {
    if (!currentJobIdRef.current) return
    try {
      const data = await apiStopJob(currentJobIdRef.current)
      if (data.ok) addLog('停止リクエスト送信...')
      else addLog('停止失敗: ' + (data.error || '不明なエラー'))
    } catch (e) {
      addLog('停止エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doExport(domain: string) {
    try {
      const blob = await apiExport(domain)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${domain}.tar.gz`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      alert('エクスポートエラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doDelete(domain: string) {
    if (!confirm(`${domain} を削除しますか？\nキャッシュとカタログが完全に削除されます。`)) return
    try {
      await apiDeleteSite(domain)
      loadSites()
    } catch (e) {
      alert('削除エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function handleImport(file: File) {
    setImportStatus(`アップロード中: ${file.name}...`)
    try {
      const data = await apiImport(file)
      setImportStatus(`カタログ生成中: ${data.domain || '...'} (job: ${data.job_id})`)
      listen(data.job_id, () => {
        setImportStatus('インポート完了')
        loadSites()
      })
    } catch (e) {
      setImportStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  return {
    sites, crawling, showLog, logs, importStatus,
    doCrawl, doResume, doRecrawl, doBuild, stopCrawl, doExport, doDelete, handleImport,
  }
}
