"""OPC UA 閘道：在模擬 PLC 前面提供 OPC UA Server（PLC = Server）。

結構（對應課程第 4 節「需要 Gateway」的情況）：

    Jetson (OPC UA Client) ──Ethernet / OPC UA──► 本閘道 ──R100/R101──► PLC 梯形圖 ＋ 機械手臂

每 10 ms 一個掃描週期：
    1. 讀 Robot.PickRequest → 寫入 R100 bit0
    2. 心跳看門狗：Robot.Heartbeat 超過 HEARTBEAT_TIMEOUT_S 沒變 → COMM_OK = False
    3. 執行梯形圖掃描
    4. 讀 R101 → 更新各狀態 Node

存取權限：只有 PickRequest 與 Heartbeat 開放 Client 寫入；其他 Node 只能讀。

單獨執行：python opcua_gateway.py
"""
import asyncio
import logging
import threading
import time

from asyncua import Server, ua

from pmc import (
    CMD_PICK_REQ, R_COMMAND, R_STATUS, SimulatedPMC,
    ST_ALARM, ST_DOOR_CLOSED, ST_FAULT, ST_PICK_ACCEPTED,
    ST_PICK_DONE, ST_PICK_REJECTED, ST_ROBOT_READY,
)
from plant_sim import SCAN_PERIOD_S, SimulatedPlant

URI = "urn:robot:training"
DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4840/robot/"
HEARTBEAT_TIMEOUT_S = 0.5

# Node 名稱 → R101 位元
STATUS_NODES = {
    "Ready": ST_ROBOT_READY,
    "DoorClosed": ST_DOOR_CLOSED,
    "Alarm": ST_ALARM,
    "PickAccepted": ST_PICK_ACCEPTED,
    "PickDone": ST_PICK_DONE,
    "PickRejected": ST_PICK_REJECTED,
    "Fault": ST_FAULT,
}
WRITABLE_NODES = ("PickRequest", "Heartbeat")


class OpcUaGateway:
    def __init__(self, endpoint=DEFAULT_ENDPOINT, pick_duration_s=0.3):
        self.endpoint = endpoint
        self.pmc = SimulatedPMC()
        self.plant = SimulatedPlant(self.pmc, pick_duration_s=pick_duration_s)
        self.nodes = {}
        self.events = []          # 給示範與測試看的事件紀錄
        self._last_hb = None
        self._last_hb_change = 0.0
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._stop = None

    # ---------- 在背景執行緒中執行，方便同一個程式示範 Client ----------
    def start(self):
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("OPC UA server did not start")

    def stop(self):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(10)

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        server = Server()
        await server.init()
        server.set_endpoint(self.endpoint)
        server.set_server_name("Simulated FANUC PMC Gateway")
        # 僅供本機練習：不加密、不驗證身分。跨機器部署需設定憑證、帳號與 SignAndEncrypt。
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        logging.getLogger("asyncua.server.server").setLevel(logging.ERROR)  # 隱藏「未加密」警告
        idx = await server.register_namespace(URI)
        robot = await server.nodes.objects.add_object(idx, "Robot")
        for name in STATUS_NODES:
            self.nodes[name] = await robot.add_variable(idx, name, False)
        self.nodes["PickRequest"] = await robot.add_variable(idx, "PickRequest", False)
        self.nodes["Heartbeat"] = await robot.add_variable(
            idx, "Heartbeat", ua.Variant(0, ua.VariantType.UInt32))
        for name in WRITABLE_NODES:
            await self.nodes[name].set_writable()

        async with server:
            self._ready.set()
            while not self._stop.is_set():
                await self._scan()
                await asyncio.sleep(SCAN_PERIOD_S)

    async def _scan(self):
        now = time.monotonic()
        # 1. PickRequest → R100
        req = await self.nodes["PickRequest"].read_value()
        self.pmc.write_short(R_COMMAND, CMD_PICK_REQ if req else 0)

        # 2. 心跳看門狗（Client 第一次送出心跳後才開始監控）
        hb = await self.nodes["Heartbeat"].read_value()
        if hb != self._last_hb:
            self._last_hb, self._last_hb_change = hb, now
        comm_ok = self._last_hb is None or hb == 0 or now - self._last_hb_change <= HEARTBEAT_TIMEOUT_S
        if comm_ok != self.plant.comm_ok:
            self.events.append("heartbeat restored" if comm_ok else "heartbeat lost → COMM_OK=False")
        self.plant.comm_ok = comm_ok

        # 3. 梯形圖掃描
        before = self.plant.picks_completed
        self.plant.scan()
        if self.plant.picks_completed != before:
            self.events.append("robot pick completed")
        if not comm_ok and req:
            # 失聯的 Client 無法撤回請求，由 PLC 端取消，避免恢復連線後自動動作
            await self.nodes["PickRequest"].write_value(False)
            self.events.append("PickRequest cancelled by PLC")

        # 4. R101 → 狀態 Node（伺服端內部寫入不受 Client 權限限制）
        word = self.pmc.read_short(R_STATUS)
        for name, bit in STATUS_NODES.items():
            value = bool(word & bit)
            if value != await self.nodes[name].read_value():
                if name == "Fault" and value:
                    self.events.append("PLC aborted motion → Fault")
                await self.nodes[name].write_value(value)


if __name__ == "__main__":
    gw = OpcUaGateway()
    gw.start()
    print(f"Simulated PLC gateway running at {gw.endpoint}  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        gw.stop()
