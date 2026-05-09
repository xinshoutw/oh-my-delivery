import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Copy } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { api, formatApiError } from '@/lib/api'
import type { AssetCreated, AssetType } from '@/types/api'

export function CleaningCreateAssets() {
  const [assetType, setAssetType] = useState<AssetType>('meal_box')
  const [count, setCount] = useState<number>(1)
  const [created, setCreated] = useState<AssetCreated[]>([])

  const create = useMutation({
    mutationFn: async () =>
      api.post<{ created: AssetCreated[] }>('/cleaning/assets', {
        asset_type: assetType,
        count,
      }),
    onSuccess: (data) => {
      setCreated(data.created)
      toast.success(`成功建立 ${data.created.length} 件`)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const onSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (count < 1 || count > 500) return toast.error('數量必須在 1–500 之間')
    create.mutate()
  }

  const copy = (txt: string) => {
    navigator.clipboard.writeText(txt).then(
      () => toast.success('已複製'),
      () => toast.error('複製失敗'),
    )
  }

  return (
    <div>
      <PageHeader title="建立資產" description="一次最多 500 件。token 為一次性回傳，請立即印上 QR code。" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">新增資產</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>資產類型</Label>
              <div className="grid grid-cols-2 gap-2">
                {(['meal_box', 'drink_cup'] as AssetType[]).map((t) => (
                  <button
                    type="button"
                    key={t}
                    onClick={() => setAssetType(t)}
                    className={
                      'rounded-md border px-3 py-2 text-sm transition-colors ' +
                      (assetType === t
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-muted')
                    }
                  >
                    {t === 'meal_box' ? '餐盒' : '飲料杯'}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="count">數量</Label>
              <Input
                id="count"
                type="number"
                min={1}
                max={500}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </div>
            <Button type="submit" size="lg" className="w-full" disabled={create.isPending}>
              {create.isPending ? '建立中…' : '建立'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {created.length > 0 ? (
        <Card className="mt-5">
          <CardHeader>
            <CardTitle className="text-base">建立結果（請立即記錄 token）</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border rounded-md border border-border">
              {created.map((a) => (
                <li key={a.id} className="space-y-1.5 px-3 py-3 text-sm">
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary">
                      {a.asset_type === 'meal_box' ? '餐盒' : '飲料杯'}
                    </Badge>
                    <span className="font-mono text-xs">{a.short_code}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-xs">
                      {a.asset_token}
                    </code>
                    <Button size="icon" variant="outline" onClick={() => copy(a.asset_token)}>
                      <Copy className="size-3.5" />
                    </Button>
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
