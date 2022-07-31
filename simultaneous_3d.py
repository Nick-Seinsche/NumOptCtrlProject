import numpy as np
import casadi as ca
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from math import pi, sin, cos, sqrt

# Time horizon
T = 850

# Number of discrete time points
N = 99

# Stepsize
h = T / (N - 1)

# Gravitational constant
grav_const = 0.0008

# masses of the simulated bodies (rocket, planet)
sun_mass = 1000000
rocket_mass = 0.05

# rocket is always body_0, planet is always body_-1
body_masses = (rocket_mass, sun_mass)

# number of bodies in orbit
n_body = 1

# dimension to simulate in
dimension = 3

# maximum thrust of the rocket
thrust_max = 0.0004

# radius of the planet
surface = 100

v_initial = 2.412

# initial position and velocity of orbiting body:
phi_0_bar = 0   # horizontal rotation
theta_0_bar = pi / 2  # vertical rotation

phi_v_0_bar = pi / 8  # horizontal rotation
theta_v_0_bar = pi / 2.1  # vertical rotation

x_0_bar = [1.1 * surface * cos(phi_0_bar) * sin(theta_0_bar),
           1.1 * surface * cos(theta_0_bar),
           1.1 * surface * sin(phi_0_bar) * sin(theta_0_bar),
           v_initial * cos(phi_v_0_bar) * sin(theta_v_0_bar),
           v_initial * cos(theta_v_0_bar),
           v_initial * sin(phi_v_0_bar) * sin(theta_v_0_bar)]

# desired circular orbit height
orbit = 190

# orbit rotation angles
theta_x = 0.3
theta_y = 0.2
theta_z = -0.2


# building the rotation matrix
rot_matrix_x = np.array([[1, 0, 0],
                        [0, ca.cos(theta_x), -ca.sin(theta_x)],
                        [0, ca.sin(theta_x), ca.cos(theta_x)]])

rot_matrix_y = np.array([[ca.cos(theta_y), 0, ca.sin(theta_y)],
                         [0, 1, 0],
                         [-ca.sin(theta_y), 0, ca.cos(theta_y)]])

rot_matrix_z = np.array([[ca.cos(theta_z), -ca.sin(theta_z), 0],
                        [ca.sin(theta_z), ca.cos(theta_z), 0],
                        [0, 0, 1]])


Q = rot_matrix_x @ rot_matrix_y @ rot_matrix_z


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
    rhs_velocity = []
    rhs_acceleration = []

    # iterate on all movable bodies around the planet
    for i in range(0, n_body):

        body_velocity_i = z[n_body * dimension + (i * dimension):
                            n_body * dimension + ((i + 1) * dimension)]

        rhs_velocity = ca.vertcat(rhs_velocity, body_velocity_i)

        rhs_acceleration_i = 0

        # calculate the force of body_j on body_i
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

        # body_0 is the actuated rocket
        if i == 0:
            r = controls[0]
            phi = controls[1]
            theta = controls[2]
            rhs_acceleration_i[0] += (r * ca.sin(phi) * ca.cos(theta)
                                      / body_masses[i])
            rhs_acceleration_i[1] += (r * ca.sin(phi) * ca.sin(theta)
                                      / body_masses[i])
            rhs_acceleration_i[2] += r * ca.cos(phi) / body_masses[i]

        rhs_acceleration = ca.vertcat(rhs_acceleration, rhs_acceleration_i)

    return ca.vertcat(rhs_velocity, rhs_acceleration)


def ode(z, controls):
    return ode_general(z, controls, body_masses, n_body, dimension)


state_dimension = 2 * n_body * dimension

x_single = ca.SX.sym('x', state_dimension)
u_single = ca.SX.sym('u', dimension)
step_h = ca.SX.sym('h')

dynamics = ca.Function('d', [x_single, u_single, step_h], [rk4step_u(
    ode, step_h, x_single, u_single
)])

# N+1 states, position and velocity, n_body bodies, dimenstion dimensions
x = ca.SX.sym('x', (N + 1) * state_dimension)
# N states, thrust and dimension-1 angles
u = ca.SX.sym('u', N * dimension)


# the orbital velocity:
orbital_vel = sqrt(sun_mass * grav_const / orbit)


def cost_function_continous(t_current, x_current, u_current):
    return u_current[0]


def cost_function_integral_discrete(x, u):
    '''
        Computes the discretized cost of given state and control variables to
        be minimized, using Simpson's rule. Assumes that N is odd.
    '''
    cost = 0
    for i in range(N):
        cost += h * u[dimension * i]
    return cost


# build nlp
constraints = []
lbg = []
ubg = []

# x_0 = x_0_bar
constraints.append(x[0:state_dimension] - x_0_bar)
lbg += [0] * state_dimension
ubg += [0] * state_dimension

for i in range(0, N):
    constraints.append(
        # x_k+1 - F(x_k, u_k)
        x[(i+1) * state_dimension:(i+2) * state_dimension] - dynamics(
            x[i * state_dimension:(i+1) * state_dimension],
            u[dimension * i:dimension * (i+1)],
            h
        )
    )
    lbg += [0] * state_dimension
    ubg += [0] * state_dimension

# stay above surface and close to orbit
for i in range(0, N):
    x_current = x[i * state_dimension:(i+1) * state_dimension]
    constraints.append(ca.norm_2(x_current[0:dimension]))
    lbg += [1.1 * surface]
    ubg += [ca.inf]

# thrust_max <= u_k1 = r_k <= thrust_max
constraints.append(u[::dimension])
lbg += [0] * N
ubg += [thrust_max] * N

# constant: limit change of thrust
for i in range(N-1):
    constraints.append(ca.fabs(u[(i+1) * dimension] - u[i * dimension]))
    lbg += [0]
    ubg += [h * thrust_max / 60]

# contraint: limit change of angle
for i in range(N-1):
    constraints.append(ca.fabs(u[(i + 1) * dimension + 1]
                               - u[i * dimension + 1]))
    lbg += [0]
    ubg += [h * pi / 48]

# contraint: limit change of angle
for i in range(N-1):
    constraints.append(ca.fabs(u[(i + 1) * dimension + 2]
                               - u[i * dimension + 2]))
    lbg += [0]
    ubg += [h * pi / 48]


# Terminal constraints
x_terminal = x[N * state_dimension: (N+1) * state_dimension]


# reach orbital velocity
constraints.append(
    ca.norm_2(x_terminal[n_body * dimension:(n_body + 1)
                         * dimension]) - orbital_vel
)

lbg += [0]
ubg += [0]

# velocity perpendicular to orbit normal
constraints.append(
    ca.dot(x_terminal[n_body * dimension:(n_body + 1)
                      * dimension], x_terminal[0:dimension])
)

lbg += [0]
ubg += [0]

orbit_normal = ca.mtimes(Q.T, [0, 1, 0])

# velocity is perpendicular to orbit binormal
constraints.append(
    ca.dot(x_terminal[n_body * dimension:(n_body + 1)
                      * dimension], orbit_normal)
)

lbg += [0]
ubg += [0]


# rocket is on the orbit
constraints.append(
    ca.dot(x_terminal[0:dimension], orbit_normal)
)

lbg += [0]
ubg += [0]

# rocket has correct distance to the planet
constraints.append(
    ca.norm_2(x_terminal[0:dimension]) - orbit
)

lbg += [0]
ubg += [0]


constraints = ca.vertcat(*constraints)

nlp = {'x': ca.vertcat(x, u), 'f': cost_function_integral_discrete(x, u),
       'g': constraints}

solver = ca.nlpsol('solver', 'ipopt', nlp)

# build initial guess

v_initial = sqrt(0.3 ** 2 + 3 ** 2)


x_initial = [1.1 * surface * cos(phi_0_bar) * sin(theta_0_bar),
             1.1 * surface * cos(theta_0_bar),
             1.1 * surface * sin(phi_0_bar) * sin(theta_0_bar),
             v_initial * cos(pi / 4) * sin(theta_v_0_bar),
             v_initial * cos(theta_v_0_bar),
             v_initial * sin(pi / 4) * sin(theta_v_0_bar)]

u_initial = [0] * (dimension * N)

for i in range(N):
    x_initial = np.concatenate(
        (
            x_initial, dynamics(x_initial[i * state_dimension:(i + 1)
                                          * state_dimension],
                                u_initial[dimension * i:dimension *
                                          (i + 1)], h).full().flatten()
        )
    )

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

optimal_trajectory = np.reshape(
    optimal_variables[:(N + 1) * state_dimension],
    (N + 1, state_dimension)
)[:, 0:6]

optimal_controls = np.reshape(
    optimal_variables[(N + 1) * state_dimension:],
    (N, 3))

optimal_controls = np.vstack([optimal_controls, np.array([0, 0, 0])])

terminal_sim = 500

for i in range(N, N+terminal_sim):
    optimal_trajectory = np.vstack([optimal_trajectory,
                                    dynamics(optimal_trajectory[i, :],
                                             [0] * 3, h).full().flatten()])
    optimal_controls = np.vstack([optimal_controls, np.array([0, 0, 0])])

fig = plt.figure()
ax = plt.axes(projection='3d')

fig2 = plt.figure()
ax2 = fig2.add_subplot()

fig3 = plt.figure()
ax3 = fig3.add_subplot()

lines = []
dots = []
objects = []


for b_index in range(n_body):
    line, = ax.plot3D(optimal_trajectory[:, b_index * dimension],
                      optimal_trajectory[:, b_index * dimension + 2],
                      optimal_trajectory[:, b_index * dimension + 1],
                      '--', alpha=0.6)

    dot, = ax.plot3D(optimal_trajectory[0, b_index * dimension],
                     optimal_trajectory[0, b_index * dimension + 2],
                     optimal_trajectory[0, b_index * dimension + 1],
                     'bo', alpha=1)

    dots.append(dot)
    lines.append(line)
    objects.append(line)
    objects.append(dot)


def update(num, optimal_trajectory, objects):
    for b_index in range(n_body):
        objects[2 * b_index].set_data(optimal_trajectory[0:num, b_index
                                                         * dimension],
                                      optimal_trajectory[0:num, b_index
                                                         * dimension + 2])
        objects[2 * b_index].set_3d_properties(optimal_trajectory[0:num,
                                                                  b_index
                                                                  * dimension
                                                                  + 1])

        objects[2 * b_index + 1].set_data(optimal_trajectory[num, b_index
                                                             * dimension],
                                          optimal_trajectory[num, b_index
                                                             * dimension + 2])
        objects[2 * b_index
                + 1].set_3d_properties(optimal_trajectory[num,
                                                          b_index
                                                          * dimension + 1])
    return objects


u, v = np.mgrid[0:2*np.pi:20j, 0:np.pi:10j]
x = surface * np.cos(u)*np.sin(v)
y = surface * np.sin(u)*np.sin(v)
z = surface * np.cos(v)
ax.plot_wireframe(x, y, z, color="r")

ax.set_title("Animated Trajectory")

ax.set_xlim((-200, 200))
ax.set_ylim((-200, 200))
ax.set_zlim((-200, 200))

optimal_control_vector = optimal_variables[(N + 1) * state_dimension:]
ax2.plot(np.linspace(0, T, num=optimal_control_vector.shape[0]//3),
         ca.fabs(optimal_control_vector[::3])/thrust_max, "--x")
ax2.set_ylim([0, 1.1])
ax2.plot([0, T], [1, 1], "--", color="black")
ax2.set_title("Thrust over time")
ax2.set_xlabel("N")
ax2.set_ylabel(r"$r(t) / t_{max}$")

phi_line = ax3.plot(np.linspace(0, T,
                                num=optimal_control_vector.shape[0] // 3),
                    optimal_control_vector[1::3], "-")
theta_line = ax3.plot(np.linspace(0, T,
                                  num=optimal_control_vector.shape[0] // 3),
                      optimal_control_vector[2::3], "-")
ax3.set_title("Animation of the control vector")
ax3.set_xlabel("N")
ax3.set_ylabel("radiants")


ani = animation.FuncAnimation(fig, update, fargs=[optimal_trajectory, objects],
                              interval=N // 5, blit=True,
                              frames=optimal_trajectory.shape[0])

plt.show()
