"""Prospective public reproduction identities, without private supervisor claims.

The request pins available source, executable and runtime bytes. It neither
launches a process nor proves that a caller used any resource supervisor.
"""
import argparse
from importlib import metadata
from pathlib import Path
import platform
import re
import sys

from measurements import ROOT, checked_json, encoded, sha, source_identity, staged, write_new


def runtime_identity():
    packages = {}
    for name in ('numpy', 'scipy', 'matplotlib', 'contourpy', 'cycler', 'fonttools',
                 'kiwisolver', 'pillow', 'pyparsing', 'packaging', 'python-dateutil', 'six'):
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if name in ('numpy', 'scipy'):
                raise ValueError('required runtime package missing: ' + name)
            continue
        files = {}
        for entry in sorted(distribution.files or [], key=str):
            # Bytecode is machine-local, regenerated state rather than package source.
            if str(entry).endswith(('.pyc', '.pyo')):
                continue
            path = Path(distribution.locate_file(entry))
            if not path.is_file():
                raise ValueError('runtime package file missing: ' + name)
            files[str(entry)] = sha(path.read_bytes())
        if not files:
            raise ValueError('runtime package inventory unavailable: ' + name)
        packages[name] = {'version': distribution.version, 'files_sha256': sha(encoded(files))}
    return {'python_version': platform.python_version(),
            'python_sha256': sha(Path(sys.executable).resolve().read_bytes()),
            'implementation': platform.python_implementation(),
            'platform': platform.platform(), 'packages': packages}


def prepare_request(binary, root=ROOT):
    return {'schema_version': 1, 'execution_kind': 'public_reproduction',
            'source': source_identity(root), 'binary_sha256': sha(Path(binary).read_bytes()),
            'runtime': runtime_identity()}


def validate_schema(request):
    if (not isinstance(request, dict) or set(request) != {'schema_version', 'execution_kind', 'source', 'binary_sha256', 'runtime'}
            or type(request['schema_version']) is not int or request['schema_version'] != 1
            or request['execution_kind'] != 'public_reproduction'
            or not isinstance(request['binary_sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', request['binary_sha256'])):
        raise ValueError('invalid public reproduction request schema')
    return request


def validate_request(path, binary=None, root=ROOT):
    request = validate_schema(checked_json(Path(path).read_bytes()))
    if request['source'] != source_identity(root) or request['runtime'] != runtime_identity():
        raise ValueError('public reproduction source/runtime identity drift')
    if binary is not None and request['binary_sha256'] != sha(Path(binary).read_bytes()):
        raise ValueError('public reproduction binary identity drift')
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    write_new(staged(args.output), prepare_request(args.binary))


if __name__ == '__main__':
    main()
