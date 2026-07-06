"""Allow running the data_sync package as a module: python -m modules.data_sync"""

from .cli import main

if __name__ == "__main__":
    from modules import ensure_utf8_stdout
    ensure_utf8_stdout()
    main()
