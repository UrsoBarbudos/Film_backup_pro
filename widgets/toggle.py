"""
Кастомный переключатель (toggle button) на базе QCheckBox.
Плоский дизайн, настраиваемые цвета, плавная анимация кружка по треку.
"""

from PySide6.QtWidgets import QCheckBox, QStyle, QStyleOptionButton
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPaintEvent

TRACK_WIDTH = 48
TRACK_HEIGHT = 24
TRACK_MARGIN = 2
ANIMATION_DURATION_MS = 250


class PyToggle(QCheckBox):
    """
    Toggle-переключатель: трек (закруглённый прямоугольник) и кружок,
    анимированно двигающийся слева (выкл) / справа (вкл).
    Наследуется от QCheckBox — совместим с isChecked(), setChecked(), toggled.
    """

    def __init__(
        self,
        text: str = "",
        *,
        bg_color: str = "#555555",
        circle_color: str = "#ffffff",
        active_color: str = "#4A90E2",
        animation_curve: QEasingCurve.Type = QEasingCurve.Type.InOutCubic,
        parent=None,
    ):
        super().__init__(text, parent)
        self._bg_color = QColor(bg_color)
        self._circle_color = QColor(circle_color)
        self._active_color = QColor(active_color)
        self._animation_curve_type = animation_curve
        self._circle_position = 0.0
        self._animation = QPropertyAnimation(self, b"circlePosition")
        self._animation.setDuration(ANIMATION_DURATION_MS)
        self._animation.setEasingCurve(QEasingCurve(animation_curve))
        self.stateChanged.connect(self._on_state_changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_position_to_state()

    def _get_circle_position(self) -> float:
        return self._circle_position

    def _set_circle_position(self, value: float) -> None:
        self._circle_position = max(0.0, min(1.0, value))
        self.update()

    circlePosition = Property(float, _get_circle_position, _set_circle_position)

    def _sync_position_to_state(self) -> None:
        self._circle_position = 1.0 if self.isChecked() else 0.0
        self.update()

    def _on_state_changed(self) -> None:
        self._animation.stop()
        target = 1.0 if self.isChecked() else 0.0
        if not self.isVisible():
            self._circle_position = target
            self.update()
            return
        self._animation.setStartValue(self._circle_position)
        self._animation.setEndValue(target)
        self._animation.start()

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def _track_rect(self) -> QRect:
        r = self.rect()
        x = r.right() - TRACK_WIDTH - 4
        y = (r.height() - TRACK_HEIGHT) // 2
        return QRect(x, y, TRACK_WIDTH, TRACK_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        full = self.rect()
        track_rect = self._track_rect()
        label_rect = full.adjusted(0, 0, -TRACK_WIDTH - 8, 0)

        # Рисуем трек (закруглённый прямоугольник)
        radius = TRACK_HEIGHT // 2
        if self.isChecked():
            track_color = self._active_color
        else:
            track_color = self._bg_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        # Кружок
        margin = TRACK_MARGIN
        circle_diam = TRACK_HEIGHT - 2 * margin
        track_inner_width = TRACK_WIDTH - 2 * margin - circle_diam
        circle_x = track_rect.x() + margin + self._circle_position * track_inner_width
        circle_y = track_rect.y() + margin
        painter.setBrush(self._circle_color)
        painter.drawEllipse(int(circle_x), circle_y, circle_diam, circle_diam)

        # Текст (подпись) — рисуем через стиль в оставшейся области
        opt.rect = label_rect
        self.style().drawControl(
            QStyle.ControlElement.CE_CheckBoxLabel, opt, painter, self
        )

    def set_toggle_colors(
        self,
        bg_color: str,
        circle_color: str,
        active_color: str,
    ) -> None:
        self._bg_color = QColor(bg_color)
        self._circle_color = QColor(circle_color)
        self._active_color = QColor(active_color)
        self.update()

    def sizeHint(self):
        base = super().sizeHint()
        base.setHeight(max(base.height(), TRACK_HEIGHT + 8))
        base.setWidth(base.width() + TRACK_WIDTH + 8)
        return base
