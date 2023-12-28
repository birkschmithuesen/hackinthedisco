import matplotlib.pyplot as plt
from pythonosc import dispatcher, osc_server, udp_client
from typing import List, Any
import numpy as np
from matplotlib.animation import FuncAnimation
from threading import Thread
import logging

logFormat = "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]: %(message)s"
timeFormat = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(format=logFormat, datefmt=timeFormat, level=logging.INFO)


plt.style.use("dark_background")

# taunus_ip = "130.149.23.24"
# local_ip = "130.149.23.218"
local_ip = "127.0.0.1"


local_port = 10009


dispatcher = dispatcher.Dispatcher()
N_CHANNELS = 20
channel_positions = np.zeros((4, N_CHANNELS))


def x_handler(address: str, fixed_argument, *osc_arguments):
    channel_positions[0, fixed_argument[0]] = osc_arguments[0]


def y_handler(address: str, fixed_argument, *osc_arguments):
    channel_positions[1, fixed_argument[0]] = osc_arguments[0]


def intensity_handler(address: str, fixed_argument, *osc_arguments):
    channel_positions[2, fixed_argument[0]] = osc_arguments[0]


def color_handler(address: str, fixed_argument, *osc_arguments):
    print(osc_arguments[0])

    channel_positions[3, fixed_argument[0]] = osc_arguments[0]


def plot(*args):
    ax.clear()

    plt.scatter(
        channel_positions[0],
        channel_positions[1],
        alpha=np.clip(channel_positions[2], 0, 1),
        s=80,
    )
    plt.grid()
    ax.set_xlim([0, 17])
    ax.set_ylim([0, 10])

    for tap, (x, y, intensity, color) in enumerate(zip(*channel_positions)):
        if (intensity) > 0 and 0 <= x <= 17 and 0 <= y <= 10:
            plt.text(x, y + 0.1, str(tap + 1), alpha=0.4)


def default_handler(address, *args):
    # pass
    logging.info(f"default: {address}: {args}")


send_path = "/light{}/{}"


for i in range(N_CHANNELS):
    dispatcher.map(send_path.format(i + 1, "xpos"), x_handler, i)
    dispatcher.map(send_path.format(i + 1, "ypos"), y_handler, i)
    dispatcher.map(send_path.format(i + 1, "color"), color_handler, i)
    dispatcher.map(send_path.format(i + 1, "intensity"), intensity_handler, i)

dispatcher.set_default_handler(default_handler)


fig, ax = plt.subplots()
ani = FuncAnimation(fig, plot, interval=int(1000 / 10), save_count=10)


server = osc_server.BlockingOSCUDPServer((local_ip, local_port), dispatcher)
# osc_debug_client = udp_client.SimpleUDPClient(taunus_ip, taunus_debug_port)

Thread(target=server.serve_forever).start()

plt.show()
server.shutdown()
