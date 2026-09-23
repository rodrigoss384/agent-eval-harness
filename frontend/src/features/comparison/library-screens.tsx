import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { FileUp, Search } from 'lucide-react'
import { useState } from 'react'
import { getDataset, importDataset, listDatasets, listRuns, listSessions } from '../runs/api'
import { getBenchmarks } from './contracts'
import { Heading, inputClass, Panel, secondaryClass, statusLabel } from './ui'

export function HistoryScreen() {
  const [filter, setFilter] = useState('')
  const benchmarks = useQuery({ queryKey: ['benchmarks'], queryFn: getBenchmarks })
  const runs = useQuery({ queryKey: ['runs'], queryFn: listRuns })
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: listSessions })
  const match = (value: string) => value.toLowerCase().includes(filter.toLowerCase())
  const error = benchmarks.error ?? runs.error ?? sessions.error
  return <div className="mx-auto max-w-6xl"><Heading eyebrow="Histórico local" title="Volte às evidências">Consulte comparações, sessões e respostas avaliadas. Abrir um resultado salvo não chama modelos nem gera cobrança.</Heading>
    <label className="mb-6 block max-w-xl text-sm font-medium"><span className="flex items-center gap-2"><Search size={16} />Filtrar por identificador ou estado</span><input className={inputClass} value={filter} onChange={e => setFilter(e.target.value)} placeholder="Ex.: completed, case_001…" /></label>
    {error && <p role="alert" className="mb-4 text-danger">{error.message}</p>}
    <div className="space-y-5"><Panel><h2 className="text-xl font-semibold">Comparações entre juízes</h2><p className="mt-1 text-xs text-muted">Até 50 execuções mais recentes.</p><div className="mt-4 space-y-2">{benchmarks.data?.filter(b => match(`${b.benchmark_id} ${b.status}`)).map(b => <Link key={b.benchmark_id} to="/compare" search={{ benchmark: b.benchmark_id }} className="flex flex-wrap justify-between gap-2 rounded-lg border border-border p-4 text-sm hover:bg-elevated"><span>{new Date(b.created_at).toLocaleString('pt-BR')} · {b.distinct_cases} casos</span><span className="text-accent">{statusLabel(b.status)} · {b.calls_attempted}/{b.calls_planned} chamadas →</span></Link>)}{!benchmarks.data?.length && <p className="text-sm text-secondary">Nenhuma comparação local. O exemplo registrado está em Comparar juízes.</p>}</div></Panel>
    <Panel><h2 className="text-xl font-semibold">Sessões com geração do agente</h2><div className="mt-4 space-y-2">{sessions.data?.filter(s => match(`${s.session_id} ${s.status}`)).map(s => <Link key={s.session_id} to="/runs" search={{ mode: 'live', session: s.session_id, run: undefined, dataset: s.request.dataset_id }} className="flex flex-wrap justify-between gap-2 rounded-lg border border-border p-4 text-sm hover:bg-elevated"><span>{new Date(s.created_at).toLocaleString('pt-BR')} · {s.request.case_ids.length} caso(s)</span><span className="text-accent">{statusLabel(s.status)} →</span></Link>)}{!sessions.data?.length && <p className="text-sm text-secondary">Nenhuma sessão executada.</p>}</div></Panel>
    <Panel><h2 className="text-xl font-semibold">Avaliações individuais</h2><p className="mt-1 text-xs text-muted">20 resultados mais recentes. Sessões completas estão acima.</p><div className="mt-4 space-y-2">{runs.data?.filter(r => match(`${r.run_id} ${r.case_id} ${r.final_verdict}`)).map(r => <Link key={r.run_id} to="/runs" search={{ mode: r.candidate_origin === 'supplied_trace' ? 'demo' : 'live', run: r.run_id, session: r.session_id ?? undefined, dataset: undefined }} className="flex flex-wrap justify-between gap-2 rounded-lg border border-border p-4 text-sm hover:bg-elevated"><span>{r.case_id} · {new Date(r.created_at).toLocaleString('pt-BR')}</span><span className="text-accent">{r.final_verdict === 'pass' ? 'Aprovado' : r.final_verdict === 'fail' ? 'Reprovado' : 'Inconclusivo'} →</span></Link>)}{!runs.data?.length && <p className="text-sm text-secondary">Comece pela demonstração local para criar seu primeiro resultado.</p>}</div></Panel></div>
  </div>
}

export function DatasetsScreen() {
  const client = useQueryClient()
  const [id, setId] = useState('builtin-v2')
  const [category, setCategory] = useState('all')
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: listDatasets })
  const dataset = useQuery({ queryKey: ['dataset', id], queryFn: () => getDataset(id) })
  const upload = useMutation({ mutationFn: async (file: File) => importDataset(file.name.replace(/\.jsonl$/i, ''), await file.text()), onSuccess: async doc => { await client.invalidateQueries({ queryKey: ['datasets'] }); setId(doc.metadata.dataset_id) } })
  return <div className="mx-auto max-w-6xl"><Heading eyebrow="Dados sintéticos" title="Saiba exatamente o que está sendo testado">Cada caso reúne uma pergunta, a resposta de referência e o critério de aprovação. Explore o conteúdo antes de interpretar os resultados.</Heading>
    <Panel><div className="grid items-end gap-4 md:grid-cols-[1fr_1fr_auto]"><label className="text-sm font-medium">Conjunto<select className={inputClass} value={id} onChange={e => setId(e.target.value)}>{datasets.data?.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.name} · {d.case_count} casos</option>)}</select></label><label className="text-sm font-medium">Categoria<select className={inputClass} value={category} onChange={e => setCategory(e.target.value)}><option value="all">Todas</option><option value="factual">Factual</option><option value="retrieval">Busca de contexto</option><option value="tool_use">Uso de ferramentas</option></select></label><label className={`${secondaryClass} cursor-pointer`}><FileUp size={16} />{upload.isPending ? 'Importando…' : 'Importar JSONL'}<input aria-label="Importar dataset JSONL sintético" type="file" accept=".jsonl" disabled={upload.isPending} className="sr-only" onChange={e => { const file = e.target.files?.[0]; if (file) upload.mutate(file); e.target.value = '' }} /></label></div><p className="mt-4 text-xs leading-6 text-muted">Somente dados sintéticos. Importar um conjunto não executa chamadas. O benchmark pareado usa seu próprio conjunto versionado de candidatos.</p></Panel>
    {(dataset.error || datasets.error || upload.error) && <p role="alert" className="mt-4 text-danger">{(dataset.error ?? datasets.error ?? upload.error)?.message}</p>}
    {dataset.isPending && <p role="status" className="mt-6 text-secondary">Carregando casos…</p>}
    <div className="mt-6 space-y-3">{dataset.data?.cases.filter(c => category === 'all' || c.category === category).map(c => <details key={c.id} className="rounded-xl border border-border bg-panel p-5"><summary className="cursor-pointer"><span className="text-xs text-accent">{c.category} · {c.difficulty} · limiar {c.threshold}</span><h2 className="mt-1 inline text-base font-semibold"> {c.input}</h2></summary><div className="mt-5 grid gap-5 border-t border-border pt-5 md:grid-cols-2"><div><h3 className="text-sm font-semibold">Resposta de referência</h3><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-secondary">{c.expected_output}</p><h3 className="mt-4 text-sm font-semibold">Definição de correto</h3><p className="mt-2 text-sm leading-6 text-secondary">{c.correctness_definition}</p></div><div><h3 className="text-sm font-semibold">Rubrica e fontes</h3><ul className="mt-2 list-disc pl-5 text-sm leading-6 text-secondary">{c.rubric.map(r => <li key={r}>{r}</li>)}</ul>{c.reference_context.map(r => <p key={r.id} className="mt-2 text-sm leading-6 text-secondary">[{r.id}] {r.text}</p>)}</div></div></details>)}</div>
  </div>
}
