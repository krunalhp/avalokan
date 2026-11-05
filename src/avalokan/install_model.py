"""Explicit, checksum-pinned model installation; never downloads during inference."""

import hashlib
import urllib.request

from .settings import MODEL_SHA256, MODEL_URL, Settings


def main():
    path = Settings().model
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == MODEL_SHA256:
        print("YOLOX Nano model already verified")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    try:
        with (
            urllib.request.urlopen(MODEL_URL, timeout=60) as response,
            temporary.open("wb") as target,
        ):
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 20 * 1024 * 1024:
                    raise ValueError("Unexpected model size")
                target.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("Downloaded model checksum mismatch")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print(
        "YOLOX Nano model installed and verified (Apache-2.0 source; see research for artifact/data terms)"
    )


if __name__ == "__main__":
    main()
