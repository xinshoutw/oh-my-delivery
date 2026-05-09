import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Menu } from 'lucide-react'
import { useState } from 'react'
import { useAuthStore } from '@/store/auth'
import { ROLE_REGISTRY } from '@/lib/role-meta'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn, shortId } from '@/lib/utils'

export function AppShell() {
  const auth = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  if (!auth.role || !auth.actorId) {
    navigate('/login', { replace: true })
    return null
  }

  const meta = ROLE_REGISTRY[auth.role]
  if (!meta) {
    navigate('/login', { replace: true })
    return null
  }

  const handleLogout = () => {
    auth.clear()
    navigate('/login', { replace: true })
  }

  const navItems = meta.routes

  return (
    <div className="flex min-h-dvh flex-col bg-bg text-fg md:flex-row">
      <aside className="hidden border-r border-border md:flex md:w-64 md:flex-col safe-top">
        <div className="flex h-16 items-center px-5">
          <span className="text-lg font-semibold tracking-tight">oh-my-delivery</span>
        </div>
        <nav className="flex-1 space-y-1 px-3 pb-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === meta.homePath}
              className={({ isActive }) =>
                cn(
                  'block rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-muted font-medium text-fg'
                    : 'text-muted-foreground hover:bg-muted/60 hover:text-fg',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-4 text-xs text-muted-foreground">
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-col">
              <span className="text-fg font-medium">{auth.label ?? meta.label}</span>
              <span className="text-[11px]">{meta.label}</span>
              {auth.organizationName ? (
                <span className="text-[11px]">{auth.organizationName}</span>
              ) : auth.organizationId ? (
                <span className="font-mono text-[10px]">org {shortId(auth.organizationId)}</span>
              ) : null}
            </div>
            <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="登出">
              <LogOut />
            </Button>
          </div>
        </div>
      </aside>

      <header className="flex h-14 items-center justify-between border-b border-border px-4 md:hidden safe-top">
        <button
          type="button"
          className="flex h-10 w-10 items-center justify-center rounded-md hover:bg-muted"
          onClick={() => setMobileNavOpen((v) => !v)}
          aria-label="切換選單"
        >
          <Menu className="size-5" />
        </button>
        <div className="flex flex-col items-end">
          <span className="text-sm font-semibold">oh-my-delivery</span>
          <Badge variant="secondary" className="mt-0.5 text-[10px]">
            {meta.label}
          </Badge>
        </div>
      </header>
      {mobileNavOpen ? (
        <div className="border-b border-border bg-bg p-3 md:hidden">
          <div className="grid grid-cols-2 gap-2">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === meta.homePath}
                onClick={() => setMobileNavOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'rounded-md border border-border px-3 py-2 text-sm text-center transition-colors',
                    isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-muted',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
            <Button
              variant="outline"
              className="col-span-2"
              onClick={() => {
                setMobileNavOpen(false)
                handleLogout()
              }}
            >
              <LogOut className="size-4" />
              登出
            </Button>
          </div>
        </div>
      ) : null}

      <main className="flex-1 safe-x">
        <div className="mx-auto w-full max-w-5xl px-4 py-5 pb-24 md:py-8 md:pb-12">
          <Outlet key={location.pathname} />
        </div>
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-bg/95 backdrop-blur md:hidden safe-bottom">
        <div className="mx-auto flex max-w-3xl items-center justify-around px-2 py-2 text-xs">
          {navItems.slice(0, 5).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === meta.homePath}
              className={({ isActive }) =>
                cn(
                  'flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-md px-1 py-1 text-center transition-colors',
                  isActive ? 'text-fg font-medium' : 'text-muted-foreground hover:text-fg',
                )
              }
            >
              <span className="truncate text-[11px]">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
