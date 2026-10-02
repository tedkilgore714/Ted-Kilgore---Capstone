"""One-off check that the Composio API key in .env is valid."""

import os

from composio import Composio


def _load_dotenv(path: str) -> None:
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    _load_dotenv(os.path.join(os.path.dirname(__file__), "..", "aijobscout.env"))

    client = Composio(api_key=os.environ["COMPOSIO_API_KEY"])
    toolkits = client.toolkits.list()
    print(f"Connected. {len(toolkits.items)} toolkits available, e.g.:")
    for toolkit in toolkits.items[:5]:
        print(f"  - {toolkit.slug}")
