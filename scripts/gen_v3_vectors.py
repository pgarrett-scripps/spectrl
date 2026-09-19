"""Generate v3 transform, native dtype, and context conformance examples."""
import json
from pathlib import Path

import numpy as np

from spectrl import InlineSpectrum, encode_spectrum
from spectrl.cbor_format import read_token_document
from spectrl.model import SpectrlCvParam, SpectrlScan, SpectrlScanWindow, SpectrlUserParam


def metadata(value):
    if isinstance(value, bytes):
        return '<bytes>'
    if isinstance(value, dict):
        return {str(k): metadata(v) for k, v in value.items()}
    if isinstance(value, list):
        return [metadata(v) for v in value]
    return value


def generate():
    vectors = []
    params = [SpectrlCvParam('MS:1000511', '2'), SpectrlCvParam('MS:1000511', '3')]
    users = [SpectrlUserParam('nested', 'kept')]
    for dtype in ['float32', 'float64', 'int32']:
        for encoding in [0, 1, 2]:
            a = np.array([0, 0, 1, 2, 2, 65536], dtype=dtype)
            if dtype.startswith('float'):
                a[0] = -0.0
            source = InlineSpectrum(len(a), mz=a, intensity=a.copy(),
                params=params, scans=[SpectrlScan(windows=[SpectrlScanWindow(params=params, user_params=users)])],
                source={'name': 'run.raw', 'spectrum_ref': 'scan=1'},
                acquisition={'instrument': {'id': 'IC1', 'components': [{'kind': 'analyzer', 'order': 1}]}},
                processing=[{'software': {'name': 'example', 'version': '1'}, 'params': params}],
                array_params={'mz': params}, array_user_params={'intensity': users},
                extensions={'example:note': {'revision': 1, 'required': False, 'data': {'label': 'x'}}})
            setting = {'encoding': encoding}
            token = encode_spectrum(source, lossless=True, array_encodings={'mz': setting, 'intensity': setting})
            doc, _ = read_token_document(token)
            vectors.append({'name': f'{dtype}-{encoding}', 'token': token,
                'dtype': dtype, 'hex': a.tobytes().hex(), 'metadata': metadata(doc)})
    return {'format': 'spectrl-v3-pipelines', 'vectors': vectors}


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'test-vectors/v3-pipelines.json'
    path.write_text(json.dumps(generate(), indent=2) + '\n')
    print(f'Wrote {path}')
