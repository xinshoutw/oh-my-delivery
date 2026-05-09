import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import type { ActorRole } from '@/types/api'

interface Props {
  role: ActorRole
  children: ReactNode
}

export function RequireAuth({ role, children }: Props) {
  const auth = useAuthStore()
  if (!auth.role || !auth.actorId) {
    return <Navigate to="/login" replace />
  }
  if (auth.role !== role && auth.role !== 'admin') {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
