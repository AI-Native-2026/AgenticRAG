import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as echarts from 'echarts'

/** 渲染单个 ECharts option。 */
function EChart({ option, height = 300 }: { option: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    chartRef.current = echarts.init(ref.current)
    const onResize = () => chartRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    if (chartRef.current && option) {
      chartRef.current.setOption(option, true)
      chartRef.current.resize()
    }
  }, [option])

  return <div ref={ref} style={{ width: '100%', height }} data-testid="echart" />
}

/** 解析 ```echarts 代码块为 option JSON。 */
function parseEcharts(raw: string): any | null {
  try {
    return JSON.parse(raw)
  } catch {
    // 容错：去掉可能存在的注释/尾逗号
    try {
      const cleaned = raw.replace(/\/\/[^\n]*/g, '').replace(/,\s*([}\]])/g, '$1')
      return JSON.parse(cleaned)
    } catch {
      return null
    }
  }
}

export default function MarkdownView({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code(props: any) {
          const { className, children } = props
          const text = String(children ?? '')
          const match = /language-(\w+)/.exec(className || '')
          const lang = match?.[1]
          if (lang === 'echarts') {
            const option = parseEcharts(text)
            if (option) return <EChart option={option} />
            return <pre className="code"><code>{text}</code></pre>
          }
          return <code className={className}>{children}</code>
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
