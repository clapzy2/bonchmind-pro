"""Run BonchMind Pro API locally."""

import os
import sys

import config


def main():
    config_errors = config.validate_config()
    if config_errors:
        print("Ошибки конфигурации:")
        for err in config_errors:
            print(f" - {err}")
        sys.exit(1)

    for path in [config.DOCS_DIR, config.DATA_DIR]:
        os.makedirs(path, exist_ok=True)

    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    print("BonchMind Pro API")
    print(f"URL: http://127.0.0.1:{port}")
    uvicorn.run("api_app:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
