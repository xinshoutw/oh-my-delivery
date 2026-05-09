import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Inbox, ScanLine, X } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { ScanInput } from '@/components/common/ScanInput'
import { api, bootstrapApi, formatApiError } from '@/lib/api'
import type { ReturnBoxAccount, ReturnScanResponse } from '@/types/api'
import { cn, formatDateTime } from '@/lib/utils'

interface ScanInput {
  return_box_id: string
  asset_token?: string
  short_code?: string
}

export function ConsumerReturn() {
  const [params] = useSearchParams()
  const initialShortCode = params.get('short_code') ?? ''

  const [returnBoxId, setReturnBoxId] = useState('')
  const [token, setToken] = useState('')
  const [shortCode, setShortCode] = useState(initialShortCode)
  const [tab, setTab] = useState<'short_code' | 'token'>(initialShortCode ? 'short_code' : 'token')
  const [result, setResult] = useState<ReturnScanResponse | null>(null)

  const boxes = useQuery({
    queryKey: ['consumer', 'return-boxes'],
    queryFn: () => bootstrapApi.get<ReturnBoxAccount[]>('/admin/return-boxes'),
  })

  const filteredBoxes = useMemo(() => (boxes.data ?? []).filter((b) => b.active), [boxes.data])

  const scan = useMutation({
    mutationFn: async (input: ScanInput) =>
      api.post<ReturnScanResponse>('/consumer/returns/scan', input),
    onSuccess: (data) => {
      setResult(data)
      toast.success('掃描成功，請投入回收箱')
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const cancel = useMutation({
    mutationFn: async (sessionId: string) =>
      api.post<{ return_session_id: string; status: string }>(
        `/consumer/return-sessions/${sessionId}/cancel`,
      ),
    onSuccess: (data) => {
      toast.info(`已取消 (${data.status})`)
      setResult(null)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const onSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!returnBoxId) return toast.error('請先選回收箱')
    if (tab === 'token' && !token.trim()) return toast.error('請輸入或掃描 token')
    if (tab === 'short_code' && !shortCode.trim()) return toast.error('請輸入 8 碼識別碼')
    scan.mutate({
      return_box_id: returnBoxId,
      asset_token: tab === 'token' ? token.trim() : undefined,
      short_code: tab === 'short_code' ? shortCode.trim() : undefined,
    })
  }

  return (
    <div>
      <PageHeader
        title="掃描歸還"
        description="選回收箱、掃 QR 或輸入 8 碼，再投入箱中即可。系統會在偵測到投入後完成這次歸還。"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Inbox className="size-4" /> 第 1 步：選擇回收箱
          </CardTitle>
        </CardHeader>
        <CardContent>
          {boxes.isLoading ? (
            <p className="text-sm text-muted-foreground">載入回收箱…</p>
          ) : filteredBoxes.length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無回收箱，請請管理員先建立。</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {filteredBoxes.map((b) => {
                const active = returnBoxId === b.id
                return (
                  <li key={b.id}>
                    <button
                      type="button"
                      onClick={() => setReturnBoxId(b.id)}
                      className={cn(
                        'w-full rounded-md border px-3 py-2.5 text-left text-sm transition-colors',
                        active
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-border hover:bg-muted',
                      )}
                    >
                      <div className="font-medium">{b.label}</div>
                      <div className={cn('text-xs', active ? 'text-primary-foreground/80' : 'text-muted-foreground')}>
                        建立於 {formatDateTime(b.created_at)}
                      </div>
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
          <CardTitle className="flex items-center gap-2 text-base">
            <ScanLine className="size-4" /> 第 2 步：掃描資產
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-3">
            <Tabs value={tab} onValueChange={(v) => setTab(v as 'short_code' | 'token')}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="short_code">8 碼</TabsTrigger>
                <TabsTrigger value="token">QR token</TabsTrigger>
              </TabsList>
              <TabsContent value="token" className="space-y-2">
                <Label>Asset token</Label>
                <ScanInput
                  value={token}
                  onChange={setToken}
                  placeholder="按相機開啟掃描，或貼上 R1A.…"
                  scannerTitle="掃描資產 QR Code"
                />
              </TabsContent>
              <TabsContent value="short_code" className="space-y-2">
                <Label>Short code</Label>
                <ScanInput
                  value={shortCode}
                  onChange={(v) => setShortCode(v.toUpperCase())}
                  placeholder="ABCDEF12"
                  maxLength={8}
                  scannerTitle="掃描或拍 8 碼"
                />
              </TabsContent>
            </Tabs>
            <Button type="submit" size="lg" className="w-full" disabled={scan.isPending}>
              {scan.isPending ? '送出中…' : '送出'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result ? (
        <Card className="mt-4 border-success/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              掃描結果
              <Badge variant={result.is_current_holder ? 'success' : 'warning'}>
                {result.is_current_holder ? '目前持有人' : '協助歸還'}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">資產類型</span>
              <span>{result.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">8 碼</span>
              <span className="font-mono">{result.asset_public_code}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">狀態</span>
              <span>{result.status}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">到期</span>
              <span>{formatDateTime(result.expires_at)}</span>
            </div>
            <p className="rounded-md bg-muted/60 p-3 text-xs leading-relaxed">{result.message}</p>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => cancel.mutate(result.return_session_id)}
              disabled={cancel.isPending}
            >
              <X className="size-4" /> 取消
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
