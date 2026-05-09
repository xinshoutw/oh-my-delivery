import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Send } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, formatApiError } from '@/lib/api'

export function AdminNotifications() {
  const [limit, setLimit] = useState(200)
  const [lastDispatched, setLastDispatched] = useState<number | null>(null)

  const dispatch = useMutation({
    mutationFn: async () =>
      api.post<{ dispatched: number }>('/admin/notifications/dispatch', undefined, {
        query: { limit },
      }),
    onSuccess: (data) => {
      setLastDispatched(data.dispatched)
      toast.success(`已派送 ${data.dispatched} 筆通知`)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const onSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (limit < 1 || limit > 10_000) return toast.error('limit 範圍 1–10000')
    dispatch.mutate()
  }

  return (
    <div>
      <PageHeader title="通知派送" description="手動觸發 NotificationService.dispatch_due，從 notifications 表撈出 due 的通知並派送。" />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Send className="size-4" />
            派送設定
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="limit">每批最大筆數</Label>
              <Input
                id="limit"
                type="number"
                min={1}
                max={10_000}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
              />
            </div>
            <Button type="submit" size="lg" className="w-full" disabled={dispatch.isPending}>
              {dispatch.isPending ? '派送中…' : '立即派送'}
            </Button>
          </form>
          {lastDispatched !== null ? (
            <p className="mt-3 text-sm text-muted-foreground">
              上次派送：<span className="font-medium text-fg">{lastDispatched}</span> 筆
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
