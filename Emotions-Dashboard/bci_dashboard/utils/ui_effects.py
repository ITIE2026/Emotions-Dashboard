"""
Shared UI effect helpers: glow shadows, gradient buttons, value animations.
"""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton
from PySide6.QtGui import QColor


def apply_card_glow(widget, color: str = "#69F0AE", radius: int = 20, opacity: float = 0.5):
    """Attach a coloured drop-shadow glow to *widget*."""
    shadow = QGraphicsDropShadowEffect(widget)
    qc = QColor(color)
    qc.setAlphaF(opacity)
    shadow.setColor(qc)
    shadow.setBlurRadius(radius)
    shadow.setOffset(0, 0)
    widget.setGraphicsEffect(shadow)
    return shadow


def remove_glow(widget):
    """Remove any graphics effect from *widget*."""
    widget.setGraphicsEffect(None)


def animate_property(widget, prop: bytes, start, end, duration: int = 300):
    """Animate a QProperty on *widget* from *start* to *end*."""
    anim = QPropertyAnimation(widget, prop, widget)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    return anim


def gradient_button_style(
    color1: str = "#69F0AE",
    color2: str = "#4DD0E1",
    text_color: str = "#0A0A0A",
    border_radius: int = 10,
    padding: str = "10px 20px",
    font_size: int = 14,
) -> str:
    """Return a stylesheet string for a gradient primary button."""
    return (
        f"QPushButton {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {color1}, stop:1 {color2});"
        f"  color: {text_color}; font-weight: bold; border: none;"
        f"  border-radius: {border_radius}px; padding: {padding};"
        f"  font-size: {font_size}px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 {color2}, stop:1 {color1});"
        f"}}"
        f"QPushButton:pressed {{"
        f"  opacity: 0.85;"
        f"}}"
        f"QPushButton:disabled {{"
        f"  background: #2A2E48; color: #555;"
        f"}}"
    )


def danger_button_style(accent: str = "#EF5350", border_radius: int = 10) -> str:
    return (
        f"QPushButton {{"
        f"  background: transparent; color: {accent};"
        f"  border: 1px solid {accent}; border-radius: {border_radius}px;"
        f"  padding: 8px 16px; font-size: 13px; font-weight: bold;"
        f"}}"
        f"QPushButton:hover {{ background: rgba(239,83,80,0.12); }}"
        f"QPushButton:disabled {{ color: #555; border-color: #333; }}"
    )


def ghost_button_style(
    accent: str = "#69F0AE",
    bg: str = "#1B1F36",
    border_radius: int = 8,
) -> str:
    return (
        f"QPushButton {{"
        f"  background: {bg}; color: {accent};"
        f"  border: 1px solid {accent}; border-radius: {border_radius}px;"
        f"  padding: 6px 14px; font-size: 12px; font-weight: bold;"
        f"}}"
        f"QPushButton:hover {{ background: rgba(105,240,174,0.1); }}"
    )
