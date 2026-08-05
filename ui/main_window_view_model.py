"""
ViewModel для управления состоянием главного окна приложения.
Отвечает за логику проверки условий и состояния UI, отделяя её от представления.
"""

from backup_state_manager import BackupStateManager
from source_manager import SourceManager


class MainWindowViewModel:
    """ViewModel для управления состоянием главного окна"""
    
    def __init__(
        self, 
        state_manager: BackupStateManager,
        source_manager: SourceManager
    ):
        """
        Инициализация ViewModel
        
        :param state_manager: Менеджер состояния резервного копирования
        :param source_manager: Менеджер источников
        """
        self.state_manager = state_manager
        self.source_manager = source_manager
    
    def can_start_backup(self) -> bool:
        """
        Проверяет, можно ли начать резервное копирование
        
        :return: True если можно начать копирование
        """
        has_sources = self.state_manager.has_sources()
        has_destination = self.state_manager.has_destination()
        
        # Базовые условия: должны быть источники и назначение
        return has_sources and has_destination
    
    def has_basic_conditions(self) -> bool:
        """
        Проверяет базовые условия (источники и назначение)
        
        :return: True если есть источники и назначение
        """
        return self.state_manager.has_sources() and self.state_manager.has_destination()
    
    def get_disk_space_info(self, file_system) -> tuple:
        """
        Получает информацию о месте на диске
        
        :param file_system: Интерфейс файловой системы
        :return: Кортеж (is_sufficient, free_space, total_space, required_space)
        """
        if not self.state_manager.has_destination():
            return (True, 0, 0, 0)
        
        try:
            from utils import get_disk_free_space
            
            destination_path = self.state_manager.destination_path
            total_space, used_space, free_space = get_disk_free_space(
                destination_path, file_system=file_system
            )
            
            if total_space == 0:
                # Не удалось получить информацию о диске
                return (True, 0, 0, 0)
            
            # Получаем общий размер всех исходников
            required_space = self.source_manager.get_total_sources_size()
            
            # Используем запас 5%: проверяем, что required_space <= 95% от free_space
            available_with_margin = free_space * 0.95
            is_sufficient = required_space <= available_with_margin
            
            return (is_sufficient, free_space, total_space, required_space)
        except Exception:
            return (True, 0, 0, 0)  # В случае ошибки считаем что места достаточно
    
