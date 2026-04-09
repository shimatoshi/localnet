import { useState, useEffect, useRef, useCallback } from 'react'
import {
  apiGetSites, apiCrawl, apiResume, apiRecrawl, apiBuild,
  apiStopJob, apiExport, apiImport, apiGetActiveJobs, apiDeleteSite,
  apiGetJob,
  type SiteInfo, type JobInfo,
} from '../api/client'

export function useCrawl(online: boolean) {
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [activeJob, setActiveJob] = useState<JobInfo | null>(null)
  const [statusMsg, setStatusMsg] = useState('')
  const [importStatus, setImportStatus] = useState('')
  const currentJobIdRef = useRef<string | null>(null)

  const loadSites = useCallback(async () => {
    try { setSites(await apiGetSites()) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!online) return
    loadSites()
    // 起動時に実行中ジョブがあるか確認
    apiGetActiveJobs().then((jobs) => {
      if (jobs.length > 0) {
        const job = jobs[0]
        currentJobIdRef.current = job.job_id
        setActiveJob(job)
        setStatusMsg(`実行中: ${job.domain || ''} (${job.page_count} ページ)`)
      }
    }).catch(() => {})
  }, [online]) // eslint-disable-line react-hooks/exhaustive-deps

  async function checkStatus() {
    // まずjob_idがあればそれを確認、なければactiveを確認
    try {
      if (currentJobIdRef.current) {
        const job = await apiGetJob(currentJobIdRef.current)
        setActiveJob(job)
        if (job.status === 'running') {
          setStatusMsg(`実行中: ${job.domain || ''} (${job.page_count} ページ取得済み)`)
        } else if (job.status === 'done') {
          setStatusMsg(`完了: ${job.domain || ''} (${job.page_count} ページ)`)
          currentJobIdRef.current = null
          setActiveJob(null)
          loadSites()
        } else if (job.status === 'error') {
          setStatusMsg(`エラー: ${job.error || '不明'}`)
          currentJobIdRef.current = null
          setActiveJob(null)
        }
        return
      }
      const jobs = await apiGetActiveJobs()
      if (jobs.length > 0) {
        const job = jobs[0]
        currentJobIdRef.current = job.job_id
        setActiveJob(job)
        setStatusMsg(`実行中: ${job.domain || ''} (${job.page_count} ページ取得済み)`)
      } else {
        setActiveJob(null)
        setStatusMsg('実行中のジョブなし')
        loadSites()
      }
    } catch (e) {
      setStatusMsg('状況取得エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doCrawl(targetUrl: string, depth: number, delay: number, exclude: string): Promise<JobInfo | undefined> {
    if (!targetUrl) return
    const excludeList = exclude ? exclude.split(',').map((s) => s.trim()).filter(Boolean) : []
    try {
      const data = await apiCrawl(targetUrl, depth, delay, excludeList)
      if (data.error) { setStatusMsg('エラー: ' + data.error); return }
      currentJobIdRef.current = data.job_id
      setActiveJob(data)
      setStatusMsg(`クロール開始: ${data.job_id} (${data.domain || targetUrl})`)
      return data
    } catch (e) {
      setStatusMsg('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doResume(domain: string, depth = 0, delay = 1.0) {
    try {
      const data = await apiResume(domain, depth, delay)
      if (data.error) { setStatusMsg('エラー: ' + data.error); return }
      currentJobIdRef.current = data.job_id
      setActiveJob(data)
      setStatusMsg(`再開: ${data.job_id} (${domain})`)
    } catch (e) {
      setStatusMsg('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doRecrawl(domain: string) {
    if (!confirm(`${domain} を再クロールしますか？\n既存のキャッシュは上書きされます。`)) return
    try {
      const data = await apiRecrawl(domain)
      if (data.error) { setStatusMsg('エラー: ' + data.error); return }
      currentJobIdRef.current = data.job_id
      setActiveJob(data)
      setStatusMsg(`再クロール開始: ${data.job_id} (${domain})`)
    } catch (e) {
      setStatusMsg('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doBuild(domain: string) {
    try {
      const data = await apiBuild(domain)
      if (data.error) { setStatusMsg('エラー: ' + data.error); return }
      currentJobIdRef.current = data.job_id
      setActiveJob(data)
      setStatusMsg(`カタログ生成中: ${data.job_id} (${domain})`)
    } catch (e) {
      setStatusMsg('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function stopCrawl() {
    if (!currentJobIdRef.current) return
    try {
      const data = await apiStopJob(currentJobIdRef.current)
      if (data.ok) setStatusMsg('停止リクエスト送信...')
      else setStatusMsg('停止失敗: ' + (data.error || '不明なエラー'))
    } catch (e) {
      setStatusMsg('停止エラー: ' + (e instanceof Error ? e.message : String(e)))
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
      currentJobIdRef.current = data.job_id
      setImportStatus(`カタログ生成中: ${data.domain || '...'}`)
    } catch (e) {
      setImportStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const crawling = activeJob?.status === 'running'

  return {
    sites, crawling, activeJob, statusMsg, importStatus,
    doCrawl, doResume, doRecrawl, doBuild, stopCrawl, doExport, doDelete, handleImport,
    checkStatus, loadSites,
  }
}
