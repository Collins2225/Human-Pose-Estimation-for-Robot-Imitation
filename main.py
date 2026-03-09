"""
===================================================================
MODULE 5: main.py — Real-Time HRI System Orchestrator
===================================================================

MENTOR EXPLANATION:
This is the final piece that wires everything together.
Every frame (~33ms at 30fps), the loop does exactly 5 things:

  1. SENSE    → Capture webcam frame + detect pose
  2. COMPUTE  → Calculate joint angles from landmarks  
  3. FILTER   → Smooth noisy angle data
  4. ACTUATE  → Send angles to robot + step physics
  5. DISPLAY  → Show annotated webcam feed with HUD

Compatible with the updated PoseDetector (MediaPipe 0.10.32+).
===================================================================
"""

import cv2
import numpy as np
import time
import sys

from pose_detector import PoseDetector
from angle_calculator import AngleCalculator
from signal_filters import MultiJointFilter
from robot_controller import RobotController


class HRISystem:
    """
    Real-time Human-Robot Interaction system.

    MENTOR NOTE on the class design:
    We wrap everything in a class so that:
    - All components are initialized in one place (__init__)
    - The run loop stays clean and readable
    - Cleanup is guaranteed via _cleanup()
    - State (frame count, FPS history, latest angles) is shared
      easily between methods without global variables
    """

    def __init__(self,
                 camera_index: int = 0,
                 target_fps: int = 30,
                 filter_window: int = 5,
                 filter_alpha: float = 0.3):

        print("╔══════════════════════════════════════╗")
        print("║   Human-Robot Interaction System     ║")
        print("╚══════════════════════════════════════╝\n")

        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps

        # Performance tracking
        self.frame_count = 0
        self.fps_history = []

        # System state
        self.is_running = False
        self.person_detected = False
        self._latest_angles = {}
        self._latest_raw_angles = {}

        # ── 1. Camera ─────────────────────────────────────────
        print(f"[1/4] Opening webcam (index {camera_index})...")
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Cannot open webcam at index {camera_index}.\n"
                "Try changing camera_index to 1 in the CONFIG dict."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, target_fps)
        print(f"    Camera ready ✓\n")

        # ── 2. Pose Detector ──────────────────────────────────
        print("[2/4] Loading MediaPipe Pose model...")
        self.detector = PoseDetector(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        print()

        # ── 3. Angle Calculator + Filter ──────────────────────
        print("[3/4] Setting up angle calculator and filter...")
        self.angle_calc = AngleCalculator()
        self.sig_filter = MultiJointFilter()
        print(f"    Angle calculator ready ✓")
        print(f"    Signal filter ready ✓\n")

        # ── 4. Robot Simulation ───────────────────────────────
        print("[4/4] Starting PyBullet simulation...")
        self.robot = RobotController(use_gui=True)
        print()

        print("━"*45)
        print("  ✅ System ready! Controls:")
        print("     Q = Quit   R = Reset robot   P = Pause")
        print("━"*45)
        print("  Stand 1.5–2m from camera with arms visible.\n")

    def run(self):
        """
        Main real-time control loop.

        MENTOR NOTE on loop timing:
        We measure how long each iteration takes, then sleep for the
        remaining budget. At 30fps, each frame has 33ms total:

          processing_time + sleep_time = 33ms

        If processing takes 25ms → sleep 8ms  (easy frame)
        If processing takes 35ms → sleep 0ms  (over budget, skip sleep)

        This keeps the robot running at a consistent speed regardless
        of how fast or slow the CPU processes each frame.
        """
        self.is_running = True
        paused = False

        while self.is_running:
            loop_start = time.time()

            # ── Keyboard input ────────────────────────────────
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nQ pressed — quitting...")
                break
            elif key == ord('r'):
                self.robot.reset_to_home()
                self.sig_filter.reset()
                print("  Robot reset to home position.")
            elif key == ord('p'):
                paused = not paused
                print(f"  {'⏸ Paused' if paused else '▶ Resumed'}.")

            if paused:
                time.sleep(0.05)
                continue

            # ── STEP 1: Capture frame ─────────────────────────
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame = cv2.flip(frame, 1)  # Mirror (feels more natural)

            # ── STEP 2: Detect pose ───────────────────────────
            annotated_frame, landmarks = self.detector.process_frame(frame)
            self.person_detected = landmarks is not None

            # ── STEP 3: Compute joint angles ──────────────────
            raw_angles = self.angle_calc.get_all_angles(landmarks)
            self._latest_raw_angles = raw_angles

            # ── STEP 4: Filter angles ─────────────────────────
            if raw_angles:
                filtered_angles = self.sig_filter.filter_angles(raw_angles)
            else:
                filtered_angles = self._latest_angles or {}
            self._latest_angles = filtered_angles

            # ── STEP 5: Control robot ─────────────────────────
            if filtered_angles:
                robot_joints = self.robot.map_human_angles_to_robot(
                    filtered_angles
                )
                self.robot.set_joint_targets(robot_joints)

            # Step physics simulation (4 sub-steps for stability)
            for _ in range(4):
                self.robot.step_simulation()

            # Update robot window overlay text
            if filtered_angles.get("left_elbow_flexion"):
                ef = filtered_angles["left_elbow_flexion"]
                se = filtered_angles.get("left_shoulder_elev") or 0
                self.robot.add_debug_text(
                    f"L.Elbow: {ef:.0f}deg  L.Shoulder: {se:.0f}deg",
                    position=[0, 0, 1.8],
                    color=[0.2, 1.0, 0.2]
                )

            # ── STEP 6: Draw HUD + display ────────────────────
            self._draw_hud(annotated_frame)
            cv2.imshow("HRI System — Pose Control", annotated_frame)

            # ── STEP 7: Frame rate management ─────────────────
            self.frame_count += 1
            elapsed = time.time() - loop_start
            actual_fps = 1.0 / elapsed if elapsed > 0 else 0
            self.fps_history.append(actual_fps)
            if len(self.fps_history) > 30:
                self.fps_history.pop(0)

            sleep_time = self.frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup()

    def _draw_hud(self, frame: np.ndarray):
        """
        Draw Heads-Up Display on the camera frame.

        MENTOR NOTE:
        The HUD gives you real-time visibility into the pipeline:
          - Are joints being detected?
          - What raw angle is MediaPipe returning?
          - What smoothed angle is the robot receiving?
          - Is the filter actually making a difference?

        The angle bars (right side) give a quick visual feel for
        joint positions without having to read numbers.
        """
        h, w = frame.shape[:2]

        # Semi-transparent dark background panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 195), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        # Detection status
        if self.person_detected:
            status_text, status_color = "TRACKING  ✓", (0, 220, 0)
        else:
            status_text, status_color = "NO PERSON DETECTED", (0, 60, 255)

        cv2.putText(frame, status_text, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        # FPS counter
        avg_fps = np.mean(self.fps_history) if self.fps_history else 0
        fps_color = (0, 220, 0) if avg_fps >= 24 else (0, 140, 255)
        cv2.putText(frame, f"FPS: {avg_fps:.1f}", (w - 115, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 2)

        # Joint angle rows
        angles = self._latest_angles
        raw    = self._latest_raw_angles
        y = 58

        def draw_row(label, key, y_pos):
            raw_v  = raw.get(key)
            filt_v = angles.get(key)
            raw_s  = f"{raw_v:.1f}d"  if raw_v  is not None else "---"
            flt_s  = f"{filt_v:.1f}d" if filt_v is not None else "---"

            cv2.putText(frame, f"{label}:", (10, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            cv2.putText(frame, f"Raw:{raw_s}", (168, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 190, 255), 1)
            cv2.putText(frame, f"Filt:{flt_s}", (278, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 255, 120), 1)

            # Angle progress bar
            if filt_v is not None:
                bx, bw = 398, 180
                ratio = np.clip(filt_v / 180.0, 0, 1)
                cv2.rectangle(frame, (bx, y_pos-10), (bx+bw, y_pos+2),
                              (45, 45, 45), -1)
                cv2.rectangle(frame, (bx, y_pos-10),
                              (bx + int(bw * ratio), y_pos+2),
                              (60, 220, 100), -1)

        draw_row("L.Elbow Flex",    "left_elbow_flexion",  y);  y += 26
        draw_row("L.Shoulder Elev", "left_shoulder_elev",  y);  y += 26
        draw_row("L.Shoulder Abd",  "left_shoulder_abd",   y);  y += 26
        draw_row("R.Elbow Flex",    "right_elbow_flexion", y);  y += 26
        draw_row("R.Shoulder Elev", "right_shoulder_elev", y);  y += 26

        # Bottom bar
        cv2.putText(frame, "[Q] Quit  [R] Reset  [P] Pause",
                    (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (130, 130, 130), 1)
        cv2.putText(frame, f"Frame {self.frame_count}",
                    (w - 120, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (100, 100, 100), 1)

    def _cleanup(self):
        """Release all resources cleanly."""
        print("\nShutting down system...")
        self.is_running = False
        self.cap.release()
        self.detector.release()
        self.robot.disconnect()
        cv2.destroyAllWindows()

        avg_fps = np.mean(self.fps_history) if self.fps_history else 0
        duration = self.frame_count / max(avg_fps, 1)

        print("\n┌─── Session Summary ───────────────────┐")
        print(f"│  Total frames : {self.frame_count:<6}                 │")
        print(f"│  Average FPS  : {avg_fps:<6.1f}                 │")
        print(f"│  Session time : {duration:<6.1f}s                │")
        print("└───────────────────────────────────────┘")
        print("Goodbye! 👋")


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":

    CONFIG = {
        "camera_index":  0,     # Try 1 if 0 doesn't open
        "target_fps":    30,    # Frames per second
        "filter_window": 5,     # Moving average window (larger = smoother)
        "filter_alpha":  0.3,   # EMA factor (smaller = smoother, more lag)
    }

    try:
        system = HRISystem(**CONFIG)
        system.run()
    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C)")