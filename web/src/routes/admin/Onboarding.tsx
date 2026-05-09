import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Building2, Copy, Inbox, KeyRound, Plus, Truck, User2, PowerOff } from 'lucide-react'
import { PageHeader } from '@/components/common/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { DeleteButton } from '@/components/common/DeleteButton'
import { api, formatApiError } from '@/lib/api'
import type {
  AssetType,
  ConsumerAccount,
  CourierOrderItem,
  DemoOrderResult,
  Organization,
  PartnerAccount,
  ReturnBoxAccount,
  UserAccount,
  UserRole,
} from '@/types/api'
import { cn, formatDateTime, shortId } from '@/lib/utils'

export function AdminOnboarding() {
  return (
    <div>
      <PageHeader
        title="Onboarding"
        description="一站式建立組織、人員、回收箱、Partner，並可模擬 partner 建單拿到 PIN。"
      />
      <Tabs defaultValue="organizations" className="w-full">
        <TabsList className="grid w-full grid-cols-2 sm:grid-cols-6 gap-0">
          <TabsTrigger value="organizations" className="text-xs sm:text-sm">組織</TabsTrigger>
          <TabsTrigger value="users" className="text-xs sm:text-sm">人員</TabsTrigger>
          <TabsTrigger value="consumers" className="text-xs sm:text-sm">消費者</TabsTrigger>
          <TabsTrigger value="returnboxes" className="text-xs sm:text-sm">回收箱</TabsTrigger>
          <TabsTrigger value="partners" className="text-xs sm:text-sm">Partner</TabsTrigger>
          <TabsTrigger value="orders" className="text-xs sm:text-sm">建立訂單</TabsTrigger>
        </TabsList>

        <TabsContent value="organizations">
          <OrganizationsPanel />
        </TabsContent>
        <TabsContent value="users">
          <UsersPanel />
        </TabsContent>
        <TabsContent value="consumers">
          <ConsumersPanel />
        </TabsContent>
        <TabsContent value="returnboxes">
          <ReturnBoxesPanel />
        </TabsContent>
        <TabsContent value="partners">
          <PartnersPanel />
        </TabsContent>
        <TabsContent value="orders">
          <DemoOrderPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ---------- Organizations ----------

function OrganizationsPanel() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['admin', 'orgs'],
    queryFn: () => api.get<Organization[]>('/admin/organizations'),
  })
  const [type, setType] = useState<'cleaning_center' | 'restaurant'>('cleaning_center')
  const [name, setName] = useState('')

  const create = useMutation({
    mutationFn: async () =>
      api.post<Organization>('/admin/organizations', { type, name: name.trim() }),
    onSuccess: () => {
      toast.success('組織已建立')
      setName('')
      void qc.invalidateQueries({ queryKey: ['admin', 'orgs'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> 建立新組織
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label>類型</Label>
            <div className="grid grid-cols-2 gap-2">
              {(['cleaning_center', 'restaurant'] as const).map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => setType(t)}
                  className={cn(
                    'rounded-md border px-3 py-2 text-sm',
                    type === t
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border hover:bg-muted',
                  )}
                >
                  {t === 'cleaning_center' ? '清洗中心' : '餐廳'}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>名稱</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={128} />
          </div>
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!name.trim()) return toast.error('請填名稱')
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立組織'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Building2 className="size-4" /> 既有組織
          </CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : list.isError ? (
            <p className="text-sm text-destructive">{formatApiError(list.error)}</p>
          ) : (list.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無組織</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.data!.map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant={o.type === 'cleaning_center' ? 'secondary' : 'success'}>
                      {o.type === 'cleaning_center' ? '清洗中心' : '餐廳'}
                    </Badge>
                    <span>{o.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CopyId id={o.id} />
                    <DeleteButton
                      confirm={`確定刪除組織「${o.name}」？已被人員或訂單引用會被擋下。`}
                      onDelete={() => api.delete<void>(`/admin/organizations/${o.id}`)}
                      onSuccess={() => qc.invalidateQueries({ queryKey: ['admin', 'orgs'] })}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- Users ----------

function UsersPanel() {
  const qc = useQueryClient()
  const orgs = useQuery({
    queryKey: ['admin', 'orgs'],
    queryFn: () => api.get<Organization[]>('/admin/organizations'),
  })
  const list = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => api.get<UserAccount[]>('/admin/users'),
  })

  const [role, setRole] = useState<UserRole>('courier')
  const [label, setLabel] = useState('')
  const [orgId, setOrgId] = useState<string>('')

  const needsOrg = role === 'cleaning_staff' || role === 'restaurant_staff'
  const filteredOrgs = useMemo(() => {
    if (role === 'cleaning_staff') return (orgs.data ?? []).filter((o) => o.type === 'cleaning_center')
    if (role === 'restaurant_staff') return (orgs.data ?? []).filter((o) => o.type === 'restaurant')
    return []
  }, [orgs.data, role])

  const orgIndex = useMemo(() => {
    const map = new Map<string, Organization>()
    for (const o of orgs.data ?? []) map.set(o.id, o)
    return map
  }, [orgs.data])

  const create = useMutation({
    mutationFn: async () =>
      api.post<UserAccount>('/admin/users', {
        role,
        label: label.trim(),
        organization_id: needsOrg ? orgId : null,
      }),
    onSuccess: () => {
      toast.success('人員已建立')
      setLabel('')
      void qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> 建立人員
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label>角色</Label>
            <div className="grid grid-cols-3 gap-2">
              {(['admin', 'courier', 'cleaning_staff', 'restaurant_staff', 'recycler', 'support'] as UserRole[]).map(
                (r) => (
                  <button
                    type="button"
                    key={r}
                    onClick={() => setRole(r)}
                    className={cn(
                      'rounded-md border px-2 py-1.5 text-xs',
                      role === r
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-muted',
                    )}
                  >
                    {r}
                  </button>
                ),
              )}
            </div>
          </div>
          <div className="space-y-2">
            <Label>顯示名稱</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={128} />
          </div>
          {needsOrg ? (
            <div className="space-y-2">
              <Label>所屬組織</Label>
              <select
                className="h-10 w-full rounded-md border border-border bg-bg px-3 text-sm"
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
              >
                <option value="">— 選擇 —</option>
                {filteredOrgs.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!label.trim()) return toast.error('請填名稱')
              if (needsOrg && !orgId) return toast.error('請選組織')
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立人員'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User2 className="size-4" /> 既有人員
          </CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <p className="text-sm text-muted-foreground">載入中…</p>
          ) : (list.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無人員</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.data!.map((u) => (
                <li key={u.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium">{u.label}</div>
                    <div className="text-xs text-muted-foreground">
                      <Badge variant="secondary">{u.role}</Badge>
                      {u.organization_id ? (
                        <span className="ml-2">
                          {orgIndex.get(u.organization_id)?.name ?? shortId(u.organization_id)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CopyId id={u.id} />
                    <DeleteButton
                      confirm={`刪除人員「${u.label}」？歷史事件會保留 actor_id（loose ref）。`}
                      onDelete={() => api.delete<void>(`/admin/users/${u.id}`)}
                      onSuccess={() => qc.invalidateQueries({ queryKey: ['admin', 'users'] })}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- Consumers ----------

function ConsumersPanel() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['admin', 'consumers'],
    queryFn: () => api.get<ConsumerAccount[]>('/admin/consumers'),
  })
  const [label, setLabel] = useState('')
  const create = useMutation({
    mutationFn: async () =>
      api.post<ConsumerAccount>('/admin/consumers', { label: label.trim() }),
    onSuccess: () => {
      toast.success('消費者已建立')
      setLabel('')
      void qc.invalidateQueries({ queryKey: ['admin', 'consumers'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> 建立消費者
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="顯示名稱（demo 用）"
            maxLength={128}
          />
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!label.trim()) return toast.error('請填名稱')
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User2 className="size-4" /> 既有消費者
          </CardTitle>
        </CardHeader>
        <CardContent>
          {(list.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無消費者</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.data!.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium">{c.label}</div>
                    <div className="text-xs text-muted-foreground">
                      錢包 {c.wallet_balance}・點 {c.points}・押金等級 L{c.deposit_level}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CopyId id={c.id} />
                    <DeleteButton
                      confirm={`刪除消費者「${c.label}」？有訂單 / 押金 / 持有資產會被擋下。`}
                      onDelete={() => api.delete<void>(`/admin/consumers/${c.id}`)}
                      onSuccess={() => qc.invalidateQueries({ queryKey: ['admin', 'consumers'] })}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- Return boxes ----------

function ReturnBoxesPanel() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['admin', 'return-boxes'],
    queryFn: () => api.get<ReturnBoxAccount[]>('/admin/return-boxes'),
  })
  const [label, setLabel] = useState('')
  const [createdKey, setCreatedKey] = useState<{ id: string; api_key: string } | null>(null)
  const create = useMutation({
    mutationFn: async () =>
      api.post<ReturnBoxAccount>('/admin/return-boxes', { label: label.trim() }),
    onSuccess: (data) => {
      toast.success('回收箱已建立，API key 一次性回傳')
      setCreatedKey({ id: data.id, api_key: data.api_key ?? '' })
      setLabel('')
      void qc.invalidateQueries({ queryKey: ['admin', 'return-boxes'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> 建立回收箱
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="標籤（例：捷運中山站 1F）"
            maxLength={128}
          />
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!label.trim()) return toast.error('請填標籤')
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立'}
          </Button>
          {createdKey ? (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs">
              <div className="mb-1 font-medium">請立即記錄 API key（僅顯示這次）</div>
              <code className="block break-all rounded bg-bg/60 px-2 py-1 font-mono">
                {createdKey.api_key}
              </code>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Inbox className="size-4" /> 既有回收箱
          </CardTitle>
        </CardHeader>
        <CardContent>
          {(list.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無回收箱</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.data!.map((b) => (
                <li key={b.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium flex items-center gap-2">
                      {b.label}
                      {!b.active ? <Badge variant="secondary">停用</Badge> : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      建立於 {formatDateTime(b.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CopyId id={b.id} />
                    {b.active ? (
                      <DeleteButton
                        label="停用"
                        confirm={`停用回收箱「${b.label}」？歷史 sensor_events 仍會保留。`}
                        onDelete={() => api.delete<{ active: boolean }>(`/admin/return-boxes/${b.id}`)}
                        onSuccess={() =>
                          qc.invalidateQueries({ queryKey: ['admin', 'return-boxes'] })
                        }
                      />
                    ) : (
                      <Badge variant="outline" className="gap-1 text-[10px]">
                        <PowerOff className="size-3" />
                        已停用
                      </Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- Partners ----------

function PartnersPanel() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['admin', 'partners'],
    queryFn: () => api.get<PartnerAccount[]>('/admin/partners'),
  })
  const [name, setName] = useState('')
  const [createdKey, setCreatedKey] = useState<{ id: string; api_key: string } | null>(null)
  const create = useMutation({
    mutationFn: async () => api.post<PartnerAccount>('/admin/partners', { name: name.trim() }),
    onSuccess: (data) => {
      toast.success('Partner 已建立，API key 一次性回傳')
      setCreatedKey({ id: data.id, api_key: data.api_key ?? '' })
      setName('')
      void qc.invalidateQueries({ queryKey: ['admin', 'partners'] })
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> 建立 Partner
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Partner 名稱（例：Demo 外送 Co.）"
            maxLength={128}
          />
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!name.trim()) return toast.error('請填名稱')
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立'}
          </Button>
          {createdKey ? (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs">
              <div className="mb-1 font-medium">API key（僅顯示這次）</div>
              <code className="block break-all rounded bg-bg/60 px-2 py-1 font-mono">
                {createdKey.api_key}
              </code>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="size-4" /> 既有 Partners
          </CardTitle>
        </CardHeader>
        <CardContent>
          {(list.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">尚無 Partner</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.data!.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <div>
                    <div className="font-medium flex items-center gap-2">
                      {p.name}
                      {!p.active ? <Badge variant="secondary">停用</Badge> : null}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {p.active ? '啟用中' : '停用'}・建立於 {formatDateTime(p.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CopyId id={p.id} />
                    {p.active ? (
                      <DeleteButton
                        label="停用"
                        confirm={`停用 Partner「${p.name}」？歷史訂單仍指向它。`}
                        onDelete={() => api.delete<{ active: boolean }>(`/admin/partners/${p.id}`)}
                        onSuccess={() => qc.invalidateQueries({ queryKey: ['admin', 'partners'] })}
                      />
                    ) : (
                      <Badge variant="outline" className="gap-1 text-[10px]">
                        <PowerOff className="size-3" />
                        已停用
                      </Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------- Demo orders ----------

function DemoOrderPanel() {
  const orgs = useQuery({
    queryKey: ['admin', 'orgs'],
    queryFn: () => api.get<Organization[]>('/admin/organizations'),
  })
  const partners = useQuery({
    queryKey: ['admin', 'partners'],
    queryFn: () => api.get<PartnerAccount[]>('/admin/partners'),
  })
  const couriers = useQuery({
    queryKey: ['admin', 'users', 'courier'],
    queryFn: () => api.get<UserAccount[]>('/admin/users', { query: { role: 'courier' } }),
  })
  const consumers = useQuery({
    queryKey: ['admin', 'consumers'],
    queryFn: () => api.get<ConsumerAccount[]>('/admin/consumers'),
  })
  const restaurants = useMemo(
    () => (orgs.data ?? []).filter((o) => o.type === 'restaurant'),
    [orgs.data],
  )

  const [partnerId, setPartnerId] = useState('')
  const [restaurantId, setRestaurantId] = useState('')
  const [courierId, setCourierId] = useState('')
  const [consumerId, setConsumerId] = useState('')
  const [mealBoxQty, setMealBoxQty] = useState(1)
  const [drinkCupQty, setDrinkCupQty] = useState(0)
  const [result, setResult] = useState<DemoOrderResult | null>(null)

  const create = useMutation({
    mutationFn: async () => {
      const manifest: Partial<Record<AssetType, number>> = {}
      if (mealBoxQty > 0) manifest.meal_box = mealBoxQty
      if (drinkCupQty > 0) manifest.drink_cup = drinkCupQty
      return api.post<DemoOrderResult>('/admin/demo-orders', {
        partner_id: partnerId,
        restaurant_id: restaurantId,
        courier_id: courierId,
        consumer_id: consumerId,
        expected_asset_manifest: manifest,
      })
    },
    onSuccess: (data) => {
      setResult(data)
      toast.success(`訂單建立成功，PIN ${data.delivery_pin}`)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  const recentOrders = useQuery({
    queryKey: ['admin', 'demo-orders', 'recent'],
    queryFn: () => api.get<CourierOrderItem[]>('/lists/courier/orders', { query: { courier_id: courierId } }),
    enabled: false,
  })

  return (
    <div className="grid gap-4 mt-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Truck className="size-4" /> 模擬 Partner 建單
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <PickRow
            label="Partner"
            value={partnerId}
            onChange={setPartnerId}
            options={(partners.data ?? []).map((p) => ({ id: p.id, name: p.name }))}
          />
          <PickRow
            label="餐廳"
            value={restaurantId}
            onChange={setRestaurantId}
            options={restaurants.map((r) => ({ id: r.id, name: r.name }))}
          />
          <PickRow
            label="外送員"
            value={courierId}
            onChange={setCourierId}
            options={(couriers.data ?? []).map((u) => ({ id: u.id, name: u.label }))}
          />
          <PickRow
            label="消費者"
            value={consumerId}
            onChange={setConsumerId}
            options={(consumers.data ?? []).map((c) => ({ id: c.id, name: c.label }))}
          />
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>餐盒數</Label>
              <Input
                type="number"
                min={0}
                max={20}
                value={mealBoxQty}
                onChange={(e) => setMealBoxQty(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label>飲料杯數</Label>
              <Input
                type="number"
                min={0}
                max={20}
                value={drinkCupQty}
                onChange={(e) => setDrinkCupQty(Number(e.target.value))}
              />
            </div>
          </div>
          <Button
            className="w-full"
            disabled={create.isPending}
            onClick={() => {
              if (!partnerId || !restaurantId || !courierId || !consumerId) {
                return toast.error('請選 Partner / 餐廳 / 外送員 / 消費者')
              }
              if (mealBoxQty + drinkCupQty === 0) {
                return toast.error('至少要 1 件餐盒或飲料杯')
              }
              create.mutate()
            }}
          >
            {create.isPending ? '建立中…' : '建立訂單並產生 PIN'}
          </Button>
          <Button
            variant="ghost"
            className="w-full"
            onClick={() => {
              if (!courierId) return toast.error('先選外送員')
              void recentOrders.refetch()
            }}
          >
            查詢該外送員既有訂單
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {result ? (
          <Card className="border-success/50">
            <CardHeader>
              <CardTitle className="text-base">訂單建立結果</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Order ID" value={result.order_id} mono />
              <Row label="External order id" value={result.external_order_id} mono />
              <Row label="Consumer" value={shortId(result.consumer_id)} mono />
              <Row label="PIN" value={result.delivery_pin} />
              <Row label="PIN 到期" value={formatDateTime(result.delivery_pin_expires_at)} />
              <p className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
                請把 PIN 提供給扮演消費者的人，外送員交付時要輸入。
              </p>
            </CardContent>
          </Card>
        ) : null}

        {recentOrders.data ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">該外送員的訂單</CardTitle>
            </CardHeader>
            <CardContent>
              {recentOrders.data.length === 0 ? (
                <p className="text-sm text-muted-foreground">尚無訂單</p>
              ) : (
                <ul className="divide-y divide-border rounded-md border border-border text-xs">
                  {recentOrders.data.map((o) => (
                    <li key={o.order_id} className="flex items-center justify-between px-3 py-2">
                      <span className="font-mono">{o.external_order_id}</span>
                      <Badge variant="secondary">{o.status}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  )
}

function PickRow({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { id: string; name: string }[]
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-md border border-border bg-bg px-3 text-sm"
      >
        <option value="">— 選擇 —</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
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

function CopyId({ id }: { id: string }) {
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(id).then(
          () => toast.success('ID 已複製'),
          () => toast.error('複製失敗'),
        )
      }}
      className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] hover:bg-muted"
    >
      <Copy className="size-3" />
      <span className="font-mono">{shortId(id)}</span>
    </button>
  )
}
