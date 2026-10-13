from pathlib import Path

import requests

# Giới hạn của Bot API khi upload file.
MAX_FILE_SIZE = 50 * 1024 * 1024


class TelegramDestination:
    """Gửi file backup tới một chat Telegram."""

    name = "Telegram"

    def __init__(self, token: str, chat_id: str, timeout: int = 300):
        self._url = f"https://api.telegram.org/bot{token}/sendDocument"
        self._chat_id = chat_id
        self._timeout = timeout

    def upload(self, path: Path, caption: str = "") -> None:
        self._ensure_size_ok(path)

        with path.open("rb") as file:
            try:
                response = requests.post(
                    self._url,
                    data={"chat_id": self._chat_id, "caption": caption},
                    files={"document": (path.name, file)},
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                # Không re-raise nguyên exception vì message chứa URL có token.
                raise RuntimeError(f"Không kết nối được Telegram: {type(exc).__name__}") from None

        if not response.ok:
            raise RuntimeError(f"Telegram trả lỗi {response.status_code}: {response.text}")

    @staticmethod
    def _ensure_size_ok(path: Path) -> None:
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            raise ValueError(
                f"File {size / 1024 / 1024:.1f}MB vượt giới hạn 50MB của Telegram Bot API"
            )