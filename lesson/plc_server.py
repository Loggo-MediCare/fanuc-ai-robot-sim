"""第二堂 檔案 A：模擬一台提供機械手臂狀態的 PLC（OPC UA Server）。

python lesson/plc_server.py
"""
import asyncio

from asyncua import Server

URI = "urn:robot:training"


async def main():
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://127.0.0.1:4840/robot/")

    idx = await server.register_namespace(URI)
    robot = await server.nodes.objects.add_object(idx, "Robot")
    await robot.add_variable(idx, "Ready", True)
    await robot.add_variable(idx, "Alarm", False)
    # 第一堂刻意只開放讀取，沒有呼叫 set_writable()，Client 不能寫入

    print("Simulated PLC server running")
    async with server:
        while True:
            await asyncio.sleep(1)


asyncio.run(main())
