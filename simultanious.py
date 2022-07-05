import numpy as np
import casadi as ca
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from ode import *

from math import *

T = 100
N = 1000
h = T / N
grav_const = 0.1

body_masses = (0.05, 1000000)
n_body = 2
dimension = 2
thrust_max = 0.3

# orbit
orbit = 10
cost_function_rescale_factor = 0.759835685652


def rk4step_u(ode, h, x, u):
    """ one step of explicit Runge-Kutta scheme of order four (RK4)

    parameters:
    ode -- odinary differential equations (your system dynamics)
    h -- step of integration
    x -- states
    u -- controls
    """
    k1 = ode(x, u)
    k2 = ode(x + h * 0.5 * k1, u)
    k3 = ode(x + h * 0.5 * k2, u)
    k4 = ode(x + h * k3, u)
    return x + ((h / 6) * (k1 + 2 * k2 + 2 * k3 + k4))


def ode_general(z: np.ndarray, controls: np.ndarray, body_masses: tuple,
        n_body: int, dimension: int) -> np.ndarray:
    '''
        The right hand side of
            z' = f(z, u)

        where u are controls (alpha, theta, r) for body_1 ie.
        (alpha, theta) specifies the rocket direction and r the thrust.
    '''
    N = 2 * dimension * n_body
    rhs_velocity = []
    rhs_acceleration = []

    for i in range(0, n_body):

        body_velocity_i = z[n_body * dimension + (i * dimension):
            n_body * dimension + ((i + 1) * dimension)]

        rhs_velocity = ca.vertcat(rhs_velocity, body_velocity_i)

        rhs_acceleration_i = 0

        for j in range(0, n_body):
            if i == j:
                continue

            body_position_i = z[(i * dimension): ((i + 1) * dimension)]
            body_position_j = z[(j * dimension): ((j + 1) * dimension)]
            rhs_acceleration_i += (grav_const * body_masses[j]
                             / (ca.norm_2(body_position_i - body_position_j) ** 3)
                             * (body_position_j - body_position_i))

        if i == 0:
            r = controls[0]
            theta = controls[1]
            rhs_acceleration_i[0] += r * ca.cos(theta)
            rhs_acceleration_i[1] += r * ca.sin(theta)

        rhs_acceleration = ca.vertcat(rhs_acceleration, rhs_acceleration_i)

    return ca.vertcat(rhs_velocity, rhs_acceleration)


def ode(z, controls):
    return ode_general(z, controls, body_masses,
                       dimension, n_body)


dynamics = ca.Function('d', [z, controls, step_h], [rk4step_u(
    ode, step_h, z, controls
)])


x = ca.SX.sym('x', (N + 1) * 2 * n_body * dimension)
u = ca.SX.sym('u', 2 * N)

# 1. Opt.
# x_0 --- x_1 ---- x_2 --- ... --- x_n
# u_0 --- u_1 ---- u_2 --- ... --- u_n

# 2. Simul.
# x_0 --- x_1 ---- x_2 --- ... --- x_n
# u_0 --- u_1 ---- u_2 --- ... --- u_n
#      ^
# x_0 = x_00 -- x_01 -- x_02 -- x_03 = x_1
# u_0 --------------------------------- u_1
# u_0 = u_00    u_01    u02    u03  =   u_1
#
#
# x(t_k) ------------------------------ x(t_k+1)


def cost_function_continous(x_current, u_current):
    dist = ca.norm_2(x[0: dimension] - x[dimension: 2 * dimension]) / cost_function_rescale_factor
    return orbit * (1 - dist / orbit) / dist + (dist / orbit) ** 3


def cost_function_integral_discrete(x, u):
    # todo: simpson auf cost function anwenden
    #return step_size / 6 * (cost_function_continous(x_i, u_i) + 4 * cost_function_continous)


# def int_simpson(function, a: float, b: float) -> float:
#     '''
#         Uses the simpson-quadrature to approximate the integral of function
#         from a to b.
#     '''
#         return (b - a) / 6 * (function(a) + 4 * function((a + b) / 2)
#                               + function(b))


# build nlp

constraints = ca.vertcat(controls[::2], controls[1::2])
lbg = [-thrust_max] * N + [-pi] * N
ubg = [thrust_max] * N + [pi] * N

nlp = {'x': ca.vertcat(x, u), 'f': cost_function_integral_discrete(x, u),
       'g': constraints}

solver = ca.nlpsol('solver', 'ipopt', nlp)

# Solve the NLP
res = solver(
    x0 = [10, pi] * 5 + [0] * (2 * N_T - 10),    # solution guess
    lbx = -ca.inf,          # lower bound on x
    ubx = ca.inf,           # upper bound on x
    lbg = lbg,                # lower bound on g
    ubg = ubg,                # upper bound on g
)

# simpson implementieren (michael)
# cost function implmentieren
# initial value
# preamble

# n-body problem beschreiben (herleitung)
# ocp diskretisieren (nick)
# florian email
# gibhub
# overleaf
