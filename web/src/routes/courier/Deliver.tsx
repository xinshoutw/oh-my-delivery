import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { KeyRound, Truck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, ApiRequestError, formatApiError } from '@/lib/api'
import type {
  AssetType,
  CourierOrderItem,
  DeliverFailure,
  DeliverSuccess,
} from '@/types/api'
import { formatDateTime, shortId } from '@/lib/utils'

const ASSET_LABEL: Record<AssetType, string> = {
  meal_box: '餐盒',
  drink_cup: '飲料杯',
}

export function CourierDeliver() {
  const qc = useQueryClient()
  const orders = useQuery({
    queryKey: ['courier', 'orders', 'picked_up'],
    queryFn: () =>
      api.get<CourierOrderItem[]>('/lists/courier/orders', { query: { status: 'picked_up' } }),
  })

  const [activeOrder, setActiveOrder] = useState<CourierOrderItem | null>(null)
  const [pin, setPin] = useState('')
  const [success, setSuccess] = useState<DeliverSuccess | null>(null)
  const [failure, setFailure] = useState<DeliverFailure | null>(null)

  const deliver = useMutation({
    mutationFn: async () => {
      if (!activeOrder) throw new Error('no order selected')
      return api.post<DeliverSuccess>(`/courier/orders/${activeOrder.order_id}/deliver`, {
        pin: pin.trim(),
      })
    },
    onSuccess: (data) => {
      setSuccess(data)
      setFailure(null)
      toast.success('PIN 驗證成功')
      void qc.invalidateQueries({ queryKey: ['courier', 'orders'] })
    },
    onError: (err) => {
      setSuccess(null)
      if (err instanceof ApiRequestError && err.status === 401) {
        const detail = err.detail as DeliverFailure | string | undefined
        if (typeof detail === 'object' && detail) {
          setFailure(detail)
          toast.error(`PIN 驗證失敗：${detail.reason}`)
          return
        }
      }
      toast.error(formatApiError(err))
    },
  })

  const onSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!activeOrder) return toast.error('請先選訂單')
    if (!/^\d{4,8}$/.test(pin.trim())) return toast.error('PIN 必須為 4–8 位數字')
    setSuccess(null)
    setFailure(null)
    deliver.mutate()
  }

  return (
    <div>
      <PageHeader title="交付訂單" description="從已取餐的訂單清單挑一筆，輸入消費者提供的 PIN 完成交付。" />

      {!activeOrder ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Truck className="size-4" /> 已取餐、待交付
            </CardTitle>
          </CardHeader>
          <CardContent>
            {orders.isLoading ? (
              <p className="text-sm text-muted-foreground">載入中…</p>
            ) : (orders.data ?? []).length === 0 ? (
              <EmptyState title="目前沒有可交付的訂單" />
            ) : (
              <ul className="space-y-2">
                {orders.data!.map((o) => (
                  <li key={o.order_id}>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveOrder(o)
                        setSuccess(null)
                        setFailure(null)
                        setPin('')
                      }}
                      className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                    >
                      <div>
                        <div className="font-medium">{o.external_order_id}</div>
                        <div className="text-xs text-muted-foreground">
                          消費者 {shortId(o.consumer_id)}・取餐於 {formatDateTime(o.created_at)}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Object.entries(o.expected_asset_manifest).map(([t, n]) => (
                            <Badge key={t} variant="secondary">
                              {ASSET_LABEL[t as AssetType] ?? t} × {n}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <Badge>輸入 PIN</Badge>
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
            <CardTitle className="flex items-center gap-2 text-base">
              <KeyRound className="size-4" />
              交付訂單 {activeOrder.external_order_id}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="del-pin">PIN（消費者提供）</Label>
                <Input
                  id="del-pin"
                  placeholder="6 位數字"
                  value={pin}
                  inputMode="numeric"
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  maxLength={8}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setActiveOrder(null)
                    setPin('')
                  }}
                >
                  返回列表
                </Button>
                <Button type="submit" disabled={deliver.isPending}>
                  {deliver.isPending ? '驗證中…' : '送出 PIN'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {failure ? (
        <Card className="mt-4 border-destructive/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Badge variant="destructive">{failure.status}</Badge>
              交付失敗
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <Row label="原因" value={failure.reason} />
            <Row label="剩餘嘗試" value={String(failure.remaining_attempts)} />
            <Row label="需客服介入" value={failure.support_required ? '是' : '否'} />
          </CardContent>
        </Card>
      ) : null}

      {success ? (
        <Card className="mt-4 border-success/50">
          <CardHeader>
            <CardTitle className="text-base">交付完成</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="消費者" value={shortId(success.consumer_id)} mono />
            <Row label="錢包餘額" value={String(success.consumer_wallet_balance_after)} />
            <ul className="divide-y divide-border rounded-md border border-border">
              {success.delivered_assets.map((a) => (
                <li key={a.deposit_id} className="space-y-1 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary">{ASSET_LABEL[a.asset_type]}</Badge>
                    <span className="font-mono text-xs">押金 {a.deposit_amount}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    歸還期限 {formatDateTime(a.due_at)}・獎勵截止 {formatDateTime(a.reward_cutoff_at)}
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1.5 last:border-b-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-xs break-all' : 'text-sm'}>{value}</span>
    </div>
  )
}
