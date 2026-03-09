"""
===================================================================
MODULE 3: signal_filter.py — Noise Reduction for Joint Angles
===================================================================

MENTOR EXPLANATION:
Raw pose data from MediaPipe is NOISY. Even if you hold perfectly still,
the detected joint positions jitter by several pixels every frame.
If we send this noisy data directly to the robot, it will vibrate
and shake — which is dangerous for real robots and ugly in simulation.

SOLUTION — Signal Filtering:
We implement TWO complementary filters:

1. MOVING AVERAGE FILTER (simple, intuitive):
   - Keep a sliding window of the last N angle readings
   - Output the average of those N readings
   - Effect: Smooths out random spikes by averaging them away
   - Drawback: Introduces lag (the robot responds N/2 frames later)

2. LOW-PASS FILTER (better, used in real robotics):
   - Inspired by electrical RC low-pass filters
   - Formula: filtered = alpha * new_value + (1 - alpha) * last_filtered
   - alpha ≈ 0.1-0.3: heavily smooth (slow robot, very stable)
   - alpha ≈ 0.6-0.9: lightly smooth (responsive but may jitter)
   - Effect: High-frequency noise is "low-passed" out; slow movements survive
   - Advantage: Only needs to store ONE previous value, not a whole window

3. COMBINED FILTER (what we actually use):
   - Apply moving average FIRST (removes spikes)
   - Then apply low-pass SECOND (smooths transitions)
   - Result: best of both worlds

REAL-WORLD CONTEXT:
In industrial robotics, Kalman filters or Butterworth filters are
common. The exponential moving average (our low-pass) is a simplified
version of a 1st-order Butterworth filter — widely used in practice.
===================================================================
"""

import numpy as np
from collections import deque
from typing import Optional


class MovingAverageFilter:
    """
    Simple sliding-window average filter.

    MENTOR NOTE on deque:
    We use Python's collections.deque with a maxlen parameter.
    This creates a fixed-size queue: when you append a new value
    and it's full, the oldest value automatically gets removed.
    This is O(1) append and O(n) average — perfect for our use case.
    """

    def __init__(self, window_size: int = 5):
        """
        Args:
            window_size: Number of past readings to average.
                         Larger = smoother but more lag.
                         Typical values: 3-10 for 30fps video.
        """
        self.window_size = window_size
        # Each joint gets its own deque of recent readings
        self._windows: dict[str, deque] = {}

    def update(self, joint_name: str, value: Optional[float]) -> Optional[float]:
        """
        Add a new reading and return the smoothed average.

        MENTOR NOTE:
        We skip None values (undetected joints) and just return
        whatever the current window average is. This means if a
        joint briefly disappears, we keep returning the last-known
        smoothed value rather than suddenly jumping to 0 or NaN.

        Args:
            joint_name: Identifier for this joint (e.g., "left_elbow_flexion")
            value: New angle reading in degrees, or None if not detected

        Returns:
            Smoothed angle value, or None if no data yet
        """
        if joint_name not in self._windows:
            self._windows[joint_name] = deque(maxlen=self.window_size)

        window = self._windows[joint_name]

        # Only add valid (non-None) readings to the window
        if value is not None:
            window.append(value)

        # Return average of current window
        if len(window) == 0:
            return None
        return float(np.mean(window))

    def filter_all(self, angles: dict) -> dict:
        """Apply moving average to every angle in the dict."""
        return {
            name: self.update(name, val)
            for name, val in angles.items()
        }

    def reset(self):
        """Clear all filter windows (use when tracking is lost)."""
        self._windows.clear()


class ExponentialFilter:
    """
    Exponential Moving Average (EMA) / Low-Pass Filter.

    MENTOR DEEP DIVE — The Math:
    
    filtered_t = alpha * raw_t + (1 - alpha) * filtered_(t-1)
    
    Where:
      - raw_t       = current noisy measurement
      - filtered_t  = our smoothed output
      - filtered_(t-1) = our previous smoothed output
      - alpha       = "smoothing factor" ∈ (0, 1)

    Intuition:
      If alpha = 1.0: output = raw input (no smoothing)
      If alpha = 0.0: output never changes (infinite smoothing)
      If alpha = 0.2: output is 20% new, 80% old (typical robot value)

    The "memory" of this filter decays exponentially:
      Most recent reading weights:     alpha
      2 frames ago weights:            alpha * (1-alpha)
      3 frames ago weights:            alpha * (1-alpha)²
      ...and so on. Hence "exponential" moving average.
    """

    def __init__(self, alpha: float = 0.3):
        """
        Args:
            alpha: Smoothing factor [0.0 - 1.0].
                   0.1-0.2: Very smooth, slow response (stable robots)
                   0.3-0.5: Balanced (good default for HRI at 30fps)
                   0.7-0.9: Fast response, some jitter remains
        """
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")

        self.alpha = alpha
        self._filtered: dict[str, float] = {}  # Stores last filtered value per joint

    def update(self, joint_name: str, value: Optional[float]) -> Optional[float]:
        """
        Apply one step of exponential smoothing.

        MENTOR NOTE on initialization:
        The very first reading for a joint has no "previous filtered" value.
        We initialize by setting filtered = first_raw_value. This means
        the first frame has a step change, but subsequent frames smooth
        correctly. This is called "warm start" initialization.

        Args:
            joint_name: Identifier for this joint
            value: New angle reading, or None

        Returns:
            Smoothed angle value
        """
        if value is None:
            return self._filtered.get(joint_name, None)

        if joint_name not in self._filtered:
            # First reading: initialize filter state
            self._filtered[joint_name] = value
            return value

        # The core EMA formula
        prev = self._filtered[joint_name]
        smoothed = self.alpha * value + (1.0 - self.alpha) * prev
        self._filtered[joint_name] = smoothed

        return smoothed

    def filter_all(self, angles: dict) -> dict:
        """Apply EMA to every angle in the dict."""
        return {
            name: self.update(name, val)
            for name, val in angles.items()
        }

    def reset(self):
        """Clear all filter states."""
        self._filtered.clear()


class CombinedFilter:
    """
    Two-stage filter: Moving Average → Exponential Smoothing.

    MENTOR EXPLANATION:
    Why combine both?
    
    Moving average FIRST:
      - Removes sudden outlier spikes (e.g., MediaPipe briefly
        misdetecting a joint 30° off from its true position)
      - Without this, one bad frame can corrupt EMA for several frames
    
    Exponential filter SECOND:
      - Smooths the already-spike-free signal into fluid motion
      - Gives us the natural deceleration effect (robot slows down
        as it approaches a target position, rather than stopping abruptly)

    This pipeline is similar to what industrial robot controllers use
    for vision-guided motion.
    """

    def __init__(self,
                 window_size: int = 5,
                 alpha: float = 0.3):
        """
        Args:
            window_size: Moving average window (spike removal)
            alpha: EMA smoothing factor (motion smoothing)
        """
        self.ma_filter = MovingAverageFilter(window_size=window_size)
        self.ema_filter = ExponentialFilter(alpha=alpha)

    def filter_all(self, angles: dict) -> dict:
        """Apply both filters in sequence."""
        # Stage 1: Spike removal via moving average
        ma_smoothed = self.ma_filter.filter_all(angles)

        # Stage 2: Motion smoothing via EMA
        final_smoothed = self.ema_filter.filter_all(ma_smoothed)

        return final_smoothed

    def reset(self):
        """Reset both filter stages."""
        self.ma_filter.reset()
        self.ema_filter.reset()


# ---------------------------------------------------------------
# QUICK TEST — Simulate noisy angle data and compare filters
# ---------------------------------------------------------------
if __name__ == "__main__":
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    print("Testing signal filters with simulated noisy data...")

    # Simulate a smooth signal (elbow bending from 180° to 90° over 60 frames)
    np.random.seed(42)
    n_frames = 100

    # True signal: smooth ramp from 180 to 90
    true_signal = np.concatenate([
        np.linspace(180, 90, 40),   # Bend down
        np.linspace(90, 180, 40),   # Extend back
        np.ones(20) * 180           # Hold
    ])

    # Noisy measurement: add Gaussian noise + occasional spikes
    noise = np.random.normal(0, 3, n_frames)          # Gaussian jitter
    spikes = np.random.choice([0, 0, 0, 0, 20, -20], n_frames)  # Occasional spikes
    noisy_signal = true_signal + noise + spikes

    # Apply all three filters
    ma_filter   = MovingAverageFilter(window_size=5)
    ema_filter  = ExponentialFilter(alpha=0.3)
    combo       = CombinedFilter(window_size=5, alpha=0.3)

    ma_output, ema_output, combo_output = [], [], []

    for val in noisy_signal:
        ma_output.append(ma_filter.update("test", val))
        ema_output.append(ema_filter.update("test", val))
        combo_output.append(combo.filter_all({"test": val})["test"])

    # Plot comparison
    plt.figure(figsize=(12, 6))
    plt.plot(true_signal, 'g-', linewidth=2, label='True Signal', alpha=0.8)
    plt.plot(noisy_signal, 'r.', alpha=0.4, markersize=4, label='Noisy Input')
    plt.plot(ma_output,    'b-', linewidth=1.5, label=f'Moving Avg (window=5)')
    plt.plot(ema_output,   'm-', linewidth=1.5, label=f'EMA (alpha=0.3)')
    plt.plot(combo_output, 'k-', linewidth=2.5, label='Combined (MA + EMA)', alpha=0.9)

    plt.xlabel('Frame')
    plt.ylabel('Angle (degrees)')
    plt.title('Filter Comparison: Noisy Pose Data Smoothing')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('/home/claude/hri_system/filter_comparison.png', dpi=120)
    print("Saved filter comparison chart to filter_comparison.png")

    # Compute RMS error for each filter
    def rms_error(filtered, true):
        f = np.array([x for x in filtered if x is not None])
        t = true[:len(f)]
        return np.sqrt(np.mean((f - t) ** 2))

    print(f"\nRMS Error vs True Signal:")
    print(f"  Noisy input:    {rms_error(noisy_signal, true_signal):.2f}°")
    print(f"  Moving Average: {rms_error(ma_output, true_signal):.2f}°")
    print(f"  EMA:            {rms_error(ema_output, true_signal):.2f}°")
    print(f"  Combined:       {rms_error(combo_output, true_signal):.2f}°")