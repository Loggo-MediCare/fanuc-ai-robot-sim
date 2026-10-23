"""模擬 PLC 梯形圖掃描與機械手臂。

在背景執行緒中每 10 ms 掃描一次，行為對應以下梯形圖邏輯：

    PERMIT   = DOOR_CLOSED AND NOT ALARM AND ROBOT_READY AND COMM_OK
    ACCEPT   = PICK_REQ AND PERMIT AND NOT BUSY AND NOT DONE  → 鎖存 BUSY，機械手臂開始動作
    REJECT   = PICK_REQ AND NOT PERMIT AND NOT BUSY
    ABORT    = BUSY AND NOT PERMIT                            → 機械手臂停止，設 FAULT
    DONE     = 機械手臂動作完成                               → 鎖存，直到 PICK_REQ 解除
"""
import threading
import time

from pmc import (
    CMD_PICK_REQ, R_COMMAND, R_STATUS,
    ST_ALARM, ST_DOOR_CLOSED, ST_FAULT, ST_PICK_ACCEPTED,
    ST_PICK_DONE, ST_PICK_REJECTED, ST_ROBOT_READY,
)

SCAN_PERIOD_S = 0.01


class SimulatedPlant:
    def __init__(self, pmc, pick_duration_s=0.3):
        self.pmc = pmc
        self.pick_duration_s = pick_duration_s
        # 現場輸入（由測試情境改變）
        self.door_closed = True
        self.alarm = False
        self.robot_ready = True
        self.comm_ok = True   # 上位端心跳正常（由 OPC UA 閘道的看門狗設定）
        # PLC 內部狀態
        self._busy = False
        self._done = False
        self._fault = False
        self._move_started = 0.0
        self.picks_completed = 0
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def _loop(self):
        while self._running:
            if self.pmc.connected:
                self.scan()
            time.sleep(SCAN_PERIOD_S)

    def scan(self):
        pick_req = bool(self.pmc.read_short(R_COMMAND) & CMD_PICK_REQ)
        permit = self.door_closed and not self.alarm and self.robot_ready and self.comm_ok
        rejected = False

        if self._busy:
            if not permit:
                self._busy = False
                self._fault = True
            elif time.monotonic() - self._move_started >= self.pick_duration_s:
                self._busy = False
                self._done = True
                self.picks_completed += 1
        elif pick_req and not self._done and not self._fault:
            if permit:
                self._busy = True
                self._move_started = time.monotonic()
            else:
                rejected = True

        if not pick_req:
            # 握手完成：上位端撤回請求後清除鎖存位元
            self._done = False
            self._fault = False

        status = 0
        if self.door_closed:
            status |= ST_DOOR_CLOSED
        if self.alarm:
            status |= ST_ALARM
        if self.robot_ready and not self._busy:
            status |= ST_ROBOT_READY
        if self._busy:
            status |= ST_PICK_ACCEPTED
        if self._done:
            status |= ST_PICK_DONE
        if rejected:
            status |= ST_PICK_REJECTED
        if self._fault:
            status |= ST_FAULT
        self.pmc.write_short(R_STATUS, status)
