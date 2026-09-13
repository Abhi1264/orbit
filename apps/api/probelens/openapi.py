"""Dump the OpenAPI document. The web app generates its TypeScript API types from this."""

import json
import sys

from probelens.main import create_app

if __name__ == "__main__":
    json.dump(create_app().openapi(), sys.stdout, indent=2)
