# 回收箱（Return Box）硬體整合規格

> 對象：負責回收箱韌體與機構設計的硬體工程師
> 系統側資料來源：`app/api/routes/devices.py`、`app/domain/devices/service.py`、`app/domain/returns/service.py`
> 文件版本：v1（黑客松 Demo 範圍）

---

## 1. 系統脈絡

回收箱是「消費者歸還」流程中的中間證據來源，**不是最終事實來源**（最終事實是清洗中心收貨確認）。

完整流程：

```
[消費者 App]                [回收箱（你的硬體）]              [後端]              [清洗中心]
     |                              |                          |                       |
  1. 掃 QR ── POST /consumer/returns/scan ─────────────────► 建立 ReturnSession        |
                                                              (status=SCANNED, TTL 60s)
     |                              |                          |                       |
  2. 顯示資產代碼確認                |                          |                       |
                                                                                       |
  3. 開啟投入口 ──── 物理投入 ──► 微動開關被觸發                |                       |
                                  │                            |                       |
                                  └─ POST /devices/return-boxes/{id}/sensor-events ──► 比對
                                                                                       匹配 SCANNED session
                                                                                       資產 → DEPOSITED_IN_RETURN_BOX
     |                              |                          |                       |
     |                              |                  4. 回收車載運至清洗中心 ───────► 掃描收貨
     |                              |                                               資產 → RETURNED_TO_CLEANING_CENTER
     |                              |                                               觸發押金退還、獎勵發放
```

回收箱韌體只需要關心 **Step 3**：在物理投入發生時，把一個帶有唯一 ID 的事件 POST 給後端。

---

## 2. 設備生命週期

### 2.1 註冊（一次性，由 Admin 在後台執行）

```
POST /onboarding/return-boxes
Headers: X-Role: admin   X-Actor-Id: <admin-uuid>
Body: { "label": "1F 大廳投入箱" }

回應 201:
{
  "id": "01923e7d-...",            ← return_box_id（韌體要燒入這個）
  "label": "1F 大廳投入箱",
  "active": true,
  "created_at": "...",
  "api_key": "rb_K9wXp7Mq..."      ← API key（韌體要安全儲存，僅此次回傳）
}
```

韌體出廠或現場部署時，把 `id` 與 `api_key` 燒入安全儲存區（NVS / secure element）。

> **重要**：`api_key` 只在建立當下回傳一次，之後後端只存 HMAC-SHA256 hash，遺失只能由 Admin 重建設備。

### 2.2 停用 / 啟用

Admin 可以將 `active=false`。被停用後，所有事件回應 `403 return box disabled`。韌體看到 401 / 403 應該：
- 停止再送同一事件
- 點亮錯誤指示燈（紅燈長亮）
- 後續觸發進入「離線緩存」模式（見 §6）

---

## 3. 唯一 API：上報感測器事件

```
POST /devices/return-boxes/{return_box_id}/sensor-events
Content-Type: application/json
X-Device-Key: <api_key>            ← 純文字 header，HTTPS 傳輸

Body:
{
  "device_event_id": "evt-{box_id}-{monotonic_counter}",
  "event_type": "micro_switch_triggered",
  "triggered_at": "2026-05-10T14:32:11.123Z"
}
```

| 欄位 | 必填 | 限制 | 說明 |
|---|---|---|---|
| `device_event_id` | 是 | 1–128 字元 | **裝置端產生的全域唯一 ID**。是冪等鍵；同一 ID 多次送只計一次。 |
| `event_type` | 是 | ≤64 字元 | 目前只接受 `micro_switch_triggered`。預留給未來重量感測 / 紅外線。 |
| `triggered_at` | 是 | ISO 8601 + TZ | 微動開關被觸發的本地時戳；要包含 timezone（建議用 UTC 後綴 `Z`）。**`|now − triggered_at| > 5 分鐘會被後端拒絕（HTTP 422）**。請務必對時（NTP）。 |

### 3.1 回應

```jsonc
HTTP 202 Accepted
{
  "sensor_event_id": "01923e7d-...",
  "duplicate": false,                          // 同 device_event_id 重複送會是 true
  "matched_return_session_id": "01923e7d-...", // null 表示沒成功匹配
  "deposit_recorded": true,                    // 唯一可信的「成功」訊號（true ↔ 資產狀態已轉移）
  "message": "matched return session; deposit recorded"
}
```

> **韌體請只看 `deposit_recorded` 判斷成功 / 失敗。** `message` 與 `matched_return_session_id` 僅供 log。

| `deposit_recorded` | `matched_return_session_id` | 訊息 | 含義 | 韌體應該怎麼做 |
|---|---|---|---|---|
| `true` | 不為 null | `matched return session; deposit recorded` | 成功匹配並轉移資產 | 綠燈 1.5 秒，回 IDLE |
| `false` | null | `orphan event recorded; no active return session` | 沒掃描就投入，或 60 秒過期 | 黃燈 2 秒 + 螢幕「請先在 App 掃描」 |
| `false` | null | `session found but asset not in return_pending_deposit; no transition` | 有 session 但消費者已取消 / Admin override | 黃燈 2 秒 + 螢幕「請聯絡服務人員」 |
| `false` | 重複時可能不為 null | `duplicate device_event_id; ignored` | 你重送了同一事件 | 不再重送，回 IDLE |

### 3.2 錯誤碼

| Status | 情境 | 處置 |
|---|---|---|
| 401 | `X-Device-Key` 錯誤 | 永久故障，紅燈長亮，需要現場重新部署 |
| 403 | 該 return box 已被 Admin 停用 | 同上，不再重送 |
| 404 | `return_box_id` 不存在 | 同上 |
| 422 | Body 格式錯誤 **或 `triggered_at` 偏離伺服器時間 > 5 分鐘** | 檢查 NTP；對時成功後重產 `device_event_id` 重送 |
| 5xx / timeout | 後端暫時不可用 | 進入離線緩存模式（見 §6） |

> **關於 422 + 時鐘偏移**：若離線緩存事件積壓很久才送出，整批可能因 skew 全被 422 拒絕。處理方式：恢復網路後**先校時 NTP**，再重新檢查緩存中事件的 `triggered_at` 是否已超出 5 分鐘窗。**超過 5 分鐘的事件**屬於資料事故，不要試圖竄改時戳重送；應該（a）登錄錯誤、（b）通知中央伺服器有遺失事件需要 Admin 補登。

---

## 4. `device_event_id` 規格（重要！）

冪等鍵設計直接影響資料一致性。要求：

1. **格式**：建議 `evt-{return_box_id_short}-{monotonic_counter}`
   - 例：`evt-9c5f-000001234`
   - `monotonic_counter` 必須單調遞增、跨重啟保留（存 NVS / EEPROM）
2. **長度**：≤128 字元（後端 `String(128)`）
3. **唯一性**：同一 `(return_box_id, device_event_id)` 在後端有 UNIQUE 約束。重複送回應 `duplicate=true`。
4. **重啟後**：counter 從 NVS 讀取，繼續遞增；**禁止**從 0 重新開始（會撞到歷史 ID 並被當成 duplicate，導致實際投入被誤判為重複）。

> **失敗模式**：如果 NVS 寫入失敗或被清除，counter 重置 → 實際的新投入被誤判為重複事件 → 後端不轉移資產 → 消費者押金不退。**必須**在 counter 寫入失敗時點亮紅燈並停機。

---

## 5. 物理觸發與防彈跳（Debounce）

微動開關的物理特性：

- **接觸彈跳**：機械開關在切換瞬間會產生數十至數百個短脈衝。若不 debounce，一次投入會送出 N 個 event。
- **多重觸發**：投入大型餐盒可能同時壓到兩顆開關。
- **誤觸**：清潔人員打開後門檢查也可能觸發。

### 韌體要求

1. **硬體 RC 濾波 + 軟體 debounce**：兩級組合。建議軟體 debounce 視窗 ≥ 50ms。
2. **單一邏輯事件**：一次「物理投入」必須只送 **一個** `device_event_id`。多顆開關取邏輯 OR + debounce 後當一個事件。
3. **冷卻時間**：相鄰兩次合法事件之間應有最小間隔（建議 ≥ 2 秒），低於此間隔的觸發視為彈跳忽略。
4. **後門 / 維護蓋觸發另計**：建議獨立感測器 + 獨立 `event_type`（未來預留 `service_door_opened`，本期不上報）。

---

## 6. 網路不穩 — 離線緩存策略

回收箱可能在 Wi-Fi 失聯時仍被使用。要求：

1. **本地佇列**：把未送出的事件（含已分配的 `device_event_id` 與 `triggered_at`）存到 NVS。佇列容量建議 ≥ 256 筆。
2. **重送策略**：
   - 指數退避：1s → 2s → 4s → 8s → … 上限 60s
   - 收到 `2xx` 或 `4xx`（除 `401/403` 外的 4xx）視為「處理完畢」，移出佇列
   - 收到 `401 / 403`：永久故障，停送、亮紅燈
3. **批次送**：不需要批次 API；逐筆 POST 即可（後端冪等保護到位）。
4. **時鐘**：盡量用 NTP；若無網路則用 RTC + 啟動時的最後已知 NTP 時間估算。`triggered_at` 不準不會擋事件（後端只用做稽核），但會影響日後對帳。

---

## 7. 狀態機保證（後端 + 硬體雙重閉環）

### 7.1 後端側保證（已實作）

後端強制「同一 return box 同時最多一個 active SCANNED session」：

- 消費者 A 在箱 B 掃資產 X → session A 建立（status=SCANNED）。
- 在 session A 仍 active 的 60 秒內，**任何人**（含 A 自己換另一件）試圖在箱 B 掃描 → 後端回 `409 Conflict: another return is in progress at this box; please wait or cancel it`。
- session A 過期 / 取消 / 已偵測到投入 後，下一個人才能掃。

這個約束消除了「雙 session race 導致的誤匹配」風險。**App 端會把 409 顯示給使用者**，引導他們等一下或請前一位完成。

### 7.2 硬體側仍應提供的物理閉環

即使後端有約束，硬體仍須避免「兩個人物理同時靠近」：

1. **單投入口設計**：物理上只允許一次投入一件。
2. **建議 UX**（IDLE → 掃描中 → 等待投入 → 完成）：
   - LCD `IDLE`：「請使用 App 掃描 QR Code」
   - 偵測到投入：綠燈 1.5 秒、`投入成功（後 4 碼）` 顯示 3 秒、回 IDLE
   - 60 秒內未投入：黃燈 + `請先在 App 上掃描`（此時對應後端 orphan event）
   - 收到 422（時鐘偏移）：紅燈 + `設備時鐘異常，請聯絡管理員`
3. **冷卻期**：偵測到一次投入後，最少 3 秒不接受下一次微動觸發（避免反彈與快速連投）。

> 本 Demo 不做「App ↔ 箱子」即時通訊，箱子無法主動知道哪個 session 正在等待。但有了 §7.1 的後端約束，即便箱子無感知，**雙 session 競爭也不會發生**。

---

## 8. 安全 / 合規

| 項目 | 規範 |
|---|---|
| 傳輸 | HTTPS only。Demo 可用自簽憑證，但韌體要支援設定 trusted CA。 |
| API key | 只送出，不顯示在 LCD / log。記憶體中盡量短暫保留。 |
| 個資 | 韌體**絕對不**接觸 consumer_id、訂單資訊、身分證、電話。只送 `device_event_id`。 |
| 日誌 | 本機只保留事件流水（device_event_id、time、http_status）。不存任何個資。 |
| 韌體更新 | OTA 機制本期不規範；建議現場 USB 燒錄。 |

---

## 9. 韌體驗收測試清單

啟動後請對照後端執行以下情境（可用 Postman / curl 對照）：

| # | 情境 | 預期結果 |
|---|---|---|
| 1 | 正常投入：先用 App 掃，60 秒內物理投入 | 收 202、`deposit_recorded=true`、`matched_return_session_id` 不為 null、綠燈、消費者後台看到資產狀態 `deposited_in_return_box` |
| 2 | 沒掃描就投入 | 收 202、`deposit_recorded=false`、`matched_return_session_id` 為 null、黃燈 |
| 3 | 微動開關彈跳 | 連續 10 個物理脈衝只送出 1 個 `device_event_id` |
| 4 | 重送同 event | 收 202、`duplicate=true`、不額外動作 |
| 5 | 拔掉網路時投入 → 5 分鐘內恢復網路 | 緩存中的事件全部送出（`deposit_recorded=true`），狀態正確 |
| 5b | 拔網投入 → 超過 5 分鐘才恢復 | 該事件送出時收 422 `clock skew`；韌體應該登錄錯誤而非偽造時戳 |
| 6 | 故意傳錯 X-Device-Key | 收 401、紅燈長亮、不再重送 |
| 7 | 後台把 box 設 inactive | 收 403、紅燈長亮、不再重送 |
| 8 | counter NVS 失敗（拔電寫入時） | 紅燈、停機、不上送任何新事件 |
| 9 | 消費者掃描後取消、再投入 | 收 202、`deposit_recorded=false`、`matched_return_session_id` 為 null（後端不會誤標）、黃燈 + 「請聯絡服務人員」訊息 |

---

## 10. 待硬體側回覆 / 確認的問題

- [ ] 微動開關型號 / 額定操作壽命 → 影響韌體 debounce 參數
- [ ] 是否同時支援多顆開關 OR 邏輯
- [ ] 是否有後門 / 維護蓋的獨立感測（本期不上報，但結構上建議預留）
- [ ] 預期日均投入次數 → 影響 NVS 寫入耗損評估
- [ ] 是否提供現場按鈕「手動取消最後一次事件」（**Demo 不需要**，但若做了會影響後端 API 設計）

---

## 11. 後端修復紀錄（v1）

下列三個問題在 v1 已修復；保留紀錄供回溯：

| Issue | 修復方式 | 對韌體的意義 |
|---|---|---|
| 多 session 同箱 race | `ReturnService.scan` 拒絕「同箱另有 active SCANNED session」，回 409 | 韌體不必再擔心被誤匹配；雙 session 在後端被擋掉 |
| 「假匹配」訊息誤導 | 改為 **只有資產真的轉移時才設 `matched_return_session_id` + 新增 `deposit_recorded` 旗標** | 韌體只看 `deposit_recorded` 即可判斷成敗 |
| `triggered_at` 不驗證 | 偏離 ±5 分鐘的事件 → HTTP 422 | 韌體必須對時 NTP；超期事件視為資料事故 |

對應驗證測試：

- `tests/integration/test_return_flow.py::test_concurrent_scan_at_same_box_is_rejected`
- `tests/integration/test_return_flow.py::test_sensor_event_does_not_lie_when_asset_not_pending`
- `tests/integration/test_return_flow.py::test_sensor_event_with_clock_skew_rejected`

---

## 12. 聯絡 / 變更管理

- 規格變更：以 PR 修改本檔，標 `docs(hardware)`。硬體側 sign-off 後合併。
- 後端 API 在 v1 內保證 backward compatible。
- 任何 schema 變動會在 PR 描述列出 `BREAKING:` 標記。
