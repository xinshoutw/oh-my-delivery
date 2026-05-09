import type { ActorRole } from '@/types/api'

export interface RoleMeta {
  role: ActorRole
  label: string
  description: string
  homePath: string
  needsOrganization: boolean
  routes: { path: string; label: string }[]
}

export const ROLE_REGISTRY: Record<string, RoleMeta> = {
  consumer: {
    role: 'consumer',
    label: '消費者',
    description: '掃描歸還、查持有資產與點數',
    homePath: '/consumer',
    needsOrganization: false,
    routes: [
      { path: '/consumer', label: '我的持有' },
      { path: '/consumer/return', label: '掃描歸還' },
    ],
  },
  courier: {
    role: 'courier',
    label: '外送員',
    description: '取餐掃描 / PIN 交付',
    homePath: '/courier',
    needsOrganization: false,
    routes: [
      { path: '/courier', label: '取餐 session' },
      { path: '/courier/deliver', label: '交付訂單' },
    ],
  },
  restaurant: {
    role: 'restaurant',
    label: '餐廳',
    description: '一鍵確認收貨',
    homePath: '/restaurant',
    needsOrganization: true,
    routes: [{ path: '/restaurant', label: '收貨確認' }],
  },
  cleaning_center: {
    role: 'cleaning_center',
    label: '清洗中心',
    description: '建立資產、收貨、檢查、清洗、出貨',
    homePath: '/cleaning',
    needsOrganization: true,
    routes: [
      { path: '/cleaning', label: '總覽' },
      { path: '/cleaning/assets', label: '建立資產' },
      { path: '/cleaning/receive', label: '收貨' },
      { path: '/cleaning/inspection', label: '檢查' },
      { path: '/cleaning/washing', label: '完成清洗' },
      { path: '/cleaning/dispatch', label: '出貨' },
    ],
  },
  admin: {
    role: 'admin',
    label: '系統管理員',
    description: 'Onboarding、儀表板、通知派送、Hash chain anchor',
    homePath: '/admin',
    needsOrganization: false,
    routes: [
      { path: '/admin', label: '儀表板' },
      { path: '/admin/onboarding', label: 'Onboarding' },
      { path: '/admin/notifications', label: '通知派送' },
      { path: '/admin/anchors', label: 'Chain Anchor' },
    ],
  },
}

export const SUPPORTED_ROLES: ActorRole[] = [
  'consumer',
  'courier',
  'restaurant',
  'cleaning_center',
  'admin',
]
