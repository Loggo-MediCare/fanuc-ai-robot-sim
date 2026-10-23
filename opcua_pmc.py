"""Jetson 端（OPC UA Client）的 PMC 介面實作。

實作 pmc.PMCInterface，讓 controller.py 完全不用修改：
    read_short(R101)  → 一次讀取所有狀態 Node，組成位元字
    write_short(R100) → 寫入 Robot.PickRequest

另外有一條背景執行緒每 HEARTBEAT_PERIOD_S 遞增 Robot.Heartbeat，
讓 PLC 端的看門狗知道 Jetson 還活著。
"""
import threading

from asyncua import ua
from asyncua.sync import Client

from opcua_gateway import DEFAULT_ENDPOINT, STATUS_NODES, URI
from pmc import CMD_PICK_REQ, PMCError, PMCInterface, R_COMMAND, R_STATUS

HEARTBEAT_PERIOD_S = 0.1


class OpcUaPMC(PMCInterface):
    def __init__(self, url=DEFAULT_ENDPOINT, heartbeat=True):
        self.client = Client(url=url, timeout=4)
        try:
            self.client.connect()
            idx = self.client.get_namespace_index(URI)
            robot = self.client.nodes.objects.get_child([f"{idx}:Robot"])
            self._status = {name: robot.get_child([f"{idx}:{name}"]) for name in STATUS_NODES}
            self._pick_request = robot.get_child([f"{idx}:PickRequest"])
            self._heartbeat = robot.get_child([f"{idx}:Heartbeat"])
            self.idx, self.robot = idx, robot
        except Exception as e:
            raise PMCError(f"OPC UA connect failed: {e}") from e
        self._hb_count = int(self._heartbeat.read_value())
        self._hb_stop = threading.Event()
        self._hb_thread = None
        if heartbeat:
            self._send_heartbeat()          # 先送一次，PLC 看門狗立即恢復 COMM_OK
            self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._hb_thread.start()

    def _send_heartbeat(self):
        self._hb_count = (self._hb_count % 0xFFFFFFFE) + 1   # 0 保留為「尚未開始」
        try:
            self._heartbeat.write_value(ua.Variant(self._hb_count, ua.VariantType.UInt32))
        except Exception:
            pass

    def _heartbeat_loop(self):
        while not self._hb_stop.wait(HEARTBEAT_PERIOD_S):
            self._send_heartbeat()

    def stop_heartbeat(self):
        """模擬 Jetson 程式卡死：心跳停止，但連線還在。"""
        self._hb_stop.set()
        if self._hb_thread:
            self._hb_thread.join()

    def read_short(self, r_addr):
        if r_addr != R_STATUS:
            raise PMCError(f"R{r_addr} is not mapped to OPC UA")
        try:
            values = self.client.read_values(list(self._status.values()))
        except Exception as e:
            raise PMCError(f"read status failed: {e}") from e
        word = 0
        for (name, bit), value in zip(STATUS_NODES.items(), values):
            if value:
                word |= bit
        return word

    def write_short(self, r_addr, value):
        if r_addr != R_COMMAND:
            raise PMCError(f"R{r_addr} is not mapped to OPC UA")
        try:
            self._pick_request.write_value(bool(value & CMD_PICK_REQ))
        except Exception as e:
            raise PMCError(f"write PickRequest failed: {e}") from e

    def try_write(self, node_name, value):
        """示範用：嘗試寫入任意 Node，回傳伺服端的結果。"""
        node = self.robot.get_child([f"{self.idx}:{node_name}"])
        try:
            node.write_value(value)
            return "OK"
        except ua.UaStatusCodeError as e:
            return type(e).__name__

    def close(self):
        self.stop_heartbeat()
        try:
            self.client.disconnect()
        except Exception:
            pass
