import math

from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server, udp_client
from threading import Thread

from time import sleep, time
import numpy as np
from dataclasses import dataclass, field
from enum import Enum

update_rate = 1 / 20
check_trackers_up_to = 15
game_dim_x = 17.0  # in meters
game_dim_y = 10.0  # in meters
pedal_height = 3.5  # in meters
win_threshold = 3  # number of points to win


positions = []


class GameMode(Enum):
    WAIT = 0
    RUNNING = 1
    GAME_END = 2


@dataclass
class pos:
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other):
        return pos(self.x + other.x, self.y + other.y)


@dataclass
class GameState:
    p1: pos
    p2: pos
    ball: pos
    ball_speed: pos
    mode: GameMode
    ball_color: int = 0
    p1_points: int = 0
    p2_points: int = 0


state = GameState(
    p1=pos(1, 5),
    p2=pos(16, 5),
    ball=pos(game_dim_x / 2.0, game_dim_y / 2.0),
    ball_speed=pos(1, 0.1),
    mode=GameMode.RUNNING,
)

default_ball_speed = 0.2
player1_lights = [0, 1, 2, 3, 4]
player2_lights = [15, 16, 17, 18, 19]
ball_lights = [6, 7, 8, 11, 12, 13]

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
    line_r = pedal_height / 2
    y = min(max(p.y, line_r), (game_dim_y - line_r))
    y = y - line_r
    delta_y = pedal_height / (len(lights) - 1)
    for i in lights:
        client.send_message(send_path.format(i + 1, "ypos"), y)
        y += delta_y


def plot_ball(client: udp_client.SimpleUDPClient):
    for i in ball_lights:
        client.send_message(send_path.format(i + 1, "xpos"), state.ball.x)
        client.send_message(send_path.format(i + 1, "ypos"), state.ball.y)


def send_game_state(client: udp_client.SimpleUDPClient):
    # send ball position to 2 leds
    # send left line to one half
    plot_line(client, state.p1, player1_lights)
    plot_line(client, state.p2, player2_lights)
    plot_ball(client)
    # send right line to other half
    pass


def send_initial_state(client: udp_client.SimpleUDPClient):
    for i in player1_lights:
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)
        client.send_message(send_path.format(i + 1, "xpos"), state.p1.x)
    for i in player2_lights:
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)
        client.send_message(send_path.format(i + 1, "xpos"), state.p2.x)
    for i in ball_lights:
        client.send_message(send_path.format(i + 1, "intensity"), 0.8)


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


def update_player_positions():
    player1_position = get_player_position(0, state.p1.x + 2)
    if player1_position != -1:
        state.p1.y = player1_position
    player2_position = get_player_position(state.p2.x - 2, game_dim_x)
    if player2_position != -1:
        state.p2.y = player2_position
    # calculate ball position here


def send_thread():
    client = udp_client.SimpleUDPClient(send_ip, send_port)
    send_initial_state(client=client)
    while thread_runs:
        update_player_positions()
        update_game_state()
        send_game_state(client)

        sleep(update_rate)


def ball_reset():
    # Reset the ball position to center and random direction
    print(f"P1 {state.p1_points}, P2 {state.p2_points}")
    state.ball.x = game_dim_x / 2.0
    state.ball.y = game_dim_y / 2.0
    state.ball_color = 0.0

    # Limit angle to the side of players to prevent boring vertical bouncing
    random_angle = np.random.rand() * np.deg2rad(90) + np.deg2rad(90)
    if (np.random.choice(a=[False, True])):
        # Randomly decide player direction
        random_angle += np.pi

    state.ball_speed.x = default_ball_speed * np.sin(random_angle)
    state.ball_speed.y = default_ball_speed * np.cos(random_angle)


def ball_x_bounce():
    # Ball caught and bounce
    state.ball_speed.x *= -1
    state.ball_color += 1/20
    if state.ball_color >= 1:
        state.ball_color = 0.0


def ball_y_bounce():
    state.ball_speed.y *= -1
    state.ball_color += 1/20
    if state.ball_color >= 1:
        state.ball_color = 0.0


def update_game_state():
    # Update ball positions
    state.ball += state.ball_speed

    # Handle vertical reflections
    if state.ball.y <= 0 or state.ball.y >= game_dim_y:
        ball_y_bounce()

    # Check if player 1 catched the ball
    if state.ball.x <= state.p1.x:
        if state.ball.y <= (state.p1.y + pedal_height / 2) and state.ball.y >= (
            state.p1.y - pedal_height / 2
        ):
            ball_x_bounce()
        else:
            # Ball missed respawn ball
            state.p2_points += 1
            ball_reset()

        # Check if player 2 catched the ball
    elif state.ball.x >= state.p2.x:
        if state.ball.y <= (state.p2.y + pedal_height / 2) and state.ball.y >= (
            state.p2.y - pedal_height / 2
        ):
            ball_x_bounce()
        else:
            # Ball missed respawn ball
            state.p1_points += 1
            ball_reset()


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
