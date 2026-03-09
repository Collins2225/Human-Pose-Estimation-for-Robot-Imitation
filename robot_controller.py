"""
===================================================================
MODULE 4: robot_controller.py — PyBullet Robot Simulation Control
===================================================================

MENTOR EXPLANATION:
PyBullet is a physics simulation engine (like a video game engine for
robots). We load a URDF file (Unified Robot Description Format — an
XML file describing a robot's joints, links, and geometry), then
control it by setting joint angles every frame.

KEY CONCEPTS:

1. URDF Files:
   The KUKA iiwa is a popular 7-DOF robot arm. PyBullet includes it.
   It has 7 revolute joints, each with specific limits (min/max angles).

2. Joint Space vs. Task Space:
   - JOINT space: angles of each motor (what we control directly)
   - TASK space: position of the hand in 3D (x, y, z)
   We work in JOINT space (simpler, more direct for our case).

3. Inverse Kinematics (IK):
   Converting from task-space (hand position) to joint-space (angles).
   PyBullet has a built-in IK solver. We use both approaches:
   - Direct angle mapping (for simple demonstrations)
   - IK-based (for more realistic arm behavior)

4. JOINT LIMITS:
   Every real robot joint has physical limits it cannot exceed.
   Sending commands beyond these limits either gets clamped or
   could damage a real robot. We ALWAYS respect these limits.

5. POSITION CONTROL:
   PyBullet's setJointMotorControl2() lets us command a joint to
   move to a target angle. We use POSITION_CONTROL mode which
   simulates a motor trying to reach the target position.
===================================================================
"""

import pybullet as p
import pybullet_data
import numpy as np
import time
from typing import Optional


# ---------------------------------------------------------------
# ROBOT JOINT CONFIGURATION
# ---------------------------------------------------------------
# These are the physical limits of the KUKA iiwa 7-DOF arm in RADIANS.
# MENTOR NOTE: Always work in radians internally; convert to/from
# degrees only at the human interface boundary.
KUKA_JOINT_LIMITS = {
    # joint_index: (min_rad, max_rad, description)
    0: (-2.96706, 2.96706, "Base rotation"),
    1: (-2.09440, 2.09440, "Shoulder pitch"),
    2: (-2.96706, 2.96706, "Elbow rotation"),
    3: (-2.09440, 2.09440, "Elbow pitch"),
    4: (-2.96706, 2.96706, "Wrist rotation"),
    5: (-2.09440, 2.09440, "Wrist pitch"),
    6: (-3.05433, 3.05433, "End-effector rotation"),
}

# Default arm position (resting pose, all joints at ~0)
HOME_POSITION = [0.0, -0.5, 0.0, 1.0, 0.0, -0.5, 0.0]


class RobotController:
    """
    Controls a KUKA iiwa robotic arm in PyBullet simulation.

    MENTOR NOTE on design:
    We use the KUKA iiwa because:
    1. It's included with pybullet_data (no extra downloads)
    2. It's a realistic 7-DOF arm used in actual research labs
    3. Its joint structure maps well to human arm movements

    Mapping human → robot:
      Human shoulder elevation → Robot joints 0, 1 (base + shoulder)
      Human elbow flexion      → Robot joint 3 (elbow pitch)
      Human wrist angle        → Robot joint 5 (wrist pitch)
    """

    def __init__(self, use_gui: bool = True, gravity: float = -9.81):
        """
        Initialize PyBullet and load the robot.

        Args:
            use_gui: Show 3D visualization window (True) or run headless (False)
            gravity: Gravitational acceleration (m/s²). Earth = -9.81
        """
        self.use_gui = use_gui
        self.robot_id = None
        self.joint_ids = []
        self._target_angles = HOME_POSITION.copy()

        # Connect to PyBullet
        # MENTOR NOTE: p.GUI opens a 3D window; p.DIRECT runs without display
        if use_gui:
            self.physics_client = p.connect(p.GUI)
            # Set up a nice camera view
            p.resetDebugVisualizerCamera(
                cameraDistance=1.5,
                cameraYaw=45,
                cameraPitch=-30,
                cameraTargetPosition=[0, 0, 0.5]
            )
        else:
            self.physics_client = p.connect(p.DIRECT)

        # Configure simulation
        p.setGravity(0, 0, gravity)  # x=0, y=0, z=gravity
        p.setTimeStep(1.0 / 240.0)  # 240Hz physics update rate

        # Add PyBullet's built-in robot models to the search path
        p.setAdditionalSearchPath(pybullet_data.getDataPath())

        # Load the environment and robot
        self._load_environment()
        self._load_robot()

    def _load_environment(self):
        """
        Load the ground plane and environment.

        MENTOR NOTE:
        In PyBullet, we must explicitly create a ground plane, otherwise
        the robot will fall through infinite space due to gravity.
        The plane.urdf is a simple flat surface.
        """
        self.plane_id = p.loadURDF("plane.urdf")

        # Optional: Add a table for the robot to "sit on"
        # p.loadURDF("table/table.urdf", [0, 0, -0.65])

    def _load_robot(self):
        """
        Load the KUKA iiwa robot arm from its URDF file.

        MENTOR NOTE on URDF loading:
        - basePosition: Where to place the robot in 3D space (x, y, z)
        - baseOrientation: Rotation as a quaternion [x, y, z, w]
          Identity quaternion [0,0,0,1] means no rotation
        - useFixedBase=True: Robot base is bolted to the ground
          (False would make the whole robot fall due to gravity)
        """
        self.robot_id = p.loadURDF(
            "kuka_iiwa/model.urdf",
            basePosition=[0, 0, 0],
            baseOrientation=p.getQuaternionFromEuler([0, 0, 0]),
            useFixedBase=True,
            flags=p.URDF_USE_INERTIA_FROM_FILE
        )

        # Discover which joints are controllable (revolute joints)
        # MENTOR NOTE: URDF files can have many joint types:
        # JOINT_REVOLUTE (rotational), JOINT_PRISMATIC (sliding),
        # JOINT_FIXED (rigid), etc. We only care about revolute joints.
        num_joints = p.getNumJoints(self.robot_id)
        self.joint_ids = []

        print(f"Robot loaded. Found {num_joints} joints total:")
        for i in range(num_joints):
            info = p.getJointInfo(self.robot_id, i)
            joint_name = info[1].decode('utf-8')
            joint_type = info[2]

            if joint_type == p.JOINT_REVOLUTE:
                self.joint_ids.append(i)
                print(f"  Joint {i}: {joint_name} (REVOLUTE) ✓")
            else:
                print(f"  Joint {i}: {joint_name} (fixed/other, skipped)")

        print(f"\nControlling {len(self.joint_ids)} revolute joints.")

        # Move robot to home position
        self._set_home_position()

    def _set_home_position(self):
        """Instantly move robot to home position (bypasses physics)."""
        for i, joint_id in enumerate(self.joint_ids):
            if i < len(HOME_POSITION):
                p.resetJointState(self.robot_id, joint_id, HOME_POSITION[i])

    def map_human_angles_to_robot(self, human_angles: dict) -> list:
        """
        Convert human joint angles to robot joint target angles.

        MENTOR EXPLANATION — The Mapping Problem:
        This is the most creative part of the project. Human arms and
        robot arms are mechanically VERY different:
        
        Humans: Ball-and-socket shoulder (3 DOF), hinge elbow (1 DOF),
                twisting forearm (1 DOF), complex wrist (2 DOF)
        KUKA:   7 revolute joints in a serial chain
        
        We create an APPROXIMATE mapping that looks natural:
        
        Human angle (degrees) → Robot joint angle (radians)
        
        Key transformations:
        1. Degrees → Radians (multiply by π/180)
        2. Range mapping (human 0-180° → robot joint limits)
        3. Offset and inversion (different zero-points and directions)

        Args:
            human_angles: Dict from AngleCalculator.get_all_angles()

        Returns:
            List of 7 joint angles in radians for KUKA joints 0-6
        """
        # Start from home position
        robot_angles = HOME_POSITION.copy()

        # Helper: safely get an angle value, use default if None
        def get_angle(key, default=90.0):
            val = human_angles.get(key)
            return val if val is not None else default

        # --- JOINT 0: Base rotation (shoulder abduction) ---
        # Human: shoulder abduction 0-90° → Robot: -1.0 to 1.0 rad
        # When you raise your arm sideways, the robot base rotates
        left_abd = get_angle("left_shoulder_abd", 0.0)
        robot_angles[0] = self._remap_and_clamp(
            value=left_abd,
            in_min=0, in_max=90,         # Human range
            out_min=0, out_max=1.2,      # Robot range (radians)
            joint_idx=0
        )

        # --- JOINT 1: Shoulder pitch (elevation) ---
        # Human: shoulder elevation 90°(down) to 180°(up)
        # Robot: bends forward as arm raises
        left_elev = get_angle("left_shoulder_elev", 90.0)
        robot_angles[1] = self._remap_and_clamp(
            value=left_elev,
            in_min=60, in_max=160,
            out_min=0.5, out_max=-1.2,   # Inverted: up = negative
            joint_idx=1
        )

        # --- JOINT 3: Elbow pitch (flexion/extension) ---
        # Human: elbow flexion 180°(straight) to 30°(bent)
        # Robot: straightens and bends correspondingly
        # NOTE: We invert because human "straight" should = robot "straight"
        left_flex = get_angle("left_elbow_flexion", 170.0)
        robot_angles[3] = self._remap_and_clamp(
            value=left_flex,
            in_min=40, in_max=170,       # Human elbow range
            out_min=1.8, out_max=0.0,    # Robot range (inverted)
            joint_idx=3
        )

        # --- JOINT 2: Elbow rotation (twisting with shoulder) ---
        # Use shoulder abduction slightly to give a natural twist
        robot_angles[2] = self._remap_and_clamp(
            value=left_abd * 0.3,        # Partial coupling
            in_min=0, in_max=30,
            out_min=0, out_max=0.5,
            joint_idx=2
        )

        # --- JOINT 5: Wrist pitch ---
        left_wrist = get_angle("left_wrist_angle", 90.0)
        robot_angles[5] = self._remap_and_clamp(
            value=left_wrist,
            in_min=0, in_max=180,
            out_min=-1.0, out_max=1.0,
            joint_idx=5
        )

        return robot_angles

    def _remap_and_clamp(self,
                          value: float,
                          in_min: float, in_max: float,
                          out_min: float, out_max: float,
                          joint_idx: int) -> float:
        """
        Linearly remap a value from one range to another, then clamp
        to the robot's physical joint limits.

        MENTOR NOTE on linear remapping:
        The formula is:    out = out_min + (value - in_min) * (out_max - out_min)
                                                              ───────────────────
                                                                  (in_max - in_min)
        
        This is just the equation of a line (y = mx + b) that maps
        [in_min, in_max] → [out_min, out_max].

        We also CLAMP to joint limits to protect the robot.
        """
        # Avoid division by zero
        if abs(in_max - in_min) < 1e-6:
            return out_min

        # Linear interpolation (remap)
        t = (value - in_min) / (in_max - in_min)  # Normalized 0-1
        remapped = out_min + t * (out_max - out_min)

        # Clamp to robot's physical joint limits
        if joint_idx in KUKA_JOINT_LIMITS:
            min_rad, max_rad, _ = KUKA_JOINT_LIMITS[joint_idx]
            remapped = np.clip(remapped, min_rad, max_rad)

        return float(remapped)

    def set_joint_targets(self, target_angles: list):
        """
        Send joint angle targets to the robot.

        MENTOR NOTE on POSITION_CONTROL:
        PyBullet's motor control modes:
        - POSITION_CONTROL: "Move to this angle" (what we use)
        - VELOCITY_CONTROL: "Move at this speed"
        - TORQUE_CONTROL: "Apply this force"
        
        For position control, we tune:
        - positionGain (kp): How aggressively to correct position error
        - velocityGain (kd): Damping to prevent oscillation
        - maxVelocity: Speed limit (prevent violent movements)
        - force: Maximum motor torque (Newton-meters)

        Args:
            target_angles: List of joint angles in radians
        """
        self._target_angles = target_angles

        for i, joint_id in enumerate(self.joint_ids):
            if i >= len(target_angles):
                break

            p.setJointMotorControl2(
                bodyUniqueId=self.robot_id,
                jointIndex=joint_id,
                controlMode=p.POSITION_CONTROL,
                targetPosition=target_angles[i],
                positionGain=0.3,    # Proportional gain (stiffness)
                velocityGain=1.0,    # Derivative gain (damping)
                maxVelocity=1.5,     # Max speed (rad/s) — safety limit
                force=500            # Max torque (Nm)
            )

    def step_simulation(self):
        """
        Advance the physics simulation by one timestep.

        MENTOR NOTE:
        PyBullet doesn't simulate continuously on its own. We must
        call stepSimulation() every frame. This is called the
        "simulation loop" pattern:
        
        while running:
            update_targets()       ← from our pose data
            step_simulation()      ← advance physics
            sleep(1/fps)           ← maintain frame rate
        
        At 240Hz physics with 30fps control, we run ~8 physics steps
        per control frame. This improves simulation stability.
        """
        p.stepSimulation()

    def get_joint_states(self) -> list:
        """
        Read actual current joint angles from the simulation.

        MENTOR NOTE:
        There's a difference between:
        - TARGET angle: what we WANT the joint to be
        - ACTUAL angle: what the joint IS (may differ due to physics)
        
        PyBullet simulates the physics of the motor trying to reach
        the target. For stiff position control, actual ≈ target,
        but the physics still plays out realistically.

        Returns:
            List of (position, velocity, reaction_forces, torque) tuples
        """
        states = []
        for joint_id in self.joint_ids:
            state = p.getJointState(self.robot_id, joint_id)
            states.append({
                "position": state[0],   # Current angle (radians)
                "velocity": state[1],   # Current angular velocity (rad/s)
                "torque":   state[3]    # Applied torque (Nm)
            })
        return states

    def reset_to_home(self):
        """Instantly reset robot to home position."""
        self._set_home_position()

    def get_end_effector_position(self) -> np.ndarray:
        """
        Get the 3D position of the robot's end-effector (hand/tool tip).

        MENTOR NOTE:
        getLinkState returns the world-frame position and orientation
        of a link. The end-effector is the last link (index = num_joints - 1).

        Returns:
            [x, y, z] position in meters (world coordinates)
        """
        last_link = len(self.joint_ids) - 1
        state = p.getLinkState(self.robot_id, last_link)
        return np.array(state[0])  # World position

    def add_debug_text(self, text: str, position: list = [0, 0, 1.5],
                        color: list = [1, 1, 1]):
        """Add overlay text in the 3D simulation view."""
        if self.use_gui:
            p.addUserDebugText(
                text=text,
                textPosition=position,
                textColorRGB=color,
                textSize=1.2,
                lifeTime=0.1  # Auto-removes after 0.1s (refreshed each frame)
            )

    def disconnect(self):
        """Cleanly shut down PyBullet."""
        p.disconnect(self.physics_client)


# ---------------------------------------------------------------
# QUICK TEST — Load robot and move it to a test position
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("Testing RobotController...")
    print("A PyBullet window should open showing the KUKA arm.")
    print("The arm will move through a test sequence.")
    print("Close the window or press Ctrl+C to quit.\n")

    controller = RobotController(use_gui=True)

    # Test sequence: sweep the elbow joint
    print("Running test motion sequence...")

    try:
        for t in range(500):
            # Simulate a bending elbow motion
            angle = 0.8 * np.sin(t * 0.05)  # Oscillate ±0.8 radians

            test_angles = HOME_POSITION.copy()
            test_angles[3] = angle  # Elbow joint

            controller.set_joint_targets(test_angles)
            controller.step_simulation()
            time.sleep(1.0 / 60.0)  # 60fps

        print("Test complete!")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        controller.disconnect()