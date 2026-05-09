import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ActorRole } from '@/types/api'

export interface AuthState {
  role: ActorRole | null
  actorId: string | null
  organizationId: string | null
  label: string | null
  organizationName: string | null
  partnerApiKey: string | null
  deviceKey: string | null
  setSession: (next: {
    role: ActorRole
    actorId: string
    organizationId?: string | null
    label?: string | null
    organizationName?: string | null
    partnerApiKey?: string | null
    deviceKey?: string | null
  }) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      role: null,
      actorId: null,
      organizationId: null,
      label: null,
      organizationName: null,
      partnerApiKey: null,
      deviceKey: null,
      setSession: ({
        role,
        actorId,
        organizationId,
        label,
        organizationName,
        partnerApiKey,
        deviceKey,
      }) =>
        set({
          role,
          actorId,
          organizationId: organizationId ?? null,
          label: label ?? null,
          organizationName: organizationName ?? null,
          partnerApiKey: partnerApiKey ?? null,
          deviceKey: deviceKey ?? null,
        }),
      clear: () =>
        set({
          role: null,
          actorId: null,
          organizationId: null,
          label: null,
          organizationName: null,
          partnerApiKey: null,
          deviceKey: null,
        }),
    }),
    {
      name: 'omd-auth',
    },
  ),
)
