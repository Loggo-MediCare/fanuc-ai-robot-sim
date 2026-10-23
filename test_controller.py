"""python -m unittest -v"""
import unittest

from demo import run
from vision import Detection


class PickCycleTests(unittest.TestCase):
    def test_normal_pick(self):
        self.assertEqual(run("normal"), "PICK_DONE")

    def test_no_object_waits(self):
        self.assertEqual(run("no object", detection=Detection(False)), "WAIT")

    def test_low_confidence_waits(self):
        self.assertEqual(run("low conf", detection=Detection(True, "BOX", 0.7)), "WAIT")

    def test_door_open_blocked(self):
        self.assertEqual(run("door", setup=lambda p, m: setattr(p, "door_closed", False)), "BLOCKED")

    def test_alarm_blocked(self):
        self.assertEqual(run("alarm", setup=lambda p, m: setattr(p, "alarm", True)), "BLOCKED")

    def test_door_opens_during_motion_faults(self):
        result = run("door mid", during=lambda p, m: setattr(p, "door_closed", False))
        self.assertEqual(result, "FAULT")

    def test_comm_loss_during_motion(self):
        result = run("comm loss", during=lambda p, m: setattr(m, "connected", False))
        self.assertTrue(result.startswith("COMM_ERROR"), result)


if __name__ == "__main__":
    unittest.main()
