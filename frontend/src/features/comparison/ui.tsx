import type { ReactNode } from 'react'

export const buttonClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50'
export const secondaryClass = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border bg-panel px-4 py-2.5 text-sm font-semibold text-primary hover:bg-elevated disabled:opacity-50'
export const inputClass = 'mt-2 min-h-11 w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-primary'
export function Heading({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="mb-8 max-w-3xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">{eyebrow}</p><h1 className="mt-3 text-3xl font-semibold tracking-tight text-primary sm:text-4xl">{title}</h1><p className="mt-4 text-base leading-7 text-secondary">{children}</p></header>
}
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`min-w-0 rounded-2xl border border-border bg-panel p-5 sm:p-6 ${className}`}>{children}</section>
}
export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return <div className="min-w-0 rounded-xl border border-border bg-panel p-4"><p className="text-xs font-medium text-secondary">{label}</p><p className="mt-2 break-words text-2xl font-semibold tracking-tight tabular-nums">{value}</p>{note && <p className="mt-1 text-xs leading-5 text-muted">{note}</p>}</div>
}
export const percent = (n: number | null | undefined) => n == null ? 'Não disponível' : `${(n * 100).toFixed(1)}%`
export const money = (n: number | null | undefined) => n == null ? 'Não informado' : `US$ ${n.toFixed(8)}`
export const number = (n: number | null | undefined) => n == null ? '—' : n.toLocaleString('pt-BR', { maximumFractionDigits: 3 })
export const statusLabel = (s: string) => ({ queued: 'Na fila', running: 'Em andamento', completed: 'Concluído', partial: 'Resultado parcial', failed: 'Falha de execução', cancelled: 'Cancelado', interrupted: 'Interrompido', budget_exhausted: 'Limite atingido' }[s] ?? s)
