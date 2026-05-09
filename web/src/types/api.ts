export type AssetType = 'meal_box' | 'drink_cup'

export type ActorRole =
  | 'admin'
  | 'cleaning_center'
  | 'restaurant'
  | 'courier'
  | 'consumer'
  | 'recycler'
  | 'partner'
  | 'support'
  | 'system'

export type AssetStatus =
  | 'manufactured'
  | 'at_cleaning_center'
  | 'washing'
  | 'cleaned_ready'
  | 'in_transit_to_restaurant'
  | 'at_restaurant'
  | 'picked_by_courier'
  | 'with_consumer'
  | 'return_pending_deposit'
  | 'deposited_in_return_box'
  | 'collected_by_recycling_unit'
  | 'returned_to_cleaning_center'
  | 'under_inspection'
  | 'damaged'
  | 'lost'
  | 'retired'
  | 'under_dispute'

export type DispatchStatus = 'pending' | 'acknowledged' | 'cancelled'

export type OrderStatus = 'created' | 'picked_up' | 'delivered' | 'cancelled' | 'pin_locked'

export type OrganizationType = 'cleaning_center' | 'restaurant'

export type UserRole =
  | 'admin'
  | 'cleaning_staff'
  | 'restaurant_staff'
  | 'courier'
  | 'recycler'
  | 'support'

export interface Organization {
  id: string
  type: OrganizationType
  name: string
  created_at: string
}

export interface UserAccount {
  id: string
  role: UserRole
  label: string
  organization_id: string | null
  created_at: string
}

export interface ConsumerAccount {
  id: string
  label: string
  email: string | null
  phone: string | null
  wallet_balance: number
  points: number
  deposit_level: number
}

export interface PartnerAccount {
  id: string
  name: string
  active: boolean
  created_at: string
  api_key?: string
}

export interface ReturnBoxAccount {
  id: string
  label: string
  active: boolean
  created_at: string
  api_key?: string
}

export interface HoldingItem {
  asset_id: string
  asset_type: AssetType
  short_code: string
  status: AssetStatus
  deposit_id: string | null
  deposit_amount: number | null
  deposit_status: string | null
  borrowed_at: string | null
  due_at: string | null
  reward_cutoff_at: string | null
}

export interface CourierOrderItem {
  order_id: string
  external_order_id: string
  status: OrderStatus
  restaurant_id: string
  consumer_id: string
  expected_asset_manifest: Partial<Record<AssetType, number>>
  created_at: string
}

export interface RestaurantDispatchItem {
  dispatch_id: string
  cleaning_center_id: string
  status: DispatchStatus
  asset_count: number
  note: string | null
  created_at: string
  acknowledged_at: string | null
}

export interface RestaurantInventoryItem {
  asset_id: string
  asset_type: AssetType
  short_code: string
  status: AssetStatus
  usage_count: number
}

export interface CleaningAssetItem {
  asset_id: string
  asset_type: AssetType
  short_code: string
  status: AssetStatus
  physical_holder_type: string | null
  usage_count: number
  last_washed_at: string | null
}

export interface AssetLookup {
  asset_id: string
  asset_type: AssetType
  short_code: string
  status: AssetStatus
}

export interface DemoOrderResult {
  order_id: string
  external_order_id: string
  consumer_id: string
  delivery_pin: string
  delivery_pin_expires_at: string
  expected_asset_manifest: Partial<Record<AssetType, number>>
}

export interface AssetCreated {
  id: string
  asset_type: AssetType
  short_code: string
  asset_token: string
  status: AssetStatus
}

export interface ProgressEntry {
  expected: number
  scanned: number
}

export interface PickupSession {
  pickup_session_id: string
  order_id: string
  expected_manifest: Partial<Record<AssetType, number>>
  expires_in_seconds: number
  expires_at: string
  status: string
}

export interface ScanResult {
  accepted: boolean
  already_scanned: boolean
  asset_id: string | null
  asset_type: AssetType | null
  asset_public_code: string | null
  reject_reason: string | null
  progress: Partial<Record<AssetType, ProgressEntry>>
  fully_scanned: boolean
}

export interface ConfirmedAsset {
  asset_id: string
  asset_type: AssetType
  public_code: string
}

export interface ConfirmPickupResponse {
  pickup_session_id: string
  order_id: string
  transferred_assets: ConfirmedAsset[]
  order_status: string
}

export interface DeliveredAsset {
  asset_id: string
  asset_type: AssetType
  deposit_id: string
  deposit_amount: number
  due_at: string
  reward_cutoff_at: string
}

export interface DeliverSuccess {
  status: 'delivered'
  order_id: string
  consumer_id: string
  delivered_assets: DeliveredAsset[]
  consumer_wallet_balance_after: number
}

export interface DeliverFailure {
  status: string
  order_id: string
  remaining_attempts: number
  support_required: boolean
  reason: string
}

export interface ReturnScanResponse {
  return_session_id: string
  asset_id: string
  asset_type: AssetType
  asset_public_code: string
  is_current_holder: boolean
  status: string
  expires_in_seconds: number
  expires_at: string
  message: string
}

export interface ReceivedAsset {
  asset_id: string
  asset_type: string
  deposit_outcome: string
  reward_granted: boolean
  reward_points: number
}

export interface DispatchSummary {
  id: string
  cleaning_center_id: string
  restaurant_id: string
  status: DispatchStatus
  asset_ids: string[]
  note: string | null
  created_at: string
  acknowledged_at: string | null
}

export interface DashboardSummary {
  total_assets: number
  assets_by_status: Record<string, number>
  active_deposits: number
  released_deposits: number
  charged_deposits: number
  total_consumers: number
  total_points_granted: number
  total_orders: number
  orders_by_status: Record<string, number>
  completed_cycles: number
  active_cycles: number
  avg_wallet_balance: number
}

export interface ApiError {
  detail?: string | Array<{ loc: string[]; msg: string; type: string }>
  message?: string
}
