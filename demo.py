"""執行所有模擬情境：python demo.py"""
import threading
import time

from controller import run_pick_cycle
from plant_sim import SimulatedPlant
from pmc import SimulatedPMC
from vision import Detection, SimulatedVision


def run(name, setup=None, detection=None, during=None):
    pmc = SimulatedPMC()
    plant = SimulatedPlant(pmc)
    if setup:
        setup(plant, pmc)
    plant.start()
    time.sleep(0.05)  # 讓 PLC 先掃描幾次，寫入初始狀態
    if during:
        threading.Timer(0.1, during, args=(plant, pmc)).start()
    result = run_pick_cycle(pmc, SimulatedVision(detection), accept_timeout_s=0.5, done_timeout_s=1.0)
    plant.stop()
    print(f"{name:<28} → {result}")
    return result


def scenarios():
    return [
        ("1. 正常抓取", {}),
        ("2. 沒有偵測到物件", {"detection": Detection(False)}),
        ("3. 辨識信心不足 (0.70)", {"detection": Detection(True, "BOX", 0.70)}),
        ("4. 安全門開啟", {"setup": lambda p, m: setattr(p, "door_closed", False)}),
        ("5. PLC 警報", {"setup": lambda p, m: setattr(p, "alarm", True)}),
        ("6. 動作中安全門被打開", {"during": lambda p, m: setattr(p, "door_closed", False)}),
        ("7. 動作中 PLC 通訊中斷", {"during": lambda p, m: setattr(m, "connected", False)}),
    ]


if __name__ == "__main__":
    for name, kwargs in scenarios():
        run(name, **kwargs)
