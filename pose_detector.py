"""
===================================================================
MODULE 1: pose_detector.py — Human Pose Detection via MediaPipe
===================================================================

UPDATED FOR MediaPipe 0.10.x+ (New Tasks API)
Fully compatible — no mp.solutions dependencies.

MENTOR EXPLANATION:
This version removes ALL references to mp.solutions.* which caused
the AttributeError. Instead we:
  1. Use the new Tasks API for detection
  2. Manually define pose connections (the skeleton lines)
  3. Draw landmarks ourselves using OpenCV directly
  4. Use only: mp.Image, mp.ImageFormat, mp.tasks — all safe in 0.10.32
===================================================================
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.vision import RunningMode
import numpy as np
import urllib.request
import os


# ── Model download config ─────────────────────────────────────
MODEL_FILENAME = "pose_landmarker_full.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_full/float16/latest/"
    "pose_landmarker_full.task"
)

# ── Arm landmark indices (from MediaPipe's 33-point model) ────
ARM_LANDMARK_INDICES = {
    "left_shoulder":  11,
    "left_elbow":     13,
    "left_wrist":     15,
    "right_shoulder": 12,
    "right_elbow":    14,
    "right_wrist":    16,
    "left_hip":       23,
    "right_hip":      24,
}

# ── Skeleton connections (drawn as lines between joint pairs) ──
# MENTOR NOTE:
# Each tuple (A, B) means "draw a line from landmark A to landmark B".
# These cover the full body skeleton. We draw them manually with
# OpenCV since we no longer use mp.solutions.drawing_utils.
POSE_CONNECTIONS = [
    # Face
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    # Shoulders
    (11, 12),
    # Left arm
    (11, 13), (13, 15),
    # Right arm
    (12, 14), (14, 16),
    # Torso
    (11, 23), (12, 24), (23, 24),
    # Left leg
    (23, 25), (25, 27), (27, 29), (29, 31),
    # Right leg
    (24, 26), (26, 28), (28, 30), (30, 32),
]


def download_model_if_needed(model_path: str = MODEL_FILENAME) -> str:
    """Download the .task model file if not already present."""
    if os.path.exists(model_path):
        print(f"    Model file found: {model_path} ✓")
        return model_path

    print(f"    Downloading pose model (~5MB), please wait...")
    try:
        urllib.request.urlretrieve(MODEL_URL, model_path)
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        print(f"    Downloaded: {model_path} ({size_mb:.1f} MB) ✓")
        return model_path
    except Exception as e:
        raise RuntimeError(
            f"Failed to download model: {e}\n"
            f"Please download manually from:\n{MODEL_URL}\n"
            f"Save it as '{model_path}' in your project folder."
        )


class PoseDetector:
    """
    MediaPipe PoseLandmarker wrapper — fully compatible with 0.10.32+.

    MENTOR NOTE on what changed vs old API:
    ┌─────────────────────────────────────────────────────────┐
    │  OLD (broken)          │  NEW (this file)               │
    ├─────────────────────────────────────────────────────────┤
    │  mp.solutions.pose     │  mp_vision.PoseLandmarker      │
    │  mp.solutions.drawing  │  OpenCV draw manually          │
    │  pose.POSE_CONNECTIONS │  Our POSE_CONNECTIONS list     │
    │  results.pose_landmarks│  result.pose_landmarks[0]      │
    └─────────────────────────────────────────────────────────┘
    """

    def __init__(self,
                 min_detection_confidence: float = 0.7,
                 min_tracking_confidence: float = 0.7,
                 model_path: str = MODEL_FILENAME):

        # Download model if needed
        model_path = download_model_if_needed(model_path)

        # Configure the landmarker
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            num_poses=1,
            output_segmentation_masks=False
        )
        self.landmarker = mp_vision.PoseLandmarker.create_from_options(options)

        # Skeleton connections (no mp.solutions dependency)
        self.pose_connections = POSE_CONNECTIONS

        # Timestamp: VIDEO mode needs monotonically increasing value
        # We simulate 30fps → increment 33ms each frame
        self._timestamp_ms = 0

        # Last known result for stability when detection is lost
        self._last_result = None

        print("    PoseDetector ready (MediaPipe 0.10.32 compatible) ✓")

    def detect(self, frame: np.ndarray):
        """
        Run pose detection on one frame and store the result.

        MENTOR NOTE:
        We separate detection (this method) from drawing and landmark
        extraction. This makes the code cleaner and easier to test —
        you can call detect() then decide whether to draw or just
        extract landmarks depending on what you need.

        Args:
            frame: BGR image from OpenCV
        """
        self._timestamp_ms += 33

        # BGR → RGB → MediaPipe Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # Detect landmarks
        result = self.landmarker.detect_for_video(mp_image, self._timestamp_ms)

        # Store result if valid, otherwise keep last known
        if result.pose_landmarks and len(result.pose_landmarks) > 0:
            self._last_result = result
        # If no detection, self._last_result stays as-is (stability)

    def get_landmarks(self) -> dict | None:
        """
        Extract arm joint positions from the last detection result.

        MENTOR NOTE:
        Returns normalized (0.0–1.0) x, y coordinates — NOT pixels yet.
        We convert to pixels in process_frame() using the frame dimensions.
        Keeping them normalized here makes the class more reusable.

        Returns:
            Dict {joint_name: np.array([x_norm, y_norm, z_m])} or None
        """
        if self._last_result is None:
            return None

        pose_landmarks = self._last_result.pose_landmarks[0]
        landmarks = {}
        for name, idx in ARM_LANDMARK_INDICES.items():
            lm = pose_landmarks[idx]
            landmarks[name] = np.array([lm.x, lm.y, lm.z])
        return landmarks

    def draw_landmarks(self, frame: np.ndarray):
        """
        Draw the full body skeleton on the frame using OpenCV.

        MENTOR NOTE on manual drawing:
        Since we removed mp.solutions.drawing_utils, we draw ourselves:
          1. Loop through all 33 landmarks → draw a green circle at each
          2. Loop through POSE_CONNECTIONS → draw a white line for each bone

        This gives us full control over colors, thickness, and style —
        and removes the dependency that was causing AttributeErrors.

        Args:
            frame: BGR image to draw on (modified in place)
        """
        if self._last_result is None:
            return

        h, w = frame.shape[:2]
        pose_landmarks = self._last_result.pose_landmarks[0]

        # Convert all 33 landmarks to pixel coordinates
        points = []
        for lm in pose_landmarks:
            x = int(lm.x * w)
            y = int(lm.y * h)
            points.append((x, y))

        # Draw skeleton lines (bones)
        for start_idx, end_idx in self.pose_connections:
            if start_idx < len(points) and end_idx < len(points):
                start_pt = points[start_idx]
                end_pt   = points[end_idx]
                cv2.line(frame, start_pt, end_pt, (255, 255, 255), 2)

        # Draw joint dots on top of lines
        for (x, y) in points:
            cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)   # Filled green dot
            cv2.circle(frame, (x, y), 4, (0, 180, 0), 1)    # Dark green border

    def process_frame(self, frame: np.ndarray) -> tuple:
        """
        Full pipeline: detect → draw → extract landmarks.

        This is the main method called by main.py every frame.

        Args:
            frame: BGR webcam frame

        Returns:
            annotated_frame: Frame with skeleton overlay
            landmarks: Dict {joint_name: np.array([x_px, y_px, z])} or None
        """
        # Run detection
        self.detect(frame)

        # Draw skeleton on a copy
        annotated_frame = frame.copy()
        self.draw_landmarks(annotated_frame)

        # Extract and convert landmarks to pixel coordinates
        norm_landmarks = self.get_landmarks()
        if norm_landmarks is None:
            return annotated_frame, None

        h, w = frame.shape[:2]
        pixel_landmarks = {}
        for name, coords in norm_landmarks.items():
            pixel_landmarks[name] = np.array([
                coords[0] * w,   # x in pixels
                coords[1] * h,   # y in pixels
                coords[2]        # z in meters (keep as-is)
            ])

        return annotated_frame, pixel_landmarks

    def release(self):
        """Clean up MediaPipe resources."""
        self.landmarker.close()


# ── Quick Test ────────────────────────────────────────────────
if __name__ == "__main__":
    print("="*50)
    print("  Pose Detector Test (MediaPipe 0.10.32+)")
    print("="*50)
    print("Stand in front of your camera.")
    print("Press Q to quit.\n")

    detector = PoseDetector()
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Could not open webcam. Try changing index to 1.")
        exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame.")
            break

        frame = cv2.flip(frame, 1)  # Mirror
        annotated, landmarks = detector.process_frame(frame)
        frame_count += 1

        # Print joint positions every 10 frames
        if landmarks and frame_count % 10 == 0:
            ls = landmarks["left_shoulder"]
            le = landmarks["left_elbow"]
            lw = landmarks["left_wrist"]
            print(
                f"  L.Shoulder:({ls[0]:.0f},{ls[1]:.0f})  "
                f"L.Elbow:({le[0]:.0f},{le[1]:.0f})  "
                f"L.Wrist:({lw[0]:.0f},{lw[1]:.0f})",
                end="\r"
            )

        # Status overlay
        if landmarks:
            status, color = "DETECTED ✓", (0, 220, 0)
        else:
            status, color = "NO PERSON DETECTED", (0, 60, 255)

        cv2.putText(annotated, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(annotated, "Q = quit", (10, 465),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 140, 140), 1)
        cv2.putText(annotated, f"Frame: {frame_count}", (520, 465),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (140, 140, 140), 1)

        cv2.imshow("Pose Detector Test", annotated)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    print("\n\nCleaning up...")
    detector.release()
    cap.release()
    cv2.destroyAllWindows()
    print("Done!")