# FANUC PMC + AI 機械手臂模擬（第 1 步）

純 Python 模擬，不需 Jetson、不需 FANUC 控制器、不需安裝任何套件（Python 3.8+）。

分工原則：**AI 負責「看見、判斷、提出請求」；PLC 負責「確認條件、允許動作」；機械手臂控制器負責「實際移動」。** AI 的判斷不能取代緊急停止或安全互鎖。

## 執行

```
python demo.py              # 執行 7 個情境
python -m unittest -v       # 執行測試
```

## 檔案

| 檔案 | 角色 | 日後替換為 |
|---|---|---|
| `vision.py` | 模擬 AI 辨識 | NVIDIA Jetson / Isaac ROS 推論結果 |
| `pmc.py` | PMC 讀寫介面＋模擬 R 區暫存器 | FOCAS `pmc_rdpmcrng` / `pmc_wrpmcrng`，或 C Executor 橋接 |
| `plant_sim.py` | 模擬 PLC 梯形圖掃描＋機械手臂 | 真實 FANUC PMC 與機械手臂控制器 |
| `controller.py` | 上位端邏輯：判斷 → 請求 → 握手 | 保留不改（只換 `pmc` 與 `vision` 實作） |
| `demo.py` | 7 個情境 | — |

## R 區配置（對應書中 `pmc_getpmcptr(5, 100, ...)`）

| 位址 | 方向 | 位元 |
|---|---|---|
| R100 | Python → PLC | bit0 `PICK_REQ` |
| R101 | PLC → Python | bit0 `DOOR_CLOSED`、bit1 `ALARM`、bit2 `ROBOT_READY`、bit3 `PICK_ACCEPTED`、bit4 `PICK_DONE`、bit5 `PICK_REJECTED`、bit6 `FAULT` |

## 梯形圖邏輯（`plant_sim.py`）

```
PERMIT = DOOR_CLOSED AND NOT ALARM AND ROBOT_READY
ACCEPT = PICK_REQ AND PERMIT AND NOT BUSY AND NOT DONE   → 鎖存 BUSY，手臂開始動作
REJECT = PICK_REQ AND NOT PERMIT AND NOT BUSY
ABORT  = BUSY AND NOT PERMIT                             → 手臂停止，設 FAULT
DONE   = 手臂動作完成                                    → 鎖存到 PICK_REQ 撤回為止
```

## 握手流程（`controller.py`）

1. 讀 R101 狀態＋AI 辨識 → 決定 `WAIT` / `BLOCKED` / `REQUEST_PICK`
2. 寫 R100 `PICK_REQ=1`
3. 等 `ACCEPTED` / `REJECTED` / `FAULT`（逾時 → `TIMEOUT_ACCEPT`）
4. 等 `DONE` / `FAULT`（逾時 → `TIMEOUT_DONE`）
5. 無論結果都寫 R100 `PICK_REQ=0`，PLC 清除鎖存位元

## 情境與結果

| 情境 | 結果 |
|---|---|
| 1. 正常抓取 | `PICK_DONE` |
| 2. 沒有偵測到物件 | `WAIT` |
| 3. 辨識信心不足 (0.70) | `WAIT` |
| 4. 安全門開啟 | `BLOCKED` |
| 5. PLC 警報 | `BLOCKED` |
| 6. 動作中安全門被打開 | `FAULT`（PLC 中止動作） |
| 7. 動作中 PLC 通訊中斷 | `COMM_ERROR` |

## 下一步

1. **PLC 端心跳（watchdog）**：情境 7 中上位端知道斷線，但 PLC 端不知道。真實系統需由 Python 定期翻轉一個心跳位元，PLC 偵測停止翻轉即中止動作。
2. 把 `SimulatedVision` 換成真實攝影機＋模型推論。
3. 把 `SimulatedPMC` 換成 FOCAS 實作（需確認控制器型號與選配是否支援）。
4. 包成 ROS 2 node，接 Isaac Sim 機械手臂模擬。
