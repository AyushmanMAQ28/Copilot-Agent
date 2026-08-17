import { useRef, useState } from 'react'
import { Download, FileUp, Moon, Send, Sparkles, Sun, X, ZoomIn } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { toPng } from 'html-to-image'
import './App.css'

type Insight = { id: string; title: string; body: string; category: string; severity: string; confidence: number }
type Chart = { id: string; title: string; description: string; chart_type: string; x_key: string; series: { key: string; label: string; color: string }[]; data: Record<string, string | number>[] }
type Result = { summary: string; insights: Insight[]; charts: Chart[]; next_steps: { id: string; question: string; rationale: string }[]; table: { columns: string[]; rows: Record<string, string | number>[] }; meta: { model: string; duration_ms: number } }
const api = import.meta.env.VITE_API_URL ?? '/api'

function App() {
  const [file, setFile] = useState<File>()
  const [datasetId, setDatasetId] = useState<string>()
  const [result, setResult] = useState<Result>()
  const [prompt, setPrompt] = useState('Show me the most important participation and completion trends.')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')
  const [expanded, setExpanded] = useState<Chart>()
  const input = useRef<HTMLInputElement>(null)
  const upload = async (picked: File) => {
    setError('')
    if (!picked.name.toLowerCase().endsWith('.csv')) { setError('Please select a CSV file.'); return }
    const project = await fetch(`${api}/projects`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'My analysis' }) }).then(r => r.json() as Promise<{ id: string }>)
    const data = new FormData(); data.append('file', picked)
    const uploaded = await fetch(`${api}/projects/${project.id}/datasets`, { method: 'POST', body: data })
    if (!uploaded.ok) throw new Error((await uploaded.json() as { detail?: string }).detail ?? 'Upload failed')
    const dataset = await uploaded.json() as { id: string }
    setFile(picked); setDatasetId(dataset.id)
  }
  const analyze = async (question = prompt) => {
    if (!datasetId) { setError('Attach a CSV before running analysis.'); return }
    setLoading(true); setError('')
    try {
      const project = await fetch(`${api}/projects`).then(r => r.json() as Promise<{ id: string }[]>)
      const chat = await fetch(`${api}/projects/${project[0]?.id}/chats`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: question.slice(0, 60) }) }).then(r => r.json() as Promise<{ id: string }>)
      const response = await fetch(`${api}/chats/${chat.id}/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: question, dataset_id: datasetId }) })
      if (!response.ok) throw new Error((await response.json() as { detail?: string }).detail ?? 'Analysis failed')
      setResult(await response.json() as Result)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Analysis failed') } finally { setLoading(false) }
  }
  const toggleTheme = () => { const value = !dark; setDark(value); localStorage.setItem('theme', value ? 'dark' : 'light'); document.documentElement.classList.toggle('dark', value) }
  const saveChart = async (chart: Chart) => { const node = document.getElementById(`chart-${chart.id}`); if (!node) return; const href = await toPng(node); const a = document.createElement('a'); a.href = href; a.download = `${chart.title}.png`; a.click() }
  return <main className={dark ? 'app dark' : 'app'}>
    <aside><div className="brand"><Sparkles size={20} /> CSV Insights</div><button className="new">+ New analysis</button><p className="muted">PROJECTS</p><div className="project">My analysis<br /><small>Upload a CSV to begin</small></div><div className="bottom"><button onClick={toggleTheme} aria-label="Toggle theme">{dark ? <Sun size={17} /> : <Moon size={17} />} {dark ? 'Light' : 'Dark'} mode</button><small>Model · qwen-3.6-27b</small></div></aside>
    <section className="workspace">
      <header><div><h1>Data workspace</h1><p>Ask questions, uncover patterns, make decisions.</p></div><span className="status">Local analysis ready</span></header>
      <div className="composer"><textarea value={prompt} onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void analyze() }} aria-label="Analysis prompt" />
        <div className="compose-actions"><input ref={input} type="file" accept=".csv,text/csv" hidden onChange={e => { const picked = e.target.files?.[0]; if (picked) void upload(picked).catch(reason => setError(reason instanceof Error ? reason.message : 'Upload failed')) }} />
          {file ? <span className="file-chip"><FileUp size={15} />{file.name}<button onClick={() => { setFile(undefined); setDatasetId(undefined) }}><X size={14} /></button></span> : <button onClick={() => input.current?.click()}><FileUp size={16} /> Attach CSV</button>}
          <span>⌘ Enter</span><button className="send" disabled={loading} onClick={() => void analyze()}><Send size={16} /> {loading ? 'Analyzing…' : 'Analyze'}</button></div></div>
      {error && <div className="error">{error}</div>}
      {!result && !loading && <div className="empty"><FileUp size={42} /><h2>Upload a CSV to see visualizations</h2><p>Your data stays structured: profile, insights, charts, and useful follow-up questions appear here.</p></div>}
      {(result || loading) && <><p className="summary">{result?.summary ?? 'Parsing CSV → Profiling → Reasoning → Building charts'}</p><div className="grid">
        <Panel title="Key insights">{loading ? <Skeleton /> : result?.insights.map(i => <article className="insight" key={i.id}><span className={`badge ${i.severity}`}>{i.category}</span><h3>{i.title}</h3><p>{i.body}</p><small>{Math.round(i.confidence * 100)}% confidence</small></article>)}</Panel>
        <Panel title="Data visualizations" wide>{loading ? <Skeleton /> : result?.charts.map(chart => <article className="chart-card" key={chart.id}><div className="chart-head"><div><h3>{chart.title}</h3><p>{chart.description}</p></div><div><button aria-label="Expand chart" onClick={() => setExpanded(chart)}><ZoomIn size={16} /></button><button aria-label="Download PNG" onClick={() => void saveChart(chart)}><Download size={16} /></button></div></div><ChartView chart={chart} /></article>)}
          {result && <Table data={result.table} />}</Panel>
        <Panel title="Next steps">{loading ? <Skeleton /> : result?.next_steps.map(step => <button className="step" key={step.id} onClick={() => { setPrompt(step.question); void analyze(step.question) }}><strong>{step.question}</strong><span>{step.rationale}</span></button>)}</Panel>
      </div></>}
    </section>
    {expanded && <div className="modal" role="dialog" aria-modal="true"><div className="modal-body"><button className="close" onClick={() => setExpanded(undefined)}><X /></button><h2>{expanded.title}</h2><ChartView chart={expanded} /></div></div>}
  </main>
}
function Panel({ title, children, wide = false }: { title: string; children: React.ReactNode; wide?: boolean }) { return <section className={`panel ${wide ? 'wide' : ''}`}><h2>{title}</h2>{children}</section> }
function Skeleton() { return <div className="skeleton"><i /><i /><i /></div> }
function ChartView({ chart }: { chart: Chart }) { return <div className="chart" id={`chart-${chart.id}`}><ResponsiveContainer width="100%" height={280}><BarChart data={chart.data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey={chart.x_key} tick={{ fontSize: 11 }} /><YAxis /><Tooltip />{chart.series.map(s => <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[4, 4, 0, 0]} />)}</BarChart></ResponsiveContainer></div> }
function Table({ data }: { data: Result['table'] }) { return <div className="table"><h3>Complete data analysis table</h3><div className="table-scroll"><table><thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{data.rows.slice(0, 15).map((row, i) => <tr key={i}>{data.columns.map(c => <td key={c}>{String(row[c] ?? '')}</td>)}</tr>)}</tbody></table></div></div> }
export default App
