"""Allow ``python -m iot_trustbench`` to behave like the CLI."""

import sys

from iot_trustbench.cli import main

if __name__ == "__main__":
    sys.exit(main())
