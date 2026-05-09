import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, Copy, Package, Truck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type { AssetType, RestaurantDispatchItem, RestaurantInventoryItem } from '@/types/api'
import { formatDateTime, shortId } from '@/lib/utils'

const ASSET_LABEL: Record<AssetType, string> = {
  meal_box: '餐盒',
  drink_cup: '飲料杯',
}

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

  const inventory = useQuery({
    queryKey: ['restaurant', 'inventory'],
    queryFn: () => api.get<RestaurantInventoryItem[]>('/lists/restaurant/inventory'),
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
      void qc.invalidateQueries({ queryKey: ['restaurant', 'inventory'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const copy = (txt: string) => {
    navigator.clipboard.writeText(txt).then(
      () => toast.success(`已複製 ${txt}`),
      () => toast.error('複製失敗'),
    )
  }

  return (
    <div>
      <PageHeader
        title="餐廳作業"
        description="待簽收 dispatch 一鍵確認；下方列出店內目前可供外送員取餐的循環餐具。"
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

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Package className="size-4" /> 店內庫存
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              ({(inventory.data ?? []).length} 件)
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {inventory.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : inventory.isError ? (
            <p className="text-sm text-destructive">{formatApiError(inventory.error)}</p>
          ) : (inventory.data ?? []).length === 0 ? (
            <EmptyState
              title="店內目前沒有可取餐的資產"
              description="先確認上方的 dispatch，資產才會進入店內庫存。"
            />
          ) : (
            <>
              <p className="mb-2 text-xs text-muted-foreground">
                點 short_code 可複製，方便外送員 demo 時直接貼到掃描欄位。
              </p>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {inventory.data!.map((a) => (
                  <li
                    key={a.asset_id}
                    className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm"
                  >
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{ASSET_LABEL[a.asset_type]}</Badge>
                      <button
                        type="button"
                        onClick={() => copy(a.short_code)}
                        className="font-mono text-xs underline-offset-2 hover:underline"
                        title="點擊複製"
                      >
                        {a.short_code}
                      </button>
                    </div>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => copy(a.short_code)}
                      aria-label="複製 short code"
                    >
                      <Copy className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
