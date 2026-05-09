import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Droplets } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type { CleaningAssetItem } from '@/types/api'
import { cn, shortId } from '@/lib/utils'

export function CleaningWashing() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['cleaning', 'assets', 'washing'],
    queryFn: () =>
      api.get<CleaningAssetItem[]>('/lists/cleaning/assets', { query: { status: 'washing' } }),
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())

  const items = useMemo(() => list.data ?? [], [list.data])

  const complete = useMutation({
    mutationFn: async () =>
      api.post<{ asset_ids: string[]; new_status: string }>(
        '/cleaning/washing-batches/complete',
        { asset_ids: Array.from(selected) },
      ),
    onSuccess: (data) => {
      toast.success(`完成清洗 ${data.asset_ids.length} 件`)
      setSelected(new Set())
      void qc.invalidateQueries({ queryKey: ['cleaning'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const allChecked = items.length > 0 && items.every((a) => selected.has(a.asset_id))

  return (
    <div>
      <PageHeader title="完成清洗" description="把 washing 中的資產勾選後一鍵標為 cleaned_ready。" />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Droplets className="size-4" /> 清洗中資產
          </CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : items.length === 0 ? (
            <EmptyState
              title="目前沒有 washing 中的資產"
              description="檢查 usable 後會自動進入 washing。"
            />
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-muted"
                  onClick={() =>
                    setSelected(allChecked ? new Set() : new Set(items.map((a) => a.asset_id)))
                  }
                >
                  {allChecked ? '取消全選' : '全選'}
                </button>
                <span className="text-xs text-muted-foreground">
                  已選 {selected.size} / {items.length}
                </span>
              </div>
              <ul className="space-y-2">
                {items.map((a) => {
                  const checked = selected.has(a.asset_id)
                  return (
                    <li key={a.asset_id}>
                      <button
                        type="button"
                        onClick={() => toggle(a.asset_id)}
                        className={cn(
                          'flex w-full items-center justify-between rounded-md border px-3 py-2.5 text-left text-sm transition-colors',
                          checked
                            ? 'border-primary bg-primary/10'
                            : 'border-border hover:bg-muted',
                        )}
                      >
                        <div>
                          <div className="font-medium">
                            {a.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}・{a.short_code}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            ID {shortId(a.asset_id)}・使用 {a.usage_count} 次
                          </div>
                        </div>
                        <Badge variant={checked ? 'success' : 'secondary'}>
                          {checked ? '已選' : '勾選'}
                        </Badge>
                      </button>
                    </li>
                  )
                })}
              </ul>
              <Button
                size="lg"
                className="mt-4 w-full"
                disabled={selected.size === 0 || complete.isPending}
                onClick={() => complete.mutate()}
              >
                {complete.isPending
                  ? '提交中…'
                  : `將 ${selected.size} 件標為 cleaned_ready`}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
