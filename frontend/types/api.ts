export type Severity = "high" | "medium" | "low";
export interface Insight { id: string; title: string; detail: string; category: string; severity: Severity; confidence: number; }
export interface ChartData { labels: string[]; datasets: Array<{ label: string; data: number[]; }>; }
export interface Chart { id: string; title: string; chart_type: string; data: ChartData; }
export interface Analysis { insights: Insight[]; charts: Chart[]; next_steps: string[]; quality_score?: number; }
