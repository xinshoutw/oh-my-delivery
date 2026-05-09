import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CheckCircle2, Package, ScanLine, X, Truck } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ScanInput } from '@/components/common/ScanInput'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type {
  AssetType,
  ConfirmPickupResponse,
  CourierOrderItem,
  PickupSession,
  ProgressEntry,
  RestaurantInventoryItem,
  ScanResult,
} from '@/types/api'
import { formatDateTime, shortId } from '@/lib/utils'

const ASSET_LABEL: Record<AssetType, string> = {
  meal_box: '餐盒',
  drink_cup: '飲料杯',
}

export function CourierSession() {
  const qc = useQueryClient()
  const [session, setSession] = useState<PickupSession | null>(null)
  const [progress, setProgress] = useState<Partial<Record<AssetType, ProgressEntry>>>({})
  const [tab, setTab] = useState<'token' | 'short_code'>('token')
  const [token, setToken] = useState('')
  const [shortCode, setShortCode] = useState('')
  const [scanLog, setScanLog] = useState<ScanResult[]>([])
  const [confirmed, setConfirmed] = useState<ConfirmPickupResponse | null>(null)

  const orders = useQuery({
    queryKey: ['courier', 'orders', 'created'],
    queryFn: () =>
      api.get<CourierOrderItem[]>('/lists/courier/orders', { query: { status: 'created' } }),
  })

  const inventory = useQuery({
    queryKey: ['courier', 'restaurant-inventory', session?.order_id],
    queryFn: () =>
      api.get<RestaurantInventoryItem[]>('/lists/restaurant/inventory', {
        query: { order_id: session!.order_id },
      }),
    enabled: Boolean(session?.order_id),
    refetchInterval: 15_000,
  })

  const create = useMutation({
    mutationFn: async (orderId: string) =>
      api.post<PickupSession>(`/courier/orders/${orderId}/pickup-sessions`),
    onSuccess: (data) => {
      setSession(data)
      setProgress(data.expected_manifest as never)
      setScanLog([])
      setConfirmed(null)
      toast.success('Session 建立完成，開始掃描')
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const scan = useMutation({
    mutationFn: async ({
      sessionId,
      payload,
    }: {
      sessionId: string
      payload: { asset_token?: string; short_code?: string }
    }) => api.post<ScanResult>(`/courier/pickup-sessions/${sessionId}/scan`, payload),
    onSuccess: (data) => {
      setProgress(data.progress)
      setScanLog((log) => [data, ...log].slice(0, 20))
      if (data.accepted) {
        toast.success(`已接受 ${data.asset_public_code ?? ''}`)
      } else if (data.already_scanned) {
        toast.info('已掃描過')
      } else {
        toast.error(`拒絕：${data.reject_reason ?? 'unknown'}`)
      }
      setToken('')
      setShortCode('')
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const confirm = useMutation({
    mutationFn: async (sessionId: string) =>
      api.post<ConfirmPickupResponse>(`/courier/pickup-sessions/${sessionId}/confirm`),
    onSuccess: (data) => {
      setConfirmed(data)
      toast.success(`確認完成，已轉移 ${data.transferred_assets.length} 件`)
      void qc.invalidateQueries({ queryKey: ['courier'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const cancel = useMutation({
    mutationFn: async (sessionId: string) =>
      api.post<{ pickup_session_id: string; status: string }>(
        `/courier/pickup-sessions/${sessionId}/cancel`,
      ),
    onSuccess: () => {
      toast.info('Session 已取消')
      setSession(null)
      setProgress({})
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const onScan = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!session) return
    if (tab === 'token' && !token.trim()) return toast.error('請輸入或掃描 token')
    if (tab === 'short_code' && !shortCode.trim()) return toast.error('請輸入 short code')
    scan.mutate({
      sessionId: session.pickup_session_id,
      payload: {
        asset_token: tab === 'token' ? token.trim() : undefined,
        short_code: tab === 'short_code' ? shortCode.trim() : undefined,
      },
    })
  }

  const fullyScanned = Object.entries(progress).every(
    ([, p]) => (p?.scanned ?? 0) >= (p?.expected ?? 0),
  )

  return (
    <div>
      <PageHeader
        title="取餐 Session"
        description="從待取餐訂單清單挑一筆，逐件掃描，全部齊全後一鍵確認。"
      />

      {!session ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Truck className="size-4" /> 待取餐訂單
            </CardTitle>
          </CardHeader>
          <CardContent>
            {orders.isLoading ? (
              <p className="text-sm text-muted-foreground">載入中…</p>
            ) : orders.isError ? (
              <p className="text-sm text-destructive">{formatApiError(orders.error)}</p>
            ) : (orders.data ?? []).length === 0 ? (
              <EmptyState title="目前沒有待取餐的訂單" description="管理員或 Partner 建單後會出現在這裡。" />
            ) : (
              <ul className="space-y-2">
                {orders.data!.map((o) => (
                  <li key={o.order_id}>
                    <button
                      type="button"
                      onClick={() => create.mutate(o.order_id)}
                      disabled={create.isPending}
                      className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                    >
                      <div>
                        <div className="font-medium">{o.external_order_id}</div>
                        <div className="text-xs text-muted-foreground">
                          餐廳 {shortId(o.restaurant_id)}・建立於 {formatDateTime(o.created_at)}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Object.entries(o.expected_asset_manifest).map(([t, n]) => (
                            <Badge key={t} variant="secondary">
                              {ASSET_LABEL[t as AssetType] ?? t} × {n}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <Badge>取餐</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span>進度</span>
                <Badge variant={fullyScanned ? 'success' : 'warning'}>
                  {fullyScanned ? '可確認' : '尚未掃完'}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Session</span>
                <span className="font-mono text-xs">{shortId(session.pickup_session_id)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">到期</span>
                <span>{formatDateTime(session.expires_at)}</span>
              </div>
              <div className="grid gap-2">
                {Object.entries(progress).map(([type, entry]) => {
                  const expected = entry?.expected ?? 0
                  const scanned = entry?.scanned ?? 0
                  const pct = expected ? Math.min(100, (scanned / expected) * 100) : 0
                  return (
                    <div key={type} className="rounded-md border border-border p-3">
                      <div className="mb-2 flex items-center justify-between text-sm">
                        <span>{ASSET_LABEL[type as AssetType] ?? type}</span>
                        <span className="font-mono">
                          {scanned} / {expected}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full bg-primary transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          {!confirmed ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Package className="size-4" /> 餐廳可掃資產
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    ({(inventory.data ?? []).length} 件)
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                {inventory.isLoading ? (
                  <p className="text-sm text-muted-foreground">載入中…</p>
                ) : (inventory.data ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    餐廳目前沒有 at_restaurant 的資產，請確認是否已簽收 dispatch。
                  </p>
                ) : (
                  <ul className="grid gap-1.5 sm:grid-cols-2">
                    {inventory.data!.map((a) => (
                      <li key={a.asset_id}>
                        <button
                          type="button"
                          onClick={() => {
                            setTab('short_code')
                            setShortCode(a.short_code)
                            toast.success(`已帶入 ${a.short_code}，按送出即可掃`)
                          }}
                          className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-muted"
                        >
                          <span className="flex items-center gap-2">
                            <Badge variant="secondary">{ASSET_LABEL[a.asset_type]}</Badge>
                            <span className="font-mono text-xs">{a.short_code}</span>
                          </span>
                          <Badge variant="outline">點擊代填</Badge>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          ) : null}

          {!confirmed ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ScanLine className="size-4" /> 掃描
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={onScan} className="space-y-3">
                  <Tabs value={tab} onValueChange={(v) => setTab(v as 'token' | 'short_code')}>
                    <TabsList className="grid w-full grid-cols-2">
                      <TabsTrigger value="token">QR Token</TabsTrigger>
                      <TabsTrigger value="short_code">8 碼</TabsTrigger>
                    </TabsList>
                    <TabsContent value="token">
                      <ScanInput
                        value={token}
                        onChange={setToken}
                        placeholder="按相機掃描或貼上 token"
                        scannerTitle="掃描餐具 QR Code"
                      />
                    </TabsContent>
                    <TabsContent value="short_code">
                      <ScanInput
                        value={shortCode}
                        onChange={(v) => setShortCode(v.toUpperCase())}
                        placeholder="8 碼"
                        maxLength={8}
                        scannerTitle="掃 QR 自動代填"
                      />
                    </TabsContent>
                  </Tabs>
                  <Button type="submit" size="lg" className="w-full" disabled={scan.isPending}>
                    {scan.isPending ? '送出中…' : '送出'}
                  </Button>
                </form>
              </CardContent>
            </Card>
          ) : null}

          {!confirmed ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <Button
                size="lg"
                disabled={!fullyScanned || confirm.isPending}
                onClick={() => confirm.mutate(session.pickup_session_id)}
              >
                <CheckCircle2 className="size-4" />
                {confirm.isPending ? '確認中…' : '確認取餐'}
              </Button>
              <Button
                variant="outline"
                size="lg"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(session.pickup_session_id)}
              >
                <X className="size-4" />
                取消 session
              </Button>
            </div>
          ) : (
            <Card className="border-success/50">
              <CardHeader>
                <CardTitle className="text-base">已轉移資產</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">
                  Order {shortId(confirmed.order_id)}・共 {confirmed.transferred_assets.length} 件
                </p>
                <ul className="divide-y divide-border rounded-md border border-border">
                  {confirmed.transferred_assets.map((a) => (
                    <li key={a.asset_id} className="flex items-center justify-between px-3 py-2">
                      <span className="font-mono text-xs">{a.public_code}</span>
                      <Badge variant="secondary">{ASSET_LABEL[a.asset_type]}</Badge>
                    </li>
                  ))}
                </ul>
                <Button
                  variant="outline"
                  className="mt-2 w-full"
                  onClick={() => {
                    setSession(null)
                    setConfirmed(null)
                    setProgress({})
                    void orders.refetch()
                  }}
                >
                  返回訂單列表
                </Button>
              </CardContent>
            </Card>
          )}

          {scanLog.length > 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">最近掃描</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5 text-xs">
                  {scanLog.map((s, i) => (
                    <li
                      key={i}
                      className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                    >
                      <span className="font-mono">{s.asset_public_code ?? '-'}</span>
                      <Badge
                        variant={
                          s.accepted ? 'success' : s.already_scanned ? 'warning' : 'destructive'
                        }
                      >
                        {s.accepted ? '接受' : s.already_scanned ? '已掃' : (s.reject_reason ?? '拒絕')}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}
