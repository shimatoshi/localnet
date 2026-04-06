import { useState, useCallback, useRef, useEffect } from 'react'
import { apiGetJob, remoteBase } from '../api/client'

export interface LogLine {
  text: string
  isProgress: boolean
}

export function useSSE() {
  const [logs, setLogs] = useState<LogLine[]>([])
  const esRef = useRef<EventSource | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => {
      if (msg.startsWith('\r')) {
        const text = msg.slice(1)
        const last = prev[prev.length - 1]
        if (last?.isProgress) {
          return [...prev.slice(0, -1), { text, isProgress: true }]
        }
        return [...prev, { text, isProgress: true }]
      }
      return [...prev, { text: msg, isProgress: false }]
    })
  }, [])

  const clearLogs = useCallback(() => setLogs([]), [])

  const listen = useCallback((jobId: string, onFinish?: () => void) => {
    // 前の接続を閉じる
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    clearTimeout(timerRef.current)

    const es = new EventSource(`${remoteBase()}/api/jobs/${jobId}/stream`)
    esRef.current = es

    es.onmessage = (event) => {
      let msg: { type: string; message?: string; error?: string }
      try { msg = JSON.parse(event.data) } catch { return }
      if (msg.type === 'ping') return
      if (msg.type === 'log') addLog(msg.message || '')
      if (msg.type === 'done') {
        es.close(); esRef.current = null
        addLog('--- 完了 ---')
        onFinish?.()
      }
      if (msg.type === 'error') {
        es.close(); esRef.current = null
        addLog('エラー: ' + (msg.message || ''))
        onFinish?.()
      }
    }

    es.onerror = () => {
      es.close()
      esRef.current = null
      addLog('接続が切断されました。再接続中...')
      timerRef.current = setTimeout(async () => {
        try {
          const job = await apiGetJob(jobId)
          if (job.status === 'running') {
            addLog('再接続...')
            listen(jobId, onFinish)
          } else if (job.status === 'done') {
            addLog('--- 完了 ---')
            onFinish?.()
          } else if (job.status === 'error') {
            addLog('エラー: ' + (job.error || '不明'))
            onFinish?.()
          }
        } catch {
          addLog('サーバーに接続できません。後で再試行...')
          timerRef.current = setTimeout(() => listen(jobId, onFinish), 10000)
        }
      }, 3000)
    }
  }, [addLog])

  // クリーンアップ
  useEffect(() => {
    return () => {
      esRef.current?.close()
      clearTimeout(timerRef.current)
    }
  }, [])

  return { logs, addLog, clearLogs, listen }
}
