import { useEffect, useRef } from 'react'
import type { LogLine } from '../hooks/useSSE'

interface Props {
  logs: LogLine[]
}

export default function LogArea({ logs }: Props) {
  const areaRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (areaRef.current) {
      areaRef.current.scrollTop = areaRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div id="log-area" ref={areaRef}>
      {logs.map((line, i) => (
        <div key={i} className={`log-line${line.isProgress ? ' log-progress' : ''}`}>
          {line.text}
        </div>
      ))}
    </div>
  )
}
