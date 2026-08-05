"""
Скрипт для тестирования производительности единого сканирования.
Сравнивает время выполнения старого и нового подхода.
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from repositories import FileSystemRepository
from engine_modules.scanning import scan_total_size, scan_sources_unified


def create_test_directory(base_path: Path, num_files: int = 100) -> Path:
    """Создает тестовую директорию с файлами"""
    test_dir = base_path / "test_source"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаем подпапки и файлы
    for i in range(num_files):
        subdir = test_dir / f"subdir_{i % 10}"
        subdir.mkdir(exist_ok=True)
        file_path = subdir / f"file_{i}.txt"
        file_path.write_text(f"Test content {i}" * 100)
    
    return test_dir


def run_old_approach(source_path: str, destination_root: str, fs, log_callback) -> tuple[float, int, int]:
    """Тестирует старый подход: два отдельных сканирования"""
    start_time = time.time()
    
    # Первое сканирование для размера
    total_size = scan_total_size([source_path], log_callback, fs)
    
    # Второе сканирование для списка файлов
    result = scan_sources_unified([source_path], destination_root, log_callback, fs)
    files_list = result.files_list

    elapsed = time.time() - start_time
    return elapsed, total_size, len(files_list)


def run_new_approach(source_path: str, destination_root: str, fs, log_callback) -> tuple[float, int, int]:
    """Тестирует новый подход: единое сканирование"""
    start_time = time.time()
    
    result = scan_sources_unified([source_path], destination_root, log_callback, fs)
    
    elapsed = time.time() - start_time
    return elapsed, result.total_size, len(result.files_list)


def main() -> int:
    fs = FileSystemRepository()
    
    logs: list[str] = []
    
    def log_callback(msg: str) -> None:
        logs.append(msg)
    
    with tempfile.TemporaryDirectory() as tmp:
        base_path = Path(tmp)
        destination_root = str(base_path / "destination")
        
        # Создаем тестовую директорию
        print("Создание тестовой директории...")
        test_dir = create_test_directory(base_path, num_files=50)
        source_path = str(test_dir)
        
        print(f"\nТестирование с {len(list(test_dir.rglob('*')))} файлов...")
        print("=" * 60)
        
        # Тест старого подхода
        print("\n1. Старый подход (два отдельных сканирования):")
        old_time, old_size, old_count = run_old_approach(source_path, destination_root, fs, log_callback)
        print(f"   Время: {old_time:.3f} сек")
        print(f"   Размер: {old_size} байт")
        print(f"   Файлов: {old_count}")
        
        # Очищаем логи
        logs.clear()
        
        # Тест нового подхода
        print("\n2. Новый подход (единое сканирование):")
        new_time, new_size, new_count = run_new_approach(source_path, destination_root, fs, log_callback)
        print(f"   Время: {new_time:.3f} сек")
        print(f"   Размер: {new_size} байт")
        print(f"   Файлов: {new_count}")
        
        # Сравнение
        print("\n" + "=" * 60)
        print("СРАВНЕНИЕ:")
        print(f"   Ускорение: {old_time / new_time:.2f}x")
        print(f"   Экономия времени: {old_time - new_time:.3f} сек ({((old_time - new_time) / old_time * 100):.1f}%)")
        
        # Проверка корректности
        if old_size != new_size:
            print(f"\nОШИБКА: Размеры не совпадают! Старый: {old_size}, Новый: {new_size}")
            return 1
        
        if old_count != new_count:
            print(f"\nОШИБКА: Количество файлов не совпадает! Старый: {old_count}, Новый: {new_count}")
            return 1
        
        print("\n✓ Результаты идентичны - оптимизация работает корректно!")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
