"""
BCI Music DJ — Beat Pad with head-aim (gyro) + focus-tap (EEG attention dwell).

4×4 pad grid: drums, percussion, synth notes.
Gyro controls pad cursor. Focus dwell ≥ 70 for 0.4 s triggers the sound.
Procedural audio synthesis — no external files needed.
Modern DJ-controller aesthetic (glassmorphism).
"""
from __future__ import annotations

import logging
import math
import os
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QRectF
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QLinearGradient, QRadialGradient, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy,
)

log = logging.getLogger(__name__)

# ── Audio backend ─────────────────────────────────────────────────────
try:
    from PySide6.QtMultimedia import QSoundEffect
    _AUDIO_OK = "qt"
except ImportError:
    _AUDIO_OK = None

if not _AUDIO_OK and sys.platform == "win32":
    try:
        import winsound
        _AUDIO_OK = "winsound"
    except ImportError:
        pass

if not _AUDIO_OK:
    log.warning("No audio backend available — DJ pads will be silent")

# ── Tuning ────────────────────────────────────────────────────────────
_COLS, _ROWS = 4, 4
_DEAD_ZONE   = 2.0        # deg/s
_SENSITIVITY = 3.0         # cells/s per deg/s
_TICK_MS     = 16          # ~60 FPS
_FOCUS_THR   = 70          # attention threshold
_DWELL_SEC   = 0.40        # fast trigger for music
_COOLDOWN    = 0.30        # between triggers
_FLASH_SEC   = 0.25        # visual flash duration
_SR          = 44100       # sample rate for WAV

# ── Colours ───────────────────────────────────────────────────────────
_BG_TOP  = QColor(10, 14, 39)
_BG_BOT  = QColor(28, 10, 62)
_ROW = [
    (QColor(255, 145, 0),   QColor(255, 183, 77)),   # amber — drums
    (QColor(245, 0, 87),    QColor(255, 64, 129)),    # pink — perc
    (QColor(0, 229, 255),   QColor(24, 255, 255)),    # cyan — synth lo
    (QColor(170, 0, 255),   QColor(213, 0, 249)),     # violet — synth hi
]
_PAD_IDLE   = QColor(255, 255, 255, 14)
_CURSOR_CLR = QColor(255, 255, 255, 210)
_TXT        = QColor(255, 255, 255, 230)
_TXT_DIM    = QColor(255, 255, 255, 90)
_REC_RED    = QColor(255, 23, 68)
_PLAY_GREEN = QColor(0, 230, 118)

# ── Pad definitions (label, gen_key, param, duration) ─────────────────
_PADS = [
    ("KICK",  "kick",  0,      0.30),
    ("SNARE", "snare", 0,      0.20),
    ("HAT",   "hihat", 0,      0.10),
    ("CLAP",  "clap",  0,      0.25),
    ("TOM ↓", "tom",   80,     0.40),
    ("TOM →", "tom",   120,    0.35),
    ("TOM ↑", "tom",   180,    0.30),
    ("CRASH", "crash", 0,      0.55),
    ("C",     "note",  261.63, 0.45),
    ("D",     "note",  293.66, 0.45),
    ("E",     "note",  329.63, 0.45),
    ("F",     "note",  349.23, 0.45),
    ("G",     "note",  392.00, 0.45),
    ("A",     "note",  440.00, 0.45),
    ("B",     "note",  493.88, 0.45),
    ("C5",    "note",  523.25, 0.45),
]

# =====================================================================
#  WAV synthesis helpers
# =====================================================================

def _noise(seed: int) -> float:
    x = ((seed * 1103515245 + 12345) & 0x7FFFFFFF)
    return x / 0x3FFFFFFF - 1.0


def _wav_bytes(duration: float, gen) -> bytes:
    n = int(_SR * duration)
    pcm = bytearray(n * 2)
    for i in range(n):
        t = i / _SR
        v = max(-1.0, min(1.0, gen(t, i, n)))
        struct.pack_into("<h", pcm, i * 2, int(v * 32000))
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, _SR, _SR * 2, 2, 16,
        b"data", len(pcm),
    )
    return hdr + bytes(pcm)


def _gen_kick(t, i, n):
    f = 150 * math.exp(-t * 15) + 40
    return math.exp(-t * 8) * math.sin(2 * math.pi * f * t)

def _gen_snare(t, i, n):
    ns = _noise(i * 3 + 7)
    tone = math.sin(2 * math.pi * 200 * t)
    return math.exp(-t * 14) * (0.6 * ns + 0.4 * tone)

def _gen_hihat(t, i, n):
    return math.exp(-t * 40) * _noise(i * 7 + 3) * 0.7

def _gen_clap(t, i, n):
    ns = _noise(i * 13 + 11)
    burst = sum(math.exp(-((t - 0.01 * k) ** 2) * 20000) for k in range(4))
    return ns * burst * 0.25

def _gen_tom(freq):
    def g(t, i, n):
        f = freq * math.exp(-t * 5) + freq * 0.5
        return math.exp(-t * 6) * math.sin(2 * math.pi * f * t)
    return g

def _gen_crash(t, i, n):
    ns = _noise(i * 17 + 11)
    metal = sum(math.sin(2 * math.pi * f * t) for f in (800, 1200, 2300, 3100)) / 4
    return math.exp(-t * 3) * (0.5 * ns + 0.5 * metal) * 0.45

def _gen_note(freq):
    def g(t, i, n):
        env = max(0.0, 1.0 - t / (n / _SR))
        v  = math.sin(2 * math.pi * freq * t)
        v += 0.4 * math.sin(2 * math.pi * freq * 2 * t)
        v += 0.15 * math.sin(2 * math.pi * freq * 3 * t)
        return env * v * 0.35
    return g

_GEN_MAP = {
    "kick": lambda _p: _gen_kick,
    "snare": lambda _p: _gen_snare,
    "hihat": lambda _p: _gen_hihat,
    "clap": lambda _p: _gen_clap,
    "tom": lambda p: _gen_tom(p),
    "crash": lambda _p: _gen_crash,
    "note": lambda p: _gen_note(p),
}

# =====================================================================
#  Canvas — paints the 4×4 pad grid
# =====================================================================

class _DJCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.cursor_col: float = 0.0
        self.cursor_row: float = 0.0
        self.dwell_frac: float = 0.0          # 0‥1
        self.flash_times: dict[int, float] = {}
        self._label_font = QFont("Segoe UI", 11, QFont.Bold)
        self._sub_font   = QFont("Segoe UI", 8)

    # ── paint ─────────────────────────────────────────────────────────
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        now = time.monotonic()

        # background gradient
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, _BG_TOP)
        bg.setColorAt(1, _BG_BOT)
        p.fillRect(0, 0, w, h, bg)

        pad_w = w / _COLS
        pad_h = h / _ROWS
        margin = 6
        radius = 14

        cur_c = int(self.cursor_col)
        cur_r = int(self.cursor_row)

        for idx, (label, *_rest) in enumerate(_PADS):
            c, r = idx % _COLS, idx // _COLS
            x0 = c * pad_w + margin
            y0 = r * pad_h + margin
            pw = pad_w - 2 * margin
            ph = pad_h - 2 * margin
            rect = QRectF(x0, y0, pw, ph)

            row_main, row_light = _ROW[r]
            is_cursor = (c == cur_c and r == cur_r)

            # flash?
            flash_t = self.flash_times.get(idx)
            flashing = flash_t is not None and (now - flash_t) < _FLASH_SEC
            flash_frac = 0.0
            if flashing:
                flash_frac = 1.0 - (now - flash_t) / _FLASH_SEC

            # pad fill
            if flashing:
                fill = QColor(row_light)
                fill.setAlphaF(0.35 + 0.55 * flash_frac)
            elif is_cursor:
                fill = QColor(row_main)
                fill.setAlphaF(0.22)
            else:
                fill = _PAD_IDLE

            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            p.fillPath(path, fill)

            # border
            if is_cursor:
                pen = QPen(_CURSOR_CLR, 2.5)
            elif flashing:
                glow = QColor(row_light)
                glow.setAlphaF(0.6 * flash_frac)
                pen = QPen(glow, 2.0)
            else:
                pen = QPen(QColor(255, 255, 255, 18), 1.0)
            p.setPen(pen)
            p.drawRoundedRect(rect, radius, radius)

            # label
            p.setPen(_TXT if (is_cursor or flashing) else _TXT_DIM)
            p.setFont(self._label_font)
            p.drawText(rect, Qt.AlignCenter, label)

            # dwell ring on cursor pad
            if is_cursor and self.dwell_frac > 0:
                ring_r = min(pw, ph) * 0.42
                cx = x0 + pw / 2
                cy = y0 + ph / 2
                arc_rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
                arc_pen = QPen(row_light, 3.0)
                arc_pen.setCapStyle(Qt.RoundCap)
                p.setPen(arc_pen)
                span = int(self.dwell_frac * 360 * 16)
                p.drawArc(arc_rect, 90 * 16, -span)

        p.end()

# =====================================================================
#  Main window
# =====================================================================

class BciMusicDjWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("BCI Music DJ")
        self.resize(560, 640)
        self.setMinimumSize(400, 480)
        self.setStyleSheet("background: #0a0e27;")

        # ── central widget ────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        # title
        title = QLabel("BCI MUSIC DJ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: #fff; font-size: 18px; font-weight: 700;"
            " letter-spacing: 4px; background: transparent;"
        )
        root.addWidget(title)

        # canvas
        self._canvas = _DJCanvas()
        root.addWidget(self._canvas, stretch=1)

        # ── controls bar ──────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self._rec_btn = self._make_btn("● REC", _REC_RED, checkable=True)
        self._rec_btn.toggled.connect(self._on_rec_toggle)
        bar.addWidget(self._rec_btn)

        self._play_btn = self._make_btn("▶ LOOP", _PLAY_GREEN, checkable=True)
        self._play_btn.toggled.connect(self._on_play_toggle)
        bar.addWidget(self._play_btn)

        self._clear_btn = self._make_btn("✕ CLEAR", QColor(180, 180, 180))
        self._clear_btn.clicked.connect(self._on_clear)
        bar.addWidget(self._clear_btn)

        bar.addStretch()

        self._focus_lbl = QLabel("Focus: —")
        self._focus_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.6); font-size: 12px; background: transparent;"
        )
        bar.addWidget(self._focus_lbl)

        root.addLayout(bar)

        # ── state ─────────────────────────────────────────────────────
        self._gyro_vx = 0.0
        self._gyro_vy = 0.0
        self._attention = 0.0
        self._dwell_start: float | None = None
        self._last_trigger = 0.0

        # recording
        self._recording = False
        self._rec_start = 0.0
        self._rec_events: list[tuple[float, int]] = []
        self._looping = False

        # audio
        self._tmp_dir: str | None = None
        self._effects: list = []         # QSoundEffect objects (qt) or None
        self._wav_cache: list[bytes] = []  # raw WAV bytes for winsound fallback
        self._build_audio()

        # tick timer
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_btn(text, color: QColor, checkable=False):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setCheckable(checkable)
        cs = color.name()
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {cs};"
            f" border: 1px solid {cs}; border-radius: 8px;"
            f" padding: 5px 14px; font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {cs}; color: #0a0e27; }}"
            f"QPushButton:checked {{ background: {cs}; color: #0a0e27; }}"
        )
        return b

    # ── audio generation ──────────────────────────────────────────────

    def _build_audio(self):
        if not _AUDIO_OK:
            self._effects = [None] * len(_PADS)
            return
        # Generate WAV bytes for every pad
        wav_list: list[bytes] = []
        for idx, (label, gen_key, param, dur) in enumerate(_PADS):
            gen_fn = _GEN_MAP[gen_key](param)
            wav_list.append(_wav_bytes(dur, gen_fn))

        if _AUDIO_OK == "qt":
            self._tmp_dir = tempfile.mkdtemp(prefix="bci_dj_")
            for idx, wav in enumerate(wav_list):
                path = os.path.join(self._tmp_dir, f"pad_{idx}.wav")
                with open(path, "wb") as f:
                    f.write(wav)
                fx = QSoundEffect(self)
                fx.setSource(QUrl.fromLocalFile(path))
                fx.setVolume(0.85)
                self._effects.append(fx)
            log.info("BCI Music DJ: %d pads (Qt audio) in %s", len(_PADS), self._tmp_dir)
        else:  # winsound
            self._wav_cache = wav_list
            log.info("BCI Music DJ: %d pads (winsound fallback)", len(_PADS))

    def _play_sound(self, idx: int):
        if _AUDIO_OK == "qt":
            if 0 <= idx < len(self._effects) and self._effects[idx] is not None:
                self._effects[idx].play()
        elif _AUDIO_OK == "winsound" and 0 <= idx < len(self._wav_cache):
            wav = self._wav_cache[idx]
            threading.Thread(
                target=winsound.PlaySound,
                args=(wav, winsound.SND_MEMORY),
                daemon=True,
            ).start()

    # ── tick loop ─────────────────────────────────────────────────────

    def _tick(self):
        if not self.isVisible():
            return
        now = time.monotonic()
        dt = _TICK_MS / 1000.0

        # move cursor
        cx = self._canvas.cursor_col
        cy = self._canvas.cursor_row
        vx, vy = self._gyro_vx, self._gyro_vy
        if abs(vx) > _DEAD_ZONE:
            cx += (vx - math.copysign(_DEAD_ZONE, vx)) * _SENSITIVITY * dt
        if abs(vy) > _DEAD_ZONE:
            cy += (vy - math.copysign(_DEAD_ZONE, vy)) * _SENSITIVITY * dt
        self._canvas.cursor_col = max(0.0, min(_COLS - 1.0, cx))
        self._canvas.cursor_row = max(0.0, min(_ROWS - 1.0, cy))

        # dwell logic
        pad_idx = int(self._canvas.cursor_row) * _COLS + int(self._canvas.cursor_col)
        if self._attention >= _FOCUS_THR:
            if self._dwell_start is None:
                self._dwell_start = now
            elapsed = now - self._dwell_start
            self._canvas.dwell_frac = min(1.0, elapsed / _DWELL_SEC)
            if elapsed >= _DWELL_SEC and (now - self._last_trigger) >= _COOLDOWN:
                self._trigger_pad(pad_idx)
                self._dwell_start = None
                self._canvas.dwell_frac = 0.0
                self._last_trigger = now
        else:
            self._dwell_start = None
            self._canvas.dwell_frac = 0.0

        self._canvas.update()

    def _trigger_pad(self, idx: int):
        self._canvas.flash_times[idx] = time.monotonic()
        self._play_sound(idx)
        label = _PADS[idx][0] if idx < len(_PADS) else "?"
        log.info("DJ pad triggered: %s (#%d)", label, idx)

        if self._recording:
            self._rec_events.append((time.monotonic() - self._rec_start, idx))

    # ── recording / loop ──────────────────────────────────────────────

    def _on_rec_toggle(self, checked: bool):
        if checked:
            self._recording = True
            self._rec_events.clear()
            self._rec_start = time.monotonic()
            log.info("DJ REC started")
        else:
            self._recording = False
            log.info("DJ REC stopped — %d events", len(self._rec_events))

    def _on_play_toggle(self, checked: bool):
        if checked:
            if not self._rec_events:
                self._play_btn.setChecked(False)
                return
            self._looping = True
            self._start_loop_chain(0, self._loop_duration())
            log.info("DJ LOOP started")
        else:
            self._looping = False
            log.info("DJ LOOP stopped")

    def _on_clear(self):
        self._rec_events.clear()
        self._play_btn.setChecked(False)
        self._rec_btn.setChecked(False)
        self._looping = False
        self._recording = False

    def _loop_duration(self) -> float:
        if not self._rec_events:
            return 1.0
        return self._rec_events[-1][0] + 0.4

    def _start_loop_chain(self, idx: int, dur: float):
        if not self._looping:
            return
        if idx >= len(self._rec_events):
            remaining = max(0.05, dur - (self._rec_events[-1][0] if self._rec_events else 0))
            QTimer.singleShot(int(remaining * 1000),
                              lambda: self._start_loop_chain(0, dur))
            return
        t_evt, pad = self._rec_events[idx]
        self._trigger_pad(pad)
        if idx + 1 < len(self._rec_events):
            gap = max(0.01, self._rec_events[idx + 1][0] - t_evt)
            QTimer.singleShot(int(gap * 1000),
                              lambda i=idx + 1: self._start_loop_chain(i, dur))
        else:
            remaining = max(0.05, dur - t_evt)
            QTimer.singleShot(int(remaining * 1000),
                              lambda: self._start_loop_chain(0, dur))

    # ── public API (from signal_dispatcher) ───────────────────────────

    def on_mems(self, mems_timed_data):
        if not self.isVisible():
            return
        try:
            g = mems_timed_data.get_gyroscope(0)
            self._gyro_vx = g.z   # roll → horizontal
            self._gyro_vy = g.x   # pitch → vertical
        except Exception:
            pass

    def on_emotions(self, data):
        if not self.isVisible():
            return
        try:
            self._attention = data.get("attention", 0.0)
            self._focus_lbl.setText(f"Focus: {int(self._attention)}")
        except Exception:
            pass

    def shutdown(self):
        self._timer.stop()
        self._looping = False
        for fx in self._effects:
            if fx is not None:
                fx.stop()
        self._effects.clear()
        if self._tmp_dir:
            try:
                import shutil
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            except Exception:
                pass
        self.close()
