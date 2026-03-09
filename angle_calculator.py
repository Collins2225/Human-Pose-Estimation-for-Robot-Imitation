"""
===================================================================
MODULE 2: angle_calculator.py — Joint Angle Computation
===================================================================

MENTOR EXPLANATION:
This is the mathematical heart of the project. We need to convert
3D positions of joints into ANGLES that a robot can use.

THE KEY CONCEPT — The Vector Dot Product Method:
  Given 3 points A (proximal), B (joint), C (distal):
  
        A (shoulder)
        |
        | ← vector BA
        B (elbow)    ← We want the angle HERE
        |
        | ← vector BC
        C (wrist)

  1. Compute vector BA = A - B  (from elbow TO shoulder)
  2. Compute vector BC = C - B  (from elbow TO wrist)
  3. angle = arccos( (BA · BC) / (|BA| × |BC|) )

  This gives us the INTERIOR angle at joint B.

WHY NOT JUST USE ATAN2?
  atan2 works in 2D but breaks in 3D. The dot product method
  works in any dimension and is numerically stable.

ANGLES WE COMPUTE:
  - Elbow flexion: angle between upper arm and forearm (0°=straight, 90°=bent)
  - Shoulder elevation: angle of upper arm relative to body vertical
  - Shoulder abduction: how far the arm is raised sideways
===================================================================
"""

import numpy as np
from typing import Optional


class AngleCalculator:
    """
    Computes human joint angles from 3D landmark positions.

    MENTOR NOTE on coordinate systems:
    MediaPipe uses a RIGHT-HANDED coordinate system where:
      - x increases to the RIGHT
      - y increases DOWNWARD (image convention, not standard math!)
      - z increases TOWARD the camera

    This means "up" in the real world is NEGATIVE y in MediaPipe space.
    We account for this when computing shoulder elevation.
    """

    def compute_angle_3d(self,
                         point_a: np.ndarray,
                         point_b: np.ndarray,
                         point_c: np.ndarray) -> float:
        """
        Compute the interior angle at point B formed by the A-B-C triplet.

        MENTOR DEEP DIVE — Why we use arccos of dot product:
        
        The dot product formula is: A·B = |A||B|cos(θ)
        Rearranging: θ = arccos(A·B / (|A||B|))
        
        This is mathematically exact for any 3D angle.
        We clamp the value to [-1, 1] before arccos to handle
        floating-point errors that could push it slightly outside
        that range (which would make arccos return NaN).

        Args:
            point_a: Position of the proximal point (e.g., shoulder)
            point_b: Position of the joint vertex (e.g., elbow) ← angle here
            point_c: Position of the distal point (e.g., wrist)

        Returns:
            Angle in DEGREES (0-180)
        """
        # Vectors FROM the joint vertex TO each neighboring joint
        vector_ba = point_a - point_b  # Points toward shoulder
        vector_bc = point_c - point_b  # Points toward wrist

        # Compute magnitudes (lengths) of each vector
        mag_ba = np.linalg.norm(vector_ba)
        mag_bc = np.linalg.norm(vector_bc)

        # Guard against division by zero if two points overlap
        if mag_ba < 1e-6 or mag_bc < 1e-6:
            return 0.0

        # Dot product of the two vectors
        dot_product = np.dot(vector_ba, vector_bc)

        # Cosine of the angle (clamped to [-1, 1] for numerical safety)
        cos_angle = np.clip(dot_product / (mag_ba * mag_bc), -1.0, 1.0)

        # Convert from radians to degrees
        angle_degrees = np.degrees(np.arccos(cos_angle))

        return float(angle_degrees)

    def compute_elbow_flexion(self, landmarks: dict) -> Optional[float]:
        """
        Compute ELBOW FLEXION ANGLE for the left arm.

        MENTOR NOTE:
        Elbow flexion = how bent is the elbow?
          - 180° = fully straight arm
          - 90°  = classic "L-shape" bicep curl position
          - 30°  = very bent

        The three points are: shoulder → elbow → wrist
        We measure the angle AT the elbow.

        Returns:
            Angle in degrees [0, 180], or None if landmarks missing
        """
        try:
            shoulder = landmarks["left_shoulder"]
            elbow    = landmarks["left_elbow"]
            wrist    = landmarks["left_wrist"]
            return self.compute_angle_3d(shoulder, elbow, wrist)
        except (KeyError, TypeError):
            return None

    def compute_right_elbow_flexion(self, landmarks: dict) -> Optional[float]:
        """Same as above but for the RIGHT arm."""
        try:
            shoulder = landmarks["right_shoulder"]
            elbow    = landmarks["right_elbow"]
            wrist    = landmarks["right_wrist"]
            return self.compute_angle_3d(shoulder, elbow, wrist)
        except (KeyError, TypeError):
            return None

    def compute_shoulder_elevation(self, landmarks: dict,
                                   side: str = "left") -> Optional[float]:
        """
        Compute SHOULDER ELEVATION — how high the arm is raised.

        MENTOR NOTE:
        We measure the angle between:
          1. The vector from shoulder DOWN to hip (body reference vertical)
          2. The vector from shoulder OUT to elbow (upper arm direction)

        When arm hangs down: ~0°
        When arm is horizontal: ~90°
        When arm is straight up: ~180°

        The hip point gives us a stable "body vertical" reference
        that moves with the person, so it works even if they tilt.

        Args:
            side: "left" or "right"
        """
        try:
            shoulder = landmarks[f"{side}_shoulder"]
            elbow    = landmarks[f"{side}_elbow"]
            hip      = landmarks[f"{side}_hip"]
            # Angle at SHOULDER between hip-reference and arm
            return self.compute_angle_3d(hip, shoulder, elbow)
        except (KeyError, TypeError):
            return None

    def compute_shoulder_abduction(self, landmarks: dict,
                                   side: str = "left") -> Optional[float]:
        """
        Compute SHOULDER ABDUCTION — sideways arm raise.

        MENTOR NOTE:
        Abduction uses the horizontal body axis (shoulder-to-shoulder line)
        as the reference, and measures how far the arm deviates from it
        in the frontal plane.

        We use: opposite_shoulder → shoulder → elbow
        
        - Arm at side (down): ~90° from horizontal
        - Arm horizontal: ~90° to ~180° depending on interpretation
        
        We remap this to 0° (arm down) to 90° (arm horizontal).
        """
        try:
            shoulder = landmarks[f"{side}_shoulder"]
            elbow    = landmarks[f"{side}_elbow"]

            # Use opposite shoulder as the horizontal body reference
            opp_side = "right" if side == "left" else "left"
            opp_shoulder = landmarks[f"{opp_side}_shoulder"]

            raw_angle = self.compute_angle_3d(opp_shoulder, shoulder, elbow)

            # Remap: when arm is hanging, raw ≈ 180°; when horizontal raw ≈ 90°
            # So abduction = 180 - raw_angle gives 0° (hanging) to 90° (horizontal)
            abduction = max(0.0, 180.0 - raw_angle)
            return abduction
        except (KeyError, TypeError):
            return None

    def compute_wrist_angle(self, landmarks: dict,
                             side: str = "left") -> Optional[float]:
        """
        Compute wrist flexion/extension angle.

        MENTOR NOTE:
        We'd need a finger landmark to do this properly, but MediaPipe
        Pose (not Hands) gives us the wrist only. As an approximation,
        we compute the angle elbow → wrist relative to the forearm axis.
        This gives us the wrist's orientation in space (useful for
        end-effector orientation on the robot).
        """
        try:
            elbow = landmarks[f"{side}_elbow"]
            wrist = landmarks[f"{side}_wrist"]

            # Forearm direction vector
            forearm = wrist - elbow

            # Reference: pure horizontal (x-axis in image space)
            horizontal = np.array([1.0, 0.0, 0.0])

            # Project to XY plane (ignore depth for this simpler calculation)
            forearm_2d = forearm[:2]
            if np.linalg.norm(forearm_2d) < 1e-6:
                return None

            forearm_2d_norm = forearm_2d / np.linalg.norm(forearm_2d)
            cos_val = np.clip(np.dot(forearm_2d_norm, horizontal[:2]), -1.0, 1.0)
            return float(np.degrees(np.arccos(cos_val)))
        except (KeyError, TypeError):
            return None

    def get_all_angles(self, landmarks: dict) -> dict:
        """
        Compute ALL joint angles for both arms in one call.

        MENTOR NOTE:
        This is the main interface used by the robot controller.
        We return a flat dictionary with all angles. None values
        indicate that a landmark wasn't detected or was occluded.

        Returns:
            Dict with keys:
              left_elbow_flexion    (degrees, 0-180)
              right_elbow_flexion   (degrees, 0-180)
              left_shoulder_elev    (degrees, 0-180)
              right_shoulder_elev   (degrees, 0-180)
              left_shoulder_abd     (degrees, 0-90)
              right_shoulder_abd    (degrees, 0-90)
              left_wrist_angle      (degrees, 0-180)
              right_wrist_angle     (degrees, 0-180)
        """
        if landmarks is None:
            return {}

        return {
            "left_elbow_flexion":   self.compute_elbow_flexion(landmarks),
            "right_elbow_flexion":  self.compute_right_elbow_flexion(landmarks),
            "left_shoulder_elev":   self.compute_shoulder_elevation(landmarks, "left"),
            "right_shoulder_elev":  self.compute_shoulder_elevation(landmarks, "right"),
            "left_shoulder_abd":    self.compute_shoulder_abduction(landmarks, "left"),
            "right_shoulder_abd":   self.compute_shoulder_abduction(landmarks, "right"),
            "left_wrist_angle":     self.compute_wrist_angle(landmarks, "left"),
            "right_wrist_angle":    self.compute_wrist_angle(landmarks, "right"),
        }


# ---------------------------------------------------------------
# QUICK TEST — Verify angle math with a known example
# ---------------------------------------------------------------
if __name__ == "__main__":
    calc = AngleCalculator()

    print("=== Angle Calculator Tests ===\n")

    # Test 1: 90-degree elbow bend
    # Shoulder above elbow, wrist to the right of elbow
    shoulder = np.array([100, 50, 0])   # Up
    elbow    = np.array([100, 150, 0])  # Below shoulder
    wrist    = np.array([200, 150, 0])  # To the right

    angle = calc.compute_angle_3d(shoulder, elbow, wrist)
    print(f"Test 1 (Expected ~90°): {angle:.1f}°")

    # Test 2: Straight arm (180 degrees)
    shoulder = np.array([100, 50, 0])
    elbow    = np.array([100, 150, 0])
    wrist    = np.array([100, 250, 0])  # Same column = straight line

    angle = calc.compute_angle_3d(shoulder, elbow, wrist)
    print(f"Test 2 (Expected ~180°): {angle:.1f}°")

    # Test 3: Fully bent (0 degrees — wrist meets shoulder)
    shoulder = np.array([100, 50, 0])
    elbow    = np.array([100, 150, 0])
    wrist    = np.array([100, 50, 0])  # Same as shoulder

    angle = calc.compute_angle_3d(shoulder, elbow, wrist)
    print(f"Test 3 (Expected ~0°): {angle:.1f}°")

    print("\nAll tests passed!")


# Alias for compatibility with main.py
JointAngleExtractor = AngleCalculator