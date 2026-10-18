"""Explicit operator download of pinned upstream assets. Never used by search."""
import json
import shutil
import tempfile
from pathlib import Path
import httpx
from .encoder import digest


def fetch_model(name, destination):
    pins=json.loads(Path(__file__).with_name('models.json').read_text())
    pin=pins[name]
    destination=Path(destination)
    if destination.exists():
        if all((destination/file).is_file() and digest(destination/file)==meta['sha256'] for file,meta in pin['files'].items()):
            return pin
        raise ValueError('model_directory_exists_with_different_assets')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.e5-download-',dir=destination.parent))
    try:
        with httpx.Client(timeout=120,follow_redirects=True) as client:
            for filename,meta in pin['files'].items():
                url=f"https://huggingface.co/{pin['repo']}/resolve/{pin['revision']}/{meta['source_path']}"
                with client.stream('GET',url) as response:
                    response.raise_for_status()
                    size=0
                    with (stage/filename).open('wb') as out:
                        for chunk in response.iter_bytes(1024*1024):
                            size+=len(chunk)
                            if size>meta['bytes']:
                                raise ValueError('model_asset_size_mismatch')
                            out.write(chunk)
                if size!=meta['bytes'] or digest(stage/filename)!=meta['sha256']:
                    raise ValueError('model_asset_hash_mismatch')
        (stage/'model_manifest.json').write_text(json.dumps(pin,indent=2))
        stage.rename(destination)
        return pin
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
