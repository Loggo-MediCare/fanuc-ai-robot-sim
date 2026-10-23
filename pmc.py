"""PMC 介面與模擬 PMC。

真實系統中，PMC 讀寫由 FANUC FOCAS（pmc_rdpmcrng / pmc_wrpmcrng）或
C Executor 橋接程式提供。這裡定義同樣形狀的介面，日後只要換掉實作類別，
controller.py 不需修改。
"""
import threading
from abc import ABC, abstractmethod

# R 區位址（對應書中 pmc_getpmcptr(5, 100, ...) 的 R100）
R_COMMAND = 100  # Python → PLC
R_STATUS = 101   # PLC → Python

# R100 命令位元
CMD_PICK_REQ = 1 << 0

# R101 狀態位元
ST_DOOR_CLOSED = 1 << 0
ST_ALARM = 1 << 1
ST_ROBOT_READY = 1 << 2
ST_PICK_ACCEPTED = 1 << 3
ST_PICK_DONE = 1 << 4
ST_PICK_REJECTED = 1 << 5
ST_FAULT = 1 << 6


class PMCError(Exception):
    """通訊失敗（對應 FOCAS 回傳非 EW_OK）。"""


class PMCInterface(ABC):
    @abstractmethod
    def read_short(self, r_addr: int) -> int: ...

    @abstractmethod
    def write_short(self, r_addr: int, value: int) -> None: ...


class SimulatedPMC(PMCInterface):
    """以字典模擬 R 區暫存器，可模擬通訊中斷。"""

    def __init__(self):
        self._regs = {}
        self._lock = threading.Lock()
        self.connected = True

    def read_short(self, r_addr):
        if not self.connected:
            raise PMCError(f"read R{r_addr} failed: not connected")
        with self._lock:
            return self._regs.get(r_addr, 0)

    def write_short(self, r_addr, value):
        if not self.connected:
            raise PMCError(f"write R{r_addr} failed: not connected")
        with self._lock:
            self._regs[r_addr] = value & 0xFFFF
