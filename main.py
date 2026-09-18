from __future__ import annotations

import logging
import os
import threading
import webbrowser
import uvicorn

from src.namescope.config import load_settings


def _open_browser(url: str, delay: float = 0.8) -> None:
    timer = threading.Timer(delay, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not settings.is_loopback and not settings.allow_remote:
        raise SystemExit(
            "Refusing to bind NameScope to a non-loopback address. "
            "Set NAMESCOPE_ALLOW_REMOTE=true only if you understand that the app has no authentication layer."
        )

    url = f"http://{settings.host}:{settings.port}"
    headless = os.environ.get("NAMESCOPE_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}
    if settings.open_browser and settings.is_loopback and not headless:
        _open_browser(url)

    uvicorn.run(
        "src.namescope.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
