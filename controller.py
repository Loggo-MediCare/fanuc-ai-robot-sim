"""上位端（Jetson Python）邏輯：AI 判斷 → 向 PLC 提出請求 → 等待握手完成。

分工原則：AI 只「提出請求」，是否允許動作由 PLC 互鎖決定。
"""
import time
from dataclasses import dataclass

from pmc import (
    CMD_PICK_REQ, PMCError, R_COMMAND, R_STATUS,
    ST_ALARM, ST_DOOR_CLOSED, ST_FAULT, ST_PICK_ACCEPTED,
    ST_PICK_DONE, ST_PICK_REJECTED, ST_ROBOT_READY,
)

MIN_CONFIDENCE = 0.90
POLL_S = 0.01


@dataclass
class PLCStatus:
    door_closed: bool
    alarm: bool
    robot_ready: bool

    @classmethod
    def from_word(cls, word):
        return cls(
            door_closed=bool(word & ST_DOOR_CLOSED),
            alarm=bool(word & ST_ALARM),
            robot_ready=bool(word & ST_ROBOT_READY),
        )


def plan_robot_action(detection, plc):
    """回傳 WAIT / BLOCKED / REQUEST_PICK。"""
    if not detection.detected or detection.confidence < MIN_CONFIDENCE:
        return "WAIT"
    if not plc.door_closed or plc.alarm or not plc.robot_ready:
        return "BLOCKED"
    return "REQUEST_PICK"


def _wait_for(pmc, mask, timeout_s):
    """等待 R101 任一指定位元為 1；逾時回傳 None。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        word = pmc.read_short(R_STATUS)
        if word & mask:
            return word
        time.sleep(POLL_S)
    return None


def run_pick_cycle(pmc, vision, accept_timeout_s=1.0, done_timeout_s=3.0):
    """執行一次完整的抓取循環，回傳結果字串。"""
    try:
        plc = PLCStatus.from_word(pmc.read_short(R_STATUS))
        action = plan_robot_action(vision.detect(), plc)
        if action != "REQUEST_PICK":
            return action

        pmc.write_short(R_COMMAND, CMD_PICK_REQ)
        try:
            word = _wait_for(pmc, ST_PICK_ACCEPTED | ST_PICK_DONE | ST_PICK_REJECTED | ST_FAULT,
                             accept_timeout_s)
            if word is None:
                return "TIMEOUT_ACCEPT"
            if word & ST_PICK_REJECTED:
                return "REJECTED_BY_PLC"
            if word & ST_FAULT:
                return "FAULT"

            word = _wait_for(pmc, ST_PICK_DONE | ST_FAULT, done_timeout_s)
            if word is None:
                return "TIMEOUT_DONE"
            if word & ST_FAULT:
                return "FAULT"
            return "PICK_DONE"
        finally:
            # 無論結果如何都撤回請求，讓 PLC 清除鎖存位元；
            # 通訊已斷時撤回也會失敗，不可蓋掉原本的錯誤
            try:
                pmc.write_short(R_COMMAND, 0)
            except PMCError:
                pass
    except PMCError as e:
        return f"COMM_ERROR: {e}"
