# oh-my-delivery — 循環餐具責任權管理系統

> 本檔是專案的單一事實來源（single source of truth）。任何後續 agent / 開發者進場時，請先讀這份 CLAUDE.md，再閱讀程式碼。
> 本系統為 2026 技職杯黑客松 MAKERTHON 題目實作。

---

## 0. 一句話描述

> 一套以 Python 後端實作的**低摩擦循環餐具責任權管理平台**。透過餐盒與飲料杯上的 QR token 進行逐件掃描，結合外送訂單預期餐具數量、取餐掃描 session、PIN 交付、消費者自助歸還、微動開關投入偵測、清洗中心最終確認、押金與獎勵制度，以及 per-asset hash chain 事件紀錄，建立可追蹤、可稽核、可未來上鏈的循環餐具系統。

---

## 1. 技術棧（已決議）

| 項目 | 選擇 |
|---|---|
| 語言 | Python 3.13+ |
| 套件管理 | **uv**（必用 `uv add` 加依賴，不要直接編輯 pyproject.toml） |
| 框架 | FastAPI |
| 資料庫 | PostgreSQL 16（透過 docker-compose 啟動） |
| ORM | SQLModel（= SQLAlchemy + Pydantic） |
| Migration | Alembic |
| 排程 | APScheduler（同進程，不引入 Celery / Redis） |
| Auth | JWT (使用者) + API key (Partner / Device) |
| 容器 | docker-compose（pg + app） |
| Demo 前端 | **本輪不實作前端**，只做後端 + OpenAPI Swagger UI（`/docs`） |

### uv 操作規範
```bash
uv sync                        # 安裝鎖定依賴
uv add fastapi                 # 加 runtime 依賴
uv add --dev pytest            # 加 dev 依賴
uv run pytest                  # 執行命令
uv run alembic upgrade head    # 跑 migration
uv run uvicorn app.main:app --reload
```
**禁止**：手寫 `pip install`、手動編輯 `pyproject.toml` 的 dependencies 區塊（用 `uv add`）。

---

## 2. 已確認的架構決策（DECISIONS）

以下是與業主對齊後的決策，**程式必須遵守**。任何違反必須先發 issue 討論。

### D1. token / short_code 安全
- `asset_token`：16 字元 Crockford Base32 隨機 token，前綴 `R1A.`，例：`R1A.B7K3M9Q2X8P4ZD6A`
- `token_hash`：**HMAC-SHA256(token, SERVER_SECRET)**，DB 只存 hash，不存 plaintext
- `short_code`：**獨立隨機產生** 8 字元 Base32（**不**從 token 派生），DB 存 `short_code`（plain，唯一索引）+ `short_code_hash`
- QR-Code 印 token + short_code（人工備援）
- short_code 操作有額外限制（角色 + 狀態 + rate limit）

### D2. State Machine 單一事實來源
- asset.status 僅在 session **confirm** 後才轉移。
- **去除** `pickup_scanning`、`delivery_pin_pending` 兩個中間態 — 由 session 自己的 status 表達。
- 合法狀態（asset.status）：`manufactured`、`at_cleaning_center`、`washing`、`cleaned_ready`、`in_transit_to_restaurant`、`at_restaurant`、`picked_by_courier`、`with_consumer`、`return_pending_deposit`、`deposited_in_return_box`、`collected_by_recycling_unit`、`returned_to_cleaning_center`、`under_inspection`、`damaged`、`lost`、`retired`、`under_dispute`

### D3. Consumer 對應（Partner 整合）
- Partner 建立訂單時帶 `external_consumer_ref`（Partner 自己的 user id）
- 系統用 `partner_consumers(partner_id, external_ref) → consumer_id` 對應表，first-seen 自動 upsert
- Partner 可選擇性帶 `national_id_hash` 做帳號合併（HMAC-SHA256(身分證, SERVER_SECRET)）
- **絕對不存身分證明文**

### D4. Hash Chain 結構
- **Per-asset chain**：每個 asset 一條獨立鏈
- `previous_event_hash` = 該 asset 上一筆 event 的 `event_hash`
- `event_hash = SHA256(canonical_event_json + previous_event_hash)`
- canonical event **不含**任何個資（無 email / 電話 / 身分證 / 明文 user_id / 訂單詳細）
- 每日跑 cron，把當日所有 event_hash 算 Merkle root 寫到 `chain_anchors` 表，為未來 blockchain anchor 預留接口

### D5. 押金累進規則（虛擬錢包）
- **不接真實金流**，consumer 有 `wallet_balance` 欄位
- 基礎押金：200，每次逾期下次 +100，**上限 500**，90 天無逾期 reset 為 200
- `deposit_level` 0/1/2/3 對應 200/300/400/500
- 逾期扣款 = 從 wallet_balance 扣（即使餘額為負也記錄）
- 借出時 `wallet_balance` 減押金（凍結），歸還且確認後加回

### D6. 獎勵
- 條件：14 天內歸還 **且** 清洗中心確認收到（依清洗中心確認時間判定，**不**依消費者掃描時間）
- 單位：**5 points / 次**，存 `consumer.points` 累積
- 防重複：`reward_transactions` 加 `UNIQUE(asset_id, cycle_id, reason)`

### D7. PIN 機制
- 訂單建立時系統產 6 位數字 PIN，**只存 `pin_hash`（SHA256）+ expires_at**
- PIN 隨 `POST /partner/orders` response 回傳給 Partner，由 Partner 顯示給消費者
- 失敗 5 次 / 訂單 → `order.status = pin_locked`，需客服解鎖
- 10 分鐘 cooldown（兩次失敗間最少間隔不強制，但連續 5 次後鎖定）
- 所有嘗試（成功/失敗）都寫 `delivery_pin_attempts`（attempted_pin_hash + server_timestamp）
- 成功後 PIN hash 從 order 清除（避免重放）

### D8. Cycle 編號
- `cycle_number` 從 **1** 開始
- `manufactured → 首次 cleaned_ready` 為**初始化**，不算 cycle
- Cycle 1 起點：首次從 cleaned_ready 出庫（`AssetDispatchedToRestaurant` 事件）
- Cycle 結束：再次回到 cleaned_ready（`AssetMarkedReady` 事件）

### D9. 餐廳收貨
- 餐廳 App 一鍵「確認收貨」（**批次 ack**，不逐件掃）
- API：`POST /restaurant/dispatches/{dispatch_id}/acknowledge`
- 一次性把 dispatch 內所有 asset 從 `in_transit_to_restaurant` → `at_restaurant`
- 以 dispatch 為單位記入 audit

### D10. 取餐流程（外送員逐件掃）
- `pickup_scan_sessions` 管理一次取餐
- 掃描階段不轉移 asset（保持 `at_restaurant`），只在 session items 暫存
- `confirm` 時一次性轉移所有掃描 asset → `picked_by_courier`
- session expire 60 秒（可調），失效後 items 廢棄
- 同 session 重複掃同 token：回應 already_scanned，不報錯
- 掃到不屬於該餐廳 / 類型不符 / 超過 expected manifest：回應 reject + reason

### D11. 歸還流程（消費者自助）
- `return_sessions` 管理一次掃描+投入
- 消費者掃描 → 顯示 short_code 確認 → 投入回收箱 → 微動開關事件
- 不揭示「目前持有人是誰」，只回 `is_current_holder: bool`
- 微動開關事件 → 系統嘗試匹配同 return_box 60 秒內的 active session
- 匹配成功 → asset.status = `deposited_in_return_box`
- **押金與獎勵不在此時觸發**，等清洗中心確認

### D12. 清洗中心最終確認
- 唯一可信的「歸還完成」事實來源
- 清洗中心掃描 → `returned_to_cleaning_center` → 觸發：
  - 押金釋放（若 `cleaning_confirmed_at <= due_at`）或扣款（若超期）
  - 獎勵發放（若 `cleaning_confirmed_at - borrowed_at <= 14 days`）
  - 押金等級調整（逾期 → +1，最多 4 級；90 天無逾期 reset）

### D13. Worker / 外部服務（Demo 範圍）
- **APScheduler**：押金到期檢查、通知排程觸發、session 過期清理、daily hash chain anchor
- **通知**：只寫入 `notifications` 表 + log，**不**實際寄 email/SMS
- **微動開關**：HTTP API + Device API key（header `X-Device-Key`），無真實硬體
- **Blockchain anchor**：寫入本地 `chain_anchors` 表（daily Merkle root），不上鏈

### D14. 小零件（筷子/叉子/湯匙/蓋子）
- **不**作為主資產追蹤
- 清洗中心檢查時記錄 `washing_batch_items.component_status` JSONB（`{"lid":"ok","chopsticks":"missing",...}`）
- 用於營運統計 / 損耗率分析

---

## 3. 角色（Roles）

| Role | 主要 API 群 | 說明 |
|---|---|---|
| Admin | `/admin/*` | 全權，管理組織、API key、資產 |
| CleaningCenterStaff | `/cleaning/*`、`/washing/*` | 建立資產、收貨確認、清洗、分發 |
| RestaurantStaff | `/restaurant/*` | 確認收貨、查庫存（不需逐件掃） |
| Courier | `/courier/*` | 取餐掃描、PIN 交付 |
| Consumer | `/consumer/*` | 查持有、掃描歸還 |
| Recycler | `/recycler/*` | 查回收箱狀態、協助異常 |
| Partner | `/partner/*` | 建單、查單，需 API key |
| Support | `/support/*` | 客服介入、爭議處理（所有操作必入 audit log） |

---

## 4. 主要實體（Entities）

### 4.1 Asset（餐盒 / 飲料杯）
```
id              UUIDv7  PK
asset_type      enum('meal_box','drink_cup')
short_code      TEXT    UNIQUE  -- 8 字元 Base32
short_code_hash TEXT    UNIQUE
token_hash      TEXT    UNIQUE  -- HMAC-SHA256(token, SECRET)
status          enum
physical_holder_type / id       -- 實體在哪
responsible_party_type / id     -- 誰負責（押金責任）
current_cycle_id  UUID  FK
usage_count       INT
created_at / retired_at
```

### 4.2 Order
```
id                       UUIDv7 PK
partner_id               FK
external_order_id        TEXT
restaurant_id / consumer_id / courier_id  FK
status                   enum
expected_asset_manifest  JSONB  -- {"meal_box":1,"drink_cup":2}
delivery_pin_hash        TEXT
delivery_pin_expires_at  TIMESTAMP
UNIQUE(partner_id, external_order_id)
```

### 4.3 詳細 schema
完整 schema 定義另存於 `docs/schema.md`（待建立），實作後同步維護。

---

## 5. 事件與不可竄改性

### 5.1 asset_events（per-asset hash chain）
- 每個重要動作寫一筆 event
- `event_hash` 串成鏈
- canonical event 去個資化

### 5.2 audit_logs（系統操作紀錄）
- 客服 / Admin / 手動覆寫操作
- 含 before/after snapshot、IP、User-Agent
- **不**和 asset_events 混用

### 5.3 chain_anchors
- daily Merkle root over 當日所有 event_hash
- 為未來 blockchain anchor 預留

---

## 6. 專案結構

```
oh-my-delivery/
├── app/
│   ├── main.py                  # FastAPI app entry
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── security.py          # JWT、HMAC、PIN hash
│   │   ├── permissions.py       # RBAC dependency
│   │   ├── idempotency.py       # Idempotency-Key 中介層
│   │   ├── hashing.py           # hash chain 計算
│   │   └── ids.py               # UUIDv7 / token / short_code 生成
│   ├── db/
│   │   ├── session.py
│   │   └── base.py
│   ├── domain/
│   │   ├── assets/              # AssetService、StateMachineService
│   │   ├── orders/
│   │   ├── pickup/              # PickupService（取餐 session）
│   │   ├── delivery/            # DeliveryService（PIN）
│   │   ├── returns/             # ReturnService（消費者歸還 session）
│   │   ├── cleaning/            # CleaningService（清洗中心確認）
│   │   ├── washing/             # 清洗批次
│   │   ├── deposits/            # DepositService（虛擬錢包）
│   │   ├── rewards/
│   │   ├── notifications/
│   │   ├── support/
│   │   ├── audit/
│   │   └── hashchain/
│   ├── api/
│   │   ├── deps.py              # 共用 dependency（current_user 等）
│   │   └── routes/
│   │       ├── auth.py
│   │       ├── admin.py
│   │       ├── partner_orders.py
│   │       ├── courier.py
│   │       ├── consumer.py
│   │       ├── restaurant.py
│   │       ├── cleaning.py
│   │       ├── washing.py
│   │       ├── devices.py       # 微動開關事件 ingest
│   │       └── support.py
│   ├── workers/
│   │   └── scheduler.py         # APScheduler jobs
│   └── integrations/
│       └── partner_api.py
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docker-compose.yml           # postgres
├── pyproject.toml               # uv 管理
├── uv.lock
├── .env.example
└── CLAUDE.md
```

**檔案大小規範**：典型 200–400 行，最多 800 行。超過要拆。

---

## 7. 核心設計原則（編碼時必須遵守）

1. **不可變優先**：service 回傳新物件，不就地 mutate
2. **每個寫入都要事務**：asset 狀態變更 + asset_events + audit/wallet 在同一 transaction
3. **Idempotency**：取餐 confirm、PIN 交付、感測器事件、清洗確認、押金扣款 / 釋放、獎勵發放 — 一律支援 `Idempotency-Key` header
4. **State machine 走 service**：禁止在 route 直接 `asset.status = ...`，一律過 `StateMachineService.transition(asset, target_state, actor, ctx)`
5. **錯誤訊息不洩資訊**：對外不揭示其他用戶的身份；對內 audit log 記細節
6. **時區**：DB 一律 UTC（`TIMESTAMP WITH TIME ZONE`），對外回 ISO 8601；面向消費者顯示時前端做轉換
7. **不寫沒被需求要求的功能**（YAGNI）；不為未來想像加抽象
8. **少加註解**：name 自說明；只有 *why* 不顯然時才加一行

---

## 8. 開發流程

### 8.1 啟動環境
```bash
# 第一次
uv sync
docker compose up -d                    # postgres
cp .env.example .env
uv run alembic upgrade head

# 日常
uv run uvicorn app.main:app --reload
uv run pytest
```

### 8.2 加新依賴
```bash
uv add fastapi sqlmodel alembic asyncpg
uv add --dev pytest pytest-asyncio httpx
```

### 8.3 加新 migration
```bash
uv run alembic revision --autogenerate -m "add deposit_records"
uv run alembic upgrade head
```

### 8.4 測試要求
- 單元測試：service / state_machine / hash chain 必測
- 整合測試：每個 API route 至少一個 happy path + 一個 error case
- TDD 優先（紅 → 綠 → 重構）
- 覆蓋率目標 80%+（黑客松 Demo 階段不卡死，但核心 service 必達）

---

## 9. Git Commit 規範

依照全域偏好（`~/.claude/CLAUDE.md`）：

- **不加 `Co-Authored-By:`**
- 格式：
  ```
  feat(scope): short description

  - bullet point 1
  - bullet point 2
  ```
- **分多次 commit**：每個功能段落 / checkpoint 各一次 commit。**禁止**把整個 sprint 堆到最後一次。
- type：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci`
- scope 範例：`assets`、`pickup`、`returns`、`cleaning`、`deposits`、`rewards`、`hashchain`、`partner-api`、`infra`

範例：
```
feat(assets): add Asset model with HMAC-SHA256 token_hash

- Asset SQLModel with status enum and holder fields
- ID generator producing UUIDv7 + Crockford Base32 token / short_code
- HMAC keyed by SERVER_SECRET from settings
```

---

## 10. Demo 範圍（v1 必交付）

### Must
- [ ] Asset / Order / Cycle / Event 資料模型 + Alembic migration
- [ ] HMAC token / short_code / hash chain 工具
- [ ] 清洗中心建立資產
- [ ] 清洗中心 → 餐廳分發 + 餐廳 ack
- [ ] Partner 建單（含 expected_manifest + PIN 產生）
- [ ] 外送員 pickup scan session（建立 / 掃描 / confirm）
- [ ] PIN 交付（含失敗計數 / 鎖定）
- [ ] 消費者歸還 session
- [ ] 微動開關事件 ingest + session 匹配
- [ ] 清洗中心收貨確認（觸發押金 / 獎勵）
- [ ] 清洗檢查 + component_status
- [ ] 押金釋放 / 扣款 / 等級累進
- [ ] 獎勵發放（防重複）
- [ ] 通知排程（寫表，不寄信）
- [ ] audit_logs
- [ ] daily chain_anchors 計算
- [ ] 基本 dashboard（GET 統計指標）

### Mock
- email/SMS 寄送、付款金流、真實感測器、真實外送平台、blockchain 上鏈

### Out of scope（v1 不做）
- 前端 UI / SPA
- 餐廳間餐具調度
- 回收車路線規劃
- GPS 驗證、NFC

---

## 11. 已知待澄清項（TBD，實作前再確認）

- 押金扣款失敗（wallet 餘額不足）的處理：允許負餘額？或產生待繳費單？
- 同一消費者同時持有多個餐具，逾期是否獨立計算 deposit_level？
- short_code 衝突重試上限（生成時 unique 衝突）
- chain_anchors 是否包含跨日 carry-over hash
- Demo 是否需要 seed data 腳本（建議：是，給示範用）

遇到上述項目時，先在 PR 描述中標 `TBD`，由業主確認後再 merge。

---

## 12. 重要參考

- 完整原始需求文件：本檔 §13（保留版）或專案根的 `docs/spec-original.md`（待建立）
- 流程圖 / 序列圖：`docs/diagrams/`（待建立）
- API 範例：FastAPI Swagger UI `/docs`、ReDoc `/redoc`

---

## 13. 重要設計結論（不可違反的鐵律）

1. 每個餐盒與飲料杯都是獨立主要資產
2. 外送員取餐必須逐一掃描每個主要資產
3. 掃描階段不立即轉移，confirm 時一次性轉移
4. 小零件不做責任追蹤，只在清洗中心記錄狀態
5. 微動開關只是中間證據，**清洗中心確認**才是最終事實
6. 押金與獎勵均依**清洗中心確認時間**判定
7. 身分證字號**絕對不**明文儲存（HMAC-SHA256）
8. 個資**絕對不**進 hash chain canonical event
9. 所有人工 / 管理操作必入 `audit_logs`
10. 所有狀態轉移必過 `StateMachineService`
11. 寫入操作支援 `Idempotency-Key`
12. 程式檔案 200–400 行典型，800 行硬上限

> 違反鐵律的程式不該被 merge。
