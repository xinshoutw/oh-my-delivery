import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Login } from '@/routes/Login'
import { ConsumerHome } from '@/routes/consumer/Home'
import { ConsumerReturn } from '@/routes/consumer/Return'
import { CourierSession } from '@/routes/courier/Session'
import { CourierDeliver } from '@/routes/courier/Deliver'
import { RestaurantAck } from '@/routes/restaurant/Ack'
import { CleaningHome } from '@/routes/cleaning/Home'
import { CleaningCreateAssets } from '@/routes/cleaning/CreateAssets'
import { CleaningReceive } from '@/routes/cleaning/Receive'
import { CleaningInspect } from '@/routes/cleaning/Inspect'
import { CleaningWashing } from '@/routes/cleaning/Washing'
import { CleaningDispatch } from '@/routes/cleaning/Dispatch'
import { AdminDashboard } from '@/routes/admin/Dashboard'
import { AdminNotifications } from '@/routes/admin/Notifications'
import { AdminAnchors } from '@/routes/admin/Anchors'
import { AdminOnboarding } from '@/routes/admin/Onboarding'
import { useAuthStore } from '@/store/auth'

function RootRedirect() {
  const auth = useAuthStore()
  if (!auth.role) return <Navigate to="/login" replace />
  switch (auth.role) {
    case 'consumer':
      return <Navigate to="/consumer" replace />
    case 'courier':
      return <Navigate to="/courier" replace />
    case 'restaurant':
      return <Navigate to="/restaurant" replace />
    case 'cleaning_center':
      return <Navigate to="/cleaning" replace />
    case 'admin':
      return <Navigate to="/admin" replace />
    default:
      return <Navigate to="/login" replace />
  }
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<RootRedirect />} />
      <Route element={<AppShell />}>
        <Route path="/consumer" element={<ConsumerHome />} />
        <Route path="/consumer/return" element={<ConsumerReturn />} />

        <Route path="/courier" element={<CourierSession />} />
        <Route path="/courier/deliver" element={<CourierDeliver />} />

        <Route path="/restaurant" element={<RestaurantAck />} />

        <Route path="/cleaning" element={<CleaningHome />} />
        <Route path="/cleaning/assets" element={<CleaningCreateAssets />} />
        <Route path="/cleaning/receive" element={<CleaningReceive />} />
        <Route path="/cleaning/inspection" element={<CleaningInspect />} />
        <Route path="/cleaning/washing" element={<CleaningWashing />} />
        <Route path="/cleaning/dispatch" element={<CleaningDispatch />} />

        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/onboarding" element={<AdminOnboarding />} />
        <Route path="/admin/notifications" element={<AdminNotifications />} />
        <Route path="/admin/anchors" element={<AdminAnchors />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
