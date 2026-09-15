import { CircleCheck, CircleMinus, CircleX } from 'lucide-react'

type Verdict = 'pass' | 'fail' | 'inconclusive'

const config = {
  pass: { label: 'Aprovado', icon: CircleCheck, className: 'text-success border-success/25 bg-success/8' },
  fail: { label: 'Reprovado', icon: CircleX, className: 'text-danger border-danger/25 bg-danger/8' },
  inconclusive: {
    label: 'Inconclusivo',
    icon: CircleMinus,
    className: 'text-warning border-warning/25 bg-warning/8',
  },
} satisfies Record<Verdict, { label: string; icon: typeof CircleCheck; className: string }>

export function StatusPill({ verdict }: { verdict: Verdict }) {
  const current = config[verdict]
  const Icon = current.icon

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${current.className}`}>
      <Icon aria-hidden="true" className="size-3.5" />
      {current.label}
    </span>
  )
}
