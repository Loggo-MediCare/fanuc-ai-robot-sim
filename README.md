# FANUC PMC + AI 機械手臂模擬（第 1 步）

純 Python 模擬，不需 Jetson、不需 FANUC 控制器。第 1 步不需安裝任何套件（Python 3.8+）；第 2 步 OPC UA 需要 `asyncua`。

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

## 第 2 步：OPC UA 雙向通訊（Jetson = Client，PLC = Server）

需要 `python -m pip install -r requirements.txt`（asyncua）。

```
python demo_opcua.py              # 5 個情境
python -m unittest test_opcua -v  # 5 個測試
```

### 第二堂課程範例（`lesson/`）

```
python lesson/plc_server.py       # 終端機 1
python lesson/jetson_client.py    # 終端機 2 → Robot Ready: True / Robot Alarm: False / AI may propose a pick request
```

### 架構

```
Jetson Python（OPC UA Client）          OPC UA 閘道（Server）            PLC 梯形圖＋機械手臂
  controller.py（未修改）                opcua_gateway.py                 plant_sim.py
  └ opcua_pmc.py ──── Ethernet / OPC UA ──► Robot.* Node ◄──► R100/R101 ──► PERMIT / ACCEPT / ABORT
       └ 心跳執行緒，每 0.1 s 寫 Robot.Heartbeat      └ 看門狗：0.5 s 沒變 → COMM_OK = False
```

`opcua_pmc.py` 實作和 `SimulatedPMC` 相同的 `read_short` / `write_short` 介面，所以 `controller.py` 一行都不用改，正好驗證第 1 步「只換 PMC 實作」的設計。

### Node 一覽（教學用名稱，不是 FANUC 內建 Node）

| Node | 類型 | 方向 | Client 可寫 | 對應 R 區 |
|---|---|---|---|---|
| `Robot.Ready` | Boolean | PLC → Jetson | 否 | R101 bit2 |
| `Robot.DoorClosed` | Boolean | PLC → Jetson | 否 | R101 bit0 |
| `Robot.Alarm` | Boolean | PLC → Jetson | 否 | R101 bit1 |
| `Robot.PickAccepted` | Boolean | PLC → Jetson | 否 | R101 bit3 |
| `Robot.PickDone` | Boolean | PLC → Jetson | 否 | R101 bit4 |
| `Robot.PickRejected` | Boolean | PLC → Jetson | 否 | R101 bit5 |
| `Robot.Fault` | Boolean | PLC → Jetson | 否 | R101 bit6 |
| `Robot.PickRequest` | Boolean | Jetson → PLC | **是** | R100 bit0 |
| `Robot.Heartbeat` | UInt32 | Jetson → PLC | **是** | （閘道內部看門狗） |

### 情境與結果

| 情境 | 結果 |
|---|---|
| 1. 正常抓取（寫 PickRequest → PLC 回 PickDone） | `PICK_DONE` |
| 2. 安全門開啟 | `BLOCKED` |
| 3. 動作中安全門被打開 | `FAULT` |
| 4. Client 嘗試寫入 `Alarm`、`PickDone`、`DoorClosed` | 伺服端回 `BadUserAccessDenied`；只有 `PickRequest` 寫入成功 |
| 5. 動作中 Jetson 程式卡死（心跳停止） | PLC 看門狗 0.5 s 後中止手臂、設 Fault，並取消失聯 Client 的 PickRequest |

情境 5 補上了第 1 步情境 7 的缺口：現在 PLC 端自己知道上位端失聯，不需要上位端回報。

### 安全性提醒

本範例使用 `127.0.0.1`、`NoSecurity`（不加密、不驗證身分），**只適合同一台電腦練習**。跨機器部署時需要：可信任憑證、`SignAndEncrypt` 安全策略、使用者帳號與權限、網路隔離。AI 通訊系統不能取代獨立的安全互鎖與緊急停止。

### 接真正的 FANUC 之前要確認

1. 控制器是否原生提供 OPC UA Server，或需要 Gateway（FANUC FASOPC 定位為 CNC 資料擷取，不能假設可寫入任意 PMC 或下達手臂動作）。
2. 哪些 Node 可讀、哪些可寫。
3. 機械手臂控制器接受什麼動作請求。
4. 安全互鎖與緊急停止如何獨立於 AI 通訊系統運作。

## 下一步

1. 把 `SimulatedVision` 換成 NVIDIA Jetson 上的攝影機＋影像辨識模型。
2. 依實際控制器，把 `opcua_gateway.py` 換成真正的 OPC UA Server，或把 `SimulatedPMC` 換成 FOCAS 實作。
3. 包成 ROS 2 node，接 Isaac Sim 機械手臂模擬。
