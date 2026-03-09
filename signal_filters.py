#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════
signal_filters.py — Smooth and Denoise Pose Data
════════════════════════════════════════════════════════════════

This module implements signal filtering techniques to remove jitter
and noise from pose estimation data, ensuring smooth robot motion.

🎯 WHY FILTERING IS CRITICAL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem: Raw pose estimates have noise
──────────────────────────────────────
- Webcam jitter (slight position changes each frame)
- Detection uncertainty (landmark position varies ±2-5 pixels)
- Lighting changes affect detection

Result: Jerky robot movements
─────────────────────────────
- If joint angle oscillates: 95°, 93°, 96°, 92°, 94°
- Robot gets 5 different commands in 1 second
- Causes jittery, unnatural motion
- Can stress robot motors/servos

Solution: Filter the signal
──────────────────────────
- Smooth out high-frequency noise
- Keep real movement (low frequency)
- Result: 95°, 95°, 95.2°, 95.1°, 95.3°
- Robot moves smoothly and naturally

FILTER COMPARISON:
─────────────────

1. MOVING AVERAGE (Simple)
   ├─ Average last N samples
   ├─ Fast & lightweight
   ├─ Lag: Movement is delayed by N/2 frames
   ├─ Best for: Real-time responsiveness needed

2. LOW-PASS FILTER (Exponential Smoothing)
   ├─ Smooth exponential weighted average
   ├─ Adjustable cutoff frequency
   ├─ Minimal lag
   ├─ Best for: Smooth natural motion

3. KALMAN FILTER (Advanced)
   ├─ Probabilistic state estimation
   ├─ Assumes motion model + measurement noise
   ├─ Most accurate filtering
   ├─ Best for: Critical applications

════════════════════════════════════════════════════════════════
"""

import numpy as np
from collections import deque
from typing import Deque, Optional, Dict, List


class MovingAverageFilter:
    """
    Simple moving average filter - average last N samples.
    
    CONCEPT:
    ────────
    If we have: [10, 15, 12, 9, 16]  (noisy samples)
    
    With window=3:
    - Average([10, 15, 12]) = 12.3
    - Average([15, 12, 9]) = 12.0
    - Average([12, 9, 16]) = 12.3
    
    Output: [12.3, 12.0, 12.3] - much smoother!
    
    Trade-off:
    ─────────
    Larger window = smoother output BUT more latency
    
    For 30 FPS:
    - window=3 → 100ms latency (barely noticeable)
    - window=10 → 333ms latency (noticeably delayed)
    - window=5 is usually a sweet spot
    """
    
    def __init__(self, window_size: int = 5):
        """
        Initialize moving average filter.
        
        Args:
            window_size: Number of samples to average (typically 3-10)
        """
        self.window_size = max(1, window_size)
        self.buffer: Deque[float] = deque(maxlen=window_size)
    
    def filter(self, value: Optional[float]) -> Optional[float]:
        """
        Apply filter to single value.
        
        Args:
            value: New sample (or None if unavailable)
            
        Returns:
            Smoothed value, or None if buffer not full yet
        """
        if value is None:
            return None
        
        # Add to buffer (automatically removes oldest if full)
        self.buffer.append(value)
        
        # Return average of all samples in buffer
        if len(self.buffer) > 0:
            return np.mean(list(self.buffer))
        
        return None
    
    def filter_array(self, values: np.ndarray) -> np.ndarray:
        """
        Apply filter to array of values.
        
        Args:
            values: 1D array of values
            
        Returns:
            Smoothed array (same length)
        """
        output = []
        for val in values:
            output.append(self.filter(val))
        return np.array(output)
    
    def reset(self):
        """Clear the buffer (use when detection is lost)."""
        self.buffer.clear()


class LowPassFilter:
    """
    Exponential low-pass filter (first-order IIR filter).
    
    CONCEPT:
    ────────
    Instead of averaging N samples, use exponential weighting:
    - Current sample: high weight
    - Previous samples: exponentially decreasing weight
    
    Formula: output_new = α × input + (1 - α) × output_old
    
    Where α (alpha) is the smoothing factor:
    ─────────────────────────────────────────
    - α = 1.0: No filtering (use current value only)
    - α = 0.5: 50% current, 50% history (moderate smoothing)
    - α = 0.1: Only 10% current value (heavy smoothing, laggy)
    
    Typical range: 0.3 - 0.7
    
    ADVANTAGES over moving average:
    ───────────────────────────────
    ✓ No initial latency (works from first sample)
    ✓ Easy to adjust smoothing (just change α)
    ✓ Less memory (only need 1 previous value)
    ✓ Most natural motion
    
    The math works because:
    ───────────────────────
    Real movements are "low frequency" (smooth changes)
    Jitter is "high frequency" (rapid noise)
    
    Low-pass filter lets low frequencies through,
    blocks high frequencies (noise).
    """
    
    def __init__(self, alpha: float = 0.3):
        """
        Initialize low-pass filter.
        
        Args:
            alpha: Smoothing factor [0.0, 1.0]
                  Suggested values:
                  - 0.1-0.3: Heavy smoothing (sluggish response)
                  - 0.3-0.5: Balanced (recommended)
                  - 0.5-0.7: Light smoothing (responsive)
                  - 0.7+: Minimal smoothing (noisy)
        """
        self.alpha = np.clip(alpha, 0.0, 1.0)
        self.filtered_value: Optional[float] = None
    
    def filter(self, value: Optional[float]) -> Optional[float]:
        """
        Apply low-pass filter to single value.
        
        Args:
            value: New measurement
            
        Returns:
            Filtered value
            
        FIRST-ORDER RESPONSE:
        ────────────────────
        First call (filtered_value is None):
            output = value (no history yet)
        
        Subsequent calls:
            output = α × value + (1 - α) × previous_output
            
        Example with α = 0.3:
            Frame 1: measurement = 100.0 → output = 100.0
            Frame 2: measurement = 110.0 → output = 0.3×110 + 0.7×100 = 103.0
            Frame 3: measurement = 105.0 → output = 0.3×105 + 0.7×103 = 103.6
            Frame 4: measurement = 100.0 → output = 0.3×100 + 0.7×103.6 = 102.5
            Frame 5: measurement = 95.0 → output = 0.3×95 + 0.7×102.5 = 100.3
            
            Notice how output smoothly tracks input without jerks!
        """
        if value is None:
            return self.filtered_value
        
        # First sample: initialize
        if self.filtered_value is None:
            self.filtered_value = value
        else:
            # Apply exponential smoothing formula
            self.filtered_value = (self.alpha * value + 
                                  (1.0 - self.alpha) * self.filtered_value)
        
        return self.filtered_value
    
    def set_alpha(self, alpha: float):
        """Adjust smoothing factor on the fly."""
        self.alpha = np.clip(alpha, 0.0, 1.0)
    
    def reset(self):
        """Reset internal state (use when starting new motion)."""
        self.filtered_value = None
    
    def get_alpha_from_cutoff(self, cutoff_hz: float, 
                             sample_rate_hz: float) -> float:
        """
        Convert high-cutoff frequency to alpha value.
        
        Args:
            cutoff_hz: Frequency above which to filter (e.g., 5 Hz)
            sample_rate_hz: Sampling rate (e.g., 30 FPS = 30 Hz)
            
        Returns:
            Appropriate alpha value
            
        EXPLANATION:
        ────────────
        This converts desired frequency response into the α parameter.
        
        For example:
        - If sample_rate = 30 FPS (30 Hz)
        - And cutoff = 5 Hz
        - This filters out jitter above 5 Hz
        - But passes real movements below 5 Hz
        
        This is more intuitive than picking alpha directly!
        """
        # Time constant
        t_const = 1.0 / (2.0 * np.pi * cutoff_hz)
        # Time between samples
        dt = 1.0 / sample_rate_hz
        # Calculate alpha
        alpha = dt / (t_const + dt)
        return np.clip(alpha, 0.0, 1.0)


class KalmanFilter1D:
    """
    1D Kalman filter for optimal estimation.
    
    CONCEPT:
    ────────
    Kalman filter is a probabilistic approach that:
    1. Predicts next state based on motion model
    2. Compares prediction to measurement
    3. Combines them optimally
    
    Better than simple averaging because it:
    - Learns measurement noise variance
    - Learns process noise variance
    - Adapts to conditions
    
    FORMULA:
    ────────
    Prediction:
        x_pred = x_prev + v × dt
        (assume constant velocity)
    
    Update:
        Kalman gain = estimate_error / (estimate_error + measurement_error)
        x_new = x_pred + K × (measurement - x_pred)
    
    This is more mathematically rigorous than low-pass,
    but usually low-pass is simpler and sufficient for our use case.
    """
    
    def __init__(self, q: float = 0.03, r: float = 0.5):
        """
        Initialize Kalman filter.
        
        Args:
            q: Process noise (how much we expect actual motion to vary)
               Lower q = filter trusts motion model more
               (use lower for smooth predictable motion)
            
            r: Measurement noise (how much we trust measurements)
               Lower r = filter trusts measurements more
               (use lower if sensor is accurate)
        """
        self.q = q  # Process noise
        self.r = r  # Measurement noise
        
        self.x = 0.0              # State estimate
        self.v = 0.0              # Velocity estimate
        self.p = 1.0              # Error estimate
        self.initialized = False
    
    def filter(self, z: Optional[float]) -> Optional[float]:
        """
        Apply Kalman filter.
        
        Args:
            z: Measurement (can be None if not available)
            
        Returns:
            Filtered estimate
        """
        if z is None:
            return None
        
        if not self.initialized:
            self.x = z
            self.initialized = True
            return z
        
        # Prediction step
        # Assume constant velocity model
        x_pred = self.x + self.v
        p_pred = self.p + self.q  # Uncertainty increases
        
        # Update step
        # How much to trust measurement vs prediction?
        K = p_pred / (p_pred + self.r)  # Kalman gain
        
        # Blend prediction and measurement
        self.x = x_pred + K * (z - x_pred)
        self.p = (1.0 - K) * p_pred  # Update uncertainty
        
        # Estimate velocity (change in position)
        self.v = self.x - (self.x - K * (z - x_pred))
        
        return self.x
    
    def reset(self):
        """Reset filter state."""
        self.x = 0.0
        self.v = 0.0
        self.p = 1.0
        self.initialized = False


class MultiJointFilter:
    """
    Apply the same filter to multiple joint angles simultaneously.
    
    Manages a dict of filters for different joints:
        {
            'left_elbow': LowPassFilter(),
            'right_elbow': LowPassFilter(),
            ...
        }
    
    This is the practical interface for filtering entire pose data.
    """
    
    def __init__(self, filter_type: str = 'low_pass', 
                 filter_params: Optional[Dict] = None):
        """
        Initialize multi-joint filter.
        
        Args:
            filter_type: 'moving_average', 'low_pass', or 'kalman'
            filter_params: Dict of parameters for chosen filter
                          E.g., {'alpha': 0.3} for low_pass
        """
        self.filter_type = filter_type
        self.filter_params = filter_params or {}
        self.filters: Dict[str, object] = {}
    
    def _create_filter(self):
        """Create a new filter instance based on type."""
        if self.filter_type == 'moving_average':
            window = self.filter_params.get('window_size', 5)
            return MovingAverageFilter(window)
        elif self.filter_type == 'low_pass':
            alpha = self.filter_params.get('alpha', 0.3)
            return LowPassFilter(alpha)
        elif self.filter_type == 'kalman':
            q = self.filter_params.get('q', 0.03)
            r = self.filter_params.get('r', 0.5)
            return KalmanFilter1D(q, r)
        else:
            return LowPassFilter(0.3)
    
    def filter_angles(self, angles: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
        """
        Filter all joint angles.
        
        Args:
            angles: Dict like {'left_elbow': 95.0, 'right_elbow': None, ...}
            
        Returns:
            Filtered angles with same structure
            
        LAZY INITIALIZATION:
        ───────────────────
        First time a joint is seen, create a filter for it.
        Subsequent calls reuse the filter (maintains state).
        """
        filtered = {}
        
        for joint_name, angle in angles.items():
            # Create filter for this joint if not exists
            if joint_name not in self.filters:
                self.filters[joint_name] = self._create_filter()
            
            # Apply filter
            filtered[joint_name] = self.filters[joint_name].filter(angle)
        
        return filtered
    
    def reset_joint(self, joint_name: str):
        """Reset filter state for specific joint."""
        if joint_name in self.filters:
            self.filters[joint_name].reset()
    
    def reset_all(self):
        """Reset all filters."""
        for filt in self.filters.values():
            filt.reset()


# ════════════════════════════════════════════════════════════════
# Example Usage and Testing
# ════════════════════════════════════════════════════════════════

def demo_filters():
    """
    Compare different filtering techniques on synthetic noisy data.
    """
    print("📊 Signal Filter Comparison Demo\n")
    
    # Create synthetic noisy signal: sine wave + random noise
    # ─────────────────────────────────────────────────────────
    true_signal = np.sin(np.linspace(0, 4*np.pi, 100))  # 2 complete sine waves
    noise = np.random.normal(0, 0.15, 100)               # Gaussian noise
    noisy_signal = true_signal + noise
    
    # Apply different filters
    # ─────────────────────────
    ma_filter = MovingAverageFilter(window_size=5)
    lp_filter = LowPassFilter(alpha=0.3)
    kf_filter = KalmanFilter1D(q=0.03, r=0.5)
    
    ma_output = [ma_filter.filter(v) for v in noisy_signal]
    lp_output = [lp_filter.filter(v) for v in noisy_signal]
    kf_output = [kf_filter.filter(v) for v in noisy_signal]
    
    # Print comparison at key points
    print("Sample values at indices [0, 25, 50, 75, 99]:")
    print("─" * 70)
    print("Index | True   | Noisy  | Mov.Avg| LowPass| Kalman")
    print("─" * 70)
    
    for idx in [0, 25, 50, 75, 99]:
        print(f"{idx:5d} | {true_signal[idx]:6.3f} | {noisy_signal[idx]:6.3f} | "
              f"{ma_output[idx]:6.3f} | {lp_output[idx]:6.3f} | {kf_output[idx]:6.3f}")
    
    print("\n" + "="*70)
    print("RESULTS EXPLANATION:")
    print("="*70)
    print("""
✓ Moving Average: Smooth but lags behind actual signal
✓ Low-Pass: Good balance of smoothness and responsiveness
✓ Kalman: Optimal if parameters tuned correctly

For pose estimation → LowPassFilter is usually best choice!
""")


def demo_multi_joint_filter():
    """
    Demonstrate filtering multiple joint angles.
    """
    print("\n📊 Multi-Joint Filter Demo\n")
    
    # Create filter for angles
    multi_filter = MultiJointFilter('low_pass', {'alpha': 0.3})
    
    # Simulate 5 frames of angle measurements (with some noise)
    print("Frame | Left Elbow | Right Elbow | Filtered L.Elbow | Filtered R.Elbow")
    print("─" * 72)
    
    for frame in range(5):
        # Noisy measurements
        left_elbow_raw = 95.0 + np.random.normal(0, 2.0)
        right_elbow_raw = 85.0 + np.random.normal(0, 2.0)
        
        # Filter
        filtered = multi_filter.filter_angles({
            'left_elbow': left_elbow_raw,
            'right_elbow': right_elbow_raw
        })
        
        print(f"{frame+1:5d} | {left_elbow_raw:10.2f} | {right_elbow_raw:11.2f} | "
              f"{filtered['left_elbow']:16.2f} | {filtered['right_elbow']:16.2f}")
    
    print("\nNotice how filtered values stabilize while tracking movement!")


if __name__ == "__main__":
    demo_filters()
    demo_multi_joint_filter()
