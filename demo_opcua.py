"""OPC UA 雙向通訊實驗：Jetson（Client）↔ 模擬 PLC 閘道（Server）。

python demo_opcua.py

同一個程式裡在背景啟動 PLC 閘道，再以 OPC UA Client 連線執行各情境。
也可以分開兩個終端機：python opcua_gateway.py ／ 自己寫 Client 連線。
"""
import time

from controller import run_pick_cycle
from opcua_gateway import OpcUaGateway
from opcua_pmc import OpcUaPMC
from pmc import CMD_PICK_REQ, R_COMMAND, R_STATUS, ST_PICK_ACCEPTED
from vision import SimulatedVision


def settle():
    time.sleep(0.1)   # 等 PLC 掃描幾次（每 10 ms 一次）


def pick(gw, during=None):
    pmc = OpcUaPMC(gw.endpoint)
    settle()
    if during:
        import threading
        threading.Timer(0.1, during).start()
    result = run_pick_cycle(pmc, SimulatedVision(), accept_timeout_s=1.0, done_timeout_s=2.0)
    pmc.close()
    return result


def main():
    gw = OpcUaGateway()
    gw.start()
    print(f"PLC 閘道（OPC UA Server）：{gw.endpoint}\n")
    try:
        print("1. 正常抓取（寫 PickRequest → PLC 回 PickDone）  →", pick(gw))

        gw.plant.door_closed = False
        print("2. 安全門開啟                                 →", pick(gw))
        gw.plant.door_closed = True
        settle()

        print("3. 動作中安全門被打開                         →",
              pick(gw, during=lambda: setattr(gw.plant, "door_closed", False)))
        gw.plant.door_closed = True
        settle()

        pmc = OpcUaPMC(gw.endpoint)
        print("4. 寫入權限（Client 只能寫 PickRequest、Heartbeat）")
        for name, value in [("Alarm", False), ("PickDone", True), ("DoorClosed", True), ("PickRequest", False)]:
            print(f"     寫入 Robot.{name:<12} → {pmc.try_write(name, value)}")
        pmc.close()

        print("5. 動作中 Jetson 程式卡死（心跳停止）")
        gw.events.clear()
        gw.plant.pick_duration_s = 2.0   # 動作時間長於心跳逾時 0.5 s
        done_before = gw.plant.picks_completed
        pmc = OpcUaPMC(gw.endpoint)
        settle()
        pmc.write_short(R_COMMAND, CMD_PICK_REQ)
        while not pmc.read_short(R_STATUS) & ST_PICK_ACCEPTED:
            time.sleep(0.01)
        print("     PLC 已接受抓取請求，手臂開始動作 → Jetson 停止送心跳")
        pmc.stop_heartbeat()
        time.sleep(1.0)
        for e in gw.events:
            print(f"     PLC 事件：{e}")
        print(f"     手臂是否完成動作：{'是' if gw.plant.picks_completed > done_before else '否（已由 PLC 中止）'}")
        pmc.client.disconnect()
    finally:
        gw.stop()


if __name__ == "__main__":
    main()
