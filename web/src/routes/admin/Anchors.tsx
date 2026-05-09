import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Anchor } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { api, formatApiError } from '@/lib/api'

interface AnchorResponse {
  anchor_date: string
  root_hash: string
  event_count: number
}

export function AdminAnchors() {
  const [yesterday, setYesterday] = useState(true)
  const [result, setResult] = useState<AnchorResponse | null>(null)

  const compute = useMutation({
    mutationFn: async () =>
      api.post<AnchorResponse>('/admin/chain-anchors/compute', undefined, {
        query: { anchor_for_yesterday: yesterday },
      }),
    onSuccess: (data) => {
      setResult(data)
      toast.success(`已計算 ${data.anchor_date} 的 root hash`)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div>
      <PageHeader title="Hash Chain Anchor" description="對指定日期計算 daily Merkle root，作為未來 blockchain anchor 的離線憑證。" />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Anchor className="size-4" />
            計算 anchor
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>計算日期</Label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                className={
                  'rounded-md border px-3 py-2 text-sm transition-colors ' +
                  (yesterday
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border hover:bg-muted')
                }
                onClick={() => setYesterday(true)}
              >
                昨天（預設）
              </button>
              <button
                type="button"
                className={
                  'rounded-md border px-3 py-2 text-sm transition-colors ' +
                  (!yesterday
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border hover:bg-muted')
                }
                onClick={() => setYesterday(false)}
              >
                今天（測試用）
              </button>
            </div>
          </div>
          <Button
            size="lg"
            className="w-full"
            disabled={compute.isPending}
            onClick={() => compute.mutate()}
          >
            {compute.isPending ? '計算中…' : '送出計算請求'}
          </Button>
        </CardContent>
      </Card>

      {result ? (
        <Card className="mt-5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Badge variant="secondary">{result.anchor_date}</Badge>
              Anchor 結果
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <Label className="text-xs text-muted-foreground">事件數</Label>
              <div className="text-2xl font-semibold tabular-nums">{result.event_count}</div>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Root hash</Label>
              <code className="mt-1 block break-all rounded bg-muted px-3 py-2 font-mono text-xs">
                {result.root_hash}
              </code>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
