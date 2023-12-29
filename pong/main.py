import math

from dataclasses import dataclass, field
from enum import Enum
from threading import Thread
from time import sleep, time

import numpy as np
from pythonosc import osc_server, udp_client
from pythonosc.dispatcher import Dispatcher


update_rate = 1 / 30  # in 1/frequency (Hz)

n_trackers = 15
n_lights = 20

game_dim_x = 17.0  # in meters
y_dim_offset = (
    0  # used if the playing field is offset in relation to the coordinate system
)
game_dim_y = 6.5 - y_dim_offset  # in meters
paddle_height = 2  # in meters
paddle_offset = 2  # x-distance from paddle to edge of playing field

win_threshold = 4  # number of points to win


default_ball_speed = 0.05  # relative to update_rate
ball_opening_angle = 120.0  # start angle after ball reset to player side

# lists of lights, these are the indices of the corresponding ids in the OSC paths
player1_lights = [0, 1, 2, 3, 4]
player2_lights = [15, 16, 17, 18, 19]
ball_lights = [6, 7, 8, 11, 12, 13]
player_1_score_lights = [5, 9]
player_2_score_lights = [10, 14]
all_lights = (
    ball_lights
    + player1_lights
    + player2_lights
    + player_1_score_lights
    + player_2_score_lights
)

# OSC listener for tracker data
listen_ip = "0.0.0.0"
listen_port = 10000

# OSC client for controlling lights
send_ip = "127.0.0.1"  # local debug
# send_ip = "192.168.0.232"   # production server
send_port = 12344

# OSC Triggers are sent to this address for triggering audio samples
audio_send_ip = "192.168.0.230"
audio_send_port = 1000

# OSC paths for sending and receiving
recv_path = "/tracker_{}:vals:{}"
send_path = "/light{}/{}"

# boolean for stopping the game thread
thread_runs = True

# holds all tracker positions
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
    ball_color: float = 0  # Color value of the ball, mapping between the number and the actual color is beyond the scope of this work
    p1_points: int = 0
    p2_points: int = 0
    ball_rotation: float = (
        0.0  # the ball lights get rotated by this continuously incrementing value
    )
    time_game_end: float = 0.0


client = udp_client.SimpleUDPClient(send_ip, send_port)
audio_client = udp_client.SimpleUDPClient(audio_send_ip, audio_send_port)


# OSC Input Handlers
def handle_x(unused_addr, args, x_pos, *mehr_args):
    positions[args[0]].x = x_pos


def handle_y(unused_addr, args, y_pos, *mehr_args):
    positions[args[0]].y = y_pos - y_dim_offset


def handle_speed(unused_addr, args, speed, *mehr_args):
    # lmao was soll ich denn damit?
    pass


# OSC Send Functions
def set_intensity(lights: list, intensity: float):
    if type(lights) == int:
        lights = [lights]
    for l in lights:
        client.send_message(send_path.format(l + 1, "intensity"), intensity)


def set_xpos(lights: list, xpos: float):
    if type(lights) == int:
        lights = [lights]

    for l in lights:
        client.send_message(send_path.format(l + 1, "xpos"), xpos)


def set_ypos(lights: list, ypos: float):
    if type(lights) == int:
        lights = [lights]

    for l in lights:
        client.send_message(send_path.format(l + 1, "ypos"), ypos + y_dim_offset)


def set_ypos_arr(lights: list, ypos: float):
    for l, y in zip(lights, ypos):
        client.send_message(send_path.format(l + 1, "ypos"), y + y_dim_offset)


def set_xpos_arr(lights: list, xpos: float):
    for l, x in zip(lights, xpos):
        client.send_message(send_path.format(l + 1, "xpos"), x)


def set_color(lights: list, color: float):
    if type(lights) == int:
        lights = [lights]
    for l in lights:
        client.send_message(send_path.format(l + 1, "color"), color)


def send_sound(path):
    try:
        audio_client.send_message(path, True)
        audio_client.send_message(path, False)
    except Exception:
        print("can't send audio osc well shit")


# Higher Level Draw Functions
def draw_line(p: pos, lights):
    y = p.y - paddle_height / 2
    delta_y = paddle_height / (len(lights) - 1)
    for i in lights:
        set_ypos(i, y)
        set_xpos(i, p.x)
        y += delta_y


# lights are placed in a circular shape around p
def draw_ball(p: pos, lights, color, radius=1, rotation_speed=1):
    x = np.ones(len(lights)) * radius

    state.ball_rotation += rotation_speed
    theta = np.linspace(0, 2 * np.pi, len(lights)) + state.ball_rotation
    x_new = np.cos(theta) * x
    y_new = np.sin(theta) * x

    set_ypos_arr(lights, y_new + p.y)
    set_xpos_arr(lights, x_new + p.x)
    set_color(lights, color)


def draw_score():
    step_size = game_dim_x / 2 / win_threshold
    for score_lights, x in [
        (player_1_score_lights, step_size * state.p1_points),
        (player_2_score_lights, game_dim_x - step_size * state.p2_points),
    ]:
        for light, y in zip(score_lights, [0, game_dim_y]):
            set_ypos(light, y)
            set_xpos(light, x)


# call the relevant draw functions for the current game mode
def send_game_state():
    if state.mode == GameMode.RUNNING:
        draw_line(state.p1, player1_lights)
        draw_line(state.p2, player2_lights)

        center_x = game_dim_x / 2
        mod = (center_x - np.abs(center_x - state.ball.x)) / center_x
        draw_ball(
            state.ball, ball_lights, (state.ball_color + mod * 0.3) % 1, mod, mod * 0.4
        )
        draw_score()

    elif state.mode == GameMode.GAME_END:
        winner = state.p1 if state.p1_points >= win_threshold else state.p2
        winner_points = (
            state.p1_points if state.p1_points >= win_threshold else state.p2_points
        )
        loser_points = (
            state.p2_points if state.p1_points >= win_threshold else state.p1_points
        )
        n_winner_lights = int(
            round(winner_points / (winner_points + loser_points) * n_lights)
        )
        draw_ball(
            winner,
            all_lights[:n_winner_lights],
            (state.ball_rotation % 100) / 100,
            2,
            2.1,
        )
        set_intensity(all_lights[n_winner_lights:], 0)


# reset all lights to an off position (to ensure there is movement at the start of the program)
def initialize_lights():
    set_intensity(all_lights, 0)
    set_color(all_lights, 0)
    set_xpos(all_lights, game_dim_x / 2)
    set_ypos(all_lights, game_dim_y / 2)


# set initial positions and colors for
def send_initial_state():
    set_intensity(all_lights, 0.8)
    set_xpos(player1_lights, state.p1.x)
    set_xpos(player2_lights, state.p2.x)
    set_color(player_1_score_lights + player_2_score_lights, 0.2)
    set_color(player1_lights + player2_lights, 0.3)


# return y of the first tracker position in the given x range
def get_player_position(x_lower, x_upper):
    line_r = paddle_height / 2
    for i, p in enumerate(positions):
        if not (p.x == 0 and p.y == 0) and x_lower <= p.x <= x_upper:
            return min(max(p.y, line_r), (game_dim_y - line_r))

    return -1


def update_player_positions():
    player1_position = get_player_position(-np.inf, state.p1.x + 4)
    if player1_position != -1:
        state.p1.y = player1_position
    player2_position = get_player_position(state.p2.x - 4, np.inf)
    if player2_position != -1:
        state.p2.y = player2_position


# this thread handles updating the games state and sending the update to the lights
def send_thread():
    send_initial_state()
    while thread_runs:
        update_player_positions()
        update_game_state()
        send_game_state()

        sleep(update_rate)


# set ball speed to a random angle, that is also limited to prevent boring vertical bouncing
def setup_initial_ball_speed():
    random_angle = np.random.rand() * np.deg2rad(ball_opening_angle) - np.deg2rad(
        90 + ball_opening_angle / 2
    )
    if np.random.choice(a=[False, True]):
        # Randomly decide player direction
        random_angle += np.pi

    return pos(
        default_ball_speed * np.sin(random_angle),
        default_ball_speed * np.cos(random_angle),
    )


# Reset the ball position to center and random direction. also handle game winning plays
def ball_reset():
    if state.p1_points >= win_threshold or state.p2_points >= win_threshold:
        state.mode = GameMode.GAME_END
        state.time_game_end = time()
        send_sound("/win")
    print(f"P1 {state.p1_points}, P2 {state.p2_points}")
    state.ball.x = game_dim_x / 2.0
    state.ball.y = game_dim_y / 2.0
    state.ball_color = 0.0
    send_sound("/score")
    state.ball_speed = setup_initial_ball_speed()


# Ball caught and bounce
def ball_x_bounce():
    state.ball_speed.x *= -1
    state.ball_color = (state.ball_color + 1 / 20) % 1.0
    send_sound("/bounce")


# ball bounce of walls
def ball_y_bounce():
    state.ball_speed.y *= -1
    state.ball_color = (state.ball_color + 1 / 20) % 1.0
    send_sound("/wallbounce")


# main game logic
def update_game_state():
    if state.mode == GameMode.RUNNING:
        # Update ball positions
        state.ball += state.ball_speed

        # Handle vertical reflections
        if state.ball.y <= 0 or state.ball.y >= game_dim_y:
            ball_y_bounce()

        # Check if player 1 catched the ball
        if state.ball.x <= state.p1.x:
            if state.ball.y <= (state.p1.y + paddle_height / 2) and state.ball.y >= (
                state.p1.y - paddle_height / 2
            ):
                ball_x_bounce()
            else:
                # Ball missed respawn ball
                state.p2_points += 1
                ball_reset()

            # Check if player 2 catched the ball
        elif state.ball.x >= state.p2.x:
            if state.ball.y <= (state.p2.y + paddle_height / 2) and state.ball.y >= (
                state.p2.y - paddle_height / 2
            ):
                ball_x_bounce()
            else:
                # Ball missed respawn ball
                state.p1_points += 1
                ball_reset()
    elif state.mode == GameMode.GAME_END:
        if state.time_game_end + 6 <= time():
            state.mode = GameMode.RUNNING
            send_initial_state()
            state.p1_points, state.p2_points = (0, 0)


if __name__ == "__main__":
    # Init array of tracker positions
    initialize_lights()
    for i in range(1, n_trackers + 1):
        positions.append(pos())

    state = GameState(
        p1=pos(paddle_offset, game_dim_y / 2),
        p2=pos(game_dim_x - paddle_offset, game_dim_y / 2),
        ball=pos(game_dim_x / 2.0, game_dim_y / 2.0),
        ball_speed=setup_initial_ball_speed(),
        mode=GameMode.RUNNING,
    )

    # subscribe OSC listener to trackers
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
