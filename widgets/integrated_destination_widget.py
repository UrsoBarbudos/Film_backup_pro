"""
Интегрированный виджет для выбора и отображения папки назначения
"""

import os
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QPixmap, QFont
from PySide6.QtSvg import QSvgRenderer
from .elided_label import ElidedLabel
from utils import get_disk_free_space, format_size
from ui.ui_constants import UISizes


class IntegratedDestinationWidget(QFrame):
    """Интегрированный виджет для выбора и отображения папки назначения"""
    
    def _get_folder_svg(self, theme='light') -> str:
        """Возвращает SVG иконку папки"""
        fill_color = "#666" if theme == 'light' else "#aaa"
        return f"""<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M10 4H4c-1.11 0-2 .89-2 2v12c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2h-8l-2-2z" fill="{fill_color}"/>
        </svg>"""
    
    def __init__(self, parent=None, app_instance=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.theme = app_instance.theme if app_instance else 'light'
        self.current_path = None
        self._is_dragging = False
        self._is_exceeded = False  # Флаг превышения лимита места
        
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setObjectName("IntegratedDestinationWidget")
        self.setFixedHeight(UISizes.DESTINATION_ROW_HEIGHT)
        
        # Основной layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        # Иконка папки (скрыта когда путь не выбран)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.hide()
        
        # SVG иконка папки будет обновляться при изменении темы
        self._update_icon()
        
        layout.addWidget(self.icon_label)
        
        # Контейнер для текста и информации о диске
        from PySide6.QtWidgets import QSizePolicy
        self.text_container = QWidget()
        self.text_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout = QVBoxLayout(self.text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        
        # Текст (placeholder или путь)
        self.text_label = ElidedLabel("Перетащите сюда папку назначения или кликните сюда")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.text_label.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout.addWidget(self.text_label)
        
        # Информация о диске (свободно/всего)
        self.disk_info_label = QLabel()
        self.disk_info_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.disk_info_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        disk_info_font = QFont("Arial", 10)
        self.disk_info_label.setFont(disk_info_font)
        self.disk_info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.disk_info_label.hide()  # Скрыта по умолчанию
        text_layout.addWidget(self.disk_info_label)
        
        layout.addWidget(self.text_container, 1)
        
        self.update_theme(self.theme)
    
    def _update_icon(self):
        """Обновляет иконку папки в зависимости от темы"""
        svg_data = self._get_folder_svg(self.theme)
        svg_renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
        icon_pixmap = QPixmap(24, 24)
        icon_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(icon_pixmap)
        svg_renderer.render(painter)
        painter.end()
        self.icon_label.setPixmap(icon_pixmap)
    
    def update_theme(self, theme):
        """Обновляет стили в зависимости от темы"""
        self.theme = theme
        
        # Определяем цвета в зависимости от состояния превышения
        if self._is_exceeded:
            # Красное состояние при превышении лимита
            if theme == 'dark':
                bg_color = "#3b2b2b"
                border_color = "#DC3545"
                text_color = "white"
                hover_bg = "#4a3333"
                disk_info_color = "#ff6b6b"
            else:
                bg_color = "#fff5f5"
                border_color = "#DC3545"
                text_color = "black"
                hover_bg = "#ffe0e0"
                disk_info_color = "#dc3545"
        else:
            # Обычное состояние
            if theme == 'dark':
                if self.current_path:
                    # Состояние: путь выбран - зеленая граница постоянно
                    bg_color = "#3b3b3b"
                    border_color = "#2FA572"
                    text_color = "white"
                    hover_bg = "#444"
                    disk_info_color = "#aaa"
                else:
                    # Состояние: пусто
                    bg_color = "#2b2b2b"
                    border_color = "#666"
                    text_color = "#aaa"
                    hover_bg = "#333"
                    disk_info_color = "#888"
            else:
                if self.current_path:
                    # Состояние: путь выбран - зеленая граница постоянно
                    bg_color = "white"
                    border_color = "#2FA572"
                    text_color = "black"
                    hover_bg = "#f5f5f5"
                    disk_info_color = "#666"
                else:
                    # Состояние: пусто
                    bg_color = "#f9f9f9"
                    border_color = "#ddd"
                    text_color = "#999"
                    hover_bg = "#f0f0f0"
                    disk_info_color = "#999"
        
        # Обновляем иконку при смене темы
        self._update_icon()
        
        if self.current_path:
            # Когда путь установлен
            hover_border_color = "#ff6b6b" if self._is_exceeded else "#3BC689"
            self.setStyleSheet(f"""
                QFrame#IntegratedDestinationWidget {{
                    background-color: {bg_color};
                    border: 2px solid {border_color};
                    border-radius: 6px;
                }}
                QFrame#IntegratedDestinationWidget:hover {{
                    border-color: {hover_border_color};
                    background-color: {hover_bg};
                }}
            """)
        else:
            # Когда путь не установлен, обычная граница с hover эффектом
            self.setStyleSheet(f"""
                QFrame#IntegratedDestinationWidget {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 6px;
                }}
                QFrame#IntegratedDestinationWidget:hover {{
                    border-color: #2FA572;
                    background-color: {hover_bg};
                }}
            """)
        
        self.text_label.setStyleSheet(f"""
            color: {text_color};
            font-size: 14px;
            background-color: transparent;
            border: none;
        """)
        
        self.disk_info_label.setStyleSheet(f"""
            color: {disk_info_color};
            font-size: 10px;
            background-color: transparent;
            border: none;
        """)
        
        # Устанавливаем прозрачный фон для дочерних виджетов
        if hasattr(self, 'text_container'):
            self.text_container.setStyleSheet("background-color: transparent; border: none;")
        if hasattr(self, 'icon_label'):
            self.icon_label.setStyleSheet("background-color: transparent; border: none;")
    
    def set_path(self, path: str):
        """Устанавливает путь и обновляет отображение"""
        self.current_path = path
        
        if path:
            # Извлекаем имя папки
            clean_path = path.rstrip('/') if path != '/' else path
            folder_name = os.path.basename(clean_path) or path
            self.text_label.setText(folder_name)
            self.text_label.setToolTip(path)
            self.icon_label.show()
            # Обновляем информацию о диске
            self.update_disk_info()
        else:
            self.text_label.setText("Перетащите сюда папку назначения или кликните сюда")
            self.text_label.setToolTip("")
            self.icon_label.hide()
            self.disk_info_label.hide()
        
        self.update_theme(self.theme)
    
    def update_disk_info(self):
        """Обновляет информацию о свободном месте на диске"""
        if self.app_instance and hasattr(self.app_instance, 'debug_logger'):
            self.app_instance.debug_logger.log(
                location="integrated_destination_widget.py:update_disk_info",
                message="update_disk_info called",
                data={"current_path": self.current_path},
                hypothesis_id="D"
            )
        
        if not self.current_path:
            self.disk_info_label.hide()
            return
        
        try:
            if not (self.app_instance and hasattr(self.app_instance, "file_system")):
                self.disk_info_label.hide()
                return

            total, used, free = get_disk_free_space(
                self.current_path, file_system=self.app_instance.file_system
            )
            if self.app_instance and hasattr(self.app_instance, 'debug_logger'):
                self.app_instance.debug_logger.log(
                    location="integrated_destination_widget.py:update_disk_info",
                    message="Disk info retrieved",
                    data={"total": total, "used": used, "free": free},
                    hypothesis_id="D"
                )
            
            if total > 0:
                free_str = format_size(free)
                total_str = format_size(total)
                self.disk_info_label.setText(f"Свободно: {free_str} / Всего: {total_str}")
                self.disk_info_label.setToolTip(f"Свободно: {free_str} / Использовано: {format_size(used)} / Всего: {total_str}")
                self.disk_info_label.show()
            else:
                self.disk_info_label.hide()
        except Exception as e:
            print(f"WARNING: Не удалось получить информацию о диске: {e}", flush=True)
            self.disk_info_label.hide()
    
    def set_exceeded_state(self, is_exceeded: bool):
        """Устанавливает состояние превышения лимита места"""
        if self.app_instance and hasattr(self.app_instance, 'debug_logger'):
            self.app_instance.debug_logger.log(
                location="integrated_destination_widget.py:set_exceeded_state",
                message="set_exceeded_state called",
                data={"is_exceeded": is_exceeded, "current_state": self._is_exceeded, "will_change": self._is_exceeded != is_exceeded},
                hypothesis_id="B,E"
            )
        
        if self._is_exceeded != is_exceeded:
            self._is_exceeded = is_exceeded
            if self.app_instance and hasattr(self.app_instance, 'debug_logger'):
                self.app_instance.debug_logger.log(
                    location="integrated_destination_widget.py:set_exceeded_state",
                    message="State changed, updating theme",
                    data={"new_state": self._is_exceeded, "theme": self.theme},
                    hypothesis_id="E"
                )
            self.update_theme(self.theme)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Обработка входа перетаскиваемого объекта"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid = False
            for url in urls:
                path = url.toLocalFile()
                if os.path.isdir(path):
                    valid = True
                    break
            
            if valid:
                event.acceptProposedAction()
                self._is_dragging = True
                if self.theme == 'dark':
                    hover_bg = "rgba(47, 165, 114, 0.2)"
                else:
                    hover_bg = "#e8f5e9"
                self.setStyleSheet(f"""
                    QFrame#IntegratedDestinationWidget {{
                        background-color: {hover_bg};
                        border: 2px dashed #2FA572;
                        border-radius: 6px;
                    }}
                """)
            else:
                event.ignore()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Обработка выхода перетаскиваемого объекта"""
        self._is_dragging = False
        self.update_theme(self.theme)
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Обработка события drop"""
        self._is_dragging = False
        self.update_theme(self.theme)
        
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = []
            for url in urls:
                path = url.toLocalFile()
                if os.path.isdir(path):
                    paths.append(path)
            
            if paths and self.app_instance:
                self.app_instance.on_drop_destination(paths[0])
        
        event.acceptProposedAction()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Обработка клика по виджету"""
        if event.button() == Qt.MouseButton.LeftButton and self.app_instance:
            self.app_instance.select_destination()
        super().mousePressEvent(event)
    
    def enterEvent(self, event):
        """Изменение курсора при наведении"""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Восстановление курсора при уходе"""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
