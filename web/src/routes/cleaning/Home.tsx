import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Boxes } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { api, formatApiError } from '@/lib/api'
import type { CleaningAssetItem } from '@/types/api'

const TILES = [
  { to: '/cleaning/assets', title: '建立資產', desc: '產生新餐盒 / 飲料杯與 token、short_code' },
  { to: '/cleaning/receive', title: '收貨確認', desc: '掃描回流資產，觸發押金釋放與獎勵' },
  { to: '/cleaning/inspection', title: '檢查', desc: 'usable / damaged / retired 與小零件狀態' },
  { to: '/cleaning/washing', title: '完成清洗', desc: '批次將資產標為 cleaned_ready' },
  { to: '/cleaning/dispatch', title: '出貨', desc: '建立 dispatch 送往餐廳' },
]

const PRIMARY_GROUPS: { label: string; statuses: string[] }[] = [
  { label: '新建立', statuses: ['manufactured'] },
  { label: '在中心', statuses: ['at_cleaning_center'] },
  { label: '清洗中', statuses: ['washing'] },
  { label: '檢查中', statuses: ['under_inspection'] },
  { label: '可出貨', statuses: ['cleaned_ready'] },
  { label: '回流中', statuses: ['returned_to_cleaning_center'] },
]

export function CleaningHome() {
  const list = useQuery({
    queryKey: ['cleaning', 'assets', 'all'],
    queryFn: () => api.get<CleaningAssetItem[]>('/lists/cleaning/assets', { query: { limit: 1000 } }),
    refetchInterval: 30_000,
  })

  const counts = (list.data ?? []).reduce<Record<string, number>>((acc, a) => {
    acc[a.status] = (acc[a.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div>
      <PageHeader title="清洗中心總覽" description="從建立資產到出貨完整循環，每一步都會落入 hash chain。" />

      <Card className="mb-5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Boxes className="size-4" /> 資產分布
          </CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : list.isError ? (
            <p className="text-sm text-destructive">{formatApiError(list.error)}</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {PRIMARY_GROUPS.map((g) => {
                const total = g.statuses.reduce((sum, s) => sum + (counts[s] ?? 0), 0)
                return (
                  <div
                    key={g.label}
                    className="rounded-md border border-border bg-bg p-3"
                  >
                    <div className="text-xs text-muted-foreground">{g.label}</div>
                    <div className="mt-1 text-2xl font-semibold tabular-nums">{total}</div>
                  </div>
                )
              })}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
            {Object.entries(counts).map(([s, c]) => (
              <Badge key={s} variant="secondary">
                {s}: {c}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        {TILES.map((t) => (
          <Link key={t.to} to={t.to}>
            <Card className="h-full transition-colors hover:border-primary/40 hover:bg-muted/40">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                  {t.title}
                  <ArrowRight className="size-4 text-muted-foreground" />
                </CardTitle>
                <CardDescription>{t.desc}</CardDescription>
              </CardHeader>
              <CardContent />
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
