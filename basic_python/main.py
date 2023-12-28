import math

from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client
from threading import Thread

import numpy as np

from time import sleep
from dataclasses import dataclass, field

update_rate = 1 / 10
check_trackers_up_to = 15
game_dim_x = 17.0
game_dim_y = 10.0
line_width = 2


positions = []


@dataclass
class pos:
    x: float = 0.0
    y: float = 0.0


@dataclass
class GameState:
    p1: pos
    p2: pos
    ball: pos


state = GameState(p1=pos(1, 5), p2=pos(16, 5), ball=pos(game_dim_x / 2, game_dim_y / 2))
player1_lights = [0, 1, 2, 3, 4]
player2_lights = [15, 16, 17, 18, 19]

listen_ip = "0.0.0.0"
listen_port = 10000
send_ip = "127.0.0.1"
# send_ip = "192.168.0.232"
send_port = 10009

n_trackers = 15
n_lights = 20

recv_path = "/tracker_{}:vals:{}"
send_path = "/light{}/{}"

thread_runs = True


def handle_x(unused_addr, args, x_pos, *mehr_args):
    positions[args[0]].x = x_pos


def handle_y(unused_addr, args, y_pos, *mehr_args):
    positions[args[0]].y = y_pos


def handle_speed(unused_addr, args, speed, *mehr_args):
    # lmao was soll ich denn damit?
    pass


def plot_line(client, p: pos, lights):
    line_r = line_width / 2
    y = min(max(p.y, line_r), (game_dim_y - line_r))
    y = y - line_r
    delta_y = line_width / (len(lights) - 1)
    for i in lights:
        client.send_message(send_path.format(i + 1, "ypos"), y)
        y += delta_y


def send_game_state(client: udp_client.SimpleUDPClient):
    # send ball position to 2 leds
    # send left line to one half
    plot_line(client, state.p1, player1_lights)
    plot_line(client, state.p2, player2_lights)

    # send right line to other half
    pass


def send_initial_state(client: udp_client.SimpleUDPClient):
    for i in player1_lights:
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)
        client.send_message(send_path.format(i + 1, "xpos"), state.p1.x)
    for i in player2_lights:
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)
        client.send_message(send_path.format(i + 1, "xpos"), state.p2.x)


def send_all(client: udp_client.SimpleUDPClient, x, y, z):
    for i in range(n_lights):
        print(x, y)
        client.send_message(send_path.format(i + 1, "xpos"), x)
        client.send_message(send_path.format(i + 1, "ypos"), y)
        client.send_message(send_path.format(i + 1, "height"), z)
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)


def get_player_position(x_lower, x_upper):
    for i, p in enumerate(positions):
        if not (p.x == 0 and p.y == 0) and x_lower <= p.x <= x_upper:
            return p.y

    return -1


def update_game_state():
    player1_position = get_player_position(0, 2)
    if player1_position != -1:
        state.p1.y = player1_position
    player2_position = get_player_position(15, 17)
    if player2_position != -1:
        state.p2.y = player2_position
    # calculate ball position here


def send_thread():
    client = udp_client.SimpleUDPClient(send_ip, send_port)
    send_initial_state(client=client)
    while thread_runs:
        update_game_state()
        send_game_state(client)

        sleep(update_rate)


if __name__ == "__main__":
    # Init array of tracker positions
    for i in range(1, check_trackers_up_to + 1):
        positions.append(pos())
    print(positions)

    dispatcher = Dispatcher()
    for i in range(n_trackers):
        dispatcher.map(recv_path.format(i + 1, "pos_x"), handle_x, i)
        dispatcher.map(recv_path.format(i + 1, "pos_y"), handle_y, i)
        dispatcher.map(recv_path.format(i + 1, "speed"), handle_speed, i)

    send_thread = Thread(target=send_thread).start()

    server = osc_server.ThreadingOSCUDPServer((listen_ip, listen_port), dispatcher)
    print("Serving on {}".format(server.server_address))
    server.serve_forever()
    thread_runs = False
