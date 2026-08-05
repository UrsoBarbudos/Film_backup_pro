"""
Модуль для предотвращения спящего режима системы во время копирования
"""

import subprocess


class SleepPrevention:
    """
    Контекстный менеджер для предотвращения спящего режима macOS
    во время выполнения процесса копирования.
    
    Использует команду caffeinate для предотвращения:
    - idle sleep (спящий режим системы)
    - display sleep (спящий режим дисплея)
    """
    
    def __init__(self):
        
        self.process = None
    
    def __enter__(self):
        """Запускает процесс caffeinate при входе в контекст"""
        try:
            # Запускаем caffeinate с флагами:
            # -i: предотвращает idle sleep (спящий режим системы)
            # -d: предотвращает display sleep (спящий режим дисплея)
            self.process = subprocess.Popen(
                ['caffeinate', '-i', '-d'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print("INFO: Предотвращение спящего режима включено", flush=True)
        except FileNotFoundError:
            print("WARNING: Команда caffeinate не найдена. Предотвращение спящего режима недоступно.", flush=True)
            self.process = None
        except Exception as e:
            print(f"WARNING: Не удалось запустить caffeinate: {e}", flush=True)
            self.process = None
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Завершает процесс caffeinate при выходе из контекста"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                print("INFO: Предотвращение спящего режима выключено", flush=True)
            except subprocess.TimeoutExpired:
                print("WARNING: Процесс caffeinate не завершился вовремя, принудительное завершение...", flush=True)
                self.process.kill()
                self.process.wait()
            except Exception as e:
                print(f"WARNING: Ошибка при завершении caffeinate: {e}", flush=True)
        
        # Возвращаем False, чтобы не подавлять исключения
        return False
