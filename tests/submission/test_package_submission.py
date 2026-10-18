"""T26: the packaging script enforces the page limits and never packages a failing set."""
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import package_submission as ps


def _pdf(path, pages):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)
    return path


@pytest.fixture
def video(tmp_path, monkeypatch):
    v = tmp_path / "demo.mp4"; v.write_bytes(b"x")
    monkeypatch.setattr(ps, "video_seconds", lambda p: 115.0)
    return v


def test_valid_set_is_packaged_with_manifest(tmp_path, video):
    out = tmp_path / "out"
    rc = ps.run(_pdf(tmp_path / "p.pdf", 10), _pdf(tmp_path / "r.pdf", 6), video, "https://video.example", out, live=False)
    assert rc == 0
    with zipfile.ZipFile(out / "bern-match-submission.zip") as z:
        assert sorted(z.namelist()) == ["README-links.txt", "pitch.pdf", "report.pdf"]
    assert (out / "manifest.txt").read_text(encoding="utf-8").startswith("All checks passed")


def test_too_many_pages_or_too_long_video_is_not_packaged(tmp_path, video, monkeypatch, capsys):
    out = tmp_path / "out"
    assert ps.run(_pdf(tmp_path / "p.pdf", 11), _pdf(tmp_path / "r.pdf", 6), video, "https://v", out, live=False) == 1
    assert "FAIL  pitch.pdf pages <= 10: 11 pages" in capsys.readouterr().out
    assert not out.exists()
    monkeypatch.setattr(ps, "video_seconds", lambda p: 121.0)
    assert ps.run(_pdf(tmp_path / "p2.pdf", 9), _pdf(tmp_path / "r2.pdf", 7), video, "https://v", out, live=False) == 1
    text = capsys.readouterr().out
    assert "FAIL  report.pdf pages <= 6: 7 pages" in text and "FAIL  video <= 120 s: 121.0 s" in text


def test_unmeasured_video_fails_and_force_marks_the_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "video_seconds", lambda p: None)  # ffprobe missing
    v = tmp_path / "demo.mp4"; v.write_bytes(b"x")
    out = tmp_path / "out"
    rc = ps.run(_pdf(tmp_path / "p.pdf", 3), _pdf(tmp_path / "r.pdf", 3), v, "", out, live=False, force=True)
    assert rc == 1
    manifest = (out / "manifest.txt").read_text(encoding="utf-8")
    assert manifest.startswith("FAILED CHECKS") and "not measured" in manifest and "video link given: missing" in manifest
