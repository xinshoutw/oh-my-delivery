import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ClipboardList } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type { CleaningAssetItem } from '@/types/api'
import { cn, shortId } from '@/lib/utils'

type Condition = 'usable' | 'damaged' | 'retired'
type ComponentState = 'ok' | 'missing' | 'damaged'

const COMPONENTS = [
  { key: 'lid', label: '蓋子' },
  { key: 'chopsticks', label: '筷子' },
  { key: 'fork', label: '叉子' },
  { key: 'spoon', label: '湯匙' },
]
const STATES: ComponentState[] = ['ok', 'missing', 'damaged']

export function CleaningInspect() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['cleaning', 'assets', 'returned'],
    queryFn: () =>
      api.get<CleaningAssetItem[]>('/lists/cleaning/assets', {
        query: { status: 'returned_to_cleaning_center' },
      }),
  })

  const [active, setActive] = useState<CleaningAssetItem | null>(null)
  const [condition, setCondition] = useState<Condition>('usable')
  const [componentStatus, setComponentStatus] = useState<Record<string, ComponentState>>({
    lid: 'ok',
    chopsticks: 'ok',
    fork: 'ok',
    spoon: 'ok',
  })
  const [notes, setNotes] = useState('')

  const inspect = useMutation({
    mutationFn: async () => {
      if (!active) throw new Error('no asset selected')
      return api.post<{ asset_id: string; new_status: string }>('/cleaning/inspection', {
        asset_id: active.asset_id,
        condition,
        component_status: componentStatus,
        notes: notes.trim() || null,
      })
    },
    onSuccess: (data) => {
      toast.success(`新狀態：${data.new_status}`)
      setActive(null)
      setNotes('')
      void qc.invalidateQueries({ queryKey: ['cleaning'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const items = useMemo(() => list.data ?? [], [list.data])

  return (
    <div>
      <PageHeader
        title="檢查 / 評定"
        description="從待檢查的回流資產清單挑一件做檢查，記錄主資產 condition 與小零件狀態。"
      />

      {!active ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardList className="size-4" /> 待檢查資產
            </CardTitle>
          </CardHeader>
          <CardContent>
            {list.isLoading ? (
              <p className="text-sm text-muted-foreground">載入中…</p>
            ) : items.length === 0 ? (
              <EmptyState title="沒有待檢查的資產" description="收貨確認後會出現在這裡。" />
            ) : (
              <ul className="space-y-2">
                {items.map((a) => (
                  <li key={a.asset_id}>
                    <button
                      type="button"
                      onClick={() => setActive(a)}
                      className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                    >
                      <div>
                        <div className="font-medium">
                          {a.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}・{a.short_code}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          ID {shortId(a.asset_id)}・使用 {a.usage_count} 次
                        </div>
                      </div>
                      <Badge>檢查</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              檢查 {active.short_code}（{active.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}）
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Condition</Label>
              <div className="grid grid-cols-3 gap-2">
                {(['usable', 'damaged', 'retired'] as Condition[]).map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCondition(c)}
                    className={cn(
                      'rounded-md border px-3 py-2 text-sm capitalize',
                      condition === c
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-muted',
                    )}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>小零件狀態</Label>
              <div className="space-y-2 rounded-md border border-border p-3">
                {COMPONENTS.map((c) => (
                  <div key={c.key} className="flex items-center justify-between gap-2">
                    <span className="text-sm">{c.label}</span>
                    <div className="flex gap-1">
                      {STATES.map((s) => {
                        const active = componentStatus[c.key] === s
                        const variant: 'success' | 'destructive' | 'warning' | 'secondary' =
                          s === 'ok' ? 'success' : s === 'missing' ? 'warning' : 'destructive'
                        return (
                          <button
                            key={s}
                            type="button"
                            onClick={() => setComponentStatus((p) => ({ ...p, [c.key]: s }))}
                            className={cn(
                              'rounded-full border px-2.5 py-0.5 text-xs',
                              active
                                ? 'border-transparent'
                                : 'border-border bg-bg text-muted-foreground hover:bg-muted',
                            )}
                          >
                            {active ? <Badge variant={variant}>{s}</Badge> : s}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>備註</Label>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={512} />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => setActive(null)}>
                返回列表
              </Button>
              <Button onClick={() => inspect.mutate()} disabled={inspect.isPending}>
                {inspect.isPending ? '提交中…' : '提交檢查'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
