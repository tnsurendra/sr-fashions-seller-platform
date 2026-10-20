
"""Development only: write an ignored environment file, never print private keys."""
import argparse
import os
from pathlib import Path
from app.ondc.signing.crypto import generate_keys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".ondc-keys/.env"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private, public = generate_keys()
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(f"ONDC_SIGNING_PRIVATE_KEY={private}\nONDC_SIGNING_PUBLIC_KEY={public}\n")
    print(f"Development key file written: {args.output}; protect its access permissions.")

if __name__ == "__main__":
    main()
