import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, Truck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type { RestaurantDispatchItem } from '@/types/api'
import { formatDateTime, shortId } from '@/lib/utils'

export function RestaurantAck() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['restaurant', 'dispatches', 'pending'],
    queryFn: () =>
      api.get<RestaurantDispatchItem[]>('/lists/restaurant/dispatches', {
        query: { status: 'pending' },
      }),
    refetchInterval: 30_000,
  })

  const ack = useMutation({
    mutationFn: async (dispatchId: string) =>
      api.post<{ dispatch_id: string; acknowledged_count: number; asset_ids: string[] }>(
        `/restaurant/dispatches/${dispatchId}/acknowledge`,
      ),
    onSuccess: (data) => {
      toast.success(`一鍵確認 ${data.acknowledged_count} 件`)
      void qc.invalidateQueries({ queryKey: ['restaurant', 'dispatches'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div>
      <PageHeader
        title="一鍵收貨"
        description="清洗中心送來的待簽收 dispatch。一筆對應一批資產，按下後會一次將所有資產轉為 at_restaurant。"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Truck className="size-4" /> 待收貨清單
          </CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : list.isError ? (
            <p className="text-sm text-destructive">{formatApiError(list.error)}</p>
          ) : (list.data ?? []).length === 0 ? (
            <EmptyState
              title="目前沒有待收貨 dispatch"
              description="清洗中心建立 dispatch 後會出現在這裡。"
            />
          ) : (
            <ul className="space-y-2">
              {list.data!.map((d) => (
                <li
                  key={d.dispatch_id}
                  className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="text-sm">
                    <div className="font-mono text-xs text-muted-foreground">
                      {shortId(d.dispatch_id, 10)}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2">
                      <Badge variant="warning">{d.status}</Badge>
                      <span className="font-medium">{d.asset_count} 件</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      建立於 {formatDateTime(d.created_at)}
                      {d.note ? `・${d.note}` : ''}
                    </div>
                  </div>
                  <Button onClick={() => ack.mutate(d.dispatch_id)} disabled={ack.isPending}>
                    <CheckCircle2 className="size-4" />
                    確認收貨
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
