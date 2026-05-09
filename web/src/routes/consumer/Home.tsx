import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ScanLine, Package } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/common/EmptyState'
import { api, formatApiError } from '@/lib/api'
import type { HoldingItem, AssetType } from '@/types/api'
import { formatDateTime } from '@/lib/utils'

const ASSET_LABEL: Record<AssetType, string> = {
  meal_box: '餐盒',
  drink_cup: '飲料杯',
}

export function ConsumerHome() {
  const holdings = useQuery({
    queryKey: ['consumer', 'holdings'],
    queryFn: () => api.get<HoldingItem[]>('/lists/consumer/holdings'),
    refetchInterval: 30_000,
  })

  return (
    <div>
      <PageHeader
        title="我的持有"
        description="目前還沒歸還的循環餐具。準時歸還可拿回押金與點數。"
        actions={
          <Button asChild>
            <Link to="/consumer/return">
              <ScanLine className="size-4" />
              掃描歸還
            </Link>
          </Button>
        }
      />

      {holdings.isLoading ? (
        <p className="text-sm text-muted-foreground">載入中…</p>
      ) : holdings.isError ? (
        <p className="text-sm text-destructive">{formatApiError(holdings.error)}</p>
      ) : !holdings.data || holdings.data.length === 0 ? (
        <EmptyState
          title="沒有未歸還的資產"
          description="當外送員把餐具交付給你時，會出現在這裡。"
        />
      ) : (
        <ul className="space-y-3">
          {holdings.data.map((h) => (
            <li key={h.asset_id}>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-base">
                    <span className="flex items-center gap-2">
                      <Package className="size-4" />
                      {ASSET_LABEL[h.asset_type]}
                    </span>
                    <Badge variant="outline" className="font-mono">
                      {h.short_code}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <div>
                      <div>狀態</div>
                      <div className="text-fg">{h.status}</div>
                    </div>
                    <div>
                      <div>押金</div>
                      <div className="text-fg">{h.deposit_amount ?? '-'}</div>
                    </div>
                    <div>
                      <div>歸還期限</div>
                      <div className="text-fg">{formatDateTime(h.due_at)}</div>
                    </div>
                    <div>
                      <div>獎勵截止</div>
                      <div className="text-fg">{formatDateTime(h.reward_cutoff_at)}</div>
                    </div>
                  </div>
                  <Button asChild className="w-full">
                    <Link to={`/consumer/return?short_code=${encodeURIComponent(h.short_code)}`}>
                      歸還這個
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
