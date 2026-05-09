import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, bootstrapApi, formatApiError } from '@/lib/api'
import type { CleaningAssetItem, DispatchStatus, Organization } from '@/types/api'
import { cn, formatDateTime, shortId } from '@/lib/utils'

interface DispatchOut {
  id: string
  cleaning_center_id: string
  restaurant_id: string
  status: DispatchStatus
  asset_ids: string[]
  note: string | null
  created_at: string
  acknowledged_at: string | null
}

export function CleaningDispatch() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['cleaning', 'assets', 'cleaned_ready'],
    queryFn: () =>
      api.get<CleaningAssetItem[]>('/lists/cleaning/assets', {
        query: { status: 'cleaned_ready' },
      }),
  })
  const restaurants = useQuery({
    queryKey: ['cleaning', 'restaurants'],
    queryFn: () =>
      bootstrapApi.get<Organization[]>('/admin/organizations', { type: 'restaurant' }),
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [restaurantId, setRestaurantId] = useState('')
  const [note, setNote] = useState('')
  const [stage, setStage] = useState<'select' | 'create'>('select')
  const [result, setResult] = useState<DispatchOut | null>(null)

  const items = useMemo(() => list.data ?? [], [list.data])

  const prepare = useMutation({
    mutationFn: async () =>
      api.post<{ prepared_count: number; asset_ids: string[] }>(
        '/cleaning/assets/prepare-for-dispatch',
        { asset_ids: Array.from(selected) },
      ),
    onSuccess: (data) => {
      toast.success(`${data.prepared_count} 件已標為 in_transit_to_restaurant`)
      setStage('create')
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const create = useMutation({
    mutationFn: async () =>
      api.post<DispatchOut>('/cleaning/dispatches', {
        restaurant_id: restaurantId,
        asset_ids: Array.from(selected),
        note: note.trim() || null,
      }),
    onSuccess: (data) => {
      setResult(data)
      toast.success(`Dispatch ${shortId(data.id)} 建立完成`)
      setSelected(new Set())
      setStage('select')
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

  return (
    <div>
      <PageHeader
        title="出貨"
        description="勾選 cleaned_ready 資產 → prepare（轉為 in_transit）→ 建立 dispatch 通知餐廳。"
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">第 1 步：勾選資產</CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : items.length === 0 ? (
            <EmptyState title="目前沒有 cleaned_ready 資產" description="完成清洗後會出現在這裡。" />
          ) : (
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
                          ID {shortId(a.asset_id)}
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
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">第 2 步：Prepare 與選餐廳</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button
            variant="default"
            className="w-full"
            disabled={selected.size === 0 || prepare.isPending}
            onClick={() => prepare.mutate()}
          >
            {prepare.isPending
              ? 'Prepare 中…'
              : stage === 'select'
                ? `Prepare ${selected.size} 件`
                : '已 prepare（可重做）'}
          </Button>

          <div className="space-y-2">
            <Label>送往餐廳</Label>
            <select
              value={restaurantId}
              onChange={(e) => setRestaurantId(e.target.value)}
              className="h-10 w-full rounded-md border border-border bg-bg px-3 text-sm"
            >
              <option value="">— 選擇 —</option>
              {(restaurants.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label>備註（選填）</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={256} />
          </div>

          <Button
            size="lg"
            className="w-full"
            disabled={
              create.isPending || stage !== 'create' || !restaurantId || selected.size === 0
            }
            onClick={() => create.mutate()}
          >
            {create.isPending ? '建立中…' : '建立 dispatch'}
          </Button>
        </CardContent>
      </Card>

      {result ? (
        <Card className="mt-4 border-success/50">
          <CardHeader>
            <CardTitle className="text-base">Dispatch 已建立</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="ID" value={result.id} mono />
            <Row label="狀態" value={result.status} />
            <Row label="資產數量" value={String(result.asset_ids.length)} />
            <Row label="建立時間" value={formatDateTime(result.created_at)} />
            <p className="text-xs text-muted-foreground">
              請通知餐廳到「一鍵收貨」頁面確認 — 他們的清單會自動列出待 ack 的 dispatch。
            </p>
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
