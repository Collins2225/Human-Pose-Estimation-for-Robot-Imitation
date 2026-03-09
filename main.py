"""
===================================================================
MODULE 5: main.py — Real-Time HRI System Orchestrator
===================================================================

MENTOR EXPLANATION:
This is the "brain" that wires everything together into a real-time
control loop. Think of it as the conductor of an orchestra — it doesn't
play an instrument itself, but coordinates every musician perfectly.

THE REAL-TIME CONTROL LOOP:
Every frame (~33ms for 30fps), we:
  1. SENSE:    Capture webcam frame + detect pose
  2. COMPUTE:  Calculate joint angles from landmarks
  3. FILTER:   Smooth noisy angle data
  4. ACTUATE:  Send angles to robot + advance simulation
  5. DISPLAY:  Show annotated webcam feed + HUD overlay
  6. REPEAT

PERFORMANCE CONSIDERATIONS:
- Target: 30fps (33ms per loop iteration)
- MediaPipe takes ~15-25ms on CPU (usually our bottleneck)
- PyBullet physics takes ~1-5ms
- We use time.sleep() to maintain consistent frame rate

THREADING NOTE:
For production systems, pose detection and physics simulation would
run on separate threads. For this educational project, we run them
sequentially (simpler to understand, still works at 30fps).
===================================================================
"""

import cv2
import numpy as np
import time
import sys
from datetime import datetime

# Import our custom modules
from pose_detector import PoseDetector
from angle_calculator import AngleCalculator
from signal_filter import CombinedFilter
from robot_controller import RobotController


class HRISystem:
    """
    Real-time Human-Robot Interaction system.

    Orchestrates pose detection → angle computation → filtering →
    robot control in a live loop.
    """

    def __init__(self,
                 camera_index: int = 0,
                 target_fps: int = 30,
                 filter_window: int = 5,
                 filter_alpha: float = 0.3):
        """
        Initialize all system components.

        MENTOR NOTE on dependency order:
        We initialize in this specific order because:
        1. Camera first — we want to test it ASAP
        2. Pose detector — depends on having a camera
        3. Math modules — no dependencies, fast
        4. Robot LAST — PyBullet GUI takes time to open

        Args:
            camera_index: Webcam index (0=default, 1=external, etc.)
            target_fps:   Desired frame rate (30 is typical for webcams)
            filter_window: Moving average window size
            filter_alpha:  EMA smoothing factor (0.1-0.9)
        """
        print("╔══════════════════════════════════════╗")
        print("║  Human-Robot Interaction System HRI  ║")
        print("╚══════════════════════════════════════╝\n")

        self.target_fps = target_fps
        self.frame_time = 1.0 / target_fps  # Seconds per frame

        # Performance tracking
        self.frame_count = 0
        self.fps_history = []
        self.last_frame_time = time.time()

        # System state
        self.is_running = False
        self.person_detected = False

        # --- Initialize Camera ---
        print(f"[1/4] Opening webcam (index {camera_index})...")
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open webcam at index {camera_index}. "
                               "Check if it's connected and not in use.")

        # Set camera resolution and FPS
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, target_fps)
        print(f"    Camera ready: {int(self.cap.get(3))}x{int(self.cap.get(4))} @ {target_fps}fps ✓")

        # --- Initialize Pose Detector ---
        print("[2/4] Loading MediaPipe Pose model...")
        self.detector = PoseDetector(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        print("    Pose model loaded ✓")

        # --- Initialize Angle Calculator ---
        print("[3/4] Setting up angle calculator...")
        self.angle_calc = AngleCalculator()
        print("    Angle calculator ready ✓")

        # --- Initialize Signal Filter ---
        self.sig_filter = CombinedFilter(
            window_size=filter_window,
            alpha=filter_alpha
        )
        print(f"    Signal filter ready (window={filter_window}, α={filter_alpha}) ✓")

        # --- Initialize Robot Simulation ---
        print("[4/4] Starting PyBullet simulation...")
        self.robot = RobotController(use_gui=True)
        print("    Robot simulation ready ✓\n")

        print("System initialized! Stand in front of the camera.")
        print("Press 'q' to quit | 'r' to reset robot | 'p' to pause\n")

        # Store latest data for HUD display
        self._latest_angles = {}
        self._latest_raw_angles = {}

    def run(self):
        """
        Main real-time control loop.

        MENTOR DEEP DIVE — The Loop Structure:
        
        This while loop is the core of every real-time system.
        Each iteration is called a "frame" or "tick."
        
        The timing logic at the bottom (time.sleep) is important:
        - We measure how long processing took
        - We sleep for the REMAINDER of the frame budget
        - This maintains consistent timing regardless of processing load
        
        Example at 30fps (33ms budget):
          If processing took 20ms → sleep 13ms
          If processing took 33ms → sleep 0ms (no sleep, already over budget)
        """
        self.is_running = True
        paused = False

        while self.is_running:
            loop_start = time.time()

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\nQuitting...")
                break
            elif key == ord('r'):
                self.robot.reset_to_home()
                self.sig_filter.reset()
                print("Robot reset to home position.")
            elif key == ord('p'):
                paused = not paused
                print(f"{'Paused' if paused else 'Resumed'}.")

            if paused:
                time.sleep(0.1)
                continue

            # ── STEP 1: CAPTURE FRAME ──────────────────────────────
            ret, frame = self.cap.read()
            if not ret:
                print("Warning: Failed to capture frame, retrying...")
                time.sleep(0.01)
                continue

            # Mirror the frame (more intuitive — like a mirror)
            frame = cv2.flip(frame, 1)

            # ── STEP 2: DETECT POSE ───────────────────────────────
            annotated_frame, landmarks = self.detector.process_frame(frame)
            self.person_detected = landmarks is not None

            # ── STEP 3: COMPUTE JOINT ANGLES ──────────────────────
            raw_angles = self.angle_calc.get_all_angles(landmarks)
            self._latest_raw_angles = raw_angles

            # ── STEP 4: FILTER ANGLES ─────────────────────────────
            if raw_angles:
                filtered_angles = self.sig_filter.filter_all(raw_angles)
            else:
                # No person detected — use last filtered values (stability)
                filtered_angles = self._latest_angles or {}

            self._latest_angles = filtered_angles

            # ── STEP 5: CONTROL ROBOT ─────────────────────────────
            if filtered_angles:
                robot_joint_angles = self.robot.map_human_angles_to_robot(
                    filtered_angles
                )
                self.robot.set_joint_targets(robot_joint_angles)

            # Advance physics simulation (multiple steps for stability)
            for _ in range(4):  # 4 physics steps per control frame
                self.robot.step_simulation()

            # Update robot HUD text
            if filtered_angles.get("left_elbow_flexion"):
                ef = filtered_angles["left_elbow_flexion"]
                se = filtered_angles.get("left_shoulder_elev", 0) or 0
                self.robot.add_debug_text(
                    f"L.Elbow: {ef:.0f}°  L.Shoulder: {se:.0f}°",
                    position=[0, 0, 1.8],
                    color=[0.2, 1.0, 0.2]
                )

            # ── STEP 6: UPDATE DISPLAY ────────────────────────────
            self._draw_hud(annotated_frame)
            cv2.imshow("HRI System — Pose Control", annotated_frame)

            # ── STEP 7: FRAME RATE MANAGEMENT ────────────────────
            self.frame_count += 1
            elapsed = time.time() - loop_start

            # Track actual FPS
            actual_fps = 1.0 / elapsed if elapsed > 0 else 0
            self.fps_history.append(actual_fps)
            if len(self.fps_history) > 30:
                self.fps_history.pop(0)

            # Sleep if we have budget remaining
            sleep_time = self.frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup()

    def _draw_hud(self, frame: np.ndarray):
        """
        Draw the Heads-Up Display (HUD) overlay on the camera frame.

        MENTOR NOTE on HUD design:
        The HUD gives real-time feedback about what the system is doing.
        This is crucial for debugging — you can see if angles are being
        detected correctly and whether the robot should be moving.

        We draw:
        1. Status bar (detection status, FPS)
        2. Joint angle readouts (raw vs filtered)
        3. Instructions
        4. Visual angle bars
        """
        h, w = frame.shape[:2]

        # --- Background panel for HUD text ---
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 180), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

        # --- Detection status ---
        status_text = "TRACKING" if self.person_detected else "NO PERSON DETECTED"
        status_color = (0, 255, 100) if self.person_detected else (0, 80, 255)
        cv2.putText(frame, status_text, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        # --- FPS counter ---
        avg_fps = np.mean(self.fps_history) if self.fps_history else 0
        fps_text = f"FPS: {avg_fps:.1f}"
        fps_color = (0, 255, 0) if avg_fps >= 25 else (0, 165, 255)
        cv2.putText(frame, fps_text, (w - 120, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 2)

        # --- Joint angle readouts ---
        angles = self._latest_angles
        y_pos = 60

        def draw_angle_row(label, key, y):
            raw_val = self._latest_raw_angles.get(key)
            filt_val = angles.get(key)

            raw_str  = f"{raw_val:.1f}°"  if raw_val  is not None else "---"
            filt_str = f"{filt_val:.1f}°" if filt_val is not None else "---"

            cv2.putText(frame, f"{label}:", (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(frame, f"Raw:{raw_str}", (170, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 255), 1)
            cv2.putText(frame, f"Filtered:{filt_str}", (290, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)

            # Draw angle bar if we have data
            if filt_val is not None:
                bar_x = 460
                bar_w = 150
                bar_ratio = np.clip(filt_val / 180.0, 0, 1)
                cv2.rectangle(frame, (bar_x, y-10), (bar_x + bar_w, y+2),
                              (50, 50, 50), -1)
                cv2.rectangle(frame, (bar_x, y-10),
                              (bar_x + int(bar_w * bar_ratio), y+2),
                              (100, 255, 100), -1)

        draw_angle_row("L.Elbow Flex",   "left_elbow_flexion",  y_pos);    y_pos += 25
        draw_angle_row("L.Shoulder Elev","left_shoulder_elev",  y_pos);    y_pos += 25
        draw_angle_row("L.Shoulder Abd", "left_shoulder_abd",   y_pos);    y_pos += 25
        draw_angle_row("R.Elbow Flex",   "right_elbow_flexion", y_pos);    y_pos += 25
        draw_angle_row("R.Shoulder Elev","right_shoulder_elev", y_pos);    y_pos += 25

        # --- Instructions ---
        instructions = "[Q] Quit   [R] Reset   [P] Pause"
        cv2.putText(frame, instructions, (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

        # --- Frame counter ---
        cv2.putText(frame, f"Frame: {self.frame_count}", (w - 150, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1)

    def _cleanup(self):
        """Release all resources cleanly."""
        print("\nShutting down...")
        self.is_running = False
        self.cap.release()
        self.detector.release()
        self.robot.disconnect()
        cv2.destroyAllWindows()

        # Print session summary
        avg_fps = np.mean(self.fps_history) if self.fps_history else 0
        print(f"\n Session Summary ")
        print(f"  Total frames:  {self.frame_count}")
        print(f"  Average FPS:   {avg_fps:.1f}")
        print(f"  Session time:  {self.frame_count / max(avg_fps, 1):.1f}s")
        print("Goodbye!")


# ---------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------
if __name__ == "__main__":

    print("\n" + "="*50)
    print("  HRI Pose-Controlled Robot Simulation")
    print("="*50 + "\n")

    # Configuration — adjust these to tune the system
    CONFIG = {
        "camera_index": 0,      # Try 1 or 2 if 0 doesn't work
        "target_fps":   30,     # Frames per second
        "filter_window": 5,     # Larger = smoother but laggier
        "filter_alpha":  0.3,   # Smaller = smoother but laggier (0.1-0.9)
    }

    try:
        system = HRISystem(**CONFIG)
        system.run()

    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
        print("Troubleshooting tips:")
        print("  - Try camera_index=1 if camera 0 doesn't open")
        print("  - Make sure no other app is using the webcam")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user (Ctrl+C)")