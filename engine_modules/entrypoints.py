from __future__ import annotations

import logging
from typing import Optional

from interfaces import IFileSystemInterface

logger = logging.getLogger(__name__)


def start_backup_process(
    destination_root: str,
    source_drives: list,
    log_callback,
    prevent_sleep: bool = True,
    success_callback=None,
    create_md_log: bool = False,
    pause_event=None,
    pause_token=None,
    cancel_token=None,
    progress_callback=None,
    signals=None,
    verification_action_callback=None,
    copy_conflict_action_callback=None,
    config=None,
    file_system: Optional[IFileSystemInterface] = None,
    progress_batcher=None,
    telegram_client=None,
    source_backup_marker_service=None,
):
    """
    Главная управляющая функция (обертка для обратной совместимости):
    создает BackupOrchestrator и запускает процесс резервного копирования.
    """
    logger.info(
        "start_backup_process() entry (destination=%s, sources=%d)",
        destination_root,
        len(source_drives),
    )

    # Локальные импорты, чтобы избежать циклических зависимостей с `engine.py`.
    from backup_components import BackupOrchestrator
    from backup_components.backup_run_context import (
        BackupCallbacks,
        BackupDeps,
        BackupRunConfig,
        BackupTokens,
    )

    verification_mode = config.get("verification_mode", "full") if config else "full"

    logger.debug(
        "Creating BackupOrchestrator (verification_mode=%s)",
        verification_mode,
    )

    run = BackupRunConfig(
        destination_root=destination_root,
        source_drives=list(source_drives),
        verification_mode=verification_mode,
        create_md_log=create_md_log,
        prevent_sleep=prevent_sleep,
    )
    tokens = BackupTokens.from_legacy(
        pause_event=pause_event,
        pause_token=pause_token,
        cancel_token=cancel_token,
    )
    callbacks = BackupCallbacks(
        log_callback=log_callback,
        progress_callback=progress_callback,
        signals=signals,
        verification_action_callback=verification_action_callback,
        copy_conflict_action_callback=copy_conflict_action_callback,
        success_callback=success_callback,
        progress_batcher=progress_batcher,
    )
    deps = BackupDeps(
        file_system=file_system,  # type: ignore[arg-type]
        config=config,
        telegram_client=telegram_client,
        source_backup_marker_service=source_backup_marker_service,
    )

    orchestrator = BackupOrchestrator.create(run=run, tokens=tokens, callbacks=callbacks, deps=deps)

    orchestrator.run()
    logger.debug("start_backup_process(): orchestrator.run() finished")
