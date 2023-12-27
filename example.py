from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
import asyncio

"""
pip install python-osc
"""

TRACKER_X = "/tracker_1:vals:pos_x"
TRACKER_Y = "/tracker_1:vals:pos_y"

values = {
    TRACKER_X: 1.0,
    TRACKER_Y: 1.0,
}


def update_handler(address, *args):
    values[str(address)] = args[0]


dispatcher = Dispatcher()
# dispatcher.map("*", update_handler)
dispatcher.set_default_handler(update_handler)

client = SimpleUDPClient("192.168.0.232", 1339)

ip = "0.0.0.0"
port = 10000


def send():
    for i in range(1, 21):
        client.send_message(f"/light{i}/xpos", values[TRACKER_X])
        client.send_message(f"/light{i}/ypos", values[TRACKER_Y])
        client.send_message(f"/light{i}/intensity", 1.0)
        client.send_message(f"/light{i}/color", 0.5)
        client.send_message(f"/light{i}/frost", 1)
        client.send_message(f"/light{i}/height", 0.0)


async def loop():
    while True:
        print(f"X: {values[TRACKER_X]}\tY: {values[TRACKER_Y]}")
        send()
        await asyncio.sleep(0.1)


async def init_main():
    # noinspection PyTypeChecker
    server = AsyncIOOSCUDPServer((ip, port), dispatcher, asyncio.get_event_loop())
    transport, protocol = await server.create_serve_endpoint()  # Create datagram endpoint and start serving

    await loop()  # Enter main loop of program

    transport.close()  # Clean up serve endpoint


if __name__ == '__main__':
    asyncio.run(init_main())
