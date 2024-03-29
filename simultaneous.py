import numpy as np
import casadi as ca
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from math import pi, sin, cos, sqrt

# Time horizon
T = 700

# Number of discrete time points (N + 1 in the report)
N = 176

# Stepsize
h = T / (N - 1)

# Gravitational constant
grav_const = 0.0008

# masses of the simulated bodies
sun_mass = 1000000
rocket_mass = 0.05

# rocket is always body_0, planet is always body_-1
body_masses = (rocket_mass, sun_mass)

# number of bodies in orbit
n_body = 1

# dimension to simulate in
dimension = 2

# maximum thrust of the rocket
thrust_max = 0.0003

# radius of the planet
surface = 100

# initial position and velocity of orbiting body
v_initial = 2.412

x_0_bar = [surface * 1.1, 0, v_initial * cos(pi/4), v_initial * sin(pi/4)]

# desired circular orbit height
orbit = 190


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


def ode_general(z, controls, body_masses: tuple, n_body: int, dimension: int):
    '''
        The right hand side of
            z' = f(z, u)

        where u are controls (alpha, theta, r) for body_1 ie.
        (alpha, theta) specifies the rocket direction and r the thrust.
    '''
    rhs_velocity = []
    rhs_acceleration = []

    # iterate on all movable bodies around the planet
    for i in range(0, n_body):

        body_velocity_i = z[n_body * dimension + (i * dimension):
                            n_body * dimension + ((i + 1) * dimension)]

        rhs_velocity = ca.vertcat(rhs_velocity, body_velocity_i)

        rhs_acceleration_i = 0

        # calculate the force of body_j on body_i (in case there is more
        # than one body in orbit)
        for j in range(0, n_body):
            # no force of a body on itself
            if i == j:
                continue

            body_position_i = z[(i * dimension): ((i + 1) * dimension)]
            body_position_j = z[(j * dimension): ((j + 1) * dimension)]

            rhs_acceleration_i += (grav_const * body_masses[j]
                                   / (ca.norm_2(body_position_i
                                                - body_position_j) ** 3)
                                   * (body_position_j - body_position_i))

        # calculate the force of the planet on body_i
        body_position_i = z[(i * dimension): ((i + 1) * dimension)]
        planet_position = [0] * dimension

        rhs_acceleration_i += (grav_const * body_masses[-1]
                               / (ca.norm_2(body_position_i
                                            - planet_position) ** 3)
                               * (planet_position - body_position_i))

        # body_0 is the actuated rocket, add control force
        if i == 0:
            r = controls[0]
            phi = controls[1]
            rhs_acceleration_i[0] += r * ca.cos(phi) / body_masses[i]
            rhs_acceleration_i[1] += r * ca.sin(phi) / body_masses[i]

        rhs_acceleration = ca.vertcat(rhs_acceleration, rhs_acceleration_i)

    return ca.vertcat(rhs_velocity, rhs_acceleration)


def ode(z, controls):
    # fix the body data defined above
    return ode_general(z, controls, body_masses, n_body, dimension)


state_dimension = 2 * n_body * dimension


x_single = ca.SX.sym('x', state_dimension)
u_single = ca.SX.sym('u', dimension)
step_h = ca.SX.sym('h')


# define the dynamics using the RK4-integrator
dynamics = ca.Function('d', [x_single, u_single, step_h], [rk4step_u(
    ode, step_h, x_single, u_single
)])


# N+1 states, position and velocity, n_body bodies, dimenstion dimensions
x = ca.SX.sym('x', (N + 1) * state_dimension)
# N states, thrust and dimension-1 angles
u = ca.SX.sym('u', N * dimension)


# define the orbital velocity
orbital_vel = sqrt(sun_mass * grav_const / orbit)


def cost_function_continous(t_current, x_current, u_current):
    '''
        Cost of a current state and controls.
    '''
    return u_current[0]


def cost_function_integral_discrete(x, u):
    '''
        Computes the discretized cost of given state and control variables to
        be minimized as a finite Riemann sum. Corresponds to eqn. (25).
    '''
    cost = 0
    for i in range(N):
        cost += h * u[dimension * i]
    return cost


# build nlp
constraints = []
lbg = []
ubg = []

# constraint: x_0 = x_0_bar (eqn. (27))
constraints.append(x[0:state_dimension] - x_0_bar)
lbg += [0] * state_dimension
ubg += [0] * state_dimension

for i in range(0, N):
    constraints.append(
        # contraint: x_k+1 - F(x_k, u_k) (eqn. (26))
        x[(i+1) * state_dimension:(i+2) * state_dimension] - dynamics(
            x[i * state_dimension:(i+1) * state_dimension],
            u[dimension * i:dimension * (i+1)],
            h
        )
    )
    lbg += [0] * state_dimension
    ubg += [0] * state_dimension

# contraint: stay above the surface (eqn. (24))
for i in range(0, N):
    x_current = x[i * state_dimension:(i+1) * state_dimension]
    constraints.append(ca.norm_2(x_current[0:dimension]))
    lbg += [1.1 * surface]
    ubg += [ca.inf]

# constraint: 0 <= u_k1 = r_k <= thrust_max (eqn. (23))
constraints.append(u[::dimension])
lbg += [0] * N
ubg += [thrust_max] * N

# constant: limit change of thrust (eqn. (31))
for i in range(N-1):
    constraints.append(ca.fabs(u[(i+1) * dimension] - u[i * dimension]))
    lbg += [0]
    ubg += [h * thrust_max / 60]

# contraint: limit change of angle (eqn. (32))
for i in range(N-1):
    constraints.append(ca.fabs(u[(i + 1) * dimension + 1]
                               - u[i * dimension + 1]))
    lbg += [0]
    ubg += [h * pi / 48]

# Terminal constraints:
x_terminal = x[N * state_dimension:(N+1) * state_dimension]

# constraint: reach orbital velocity (eqn. (16))
constraints.append(
    ca.norm_2(x_terminal[n_body * dimension:(n_body + 1)
                         * dimension]) - orbital_vel
)
lbg += [0]
ubg += [0]

# constraint: velocity is perpendicular to orbit normal (eqn. (17))
constraints.append(
    ca.dot(x_terminal[n_body * dimension:(n_body + 1) * dimension],
           x_terminal[0:dimension])
)
lbg += [0]
ubg += [0]

# constraint: rocket has correct distance to the planet (eqn. (15))
constraints.append(
    ca.norm_2(x_terminal[0:dimension]) - orbit
)
lbg += [0]
ubg += [0]


constraints = ca.vertcat(*constraints)

J_constraint_expr = ca.jacobian(constraints, ca.vertcat(x, u))
J_constraint = ca.Function("JC", [ca.vertcat(x, u)], [J_constraint_expr])

nlp = {'x': ca.vertcat(x, u), 'f': cost_function_integral_discrete(x, u),
       'g': constraints}

solver = ca.nlpsol('solver', 'ipopt', nlp)

# build initial guess
v_initial = sqrt(0.3 ** 2 + 3 ** 2)
x_initial = [surface, 0, v_initial * cos(pi/3), v_initial * sin(pi/3)]
u_initial = [0] * (2 * N)

# simultate the initial trajectory using u_initial
for i in range(N):
    x_initial = np.concatenate(
        (
            x_initial, dynamics(x_initial[i*state_dimension:(i + 1)
                                          * state_dimension],
                                u_initial[dimension*i:dimension*(i+1)],
                                h).full().flatten()
        )
    )

# construct the initial guess
initial_guess = np.concatenate((x_initial, u_initial)).tolist()


# Solve the NLP
res = solver(
    x0=initial_guess,    # solution guess
    lbx=-ca.inf,          # lower bound on x
    ubx=ca.inf,           # upper bound on x
    lbg=lbg,                # lower bound on g
    ubg=ubg,                # upper bound on g
)

optimal_variables = res["x"].full()

# The contraint jacobian has full rank:
# print(np.linalg.matrix_rank(J_constraint(optimal_variables)))
# print(J_constraint(optimal_variables).shape)

# get the optimal trajectory of the orbiting body
optimal_trajectory = np.reshape(
    optimal_variables[:(N + 1) * state_dimension],
    (N + 1, state_dimension)
)[:, 0:4]

# get the optimal controls of the orbiting body
optimal_controls = np.reshape(
    optimal_variables[(N + 1) * state_dimension:],
    (N, 2))

# add a zero control to u for the terminal simulation (after the body has
# reached a stable orbit and no further controls are nessecary)
optimal_controls = np.vstack([optimal_controls, np.array([0, 0])])

# terminal simulation time horizon
terminal_sim = 210

# append the terminal simulation to the optimal trajectory
for i in range(N, N+terminal_sim):
    optimal_trajectory = np.vstack([optimal_trajectory,
                                    dynamics(optimal_trajectory[i, :],
                                             [0] * 2, h).full().flatten()])
    optimal_controls = np.vstack([optimal_controls, np.array([0, 0])])


# create a visual plot:
fig = plt.figure()
ax = fig.add_subplot()

lines = []
dots = []
objects = []

fig3 = plt.figure()
ax3 = fig3.add_subplot()

fig2 = plt.figure()
axp = fig2.add_subplot(polar=True)

# a rescale factor for the visual control vector in the plot
vrf = 80 / thrust_max

# add animated control vector
vector = ax.annotate("", xytext=(optimal_trajectory[0, 0 * dimension],
                                 optimal_trajectory[0, 0 * dimension + 1]),
                     xy=(
                             optimal_trajectory[0, 0 * dimension] + vrf
                             * optimal_controls[0, 0]
                             * cos(optimal_controls[0, 1]),
                             optimal_trajectory[0, 0 * dimension + 1] + vrf
                             * optimal_controls[0, 0]
                             * sin(optimal_controls[0, 1])),
                     arrowprops={"facecolor": "red"})

objects.append(vector)

for b_index in range(n_body):
    line, = ax.plot(optimal_trajectory[:, b_index * dimension],
                    optimal_trajectory[:, b_index * dimension + 1],
                    '--', alpha=0.6)
    dot, = ax.plot(optimal_trajectory[0, b_index * dimension],
                   optimal_trajectory[0, b_index * dimension + 1],
                   'bo', alpha=1)
    dots.append(dot)
    lines.append(line)
    objects.append(line)
    objects.append(dot)


def update(num, optimal_trajectory, objects):
    objects[0].xy = (
                     optimal_trajectory[num, 0 * dimension] + vrf
                     * optimal_controls[num, 0]
                     * cos(optimal_controls[num, 1]),
                     optimal_trajectory[num, 0 * dimension + 1] + vrf
                     * optimal_controls[num, 0]
                     * sin(optimal_controls[num, 1])
    )

    objects[0].set_position(
            (optimal_trajectory[num, 0 * dimension],
             optimal_trajectory[num, 0 * dimension + 1])
    )

    for b_index in range(n_body):
        objects[1 + 2 * b_index].set_data(optimal_trajectory[0:num, b_index
                                                             * dimension],
                                          optimal_trajectory[0:num, b_index
                                                             * dimension + 1])
        objects[1 + 2 * b_index + 1].set_data(optimal_trajectory[num, b_index
                                                                 * dimension],
                                              optimal_trajectory[num, b_index
                                                                 * dimension
                                                                 + 1])
    return objects


def update_polar(num):
    polar_line.set_data(optimal_control_vector[1::2][:num],
                        np.abs(optimal_control_vector[0::2][:num])
                        / thrust_max)
    return [polar_line]


optimal_control_vector = optimal_variables[(N + 1) * state_dimension:]
ax3.plot(np.linspace(0, T, num=optimal_control_vector.shape[0]//2),
         ca.fabs(optimal_control_vector[::2])/thrust_max, "--x")
ax3.set_ylim([0, 1.1])
ax3.plot([0, T], [1, 1], "--", color="black")
ax3.set_title("Thrust over time")
ax3.set_xlabel("Time")
ax3.set_ylabel(r"$r(t) / r_{\max}$")


polar_line, = axp.plot(optimal_control_vector[1::2],
                       np.abs(optimal_control_vector[0::2]) / thrust_max, "-")
axp.set_ylim([0, 1.1])
axp.set_theta_zero_location("E")
axp.set_title("Polar plot of the controls")

circle = plt.Circle((0, 0), 190, fill=False, alpha=0.03)
ax.add_patch(circle)

circle = plt.Circle((0, 0), 100, fill=True)
ax.add_patch(circle)

ax.set_aspect('equal', adjustable='box')
ax.set_title("Rocket Trajectory")

ani = animation.FuncAnimation(fig, update,
                              fargs=[optimal_trajectory, objects],
                              interval=N // 5, blit=True,
                              frames=optimal_trajectory.shape[0])

ani2 = animation.FuncAnimation(fig2, update_polar,
                               interval=N // 5, blit=True,
                               frames=optimal_trajectory.shape[0])

plt.show()
