"""T26: check the submission files against the limits and build the ZIP.

    python scripts/package_submission.py --pitch pitch.pdf --report report.pdf \
        --video demo.mp4 --video-url https://... --out dist/submission

Checks, each printed as PASS / FAIL with the measured value:
- pitch.pdf has at most 10 pages (slides), report.pdf at most 6 pages (counted with pypdf);
- the video is at most 120 s (measured with ffprobe; FAIL if ffprobe is missing, never assumed);
- the live app answers /healthz, /readyz 200 and one real search (skip with --no-live);
- the repository is public (anonymous GitHub API call; skip with --no-live).

Writes `bern-match-submission.zip` with pitch.pdf, report.pdf and README-links.txt, plus a
`manifest.txt` with SHA-256 of every file, and exits 1 if any check failed. The ZIP is built only
when every check passed, unless --force is given (the manifest then says FAILED at the top).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

LIMITS = {"pitch": 10, "report": 6, "video_s": 120}
REPO = "AnAsteria/Apertus_Hack"
APP = "https://kaktamsdengami-bern-match.hf.space"


def pdf_pages(path: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(path)).pages)


def video_seconds(path: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def _get(url: str, data: bytes | None = None, timeout: int = 60):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "bern-match-t26"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def live_checks(app: str) -> list[tuple[str, bool, str]]:
    out = []
    try:
        status, body = _get(app + "/healthz")
        rev = json.loads(body).get("revision")
        out.append(("app /healthz", status == 200, f"{status}, revision {rev}"))
    except Exception as e:  # noqa: BLE001 - every failure is reported, none is fatal here
        out.append(("app /healthz", False, type(e).__name__))
    try:
        status, _ = _get(app + "/readyz")
        out.append(("app /readyz", status == 200, str(status)))
    except Exception as e:  # noqa: BLE001
        out.append(("app /readyz", False, type(e).__name__))
    try:
        q = {"schema_version": "1", "query": "continuous glucose monitoring", "revision": 1, "entity_type": None,
             "company_context": None, "needs": [], "enrichment_requested": False}
        status, body = _get(app + "/api/v1/search", json.dumps(q).encode())
        n = len(json.loads(body)["results"])
        out.append(("app real search", status == 200 and n > 0, f"{n} results"))
    except Exception as e:  # noqa: BLE001
        out.append(("app real search", False, type(e).__name__))
    try:
        status, body = _get(f"https://api.github.com/repos/{REPO}")
        public = status == 200 and json.loads(body).get("private") is False
        out.append(("repository public", public, f"{REPO} visible without login" if public else "not public"))
    except Exception as e:  # noqa: BLE001 - a private repo answers 404 to anonymous calls
        out.append(("repository public", False, f"{REPO} not visible without login ({type(e).__name__})"))
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(pitch: Path, report: Path, video: Path | None, video_url: str, out: Path,
        live: bool = True, force: bool = False, app: str = APP) -> int:
    checks: list[tuple[str, bool, str]] = []
    for name, path in (("pitch", pitch), ("report", report)):
        try:
            n = pdf_pages(path)
            checks.append((f"{name}.pdf pages <= {LIMITS[name]}", n <= LIMITS[name], f"{n} pages"))
        except Exception as e:  # noqa: BLE001 - unreadable PDF is a failed check
            checks.append((f"{name}.pdf pages <= {LIMITS[name]}", False, f"unreadable: {type(e).__name__}"))
    if video is None:
        checks.append(("video <= 120 s", False, "no --video file given"))
    else:
        try:
            s = video_seconds(video)
            checks.append(("video <= 120 s", s is not None and s <= LIMITS["video_s"],
                           "ffprobe not installed: not measured" if s is None else f"{s:.1f} s"))
        except Exception as e:  # noqa: BLE001
            checks.append(("video <= 120 s", False, f"unreadable: {type(e).__name__}"))
    checks.append(("video link given", bool(video_url.startswith("http")), video_url or "missing"))
    if live:
        checks += live_checks(app)

    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {detail}")
    if not ok and not force:
        print("Not packaged: fix the FAIL lines (or pass --force to build a draft ZIP).")
        return 1

    out.mkdir(parents=True, exist_ok=True)
    links = out / "README-links.txt"
    links.write_text(
        f"Repository: https://github.com/{REPO}\nLive app: {app}\nDemo video: {video_url}\n"
        f"Backup video file: {video.name if video else 'none'}\n", encoding="utf-8")
    zpath = out / "bern-match-submission.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(pitch, "pitch.pdf")
        z.write(report, "report.pdf")
        z.write(links, "README-links.txt")
    lines = ["FAILED CHECKS: draft only, do not submit" if not ok else "All checks passed"]
    lines += [f"{'PASS' if p else 'FAIL'}  {n}: {d}" for n, p, d in checks]
    lines += ["", "Files:"] + [f"{sha256(p)}  {p.name}" for p in (pitch, report, links, zpath)]
    (out / "manifest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with zipfile.ZipFile(zpath) as z:
        print(f"wrote {zpath} with {z.namelist()} and manifest.txt")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pitch", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--video", type=Path, help="local video file (the backup copy), measured with ffprobe")
    p.add_argument("--video-url", default="", help="public link to the demo video")
    p.add_argument("--out", type=Path, default=Path("dist/submission"))
    p.add_argument("--app", default=APP)
    p.add_argument("--no-live", action="store_true", help="skip the live app and public repository checks")
    p.add_argument("--force", action="store_true", help="build a draft ZIP even when checks fail")
    a = p.parse_args(argv)
    return run(a.pitch, a.report, a.video, a.video_url, a.out, live=not a.no_live, force=a.force, app=a.app)


if __name__ == "__main__":
    sys.exit(main())
