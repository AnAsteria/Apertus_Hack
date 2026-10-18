"""Package one immutable generation for Space, without raw corpus or other models."""
import io
import json
import tarfile
from pathlib import Path
from app.storage.indexes import current_generation
from .encoder import digest


def package_bundle(data_dir, output):
    current=current_generation(data_dir)
    if current is None:
        raise ValueError('no_ready_generation')
    directory,manifest=current
    for filename,asset in manifest['assets'].items():
        if digest(directory/filename)!=asset['sha256']:
            raise ValueError('index_asset_hash_mismatch')
    output=Path(output)
    marker=json.dumps({'generation':directory.name,'fingerprint':manifest['fingerprint']}).encode()
    with tarfile.open(output,'w:gz',dereference=False) as archive:
        archive.add(directory,arcname='indexes/'+directory.name)
        ready=tarfile.TarInfo('READY'); ready.size=len(marker)
        archive.addfile(ready,io.BytesIO(marker))
        # T12's read-only evidence route uses this compatible DB. A relative
        # archive link avoids duplicating it or replacing an operator's corpus.
        evidence=tarfile.TarInfo('corpus.sqlite'); evidence.type=tarfile.SYMTYPE
        evidence.linkname='indexes/'+directory.name+'/search.sqlite'
        archive.addfile(evidence)
    return {'generation':directory.name,'archive_bytes':output.stat().st_size,'archive_sha256':digest(output),
            'generation_bytes':sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),
            'assets':manifest['assets'],'counts':manifest['counts']}
