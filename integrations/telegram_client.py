"""Единый клиент Telegram Bot API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


DEFAULT_TIMEOUT_SECONDS = 10
TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TEST_MESSAGE = "Тестовое сообщение от Dублёр"


@dataclass(frozen=True, slots=True)
class TelegramResult:
    """Результат операции Telegram без утечки HTTP-деталей в UI."""

    success: bool
    message: str
    error_code: Optional[str] = None


class TelegramClient:
    """Инкапсулирует HTTP-протокол Telegram Bot API."""

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        requests_module: Any = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._requests_module = requests_module

    @staticmethod
    def validate_token_format(token: str) -> TelegramResult:
        normalized = (token or "").strip()
        if not normalized:
            return TelegramResult(False, "Telegram токен не указан", "missing_credentials")

        parts = normalized.split(":", 1)
        if len(parts) != 2 or not parts[0].isdigit() or len(parts[1]) < 10:
            return TelegramResult(False, "Неверный формат токена", "invalid_token_format")
        return TelegramResult(True, "Формат токена корректен")

    @staticmethod
    def validate_chat_id_format(chat_id: str) -> TelegramResult:
        normalized = (chat_id or "").strip()
        if not normalized:
            return TelegramResult(False, "Telegram Chat ID не указан", "missing_credentials")

        numeric_part = normalized[1:] if normalized.startswith("-") else normalized
        if not numeric_part.isdigit():
            return TelegramResult(False, "Неверный формат Chat ID", "invalid_chat_id_format")
        return TelegramResult(True, "Формат Chat ID корректен")

    def validate_token(self, token: str) -> TelegramResult:
        """Проверяет формат токена и вызывает Telegram ``getMe``."""
        format_result = self.validate_token_format(token)
        if not format_result.success:
            return format_result

        return self._request(
            "get",
            f"{TELEGRAM_API_BASE_URL}/bot{token.strip()}/getMe",
            success_message="Токен подтверждён Telegram",
        )

    def send_message(
        self,
        token: str,
        chat_id: str,
        text: str,
        *,
        parse_mode: Optional[str] = None,
    ) -> TelegramResult:
        """Отправляет сообщение в указанный Telegram-чат."""
        token_result = self.validate_token_format(token)
        if not token_result.success:
            return token_result
        chat_result = self.validate_chat_id_format(chat_id)
        if not chat_result.success:
            return chat_result

        payload = {"chat_id": chat_id.strip(), "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        return self._request(
            "post",
            f"{TELEGRAM_API_BASE_URL}/bot{token.strip()}/sendMessage",
            json=payload,
            success_message="Сообщение отправлено в Telegram",
        )

    def test_connection(self, token: str, chat_id: str) -> TelegramResult:
        """Проверяет токен и отправляет тестовое сообщение."""
        token_result = self.validate_token(token)
        if not token_result.success:
            return token_result

        send_result = self.send_message(token, chat_id, TEST_MESSAGE)
        if not send_result.success:
            return send_result
        return TelegramResult(True, "Подключение успешно! Тестовое сообщение отправлено.")

    def _get_requests(self):
        if self._requests_module is not None:
            return self._requests_module
        try:
            import requests
        except ImportError:
            return None
        return requests

    def _request(
        self,
        method: str,
        url: str,
        *,
        success_message: str,
        json: Optional[dict[str, Any]] = None,
    ) -> TelegramResult:
        requests_module = self._get_requests()
        if requests_module is None:
            return TelegramResult(
                False,
                "Модуль 'requests' не установлен",
                "dependency_missing",
            )

        try:
            request_method = getattr(requests_module, method)
            kwargs: dict[str, Any] = {"timeout": self._timeout_seconds}
            if json is not None:
                kwargs["json"] = json
            response = request_method(url, **kwargs)

            status_code = getattr(response, "status_code", None)
            if status_code == 401:
                return TelegramResult(False, "Telegram отклонил токен", "unauthorized")
            if status_code == 429:
                return TelegramResult(
                    False,
                    "Слишком много запросов к Telegram. Повторите позже.",
                    "rate_limited",
                )

            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return TelegramResult(False, "Некорректный ответ Telegram", "invalid_response")
            if not payload.get("ok"):
                return TelegramResult(
                    False,
                    str(payload.get("description") or "Telegram API вернул ошибку"),
                    "api_error",
                )
            return TelegramResult(True, success_message)
        except Exception as exc:  # HTTP-библиотека подменяется в тестах
            exceptions = getattr(requests_module, "exceptions", None)
            timeout_type = getattr(exceptions, "Timeout", ()) if exceptions else ()
            request_error_type = (
                getattr(exceptions, "RequestException", ()) if exceptions else ()
            )
            if timeout_type and isinstance(exc, timeout_type):
                return TelegramResult(False, "Таймаут подключения", "timeout")
            if request_error_type and isinstance(exc, request_error_type):
                return TelegramResult(False, f"Ошибка подключения: {exc}", "network_error")
            if isinstance(exc, (ValueError, TypeError)):
                return TelegramResult(False, "Некорректный ответ Telegram", "invalid_response")
            return TelegramResult(False, f"Ошибка Telegram API: {exc}", "network_error")
