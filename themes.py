"""
Модуль для управления темами оформления приложения Dублёр
"""


class ThemeManager:
    """Класс для управления темами оформления"""
    
    @staticmethod
    def get_main_window_stylesheet(theme='light'):
        """
        Возвращает стили для главного окна
        
        :param theme: Название темы ('light' или 'dark')
        :return: Строка со стилями CSS
        """
        if theme == 'dark':
            return """
                QMainWindow {
                    background-color: rgba(43, 43, 43, 0.92);
                    color: white;
                }
                QWidget {
                    background-color: #2b2b2b;
                }
                QLabel {
                    color: white;
                }
                QLabel#SectionHeader {
                    color: white;
                    font-weight: bold;
                }
                QLineEdit {
                    background-color: #3b3b3b;
                    color: white;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #555;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
                QPushButton:disabled {
                    background-color: #333;
                    color: #888;
                }
                QScrollArea {
                    background-color: #2b2b2b;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: #2b2b2b;
                }
                QPushButton#SettingsLinkButton {
                    background-color: transparent;
                    color: #aaa;
                    border: none;
                    border-radius: 0px;
                    padding: 2px 2px 2px 0;
                    text-decoration: underline;
                }
                QPushButton#SettingsLinkButton:hover {
                    background-color: transparent;
                    color: #ccc;
                }
            """
        else:
            return """
                QMainWindow {
                    background-color: rgba(250, 250, 250, 0.92);
                }
                QWidget {
                    background-color: white;
                }
                QLabel#SectionHeader {
                    color: black;
                    font-weight: bold;
                }
                QLineEdit {
                    background-color: white;
                    color: black;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #999;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                }
                QPushButton:hover {
                    background-color: #888;
                }
                QPushButton:disabled {
                    background-color: #ccc;
                    color: #888;
                }
                QScrollArea {
                    background-color: white;
                    border: none;
                }
                QScrollArea > QWidget > QWidget {
                    background-color: white;
                }
                QPushButton#SettingsLinkButton {
                    background-color: transparent;
                    color: #666;
                    border: none;
                    border-radius: 0px;
                    padding: 2px 2px 2px 0;
                    text-decoration: underline;
                }
                QPushButton#SettingsLinkButton:hover {
                    background-color: transparent;
                    color: #999;
                }
            """
    
    @staticmethod
    def get_green_button_color():
        """Возвращает цвет зеленой кнопки 'Начать копирование'"""
        return "#2FA572"
    
    @staticmethod
    def get_red_button_color():
        """Возвращает цвет красной кнопки (для неактивной кнопки 'Начать копирование')"""
        return "#dc3545"
    
    @staticmethod
    def get_red_button_color_with_opacity():
        """Возвращает цвет красной кнопки с прозрачностью 35% (непрозрачность 65%)"""
        return "rgba(220, 53, 69, 0.65)"
