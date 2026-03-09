#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════
robot_simulator.py — PyBullet Robot Environment & Control
════════════════════════════════════════════════════════════════

This module handles:
- PyBullet physics engine setup
- Loading robot models (URDF format)
- Joint control and inverse kinematics
- Real-time visualization
- Gravity and physics constraints

 PYBULLET CONCEPTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What is PyBullet?
─────────────────
PyBullet is a physics simulation engine that:
1. Loads 3D robot models (URDF, SDF, MJCF formats)
2. Simulates realistic physics (gravity, collisions, friction)
3. Provides forward/inverse kinematics
4. Renders visualization
5. Allows joint control (position or torque)

Why use simulation?
───────────────────
✓ Test code before real robot (safe!)
✓ Reproduce results consistently
✓ Visualize what robot is doing
✓ Debug kinematics issues
✓ No risk of hardware damage

Physics modes:
──────────────
- Gravity: Realistic physics with gravity
- No gravity: Easier for manipulation tasks
- Different constraint solvers for accuracy

Robot models (URDF):
───────────────────
URDF = Unified Robot Description Format

Example structure:
  <robot name="my_robot">
    <link name="base_link"/>
    <link name="arm_link_1"/>
    <joint name="shoulder" type="revolute">
      <parent link="base_link"/>
      <child link="arm_link_1"/>
      <limits lower="0" upper="180"/>
    </joint>
  </robot>

Defines:
- Links (rigid bodies/segments)
- Joints (connections, degrees of freedom)
- Collision geometry
- Visual mesh

════════════════════════════════════════════════════════════════
"""

import pybullet as p
import pybullet_data
import numpy as np
from typing import Dict, Optional, List, Tuple
import os


class RobotSimulator:
    """
    Manages PyBullet physics environment and robot control.
    
    Sets up the simulation, loads robot model, and provides
    interface for setting joint positions.
    """
    
    def __init__(self, use_gui: bool = True, gravity: Tuple[float, float, float] = (0, 0, -9.81)):
        """
        Initialize PyBullet environment.
        
        Args:
            use_gui: If True, show visual window (slower but more intuitive)
                    If False, fast headless simulation (better for testing)
            gravity: Gravity vector (typically (0, 0, -9.81) for downward)
            
        PHYSICS_CLIENT:
        ───────────────
        PyBullet requires creating a client to the physics engine.
        
        - GUI mode: Connects to GUI server for visualization
        - DIRECT mode: Runs headless (fast, no graphics)
        
        Both modes execute the same physics.
        """
        
        self.use_gui = use_gui
        self.gravity = gravity
        self.client_id: Optional[int] = None
        self.robot_id: Optional[int] = None
        self.joint_info: Dict = {}
        self.joint_indices: Dict[str, int] = {}
        self.dt = 1.0 / 240.0  # Default physics timestep
        
        # Frame rate controls
        self.frame_count = 0
        self.simulated_time = 0.0
        
        print("🤖 Initializing PyBullet Robot Simulator...")
        self._connect_to_physics_engine()
    
    
    def _connect_to_physics_engine(self):
        """
        Connect to PyBullet physics engine.
        
        MODES:
        ──────
        1. GUI Mode (p.GUI):
           - Shows 3D visualization window
           - Mouse/keyboard interaction
           - Slower (limited to ~60 FPS)
           - Good for debugging
        
        2. DIRECT Mode:
           - No visualization
           - Fast computation
           - Good for batch processing
        """
        
        if self.use_gui:
            print("   Connecting to GUI physics engine...")
            mode = p.GUI
        else:
            print("   Connecting to DIRECT physics engine (headless)...")
            mode = p.DIRECT
        
        self.client_id = p.connect(mode)
        
        if self.client_id < 0:
            raise RuntimeError("Failed to connect to PyBullet!")
        
        # Load built-in assets (includes URDF models)
        # ──────────────────────────────────────────
        # pybullet_data contains example robots and objects:
        # - r2d2.urdf (cute robot)
        # - r2d2_limited.urdf
        # - plane.urdf (floor)
        # - cube_small.urdf
        # - sphere.urdf
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        
        # Configure gravity
        # ─────────────────
        print(f"   Setting gravity: {self.gravity}")
        p.setGravity(*self.gravity)
        
        # Control panel settings (if GUI)
        if self.use_gui:
            # Slow down simulation for easier viewing
            p.setTimeStep(self.dt)
            # Real-time simulation
            p.setRealTimeSimulation(False)
        
        print("   ✓ Physics engine ready\n")
    
    
    def load_robot(self, urdf_path: str, 
                  position: Tuple[float, float, float] = (0, 0, 0),
                  orientation: Tuple[float, float, float, float] = (0, 0, 0, 1)) -> int:
        """
        Load robot model from URDF file.
        
        Args:
            urdf_path: Path to URDF file
            position: (x, y, z) starting position
            orientation: Quaternion (x, y, z, w) starting orientation
                        (0, 0, 0, 1) = identity (no rotation)
            
        Returns:
            Robot body ID (for later reference)
            
        URDF PATH RESOLUTION:
        ─────────────────────
        Paths can be:
        - Absolute: "/path/to/robot.urdf"
        - Relative: "models/robot.urdf"
        - Built-in: "r2d2.urdf" (found via pybullet_data)
        
        Built-in robots available:
        - r2d2.urdf
        - pr2_gripper.urdf
        - laikago.urdf
        - and many more
        """
        
        print(f"🤖 Loading robot from: {urdf_path}")
        
        # Load URDF file
        # ──────────────
        # useFixedBase=True: Robot base is fixed (don't let it fall)
        # globalScaling: Scale the entire robot
        self.robot_id = p.loadURDF(
            urdf_path,
            basePosition=position,
            baseOrientation=orientation,
            useFixedBase=True  # Keeps base stationary
        )
        
        if self.robot_id < 0:
            raise RuntimeError(f"Failed to load robot from {urdf_path}")
        
        # Inspect robot structure
        # ──────────────────────
        self._build_joint_index()
        
        print(f"   ✓ Robot loaded (ID: {self.robot_id})")
        print(f"   ✓ Found {len(self.joint_indices)} controllable joints\n")
        
        return self.robot_id
    
    
    def _build_joint_index(self):
        """
        Map joint names to their PyBullet indices.
        
        PyBullet refers to joints by integer index.
        We build a name → index mapping for easier control.
        
        JOINT TYPES:
        ────────────
        - REVOLUTE: Rotating joint (typical servo)
        - PRISMATIC: Sliding joint (rare in robots)
        - FIXED: No movement
        - SPHERICAL: Ball joint
        
        We only control REVOLUTE joints typically.
        """
        
        self.joint_indices.clear()
        self.joint_info.clear()
        
        # Get number of joints in robot
        num_joints = p.getNumJoints(self.robot_id)
        
        print(f"   Analyzing {num_joints} joints...")
        
        for joint_idx in range(num_joints):
            # Get joint info from PyBullet
            info = p.getJointInfo(self.robot_id, joint_idx)
            
            # Unpack joint info tuple:
            # (jointIndex, jointName, jointType, qIndex, uIndex,
            #  flags, jointDamping, jointFriction, lowerLimit, upperLimit,
            #  maxForce, maxVelocity, linkName, ...)
            
            joint_name = info[1].decode('utf-8')  # Decode from bytes
            joint_type = info[2]  # Type: REVOLUTE, PRISMATIC, etc.
            lower_limit = info[8]
            upper_limit = info[9]
            
            # Only map controllable revolute joints
            if joint_type in [p.JOINT_REVOLUTE]:
                self.joint_indices[joint_name] = joint_idx
                self.joint_info[joint_name] = {
                    'index': joint_idx,
                    'type': joint_type,
                    'lower_limit': lower_limit,
                    'upper_limit': upper_limit,
                    'range': upper_limit - lower_limit
                }
                
                print(f"      [{joint_idx:2d}] {joint_name:30s} | "
                      f"Range: [{lower_limit:7.2f}°, {upper_limit:7.2f}°]")
    
    
    def set_joint_angle(self, joint_name: str, angle_rad: float):
        """
        Set a joint to specific angle using position control.
        
        Args:
            joint_name: Name of joint (must exist in robot)
            angle_rad: Target angle in radians
            
        CONTROL MODES:
        ──────────────
        PyBullet has multiple control modes:
        
        1. POSITION_CONTROL (what we use):
           - Specify target position
           - PID controller reaches it
           - Best for trajectory following
        
        2. VELOCITY_CONTROL:
           - Specify target velocity
           - Useful for continuous motion
        
        3. TORQUE_CONTROL:
           - Apply raw torque
           - Like real robot actuators
           - Hardest to control
        
        We use POSITION_CONTROL because it's intuitive
        and matches how servo motors work.
        """
        
        if joint_name not in self.joint_indices:
            print(f"⚠️  Unknown joint: {joint_name}")
            return
        
        joint_idx = self.joint_indices[joint_name]
        
        # Convert radians to degrees for display
        angle_deg = np.degrees(angle_rad)
        
        # Get joint limits and clamp (extra safety)
        info = self.joint_info[joint_name]
        angle_rad_clamped = np.clip(angle_rad, info['lower_limit'], info['upper_limit'])
        
        # Set target position
        # ───────────────────
        # p.setJointMotorControl2: Low-level joint control
        # 
        # Parameters:
        # - bodyUniqueId: Robot ID
        # - jointIndex: Which joint
        # - controlMode: How to control (POSITION_CONTROL)
        # - targetPosition: Where to go (radians)
        # - maxForce: Maximum force servo can exert
        # - positionGain, velocityGain: PID tuning
        
        p.setJointMotorControl2(
            bodyUniqueId=self.robot_id,
            jointIndex=joint_idx,
            controlMode=p.POSITION_CONTROL,
            targetPosition=angle_rad_clamped,
            maxForce=500,  # Strong servo
            positionGain=0.1,  # PID proportional gain
            velocityGain=0.1   # PID derivative gain
        )
    
    
    def set_all_joint_angles(self, angles: Dict[str, float]):
        """
        Set multiple joints to target angles.
        
        Args:
            angles: Dict like {'joint1': 1.5, 'joint2': 0.5, ...}
                   Values in radians
                   
        This is the main interface you'll call from the main loop.
        """
        for joint_name, angle_rad in angles.items():
            self.set_joint_angle(joint_name, angle_rad)
    
    
    def get_joint_angle(self, joint_name: str) -> Optional[float]:
        """
        Get current angle of a joint.
        
        Args:
            joint_name: Name of joint
            
        Returns:
            Current angle in radians, or None if joint not found
            
        This lets us read back the actual robot state
        for visualization and debugging.
        """
        
        if joint_name not in self.joint_indices:
            return None
        
        joint_idx = self.joint_indices[joint_name]
        
        # Get joint state
        # ──────────────
        # Returns: (position, velocity, reactionForces, appliedTorque)
        state = p.getJointState(self.robot_id, joint_idx)
        position = state[0]  # Angle in radians
        
        return position
    
    
    def get_all_joint_angles(self) -> Dict[str, float]:
        """Get all current joint angles."""
        angles = {}
        for joint_name in self.joint_indices.keys():
            angles[joint_name] = self.get_joint_angle(joint_name)
        return angles
    
    
    def step_simulation(self, num_steps: int = 1):
        """
        Advance physics simulation.
        
        Args:
            num_steps: Number of physics steps to simulate
                      (each step is dt = 1/240s by default)
            
        WHY MANUAL STEPPING?
        ───────────────────
        Unlike real-time mode, manual stepping gives us:
        - Precise control over simulation rate
        - Reproducible results
        - Easier frame skip for speed
        
        For 30 FPS pose input:
        - Pose data arrives every 33ms
        - At dt=1/240s, that's 8 simulation steps
        - We do step_simulation(8) between pose updates
        """
        
        for _ in range(num_steps):
            p.stepSimulation()
            self.frame_count += 1
            self.simulated_time += self.dt
    
    
    def load_ground_plane(self, z_position: float = -1.0):
        """
        Load a simple ground plane for visualization.
        
        Args:
            z_position: Height of the ground (typically negative)
        """
        print("🌍 Loading ground plane...")
        plane_id = p.loadURDF("plane.urdf", basePosition=(0, 0, z_position))
        print("   ✓ Ground plane loaded\n")
        return plane_id
    
    
    def reset_robot_to_neutral(self):
        """Move all joints back to neutral (zero) position."""
        print("↻ Resetting robot to neutral pose...")
        
        for joint_name in self.joint_indices.keys():
            self.set_joint_angle(joint_name, 0.0)
        
        # Let simulation reach neutral
        self.step_simulation(100)
        print("✓ Robot reset\n")
    
    
    def get_link_position(self, link_name: str) -> Optional[Tuple[float, float, float]]:
        """
        Get 3D position of end effector or any link.
        
        Args:
            link_name: Name of link to query
            
        Returns:
            (x, y, z) position tuple
            
        USE CASE:
        ─────────
        Get end effector position for forward kinematics visualization.
        """
        if link_name not in self.joint_indices:
            return None
        
        joint_idx = self.joint_indices[link_name]
        state = p.getLinkState(self.robot_id, joint_idx)
        position = state[0]  # (x, y, z)
        
        return position
    
    
    def visualize_step(self, dt: float = 0.016):
        """
        Update visualization (only in GUI mode).
        
        Args:
            dt: Sleep time for smooth visualization
        """
        if self.use_gui:
            # This keeps the visualization window responsive
            p.stepSimulation()
    
    
    def close(self):
        """Disconnect from physics engine and cleanup."""
        if self.client_id is not None:
            print("🛑 Closing PyBullet connection...")
            p.disconnect()
            print("✓ Connection closed\n")
    
    
    def print_robot_info(self):
        """Print detailed robot information."""
        print("\n" + "=" * 70)
        print("ROBOT INFORMATION")
        print("=" * 70)
        print(f"Robot ID: {self.robot_id}")
        print(f"Number of joints: {len(self.joint_indices)}")
        print(f"Simulated time: {self.simulated_time:.2f}s")
        print(f"Frames simulated: {self.frame_count}")
        print("\nControllable Joints:")
        print("─" * 70)
        
        for joint_name, info in sorted(self.joint_info.items()):
            current_angle = self.get_joint_angle(joint_name)
            current_deg = np.degrees(current_angle) if current_angle else 0
            limits = f"[{info['lower_limit']:7.2f}°, {info['upper_limit']:7.2f}°]"
            print(f"{joint_name:30s} | {limits} | Current: {current_deg:7.2f}°")
        
        print("=" * 70 + "\n")


# ════════════════════════════════════════════════════════════════
# Example Usage and Testing
# ════════════════════════════════════════════════════════════════

def demo_robot_simulator():
    """
    Demonstrate robot simulator with simple animation.
    """
    print("🎬 Robot Simulator Demo\n")
    
    # Create simulator (use GUI for visualization)
    sim = RobotSimulator(use_gui=True, gravity=(0, 0, -9.81))
    
    try:
        # Load environment
        sim.load_ground_plane(z_position=-0.5)
        
        # Load robot (R2D2 is cute!)
        sim.load_robot("r2d2.urdf", position=(0, 0, 0))
        
        # Print info
        sim.print_robot_info()
        
        # Simple animation: wiggle some joints
        print("🎵 Animating robot...\n")
        
        angle_variation = 0.5  # radians
        for frame in range(200):  # ~3 seconds at 60 Hz
            # Cycle through angles for each joint
            for joint_name in list(sim.joint_indices.keys())[:3]:  # First 3 joints
                phase = (frame * 0.05) % (2 * np.pi)
                target_angle = angle_variation * np.sin(phase)
                sim.set_joint_angle(joint_name, target_angle)
            
            # Step physics
            sim.step_simulation(1)
            
            # Update visualization
            sim.visualize_step()
            
            if frame % 50 == 0:
                print(f"  Frame {frame}: Joints in motion...")
        
        print("\n✓ Animation complete!")
        
        # Keep window open
        print("\n💡 Close the visualization window to exit.")
        
        # Wait for user to close window
        while sim.use_gui:
            sim.visualize_step()
    
    finally:
        sim.close()


def demo_joint_control():
    """
    Demonstrate precise joint control (headless).
    """
    print("🎮 Joint Control Demo (Headless)\n")
    
    # Headless mode for fast testing
    sim = RobotSimulator(use_gui=False, gravity=(0, 0, 0))
    
    try:
        # Simple robot
        sim.load_robot("r2d2.urdf", position=(0, 0, 1))
        
        # Move first 3 joints
        print("Setting joint angles...")
        target_angles = {}
        joint_list = list(sim.joint_indices.keys())[:3]
        
        for i, joint_name in enumerate(joint_list):
            target_angles[joint_name] = (i + 1) * 0.3  # 0.3, 0.6, 0.9 rad
        
        sim.set_all_joint_angles(target_angles)
        
        # Simulate for a bit
        sim.step_simulation(50)
        
        # Read back results
        print("\nJoint positions after control:")
        for joint_name in joint_list:
            angle_rad = sim.get_joint_angle(joint_name)
            angle_deg = np.degrees(angle_rad)
            print(f"  {joint_name}: {angle_deg:.1f}°")
    
    finally:
        sim.close()


if __name__ == "__main__":
    demo_robot_simulator()
    # demo_joint_control()
