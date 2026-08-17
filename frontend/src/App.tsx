import { FormEvent, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

type Chart = {
  title: string
  category_key: string
  value_key: string
  data: Record<string, string | number>[]
}

type Analysis = {
  filename: string
  row_count: number
  column_count: number
  insights: string[]
  chart: Chart
  next_steps: string[]
  source: string
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [prompt, setPrompt] = useState('Show me the participation and completion data.')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const chartRef = useRef<HTMLDivElement>(null)

  async function runAnalysis(question: string) {
    if (!file) {
      setError('Choose a CSV file first.')
      return
    }

    setLoading(true)
    setError('')
    const form = new FormData()
    form.append('file', file)
    form.append('prompt', question)
    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: 'POST',
        body: form,
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Analysis failed.')
      setAnalysis(body)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Analysis failed.')
    } finally {
      setLoading(false)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void runAnalysis(prompt)
  }

  function exportCsv() {
    if (!analysis) return
    const { category_key, value_key, data } = analysis.chart
    const escape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
    const rows = [
      [category_key, value_key],
      ...data.map((row) => [row[category_key], row[value_key]]),
    ]
    const blob = new Blob([rows.map((row) => row.map(escape).join(',')).join('\n')], {
      type: 'text/csv',
    })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'csv-insights-chart.csv'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  function downloadChart() {
    const svg = chartRef.current?.querySelector('svg')
    if (!svg) return
    const source = new XMLSerializer().serializeToString(svg)
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = image.width || 900
      canvas.height = image.height || 480
      const context = canvas.getContext('2d')
      if (!context) return
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(image, 0, 0)
      const link = document.createElement('a')
      link.download = 'csv-insights-chart.png'
      link.href = canvas.toDataURL('image/png')
      link.click()
    }
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(source)}`
  }

  return (
    <main>
      <header>
        <div>
          <span className="eyebrow">CSV Insights Agent</span>
          <h1>Turn a spreadsheet into a clear plan.</h1>
          <p>Upload a CSV to discover patterns, visualize results, and decide what to do next.</p>
        </div>
        <div className="status">Local analysis</div>
      </header>

      <form className="upload-panel" onSubmit={submit}>
        <label className="file-picker">
          <span>{file ? file.name : 'Choose a CSV file'}</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => {
              setFile(event.target.files?.[0] || null)
              setAnalysis(null)
              setError('')
            }}
          />
        </label>
        <input
          className="prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          aria-label="Analysis prompt"
          placeholder="What would you like to learn?"
        />
        <button className="primary" disabled={loading}>
          {loading ? 'Analyzing…' : 'Analyze CSV'}
        </button>
      </form>
      {error && <div className="error">{error}</div>}

      <section className="dashboard">
        <article className="panel">
          <div className="panel-heading">
            <span>01</span>
            <h2>Key Insights</h2>
          </div>
          {analysis ? (
            <ul className="insights">
              {analysis.insights.map((insight) => <li key={insight}>{insight}</li>)}
            </ul>
          ) : (
            <EmptyState text="Your most important findings will appear here." />
          )}
        </article>

        <article className={`panel chart-panel ${expanded ? 'expanded' : ''}`}>
          <div className="panel-heading chart-heading">
            <div><span>02</span><h2>Data Visualization</h2></div>
            {analysis && (
              <div className="tools">
                <button onClick={() => setExpanded(!expanded)} title="Expand chart">
                  {expanded ? 'Close' : 'Expand'}
                </button>
                <button onClick={downloadChart} title="Download chart as PNG">PNG</button>
                <button onClick={exportCsv} title="Export chart data as CSV">CSV</button>
              </div>
            )}
          </div>
          {analysis ? (
            <>
              <h3>{analysis.chart.title}</h3>
              <div className="chart" ref={chartRef}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={analysis.chart.data} margin={{ top: 10, right: 15, left: 0, bottom: 15 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey={analysis.chart.category_key} tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey={analysis.chart.value_key} fill="#356859" radius={[7, 7, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <small>{analysis.row_count} rows · {analysis.column_count} columns · {analysis.source}</small>
            </>
          ) : (
            <EmptyState text="A chart based on your data will appear here." />
          )}
        </article>

        <article className="panel">
          <div className="panel-heading">
            <span>03</span>
            <h2>Next Steps</h2>
          </div>
          {analysis ? (
            <div className="next-steps">
              {analysis.next_steps.map((step) => (
                <button key={step} onClick={() => {
                  setPrompt(step)
                  void runAnalysis(step)
                }}>
                  <span>{step}</span><b>→</b>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState text="Actionable recommendations will appear here." />
          )}
        </article>
      </section>
    </main>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty"><span>✦</span><p>{text}</p></div>
}

export default App
