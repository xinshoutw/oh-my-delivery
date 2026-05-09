import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, ChevronRight, Settings } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuthStore } from '@/store/auth'
import { bootstrapApi, formatApiError } from '@/lib/api'
import { ROLE_REGISTRY, SUPPORTED_ROLES } from '@/lib/role-meta'
import type {
  ActorRole,
  ConsumerAccount,
  Organization,
  UserAccount,
  UserRole,
} from '@/types/api'
import { cn, shortId } from '@/lib/utils'

type RoleTab = 'consumer' | 'courier' | 'restaurant' | 'cleaning_center' | 'admin'

const TAB_TO_USER_ROLE: Record<Exclude<RoleTab, 'consumer'>, UserRole> = {
  admin: 'admin',
  courier: 'courier',
  restaurant: 'restaurant_staff',
  cleaning_center: 'cleaning_staff',
}

const TAB_TO_BACKEND_ROLE: Record<RoleTab, ActorRole> = {
  consumer: 'consumer',
  admin: 'admin',
  courier: 'courier',
  restaurant: 'restaurant',
  cleaning_center: 'cleaning_center',
}

export function Login() {
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)
  const [tab, setTab] = useState<RoleTab>('consumer')

  const meta = ROLE_REGISTRY[tab]

  const onLoginAsUser = (user: UserAccount, orgName?: string) => {
    setSession({
      role: TAB_TO_BACKEND_ROLE[tab],
      actorId: user.id,
      organizationId: user.organization_id ?? null,
      label: user.label,
      organizationName: orgName ?? null,
    })
    toast.success(`已登入：${user.label}`)
    navigate(meta.homePath, { replace: true })
  }

  const onLoginAsConsumer = (consumer: ConsumerAccount) => {
    setSession({
      role: 'consumer',
      actorId: consumer.id,
      label: consumer.label,
    })
    toast.success(`已登入：${consumer.label}`)
    navigate(ROLE_REGISTRY.consumer.homePath, { replace: true })
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-muted/40 px-4 py-8 safe-top safe-bottom safe-x">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>oh-my-delivery</CardTitle>
          <CardDescription>
            選擇身分後從清單挑一個 demo 帳號登入。沒有帳號？直接點「建立新帳號」即可。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Tabs value={tab} onValueChange={(v) => setTab(v as RoleTab)}>
            <TabsList className="grid w-full grid-cols-5 gap-0">
              {SUPPORTED_ROLES.map((r) => (
                <TabsTrigger key={r} value={r} className="text-xs sm:text-sm">
                  {ROLE_REGISTRY[r].label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>

          <p className="text-sm text-muted-foreground">{meta.description}</p>

          {tab === 'consumer' ? (
            <ConsumerPicker onPick={onLoginAsConsumer} />
          ) : (
            <UserPicker tab={tab} onPick={onLoginAsUser} />
          )}
        </CardContent>
      </Card>

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Bootstrap admin id（自動產生）：
        <span className="ml-1 font-mono">{shortId(bootstrapApi.adminId(), 12)}</span>
      </p>
    </div>
  )
}

// --- Consumer picker --------------------------------------------------------

function ConsumerPicker({ onPick }: { onPick: (c: ConsumerAccount) => void }) {
  const [creating, setCreating] = useState(false)
  const list = useQuery({
    queryKey: ['login', 'consumers'],
    queryFn: () => bootstrapApi.get<ConsumerAccount[]>('/admin/consumers'),
  })

  return (
    <div className="space-y-3">
      {list.isLoading ? (
        <p className="text-sm text-muted-foreground">載入消費者…</p>
      ) : list.isError ? (
        <p className="text-sm text-destructive">{formatApiError(list.error)}</p>
      ) : (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {(list.data ?? []).map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onPick(c)}
                className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
              >
                <div>
                  <div className="font-medium">{c.label}</div>
                  <div className="text-xs text-muted-foreground">
                    錢包 {c.wallet_balance}・點數 {c.points}・押金等級 L{c.deposit_level}
                  </div>
                </div>
                <ChevronRight className="size-4 text-muted-foreground" />
              </button>
            </li>
          ))}
          {(list.data ?? []).length === 0 ? (
            <li className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              尚無消費者，請建立一個
            </li>
          ) : null}
        </ul>
      )}

      {creating ? (
        <ConsumerCreateForm
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false)
            void list.refetch()
          }}
        />
      ) : (
        <Button variant="outline" className="w-full" onClick={() => setCreating(true)}>
          <Plus className="size-4" />
          建立新消費者
        </Button>
      )}
    </div>
  )
}

function ConsumerCreateForm({
  onCancel,
  onCreated,
}: {
  onCancel: () => void
  onCreated: (c: ConsumerAccount) => void
}) {
  const [label, setLabel] = useState('')

  const create = useMutation({
    mutationFn: async () =>
      bootstrapApi.post<ConsumerAccount>('/admin/consumers', { label: label.trim() }),
    onSuccess: (data) => {
      toast.success('消費者已建立')
      onCreated(data)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!label.trim()) return toast.error('請填顯示名稱')
        create.mutate()
      }}
      className="space-y-3 rounded-md border border-border p-3"
    >
      <Label>顯示名稱（demo 用，例：「示範用戶 A」）</Label>
      <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={128} />
      <div className="flex gap-2">
        <Button type="button" variant="ghost" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" className="flex-1" disabled={create.isPending}>
          {create.isPending ? '建立中…' : '建立並登入'}
        </Button>
      </div>
    </form>
  )
}

// --- User picker (admin / courier / restaurant_staff / cleaning_staff) -----

function UserPicker({
  tab,
  onPick,
}: {
  tab: Exclude<RoleTab, 'consumer'>
  onPick: (u: UserAccount, orgName?: string) => void
}) {
  const userRole = TAB_TO_USER_ROLE[tab]
  const [creating, setCreating] = useState(false)

  const orgs = useQuery({
    queryKey: ['login', 'orgs'],
    queryFn: () => bootstrapApi.get<Organization[]>('/admin/organizations'),
  })

  const users = useQuery({
    queryKey: ['login', 'users', userRole],
    queryFn: () => bootstrapApi.get<UserAccount[]>('/admin/users', { role: userRole }),
  })

  const orgIndex = useMemo(() => {
    const map = new Map<string, Organization>()
    for (const o of orgs.data ?? []) map.set(o.id, o)
    return map
  }, [orgs.data])

  return (
    <div className="space-y-3">
      {users.isLoading ? (
        <p className="text-sm text-muted-foreground">載入帳號…</p>
      ) : users.isError ? (
        <p className="text-sm text-destructive">{formatApiError(users.error)}</p>
      ) : (
        <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
          {(users.data ?? []).map((u) => {
            const org = u.organization_id ? orgIndex.get(u.organization_id) : null
            return (
              <li key={u.id}>
                <button
                  type="button"
                  onClick={() => onPick(u, org?.name)}
                  className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                >
                  <div>
                    <div className="font-medium">{u.label}</div>
                    <div className="text-xs text-muted-foreground">
                      {org ? `${org.name}` : '—'}・<span className="font-mono">{shortId(u.id)}</span>
                    </div>
                  </div>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </button>
              </li>
            )
          })}
          {(users.data ?? []).length === 0 ? (
            <li className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              尚無此身分的帳號，請建立一個
            </li>
          ) : null}
        </ul>
      )}

      {creating ? (
        <UserCreateForm
          tab={tab}
          orgs={orgs.data ?? []}
          onCancel={() => setCreating(false)}
          onCreated={() => {
            setCreating(false)
            void users.refetch()
            void orgs.refetch()
          }}
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="flex-1" onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            建立新帳號
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              void users.refetch()
              void orgs.refetch()
            }}
            aria-label="重新整理"
          >
            <Settings className="size-4" />
          </Button>
        </div>
      )}

      {tab === 'admin' ? (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          初次使用：請先建立一個 admin 帳號，再切到其他身分建立組織與成員。也可以直接用「Bootstrap admin」（顯示在登入畫面下方那串）跑 onboarding。
        </p>
      ) : null}
    </div>
  )
}

function UserCreateForm({
  tab,
  orgs,
  onCancel,
  onCreated,
}: {
  tab: Exclude<RoleTab, 'consumer'>
  orgs: Organization[]
  onCancel: () => void
  onCreated: (u: UserAccount) => void
}) {
  const userRole = TAB_TO_USER_ROLE[tab]
  const orgType = tab === 'cleaning_center' ? 'cleaning_center' : tab === 'restaurant' ? 'restaurant' : null
  const filteredOrgs = useMemo(
    () => (orgType ? orgs.filter((o) => o.type === orgType) : []),
    [orgs, orgType],
  )
  const [label, setLabel] = useState('')
  const [orgId, setOrgId] = useState<string>(filteredOrgs[0]?.id ?? '')

  const needsOrg = orgType !== null

  useEffect(() => {
    if (needsOrg && filteredOrgs.length > 0 && !orgId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setOrgId(filteredOrgs[0].id)
    }
  }, [needsOrg, filteredOrgs, orgId])

  const create = useMutation({
    mutationFn: async () =>
      bootstrapApi.post<UserAccount>('/admin/users', {
        role: userRole,
        label: label.trim(),
        organization_id: needsOrg ? orgId : null,
      }),
    onSuccess: (data) => {
      toast.success(`帳號 ${data.label} 已建立`)
      onCreated(data)
    },
    onError: (err) => toast.error(formatApiError(err)),
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (!label.trim()) return toast.error('請填顯示名稱')
        if (needsOrg && !orgId) return toast.error('請先建立或選擇組織')
        create.mutate()
      }}
      className="space-y-3 rounded-md border border-border p-3"
    >
      <div className="space-y-2">
        <Label>顯示名稱</Label>
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="例：清洗中心員工 A / 外送員小李"
          maxLength={128}
        />
      </div>

      {needsOrg ? (
        <div className="space-y-2">
          <Label>所屬組織（{orgType === 'cleaning_center' ? '清洗中心' : '餐廳'}）</Label>
          {filteredOrgs.length === 0 ? (
            <OrgInlineCreate type={orgType!} onCreated={(o) => setOrgId(o.id)} />
          ) : (
            <div className="grid gap-2">
              {filteredOrgs.map((o) => (
                <button
                  type="button"
                  key={o.id}
                  onClick={() => setOrgId(o.id)}
                  className={cn(
                    'flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors',
                    orgId === o.id
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border hover:bg-muted',
                  )}
                >
                  <span>{o.name}</span>
                  {orgId === o.id ? <Badge variant="secondary">已選</Badge> : null}
                </button>
              ))}
              <OrgInlineCreate type={orgType!} onCreated={(o) => setOrgId(o.id)} compact />
            </div>
          )}
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button type="button" variant="ghost" className="flex-1" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" className="flex-1" disabled={create.isPending}>
          {create.isPending ? '建立中…' : '建立並登入'}
        </Button>
      </div>
    </form>
  )
}

function OrgInlineCreate({
  type,
  onCreated,
  compact,
}: {
  type: 'cleaning_center' | 'restaurant'
  onCreated: (o: Organization) => void
  compact?: boolean
}) {
  const [name, setName] = useState('')
  const create = useMutation({
    mutationFn: async () =>
      bootstrapApi.post<Organization>('/admin/organizations', { type, name: name.trim() }),
    onSuccess: (data) => {
      toast.success('組織已建立')
      onCreated(data)
      setName('')
    },
    onError: (err) => toast.error(formatApiError(err)),
  })
  return (
    <div className={cn('flex items-center gap-2', compact ? 'pt-1' : '')}>
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={type === 'cleaning_center' ? '新清洗中心名稱' : '新餐廳名稱'}
      />
      <Button
        type="button"
        size="sm"
        onClick={() => {
          if (!name.trim()) return toast.error('請填名稱')
          create.mutate()
        }}
        disabled={create.isPending}
      >
        {create.isPending ? '…' : '建立'}
      </Button>
    </div>
  )
}
