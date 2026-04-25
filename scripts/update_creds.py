#!/usr/bin/env python3
"""Update credentials.json with an API key for a given provider.

Reads configuration from environment variables to avoid passing secrets
as command-line arguments (which are visible in process listings).

Required env vars:
    CREDS_FILE  -- path to credentials.json
    PROVIDER    -- provider key (e.g. "grok", "openai")
    MODEL       -- model identifier

The API key is read from stdin (one line) so it never appears in the
process environment or argument list.
"""

import json
import os
import sys


def main():
    creds_path = os.environ.get("CREDS_FILE")
    provider = os.environ.get("PROVIDER")
    model = os.environ.get("MODEL")

    if not all([creds_path, provider, model]):
        print("Error: CREDS_FILE, PROVIDER, and MODEL env vars are required.", file=sys.stderr)
        sys.exit(1)

    api_key = sys.stdin.readline().rstrip("\n")
    if not api_key:
        print("Error: no API key provided on stdin.", file=sys.stderr)
        sys.exit(1)

    with open(creds_path, "r") as f:
        creds = json.load(f)

    creds.setdefault(provider, {})
    creds[provider]["api_key"] = api_key
    creds[provider]["model"] = model
    creds[provider]["enabled"] = True

    with open(creds_path, "w") as f:
        json.dump(creds, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
