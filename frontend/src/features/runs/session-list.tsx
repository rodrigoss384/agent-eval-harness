import { Clock3, Inbox, Radio } from 'lucide-react'

import type { EvaluationSession } from './schemas'
import { StatusPill } from './status-pill'

function sessionLabel(session: EvaluationSession) {
  if (session.status === 'failed') return 'Erro de execução'
  if (session.status === 'partial' || session.status === 'interrupted' || session.status === 'cancelled') return 'Inconclusivo'
  if (session.status === 'queued' || session.status === 'running') return 'Em andamento'
  return session.final_verdict === 'pass' ? 'Aprovado' : session.final_verdict === 'fail' ? 'Reprovado' : 'Inconclusivo'
}

export function SessionList({ sessions, selectedSessionId, onSelect }: { sessions: EvaluationSession[]; selectedSessionId: string | null; onSelect: (id: string) => void }) {
  if (!sessions.length) {
    return (
      <div className="grid min-h-48 place-items-center rounded-xl border border-dashed border-border bg-panel/50 p-6 text-center">
        <div><Inbox aria-hidden="true" className="mx-auto size-5 text-muted" /><h3 className="mt-3 text-sm font-semibold">Nenhuma execução real</h3><p className="mt-1 text-sm text-secondary">Quando você iniciar uma avaliação com providers, ela aparecerá aqui.</p></div>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-panel">
      <div className="border-b border-border px-4 py-3"><h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted"><Radio aria-hidden="true" className="size-3.5" />Sessões com IA</h3></div>
      <ul className="max-h-[32rem] divide-y divide-border overflow-auto" aria-label="Sessões reais disponíveis">
        {sessions.map((session) => {
          const active = selectedSessionId === session.session_id
          return (
            <li key={session.session_id}>
              <button type="button" aria-current={active ? 'true' : undefined} onClick={() => onSelect(session.session_id)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-elevated aria-[current=true]:bg-elevated">
                <span className="min-w-0"><span className="block truncate font-mono text-[11px] text-muted">{session.session_id}</span><span className="mt-1 block truncate text-sm text-primary">{session.request.case_ids.length} caso(s) · {session.runs.length}/{session.request.case_ids.length * 3} tentativas</span><span className="mt-1 flex items-center gap-1 text-xs text-muted"><Clock3 aria-hidden="true" className="size-3" />{new Date(session.created_at).toLocaleString('pt-BR')}</span></span>
                {session.status === 'queued' || session.status === 'running' ? <span className="shrink-0 rounded-full border border-accent/30 bg-accent/8 px-2 py-1 text-xs text-accent">{sessionLabel(session)}</span> : <StatusPill verdict={session.final_verdict} />}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
