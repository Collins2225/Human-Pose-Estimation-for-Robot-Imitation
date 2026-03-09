# 🚀 QUICK REFERENCE GUIDE
## Common Tasks & Solutions

---

## ⚡ **Running the System**

### First Time Setup
```bash
# 1. Navigate to project
cd "Human Pose Estimation for Robot Imitation"

# 2. Install dependencies (once)
python install_dependencies.py

# 3. Run the main system
python main.py
```

### Testing Individual Modules
```bash
# Test pose detection
python -c "from pose_detector import demo_pose_detection; demo_pose_detection()"

# Test angle extraction
python -c "from joint_angle_extractor import demo_angle_extraction; demo_angle_extraction()"

# Test signal filters
python -c "from signal_filters import demo_filters; demo_filters()"

# Test motion mapping
python -c "from motion_mapper import demo_motion_mapping; demo_motion_mapping()"

# Test robot simulator
python -c "from robot_simulator import demo_robot_simulator; demo_robot_simulator()"
```

---

## 🎮 **Controlling the System**

### Keyboard Controls During Execution
```
Q     Quit program
P     Toggle skeleton display
A     Toggle angle values display
S     Toggle detailed statistics
F     Toggle FPS counter
```

### Reading the Visual Output

**Top Left - Human Angles (Yellow):**
```
HUMAN ANGLES (deg)
left_shoulder: 125.3°
left_elbow: 95.2°
left_wrist: -5.0°
```
These are the angles detected from your pose.

**Top Right - Statistics (Green):**
```
FPS: 12.5
Detection: 98%
```
Shows system performance and reliability.

**Center - Skeleton:**
- Green circles = high confidence landmarks
- Red circles = low confidence (might skip)
- Blue lines = skeleton connections

---

## 🔧 **Customization**

### Adjusting Filter Strength

**In `main.py`, find the line:**
```python
system = HumanRobotImitationSystem(
    filter_type='low_pass',
    ...
)
```

**Then adjust** `signal_filters.py`:
```python
self.joint_filter = MultiJointFilter(
    filter_type='low_pass',
    filter_params={'alpha': 0.3}  # Change this
)
```

**Alpha values:**
- `0.1-0.2`: Heavy smoothing (smoother but sluggish)
- `0.3-0.4`: Balanced (RECOMMENDED)
- `0.5-0.7`: Light smoothing (responsive but jittery)

---

### Changing Joint Limits

**In `motion_mapper.py`, find:**
```python
self.joint_configs['left_elbow'] = RobotJointConfig(
    'left_elbow',
    min_angle=15,     # ← Change this (minimum)
    max_angle=165,    # ← Change this (maximum)
    neutral=90,       # ← Change this (rest position)
    invert=False      # ← Flip to mirror motion
)
```

**Common adjustments:**
- Limited range robot? Lower `max_angle`
- Stiff joints? Increase `neutral` offset
- Want mirroring? Set `invert=True` for right side

---

### Using Different Robots

**In `main.py`, find:**
```python
self.robot_simulator.load_robot("r2d2.urdf")
```

**Available built-in robots:**
```
"r2d2.urdf"              # Default: fun little robot
"r2d2_limited.urdf"      # Simplified version
"pr2_gripper.urdf"       # Different model
"laikago.urdf"           # Quadruped (4-legged)
```

**Using custom URDF:**
```python
self.robot_simulator.load_robot("path/to/your_robot.urdf")
```

---

### Disabling PyBullet GUI

For faster headless operation:
```python
system = HumanRobotImitationSystem(
    robot_gui=False  # No visualization window
)
```

This runs ~2x faster but shows no robot animation.

---

## 🐛 **Troubleshooting**

### Problem: Webcam Not Opening

**Try these steps:**
```python
# In Python, test camera
import cv2
cap = cv2.VideoCapture(0)
print(cap.isOpened())  # Should print: True

# If False, try other camera IDs
cap = cv2.VideoCapture(1)  # Try camera 1

# Then in main.py:
system.open_webcam(camera_id=1)  # Changed from 0
```

### Problem: Poor Pose Detection

**Checklist:**
- ✓ Good lighting (not backlit)
- ✓ Full body visible (stand back 2-3 meters)
- ✓ Look at camera
- ✓ Clear background (no clutter)

**If still poor:**
```python
# Lower confidence threshold
detector = PoseDetector(confidence_threshold=0.3)  # Was 0.5
```

### Problem: Jerky Robot Motion

**Adjust filter:**
```python
# In signal_filters.py main filter creation
filter_params={'alpha': 0.2}  # Increase smoothing
```

Or use moving average:
```python
system = HumanRobotImitationSystem(
    filter_type='moving_average'
    # Then in motion_mapper.py:
    # filter_params={'window_size': 7}
)
```

### Problem: Robot Moving in Wrong Direction

**Check inversion settings:**
```python
# In motion_mapper.py, for each joint:
self.joint_configs['right_elbow'] = RobotJointConfig(
    'right_elbow',
    ...
    invert=True  # Toggle this
)
```

Or swap min/max:
```python
# Instead of:
min_angle=15, max_angle=165

# Try:
min_angle=165, max_angle=15  # Reversed
```

---

## 📊 **Monitoring & Debugging**

### Enabling Verbose Output

**In `main.py`:**
```python
system.show_statistics = True  # Shows robot angles
system.show_fps = True         # Shows frame rate
```

### Checking Detection Statistics

Press 'S' during execution and watch top-right corner:
```
Detection: 98%   # Success rate (should be > 90%)
```

### Measuring Latency

The latency = delay from your movement to robot's movement.

**Typical latencies:**
- Professional system: < 50ms
- Our system: ~150ms (still feels OK)
- Noticeable lag > 250ms

**To reduce:**
1. Use GPU acceleration for MediaPipe
2. Reduce filter window size
3. Run pose detection in background thread

---

## 💡 **Tips & Tricks**

### Record Joint Angles to File

**Add to `main.py`:**
```python
import csv

# After angle extraction:
with open('pose_log.csv', 'a') as f:
    writer = csv.writer(f)
    writer.writerow([timestamp, left_elbow, right_elbow, ...])
```

### Replay Recorded Pose

```python
# Read from CSV and apply to robot
with open('pose_log.csv', 'r') as f:
    reader = csv.reader(f)
    for row in reader:
        angles = {
            'left_elbow': float(row[1]),
            'right_elbow': float(row[2]),
            ...
        }
        robot.set_all_joint_angles(angles)
```

### Slow-Motion Playback

**In `main.py`:**
```python
# Normal speed
system.run(target_fps=30)

# Slow motion
system.run(target_fps=15)  # 2x slower

# Fast motion
system.run(target_fps=60)  # 2x faster
```

### Record Video Output

**Add to visualization:**
```python
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('output.mp4', fourcc, 30, (640, 480))

# In main loop:
out.write(display_frame)

# At end:
out.release()
```

---

## 🔧 **Parameter Reference**

### MediaPipe Settings
```python
PoseDetector(confidence_threshold=0.5)
# 0.3: Loose detection (more false positives)
# 0.5: Balanced (recommended)
# 0.8: Strict detection (might miss joints)
```

### Filter Settings
```python
# Low-pass filter
filter_params={'alpha': 0.3}
# 0.1-0.2: Smooth but sluggish
# 0.3-0.4: Balanced (recommended)
# 0.5-0.7: Responsive but noisy

# Moving average
filter_params={'window_size': 5}
# 1: No filtering
# 3-5: Light filtering
# 10+: Heavy filtering (very smooth)
```

### PyBullet Settings
```python
# In robot_simulator.py
p.setTimeStep(1/240)  # Physics timestep
# Larger = faster simulation, less accurate
# Smaller = slower simulation, more accurate

p.setJointMotorControl2(..., maxForce=500)
# 100-200: Weak servo (slow)
# 500: Balanced (recommended)
# 1000+: Strong servo (fast but jerky)
```

---

## 📈 **Performance Measurements**

### Getting FPS

```python
# Automatic (shown on screen)
# Press F to toggle counter

# Manual in code:
import time
start = time.time()
# ... process frame ...
elapsed = time.time() - start
fps = 1.0 / elapsed
print(f"FPS: {fps:.1f}")
```

### Getting Detection Rate

```python
# Shown automatically on screen

# Or compute manually:
success_count = detection_stats['successful']
total_count = detection_stats['total']
rate = success_count / total_count * 100
print(f"Detection rate: {rate:.1f}%")
```

### Profiling Code

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# ... run code ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 slowest
```

---

## 🚀 **Next Steps**

### After Getting It Working

1. **Experiment with different settings**
   - Try different alpha values
   - Test different robot models
   - Adjust joint limits

2. **Understand each module**
   - Read comments in code
   - Try individual demo functions
   - Modify and test changes

3. **Extend functionality**
   - Add gesture recognition
   - Record and replay poses
   - Try real robot hardware

4. **Optimize performance**
   - Profile bottlenecks
   - Use threading for parallel processing
   - GPU acceleration for MediaPipe

---

## 💾 **File Dependencies**

```
main.py (entry point)
  └─ pose_detector.py
      └─ Requires: cv2, mediapipe, numpy
  
  └─ joint_angle_extractor.py
      └─ Requires: numpy
  
  └─ signal_filters.py
      └─ Requires: numpy
  
  └─ motion_mapper.py
      └─ Requires: numpy
  
  └─ robot_simulator.py
      └─ Requires: pybullet, numpy
```

**Never move files!** All imports are relative to this directory.

---

## 🎓 **Learning Path**

Recommended order to learn the system:

1. **Start here:** `README.md`
   - Overview and quick start

2. **Run demos:**
   ```bash
   python pose_detector.py       # See pose detection
   python joint_angle_extractor.py # See angle math
   python signal_filters.py      # See filtering effect
   python motion_mapper.py       # See angle mapping
   python robot_simulator.py     # See robot control
   ```

3. **Read details:** `SYSTEM_ARCHITECTURE.md`
   - Deep dive into each module
   - Mathematical explanations
   - Performance analysis

4. **Study code:**
   - Read comments in order
   - Modify one parameter
   - Observe effect

5. **Experiment:**
   - Try extensions
   - Build custom features
   - Solve your own problems

---

## 📞 **Quick Help**

| Issue | Solution |
|-------|----------|
| Can't import modules | Check you're in project directory |
| ModuleNotFoundError | Run `python install_dependencies.py` |
| Webcam frozen | Restart program |
| Robot not moving | Check confidence_threshold is not 0 |
| Too much lag | Lower filter alpha or use GPU |
| Code doesn't change behavior | Check you saved the file |
| Want to start fresh | Delete all .pyc files, restart |

---

**Happy Learning! 🤖**

---

# 📎 APPENDIX: Code Snippets

### Minimal Example
```python
from pose_detector import PoseDetector
from joint_angle_extractor import JointAngleExtractor
import cv2

detector = PoseDetector()
extractor = JointAngleExtractor(use_degrees=False)
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if detector.detect(frame):
        landmarks = detector.get_landmarks()
        angles = extractor.extract_key_angles(landmarks)
        print(f"Left elbow: {angles['left_elbow']:.2f} rad")
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
detector.close()
```

### Just Pose Detection
```python
from pose_detector import PoseDetector
import cv2

detector = PoseDetector()
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if detector.detect(frame):
        display = detector.draw_landmarks(frame)
        cv2.imshow("Pose", display)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
detector.close()
```

### Just Robot Simulation
```python
from robot_simulator import RobotSimulator
import numpy as np

sim = RobotSimulator(use_gui=True)
sim.load_ground_plane()
sim.load_robot("r2d2.urdf")

# Wiggle joints
for frame in range(200):
    phase = (frame * 0.1) % (2 * np.pi)
    angles = {
        'joint1': np.sin(phase) * 0.5,
        'joint2': np.cos(phase) * 0.3,
    }
    sim.set_all_joint_angles(angles)
    sim.step_simulation(2)

sim.close()
```

---

**End of Quick Reference**
