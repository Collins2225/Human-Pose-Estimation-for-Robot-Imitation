#!/usr/bin/env python3
"""Test if all modules can be imported without errors."""

print("Testing imports...")

try:
    print("  1. Importing pose_detector...", end=" ")
    from pose_detector import PoseDetector
    print("✓")
except Exception as e:
    print(f"✗ Error: {e}")

try:
    print("  2. Importing joint_angle_extractor...", end=" ")
    from joint_angle_extractor import JointAngleExtractor
    print("✓")
except Exception as e:
    print(f"✗ Error: {e}")

try:
    print("  3. Importing signal_filters...", end=" ")
    from signal_filters import MultiJointFilter
    print("✓")
except Exception as e:
    print(f"✗ Error: {e}")

try:
    print("  4. Importing motion_mapper...", end=" ")
    from motion_mapper import JointAngleMapper
    print("✓")
except Exception as e:
    print(f"✗ Error: {e}")

try:
    print("  5. Importing robot_controller...", end=" ")
    from robot_controller import RobotController
    print("✓")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n✓ All imports successful!")
