"""
Виджет для области drag and drop
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from paths import get_assets_animations_dir
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPixmap


logger = logging.getLogger(__name__)


class DropZone(QFrame):
    """Виджет для области drag and drop"""
    
    def __init__(
        self,
        parent=None,
        label_text="",
        is_destination=False,
        app_instance=None,
        animation_frames_dir: Optional[str] = None,
    ):
        super().__init__(parent)
        self.is_destination = is_destination
        self.app_instance = app_instance
        self.theme = 'light'  # По умолчанию светлая тема
        self._animation_frames_dir = animation_frames_dir
        self._frame_pixmaps: Dict[int, QPixmap] = {}
        self._active_frame_sequence: List[int] = []
        self._active_frame_index = 0
        self._frame_interval_ms = 33  # 30 FPS
        self._is_drag_active = False
        self._suppress_hover_after_drop_until_leave = False
        self._animation_opacity = 0.80
        self._hover_animation_active = False  # Флаг, что анимация входа была запущена

        if app_instance:
            self.theme = app_instance.theme
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        # Устанавливаем объектное имя для более точного применения стилей
        self.setObjectName("DropZone")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.animation_container = QWidget(self)
        self.animation_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        animation_layout = QVBoxLayout(self.animation_container)
        animation_layout.setContentsMargins(0, 0, 0, 0)
        animation_layout.setSpacing(0)

        self.animation_label = QLabel()
        self.animation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.animation_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.animation_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.animation_label.setAutoFillBackground(False)
        self.animation_label.setStyleSheet("background-color: transparent; border: none;")
        self._animation_opacity_effect = QGraphicsOpacityEffect(self.animation_label)
        self._animation_opacity_effect.setOpacity(self._animation_opacity)
        self.animation_label.setGraphicsEffect(self._animation_opacity_effect)
        icon_offset_y = 8
        animation_top_margin = 4   # отступ от верха для PNG-анимации
        self.animation_label.setContentsMargins(0, animation_top_margin, 0, icon_offset_y)
        # Поднимаем только иконку, не влияя на положение текста под ней.
        self.animation_label.setContentsMargins(0, -icon_offset_y, 0, icon_offset_y)
        self.animation_label.setFixedSize(120, 120)
        animation_layout.addWidget(self.animation_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.animation_container, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setContentsMargins(0, 0, 0, 12)
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        self.setMinimumHeight(160)
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._on_animation_tick)
        self._hover_delay_timer = QTimer(self)
        self._hover_delay_timer.setSingleShot(True)
        self._hover_delay_timer.timeout.connect(self._on_hover_delay_timeout)
        self._hover_leave_delay_timer = QTimer(self)
        self._hover_leave_delay_timer.setSingleShot(True)
        self._hover_leave_delay_timer.timeout.connect(self._on_hover_leave_delay_timeout)
        self._hover_delay_ms = 80
        self._hover_leave_delay_ms = 150
        self._init_png_animation()
        self.update_theme(self.theme)

    def _resolve_frames_dir(self) -> Optional[Path]:
        """Ищет директорию PNG-кадров анимации по приоритетным путям."""
        if self._animation_frames_dir:
            explicit_dir = Path(self._animation_frames_dir).expanduser()
            if explicit_dir.exists() and explicit_dir.is_dir():
                return explicit_dir

        base_dir = Path(get_assets_animations_dir())
        candidates = [
            base_dir / "media_folder_v2",
            base_dir / "media_folder",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    def _find_frame_file(self, frames_dir: Path, frame: int) -> Optional[Path]:
        """Ищет PNG-файл для конкретного номера кадра в распространенных шаблонах."""
        dir_prefix = frames_dir.name
        base_prefix = re.sub(r"_v\d+$", "", dir_prefix)
        candidates = (
            frames_dir / f"{dir_prefix}_{frame:05d}.png",
            frames_dir / f"{base_prefix}_{frame:05d}.png",
            frames_dir / f"frame_{frame:05d}.png",
            frames_dir / f"frame_{frame:04d}.png",
            frames_dir / f"{frame:05d}.png",
            frames_dir / f"{frame:04d}.png",
            frames_dir / f"frame_{frame}.png",
            frames_dir / f"{frame}.png",
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _load_scaled_frame(self, frame_path: Path) -> Optional[QPixmap]:
        """Загружает и масштабирует кадр под размер animation_label."""
        pixmap = QPixmap(str(frame_path))
        if pixmap.isNull():
            return None
        return pixmap.scaled(
            self.animation_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _init_png_animation(self) -> None:
        """Инициализирует PNG-кадры для hover in/out."""
        frames_dir = self._resolve_frames_dir()
        if frames_dir is None:
            logger.warning("PNG frames directory for drop zone animation was not found")
            return

        needed_frames = sorted(set(range(0, 13)) | set(range(21, 30)))
        for frame in needed_frames:
            frame_file = self._find_frame_file(frames_dir, frame)
            if frame_file is None:
                continue
            pixmap = self._load_scaled_frame(frame_file)
            if pixmap is not None:
                self._frame_pixmaps[frame] = pixmap

        if self._frame_pixmaps:
            initial_frame = 0 if 0 in self._frame_pixmaps else min(self._frame_pixmaps)
            self.animation_label.setPixmap(self._frame_pixmaps[initial_frame])
        else:
            logger.warning("No PNG animation frames were loaded for drop zone")

    def _start_segment(self, start_frame: int, end_frame: int) -> None:
        """Запускает проигрывание заданного диапазона кадров."""
        if not self._frame_pixmaps:
            return

        self._animation_timer.stop()
        self._active_frame_sequence = [
            frame for frame in range(start_frame, end_frame + 1)
            if frame in self._frame_pixmaps
        ]
        if not self._active_frame_sequence:
            return

        self._active_frame_index = 0
        self._apply_current_frame()
        if len(self._active_frame_sequence) > 1:
            self._animation_timer.start(self._frame_interval_ms)

    def _apply_current_frame(self) -> None:
        """Применяет текущий кадр активного сегмента."""
        if not self._active_frame_sequence:
            return
        frame = self._active_frame_sequence[self._active_frame_index]
        pixmap = self._frame_pixmaps.get(frame)
        if pixmap is not None:
            self.animation_label.setPixmap(pixmap)

    def _on_animation_tick(self) -> None:
        """Переход к следующему кадру активного сегмента."""
        if not self._active_frame_sequence:
            self._animation_timer.stop()
            return

        if self._active_frame_index >= len(self._active_frame_sequence) - 1:
            self._animation_timer.stop()
            # Сбрасываем флаг после завершения анимации выхода (сегмент 21-29)
            if self._active_frame_sequence and self._active_frame_sequence[0] == 21:
                self._hover_animation_active = False
            return

        self._active_frame_index += 1
        self._apply_current_frame()
    
    def _on_hover_delay_timeout(self) -> None:
        """Обработчик таймера задержки hover-анимации входа"""
        self._hover_animation_active = True
        self._start_segment(0, 12)
    
    def _on_hover_leave_delay_timeout(self) -> None:
        """Обработчик таймера задержки hover-анимации выхода"""
        self._start_segment(21, 29)
    
    def update_theme(self, theme):
        """Обновляет стили в зависимости от темы"""
        self.theme = theme
        if theme == 'dark':
            border_color = "#666"
            text_color = "#aaa"
            hover_bg = "rgba(47, 165, 114, 0.1)"
        else:
            border_color = "#999"
            text_color = "#808080"
            hover_bg = "#e8f5e9"
        
        # Сохраняем фиксированную высоту ДО применения стилей
        # (setStyleSheet может вызывать пересчет размеров и переопределять minimumHeight)
        fixed_height_before = None
        if self.maximumHeight() == self.minimumHeight() and self.maximumHeight() > 0:
            fixed_height_before = self.maximumHeight()
        
        # Используем объектное имя для точного применения стилей только к этому виджету
        # и явно исключаем дочерние элементы
        self.setStyleSheet(f"""
            QFrame#DropZone {{
                border: 2px dashed {border_color};
                border-radius: 8px;
                background-color: transparent;
                min-height: 80px;
            }}
            QFrame#DropZone:hover {{
                border: 2px dashed #2FA572;
                background-color: {hover_bg};
            }}
        """)
        
        # Восстанавливаем фиксированную высоту, если она была установлена ранее
        # (setStyleSheet может изменить minimumHeight через CSS min-height)
        if fixed_height_before is not None:
            self.setFixedHeight(fixed_height_before)
        
        self.label.setStyleSheet(f"""
            color: {text_color};
            font-size: 11px;
            border: none;
            background-color: transparent;
            padding: 0px;
            margin: 0px;
        """)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Обработка входа перетаскиваемого объекта"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid = False
            
            from utils import validate_path
            fs = getattr(self.app_instance, "file_system", None) if self.app_instance else None
            if fs is None:
                event.ignore()
                return
            for url in urls:
                path = url.toLocalFile()
                if not validate_path(path, file_system=fs):
                    continue
                
                # Для источников принимаем файлы и папки
                # Для назначения - только папки
                if self.is_destination:
                    if os.path.isdir(path):
                        valid = True
                        break
                else:
                    # Источники: файлы или папки
                    if os.path.isfile(path) or os.path.isdir(path):
                        valid = True
                        break
            
            if valid:
                event.acceptProposedAction()
                # Отменяем задержку hover-анимации, так как drag запускает анимацию сразу
                self._hover_delay_timer.stop()
                self._hover_leave_delay_timer.stop()
                self._hover_animation_active = False
                if not self._is_drag_active:
                    self._start_segment(0, 12)
                self._is_drag_active = True
                if self.theme == 'dark':
                    hover_bg = "rgba(47, 165, 114, 0.25)"
                else:
                    hover_bg = "#e8f5e9"
                # Сохраняем фиксированную высоту перед применением стилей
                fixed_height_before = None
                if self.maximumHeight() == self.minimumHeight() and self.maximumHeight() > 0:
                    fixed_height_before = self.maximumHeight()
                elif self.maximumHeight() > 0 and self.maximumHeight() < 1000:  # Если max установлен (фиксированная высота)
                    fixed_height_before = self.maximumHeight()
                # Используем объектное имя для точного применения стилей
                self.setStyleSheet(f"""
                    QFrame#DropZone {{
                        border: 2px dashed #2FA572;
                        border-radius: 8px;
                        background-color: {hover_bg};
                        min-height: 80px;
                    }}
                """)
                # Восстанавливаем фиксированную высоту после setStyleSheet
                if fixed_height_before is not None:
                    self.setFixedHeight(fixed_height_before)
                # Убеждаемся, что label не имеет границ
                if self.theme == 'dark':
                    text_color = "#aaa"
                else:
                    text_color = "#666"
                self.label.setStyleSheet(f"""
                    color: {text_color};
                    font-size: 11px;
                    border: none;
                    background-color: transparent;
                    padding: 0px;
                    margin: 0px;
                """)
            else:
                event.ignore()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Обработка выхода перетаскиваемого объекта"""
        if self._is_drag_active:
            self._start_segment(21, 29)
        self._is_drag_active = False
        self.update_theme(self.theme)
        # Восстанавливаем фиксированную высоту после update_theme
        if self.maximumHeight() == self.minimumHeight() and self.maximumHeight() > 0:
            self.setFixedHeight(self.maximumHeight())
        elif self.maximumHeight() > 0 and self.maximumHeight() < 1000:  # Если max установлен (фиксированная высота)
            self.setFixedHeight(self.maximumHeight())
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Обработка события drop"""
        if self._is_drag_active:
            self._start_segment(21, 29)
        self._is_drag_active = False
        self.update_theme(self.theme)
        # Восстанавливаем фиксированную высоту после update_theme
        if self.maximumHeight() == self.minimumHeight() and self.maximumHeight() > 0:
            self.setFixedHeight(self.maximumHeight())
        elif self.maximumHeight() > 0 and self.maximumHeight() < 1000:  # Если max установлен (фиксированная высота)
            self.setFixedHeight(self.maximumHeight())
        
        has_added_paths = False
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = []
            
            from utils import validate_path
            fs = getattr(self.app_instance, "file_system", None) if self.app_instance else None
            if fs is None:
                event.acceptProposedAction()
                return
            for url in urls:
                path = url.toLocalFile()
                if not validate_path(path, file_system=fs):
                    continue
                
                # Для источников принимаем файлы и папки
                # Для назначения - только папки
                if self.is_destination:
                    if os.path.isdir(path):
                        paths.append(path)
                else:
                    # Источники: файлы или папки
                    if os.path.isfile(path) or os.path.isdir(path):
                        paths.append(path)
            
            if paths and self.app_instance:
                # Вызываем методы App для обработки drop
                if self.is_destination:
                    self.app_instance.on_drop_destination(paths[0])
                else:
                    self.app_instance.on_drop_sources(paths)
                has_added_paths = True
        
        self._suppress_hover_after_drop_until_leave = has_added_paths
        event.acceptProposedAction()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Обработка клика по зоне перетаскивания"""
        if event.button() == Qt.MouseButton.LeftButton and self.app_instance:
            # Проверяем флаг перед обработкой события, чтобы предотвратить повторную обработку
            # после закрытия модального диалога
            if not self.is_destination:
                import time
                flag_state = getattr(self.app_instance, '_select_sources_in_progress', False)
                last_close_time = getattr(self.app_instance, '_last_dialog_close_time', 0)
                time_since_close = time.time() - last_close_time
                
                # Игнорируем клик, если диалог открыт или если прошло менее 500ms с момента закрытия диалога
                # Это предотвращает повторную обработку события клика, которое остаётся в очереди Qt
                # после закрытия модального диалога
                if flag_state or (last_close_time > 0 and time_since_close < 0.5):
                    event.ignore()
                    return
            
            # Принимаем событие, чтобы предотвратить дальнейшую обработку
            event.accept()
            if self.is_destination:
                # Используем QTimer для отложенного вызова, чтобы событие клика успело обработаться
                QTimer.singleShot(0, self.app_instance.select_destination)
            else:
                # Используем QTimer для отложенного вызова, чтобы событие клика успело обработаться
                # Это предотвращает повторную обработку события после закрытия модального диалога
                QTimer.singleShot(0, self.app_instance.select_sources)
        else:
            # Если событие не обработано, передаем его родителю
            super().mousePressEvent(event)
    
    def enterEvent(self, event):
        """Изменение курсора при наведении на зону"""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if not self._is_drag_active and not self._suppress_hover_after_drop_until_leave:
            # Отменяем таймер выхода, если курсор вернулся в зону
            was_exit_timer_running = self._hover_leave_delay_timer.isActive()
            self._hover_leave_delay_timer.stop()
            # Проверяем, идет ли сейчас анимация выхода (сегмент 21-29)
            is_exit_animation_running = (self._active_frame_sequence and 
                                       len(self._active_frame_sequence) > 0 and 
                                       self._active_frame_sequence[0] == 21)
            # Если таймер выхода был активен или идет анимация выхода, сбрасываем флаг и останавливаем анимацию
            if was_exit_timer_running or is_exit_animation_running:
                if is_exit_animation_running:
                    # Останавливаем анимацию выхода
                    self._animation_timer.stop()
                    self._active_frame_sequence = []
                self._hover_animation_active = False
            # Если анимация входа уже была запущена, не запускаем её снова
            if not self._hover_animation_active:
                # Запускаем анимацию с задержкой 200 мс для предотвращения дергания при быстром движении мыши
                self._hover_delay_timer.start(self._hover_delay_ms)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Восстановление курсора при уходе с зоны"""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        # Отменяем задержку hover-анимации входа, если курсор ушел до истечения задержки
        self._hover_delay_timer.stop()
        if self._suppress_hover_after_drop_until_leave:
            self._suppress_hover_after_drop_until_leave = False
            super().leaveEvent(event)
            return
        # Запускаем анимацию выхода только если анимация входа была запущена
        if not self._is_drag_active and self._hover_animation_active:
            # Отменяем предыдущий таймер выхода, если он был запущен
            self._hover_leave_delay_timer.stop()
            # Запускаем анимацию выхода с задержкой 100 мс
            self._hover_leave_delay_timer.start(self._hover_leave_delay_ms)
        elif not self._is_drag_active:
            # Если анимация входа не была запущена, сбрасываем флаг
            self._hover_animation_active = False
        super().leaveEvent(event)
