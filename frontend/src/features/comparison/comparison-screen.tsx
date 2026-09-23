import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CircleHelp, FlaskConical, RefreshCw, Square, Timer } from 'lucide-react'
import { useState } from 'react'

import { cancelBenchmark, createBenchmark, getBenchmark, getBenchmarks, getBenchmarkSummary, getPreflight, getSamples } from './contracts'
import { BenchmarkReport } from './report'
import { buttonClass, Heading, inputClass, Panel, secondaryClass, statusLabel } from './ui'

export function ComparisonScreen({ selectedId, onSelect }: { selectedId?: string; onSelect: (id: string) => void }) {
  const client = useQueryClient()
  const [configure, setConfigure] = useState(false)
  const [caseId, setCaseId] = useState('all')
  const preflight = useQuery({ queryKey: ['benchmark-preflight'], queryFn: getPreflight })
  const samples = useQuery({ queryKey: ['benchmark-samples'], queryFn: getSamples })
  const history = useQuery({ queryKey: ['benchmarks'], queryFn: getBenchmarks })
  const id = selectedId ?? 'example'
  const result = useQuery({ queryKey: ['benchmark', id], queryFn: () => getBenchmark(id), retry: false,
    refetchInterval: q => ['running', 'queued'].includes(q.state.data?.status ?? '') ? 2000 : false })
  const summary = useQuery({ queryKey: ['benchmark-summary', id, result.data?.updated_at], queryFn: () => getBenchmarkSummary(id), enabled: !!result.data })
  const start = useMutation({ mutationFn: createBenchmark, onSuccess: async data => {
    onSelect(data.benchmark_id); setConfigure(false); await client.invalidateQueries({ queryKey: ['benchmarks'] })
  } })
  const cancel = useMutation({ mutationFn: cancelBenchmark, onSuccess: data => client.setQueryData(['benchmark', id], data) })
  const running = ['running', 'queued'].includes(result.data?.status ?? '')
  const calls = caseId === 'all' ? 288 : 12
  const cases = samples.data?.filter(s => s.expected_passed) ?? []

  return <div className="mx-auto max-w-7xl">
    <div className="flex flex-wrap items-start justify-between gap-4"><Heading eyebrow="Comparação de juízes" title="A mesma resposta. Dois jeitos de avaliar.">Jev decide com uma probabilidade. O LLM produz uma nota e uma justificativa. Explore o que cada um entrega, quanto custa e onde divergem.</Heading><button type="button" className={secondaryClass} onClick={() => setConfigure(!configure)} aria-expanded={configure}><FlaskConical size={16} />Nova comparação</button></div>
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-border bg-panel px-4 py-3 text-sm">
      <span className="font-semibold text-accent">Jev <span className="font-normal text-secondary">via OpenRouter</span></span><span className="text-muted">×</span><span className="font-semibold">GPT-4.1 mini <span className="font-normal text-secondary">via OpenAI</span></span><span className="ml-auto text-xs text-muted">Mesmos dados · limiares originais · sem retry</span>
    </div>
    {configure && <Panel className="mb-6">
      <h2 className="text-xl font-semibold">Configure antes de executar</h2><p className="mt-2 text-sm leading-6 text-secondary">Os modelos avaliarão respostas sintéticas já preparadas. Nenhum agente será chamado para gerá-las. São duas respostas e três repetições por caso.</p>
      <div className="mt-5 grid items-end gap-5 md:grid-cols-[1fr_auto]">
        <label className="text-sm font-medium">O que comparar<select className={inputClass} value={caseId} onChange={e => setCaseId(e.target.value)}><option value="all">Benchmark completo · 24 casos · 288 chamadas</option>{cases.map(s => <option key={s.case.id} value={s.case.id}>{s.case.input}</option>)}</select></label>
        <button type="button" disabled={!preflight.data?.ready || running || start.isPending} className={buttonClass} onClick={() => start.mutate(caseId)}>Iniciar {calls} chamadas pagas <ArrowRight size={16} /></button>
      </div>
      <p className="mt-4 text-sm text-secondary">Limites desta execução: <strong>300 chamadas e US$ 2</strong>, somando os dois serviços. A reserva usa preços verificados e será conciliada com o consumo disponível.</p>
      {!preflight.data?.ready && <div role="status" className="mt-4 rounded-lg border border-warning/30 bg-warning/5 p-4 text-sm text-warning"><strong>Configuração necessária</strong>{preflight.data?.issues.map(issue => <p key={issue} className="mt-1">{issue}</p>)}<p className="mt-2">Configure as chaves no .env e reinicie o serviço. O exemplo registrado continua disponível sem chamadas.</p></div>}
    </Panel>}
    {(start.error || cancel.error || preflight.error) && <p role="alert" className="mb-5 rounded-lg border border-danger/30 bg-danger/5 p-4 text-danger">{(start.error ?? cancel.error ?? preflight.error)?.message}</p>}
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <label className="flex min-w-0 max-w-full flex-wrap items-center gap-3 text-sm font-medium">Resultado<select aria-label="Resultado da comparação" className="max-w-full rounded-lg border border-border bg-panel px-3 py-2 font-normal" value={id} onChange={e => onSelect(e.target.value)}><option value="example">Exemplo real registrado · sem novas chamadas</option>{history.data?.map(item => <option key={item.benchmark_id} value={item.benchmark_id}>{new Date(item.created_at).toLocaleString('pt-BR')} · {statusLabel(item.status)}</option>)}{selectedId && selectedId !== 'example' && !history.data?.some(x => x.benchmark_id === selectedId) && <option value={selectedId}>Execução selecionada</option>}</select></label>
      {running && <button className={secondaryClass} type="button" disabled={cancel.isPending} onClick={() => cancel.mutate(id)}><Square size={14} />Cancelar próximas chamadas</button>}
    </div>
    {running && result.data && <div className="mb-6 rounded-xl border border-accent/30 bg-accent/5 p-4" role="status"><p className="flex items-center gap-2 text-sm font-semibold"><Timer size={16} />{statusLabel(result.data.status)} · {result.data.calls.filter(c => c.status !== 'reserved').length} de {result.data.calls_planned} chamadas concluídas</p><progress aria-label="Progresso do benchmark" value={result.data.calls.filter(c => c.status !== 'reserved').length} max={result.data.calls_planned} className="mt-3 h-2 w-full accent-accent" /><p className="mt-2 text-xs text-secondary">Pode sair desta página. O backend continua a execução e salva cada resultado.</p></div>}
    {result.isPending && <p role="status" className="py-12 text-center text-secondary">Carregando comparação…</p>}
    {result.error && <Panel><CircleHelp className="text-accent" /><h2 className="mt-3 text-lg font-semibold">Nenhum resultado disponível</h2><p className="mt-2 text-sm text-secondary">{result.error.message}</p><button type="button" className={`${secondaryClass} mt-4`} onClick={() => void result.refetch()}><RefreshCw size={16} />Atualizar</button></Panel>}
    {result.data && summary.data && <BenchmarkReport benchmark={result.data} summary={summary.data} />}
    {summary.error && <p role="alert" className="text-danger">Não foi possível carregar as métricas: {summary.error.message}</p>}
  </div>
}
