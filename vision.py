"""模擬 AI 辨識。日後換成 NVIDIA Jetson / Isaac ROS 的推論結果。"""
from dataclasses import dataclass


@dataclass
class Detection:
    detected: bool
    label: str = ""
    confidence: float = 0.0


class SimulatedVision:
    def __init__(self, detection=None):
        self.detection = detection or Detection(True, "BOX", 0.95)

    def detect(self) -> Detection:
        return self.detection
