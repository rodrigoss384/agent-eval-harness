import { FlaskConical, Inbox } from 'lucide-react'

import type { RunVerdict } from './schemas'
import { StatusPill } from './status-pill'

interface RunListProps {
  runs: RunVerdict[]
  selectedRunId: string | null
  onSelect: (runId: string) => void
}

export function RunList({ runs, selectedRunId, onSelect }: RunListProps) {
  if (runs.length === 0) {
    return (
      <div className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-panel/40 px-6 text-center">
        <span className="mb-4 rounded-xl border border-border bg-elevated p-3 text-muted">
          <Inbox aria-hidden="true" className="size-5" />
        </span>
        <h2 className="text-sm font-semibold text-primary">Nenhum teste registrado</h2>
        <p className="mt-1 max-w-xs text-sm leading-6 text-secondary">
          Execute um caso de teste para ver o primeiro resultado da avaliação.
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-panel">
      <div className="border-b border-border px-4 py-3">
        <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
          <FlaskConical aria-hidden="true" className="size-3.5" />
          Histórico local
        </h2>
      </div>
      <ul className="divide-y divide-border" aria-label="Testes disponíveis">
        {runs.map((run) => (
          <li key={run.run_id}>
            <button
              type="button"
              onClick={() => onSelect(run.run_id)}
              aria-current={selectedRunId === run.run_id ? 'true' : undefined}
              className="group flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-elevated focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent aria-[current=true]:bg-elevated"
            >
              <span className="min-w-0">
                <span className="block truncate font-mono text-xs text-secondary">{run.run_id}</span>
                <span className="mt-1 block truncate text-sm text-primary">{run.agent_input}</span>
              </span>
              <StatusPill verdict={run.final_verdict} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
