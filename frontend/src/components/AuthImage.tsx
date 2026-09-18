import { useEffect, useState } from 'react'
import { ImageOff } from 'lucide-react'
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
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let objectUrl: string | undefined
    let cancelled = false
    setUrl(undefined)
    setFailed(false)

    const token = getToken()
    fetch(`/v1/media/${nodeId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
        return r.blob()
      })
      .then((b) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(b)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [nodeId])

  if (failed) {
    return (
      <div className="img-ph" style={style} title={alt}>
        <ImageOff size={14} />
        <span>图片不可用</span>
      </div>
    )
  }
  if (!url) {
    return <div className="img-ph" style={style}>加载中…</div>
  }
  return <img src={url} alt={alt} className={className} style={style} loading="lazy" />
}
