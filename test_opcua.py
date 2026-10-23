"""OPC UA 整合測試（需要 asyncua）：python -m unittest test_opcua -v"""
import threading
import time
import unittest

from controller import run_pick_cycle
from opcua_gateway import OpcUaGateway
from opcua_pmc import OpcUaPMC
from pmc import CMD_PICK_REQ, R_COMMAND, R_STATUS, ST_PICK_ACCEPTED
from vision import SimulatedVision

ENDPOINT = "opc.tcp://127.0.0.1:48410/robot/"   # 避開示範用的 4840


class OpcUaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = OpcUaGateway(endpoint=ENDPOINT)
        cls.gw.start()

    @classmethod
    def tearDownClass(cls):
        cls.gw.stop()

    def setUp(self):
        p = self.gw.plant
        p.door_closed, p.alarm, p.pick_duration_s = True, False, 0.3
        self.pmc = OpcUaPMC(ENDPOINT)
        time.sleep(0.1)

    def tearDown(self):
        self.pmc.close()

    def cycle(self):
        return run_pick_cycle(self.pmc, SimulatedVision(), accept_timeout_s=1.0, done_timeout_s=2.0)

    def test_pick_done_over_opcua(self):
        before = self.gw.plant.picks_completed
        self.assertEqual(self.cycle(), "PICK_DONE")
        self.assertEqual(self.gw.plant.picks_completed, before + 1)

    def test_door_open_blocked(self):
        self.gw.plant.door_closed = False
        time.sleep(0.05)
        self.assertEqual(self.cycle(), "BLOCKED")

    def test_door_opens_during_motion_faults(self):
        threading.Timer(0.1, lambda: setattr(self.gw.plant, "door_closed", False)).start()
        self.assertEqual(self.cycle(), "FAULT")

    def test_status_nodes_are_read_only(self):
        for name in ("Alarm", "PickDone", "DoorClosed", "Ready", "Fault"):
            self.assertEqual(self.pmc.try_write(name, False), "BadUserAccessDenied", name)
        self.assertEqual(self.pmc.try_write("PickRequest", False), "OK")

    def test_heartbeat_loss_aborts_motion(self):
        self.gw.plant.pick_duration_s = 2.0
        before = self.gw.plant.picks_completed
        self.pmc.write_short(R_COMMAND, CMD_PICK_REQ)
        deadline = time.monotonic() + 1.0
        while not self.pmc.read_short(R_STATUS) & ST_PICK_ACCEPTED:
            self.assertLess(time.monotonic(), deadline, "pick not accepted")
            time.sleep(0.01)
        self.gw.events.clear()
        self.pmc.stop_heartbeat()
        time.sleep(1.0)
        self.assertIn("PLC aborted motion → Fault", self.gw.events)
        self.assertEqual(self.gw.plant.picks_completed, before)
        # PLC 已取消失聯 Client 的請求，恢復連線後不會自動動作
        self.assertEqual(self.pmc.read_short(R_STATUS) & ST_PICK_ACCEPTED, 0)


if __name__ == "__main__":
    unittest.main()
