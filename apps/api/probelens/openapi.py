import json
import sys
from pathlib import Path

from probelens.main import create_app

if __name__ == "__main__":
    text = json.dumps(create_app().openapi(), indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
