#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════
pose_detector.py — Real-time Pose Detection Engine
════════════════════════════════════════════════════════════════

This module captures video from a webcam and detects human body landmarks
using MediaPipe's efficient pose estimation model.

🎯 CONCEPT EXPLANATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MediaPipe Pose detects 33 body landmarks in 3D space:
  - Landmarks represent joint positions (nose, shoulders, elbows, etc.)
  - Each landmark has (x, y, z) coordinates in normalized space
  - x, y: normalized to [0,1] relative to frame width/height
  - z: depth relative to the hips (positive = away from camera)
  - visibility: confidence score that landmark is visible

Key MediaPipe Landmarks for robot control:
  - Index 11: Left Shoulder  | Index 12: Right Shoulder
  - Index 13: Left Elbow     | Index 14: Right Elbow
  - Index 15: Left Wrist     | Index 16: Right Wrist
  - Index 23: Left Hip       | Index 24: Right Hip
  - Index 25: Left Knee      | Index 26: Right Knee
  - Index 27: Left Ankle     | Index 28: Right Ankle

════════════════════════════════════════════════════════════════
"""

import cv2
import mediapipe as mp
import numpy as np
from typing import Optional, Tuple, List


class PoseDetector:
    """
    Manages real-time pose detection from webcam using MediaPipe.
    
    Attributes:
        confidence_threshold (float): Minimum detection confidence [0-1]
        frame_width (int): Current frame width
        frame_height (int): Current frame height
        landmarks (List): Last detected 33 landmarks [x, y, z, visibility]
    """
    
    def __init__(self, confidence_threshold: float = 0.5):
        """
        Initialize MediaPipe Pose detector.
        
        Args:
            confidence_threshold: Minimum confidence to include landmark.
                                Values too low = noisy detections.
                                Values too high = missed detections.
        """
        self.confidence_threshold = confidence_threshold
        self.frame_width = None
        self.frame_height = None
        self.landmarks = []
        
        # Initialize MediaPipe components
        # ─────────────────────────────────
        # mp.solutions.pose: The pose estimation model
        # min_detection_confidence: Initial frame detection threshold
        # min_tracking_confidence: Threshold for tracking between frames
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,  # Video mode (tracks landmarks smoothly)
            model_complexity=1,        # 0=lite, 1=full (use 1 for accuracy)
            smooth_landmarks=True,     # Temporal smoothing built-in
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # MediaPipe drawing utilities for visualization
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Define landmark names for easy reference
        self._setup_landmark_names()
    
    
    def _setup_landmark_names(self):
        """
        Create mapping of landmark indices to human-readable names.
        
        This helps identify key joints later for angle extraction.
        Full list: 33 landmarks total (indices 0-32)
        """
        self.landmark_names = {
            0: "Nose",
            1: "Left Eye Inner", 2: "Left Eye", 3: "Left Eye Outer",
            4: "Right Eye Inner", 5: "Right Eye", 6: "Right Eye Outer",
            7: "Left Ear", 8: "Right Ear",
            9: "Mouth Left", 10: "Mouth Right",
            11: "Left Shoulder", 12: "Right Shoulder",
            13: "Left Elbow", 14: "Right Elbow",
            15: "Left Wrist", 16: "Right Wrist",
            17: "Left Pinky", 18: "Right Pinky",
            19: "Left Index", 20: "Right Index",
            21: "Left Thumb", 22: "Right Thumb",
            23: "Left Hip", 24: "Right Hip",
            25: "Left Knee", 26: "Right Knee",
            27: "Left Ankle", 28: "Right Ankle",
            29: "Left Heel", 30: "Right Heel",
            31: "Left Foot Index", 32: "Right Foot Index"
        }
    
    
    def detect(self, frame: np.ndarray) -> bool:
        """
        Detect human pose landmarks in the current frame.
        
        Args:
            frame: Input video frame (BGR format from OpenCV)
            
        Returns:
            True if landmarks detected successfully, False otherwise
            
        HOW IT WORKS:
        ─────────────
        1. Convert BGR (OpenCV) → RGB (MediaPipe requirement)
        2. Run inference: mediapipe.process() detects all 33 landmarks
        3. Extract landmark data with confidence filtering
        4. Store for later use by other modules
        """
        if frame is None:
            return False
        
        # Store frame dimensions for coordinate conversion later
        self.frame_height, self.frame_width = frame.shape[:2]
        
        # MediaPipe requires RGB format
        # ──────────────────────────────
        # cv2.imread() uses BGR by default, so we convert
        # This is CRITICAL - wrong format causes silent failures!
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Run pose estimation
        # ───────────────────
        # The pose model is already optimized to handle 30 FPS+ on CPU
        # Results include landmarks + world_landmarks
        # world_landmarks: 3D coordinates in meters (relative to center of hips)
        results = self.pose.process(rgb_frame)
        
        # Check if landmarks were detected
        if not results.landmarks:
            self.landmarks = []
            return False
        
        # Extract landmark data
        # ────────────────────
        # Each landmark is a Landmark object with x, y, z, visibility
        # We filter by confidence to avoid using weak detections
        self.landmarks = []
        for landmark in results.landmarks:
            if landmark.visibility >= self.confidence_threshold:
                self.landmarks.append({
                    'x': landmark.x,
                    'y': landmark.y,
                    'z': landmark.z,
                    'visibility': landmark.visibility
                })
            else:
                # Landmark below confidence threshold
                self.landmarks.append({
                    'x': None,
                    'y': None,
                    'z': None,
                    'visibility': landmark.visibility
                })
        
        return len(self.landmarks) > 0
    
    
    def get_landmarks(self) -> List[dict]:
        """
        Get all detected landmarks from last frame.
        
        Returns:
            List of 33 landmark dictionaries with keys: x, y, z, visibility
            Landmarks not detected will have None values.
        """
        return self.landmarks
    
    
    def get_landmark(self, idx: int) -> Optional[Tuple[float, float, float]]:
        """
        Get specific landmark coordinates by index.
        
        Args:
            idx: Landmark index (0-32)
            
        Returns:
            (x, y, z) tuple if detected, None if not detected
            
        Example:
            left_shoulder = detector.get_landmark(11)
        """
        if idx >= len(self.landmarks):
            return None
        
        lm = self.landmarks[idx]
        if lm['x'] is None:
            return None
        
        return (lm['x'], lm['y'], lm['z'])
    
    
    def get_landmark_pixel(self, idx: int) -> Optional[Tuple[int, int]]:
        """
        Get landmark in pixel coordinates (for drawing on frame).
        
        Args:
            idx: Landmark index (0-32)
            
        Returns:
            (pixel_x, pixel_y) tuple, or None if not detected
            
        WHY NEEDED:
        ───────────
        MediaPipe returns normalized coordinates [0,1].
        To draw on screen, we need pixel coordinates [0, width/height].
        """
        lm = self.get_landmark(idx)
        if lm is None:
            return None
        
        x_pixel = int(lm[0] * self.frame_width)
        y_pixel = int(lm[1] * self.frame_height)
        
        # Clamp to frame boundaries (safety check)
        x_pixel = max(0, min(x_pixel, self.frame_width - 1))
        y_pixel = max(0, min(y_pixel, self.frame_height - 1))
        
        return (x_pixel, y_pixel)
    
    
    def draw_landmarks(self, frame: np.ndarray, 
                      draw_connections: bool = True) -> np.ndarray:
        """
        Draw detected landmarks and skeleton on frame.
        
        Args:
            frame: Input frame to draw on
            draw_connections: Whether to draw lines connecting joints
            
        Returns:
            Frame with landmarks drawn
            
        VISUAL GUIDE:
        ─────────────
        Green circles = detected landmarks
        Blue lines = connections (skeleton structure)
        Red circles = low confidence detections
        """
        output_frame = frame.copy()
        
        # Draw individual landmarks
        for idx, landmark in enumerate(self.landmarks):
            if landmark['x'] is None:
                continue
            
            pixel_pos = self.get_landmark_pixel(idx)
            if pixel_pos is None:
                continue
            
            # Color based on confidence
            confidence = landmark['visibility']
            if confidence > 0.7:
                color = (0, 255, 0)  # Green = high confidence
            else:
                color = (0, 0, 255)  # Red = medium confidence
            
            # Draw circle at joint
            cv2.circle(output_frame, pixel_pos, 4, color, -1)
        
        # Draw skeleton connections (lines between joints)
        if draw_connections:
            # MediaPipe defines connections as part of its model metadata
            # Access them via the Pose model
            for connection in self.mp_pose.POSE_CONNECTIONS:
                start_idx, end_idx = connection
                
                start_pos = self.get_landmark_pixel(start_idx)
                end_pos = self.get_landmark_pixel(end_idx)
                
                if start_pos is None or end_pos is None:
                    continue
                
                # Blue line connecting joints
                cv2.line(output_frame, start_pos, end_pos, (255, 0, 0), 2)
        
        return output_frame
    
    
    def distance_between_landmarks(self, idx1: int, idx2: int) -> Optional[float]:
        """
        Calculate Euclidean distance between two landmarks.
        
        Args:
            idx1, idx2: Landmark indices
            
        Returns:
            Distance in normalized space [0-1.41], or None if either not detected
            
        USE CASE:
        ─────────
        Measure arm length: distance_between_landmarks(11, 15)
        (shoulder to wrist distance)
        """
        lm1 = self.get_landmark(idx1)
        lm2 = self.get_landmark(idx2)
        
        if lm1 is None or lm2 is None:
            return None
        
        dx = lm1[0] - lm2[0]
        dy = lm1[1] - lm2[1]
        dz = lm1[2] - lm2[2]
        
        distance = np.sqrt(dx**2 + dy**2 + dz**2)
        return distance
    
    
    def close(self):
        """
        Close video capture and MediaPipe resources.
        Always call this when done to free system resources.
        """
        self.pose.close()


# ════════════════════════════════════════════════════════════════
# Example Usage Section
# ════════════════════════════════════════════════════════════════

def demo_pose_detection():
    """
    Demonstration: Real-time pose detection from webcam.
    
    Shows:
    - Webcam feed with detected landmarks
    - FPS counter
    - Joint coordinates on screen
    
    Controls:
    - Press 'Q' to quit
    - Press 'S' to show statistics
    """
    print("🎥 Starting pose detection demo...")
    print("   Press 'Q' to quit, 'S' for stats\n")
    
    # Initialize detector
    detector = PoseDetector(confidence_threshold=0.5)
    
    # Open webcam (0 = default camera)
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print(" Error: Could not open webcam!")
        return
    
    # Get camera properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    print(f"   Camera: {frame_width}x{frame_height} @ {fps} FPS\n")
    
    # Real-time loop
    frame_count = 0
    import time
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print(" Error reading frame")
            break
        
        # Detect pose
        success = detector.detect(frame)
        
        # Prepare display frame
        display_frame = detector.draw_landmarks(frame)
        
        # Add FPS counter
        frame_count += 1
        elapsed = time.time() - start_time
        current_fps = frame_count / elapsed if elapsed > 0 else 0
        
        cv2.putText(display_frame, f"FPS: {current_fps:.1f}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Add status
        status = "✓ DETECTED" if success else "✗ No Detection"
        color = (0, 255, 0) if success else (0, 0, 255)
        cv2.putText(display_frame, status, (10, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Add key joint info
        left_shoulder = detector.get_landmark_pixel(11)
        if left_shoulder:
            cv2.putText(display_frame, "L-Shoulder", 
                       (left_shoulder[0] - 30, left_shoulder[1] - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        
        # Display
        cv2.imshow("Pose Detection - Press Q to quit", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("\n✓ Exiting...")
            break
        elif key == ord('s'):
            # Print statistics
            if detector.landmarks:
                detected_count = sum(1 for lm in detector.landmarks if lm['x'] is not None)
                print(f"   Detected landmarks: {detected_count}/33")
    
    # Cleanup
    cap.release()
    detector.close()
    cv2.destroyAllWindows()
    print("✓ Demo ended\n")


if __name__ == "__main__":
    demo_pose_detection()
