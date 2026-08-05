from types import SimpleNamespace

from integrations.telegram_client import TelegramClient, TelegramResult
from notifications import NotificationManager


class FakeTimeout(Exception):
    pass


class FakeRequestException(Exception):
    pass


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, error=None):
        self._payload = payload
        self.status_code = status_code
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeRequests:
    exceptions = SimpleNamespace(
        Timeout=FakeTimeout,
        RequestException=FakeRequestException,
    )

    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse({"ok": True})
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if self.error:
            raise self.error
        return self.response

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if self.error:
            raise self.error
        return self.response


class FakeTelegramClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def send_message(self, token, chat_id, text, *, parse_mode=None):
        self.calls.append((token, chat_id, text, parse_mode))
        return self.result

    def test_connection(self, token, chat_id):
        self.calls.append((token, chat_id))
        return self.result


def test_validates_token_and_chat_id_format_without_network():
    assert TelegramClient.validate_token_format("123456:abcdefghij").success
    assert not TelegramClient.validate_token_format("bad-token").success
    assert TelegramClient.validate_chat_id_format("-100123456").success
    assert not TelegramClient.validate_chat_id_format("channel-name").success


def test_validate_token_calls_get_me_with_timeout():
    requests = FakeRequests()
    client = TelegramClient(timeout_seconds=7, requests_module=requests)

    result = client.validate_token("123456:abcdefghij")

    assert result.success
    method, url, kwargs = requests.calls[0]
    assert method == "get"
    assert url.endswith("/bot123456:abcdefghij/getMe")
    assert kwargs == {"timeout": 7}


def test_send_message_builds_expected_payload():
    requests = FakeRequests()
    client = TelegramClient(requests_module=requests)

    result = client.send_message(
        "123456:abcdefghij",
        "-100123",
        "Готово",
        parse_mode="Markdown",
    )

    assert result.success
    method, url, kwargs = requests.calls[0]
    assert method == "post"
    assert url.endswith("/bot123456:abcdefghij/sendMessage")
    assert kwargs["json"] == {
        "chat_id": "-100123",
        "text": "Готово",
        "parse_mode": "Markdown",
    }


def test_maps_api_and_transport_errors():
    cases = [
        (FakeRequests(FakeResponse({"ok": False, "description": "Bad Request"})), "api_error"),
        (FakeRequests(FakeResponse({"ok": False}, status_code=401)), "unauthorized"),
        (FakeRequests(FakeResponse({"ok": False}, status_code=429)), "rate_limited"),
        (FakeRequests(error=FakeTimeout()), "timeout"),
        (FakeRequests(error=FakeRequestException("offline")), "network_error"),
        (FakeRequests(FakeResponse(ValueError("invalid json"))), "invalid_response"),
    ]

    for requests, expected_code in cases:
        result = TelegramClient(requests_module=requests).validate_token(
            "123456:abcdefghij"
        )
        assert not result.success
        assert result.error_code == expected_code


def test_notification_manager_delegates_to_injected_client(tmp_path):
    md_log = tmp_path / "result.md"
    md_log.write_text("Копирование завершено", encoding="utf-8")
    client = FakeTelegramClient(TelegramResult(True, "ok"))
    manager = NotificationManager(
        telegram_enabled=True,
        telegram_bot_token="123456:abcdefghij",
        telegram_chat_id="-100123",
        telegram_client=client,
    )

    assert manager.send_telegram_notification(str(md_log), {"successful_files": 1, "total_files": 1})
    assert client.calls[0][0:2] == ("123456:abcdefghij", "-100123")
    assert client.calls[0][3] == "Markdown"


def test_notification_manager_returns_client_error(tmp_path):
    md_log = tmp_path / "result.md"
    md_log.write_text("Ошибка", encoding="utf-8")
    client = FakeTelegramClient(
        TelegramResult(False, "Telegram недоступен", "network_error")
    )
    manager = NotificationManager(
        telegram_enabled=True,
        telegram_bot_token="123456:abcdefghij",
        telegram_chat_id="123",
        telegram_client=client,
    )

    assert not manager.send_telegram_notification(str(md_log))
