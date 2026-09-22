"""Write one short-lived demo access code to a private file.

Does not print the secret or the code. There is no HTTP mint route.
"""

from __future__ import annotations

import os
import stat
import sys
import time
from pathlib import Path

from access_grant import mint_demo_access


def main() -> int:
    secret = os.environ.get("DEMO_ACCESS_SECRET", "").strip()
    destination = os.environ.get("DEMO_ACCESS_CODE_OUT", "").strip()
    if not secret or not destination:
        sys.stderr.write("DEMO_ACCESS_SECRET and DEMO_ACCESS_CODE_OUT are required.\n")
        return 2
    ttl = int(os.environ.get("DEMO_ACCESS_TTL_SECONDS", "900") or "900")
    if ttl < 60 or ttl > 3600:
        sys.stderr.write("DEMO_ACCESS_TTL_SECONDS must be between 60 and 3600.\n")
        return 2
    expires_at = int(time.time() * 1000) + ttl * 1000
    code = mint_demo_access(secret, expires_at)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    sys.stdout.write("access code written\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
