import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { ArrowRight, CheckCircle2, CircleAlert, Database, FlaskConical, KeyRound, Scale, Server } from 'lucide-react'

import { getHealth, listModels } from '../runs/api'

function StatusCard({ icon: Icon, label, value, ready }: { icon: typeof Server; label: string; value: string; ready: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-canvas p-4">
      <span className="flex items-center gap-2 text-xs font-medium text-secondary"><Icon aria-hidden="true" className="size-4" />{label}</span>
      <span className={`mt-2 flex items-center gap-2 text-sm font-semibold ${ready ? 'text-success' : 'text-warning'}`}>
        {ready ? <CheckCircle2 aria-hidden="true" className="size-4" /> : <CircleAlert aria-hidden="true" className="size-4" />}
        {value}
      </span>
    </div>
  )
}

export function StartScreen() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, retry: false })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels, staleTime: 30_000 })
  const required = ['agent', 'judge']
  const liveReady = required.every((role) => models.data?.some((model) => model.role === role && model.configured))

  return (
    <div className="mx-auto max-w-6xl">
      <header className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Comece aqui</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-primary sm:text-4xl">Entenda por que uma avaliação passou ou falhou</h1>
        <p className="mt-4 text-base leading-7 text-secondary">Escolha uma demonstração local, sem chaves e sem custo, ou execute agentes e juízes reais. Compare a decisão probabilística do Jev com a avaliação justificada de um LLM, usando a mesma resposta e métricas rastreáveis.</p>
      </header>

      <section className="mt-8 rounded-2xl border border-accent/30 bg-panel p-6 sm:p-8" aria-labelledby="comparison-intro">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent">Novo na versão 1.1</p>
        <h2 id="comparison-intro" className="mt-3 text-2xl font-semibold">Decidir e explicar são capacidades diferentes</h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-secondary">Veja Jev e GPT-4.1 mini lado a lado: acertos, divergências, tempo, tokens, custo e disponibilidade de justificativa. Explore uma comparação real já registrada sem usar suas chaves.</p>
        <div className="mt-5 flex flex-wrap gap-3"><Link to="/compare" search={{ benchmark: 'example' }} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong">Conhecer sem gastar <ArrowRight className="size-4" /></Link><Link to="/compare" search={{ benchmark: undefined }} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-semibold">Comparar com modelos reais</Link></div>
      </section>
      <section aria-labelledby="path-title" className="mt-8">
        <h2 id="path-title" className="sr-only">Escolha seu caminho</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border border-accent/40 bg-accent/8 p-6">
            <span className="grid size-10 place-items-center rounded-xl bg-accent/15 text-accent"><FlaskConical aria-hidden="true" className="size-5" /></span>
            <p className="mt-5 text-xs font-semibold uppercase tracking-[0.12em] text-accent">Recomendado para o primeiro acesso</p>
            <h2 className="mt-2 text-xl font-semibold text-primary">Aprender com uma demonstração local</h2>
            <p className="mt-2 text-sm leading-6 text-secondary">Execute um exemplo aprovado e outro reprovado usando o avaliador real. As respostas são fornecidas pelo projeto e identificadas como tal — nenhuma IA é simulada.</p>
            <ul className="mt-4 space-y-2 text-sm text-secondary">
              <li className="flex gap-2"><CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />Sem API key e sem chamadas externas</li>
              <li className="flex gap-2"><CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />Resultados persistidos no histórico local</li>
            </ul>
            <Link to="/runs" search={{ run: undefined, session: undefined, dataset: undefined, mode: 'demo' }} className="mt-6 inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong">Abrir demonstração <ArrowRight aria-hidden="true" className="size-4" /></Link>
          </article>

          <article className="rounded-2xl border border-border bg-panel p-6">
            <span className="grid size-10 place-items-center rounded-xl bg-elevated text-secondary"><KeyRound aria-hidden="true" className="size-5" /></span>
            <p className="mt-5 text-xs font-semibold uppercase tracking-[0.12em] text-muted">Para experimentar providers</p>
            <h2 className="mt-2 text-xl font-semibold text-primary">Executar com modelos reais</h2>
            <p className="mt-2 text-sm leading-6 text-secondary">Escolha um caso do dataset e acompanhe três tentativas, recuperação de contexto, geração, julgamento e métricas.</p>
            <div className={`mt-4 rounded-lg border p-3 text-sm ${liveReady ? 'border-success/30 bg-success/8 text-success' : 'border-warning/30 bg-warning/8 text-warning'}`}>
              {liveReady ? 'Providers necessários configurados.' : 'Configure o agente e o juiz principal no .env antes de iniciar.'}
            </div>
            <Link to="/runs" search={{ run: undefined, session: undefined, dataset: undefined, mode: 'live' }} className="mt-6 inline-flex items-center gap-2 rounded-md border border-border px-4 py-2.5 text-sm font-semibold text-primary hover:border-accent">Ver execução real <ArrowRight aria-hidden="true" className="size-4" /></Link>
          </article>
        </div>
      </section>

      <section aria-labelledby="environment-title" className="mt-8 rounded-2xl border border-border bg-panel p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">Prontidão</p><h2 id="environment-title" className="mt-1 text-lg font-semibold">Seu ambiente local</h2></div>
          <Link to="/bias" search={{ audit: undefined }} className="inline-flex items-center gap-2 text-sm font-medium text-accent hover:text-accent-strong"><Scale aria-hidden="true" className="size-4" />Depois, veja uma auditoria sem custo</Link>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <StatusCard icon={Server} label="Aplicação" ready={health.data?.status === 'ok'} value={health.isPending ? 'Verificando…' : health.data?.status === 'ok' ? `Pronta · v${health.data.version}` : 'Indisponível'} />
          <StatusCard icon={Database} label="Banco local" ready={health.data?.database === 'ready'} value={health.isPending ? 'Verificando…' : health.data?.database === 'ready' ? 'SQLite pronto' : 'Verifique o serviço'} />
          <StatusCard icon={KeyRound} label="Execução com IA" ready={liveReady} value={models.isPending ? 'Verificando…' : liveReady ? 'Pronta' : 'Configuração opcional pendente'} />
        </div>
      </section>

      <section className="mt-8 grid gap-3 sm:grid-cols-3" aria-label="Como interpretar os resultados">
        <div className="rounded-xl border border-border bg-panel p-4"><strong className="text-sm text-success">Aprovado</strong><p className="mt-1 text-sm leading-6 text-secondary">Todos os critérios normativos disponíveis foram atendidos.</p></div>
        <div className="rounded-xl border border-border bg-panel p-4"><strong className="text-sm text-danger">Reprovado</strong><p className="mt-1 text-sm leading-6 text-secondary">Pelo menos um critério normativo não foi atendido.</p></div>
        <div className="rounded-xl border border-border bg-panel p-4"><strong className="text-sm text-warning">Inconclusivo</strong><p className="mt-1 text-sm leading-6 text-secondary">Faltou evidência ou uma execução foi interrompida; não equivale a reprovação.</p></div>
      </section>
    </div>
  )
}
