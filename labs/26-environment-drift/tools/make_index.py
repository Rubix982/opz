"""Builds the lab's private package index: what "PyPI" offered on each date.

    python3 tools/make_index.py                  (setup.sh runs this)
    python3 tools/make_index.py --tamper DIR     (check.sh: a compromised mirror)

Two small libraries the training code depends on, and their release history:

    featurekit 1.4.0  (2026-08)   standardize()
    featurekit 2.0.0  (2026-10)   standardize() renamed to scale()       <- breaking
    featurekit 2.1.0  (2026-11)   adds minmax()
    tinymath   1.0.0  (2026-07)   round_to(x, digits=2)
    tinymath   1.1.0  (2026-10)   round_to default changed to digits=3   <- silent
    tinymath   1.2.0  (2026-11)   adds clamp()

featurekit depends on tinymath, so tinymath is an *indirect* dependency.

Wheels are built byte-for-byte reproducibly (fixed timestamps, sorted entries),
so their hashes never change between runs or machines.
"""

import base64
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "index"

TINYMATH = {
    "1.0.0": 'def round_to(x, digits=2):\n    return round(x, digits)\n',
    "1.1.0": 'def round_to(x, digits=3):  # more precision by default!\n    return round(x, digits)\n',
    "1.2.0": 'def round_to(x, digits=3):\n    return round(x, digits)\n\n\ndef clamp(x, lo, hi):\n    return max(lo, min(hi, x))\n',
}
_STD = '''from statistics import fmean, pstdev

from tinymath import round_to


def {name}(values):
    """Center and scale a column to mean 0, standard deviation 1."""
    mean, sd = fmean(values), pstdev(values)
    return [round_to((v - mean) / sd) for v in values]
'''
FEATUREKIT = {
    "1.4.0": (_STD.format(name="standardize"), "tinymath>=1.0"),
    "2.0.0": (_STD.format(name="scale"), "tinymath>=1.1"),
    "2.1.0": (_STD.format(name="scale") + '\n\ndef minmax(values):\n    lo, hi = min(values), max(values)\n    return [(v - lo) / (hi - lo) for v in values]\n', "tinymath>=1.1"),
}
# What had been released by each date.
SNAPSHOTS = {
    "2026-09-20": [("tinymath", "1.0.0"), ("featurekit", "1.4.0")],                 # the laptop was set up
    "2026-10-25": [("tinymath", "1.0.0"), ("tinymath", "1.1.0"),
                   ("featurekit", "1.4.0"), ("featurekit", "2.0.0")],               # today
    "2026-11-01": [("tinymath", "1.0.0"), ("tinymath", "1.1.0"), ("tinymath", "1.2.0"),
                   ("featurekit", "1.4.0"), ("featurekit", "2.0.0"), ("featurekit", "2.1.0")],  # next week
}


def wheel(name: str, version: str, code: str, requires: str | None) -> tuple[str, bytes]:
    dist = f"{name}-{version}.dist-info"
    meta = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    if requires:
        meta += f"Requires-Dist: {requires}\n"
    files = {
        f"{name}/__init__.py": code,
        f"{dist}/METADATA": meta,
        f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: opz-lab26\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = []
    for path, text in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(text.encode())}")
    files[f"{dist}/RECORD"] = "\n".join(record + [f"{dist}/RECORD,,"]) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[path])
    return f"{name}-{version}-py3-none-any.whl", buf.getvalue()


def build(name: str, version: str) -> tuple[str, bytes]:
    if name == "tinymath":
        return wheel(name, version, TINYMATH[version], None)
    code, req = FEATUREKIT[version]
    return wheel(name, version, code, req)


def tamper(directory: Path) -> None:
    """Replaces every wheel in DIR with one of the same name and version whose
    code does something extra, like a compromised mirror or a hijacked release."""
    for whl in directory.glob("*.whl"):
        name, version = whl.name.split("-")[:2]
        filename, _ = build(name, version)
        if name == "tinymath":
            code, req = TINYMATH[version], None
        else:
            code, req = FEATUREKIT[version]
        code += "\n\nimport os as _os  # injected: phones home on import\n_os.environ.setdefault('PWNED', '1')\n"
        _, data = wheel(name, version, code, req)
        whl.write_bytes(data)


def main() -> None:
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--tamper":
        tamper(Path(sys.argv[2]))
        return
    for date, releases in SNAPSHOTS.items():
        d = ROOT / date
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.whl"):
            old.unlink()
        for name, version in releases:
            filename, data = build(name, version)
            (d / filename).write_bytes(data)
    print(f"index ready: {', '.join(SNAPSHOTS)} under {ROOT.name}/")


if __name__ == "__main__":
    main()
