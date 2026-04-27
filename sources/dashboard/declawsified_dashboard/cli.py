"""Console-script entry: `declawsified-dashboard` → `streamlit run app.py`."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Defer importing streamlit so `--help` can run without it.
    from streamlit.web import cli as stcli

    app_path = Path(__file__).with_name("app.py")
    sys.argv = [
        "streamlit", "run", str(app_path),
        "--server.address", "127.0.0.1",
        "--server.port", "8501",
        "--browser.gatherUsageStats", "false",
    ]
    return stcli.main()  # type: ignore[no-any-return]


if __name__ == "__main__":
    raise SystemExit(main())
