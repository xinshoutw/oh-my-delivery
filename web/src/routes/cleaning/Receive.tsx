import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScanInput } from '@/components/common/ScanInput'
import { api, formatApiError } from '@/lib/api'
import type { ReceivedAsset } from '@/types/api'
import { shortId } from '@/lib/utils'

export function CleaningReceive() {
  const [tokens, setTokens] = useState<string[]>([''])
  const [results, setResults] = useState<ReceivedAsset[]>([])

  const receive = useMutation({
    mutationFn: async () =>
      api.post<{ received: ReceivedAsset[] }>('/cleaning/receive', {
        asset_tokens: tokens.map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: (data) => {
      setResults(data.received)
      toast.success(`收貨 ${data.received.length} 件，押金與獎勵已結算`)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const onSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    const valid = tokens.filter((t) => t.trim())
    if (valid.length === 0) return toast.error('至少輸入或掃描一個 token')
    receive.mutate()
  }

  return (
    <div>
      <PageHeader
        title="收貨確認"
        description="清洗中心收到回流資產時逐件掃描。這是「歸還完成」的最終事實，會觸發押金釋放/扣款與獎勵發放。"
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">掃描 / 輸入 token</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-3">
            <ul className="space-y-2">
              {tokens.map((t, i) => (
                <li key={i} className="flex items-center gap-2">
                  <ScanInput
                    value={t}
                    onChange={(v) => {
                      const next = [...tokens]
                      next[i] = v
                      setTokens(next)
                      // auto-add a fresh empty row when last row scanned
                      if (i === tokens.length - 1 && v.trim()) {
                        setTokens([...next, ''])
                      }
                    }}
                    placeholder={`token ${i + 1}`}
                    scannerTitle="掃描 QR Code（逐件）"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    type="button"
                    onClick={() =>
                      setTokens((arr) =>
                        arr.length === 1 ? [''] : arr.filter((_, idx) => idx !== i),
                      )
                    }
                    aria-label="移除"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => setTokens((arr) => [...arr, ''])}
            >
              <Plus className="size-4" /> 新增欄位
            </Button>
            <Button type="submit" size="lg" className="w-full" disabled={receive.isPending}>
              {receive.isPending ? '處理中…' : '收貨確認'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {results.length > 0 ? (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-base">結算結果</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border rounded-md border border-border">
              {results.map((r) => (
                <li key={r.asset_id} className="space-y-1 px-3 py-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs">{shortId(r.asset_id)}</span>
                    <Badge variant="secondary">{r.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}</Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge
                      variant={
                        r.deposit_outcome === 'released'
                          ? 'success'
                          : r.deposit_outcome === 'charged'
                            ? 'destructive'
                            : 'secondary'
                      }
                    >
                      押金: {r.deposit_outcome}
                    </Badge>
                    <Badge variant={r.reward_granted ? 'success' : 'secondary'}>
                      獎勵: {r.reward_granted ? `+${r.reward_points}` : '無'}
                    </Badge>
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
