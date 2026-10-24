"""Write SHA-256 checksums for release distributions and locked runtime inputs."""
import hashlib
from pathlib import Path

paths = sorted([*Path("dist").glob("*.whl"), *Path("dist").glob("*.tar.gz"), Path("dist/requirements-runtime.txt")])
Path("dist/SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in paths))
