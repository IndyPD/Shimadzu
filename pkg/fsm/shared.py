from enum import Enum


class OpMode(Enum):
    SIMULATION = 0  # Simulation
    REAL_ROBOT = 1  # Real robot


class CollisionMode(Enum):
    KEEP_PAUSE = 0
    SLEEP_RESET = 1
    STOP_PROGRAM = 2
