import { useEffect, useState } from 'react'
import { getToken } from '@/api/client'

/** 带鉴权地加载 /v1/media/{nodeId} 图片（避免把 token 放进 URL）。 */
export default function AuthImage({
  nodeId,
  alt = '',
  className,
  style,
}: {
  nodeId: string
  alt?: string
  className?: string
  style?: React.CSSProperties
}) {
  const [url, setUrl] = useState<string>()

  useEffect(() => {
    let objectUrl: string | undefined
    let cancelled = false
    fetch(`/v1/media/${nodeId}`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((b) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(b)
        setUrl(objectUrl)
      })
      .catch(() => {})
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [nodeId])

  if (!url) {
    return <div className="img-ph" style={style}>图片加载中…</div>
  }
  return <img src={url} alt={alt} className={className} style={style} />
}
