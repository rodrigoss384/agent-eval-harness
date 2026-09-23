import { Activity, ArrowRight, CheckCircle2, ChevronDown, Coins, FileUp, Layers3, LoaderCircle, ShieldAlert } from 'lucide-react'
import { ChangeEvent, useMemo, useState } from 'react'

import type { LiveSessionInput } from './api'
import type { DatasetCase, DatasetMetadata, ModelRole } from './schemas'

interface Props {
  pending: boolean
  datasets: DatasetMetadata[]
  cases: DatasetCase[]
  datasetId: string
  onDataset: (datasetId: string) => void
  onStart: (input: LiveSessionInput) => void
  onImport: (file: File) => void
  importing: boolean
  models?: ModelRole[]
  jevReady?: boolean
  providerReady?: boolean
  missingProviders?: string[]
}

export function LivePreflight(props: Props) {
  const [profile, setProfile] = useState<'free' | 'paid_standard'>('free')
  const [mode, setMode] = useState<'single' | 'suite'>('single')
  const [category, setCategory] = useState('all')
  const [difficulty, setDifficulty] = useState('all')
  const [domain, setDomain] = useState('all')
  const [caseId, setCaseId] = useState('case_retrieval_advanced_001')
  const [concurrency, setConcurrency] = useState(2)
  const [reviewing, setReviewing] = useState(false)
  const [judgeRole, setJudgeRole] = useState<'judge' | 'judge_alt'>('judge')
  const [includeJev, setIncludeJev] = useState(false)
  const required = ['agent', judgeRole]
  const missing = props.models ? required.filter(role => !props.models?.some(m => m.role === role && m.configured)) : []
  const providerReady = props.models ? missing.length === 0 && (!includeJev || Boolean(props.jevReady)) : props.providerReady ?? true
  const model = props.models?.find(m => m.role === judgeRole)
  const agent = props.models?.find(m => m.role === 'agent')
  const domains = useMemo(() => [...new Set(props.cases.map((item) => item.domain))].sort(), [props.cases])
  const filtered = props.cases.filter((item) =>
    (category === 'all' || item.category === category)
    && (difficulty === 'all' || item.difficulty === difficulty)
    && (domain === 'all' || item.domain === domain))
  const selected = mode === 'suite' ? filtered.map((item) => item.id) : [filtered.some((item) => item.id === caseId) ? caseId : filtered[0]?.id].filter(Boolean) as string[]
  const selectedCase = props.cases.find((item) => item.id === selected[0])
  const calls = selected.length * 3 * (includeJev ? 3 : 2)

  function importFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) props.onImport(file)
    event.target.value = ''
  }

  function start() {
    props.onStart({ datasetId: props.datasetId, caseIds: selected, mode, concurrency, geminiPricingProfile: profile, judgeRole, includeJev })
    setReviewing(false)
  }

  return (
    <section aria-labelledby="preflight-title" className="rounded-xl border border-border bg-panel p-5">
      <div className="flex items-center gap-2 text-accent"><Activity aria-hidden="true" className="size-4" /><p className="text-xs font-semibold uppercase tracking-[0.14em]">Execução com IA real</p></div>
      <h2 id="preflight-title" className="mt-3 text-lg font-semibold text-primary">Escolha o que deseja avaliar</h2>
      <p className="mt-2 text-sm leading-6 text-secondary">O agente responde sem ver a resposta esperada. Cada caso roda três vezes para revelar instabilidade.</p>

      <label className="mt-5 block text-xs font-medium text-secondary" htmlFor="dataset">Conjunto de exemplos</label>
      <select id="dataset" value={props.datasetId} onChange={(event) => { props.onDataset(event.target.value); setReviewing(false) }} className="mt-2 w-full rounded-md border border-border bg-canvas px-3 py-2.5 text-sm">
        {props.datasets.map((dataset) => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.name} · {dataset.case_count} casos</option>)}
      </select>

      {mode === 'single' ? <label className="mt-4 block text-xs font-medium text-secondary">Exemplo a avaliar<select value={selected[0] ?? ''} onChange={(event) => { setCaseId(event.target.value); setReviewing(false) }} className="mt-2 w-full rounded-md border border-border bg-canvas px-3 py-2.5 text-sm">{filtered.map((item) => <option key={item.id} value={item.id}>{item.input}</option>)}</select></label> : null}
      {selectedCase && mode === 'single' ? <div className="mt-3 rounded-lg border border-border bg-canvas p-3"><p className="text-xs text-muted">Como este caso será avaliado</p><p className="mt-1 text-sm leading-6 text-secondary">{selectedCase.correctness_definition}</p></div> : null}

      <label className="mt-4 block text-sm font-medium">Juiz LLM<select value={judgeRole} onChange={e => { setJudgeRole(e.target.value as 'judge' | 'judge_alt'); setReviewing(false) }} className="mt-2 w-full rounded-md border border-border bg-canvas p-3 text-sm"><option value="judge">Principal · OpenAI</option><option value="judge_alt">Alternativo · Gemini</option></select></label>
      <label className="mt-4 flex items-start gap-2 text-sm"><input type="checkbox" checked={includeJev} onChange={e => { setIncludeJev(e.target.checked); setReviewing(false) }} className="mt-1 size-4 accent-accent" /><span>Comparar também com Jev via OpenRouter<span className="mt-1 block text-xs leading-5 text-muted">Mesma resposta, probabilidade sem racional textual. Adiciona uma chamada por tentativa.</span></span></label>
      <details className="group mt-4 rounded-lg border border-border bg-canvas">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium text-secondary"><span>Opções avançadas</span><ChevronDown aria-hidden="true" className="size-4 transition-transform group-open:rotate-180" /></summary>
        <div className="border-t border-border p-4">
          <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-accent"><FileUp aria-hidden="true" className="size-3.5" />{props.importing ? 'Validando arquivo…' : 'Importar dataset JSONL sintético'}<input className="sr-only" type="file" accept=".jsonl,application/json" onChange={importFile} disabled={props.importing} /></label>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <label className="text-xs text-secondary">Modo<select value={mode} onChange={(event) => { setMode(event.target.value as 'single' | 'suite'); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm"><option value="single">Um caso</option><option value="suite">Suíte filtrada</option></select></label>
            <label className="text-xs text-secondary">Concorrência<select value={concurrency} onChange={(event) => { setConcurrency(Number(event.target.value)); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm">{[1, 2, 3, 4].map((n) => <option key={n}>{n}</option>)}</select></label>
            <label className="text-xs text-secondary">Categoria<select value={category} onChange={(event) => { setCategory(event.target.value); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm"><option value="all">Todas</option><option value="factual">Factual</option><option value="retrieval">Busca de contexto</option><option value="tool_use">Uso de ferramenta</option></select></label>
            <label className="text-xs text-secondary">Dificuldade<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm"><option value="all">Todas</option><option value="basic">Básica</option><option value="intermediate">Intermediária</option><option value="advanced">Avançada</option></select></label>
          </div>
          <label className="mt-3 block text-xs text-secondary">Domínio<select value={domain} onChange={(event) => { setDomain(event.target.value); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm"><option value="all">Todos</option>{domains.map((item) => <option key={item}>{item}</option>)}</select></label>
          <label htmlFor="gemini-pricing" className="mt-3 block text-xs text-secondary">Perfil de preço do juiz Gemini<select id="gemini-pricing" value={profile} onChange={(event) => { setProfile(event.target.value as 'free' | 'paid_standard'); setReviewing(false) }} className="mt-1 w-full rounded-md border border-border bg-panel px-2 py-2 text-sm"><option value="free">Free tier · US$ 0 estimado para o juiz</option><option value="paid_standard">Paid standard · catálogo oficial</option></select></label>
        </div>
      </details>

      <div className="mt-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
        <Metric icon={Layers3} label="Escopo" value={`${selected.length} caso(s) × 3 tentativas`} />
        <Metric icon={ArrowRight} label="Fluxo" value={`${agent?.model ?? 'Agente'} → ${model?.model ?? 'Juiz LLM'}${includeJev ? ' + Jev' : ''}`} />
        <Metric icon={Coins} label="Chamadas externas" value={`${calls} chamadas reais`} />
      </div>

      {!providerReady ? <div className="mt-4 rounded-lg border border-warning/30 bg-warning/8 p-3 text-sm text-warning"><span className="flex items-center gap-2 font-semibold"><ShieldAlert aria-hidden="true" className="size-4" />Execução real indisponível</span><p className="mt-1 leading-6">Configure {props.models ? [...missing, ...(includeJev && !props.jevReady ? ['JEV_API_KEY ou OPENROUTER_API_KEY'] : [])].join(' e ') : props.missingProviders?.join(' e ') || 'os providers necessários'} no arquivo <code>.env</code> e reinicie o serviço. A demonstração local continua disponível.</p></div> : null}

      {!reviewing ? <button type="button" disabled={props.pending || selected.length === 0 || !providerReady} onClick={() => setReviewing(true)} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50"><Activity aria-hidden="true" className="size-4" />Revisar execução</button> : (
        <div className="mt-4 rounded-lg border border-accent/30 bg-accent/8 p-4" role="group" aria-label="Confirmação da execução real">
          <p className="flex items-center gap-2 text-sm font-semibold text-primary"><CheckCircle2 aria-hidden="true" className="size-4 text-accent" />Confirme antes de chamar os providers</p>
          <p className="mt-2 text-sm leading-6 text-secondary">Serão feitas <strong className="text-primary">{calls} chamadas externas</strong>. O valor exibido é uma estimativa do catálogo e pode não coincidir com a fatura.</p>
          <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => setReviewing(false)} className="rounded-md border border-border px-3 py-2 text-sm text-secondary hover:text-primary">Voltar</button><button type="button" disabled={props.pending} onClick={start} className="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{props.pending ? <LoaderCircle aria-hidden="true" className="size-4 animate-spin" /> : <Activity aria-hidden="true" className="size-4" />}Confirmar e iniciar {calls} chamadas</button></div>
        </div>
      )}
      <p className="mt-3 text-xs leading-5 text-muted">Não há retry nem troca automática de provider. Uma indisponibilidade será registrada como evidência inconclusiva.</p>
    </section>
  )
}

function Metric({ icon: Icon, label, value }: { icon: typeof Coins; label: string; value: string }) {
  return <div className="rounded-lg border border-border bg-canvas p-3"><span className="flex items-center gap-2 text-xs text-muted"><Icon aria-hidden="true" className="size-3.5" />{label}</span><strong className="mt-1 block text-sm text-primary">{value}</strong></div>
}
