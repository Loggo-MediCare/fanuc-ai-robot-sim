"""第二堂 檔案 B：模擬 NVIDIA Jetson 上的 Python 程式（OPC UA Client）。

先在另一個終端機執行 python lesson/plc_server.py，再執行：
python lesson/jetson_client.py
"""
import asyncio

from asyncua import Client

URL = "opc.tcp://127.0.0.1:4840/robot/"
URI = "urn:robot:training"


async def main():
    async with Client(url=URL) as client:
        idx = await client.get_namespace_index(URI)
        robot = await client.nodes.objects.get_child([f"{idx}:Robot"])
        ready_node = await robot.get_child([f"{idx}:Ready"])
        alarm_node = await robot.get_child([f"{idx}:Alarm"])

        ready = await ready_node.read_value()
        alarm = await alarm_node.read_value()
        print("Robot Ready:", ready)
        print("Robot Alarm:", alarm)

        if ready and not alarm:
            print("AI may propose a pick request")
        else:
            print("Do not request robot movement")


asyncio.run(main())
