import { Badge } from '@/components/ui/badge'

const VARIANT_BY_KEYWORD: Array<{ test: (s: string) => boolean; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'default' }> = [
  { test: (s) => s.includes('cleaned') || s.includes('delivered') || s.includes('acknowledged'), variant: 'success' },
  { test: (s) => s.includes('pending') || s.includes('washing') || s.includes('transit'), variant: 'warning' },
  { test: (s) => s.includes('damaged') || s.includes('lost') || s.includes('locked') || s.includes('failed') || s.includes('cancelled'), variant: 'destructive' },
  { test: () => true, variant: 'secondary' },
]

interface Props {
  status: string
}

export function StatusPill({ status }: Props) {
  const lower = status.toLowerCase()
  const match = VARIANT_BY_KEYWORD.find((v) => v.test(lower))
  return <Badge variant={match?.variant ?? 'secondary'}>{status}</Badge>
}
