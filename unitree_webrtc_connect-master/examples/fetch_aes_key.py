"""
Thin shim around `unitree_webrtc_connect._cli`. Lets you run the CLI
straight from a fresh checkout:

    python examples/fetch_aes_key.py --email you@example.com --password ...

When the package is installed (e.g. `pip install unitree_webrtc_connect`)
the same CLI is exposed as the `unitree-fetch-aes-key` console script:

    unitree-fetch-aes-key --email you@example.com --password ...
    unitree-fetch-aes-key --sn B42D2000XXXXXXXX --token <tok>
"""

import os
import sys

# Prefer the local checkout over any pip-installed copy.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_REPO_ROOT, "unitree_webrtc_connect")):
    sys.path.insert(0, _REPO_ROOT)

from unitree_webrtc_connect._cli import main

if __name__ == "__main__":
    sys.exit(main())
