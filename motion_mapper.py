#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════
motion_mapper.py — Map Human Angles to Robot Joint Commands
════════════════════════════════════════════════════════════════

This module handles the critical transformation from human pose
to robot-executable commands, including:
- Joint angle scaling and offset adjustment
- Respecting robot mechanical limits (joint limits)
- Mirroring for natural interaction
- Coordinate frame conversions

🎯 WHY MOTION MAPPING IS NEEDED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem: Human angles ≠ Robot angles
───────────────────────────────────
Human arm:
  - Elbow range: typically 0° (fully bent) to 180° (fully extended)
  - Shoulder: very flexible, ~120° range in one direction
  
Robot arm (typical servo-based):
  - Elbow servo: limited to 0°-150° due to motor specs
  - Shoulder servo: limited to -90° to +90° or similar
  
Direct mapping fails:
  - Human throws arm up (160° elbow) → Robot tries 160°
  - Servo overheats or binds trying to achieve impossible position
  - Risk of hardware damage!

Solution: Intelligent mapping
──────────────────────────────
1. Scale human angles to robot range
2. Clamp to limits (safety)
3. Apply offsets (mechanical adjustments)
4. Cache failure states (smoothly handle glitches)

════════════════════════════════════════════════════════════════
"""

import numpy as np
from typing import Dict, Optional, Tuple


class RobotJointConfig:
    """
    Configuration for a single robot joint.
    
    Defines the physical limits and mapping for one degree of freedom.
    
    Attributes:
        name: Joint name (e.g., 'left_elbow')
        min_angle: Minimum joint angle in degrees
        max_angle: Maximum joint angle in degrees
        neutral: Rest position (used as reference)
        invert: If True, negative feedback (mirror motion)
    """
    
    def __init__(self, name: str, min_angle: float, max_angle: float, 
                 neutral: float, invert: bool = False):
        """
        Initialize joint configuration.
        
        Args:
            name: Descriptive joint name
            min_angle: Minimum angle (degrees)
            max_angle: Maximum angle (degrees)
            neutral: Neutral/rest angle (degrees)
            invert: If True, reverse direction (left ↔ right)
            
        Example:
            left_elbow = RobotJointConfig(
                'left_elbow',
                min_angle=10,      # Can't fully bend
                max_angle=160,     # Can't fully extend
                neutral=90,        # Resting at right angle
                invert=False
            )
        """
        self.name = name
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.neutral = neutral
        self.invert = invert
        self.range = max_angle - min_angle
    
    def clamp(self, angle: float) -> float:
        """
        Constrain angle to valid robot range.
        
        Args:
            angle: Desired angle
            
        Returns:
            Angle clamped to [min_angle, max_angle]
            
        SAFETY CRITICAL:
        ────────────────
        Always clamp before sending to robot!
        Protects hardware from physical damage.
        """
        return np.clip(angle, self.min_angle, self.max_angle)
    
    def is_within_limits(self, angle: float) -> bool:
        """Check if angle is achievable by this joint."""
        return self.min_angle <= angle <= self.max_angle
    
    def __repr__(self):
        return (f"RobotJointConfig(name='{self.name}', "
               f"range=[{self.min_angle}°, {self.max_angle}°])")


class JointAngleMapper:
    """
    Converts human joint angles to robot-safe commands.
    
    Handles multiple joints with different configurations and
    applies consistent transformation pipeline.
    """
    
    def __init__(self):
        """Initialize mapper with standard robot configs."""
        self.joint_configs: Dict[str, RobotJointConfig] = {}
        self.last_valid_angles: Dict[str, float] = {}
        
        # Setup standard anthropomorphic robot arm config
        self._setup_default_robot_config()
    
    
    def _setup_default_robot_config(self):
        """
        Define default robot joint limits.
        
        Based on typical 6-DOF robot arm (UR, KUKA style).
        These are example values - adjust for your specific robot!
        
        JOINT LIMITS RATIONALE:
        ──────────────────────
        Real robot servos have mechanical stops that prevent
        over-rotation. Common limits:
        
        - Elbow: 10-160° (can't fully bend or extend)
        - Shoulder: -90 to +90° (limited swing due to base)
        - Wrist: typically ±90° (limited rotation)
        
        Pushing past limits:
        ✗ Overheats motor
        ✗ Damages gearing
        ✗ Wears out mechanical
        ✓ We prevent this with clamping
        """
        
        # ARM JOINTS
        # ══════════════════════════════════════════
        
        # Shoulder flexion/extension (up/down on sagittal plane)
        # Human range: 0-180°, Robot range: 10-160° (respecting limits)
        self.joint_configs['left_shoulder'] = RobotJointConfig(
            'left_shoulder',
            min_angle=20,
            max_angle=160,
            neutral=90,
            invert=False
        )
        
        self.joint_configs['right_shoulder'] = RobotJointConfig(
            'right_shoulder',
            min_angle=20,
            max_angle=160,
            neutral=90,
            invert=True  # Mirror left arm
        )
        
        # Elbow flexion/extension (bending/straightening)
        # Human range: 0-180°, Robot: 15-165° (practical limits)
        self.joint_configs['left_elbow'] = RobotJointConfig(
            'left_elbow',
            min_angle=15,
            max_angle=165,
            neutral=90,
            invert=False
        )
        
        self.joint_configs['right_elbow'] = RobotJointConfig(
            'right_elbow',
            min_angle=15,
            max_angle=165,
            neutral=90,
            invert=True
        )
        
        # Wrist flexion/extension
        self.joint_configs['left_wrist'] = RobotJointConfig(
            'left_wrist',
            min_angle=-45,
            max_angle=45,
            neutral=0,
            invert=False
        )
        
        self.joint_configs['right_wrist'] = RobotJointConfig(
            'right_wrist',
            min_angle=-45,
            max_angle=45,
            neutral=0,
            invert=True
        )
        
        # LEG JOINTS (Lower body)
        # ══════════════════════════════════════════
        
        self.joint_configs['left_hip'] = RobotJointConfig(
            'left_hip',
            min_angle=10,
            max_angle=170,
            neutral=90,
            invert=False
        )
        
        self.joint_configs['right_hip'] = RobotJointConfig(
            'right_hip',
            min_angle=10,
            max_angle=170,
            neutral=90,
            invert=True
        )
        
        self.joint_configs['left_knee'] = RobotJointConfig(
            'left_knee',
            min_angle=0,
            max_angle=160,
            neutral=90,
            invert=False
        )
        
        self.joint_configs['right_knee'] = RobotJointConfig(
            'right_knee',
            min_angle=0,
            max_angle=160,
            neutral=90,
            invert=True
        )
    
    
    def set_joint_config(self, joint_name: str, config: RobotJointConfig):
        """
        Override or add custom joint configuration.
        
        Args:
            joint_name: Name of joint
            config: RobotJointConfig instance
            
        Use case: Adjust limits for your specific hardware
        """
        self.joint_configs[joint_name] = config
    
    
    def _scale_angle(self, human_angle: float, robot_config: RobotJointConfig) -> float:
        """
        Scale human angle to robot joint range.
        
        Args:
            human_angle: Input angle 0-180° (typical human range)
            robot_config: Target robot joint config
            
        Returns:
            Scaled angle in robot's valid range
            
        SCALING FORMULA:
        ────────────────
        
        Example:
        ────────
        Human elbow: 95° (slightly bent)
        Robot elbow range: 15° to 165° (150° total range)
        Human range: 0° to 180° (180° total range)
        
        Normalized human: 95 / 180 = 0.528
        Robot value: 15 + (0.528 × 150) = 15 + 79.2 = 94.2°
        
        This maps ~95° in human → ~94° in robot (very similar!)
        """
        
        if human_angle is None:
            return robot_config.neutral
        
        # Clamp human angle to realistic range (0-180°)
        human_angle = np.clip(human_angle, 0, 180)
        
        # Normalize to [0, 1]
        normalized = human_angle / 180.0
        
        # Scale to robot range
        robot_angle = (robot_config.min_angle + 
                      normalized * robot_config.range)
        
        return robot_angle
    
    
    def _apply_inversion(self, angle: float, 
                        robot_config: RobotJointConfig) -> float:
        """
        Apply axis inversion for mirrored joints.
        
        Args:
            angle: Scaled angle
            robot_config: Joint configuration (has invert flag)
            
        Returns:
            Angle with inversion applied if needed
            
        WHY NEEDED:
        ───────────
        For left/right symmetry:
        
        If user raises right arm → left robot arm should lower
        
        Without inversion:
        - Human right elbow: 95° (bent)
        - Maps to: Robot right elbow: 95°
        - But robot has arms that move together
        - Hard to control individual arms
        
        With inversion:
        - Human right elbow: 95°
        - Maps to: Robot right elbow: 180° - 95° = 85°
        - Creates natural opposite motion
        """
        
        if not robot_config.invert:
            return angle
        
        # Invert around neutral position
        neutral_offset = angle - robot_config.neutral
        inverted_angle = robot_config.neutral - neutral_offset
        
        return inverted_angle
    
    
    def map_angle(self, human_angle: Optional[float], 
                 joint_name: str, 
                 use_last_valid: bool = True) -> float:
        """
        Convert single human angle to robot command.
        
        Args:
            human_angle: Detected human angle (degrees) or None
            joint_name: Name of robot joint to control
            use_last_valid: If True, use last valid angle if current is None
                           (handles brief detection losses)
            
        Returns:
            Safe robot angle (always valid)
            
        SAFETY PIPELINE:
        ────────────────
        1. Get joint config (what are the limits?)
        2. Scale human angle to robot range
        3. Apply inversion if needed (mirror symmetry)
        4. Clamp to limits (enforce mechanics)
        5. Cache result (for gap filling)
        6. Return safe value
        """
        
        # Get this joint's configuration
        if joint_name not in self.joint_configs:
            print(f"⚠️  Unknown joint: {joint_name}")
            return 0.0
        
        config = self.joint_configs[joint_name]
        
        # Handle missing detection
        if human_angle is None:
            if use_last_valid and joint_name in self.last_valid_angles:
                # Use last known good value (holds position during loss)
                return self.last_valid_angles[joint_name]
            else:
                # No data, return neutral
                return config.neutral
        
        # Pipeline:
        # ─────────
        
        # 1. Scale to robot range
        scaled_angle = self._scale_angle(human_angle, config)
        
        # 2. Apply inversion
        inverted_angle = self._apply_inversion(scaled_angle, config)
        
        # 3. Clamp to limits (SAFETY CRITICAL)
        safe_angle = config.clamp(inverted_angle)
        
        # 4. Cache for fallback
        self.last_valid_angles[joint_name] = safe_angle
        
        return safe_angle
    
    
    def map_all_angles(self, human_angles: Dict[str, Optional[float]],
                      use_last_valid: bool = True) -> Dict[str, float]:
        """
        Map all human joint angles to robot commands.
        
        Args:
            human_angles: Dict like {'left_elbow': 95.0, 'right_elbow': None, ...}
            use_last_valid: Hold last known angle during tracking loss
            
        Returns:
            Dict of safe robot angles for all joints
            
        Example input:
            {
                'left_elbow': 92.3,
                'right_elbow': 87.1,
                'left_shoulder': 125.0,
                'right_shoulder': None,  # Detection failed
                ...
            }
        
        Example output:
            {
                'left_elbow': 92.3,
                'right_elbow': 87.0,
                'left_shoulder': 124.8,
                'right_shoulder': 90.0,  # Returned to neutral
                ...
            }
        """
        robot_angles = {}
        
        for joint_name, human_angle in human_angles.items():
            robot_angles[joint_name] = self.map_angle(
                human_angle, joint_name, use_last_valid
            )
        
        return robot_angles
    
    
    def get_joint_info(self, joint_name: str) -> Optional[RobotJointConfig]:
        """Get configuration for specific joint."""
        return self.joint_configs.get(joint_name)
    
    
    def print_robot_config(self):
        """Print full robot configuration (useful for debugging)."""
        print("\n📋 ROBOT JOINT CONFIGURATION")
        print("═" * 70)
        
        for joint_name, config in sorted(self.joint_configs.items()):
            invert_marker = " (INVERTED)" if config.invert else ""
            print(f"{joint_name:20s} | Range: [{config.min_angle:6.1f}°, {config.max_angle:6.1f}°] "
                  f"| Neutral: {config.neutral:6.1f}°{invert_marker}")
        
        print("═" * 70 + "\n")


# ════════════════════════════════════════════════════════════════
# Example Usage and Testing
# ════════════════════════════════════════════════════════════════

def demo_motion_mapping():
    """
    Demonstrate motion mapping with examples.
    """
    print("🎮 Motion Mapping Demo\n")
    
    # Create mapper
    mapper = JointAngleMapper()
    
    # Show configuration
    mapper.print_robot_config()
    
    # ━━━━ TEST 1: Normal angle mapping ━━━━
    print("TEST 1: Normal Human → Robot Mapping")
    print("─" * 50)
    
    human_angles = {
        'left_elbow': 95.0,       # Slightly bent
        'right_elbow': 85.0,      # More bent
        'left_shoulder': 120.0,   # Arm raised
        'right_shoulder': None,   # Lost detection
    }
    
    robot_angles = mapper.map_all_angles(human_angles)
    
    print(f"Human left_elbow (95.0°) → Robot: {robot_angles['left_elbow']:.1f}°")
    print(f"Human right_elbow (85.0°) → Robot: {robot_angles['right_elbow']:.1f}°")
    print(f"Human left_shoulder (120.0°) → Robot: {robot_angles['left_shoulder']:.1f}°")
    print(f"Human right_shoulder (None) → Robot: {robot_angles['right_shoulder']:.1f}° (fallback to neutral)")
    
    # ━━━━ TEST 2: Extreme angles (should be clamped) ━━━━
    print("\n\nTEST 2: Extreme Angles (Clamping)")
    print("─" * 50)
    
    extreme_angles = {
        'left_elbow': 0.0,        # Impossibly bent
        'right_elbow': 180.0,     # Perfectly straight
    }
    
    safe_angles = mapper.map_all_angles(extreme_angles, use_last_valid=False)
    
    print(f"Human left_elbow (0.0°, extreme) → Robot: {safe_angles['left_elbow']:.1f}°")
    print(f"Human right_elbow (180.0°, straight) → Robot: {safe_angles['right_elbow']:.1f}°")
    print("⚠️  Both clamped to safe ranges!")
    
    # ━━━━ TEST 3: Demonstrate inversion ━━━━
    print("\n\nTEST 3: Left/Right Symmetry (Inversion)")
    print("─" * 50)
    
    symmetry_angles = {
        'left_elbow': 95.0,
        'right_elbow': 95.0,
    }
    
    sym_result = mapper.map_all_angles(symmetry_angles, use_last_valid=False)
    
    print(f"Left elbow (95.0°)  → Robot: {sym_result['left_elbow']:.1f}°")
    print(f"Right elbow (95.0°) → Robot: {sym_result['right_elbow']:.1f}°")
    print("(Right is inverted for mirror motion)")


def demo_angle_scaling():
    """
    Show detailed angle scaling example.
    """
    print("\n\n📊 ANGLE SCALING DETAILED EXAMPLE")
    print("═" * 70)
    
    mapper = JointAngleMapper()
    config = mapper.get_joint_info('left_elbow')
    
    print(f"\nJoint: {config.name}")
    print(f"Robot range: [{config.min_angle}°, {config.max_angle}°]")
    print(f"Robot neutral: {config.neutral}°")
    
    print("\nScaling human angles:")
    print("─" * 50)
    print(f"{'Human Angle':>12} | {'Normalized':>12} | {'Robot Angle':>12}")
    print("─" * 50)
    
    for human_deg in [0, 30, 60, 90, 120, 150, 180]:
        robot = mapper.map_angle(float(human_deg), 'left_elbow', 
                               use_last_valid=False)
        norm = human_deg / 180.0
        print(f"{human_deg:12.0f}° | {norm:12.3f} | {robot:12.1f}°")
    
    print("=" * 70)


if __name__ == "__main__":
    demo_motion_mapping()
    demo_angle_scaling()
