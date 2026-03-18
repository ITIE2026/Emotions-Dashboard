"""
neuroflow_launcher.py
────────────────────────────────────────────────────────────────────────────────
NEUROFLOW — EEG Focus-Based App Launcher
  Stage 1 : Device Detection (Capsule Band/Headphones via BLE)
  Stage 2 : Electrode Resistance Check (any 2+ channels ≤ 500 kΩ)
  Stage 3 : Quick Calibration & Baseline Correction (IAPF alpha-peak)
  Stage 4 : Live EEG Signal Waveform (T3, T4, O1, O2)
  Stage 5 : PSD Spectral Analysis (Delta/Theta/Alpha/Beta/SMR bands)
  Stage 6 : Concentration Index  CI = Beta / (Theta + Alpha)
             → sustain CI above threshold for 10 s to launch the selected app

  ★  SIMULATION MODE auto-starts if no device is found  ★
"""

import os, sys, time, subprocess, threading, collections, math, random
from typing import Any, List
import pyqtgraph as pg
import numpy as np

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, 'api')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QListWidget, QListWidgetItem, QTextEdit, QPushButton,
    QProgressBar, QFrame, QScrollArea
)
from PyQt5.QtCore  import QTimer, Qt, pyqtSignal, QObject, QRect, QPointF  # type: ignore
from PyQt5.QtGui   import (  # type: ignore
    QFont, QPainter, QPen, QColor, QLinearGradient, QBrush, QPainterPath, QRadialGradient
)

# ── Capsule API (gracefully optional so the file imports regardless) ──────────
try:
    from api.Capsule      import Capsule            # type: ignore
    from api.DeviceLocator import DeviceLocator     # type: ignore
    from api.DeviceType   import DeviceType         # type: ignore
    from api.Error        import Error              # type: ignore
    from api.Device       import Device, Device_Connection_Status  # type: ignore
    from api.EEGTimedData import EEGTimedData       # type: ignore
    from api.Calibrator   import Calibrator         # type: ignore
    from api.Resistances  import Resistances        # type: ignore
    from api.PSDData      import PSDData, PSDData_Band  # type: ignore
    from api.EEGArtifacts import EEGArtifacts       # type: ignore
    CAPSULE_AVAILABLE = True
except Exception as _e:
    print(f"[WARN] Capsule API not loaded: {_e} — simulation-only mode.")
    CAPSULE_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Parameters
# ─────────────────────────────────────────────────────────────────────────────
BETA_WINDOW_SIZE         = 30     # primary PSD frames averaged for CI (≈15 s if PSD@2s)
CI_FOCUS_THRESHOLD       = 0.38   # CI must REACH this to start focus timer
CI_FOCUS_DROPOUT         = 0.15   # CI must DROP BELOW this to reset timer (wide hysteresis)
CI_FOCUS_CONSEC_REQUIRED = 2      # consecutive above-threshold PSD frames before dwell starts
CI_FOCUS_SMOOTH_FRAMES   = 12     # secondary smoothing window (on top of BETA_WINDOW_SIZE)
FOCUS_DWELL_SECONDS      = 2.0    # seconds to sustain focus before launching
TRIGGER_COOLDOWN         = 5.0    # seconds between launches
EEG_BUFFER_SAMPLES       = 1250   # samples stored per channel (5s @ 250Hz)
SIM_START_DELAY_S        = 15.0   # seconds to wait before auto-starting simulation

STAGE_DETECTING   = 0
STAGE_RESISTANCE  = 1
STAGE_CALIBRATING = 2
STAGE_EEG         = 3
STAGE_SPECTRAL    = 4
STAGE_FOCUS       = 5
STAGES = [
    ("🔍", "Device\nDetection"),
    ("⚡", "Resistance\nCheck"),
    ("🔧", "Calibration\n& Baseline"),
    ("📊", "EEG\nStreaming"),
    ("🌊", "Spectral\nAnalysis"),
    ("🎯", "Focus\nLaunch"),
]

BAND_COLORS = {
    "Delta": "#5555ff", "Theta": "#00bcd4",
    "Alpha": "#4caf50", "Beta":  "#ff9800", "SMR": "#e91e63",
}

APPS = [
    {"name": "Google Chrome",     "icon": "🌐",
     "cmd": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
     "fallback": ["start", "chrome"], "shell": False},
    {"name": "System Settings",   "icon": "⚙️", "cmd": None,
     "fallback": ["start", "ms-settings:"], "shell": True},
    {"name": "Microsoft Word",    "icon": "📝", "cmd": None,
     "fallback": ["start", "winword"], "shell": True},
    {"name": "Microsoft Excel",   "icon": "📊", "cmd": None,
     "fallback": ["start", "excel"], "shell": True},
    {"name": "Microsoft PowerPoint", "icon": "📑", "cmd": None,
     "fallback": ["start", "powerpnt"], "shell": True},
]

def launch_app(app: dict):
    print(f">>> Launching: {app['name']}")
    cmd, fallback, shell = app.get("cmd"), app.get("fallback",[]), app.get("shell",False)
    if cmd and os.path.exists(cmd):
        try: subprocess.Popen([cmd]); return
        except Exception as e: print(e)
    if fallback:
        try:
            subprocess.Popen(" ".join(fallback) if shell else fallback, shell=shell)
            return
        except Exception as e: print(e)


# ── Digital Signal Processing (DSP) Helpers ───────────────────────────────────
try:
    import numpy as np
    from scipy.signal import butter, lfilter, iirnotch
    HAS_DSP = True
except ImportError:
    HAS_DSP = False

class RealtimeFilter:
    """Manages filter states for individual EEG channels to prevent transients."""
    def __init__(self, fs=250.0):
        self.fs = fs
        # 0.5-30 Hz Bandpass for cleaner visual peaks
        self.b_bp, self.a_bp = butter(4, [0.5, 30.0], btype='bandpass', fs=fs)
        # 50 Hz Notch
        self.b_nt, self.a_nt = iirnotch(50.0, 30.0, fs=fs)
        self.zi_bp = None
        self.zi_nt = None

    def apply(self, x):
        if not HAS_DSP: return x
        x = np.array(x, dtype=np.float64)
        if self.zi_bp is None:
            from scipy.signal import lfilter_zi
            self.zi_bp = lfilter_zi(self.b_bp, self.a_bp) * x[0]
            self.zi_nt = lfilter_zi(self.b_nt, self.a_nt) * x[0]
        
        y1, self.zi_bp = lfilter(self.b_bp, self.a_bp, x, zi=self.zi_bp)
        y2, self.zi_nt = lfilter(self.b_nt, self.a_nt, y1, zi=self.zi_nt)
        return y2.tolist()

# ── Calibration Overlay ───────────────────────────────────────────────────────
class CalibrationOverlay(QWidget):
    """Full-screen translucent overlay for eyes-closed calibration with countdown timer."""
    DURATION = 30  # seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._start_time = 0.0
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setInterval(200)   # 5 fps is enough for countdown
        self._repaint_timer.timeout.connect(self.update)
        self.hide()
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Dark overlay
        p.fillRect(self.rect(), QColor(2, 6, 23, 230))
        
        cx, cy = self.width() // 2, self.height() // 2
        t = time.time()
        
        # Center Icon / Text
        p.setPen(QColor("#38BDF8"))
        p.setFont(QFont("Segoe UI Emoji", 64))
        eye_glyph = "👁️\u200d🗨️" if (int(t * 2) % 2) else "🧘"
        p.drawText(cx - 100, cy - 160, 200, 100, Qt.AlignCenter, eye_glyph)
        
        p.setFont(QFont("Segoe UI", 18, QFont.Bold))
        p.setPen(QColor("#38BDF8"))
        p.drawText(QRect(0, cy - 60, self.width(), 40), Qt.AlignCenter,
                   "RELAX & CLOSE YOUR EYES")
        p.setFont(QFont("Segoe UI", 11))
        p.setPen(QColor("#94a3b8"))
        p.drawText(QRect(0, cy - 20, self.width(), 30), Qt.AlignCenter,
                   "Calibration in progress...")

        # ── Countdown timer ──────────────────────────────────────────────────
        elapsed = t - self._start_time if self._start_time > 0 else 0
        remaining = max(0, self.DURATION - int(elapsed))
        frac_done = min(1.0, elapsed / self.DURATION)

        # Arc background
        R = 56
        arc_rect = QRect(cx - R, cy + 30, R * 2, R * 2)
        p.setPen(QPen(QColor("#1e3a5f"), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 0, 360 * 16)

        # Arc fill (sweeps as time passes)
        sweep = int(frac_done * 360 * 16)
        arc_col = QColor("#10b981") if remaining > 5 else QColor("#f59e0b")
        p.setPen(QPen(arc_col, 8, Qt.SolidLine, Qt.RoundCap))
        if sweep > 0:
            p.drawArc(arc_rect, 90 * 16, -sweep)

        # Countdown number
        p.setPen(QColor("#f8fafc"))
        p.setFont(QFont("Segoe UI", 26, QFont.Bold))
        p.drawText(arc_rect, Qt.AlignCenter, str(remaining))

        # 's' label below arc
        p.setPen(QColor("#64748b"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(cx - 40, cy + 30 + R * 2 + 4, 80, 18), Qt.AlignCenter, "seconds")

        # STAY STILL pulse
        p.setFont(QFont("Segoe UI", 12, QFont.Bold))
        p.setPen(QColor(255, 255, 255, int(150 + 50 * math.sin(t * 3))))
        p.drawText(cx - 100, cy + 30 + R * 2 + 28, 200, 30, Qt.AlignCenter, "STAY STILL")
        
    def start(self):
        self._start_time = time.time()
        self.show()
        self.raise_()
        self._repaint_timer.start()
        # Auto-dismiss after DURATION seconds regardless of calibration state
        QTimer.singleShot(self.DURATION * 1000, self.stop)
        
    def stop(self):
        self._repaint_timer.stop()
        self.hide()

# ─────────────────────────────────────────────────────────────────────────────
# Custom Widgets
# ─────────────────────────────────────────────────────────────────────────────


class ElectrodeStripWidget(QWidget):
    """Horizontal row of 4 electrode status dots with labels and resistance check line."""
    HEADPHONE_CHANNELS = ["C3", "C4", "A1", "A2"]
    HEADBAND_CHANNELS  = ["T3",  "T4",  "O1",  "O2"]

    def __init__(self, parent=None, headband: bool = True):
        super().__init__(parent)
        self.setFixedHeight(90)
        self._channels = self.HEADBAND_CHANNELS if headband else self.HEADPHONE_CHANNELS
        self._status = {ch: "ok" for ch in self._channels}
        self._ohms   = {ch: 0 for ch in self._channels}

    def set_mode(self, headband: bool):
        self._channels = self.HEADBAND_CHANNELS if headband else self.HEADPHONE_CHANNELS
        self._status = {ch: "ok" for ch in self._channels}
        self._ohms   = {ch: 0 for ch in self._channels}
        self.update()

    # Realistic EEG thresholds: OK < 250 kΩ, WARN < 750 kΩ, BAD ≥ 750 kΩ
    RESIST_OK   = 250_000   # 250 kΩ
    RESIST_WARN = 750_000   # 750 kΩ

    def set_resistance(self, ch: str, ohms: float):
        # Accept both headband and headphone names
        if ch not in self._channels:
            return
        if ohms <= self.RESIST_OK:
            self._status[ch] = "ok"
        elif ohms <= self.RESIST_WARN:
            self._status[ch] = "warn"
        else:
            self._status[ch] = "bad"
        self._ohms[ch] = ohms
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self._channels)
        step = w // n
        R = 22          # larger dots

        COLOR = {"ok": "#10b981", "warn": "#f59e0b", "bad": "#ef4444"}
        GLOW  = {"ok": "#064e3b", "warn": "#78350f", "bad": "#7f1d1d"}

        cy = h // 2 - 6
        lxs, lxe = step // 2, w - step // 2

        # Base line
        p.setPen(QPen(QColor("#1e3a5f"), 2))
        p.drawLine(lxs, cy, lxe, cy)

        for i, ch in enumerate(self._channels):
            cx = step // 2 + i * step
            st = self._status[ch]
            col = QColor(COLOR[st])
            glow = QColor(GLOW[st])

            # Segment of the line between dots colored per status
            if i < n - 1:
                nx = step // 2 + (i + 1) * step
                seg_col = QColor(COLOR[st])
                seg_col.setAlpha(90)
                p.setPen(QPen(seg_col, 3))
                p.drawLine(cx, cy, nx, cy)

            # Glow halo
            g = QRadialGradient(cx, cy, R + 10)
            g.setColorAt(0.0, col)
            g.setColorAt(0.5, glow)
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(g))
            p.setPen(Qt.NoPen)
            p.drawEllipse(cx - R - 10, cy - R - 10, (R + 10) * 2, (R + 10) * 2)

            # Main circle
            p.setBrush(QBrush(col.darker(170)))
            p.setPen(QPen(col, 2))
            p.drawEllipse(cx - R, cy - R, R * 2, R * 2)

            # Channel label inside dot
            p.setPen(QPen(QColor("#f0fdf4"), 1))
            p.setFont(QFont("Consolas", 8, QFont.Bold))
            p.drawText(cx - R, cy - R, R * 2, R * 2, Qt.AlignCenter, ch)

            # Resistance label below dot (auto-scale to Ω / kΩ / MΩ)
            p.setFont(QFont("Consolas", 8))
            p.setPen(QColor("#94a3b8"))
            v = self._ohms[ch]
            if v <= 0:
                ohm_str = "--"
            elif v >= 1_000_000:
                ohm_str = f"{v/1_000_000:.1f}MΩ"
            elif v >= 1_000:
                ohm_str = f"{v/1_000:.0f}kΩ"
            else:
                ohm_str = f"{int(v)}Ω"
            p.drawText(cx - 30, cy + R + 4, 60, 16, Qt.AlignCenter, ohm_str)

# Alias for backward compat
HeadModelWidget = ElectrodeStripWidget


class SignalQualityBadge(QWidget):
    """Compact horizontal row of 4 small channel-status dots for use in a header bar."""
    _CH_NAMES = ["T3", "T4", "O1", "O2"]
    _COLORS = {"ok": "#10b981", "warn": "#f59e0b", "bad": "#ef4444", "idle": "#334155"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = {ch: "idle" for ch in self._CH_NAMES}
        # Fixed compact size: 4 dots * 26px each + some padding
        self.setFixedSize(130, 36)

    RESIST_OK   = 500_000   # 500 kΩ
    RESIST_WARN = 750_000   # 750 kΩ

    def set_resistance(self, ch: str, ohms: float):
        if ch not in self._CH_NAMES:
            return
        if ohms <= self.RESIST_OK:
            self._status[ch] = "ok"
        elif ohms <= self.RESIST_WARN:
            self._status[ch] = "warn"
        else:
            self._status[ch] = "bad"
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self._CH_NAMES)
        w, h = self.width(), self.height()
        slot = w // n
        R = 8   # dot radius
        cy = h // 2
        for i, ch in enumerate(self._CH_NAMES):
            cx = slot // 2 + i * slot
            col = QColor(self._COLORS[self._status[ch]])
            # filled dot
            p.setBrush(QBrush(col.darker(160)))
            p.setPen(QPen(col, 1.5))
            p.drawEllipse(cx - R, cy - R - 4, R * 2, R * 2)
            # label below
            p.setFont(QFont("Consolas", 6, QFont.Bold))
            p.setPen(QColor("#94a3b8"))
            p.drawText(cx - 14, cy + 6, 28, 12, Qt.AlignCenter, ch)



class PipelineStepWidget(QWidget):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)  # type: ignore[call-arg]
        self._icon, self._label, self._state = icon, label, "pending"
        self.setFixedSize(120, 100)

    def set_state(self, s):
        self._state = s; self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        cx, cy, r = self.width()//2, 34, 26
        fill = {"done":"#00c853","active":"#7b2ff7","pending":"#1a1a3a"}[self._state]
        p.setBrush(QBrush(QColor(fill)))
        p.setPen(QPen(QColor("#fff" if self._state!="pending" else "#333355"), 2))
        p.drawEllipse(cx-r, cy-r, r*2, r*2)
        p.setFont(QFont("Segoe UI Emoji", 14))
        p.setPen(Qt.white)
        p.drawText(QRect(cx-r, cy-r, r*2, r*2), Qt.AlignCenter, self._icon)
        p.setPen(QColor("#fff" if self._state!="pending" else "#444466"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.drawText(QRect(0, 64, 120, 36), Qt.AlignCenter|Qt.TextWordWrap, self._label)


class PipelineWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)  # type: ignore[call-arg]
        lo = QHBoxLayout(self); lo.setContentsMargins(12, 4, 12, 4); lo.setSpacing(0)
        self._steps: List[PipelineStepWidget] = []
        for i,(icon,label) in enumerate(STAGES):
            s = PipelineStepWidget(icon, label); self._steps.append(s); lo.addWidget(s)
            if i < len(STAGES)-1:
                a = QLabel("›"); a.setAlignment(Qt.AlignCenter)
                a.setStyleSheet("color:#334175;font-size:24px;font-weight:bold;"); a.setFixedWidth(28)
                lo.addWidget(a)
        self._steps[0].set_state("active")

    def set_stage(self, idx: int):
        for i, s in enumerate(self._steps):
            s.set_state("done" if i<idx else "active" if i==idx else "pending")


class EEGCanvas(pg.GraphicsLayoutWidget):
    """Scrolling multi-channel EEG waveform drawn with pyqtgraph at 30 fps."""
    # Scale settings (µV/pixel)
    _SCALE_INIT  = 8.0      # starting scale
    _SCALE_FLOOR = 1e-8     # ultra-sensitive floor — allows zooming to 100 pV/div and below
    _SCALE_EMA_UP   = 0.35  # faster zoom-in
    _SCALE_EMA_DOWN = 0.05  # faster zoom-out

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setBackground("#020617")
        self._bufs:  List[collections.deque] = []
        self._names: List[str] = []
        self._colors = ["#00e5ff","#ff9800","#4caf50","#e91e63","#7b2ff7","#ffeb3b"]
        
        self._plots = []
        self._curves = []
        self._texts = []

        self._scale    = self._SCALE_INIT
        self._auto_scale = True
        self._has_data = False
        self._sim_badge = False
        self._snap_badge = False
        self.setFocusPolicy(Qt.StrongFocus) # enable key events

        # 30 fps render timer — decouples data ingestion from painting
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(33)          # ~30 fps
        self._render_timer.timeout.connect(self._tick)
        self._render_timer.start()

    def set_channels(self, names: List[str]):
        self._names = names
        self.clear()
        self._plots.clear()
        self._curves.clear()
        self._texts.clear()
        self._bufs = [collections.deque([0.0]*EEG_BUFFER_SAMPLES, maxlen=EEG_BUFFER_SAMPLES) for _ in names]
        # Per-channel independent EMA scales
        self._ch_scales = [self._SCALE_INIT] * len(names)
        
        for i, name in enumerate(names):
            p = self.addPlot(row=i, col=0)
            p.hideAxis('bottom')
            p.hideAxis('left')
            p.setMouseEnabled(x=False, y=False)
            p.setMenuEnabled(False)
            
            # channel label
            color = self._colors[i % len(self._colors)]
            text = pg.TextItem(name, color=color, anchor=(0, 0))
            p.addItem(text)
            self._texts.append(text)
            
            curve = p.plot(pen=pg.mkPen(color=color, width=1.5))
            self._plots.append(p)
            self._curves.append(curve)

        self._has_data = False
        self._scale    = self._SCALE_INIT

    def push_samples(self, ch: int, samples: List[float]):
        if ch >= len(self._bufs):
            while len(self._bufs) <= ch:
                n = len(self._bufs)
                names = self._names + [f"CH{n+1}"]
                self.set_channels(names)
        self._bufs[ch].extend(samples)
        if any(abs(v) > 0.0001 for v in samples):
            self._has_data = True

    def _tick(self):
        if not self._has_data:
            return

        slot_h = max(self.height() / max(len(self._bufs), 1), 1.0)

        for i, buf in enumerate(self._bufs):
            arr = np.array(buf)
            arr = np.nan_to_num(arr)

            self._curves[i].setData(arr)
            self._plots[i].setXRange(0, EEG_BUFFER_SAMPLES, padding=0)

            # ── Per-channel independent EMA scale (only if auto-scale is ON) ──
            peak_ch = float(np.max(np.abs(arr)))
            if self._auto_scale and peak_ch > 0:
                ideal = max(self._SCALE_FLOOR, peak_ch / (slot_h * 0.40))
                cur   = self._ch_scales[i]
                ratio = ideal / cur if cur > 0 else 1e9
                if ratio < 0.01 or ratio > 100:
                    self._ch_scales[i] = ideal
                else:
                    a = self._SCALE_EMA_UP if ideal > cur else self._SCALE_EMA_DOWN
                    self._ch_scales[i] = a * ideal + (1.0 - a) * cur
                self._ch_scales[i] = max(self._SCALE_FLOOR, self._ch_scales[i])

            max_val = self._ch_scales[i] * slot_h * 0.45
            self._texts[i].setPos(0, max_val * 0.8)
            self._plots[i].setYRange(-max_val, max_val, padding=0)

        # Update global _scale as median of channel scales (used for label)
        if self._ch_scales:
            self._scale = float(np.median(self._ch_scales))

    def auto_scale(self, peak: float):
        pass

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if not self._has_data or not self._bufs:
            return
        # Re-enable auto-scale on double click
        self._auto_scale = True
        slot_h = max(self.height() / max(len(self._bufs), 1), 1.0)
        for i, buf in enumerate(self._bufs):
            try:
                peak_ch = max(abs(v) for v in buf
                              if not (math.isnan(v) or math.isinf(v)))
                if peak_ch > 0:
                    self._ch_scales[i] = max(self._SCALE_FLOOR,
                                             peak_ch / (slot_h * 0.40))
            except ValueError:
                pass
        self._scale = float(np.median(self._ch_scales)) if self._ch_scales else self._SCALE_INIT
        self._snap_badge = True
        QTimer.singleShot(1500, self._clear_snap_badge)
        self.viewport().update()

    def wheelEvent(self, event):
        """User scrolled wheel — manual scale adjustment, disables auto-scale."""
        if not self._has_data:
            return
        self._auto_scale = False
        delta = event.angleDelta().y()
        factor = 0.75 if delta > 0 else 1.25  # aggressive zoom
        self._ch_scales = [max(self._SCALE_FLOOR, s * factor)
                           for s in self._ch_scales]
        self._scale = float(np.median(self._ch_scales)) if self._ch_scales else self._SCALE_INIT
        self.viewport().update()
        event.accept()

    def keyPressEvent(self, event):
        """Keyboard manual zoom (+/-)."""
        if event.key() in [Qt.Key_Plus, Qt.Key_Equal]:
            self._adjust_manual_scale(0.8)
        elif event.key() in [Qt.Key_Minus, Qt.Key_Underscore]:
            self._adjust_manual_scale(1.25)
        else:
            super().keyPressEvent(event)

    def _adjust_manual_scale(self, factor):
        self._auto_scale = False
        self._ch_scales = [max(self._SCALE_FLOOR, s * factor) for s in self._ch_scales]
        self._scale = float(np.median(self._ch_scales)) if self._ch_scales else self._SCALE_INIT
        self.viewport().update()

    def _clear_snap_badge(self):
        self._snap_badge = False
        self.viewport().update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self.viewport())
        if not self._has_data:
            p.setPen(QColor("#333355"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "⏳  Waiting for EEG signal…")
            return
            
        w = self.width()
        
        # Horizontal separators overlay
        n_ch = max(len(self._bufs), 1)
        ch_h = self.height() / n_ch
        p.setPen(QPen(QColor("#334155"), 1))
        for i in range(1, n_ch):
            p.drawLine(0, int(ch_h*i), w, int(ch_h*i))

        if self._sim_badge:
            p.fillRect(w-72, 2, 70, 18, QColor("#7b2ff7"))
            p.setPen(Qt.white); p.setFont(QFont("Segoe UI", 7, QFont.Bold))
            p.drawText(w-72, 2, 70, 18, Qt.AlignCenter, "SIMULATION")

        if self._snap_badge:
            bw = 110
            bx = w // 2 - bw // 2
            by = self.height() - 24
            p.fillRect(bx, by, bw, 20, QColor("#10b981"))
            p.setPen(Qt.white); p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(bx, by, bw, 20, Qt.AlignCenter, "✓  Auto-scaled")

        scale_val = self._scale * (self.height() / max(len(self._bufs), 1)) * 0.40
        if scale_val >= 1000:
            scale_str = f"{scale_val/1000:.2f} mV/div"
        elif scale_val >= 1.0:
            scale_str = f"{scale_val:.2f} µV/div"
        elif scale_val >= 0.001:
            scale_str = f"{scale_val*1000:.2f} nV/div"
        else:
            scale_str = f"{scale_val*1e6:.2f} pV/div"
            
        p.setPen(QColor("#475569"))
        p.setFont(QFont("Consolas", 7))
        lbl_w = 90
        p.drawText(w - lbl_w - (74 if self._sim_badge else 4), 4, lbl_w, 14,
                   Qt.AlignRight, scale_str)



class CircularGauge(QWidget):
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = color
        self.val = 0.0
        self.setMinimumSize(90, 110)
    
    def set_value(self, val):
        self.val = val
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#020617"))
        
        w, h = self.width(), self.height()
        cx, cy, r = w//2, h//2 - 10, min(w, h)//2 - 20
        
        # Background arc
        p.setPen(QPen(QColor("#1e293b"), 6, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 0*16, 360*16)
        
        # Value arc
        sweep = int(360 * min(self.val, 1.0))
        p.setPen(QPen(QColor(self.color), 8, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 90*16, -sweep*16)
        
        # blow
        g = QRadialGradient(cx, cy, r)
        c_glow = QColor(self.color)
        c_glow.setAlpha(40)
        g.setColorAt(0.7, c_glow)
        g.setColorAt(1.0, QColor(0,0,0,0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx-r-5, cy-r-5, r*2+10, r*2+10)
        
        # text
        p.setPen(QColor("#f8fafc"))
        p.setFont(QFont("Segoe UI", 14, QFont.Bold))
        p.drawText(QRect(cx-r, cy-r, r*2, r*2), Qt.AlignCenter, f"{int(self.val*100)}%")
        
        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.drawText(QRect(0, h-20, w, 20), Qt.AlignCenter, self.title)

class HeatmapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        import random
        self._grid = [[random.uniform(0, 1) for _ in range(20)] for _ in range(10)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._shift)
        self._timer.start(100)
        
    def _shift(self):
        import random
        for i in range(10):
            self._grid[i].pop(0)
            self._grid[i].append(random.uniform(0, 1))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#020617"))
        
        cell_w = (w-30) / 20.0
        cell_h = (h-20) / 10.0
        
        p.setPen(QColor("#334155")); p.setFont(QFont("Consolas", 7))
        p.drawText(2, h//2, "FREQ")
        
        for i in range(10):
            for j in range(20):
                val = self._grid[i][j]
                # Heatmap coloring
                r = int(val * 255)
                g = int((1-abs(val-0.5)*2) * 200)
                b = int((1-val) * 200)
                p.fillRect(int(30+j*cell_w), int(i*cell_h), int(cell_w)+1, int(cell_h)+1, QColor(r,g,b,180))
        
        p.setPen(QColor("#64748b"))
        p.drawText(30, h-5, "0s")
        p.drawText(w//2, h-5, "Live Window")

class CIGauge(QWidget):
    """Large 270° gear-style concentration-index gauge."""
    CI_MAX = 1.5        # full-scale CI value
    SPAN   = 270        # degrees of arc
    START  = 225        # start angle (degrees, clock-wise from 3-o'clock = Qt coords)

    def __init__(self, parent=None):
        super().__init__(parent)  # type: ignore[call-arg]
        self.setMinimumSize(280, 280)
        self._ci = 0.0
        self._thr = CI_FOCUS_THRESHOLD
        self._has_data = False

    def set_ci(self, ci: float):
        self._ci = ci
        self._has_data = True
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#020617"))

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        R = int(min(w, h) * 0.42)   # outer radius
        r_track = R - 8

        if not self._has_data:
            p.setPen(QColor("#334155"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for data…")
            return

        # ── Outer gear-ring tick marks ────────────────────────────────────────
        N_MAJOR = 10        # 0.0 to 1.5 in 10 steps of 0.15
        N_MINOR = 4         # minor ticks per major division
        total_ticks = N_MAJOR * N_MINOR
        p.setPen(QPen(QColor("#1e3a5f"), 1))
        for ti in range(total_ticks + 1):
            frac   = ti / total_ticks
            ang_deg = 225 - frac * 270            # goes from 225° → -45° (=315°)
            ang_rad = math.radians(ang_deg)
            is_major = (ti % N_MINOR == 0)
            r_inner = R - (10 if is_major else 5)
            r_outer = R + (4 if is_major else 2)

            x1 = cx + r_inner * math.cos(ang_rad)
            y1 = cy - r_inner * math.sin(ang_rad)
            x2 = cx + r_outer * math.cos(ang_rad)
            y2 = cy - r_outer * math.sin(ang_rad)

            col = QColor("#334155") if not is_major else QColor("#475569")
            p.setPen(QPen(col, 2 if is_major else 1))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

            # Major label
            if is_major:
                val_label = f"{ti / total_ticks * self.CI_MAX:.1f}"
                lx = cx + (R + 18) * math.cos(ang_rad)
                ly = cy - (R + 18) * math.sin(ang_rad)
                p.setPen(QColor("#64748b"))
                p.setFont(QFont("Consolas", 7))
                p.drawText(int(lx) - 14, int(ly) - 7, 28, 14,
                           Qt.AlignCenter, val_label)

        # ── Background track ─────────────────────────────────────────────────
        rect = QRect(cx - r_track, cy - r_track, r_track * 2, r_track * 2)
        p.setPen(QPen(QColor("#0f2035"), 18, Qt.SolidLine, Qt.RoundCap))
        # Qt arc: 0° = 3 o'clock, angles in 1/16°, positive = counter-clockwise
        # We want arc from 225° (lower-left) sweeping 270° clockwise
        # In Qt: startAngle = 225*16, spanAngle = -270*16
        p.drawArc(rect, int(225 * 16), int(-270 * 16))

        # ── Threshold marker ─────────────────────────────────────────────────
        thr_frac = min(self._thr / self.CI_MAX, 1.0)
        thr_deg  = 225 - thr_frac * 270
        thr_rad  = math.radians(thr_deg)
        tx1 = cx + (r_track - 14) * math.cos(thr_rad)
        ty1 = cy - (r_track - 14) * math.sin(thr_rad)
        tx2 = cx + (r_track + 14) * math.cos(thr_rad)
        ty2 = cy - (r_track + 14) * math.sin(thr_rad)
        p.setPen(QPen(QColor("#f59e0b"), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(int(tx1), int(ty1), int(tx2), int(ty2))

        # ── Value arc (gradient green) ────────────────────────────────────────
        frac    = min(self._ci / self.CI_MAX, 1.0)
        sweep   = int(frac * 270 * 16)
        above   = self._ci >= self._thr
        arc_col = QColor("#10b981") if above else QColor("#6366f1")
        p.setPen(QPen(arc_col, 16, Qt.SolidLine, Qt.RoundCap))
        if sweep > 0:
            p.drawArc(rect, int(225 * 16), -sweep)

        # Glow layer (thinner, lighter, slightly inside)
        glow_col = QColor("#34d399" if above else "#818cf8")
        glow_col.setAlpha(90)
        p.setPen(QPen(glow_col, 8, Qt.SolidLine, Qt.RoundCap))
        if sweep > 0:
            p.drawArc(rect, int(225 * 16), -sweep)

        # ── Needle ────────────────────────────────────────────────────────────
        val_deg = 225 - frac * 270
        val_rad = math.radians(val_deg)
        # Needle tip
        nx = cx + (r_track - 6) * math.cos(val_rad)
        ny = cy - (r_track - 6) * math.sin(val_rad)
        # Needle base offset
        bx = cx + 12 * math.cos(val_rad + math.pi)
        by = cy - 12 * math.sin(val_rad + math.pi)
        # Side wings for diamond shape
        wrad = val_rad + math.pi / 2
        wx = 6 * math.cos(wrad); wy = -6 * math.sin(wrad)
        needle_pts = [
            QPointF(nx, ny),
            QPointF(cx + wx, cy + wy),
            QPointF(bx, by),
            QPointF(cx - wx, cy - wy),
        ]
        path = QPainterPath()
        path.moveTo(needle_pts[0])
        for pt in needle_pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        p.setBrush(QBrush(QColor("#f59e0b")))
        p.setPen(QPen(QColor("#fef3c7"), 1))
        p.drawPath(path)

        # Center pivot
        p.setBrush(QBrush(QColor("#1e293b")))
        p.setPen(QPen(QColor("#38bdf8"), 2))
        p.drawEllipse(cx - 8, cy - 8, 16, 16)

        # ── Value display ─────────────────────────────────────────────────────
        val_col = "#10b981" if above else "#f8fafc"
        p.setPen(QColor(val_col))
        p.setFont(QFont("Segoe UI", 28, QFont.Bold))
        p.drawText(QRect(cx - 60, cy - 52, 120, 50), Qt.AlignCenter,
                   f"{self._ci:.2f}")

        p.setPen(QColor("#f59e0b"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(cx - 70, cy + 2, 140, 16), Qt.AlignCenter,
                   f"Threshold: {self._thr:.2f}")

        # Percentage right-side label
        pct = int(frac * 100)
        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        pct_deg = 225 - 270 * 0.5   # =90° → top
        pct_rad = math.radians(pct_deg)
        px = cx + (r_track + 28) * math.cos(math.radians(-45))
        py = cy - (r_track + 28) * math.sin(math.radians(-45))
        p.drawText(int(px) - 20, int(py) - 8, 40, 16, Qt.AlignCenter, f"{pct}%")



# ─────────────────────────────────────────────────────────────────────────────
# Simulation Engine  (runs entirely on GUI thread via QTimer)
# ─────────────────────────────────────────────────────────────────────────────
BAND_FREQS = {           # (center_Hz, approx_width) used in synthetic PSD
    "Delta": (2.0,  4),
    "Theta": (6.0,  4),
    "Alpha": (10.0, 4),
    "Beta":  (20.0, 12),
    "SMR":   (14.0, 4),
}
SIM_SAMPLE_RATE  = 250   # Hz
SIM_CHUNK_EVERY  = 40    # ms → emit 10 samples per tick


class SimulationEngine(QObject):
    """
    Generates synthetic EEG + PSD frames at realistic rates.
    Mimics the exact same signals that CapsuleWorker emits.
    CI oscillates naturally, peaking above CI_FOCUS_THRESHOLD every ~12 s
    so the user can see the full trigger cycle.
    """
    log_signal          = pyqtSignal(str)
    stage_signal        = pyqtSignal(int)
    connected_signal    = pyqtSignal(str)
    resistances_signal  = pyqtSignal(list)
    calibrated_signal   = pyqtSignal()
    eeg_signal          = pyqtSignal(int, list)
    psd_signal          = pyqtSignal(dict, float)
    focus_trigger_signal= pyqtSignal()
    channel_names_signal= pyqtSignal(list)  # emits list[str] of channel names

    def __init__(self):
        super().__init__()
        self._t       = 0.0        # simulation time (s)
        self._ci_win: collections.deque = collections.deque(maxlen=BETA_WINDOW_SIZE)
        self._focus_start = 0.0
        self._in_focus    = False
        self._last_trigger = 0.0
        self._timer: QTimer | None = None
        self._ch_names = ["T3", "T4", "O1", "O2"]
        # Per-channel DSP filters
        self._filters: dict[int, RealtimeFilter] = {}
        for i in range(len(self._ch_names)):
            self._filters[i] = RealtimeFilter(fs=SIM_SAMPLE_RATE)

    # ── Per-channel physiologically-inspired EEG model ───────────────────────
    @staticmethod
    def _make_eeg(t: float, ch: int, n_samples: int, dt: float) -> List[float]:
        """
        Distinct EEG profile per electrode location:
          Ch 0 = T3  Left Temporal  : theta + beta + muscle noise
          Ch 1 = T4  Right Temporal : higher beta asymmetry, less theta
          Ch 2 = O1  Left Occipital : strong alpha spindles (dominant)
          Ch 3 = O2  Right Occipital: alpha slightly different amplitude & phase
        """
        out = []
        for i in range(n_samples):
            ti = t + i * dt
            mod_i = 0.6 + 0.4 * math.sin(2 * math.pi * 0.05 * ti)

            if ch == 0:   # T3 — Left Temporal
                delta  =  5.0 * math.sin(2 * math.pi * 2.0 * ti + 0.3)
                theta  = 18.0 * (1.0 - mod_i * 0.5) * math.sin(2 * math.pi * 6.0 * ti)
                alpha  =  6.0 * math.sin(2 * math.pi * 10.0 * ti + 0.5)
                beta   = 14.0 * mod_i * math.sin(2 * math.pi * 22.0 * ti + 1.1)
                noise  = random.gauss(0, 3.0 + 4.0 * mod_i)   # muscle-like bursts

            elif ch == 1: # T4 — Right Temporal
                delta  =  4.0 * math.sin(2 * math.pi * 1.8 * ti + 1.2)
                theta  = 11.0 * (1.0 - mod_i * 0.5) * math.sin(2 * math.pi * 6.5 * ti + 0.8)
                alpha  =  7.0 * math.sin(2 * math.pi * 10.5 * ti + 1.8)
                beta   = 22.0 * mod_i * math.sin(2 * math.pi * 20.0 * ti + 0.4)
                noise  = random.gauss(0, 2.0 + 5.0 * mod_i)

            elif ch == 2: # O1 — Left Occipital (alpha-dominant)
                spindle = 0.7 + 0.3 * math.sin(2 * math.pi * 0.12 * ti)
                delta  =  3.0 * math.sin(2 * math.pi * 1.5 * ti + 2.1)
                theta  =  5.0 * math.sin(2 * math.pi * 5.5 * ti + 0.9)
                alpha  = 35.0 * (1.0 - mod_i * 0.7) * spindle * math.sin(2 * math.pi * 10.2 * ti)
                beta   =  4.0 * mod_i * math.sin(2 * math.pi * 18.0 * ti + 2.4)
                noise  = random.gauss(0, 1.2)

            else:          # O2 — Right Occipital
                spindle = 0.6 + 0.4 * math.sin(2 * math.pi * 0.10 * ti + 0.3)
                delta  =  3.5 * math.sin(2 * math.pi * 1.6 * ti + 0.7)
                theta  =  4.5 * math.sin(2 * math.pi * 5.8 * ti + 1.4)
                alpha  = 28.0 * (1.0 - mod_i * 0.6) * spindle * math.sin(2 * math.pi * 9.8 * ti + 0.6)
                beta   =  5.5 * mod_i * math.sin(2 * math.pi * 19.0 * ti + 1.7)
                noise  = random.gauss(0, 1.5)

            out.append(delta + theta + alpha + beta + noise)
        return out

    # ── Band power from time variable ─────────────────────────────────────────
    @staticmethod
    def _band_powers(t: float) -> dict:
        """
        Smooth time-varying band powers. Beta rises when the 0.05 Hz modulation
        is in its positive phase (roughly 10 s on, 10 s off).
        """
        mod = 0.6 + 0.4 * math.sin(2*math.pi*0.05*t)
        # Add a bit of noise to stop the gauge looking static
        jitter = lambda s: max(0.0, s + random.gauss(0, s*0.08))
        raw = {
            "Delta": jitter(0.25 * (1-mod)),
            "Theta": jitter(0.18 * (1-mod*0.5)),
            "Alpha": jitter(0.22 * (1-mod*0.8)),
            "Beta":  jitter(0.28 * mod),
            "SMR":   jitter(0.07 * mod),
        }
        total = sum(raw.values()) or 1.0
        return {k: v/total for k,v in raw.items()}

    # ── Timer tick ────────────────────────────────────────────────────────────
    def _tick(self):
        dt  = SIM_CHUNK_EVERY / 1000.0
        n   = max(1, int(SIM_SAMPLE_RATE * dt))

        # Emit EEG for 4 channels
        for ch in range(4):
            samples = self._make_eeg(self._t, ch, n, 1.0/SIM_SAMPLE_RATE)
            self.eeg_signal.emit(ch, samples)

        # Emit PSD every ~250 ms (every 6th tick)
        self._psd_tick = getattr(self, '_psd_tick', 0) + 1
        if self._psd_tick >= 6:
            self._psd_tick = 0
            bp = self._band_powers(self._t)
            # CI = (Beta + 0.5·SMR) / (Theta + Alpha)
            # Adding SMR (12–15 Hz) to numerator rewards calm, focused alertness.
            denom = bp["Theta"] + bp["Alpha"]
            ci = ((bp["Beta"] + 0.5 * bp["SMR"]) / denom) if denom > 1e-9 else 0.0
            self._ci_win.append(ci)
            avg_ci = sum(self._ci_win) / len(self._ci_win)
            self.psd_signal.emit(bp, avg_ci)
            self._evaluate_focus(avg_ci)

        self._t += dt

    def _evaluate_focus(self, avg_ci: float):
        now = time.time()
        if now - self._last_trigger < TRIGGER_COOLDOWN:
            self._in_focus = False; self._focus_start = 0.0; return
        if avg_ci >= CI_FOCUS_THRESHOLD:
            if not self._in_focus:
                self._in_focus = True; self._focus_start = now
                self.log_signal.emit(
                    f"🧠 [SIM] Focus detected  CI={avg_ci:.2f} — hold {FOCUS_DWELL_SECONDS:.0f}s…")
            elif now - self._focus_start >= FOCUS_DWELL_SECONDS:
                self.log_signal.emit(
                    f"✅ [SIM] FOCUS CONFIRMED  CI={avg_ci:.2f}")
                self._last_trigger = now
                self._in_focus = False; self._focus_start = 0.0
                self.focus_trigger_signal.emit()
        else:
            if self._in_focus:
                self.log_signal.emit(f"⚡ [SIM] Focus lost  CI={avg_ci:.2f}")
            self._in_focus = False; self._focus_start = 0.0

    def start(self):
        self.log_signal.emit("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log_signal.emit("🟡  SIMULATION MODE — no device detected")
        self.log_signal.emit("   Connect a Capsule headband or headphones to use real EEG.")
        self.log_signal.emit("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        # Walk through pipeline stages using named helpers (avoids pyright lambda issues)
        self._emit_detecting()
        QTimer.singleShot(600,  self._emit_resistance)
        QTimer.singleShot(1200, self._emit_res_values)
        QTimer.singleShot(1800, self._emit_calibrating)
        QTimer.singleShot(3500, self._finish_calib)

    def _emit_detecting(self) -> None:
        self.stage_signal.emit(STAGE_DETECTING)

    def _emit_resistance(self) -> None:
        self.stage_signal.emit(STAGE_RESISTANCE)

    def _emit_res_values(self) -> None:
        # Emit simulated channel names (real headband uses T3/T4/O1/O2)
        self.channel_names_signal.emit(["T3", "T4", "O1", "O2"])
        self.resistances_signal.emit(["T3: 12 Ω", "T4: 14 Ω", "O1: 18 Ω", "O2: 20 Ω"])

    def _emit_calibrating(self) -> None:
        self.stage_signal.emit(STAGE_CALIBRATING)
        self.log_signal.emit("🔧 Simulating calibration…")

    def _finish_calib(self):
        self.log_signal.emit("✅ [SIM] Calibration complete — streaming synthetic EEG.")
        self.stage_signal.emit(STAGE_EEG)
        self.connected_signal.emit("Sim-Device")
        self.calibrated_signal.emit()
        self._timer = QTimer(); self._timer.timeout.connect(self._tick)
        self._timer.start(SIM_CHUNK_EVERY)

    def stop(self):
        if self._timer:
            self._timer.stop(); self._timer = None


# ─────────────────────────────────────────────────────────────────────────────
# Capsule Worker  (real hardware, background thread)
# ─────────────────────────────────────────────────────────────────────────────

class CapsuleWorker(QObject):
    log_signal          = pyqtSignal(str)
    stage_signal        = pyqtSignal(int)
    connected_signal    = pyqtSignal(str)
    resistances_signal  = pyqtSignal(list)
    ready_to_calibrate_signal = pyqtSignal()   # emitted when resistance gate passes
    calibrated_signal   = pyqtSignal()
    eeg_signal          = pyqtSignal(int, list)
    psd_signal          = pyqtSignal(dict, float)
    focus_trigger_signal= pyqtSignal()
    channel_names_signal= pyqtSignal(list)  # emits list[str] of actual channel names

    # Resistance gate: calibrate when this many channels are ≤ RESIST_GATE_OHMS
    RESIST_GATE_OHMS    = 750_000   # 750 kΩ
    MIN_CHANNELS_READY  = 2         # need at least 2 electrodes in range
    CALIB_FALLBACK_SECS = 30        # force-start calibration after this timeout

    def __init__(self):
        super().__init__()
        self.dll_path      = os.path.join(ROOT, 'CapsuleClient.dll')
        self.capsuleLib: Any = None
        self.device_locator: Any = None
        self.device: Any   = None
        self.calibrator: Any = None
        self._ci_win: collections.deque = collections.deque(maxlen=BETA_WINDOW_SIZE)
        # Secondary CI smoothing for stable focus decisions
        self._focus_ci_buf: collections.deque = collections.deque(
            maxlen=CI_FOCUS_SMOOTH_FRAMES)
        self._focus_consec  = 0
        self._focus_start   = 0.0
        self._in_focus      = False
        self._last_trigger  = 0.0
        self._running       = True
        self._connected     = False  # True once Device_ConnectionState_Connected fires
        self._calibration_started = False
        self._is_calibrated = False
        self._resist_vals: dict = {}
        self._resist_connect_time = 0.0
        # Per-channel DSP filters
        self._filters: dict[int, RealtimeFilter] = {}
        self._conn_lock = threading.Lock()
        self._found = False  # guard: prevents multi-instantiation

    # ── EEG callback ──────────────────────────────────────────────────────────
    _eeg_first_logged = False   # class-level flag to log first EEG packet once

    def _on_eeg(self, device, data):
        if not self._running:
            return
        try:
            ns = data.get_samples_count()
            nc = data.get_channels_count()
            for ch in range(nc):
                raw = []
                for si in range(ns):
                    try:
                        # Prefer processed_value (SDK artifact-cleaned)
                        v = data.get_processed_value(ch, si)
                        # If processed is exactly 0.0 (baseline), fallback to raw for visibility
                        if v == 0.0:
                            v = data.get_raw_value(ch, si)
                        raw.append(v)
                    except:
                        try:
                            v = data.get_raw_value(ch, si)
                            raw.append(v)
                        except:
                            raw.append(0.0)
                
                # Apply Butterworth + Notch filtering
                if ch not in self._filters:
                    self._filters[ch] = RealtimeFilter(fs=250.0)
                filtered = self._filters[ch].apply(raw)
                self.eeg_signal.emit(ch, filtered)

            # Log first EEG packet once for diagnostics
            if not CapsuleWorker._eeg_first_logged:
                CapsuleWorker._eeg_first_logged = True
                try:
                    r0 = data.get_raw_value(0, 0)
                    p0 = data.get_processed_value(0, 0)
                    self.log_signal.emit(
                        f"📶 First EEG  nc={nc} ns={ns}  "
                        f"ch0 raw={r0:.4f}µV  processed={p0:.6f}µV"
                    )
                except Exception as ex2:
                    self.log_signal.emit(f"📶 First EEG  nc={nc} ns={ns} [val err: {ex2}]")
        except Exception as ex:
            if self._running:
                print(f"[EEG] {ex}")

    # ── PSD callback ──────────────────────────────────────────────────────────
    _psd_first_logged = False   # class-level flag

    def _on_psd(self, device, psd):
        if not self._running:        # guard: don't emit on destroyed QObject
            return
        try:
            nc = psd.get_channels_count(); nf = psd.get_frequencies_count()
            if nc == 0 or nf == 0: return

            # ── Standard EEG frequency band boundaries (Hz) ───────────────────────
            # Hardcoded as primary: get_band_lower/upper() returns 0.0 pre-calib
            # and silently produces zero band powers (no freq matches 0≤0≤0).
            STANDARD_BANDS: list[tuple[str, float, float]] = [
                ("Delta",  0.5,  4.0),
                ("Theta",  4.0,  8.0),
                ("Alpha",  8.0, 13.0),
                ("Beta",  15.0, 30.0),   # per Capsule SDK docs: 15–30 Hz
                ("SMR",   12.0, 15.0),
            ]

            # Try to override with device-reported individual band ranges
            # (only used if the device returns non-zero values, i.e. post-calib)
            band_map = {
                "Delta": PSDData_Band.PSDData_Band_Delta,
                "Theta": PSDData_Band.PSDData_Band_Theta,
                "Alpha": PSDData_Band.PSDData_Band_Alpha,
                "Beta":  PSDData_Band.PSDData_Band_Beta,
                "SMR":   PSDData_Band.PSDData_Band_SMR,
            }
            band_ranges: list[tuple[str, float, float]] = []
            for std_name, std_lo, std_hi in STANDARD_BANDS:
                api_lo, api_hi = std_lo, std_hi   # default to standard
                try:
                    _lo = float(psd.get_band_lower(band_map[std_name]))
                    _hi = float(psd.get_band_upper(band_map[std_name]))
                    if _lo > 0.0 and _hi > _lo:   # valid API value — use it
                        api_lo, api_hi = _lo, _hi
                except Exception:
                    pass
                band_ranges.append((std_name, api_lo, api_hi))

            bp: dict[str, float] = {
                "Delta": 0.0, "Theta": 0.0, "Alpha": 0.0, "Beta": 0.0, "SMR": 0.0
            }
            for ch in range(nc):
                for fi in range(nf):
                    try:
                        freq: float = float(psd.get_frequency(fi))
                        val:  float = float(psd.get_psd(ch, fi))
                        for _n, _lo2, _hi2 in band_ranges:
                            if _lo2 <= freq <= _hi2:
                                bp[_n] = bp[_n] + val
                    except Exception:
                        pass

            total = sum(bp.values()) or 1.0
            bp_pct = {k: v/total for k,v in bp.items()}
            # CI = (Beta + 0.5·SMR) / (Theta + Alpha)
            # Adding SMR (12–15 Hz) rewards calm, focused alertness and
            # produces a more sustained signal than Beta alone.
            denom  = bp["Theta"] + bp["Alpha"]
            ci     = (bp["Beta"] + 0.5 * bp["SMR"]) / denom if denom > 1e-9 else 0.0
            self._ci_win.append(ci)
            avg_ci = sum(self._ci_win)/len(self._ci_win)
            self.psd_signal.emit(bp_pct, avg_ci)
            self._eval_focus(avg_ci)

            # Log first PSD packet for diagnostics (show ranges used)
            if not CapsuleWorker._psd_first_logged:
                CapsuleWorker._psd_first_logged = True
                rng_str = "  ".join(f"{n}[{lo:.1f}-{hi:.1f}Hz]"
                                    for n, lo, hi in band_ranges)
                bp_str  = "  ".join(f"{k}={v:.4f}" for k, v in bp.items())
                self.log_signal.emit(
                    f"📊 First PSD  nc={nc} nf={nf}  CI={ci:.3f}\n"
                    f"   Ranges: {rng_str}\n"
                    f"   Powers: {bp_str}"
                )
        except Exception as ex:
            print(f"[PSD] {ex}")

    def _eval_focus(self, avg_ci: float):
        if not getattr(self, '_is_calibrated', False):
            return
        """
        Two-layer smoothed focus detection with wide hysteresis.
        Layer 1 (avg_ci)   : 30-frame PSD moving average (~60 s @ 0.5 Hz PSD)
        Layer 2 (focus_ci) : 12-frame secondary average on top of layer 1
        Hysteresis zone    : dropout=0.15 / threshold=0.38  (wide — resists brief dips)
        Consecutive gate   : CI_FOCUS_CONSEC_REQUIRED frames above threshold
                             before the dwell timer starts (blocks single spikes).
        Formula            : CI = (Beta + 0.5·SMR) / (Theta + Alpha)
        """
        # ── Secondary smoothing layer ──────────────────────────────────────
        self._focus_ci_buf.append(avg_ci)
        focus_ci = sum(self._focus_ci_buf) / len(self._focus_ci_buf)

        now = time.time()
        if now - self._last_trigger < TRIGGER_COOLDOWN:
            self._in_focus = False; self._focus_start = 0.0
            self._focus_consec = 0; return

        if focus_ci >= CI_FOCUS_THRESHOLD:
            self._focus_consec += 1          # count consecutive above-threshold frames
            if not self._in_focus:
                # Only start dwell timer after N consecutive above-threshold frames
                if self._focus_consec >= CI_FOCUS_CONSEC_REQUIRED:
                    self._in_focus = True; self._focus_start = now
                    self.log_signal.emit(
                        f"🧠 Focus sustained CI={focus_ci:.2f} — hold {FOCUS_DWELL_SECONDS:.0f}s…")
            elif now - self._focus_start >= FOCUS_DWELL_SECONDS:
                self.log_signal.emit(f"✅ FOCUS CONFIRMED  CI={focus_ci:.2f}")
                self._last_trigger = now
                self._in_focus = False; self._focus_start = 0.0; self._focus_consec = 0
                self.focus_trigger_signal.emit()
        elif focus_ci < CI_FOCUS_DROPOUT:
            # Genuine dropout — reset everything
            if self._in_focus:
                self.log_signal.emit(
                    f"⚡ Focus lost  CI={focus_ci:.2f} (dropout < {CI_FOCUS_DROPOUT})")
            self._in_focus = False; self._focus_start = 0.0; self._focus_consec = 0
        else:
            # Hysteresis zone (0.35 – 0.55): hold current state, reset consecutive counter
            self._focus_consec = 0

    @staticmethod
    def _fmt_ohms(v: float) -> str:
        """Format an ohm value as Ω / kΩ / MΩ for the system log."""
        if v >= 1_000_000:
            return f"{v/1_000_000:.2f} MΩ"
        if v >= 1_000:
            return f"{v/1_000:.1f} kΩ"
        return f"{v:.0f} Ω"

    def _on_resistances(self, device, res):
        data = []
        ok_count = 0
        try:
            for i in range(len(res)):
                try:
                    name = res.get_channel_name(i)
                    val  = float(res.get_value(i))
                    self._resist_vals[name] = val
                    data.append(f"{name}: {self._fmt_ohms(val)}")
                    if val <= self.RESIST_GATE_OHMS:
                        ok_count += 1
                except:
                    pass
        except:
            pass
        if data:
            self.log_signal.emit("📡 Resistances: " + "  ".join(data))
        self.resistances_signal.emit(data)

        # ── Notify GUI that user can now press Calibrate ───────────────────────
        if self._calibration_started:
            return
        elapsed = time.time() - self._resist_connect_time
        can_calibrate = (ok_count >= self.MIN_CHANNELS_READY)
        timed_out     = (elapsed >= self.CALIB_FALLBACK_SECS and self.calibrator is not None)
        if (can_calibrate or timed_out) and not getattr(self, '_ready_emitted', False):
            self._ready_emitted = True
            if timed_out and not can_calibrate:
                self.log_signal.emit(
                    f"⚠️  Resistance timeout ({self.CALIB_FALLBACK_SECS}s) — "
                    f"only {ok_count} channel(s) in range. Press Calibrate to continue."
                )
            else:
                self.log_signal.emit(
                    f"✅ {ok_count} electrode(s) ≤ {self.RESIST_GATE_OHMS//1000} kΩ "
                    f"— press Calibrate when ready."
                )
            self.ready_to_calibrate_signal.emit()

    def _on_calib_done(self, cal, data):
        self.log_signal.emit("✅ Calibration complete.")
        self._is_calibrated = True
        self.calibrated_signal.emit(); self.stage_signal.emit(STAGE_EEG)

    def _on_connection(self, device, status):
        # Map status to readable string
        st_map = {
            Device_Connection_Status.Device_ConnectionState_Connected: "Connected",
            Device_Connection_Status.Device_ConnectionState_Disconnected: "Disconnected",
            Device_Connection_Status.Device_ConnectionState_UnsupportedConnection: "Unsupported",
        }
        status_name = st_map.get(status, f"Status_{status}")
        self.log_signal.emit(f"📡 Connection status: {status_name}")

        if status == Device_Connection_Status.Device_ConnectionState_Connected:
            self._connected = True   # unblocks Phase 2 polling loop in connect_device()
            sn = "Unknown"
            try:
                if self.device:
                    sn = self.device.get_info().get_serial()
            except: pass
            self.connected_signal.emit(f"Connected [{sn}]")
            self.log_signal.emit(f"✅ Device Connected: {sn}")
            
            # Read actual channel names from device firmware ONLY after successful connect
            try:
                ch_names_obj = self.device.get_channel_names()
                names = [ch_names_obj.get_name_by_index(i) for i in range(len(ch_names_obj))]
                if names:
                    self.log_signal.emit(f"📡 Device channels: {names}")
                    self.channel_names_signal.emit(names)
            except Exception as ex:
                self.log_signal.emit(f"[WARN] Channel name read failed: {ex} — using default layout.")
                self.channel_names_signal.emit(["T3", "T4", "O1", "O2"])

            self.stage_signal.emit(STAGE_RESISTANCE)
            self.log_signal.emit(
                f"⚡ Checking resistances… "
                f"(need ≥{self.MIN_CHANNELS_READY} channels ≤ "
                f"{self.RESIST_GATE_OHMS//1000} kΩ, "
                f"or wait {self.CALIB_FALLBACK_SECS}s fallback)"
            )
            # Prepare calibrator but DON'T start yet — wait for resistance gate
            self.calibrator = Calibrator(self.device, self.capsuleLib.get_lib())
            self.calibrator.set_on_calibration_finished(self._on_calib_done)
            self._calibration_started = False
            self._is_calibrated = False
            self._ready_emitted = False
            self._resist_connect_time = time.time()
            self.device.start()   # begin streaming (resistance callbacks will now fire)

    def _on_device_list(self, locator, info_list, fail_reason):
        # fail_reason: 0=OK, 1=BluetoothDisabled, 2=Unknown
        if fail_reason == 1:
            self.log_signal.emit("❌ Bluetooth is DISABLED (Conflict detected).")
            self.log_signal.emit("💡 Tip: If using both ASUS and BARROT adapters, disable the one you aren't using in Device Manager.")
        elif fail_reason == 2:
            self.log_signal.emit("⚠️ Discovery error (Unknown). Try replugging your dongle.")

        if not info_list:
            if not self._found and not getattr(self, '_scan_tick', False):
                self._scan_tick = True
                self.log_signal.emit("... scanning ...")
            return

        if self._found: return
        self._found = True  # block further discovery callbacks
        info = info_list[0]
        try:
            sn = info.get_serial()
            name = info.get_name()
            self.log_signal.emit(f"🔍 Found: {name} SN:{sn}")
            
            # Instantiate device carefully
            lib_ptr = self.capsuleLib.get_lib()
            self.device = Device(locator, sn, lib_ptr)
            
            # Setup callbacks before connect
            self.device.set_on_connection_status_changed(self._on_connection)
            self.device.set_on_resistances(self._on_resistances)
            self.device.set_on_eeg(self._on_eeg)
            self.device.set_on_psd(self._on_psd)
            
            self.log_signal.emit(f"🔌 Initiating connection to {sn}...")
            self.device.connect(bipolarChannels=False)
        except Exception as ex:
            self.log_signal.emit(f"❌ discovery error: {ex}")
            self._found = False

    def connect_device(self):
        with self._conn_lock:
            self._found = False
            self._connected = False
            try:
                self.log_signal.emit("🔍 Scanning for Capsule device…")
                self.capsuleLib = Capsule(self.dll_path)
                self.device_locator = DeviceLocator('Logs', self.capsuleLib.get_lib())
                self.device_locator.set_on_devices_list(self._on_device_list)
                # Increase timeout to 15s to allow for adapter initialization
                self.device_locator.request_devices(DeviceType.Any, 15)

                # Continuously pump the SDK event loop for the entire session.
                # ALL callbacks (discovery, connection, resistance, calibration,
                # EEG and PSD) are delivered through this same mechanism.
                # The thread stays alive until stop() sets _running = False.
                while self._running:
                    try:
                        self.device_locator.update()
                    except Exception:
                        pass
                    if getattr(self, '_pending_calibration', False):
                        self._pending_calibration = False
                        def _do_calib():
                            try:
                                import ctypes
                                from api.Error import Error, Error_Code

                                lib = self.capsuleLib.get_lib()

                                # 1. Fix the `clCDevice_Stop` crash by explicitly setting the correct argtypes!
                                lib.clCDevice_Stop.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.POINTER(Error)]
                                err = Error()
                                lib.clCDevice_Stop(self.device._pointer, ctypes.byref(err))

                                # 2. Fix the Bluetooth bandwidth overload by setting the C++ Resistance callback to NULL!
                                null_ptr = ctypes.cast(None, ctypes.CFUNCTYPE(None, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)))
                                lib.clCDevice_SetOnResistanceUpdateEvent(self.device._pointer, null_ptr)
                                # (Feed it a dummy to python so it doesn't crash if an old packet arrives)
                                def dummy_res(dev, data): pass
                                self.device.set_on_resistances(dummy_res)

                                # 3. Start safely in clean Signal-Only mode and Calibrate
                                self.device.start()
                                self.calibrator.calibrate_quick()
                            except Exception as ex:
                                self.log_signal.emit(f"❌ calibrate_quick failed: {ex}")
                        threading.Thread(target=_do_calib, daemon=True).start()

                    # Log once when discovery completes
                    if self._found and not getattr(self, '_disc_logged', False):
                        self._disc_logged = True
                        self.log_signal.emit("📡 Discovery loop finished.")
                        self.stage_signal.emit(STAGE_DETECTING)
                    time.sleep(0.05)

            except Exception as e:
                if self._running:
                    self.log_signal.emit(f"❌ {e}"); print(e)

    def stop(self):
        self._running = False
        try:
            if self.device:
                self.device.stop()
                self.device.disconnect()
        except Exception as e:
            print(f"[Worker] Stop error: {e}")

    def run_thread(self):
        threading.Thread(target=self.connect_device, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet
# ─────────────────────────────────────────────────────────────────────────────
DARK="#030712"; CARD="#0F172A"; BORDER="#1E293B"
TEXT="#F8FAFC"; DIM="#94A3B8"; ACC="#38BDF8"; ACC2="#818CF8"
GRN="#22C55E"; ORG="#F59E0B"; RED="#EF4444"

CSS = f"""
QMainWindow, QWidget {{ background:{DARK}; color:{TEXT}; }}
QLabel {{ color:{TEXT}; background:transparent; }}
QScrollArea {{ border:none; background:transparent; }}
QTextEdit {{
    background:#020617; color:{DIM};
    font-family:Consolas,monospace; font-size:11px;
    border:1px solid {BORDER}; border-radius:6px; padding:5px;
}}
QListWidget {{
    background:#020617; color:{TEXT};
    border:1px solid {BORDER}; border-radius:6px; padding:4px; outline:0;
}}
QListWidget::item {{ border-radius:4px; padding:6px 10px; margin:2px 4px; }}
QListWidget::item:selected {{
    background:{ACC2};
    color:white;
}}
QPushButton {{
    background:#1E293B; color:{TEXT};
    border:1px solid {BORDER}; border-radius:6px;
    padding:8px 16px; font-size:11px; font-weight:bold;
}}
QPushButton:hover {{ background:{ACC2}; color:white; }}
QProgressBar {{
    background:#020617; border:1px solid {BORDER};
    border-radius:4px; text-align:center; color:white; font-size:9px;
}}
QProgressBar::chunk {{
    border-radius:3px;
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACC},stop:1 {ACC2});
}}
QFrame#dashPanel {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#dashPanel > QLabel {{
    color: #cbd5e1;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
}}
"""

def sec_lbl(txt, c=ACC):
    l = QLabel(txt); l.setFont(QFont("Segoe UI",9,QFont.Bold))
    l.setStyleSheet(f"color:{c};background:transparent;letter-spacing:1px;")
    return l

def hline():
    f=QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{BORDER};"); return f


# ─────────────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────────────
class AppCyclerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🧠 NEUROFLOW pipeline | 4-Channel Focus Launcher")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(CSS)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)

        # ── Title bar ──────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("🧠 NEUROFLOW pipeline | 4-Channel Focus Launcher")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color:#0ea5e9;")
        hdr.addWidget(title)
        hdr.addStretch()
        self.sim_badge = QLabel("")
        self.sim_badge.setFont(QFont("Segoe UI", 9, QFont.Bold))
        hdr.addWidget(self.sim_badge)
        self.status_lbl = QLabel("⬤  Headset: Simulation")
        self.status_lbl.setStyleSheet(f"color:{ORG};")
        hdr.addWidget(self.status_lbl)
        # ── Calibrate button ───────────────────────────────────────────────────
        self.calibrate_btn = QPushButton("🔧  Calibrate")
        self.calibrate_btn.setFixedHeight(28)
        self.calibrate_btn.setEnabled(False)
        self.calibrate_btn.setStyleSheet(
            f"background:#0f2933; color:#34d399; border:1px solid #34d399;"
            "border-radius:5px; padding:2px 12px; font-size:10px; font-weight:bold;"
        )
        self.calibrate_btn.clicked.connect(self._on_calibrate_btn)
        hdr.addWidget(self.calibrate_btn)
        # ── Connect button ─────────────────────────────────────────────────────
        self.connect_btn = QPushButton("🔌  Connect Device")
        self.connect_btn.setFixedHeight(28)
        self.connect_btn.setStyleSheet(
            f"background:#0f2942; color:{ACC}; border:1px solid {ACC};"
            "border-radius:5px; padding:2px 12px; font-size:10px; font-weight:bold;"
        )
        self.connect_btn.clicked.connect(self._on_connect_btn)
        hdr.addWidget(self.connect_btn)
        outer.addLayout(hdr)

        # ── Helper: make a titled dark panel ───────────────────────────────────
        def make_panel(title_str: str, content, stretch: int = 1) -> QFrame:
            from PyQt5.QtWidgets import QLayout  # type: ignore
            f = QFrame(); f.setObjectName("dashPanel")
            vl = QVBoxLayout(f)
            vl.setContentsMargins(12, 10, 12, 10)
            vl.setSpacing(6)
            lbl = QLabel(title_str)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
            lbl.setStyleSheet("color:#94a3b8; letter-spacing:1px;")
            vl.addWidget(lbl)
            if isinstance(content, QLayout):
                vl.addLayout(content, stretch)
            else:
                vl.addWidget(content, stretch)
            return f

        # ── Pipeline Status — full-width row above the data grid ──────────────
        self.pipeline = PipelineWidget()
        outer.addWidget(make_panel("PIPELINE STATUS", self.pipeline), 0)

        # ── 3-column grid ──────────────────────────────────────────────────────
        from PyQt5.QtWidgets import QGridLayout  # type: ignore
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 28)   # left  ~28%
        grid.setColumnStretch(1, 44)   # mid   ~44%
        grid.setColumnStretch(2, 28)   # right ~28%
        outer.addLayout(grid, 1)

        # ══════════════════════════════════════════════════════════════════════
        # LEFT COLUMN
        # ══════════════════════════════════════════════════════════════════════
        left_vl = QVBoxLayout(); left_vl.setSpacing(8)

        # Raw EEG Input + head model overlay
        eeg_frame = QFrame(); eeg_frame.setObjectName("dashPanel")
        eeg_fl = QVBoxLayout(eeg_frame)
        eeg_fl.setContentsMargins(12, 10, 12, 10); eeg_fl.setSpacing(6)

        eeg_hdr = QHBoxLayout()
        eeg_title = QLabel("EEG SIGNAL")
        eeg_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        eeg_title.setStyleSheet("color:#94a3b8; letter-spacing:1px;")
        eeg_hdr.addWidget(eeg_title)
        eeg_hdr.addStretch()
        sq_lbl = QLabel("Signal Quality")
        sq_lbl.setStyleSheet("color:#64748b; font-size:9px;")
        eeg_hdr.addWidget(sq_lbl)
        self.head_widget = SignalQualityBadge()
        eeg_hdr.addWidget(self.head_widget)
        eeg_fl.addLayout(eeg_hdr)

        self.eeg_canvas = EEGCanvas()
        self.eeg_canvas.set_channels(["T3", "T4", "O1", "O2"])  # Default layout; updated dynamically on connect
        self.eeg_canvas.setMinimumHeight(300)
        eeg_fl.addWidget(self.eeg_canvas, 1)

        self.electrode_strip = ElectrodeStripWidget()
        eeg_fl.addWidget(self.electrode_strip)

        left_vl.addWidget(eeg_frame, 1)
        grid.addLayout(left_vl, 0, 0)

        # ══════════════════════════════════════════════════════════════════════
        # MIDDLE COLUMN  — FOCUS INTERFACE
        # ══════════════════════════════════════════════════════════════════════
        mid_frame = QFrame(); mid_frame.setObjectName("dashPanel")
        mid_fl = QVBoxLayout(mid_frame)
        mid_fl.setContentsMargins(12, 10, 12, 10); mid_fl.setSpacing(8)

        mid_title = QLabel("FOCUS INTERFACE")
        mid_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        mid_title.setStyleSheet("color:#94a3b8; letter-spacing:1px;")
        mid_fl.addWidget(mid_title)

        ci_title = QLabel("CONCENTRATION INDEX (CI)")
        ci_title.setFont(QFont("Segoe UI", 9, QFont.Bold))
        ci_title.setStyleSheet("color:#cbd5e1;")
        ci_title.setAlignment(Qt.AlignCenter)
        mid_fl.addWidget(ci_title)

        self.ci_gauge = CIGauge()
        mid_fl.addWidget(self.ci_gauge, 1)

        # Dwell progress bar (thin, under gauge)
        self.dwell_bar = QProgressBar()
        self.dwell_bar.setRange(0, 100); self.dwell_bar.setValue(0)
        self.dwell_bar.setFixedHeight(5); self.dwell_bar.setTextVisible(False)
        self.dwell_bar.setStyleSheet("""
            QProgressBar { background:#0F172A; border:none; border-radius:2px; }
            QProgressBar::chunk { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #10b981,stop:1 #22c55e); border-radius:2px; }
        """)
        mid_fl.addWidget(self.dwell_bar)

        # App Selector
        app_sel_lbl = QLabel("APP SELECTOR")
        app_sel_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        app_sel_lbl.setStyleSheet("color:#cbd5e1;")
        app_sel_lbl.setAlignment(Qt.AlignCenter)
        mid_fl.addWidget(app_sel_lbl)

        app_row = QHBoxLayout()
        arr_l = QLabel("❮"); arr_l.setFont(QFont("Segoe UI", 16)); arr_l.setStyleSheet("color:#334155;")
        app_row.addWidget(arr_l)

        self.app_list = QListWidget()
        self.app_list.setFlow(QListWidget.LeftToRight)
        self.app_list.setSpacing(12)
        self.app_list.setFixedHeight(120)
        self.app_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.app_list.setStyleSheet("""
            QListWidget { background:transparent; border:none; }
            QListWidget::item {
                background:#0F172A; border:1px solid #1e293b;
                border-radius:10px; padding:8px; min-width:80px;
                color:#94a3b8; text-align:center;
            }
            QListWidget::item:selected {
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #064e3b,stop:1 #022c22);
                border:2px solid #10b981; color:#f0fdf4;
            }
        """)
        for i, a in enumerate(APPS):
            item = QListWidgetItem(f"\n {a['icon']} \n\n{a['name']}")
            item.setTextAlignment(Qt.AlignCenter)
            self.app_list.addItem(item)
        self.app_list.setCurrentRow(0)
        app_row.addWidget(self.app_list, 1)

        arr_r = QLabel("❯"); arr_r.setFont(QFont("Segoe UI", 16)); arr_r.setStyleSheet("color:#334155;")
        app_row.addWidget(arr_r)
        mid_fl.addLayout(app_row)

        self.hint_lbl = QLabel("🧠 Maintain focus to launch: Google Chrome")
        self.hint_lbl.setFont(QFont("Segoe UI", 9))
        self.hint_lbl.setStyleSheet("color:#38bdf8;")
        self.hint_lbl.setAlignment(Qt.AlignCenter)
        mid_fl.addWidget(self.hint_lbl)

        launch_row = QHBoxLayout()
        self.manual_btn = QPushButton("▶  Launch Manually")
        self.manual_btn.setEnabled(False)
        self.manual_btn.clicked.connect(self.launch_selected_app)
        launch_row.addStretch()
        launch_row.addWidget(self.manual_btn)
        launch_row.addStretch()
        mid_fl.addLayout(launch_row)

        self.focus_alert = QLabel("")
        self.focus_alert.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.focus_alert.setAlignment(Qt.AlignCenter)
        self.focus_alert.setFixedHeight(26)
        self.focus_alert.setStyleSheet("color:transparent; background:transparent; border-radius:4px;")
        mid_fl.addWidget(self.focus_alert)

        grid.addWidget(mid_frame, 0, 1)

        # ── Calibration Overlay (added over center area) ──────────────────────
        self.cal_overlay = CalibrationOverlay(root)
        self.cal_overlay.setGeometry(root.rect())

        # ══════════════════════════════════════════════════════════════════════
        # RIGHT COLUMN — Spectral Analysis + Heatmap + System Log
        # ══════════════════════════════════════════════════════════════════════
        right_vl = QVBoxLayout(); right_vl.setSpacing(8)

        # Spectral Analysis — 4 circular gauges (2×2)
        spec_frame = QFrame(); spec_frame.setObjectName("dashPanel")
        spec_fl = QVBoxLayout(spec_frame)
        spec_fl.setContentsMargins(12, 10, 12, 10); spec_fl.setSpacing(6)
        spec_hdr = QLabel("SPECTRAL ANALYSIS")
        spec_hdr.setFont(QFont("Segoe UI", 9, QFont.Bold))
        spec_hdr.setStyleSheet("color:#94a3b8; letter-spacing:1px;")
        spec_fl.addWidget(spec_hdr)
        bp_lbl = QLabel("BAND POWER RELATIVE %")
        bp_lbl.setFont(QFont("Segoe UI", 8))
        bp_lbl.setStyleSheet("color:#64748b;")
        bp_lbl.setAlignment(Qt.AlignCenter)
        spec_fl.addWidget(bp_lbl)

        g_row1 = QHBoxLayout()
        self.cg_delta = CircularGauge("DELTA", "#0ea5e9")
        self.cg_theta = CircularGauge("THETA", "#d946ef")
        g_row1.addWidget(self.cg_delta); g_row1.addWidget(self.cg_theta)
        g_row2 = QHBoxLayout()
        self.cg_alpha = CircularGauge("ALPHA", "#10b981")
        self.cg_beta  = CircularGauge("BETA",  "#f59e0b")
        g_row2.addWidget(self.cg_alpha); g_row2.addWidget(self.cg_beta)
        spec_fl.addLayout(g_row1, 1)
        spec_fl.addLayout(g_row2, 1)
        right_vl.addWidget(spec_frame, 3)

        # System Log  (no heatmap — full height)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        right_vl.addWidget(make_panel("SYSTEM LOG", self.log), 1)

        grid.addLayout(right_vl, 0, 2)

        # ── Internal state ────────────────────────────────────────────────────
        self.current_idx   = 0
        self.app_list.setCurrentRow(0)
        self._is_launching = False
        self._launch_lock  = threading.Lock()
        self._sim_active   = False
        self._real_connected = False
        self._is_calibrated = False

        # Cycle timer
        self.cycle_timer = QTimer(self); self.cycle_timer.timeout.connect(self.cycle_next)

        # Dwell bar refresh (10 Hz)
        self._dwell_timer = QTimer(self)
        self._dwell_timer.timeout.connect(self._refresh_dwell)
        self._dwell_timer.start(80)

        # EEG canvas repaint (20 Hz)
        self._eeg_repaint = QTimer(self)
        self._eeg_repaint.timeout.connect(self.eeg_canvas.update)
        self._eeg_repaint.start(50)

        # ── Simulation engine (shares same signal interface) ──────────────────
        self.sim = SimulationEngine()
        self._connect_data_signals(self.sim)

        # ── Real hardware worker (created lazily on button click) ─────────────
        self._worker: CapsuleWorker | None = None
        self._connecting = False   # guard against double-click

        # Start simulation immediately on open
        self._log("System ready — press \"Connect Device\" to use real EEG.")
        if not CAPSULE_AVAILABLE:
            self._log("⚠️  Capsule API not found — simulation-only mode.")
        self._start_sim()

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _connect_data_signals(self, src: QObject):
        src.log_signal.connect(self._log)
        src.stage_signal.connect(self._on_stage_changed)
        src.connected_signal.connect(self._on_connected)
        src.resistances_signal.connect(self._on_resistances)
        src.calibrated_signal.connect(self._on_calibrated)
        src.eeg_signal.connect(self._on_eeg)
        src.psd_signal.connect(self._on_psd)
        src.focus_trigger_signal.connect(self._on_focus_trigger)
        src.channel_names_signal.connect(self._on_channel_names)
        # Wire ready_to_calibrate_signal only if it exists (CapsuleWorker, not SimulationEngine)
        if hasattr(src, 'ready_to_calibrate_signal'):
            src.ready_to_calibrate_signal.connect(self._on_ready_to_calibrate)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _log(self, msg): self.log.append(msg)

    def _on_stage_changed(self, stage):
        self.pipeline.set_stage(stage)
        if stage == STAGE_CALIBRATING:
            self.cal_overlay.start()
        else:
            self.cal_overlay.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'cal_overlay'):
            self.cal_overlay.setGeometry(self.centralWidget().rect())

    def _on_connect_btn(self):
        """User clicked Connect/Disconnect toggle."""
        if self._connecting:
            return
        
        if self._real_connected:
            self._is_calibrated = False
            self.calibrate_btn.setEnabled(False)
            self._on_disconnect_clicked()
            return
            
        if not CAPSULE_AVAILABLE:
            self._log("❌ Capsule API not available — cannot connect real headband.")
            return

        self._connecting = True
        self._is_calibrated = False
        self.calibrate_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("⏳  Scanning…")
        self._log("🔍 Scanning for Capsule device (10 s timeout)…")
        # Create worker if not yet created
        if self._worker is None:
            _w = CapsuleWorker()
            self._worker = _w
            self._connect_data_signals(_w)
            _w.connected_signal.connect(self._on_real_connected)
        self._worker.run_thread()
        # Fallback: if still not connected after 20 s, re-enable button
        QTimer.singleShot(20000, self._connect_timeout)

    def _on_ready_to_calibrate(self):
        """Resistance check passed — enable the Calibrate button."""
        self.calibrate_btn.setEnabled(True)
        self._log("🟢 Resistance OK — press 🔧 Calibrate when ready.")

    def _on_calibrate_btn(self):
        """User clicked Calibrate — trigger calibration on the worker."""
        if self._worker is None or self._worker._calibration_started:
            return
        self.calibrate_btn.setEnabled(False)
        self._worker._calibration_started = True
        self._worker._pending_calibration = True
        self._worker.stage_signal.emit(STAGE_CALIBRATING)
        self._log("🔧 Calibration started by user.")

    def _on_disconnect_clicked(self):
        """Safely shut down the real device worker and revert to simulation."""
        self._log("🔌 Disconnecting device...")
        if self._worker:
            self._worker.stop()
            self._worker = None
        
        self._real_connected = False
        self._connecting = False
        
        # Reset button to Connect state
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("🔌  Connect Device")
        self.connect_btn.setStyleSheet(
            f"background:#0f2942; color:{ACC}; border:1px solid {ACC};"
            "border-radius:5px; padding:2px 12px; font-size:10px; font-weight:bold;"
        )
        
        self.status_lbl.setText("⬤  Headset: Disconnected")
        self.status_lbl.setStyleSheet(f"color:{RED};")
        self._log("🚫 Device disconnected. Returning to simulation.")
        self._start_sim()

    def _connect_timeout(self):
        if not self._real_connected:
            self._connecting = False
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("🔌  Connect Device")
            self._log("⚠️  No device found — still running in simulation mode.")

    def _on_real_connected(self, _):
        """Real device connected — stop simulation and reset canvas for real data."""
        self._real_connected = True
        self._connecting = False
        if self._sim_active:
            self.sim.stop(); self._sim_active = False
            self._log("🟢 Real device connected — simulation stopped.")
            self.sim_badge.setText("")
            self.sim_badge.setStyleSheet("color:transparent;background:transparent;")
        # Clear the SIMULATION watermark from the EEG canvas and reset for real data
        if hasattr(self, 'eeg_canvas'):
            self.eeg_canvas._sim_badge = False
            self.eeg_canvas._has_data  = False   # fresh start — wait for real signal
            self.eeg_canvas.update()
        self.connect_btn.setText("🔌  Disconnect")
        self.connect_btn.setEnabled(True)
        self.connect_btn.setStyleSheet(
            f"background:#450a0a; color:{RED}; border:1px solid {RED};"
            "border-radius:5px; padding:2px 12px; font-size:10px; font-weight:bold;"
        )

    def _on_connected(self, msg):
        self.status_lbl.setText(f"⬤  Headset: {msg}")
        color = GRN if "Sim" not in msg else ORG
        self.status_lbl.setStyleSheet(f"color:{color};")

    def _on_channel_names(self, names: list):
        """Apply real channel names (from device firmware) to all display widgets."""
        if not names:
            return
        self._log(f"📡 Channel names confirmed: {names}")
        # Update EEG canvas channel labels
        if hasattr(self, 'eeg_canvas'):
            self.eeg_canvas.set_channels(names)
        # Update electrode strip
        if hasattr(self, 'electrode_strip'):
            # Only set headband/headphone mode based on name patterns
            is_headband = any(n in names for n in ["T3", "T4", "O1", "O2", "Fp1", "Fp2"])
            self.electrode_strip.set_mode(headband=is_headband)
            # Re-key the channel dict to the actual names
            self.electrode_strip._channels = names
            self.electrode_strip._status = {ch: "ok" for ch in names}
            self.electrode_strip._ohms   = {ch: 0 for ch in names}
            self.electrode_strip.update()
        # Update signal quality badge
        if hasattr(self, 'head_widget'):
            self.head_widget._CH_NAMES = names
            self.head_widget._status = {ch: "idle" for ch in names}
            self.head_widget.update()

    def _on_resistances(self, lst):
        """Update electrode strip dots. Correctly converts kΩ/MΩ/Ω suffixes to ohms."""
        import re as _re
        if lst:
            for entry in lst:
                # Match e.g. "T3: 750.0 kΩ"  or  "O1: 5.00 MΩ"  or  "T4: 480 Ω"
                m = _re.match(r'([A-Za-z0-9]+)[:\s]+([\d.]+)\s*(MΩ|kΩ|Ω)?', entry)
                if m:
                    ch  = m.group(1)
                    val = float(m.group(2))
                    unit = m.group(3) or 'Ω'
                    if unit == 'MΩ':
                        ohms = val * 1_000_000
                    elif unit == 'kΩ':
                        ohms = val * 1_000
                    else:
                        ohms = val
                    if hasattr(self, 'electrode_strip'):
                        self.electrode_strip.set_resistance(ch, ohms)
                    if hasattr(self, 'head_widget'):
                        self.head_widget.set_resistance(ch, ohms)

    def _on_calibrated(self):
        self._is_calibrated = True
        self.manual_btn.setEnabled(True)
        self._log(">>> System Ready. App cycling started — sustain focus to launch! <<<")
        self.cycle_timer.start(5000)
        self.pipeline.set_stage(STAGE_SPECTRAL)

    def _on_eeg(self, ch: int, samples: list):
        """Push data into the EEGCanvas buffer. Scale + repaint handled by canvas timer."""
        self.eeg_canvas.push_samples(ch, samples)

    def _on_psd(self, bp: dict, ci: float):
        if hasattr(self, 'cg_delta'):
            self.cg_delta.set_value(bp.get('Delta', 0.0))
            self.cg_theta.set_value(bp.get('Theta', 0.0))
            self.cg_alpha.set_value(bp.get('Alpha', 0.0))
            self.cg_beta.set_value(bp.get('Beta', 0.0))
        self.ci_gauge.set_ci(ci)
        self.pipeline.set_stage(STAGE_FOCUS)

    def _refresh_dwell(self):
        src = self.sim if self._sim_active else (self._worker or self.sim)
        in_f  = getattr(src, '_in_focus', False)
        t_s   = getattr(src, '_focus_start', 0.0)
        if in_f and t_s > 0:
            pct = int(min((time.time()-t_s)/FOCUS_DWELL_SECONDS*100, 100))
        else:
            pct = 0
        self.dwell_bar.setValue(pct)

    def _on_focus_trigger(self):
        self.cycle_timer.stop()
        self._flash_focus()
        self.launch_selected_app()
        QTimer.singleShot(int(TRIGGER_COOLDOWN*1000), self.cycle_timer.start)

    def cycle_next(self):
        self.current_idx = (self.current_idx+1) % len(APPS)
        self.app_list.setCurrentRow(self.current_idx)
        a = APPS[self.current_idx]
        self.hint_lbl.setText(f"🧠  Focus to launch:  {a['icon']} {a['name']}")

    def launch_selected_app(self):
        if not self._is_calibrated:
            self._log("[WARNING] Apps cannot be launched before calibration.")
            return

        with self._launch_lock:
            if self._is_launching:
                self._log("[BLOCKED] Launch in progress."); return
            self._is_launching = True
        idx = self.app_list.currentRow()
        if not (0 <= idx < len(APPS)):
            self._is_launching = False; return
        a = APPS[idx]
        self._log(f">>> Launching: {a['icon']} {a['name']} <<<")
        def _run():
            launch_app(a); self._is_launching = False
        threading.Thread(target=_run, daemon=True).start()

    def _flash_focus(self):
        self.focus_alert.setText("🧠  FOCUS CONFIRMED — Launching App!  🚀")
        self.focus_alert.setStyleSheet(
            f"color:white;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {GRN},stop:1 {ACC2});border-radius:5px;")
        QTimer.singleShot(1800, self._clear_flash)

    def _clear_flash(self):
        self.focus_alert.setText("")
        self.focus_alert.setStyleSheet(
            "color:transparent;background:transparent;border-radius:5px;")

    # ── Simulation management ─────────────────────────────────────────────────
    def _start_sim(self):
        if self._sim_active: return
        self._sim_active = True
        self.eeg_canvas._sim_badge = True
        self.sim.start()
        self.sim_badge.setText(
            "⚠️  SIMULATION MODE — press \"Connect Device\" to use real EEG")
        self.sim_badge.setStyleSheet(
            f"color:{ORG}; background:#1a0f00; border:1px solid {ORG};"
            "border-radius:4px; padding:2px 8px;")

    def closeEvent(self, event):
        if hasattr(self, '_worker') and self._worker:
            self._worker.stop()
        if hasattr(self, 'sim') and self.sim:
            self.sim.stop()
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = AppCyclerGUI()
    win.showMaximized()
    sys.exit(app.exec_())
