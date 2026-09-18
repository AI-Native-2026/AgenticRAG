import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as echarts from 'echarts'
import { useTheme } from '@/store/theme'

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/** 读取当前主题的 CSS 变量，生成与 UI 一致的基础样式。 */
function themeBase() {
  const text = cssVar('--text', '#0f172a')
  const text2 = cssVar('--text-2', '#475569')
  const border = cssVar('--border-2', 'rgba(15,23,42,.16)')
  const panel = cssVar('--panel', '#ffffff')
  const axis = {
    axisLabel: { color: text2 },
    axisLine: { lineStyle: { color: border } },
    splitLine: { lineStyle: { color: cssVar('--border', border) } },
    nameTextStyle: { color: text2 },
  }
  return {
    base: {
      backgroundColor: 'transparent',
      textStyle: { color: text },
      title: { textStyle: { color: text } },
      legend: { textStyle: { color: text2 } },
      tooltip: { backgroundColor: panel, borderColor: border, textStyle: { color: text } },
    },
    axis,
  }
}

/** 把主题样式合并进 LLM 给出的 option（不覆盖数据与系列定义）。 */
function decorateOption(option: any, isDark: boolean) {
  if (!option || typeof option !== 'object') return option
  const { base, axis } = themeBase()
  const text = cssVar('--text', isDark ? '#e7eaf0' : '#0f172a')
  const mergeAxis = (a: any) => {
    if (Array.isArray(a)) return a.map(mergeOne)
    return a ? mergeOne(a) : a
  }
  const mergeOne = (a: any) => ({
    ...axis,
    ...a,
    axisLabel: { ...axis.axisLabel, ...(a.axisLabel || {}) },
    axisLine: { ...axis.axisLine, ...(a.axisLine || {}) },
    splitLine: { ...axis.splitLine, ...(a.splitLine || {}) },
  })
  const mergeSeries = (s: any) => {
    const one = (x: any) => ({
      ...x,
      label: { color: text, ...(x.label || {}) },
      // 折线/柱状的数据标签与轴线文字统一为主题前景色
      emphasis: { ...(x.emphasis || {}), label: { color: text, ...((x.emphasis || {}).label || {}) } },
    })
    return Array.isArray(s) ? s.map(one) : s ? one(s) : s
  }
  return {
    ...base,
    ...option,
    textStyle: { ...base.textStyle, ...(option.textStyle || {}) },
    title: { ...base.title, ...(option.title || {}), textStyle: { ...base.title.textStyle, ...((option.title || {}).textStyle || {}) } },
    legend: { ...base.legend, ...(option.legend || {}), textStyle: { ...base.legend.textStyle, ...((option.legend || {}).textStyle || {}) } },
    tooltip: { ...base.tooltip, ...(option.tooltip || {}), textStyle: { ...base.tooltip.textStyle, ...((option.tooltip || {}).textStyle || {}) } },
    xAxis: mergeAxis(option.xAxis),
    yAxis: mergeAxis(option.yAxis),
    series: mergeSeries(option.series),
  }
}

/** 渲染单个 ECharts option（随主题自适应）。 */
function EChart({ option, height = 300 }: { option: any; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const theme = useTheme((s) => s.theme)
  const isDark = theme === 'dark'

  // 主题切换时重建实例，并切换 ECharts 内置 dark 主题，确保颜色完全刷新
  useEffect(() => {
    if (!ref.current) return
    chartRef.current = echarts.init(ref.current, isDark ? 'dark' : undefined)
    const onResize = () => chartRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [isDark])

  useEffect(() => {
    if (chartRef.current && option) {
      chartRef.current.setOption(decorateOption(option, isDark), true)
      chartRef.current.resize()
    }
  }, [option, isDark])

  return <div ref={ref} style={{ width: '100%', height }} data-testid="echart" />
}

/** 解析 ```echarts 代码块为 option JSON。 */
function parseEcharts(raw: string): any | null {
  try {
    return JSON.parse(raw)
  } catch {
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
