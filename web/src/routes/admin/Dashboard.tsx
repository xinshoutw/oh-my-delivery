import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, formatApiError } from '@/lib/api'
import type { DashboardSummary } from '@/types/api'

export function AdminDashboard() {
  const query = useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => api.get<DashboardSummary>('/admin/dashboard'),
    refetchInterval: 30_000,
  })

  return (
    <div>
      <PageHeader
        title="儀表板"
        description="即時系統指標。每 30 秒自動重新整理一次。"
        actions={
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>
            <RefreshCw className="size-4" />
            重新整理
          </Button>
        }
      />

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">載入中…</p>
      ) : query.isError ? (
        <p className="text-sm text-destructive">{formatApiError(query.error)}</p>
      ) : query.data ? (
        <Summary data={query.data} />
      ) : null}
    </div>
  )
}

function Summary({ data }: { data: DashboardSummary }) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="總資產" value={data.total_assets} />
        <Stat label="進行中循環" value={data.active_cycles} />
        <Stat label="已完成循環" value={data.completed_cycles} />
        <Stat label="總消費者" value={data.total_consumers} />
        <Stat label="押金 active" value={data.active_deposits} />
        <Stat label="押金 released" value={data.released_deposits} />
        <Stat label="押金 charged" value={data.charged_deposits} />
        <Stat label="獎勵點數已發" value={data.total_points_granted} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">資產狀態分布</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.assets_by_status).map(([s, c]) => (
              <Badge key={s} variant="secondary" className="text-xs">
                {s}: {c}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">訂單狀態分布</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.orders_by_status).map(([s, c]) => (
              <Badge key={s} variant="secondary" className="text-xs">
                {s}: {c}
              </Badge>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            總訂單 {data.total_orders}・平均錢包餘額 {data.avg_wallet_balance.toFixed(2)}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{value.toLocaleString()}</div>
      </CardContent>
    </Card>
  )
}
