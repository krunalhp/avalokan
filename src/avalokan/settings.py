import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
MODEL_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
)


@dataclass
class Settings:
    data: Path = field(default_factory=lambda: Path(os.getenv("AVALOKAN_DATA", ROOT / ".data")))
    token: str = field(default_factory=lambda: os.getenv("AVALOKAN_API_TOKEN", ""))
    demo: bool = field(default_factory=lambda: os.getenv("AVALOKAN_DEMO") == "1")
    max_upload: int = 250 * 1024 * 1024
    max_duration: int = 600

    @property
    def dsn(self):
        return os.getenv(
            "AVALOKAN_DATABASE_URL",
            f"dbname=postgres host={self.data.resolve() / 'socket'} port=55432",
        )

    @property
    def model(self):
        return self.data / "models/yolox_nano.onnx"

    @property
    def cookies_file(self):
        """Netscape cookies.txt for sites that block datacenter downloads.

        Set AVALOKAN_YTDLP_COOKIES to a custom path or place the file at
        .data/secrets/youtube-cookies.txt. Never committed to Git.
        """
        override = os.getenv("AVALOKAN_YTDLP_COOKIES", "")
        return Path(override) if override else self.data / "secrets/youtube-cookies.txt"

    @property
    def allowed(self):
        from .activities import REGISTRY

        value = os.getenv("AVALOKAN_ALLOWED_ACTIVITIES")
        return set(REGISTRY) if value is None else set(filter(None, value.split(",")))
