import { useQuery } from '@tanstack/react-query'
import { createRootRoute, createRoute, createRouter, Link, Outlet, useRouterState } from '@tanstack/react-router'
import { Database, FlaskConical, House, Scale, ShieldCheck, GitCompareArrows, History, LibraryBig } from 'lucide-react'

import { ComparisonScreen } from './features/comparison/comparison-screen'
import { HistoryScreen, DatasetsScreen } from './features/comparison/library-screens'
import { StartScreen } from './features/onboarding/start-screen'
import { listModels } from './features/runs/api'
import { RunsScreen } from './features/runs/runs-screen'
import { BiasScreen } from './features/bias/bias-screen'

function Shell() {
  const modelsQuery = useQuery({ queryKey: ['models'], queryFn: listModels, staleTime: 30_000 })
  const path = useRouterState({ select: (state) => state.location.pathname })
  const navItems = [
    { to: '/', search: undefined, label: 'Comece aqui', icon: House, active: path === '/' },
    { to: '/compare', search: { benchmark: undefined }, label: 'Comparar juízes', icon: GitCompareArrows, active: path === '/compare' },
    { to: '/history', search: undefined, label: 'Histórico', icon: History, active: path === '/history' },
    { to: '/datasets', search: undefined, label: 'Datasets', icon: LibraryBig, active: path === '/datasets' },
    { to: '/runs', search: { mode: 'demo' as const }, label: 'Avaliações', icon: FlaskConical, active: path === '/runs' },
    { to: '/bias', search: undefined, label: 'Auditoria de viés', icon: Scale, active: path === '/bias' },
  ]

  return (
    <div className="min-h-dvh bg-canvas text-primary lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="border-b border-border bg-sidebar px-4 py-4 lg:sticky lg:top-0 lg:h-dvh lg:border-b-0 lg:border-r lg:px-3 lg:py-5">
        <div className="flex flex-col gap-4 lg:block">
          <div className="flex items-center gap-2 px-2">
            <img src="/agent-eval-mark.svg?v=2" alt="" aria-hidden="true" className="size-9 shrink-0" />
            <div>
              <p className="text-sm font-semibold tracking-[-0.02em]">agent-eval</p>
              <p className="font-mono text-[10px] text-muted">harness / v1.1.0</p>
            </div>
          </div>
          <nav aria-label="Principal" className="flex flex-wrap gap-1 lg:mt-8 lg:block lg:space-y-1">
            {navItems.map(({ to, search, label, icon: Icon, active }) => <Link key={to} to={to} search={search} aria-label={label} aria-current={active ? 'page' : undefined} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-secondary hover:bg-elevated hover:text-primary aria-[current=page]:bg-elevated aria-[current=page]:text-primary"><Icon aria-hidden="true" className={`size-4 ${active ? 'text-accent' : 'text-muted'}`} /><span className="inline">{label}</span></Link>)}
          </nav>
        </div>

        <div className="mt-5 hidden border-t border-border pt-5 lg:block">
          <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">Ambiente</p>
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2 px-2 text-xs text-secondary"><Database aria-hidden="true" className="size-3.5" /> SQLite local</div>
            <div className="flex items-center gap-2 px-2 text-xs text-secondary"><ShieldCheck aria-hidden="true" className="size-3.5" /> Dados sintéticos</div>
          </div>
          <p className="mt-6 px-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">Providers</p>
          <ul className="mt-2 space-y-1.5 px-2">
            {modelsQuery.isPending ? <li className="text-xs text-muted">Consultando…</li> : null}
            {modelsQuery.data?.map((model) => (
              <li key={model.role} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-secondary">{model.role === 'agent' ? 'Agente' : model.role === 'judge' ? 'Juiz principal' : 'Juiz alternativo'}</span>
                <span className={model.configured ? 'text-success' : 'text-muted'}>{model.configured ? 'ativo' : 'inativo'}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-7 sm:px-6 lg:px-8 lg:py-9"><Outlet /></main>
    </div>
  )
}

const rootRoute = createRootRoute({ component: Shell })
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: StartScreen,
})
const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/runs',
  validateSearch: (search: Record<string, unknown>) => ({
    run: typeof search.run === 'string' ? search.run : undefined,
    session: typeof search.session === 'string' ? search.session : undefined,
    dataset: typeof search.dataset === 'string' ? search.dataset : undefined,
    mode: search.mode === 'live' ? 'live' as const : 'demo' as const,
  }),
  component: function RunsRoute() {
    const search = runsRoute.useSearch()
    const navigate = runsRoute.useNavigate()
    return (
      <RunsScreen
        selectedRunId={search.run ?? null}
        selectedSessionId={search.session ?? null}
        selectedDatasetId={search.dataset ?? null}
        mode={search.mode}
        onSelect={(run) => navigate({ search: (current) => ({ ...current, run }) })}
        onSession={(session) => navigate({ search: (current) => ({ ...current, session }) })}
        onDataset={(dataset) => navigate({ search: (current) => ({ ...current, dataset }) })}
        onMode={(mode) => navigate({ search: (current) => ({ ...current, mode }) })}
      />
    )
  },
})

const biasRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/bias',
  validateSearch: (search: Record<string, unknown>) => ({ audit: typeof search.audit === 'string' ? search.audit : undefined }),
  component: function BiasRoute() {
    const search = biasRoute.useSearch()
    const navigate = biasRoute.useNavigate()
    return <BiasScreen selectedAuditId={search.audit ?? null} onAudit={(audit) => navigate({ search: { audit } })} />
  },
})

const compareRoute = createRoute({
  getParentRoute: () => rootRoute, path: '/compare',
  validateSearch: (search: Record<string, unknown>) => ({ benchmark: typeof search.benchmark === 'string' ? search.benchmark : undefined }),
  component: function CompareRoute() {
    const search = compareRoute.useSearch()
    const navigate = compareRoute.useNavigate()
    return <ComparisonScreen selectedId={search.benchmark} onSelect={benchmark => navigate({ search: { benchmark } })} />
  },
})
const historyRoute = createRoute({ getParentRoute: () => rootRoute, path: '/history', component: HistoryScreen })
const datasetsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/datasets', component: DatasetsScreen })
const routeTree = rootRoute.addChildren([indexRoute, compareRoute, runsRoute, historyRoute, datasetsRoute, biasRoute])
export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register { router: typeof router }
}
