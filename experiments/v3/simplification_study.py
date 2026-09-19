"""Compare small array representations using complete metadata-bearing tokens.

Experimental encoding IDs here are local to the report and are not wire IDs.
Run with the paper analysis environment and this checkout first on PYTHONPATH.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import pickle
import sys
import zlib
from pathlib import Path

import brotli
import cbor2
import numpy as np
import zstandard

ROOT = Path(__file__).resolve().parents[2]
PAPER = Path('/home/ty/Repos/spectrl-paper/paper')
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(PAPER / 'analysis/scripts'))

from _datasets import encode_all
from _study_codecs import LINEAR_FP, SLOF_FP, candidate, numpress_descriptor
from spectrl.cbor_format import read_token_document
from spectrl.codecs.dictionary import shuffle
from spectrl.peaks import canonical_sort
from spectrl.pipeline import decode_pipeline, encode_pipeline

CACHE = Path('/tmp/spectrl-simplification-corpus.pkl')
OUTPUT = ROOT / 'experiments/v3/simplification-results.json'
ZSTD = zstandard.ZstdCompressor(level=3)
COMPRESS = {
    'r': lambda b: b,
    'z': lambda b: zlib.compress(b, 6),
    's': ZSTD.compress,
    'b': lambda b: brotli.compress(b, quality=5),
}


def text_size(data):
    return 22 + (4 * len(data) + 2) // 3


def words(array):
    width = array.dtype.itemsize
    return np.ascontiguousarray(array).view(np.dtype(f'<u{width}'))


def transform(array, method):
    a = words(array)
    if method in ('raw', 'shuffle', 'bitshuffle'):
        b = a.copy()
    elif method in ('delta', 'delta2'):
        b = np.concatenate((a[:1], a[1:] - a[:-1]))
        if method == 'delta2':
            b = np.concatenate((b[:1], b[1:] - b[:-1]))
    elif method == 'xor':
        b = np.concatenate((a[:1], a[1:] ^ a[:-1]))
    else:
        raise ValueError(method)
    raw = b.tobytes()
    if method == 'bitshuffle':
        raw = np.packbits(np.unpackbits(np.frombuffer(raw, dtype=np.uint8)).reshape(len(a), -1).T.flatten()).tobytes() if len(a) else b''
    elif method != 'raw':
        raw = shuffle(raw, a.dtype.itemsize)
    recovered = inverse(raw, len(a), a.dtype, method)
    if recovered.tobytes() != a.tobytes():
        raise AssertionError(f'non-exact {method}')
    return raw


def inverse(raw, count, dtype, method):
    width = dtype.itemsize
    if method == 'bitshuffle':
        raw = np.packbits(np.unpackbits(np.frombuffer(raw, dtype=np.uint8))[:count * width * 8].reshape(width * 8, count).T.flatten()).tobytes() if count else b''
    elif method != 'raw':
        raw = shuffle(raw, width, inverse=True)
    a = np.frombuffer(raw, dtype=dtype)
    if method in ('delta', 'delta2'):
        a = np.cumsum(a, dtype=dtype)
        if method == 'delta2':
            a = np.cumsum(a, dtype=dtype)
    elif method == 'xor':
        a = np.bitwise_xor.accumulate(a)
    return a


def packed_integers(a, method):
    if not len(a):
        return b'', {'width': 1}
    width = next(w for w in (1, 2, 4, 8) if int(a.max()) < 2 ** (w * 8))
    if method in ('shuffle', 'delta', 'delta2', 'bitshuffle'):
        return transform(a.astype(f'<u{width}'), method), {'width': width}
    if method in ('varint-delta', 'varint-delta2'):
        values = [int(x) for x in a]
        d = [values[0]] + [b - a for a, b in zip(values, values[1:])]
        if method == 'varint-delta2':
            d = [d[0]] + [b - a for a, b in zip(d, d[1:])]
        out = bytearray()
        for x in d:
            n = x * 2 if x >= 0 else -x * 2 - 1
            while n >= 128:
                out.append((n & 127) | 128)
                n >>= 7
            out.append(n)
        decoded = []
        acc = shift = 0
        for byte in out:
            acc |= (byte & 127) << shift
            if byte < 128:
                decoded.append((acc >> 1) if acc & 1 == 0 else -(acc >> 1) - 1)
                acc = shift = 0
            else:
                shift += 7
        from itertools import accumulate
        decoded = list(accumulate(decoded))
        if method == 'varint-delta2':
            decoded = list(accumulate(decoded))
        assert decoded == values
        return bytes(out), {}
    raise ValueError(method)


def exact_choice(a, method):
    ids = {'raw': 0, 'shuffle': 1, 'delta': 3, 'delta2': 8, 'xor': 9, 'bitshuffle': 10}
    return {0: {4: 1000521, 8: 1000523}[a.dtype.itemsize] if a.dtype.kind == 'f' else 1000519,
            2: [ids[method], 1], 3: [0, 1], 7: 0, 5: transform(a, method)}


def quantized(a, role, error, method):
    values = a.astype('float64')
    step = 2 * error
    rounded = np.rint(values / step)
    if np.any(rounded < 0) or np.any(rounded > 2**53 - 1) or not np.isfinite(rounded).all():
        raise ValueError('quantizer domain')
    recovered = rounded * step
    observed = float(np.max(np.abs(values - recovered), initial=0))
    if observed > error:
        raise ValueError('quantizer error bound')
    blob, params = packed_integers(rounded.astype('<u8'), method)
    params['step'] = step
    ids = {'shuffle': 11, 'delta': 12, 'delta2': 13, 'bitshuffle': 14, 'varint-delta': 15, 'varint-delta2': 16}
    return {0: 1000523, 2: [ids[method], 1, params], 3: [0, 1], 7: 1, 5: blob}, {
        'max_abs': observed, 'positive_to_zero': int(np.sum((values > 0) & (recovered == 0))),
        'positive_count': int(np.sum(values > 0)),
    }


def rounded_float(a, error, method):
    # Remove a shared number of low mantissa bits, preserving the native width.
    original = words(a)
    chosen = original.copy()
    dropped = 0
    max_bits = 23 if a.dtype.itemsize == 4 else 52
    for k in range(1, max_bits + 1):
        mask = np.array((2 ** (8 * a.dtype.itemsize) - 1) ^ (2**k - 1), dtype=original.dtype)
        trial = (original + np.array(2 ** (k - 1), dtype=original.dtype)) & mask
        recovered = trial.view(a.dtype)
        if not np.isfinite(recovered).all() or np.max(np.abs(recovered.astype('float64') - a.astype('float64')), initial=0) > error:
            break
        chosen, dropped = trial, k
    recovered = chosen.view(a.dtype)
    d = exact_choice(recovered, method)
    # Numeric precision reduction is recorded rather than claiming exact input fidelity.
    d[2] = [17 if method == 'shuffle' else 18, 1, {'bits': dropped}]
    d[7] = 1
    return d, {'max_abs': float(np.max(np.abs(recovered.astype('float64') - a.astype('float64')), initial=0)),
               'positive_to_zero': int(np.sum((a > 0) & (recovered == 0))), 'positive_count': int(np.sum(a > 0))}


def tuned_raw(a, role, error):
    choices = []
    for eid in ([4] if role == 'mz' else [4, 6]):
        floating = 0.5 / error if eid == 4 else 0.5 / math.log1p(error / (float(np.max(a, initial=0)) + 1))
        descriptors = [[LINEAR_FP if eid == 4 else SLOF_FP, 1, {'fp': floating * (1 + 1e-12)}]]
        for bound in (error, None):
            try:
                descriptors.append(numpress_descriptor(eid, a, bound))
            except ValueError:
                pass
        for enc in descriptors:
            try:
                item, blob = candidate(a, role, enc, [0, 1])
                if item['errors']['max_abs'] <= error:
                    choices.append((item, blob))
            except ValueError:
                pass
    return choices


def assembled(doc, choices, outer='z', inner=False, omit_compression=False):
    result = copy.deepcopy(doc)
    for desc, choice in zip(result[6], choices, strict=True):
        desc.update(choice)
        if inner:
            desc[5] = zlib.compress(desc[5], 6)
            desc[3] = [1, 1]
        elif omit_compression:
            desc.pop(3, None)
    raw = cbor2.dumps(result, canonical=True)
    return text_size(COMPRESS[outer](raw)), len(raw)


def main():
    if CACHE.exists():
        rows = pickle.loads(CACHE.read_bytes())
    else:
        rows = encode_all()
        CACHE.write_bytes(pickle.dumps(rows))
    print(f'Loaded {len(rows)} selected spectra', flush=True)
    output = {'settings': {'outer': {'zlib': 6, 'zstd': 3, 'brotli': 5}, 'mz_error': 1e-5, 'intensity_base_peak_fraction': 1e-4},
              'spectra': [], 'inputs': {}}
    for path in [Path(__file__), PAPER / 'analysis/data/corpus.json']:
        output['inputs'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    totals = {}
    if OUTPUT.exists():
        output = json.loads(OUTPUT.read_text())
        totals = output.get('totals', {})
        print(f'Resuming after {len(output["spectra"])} spectra', flush=True)
    for index, row in enumerate(rows):
        if index < len(output['spectra']):
            continue
        source = canonical_sort(row.source)
        doc, _ = read_token_document(row.lossless_token)
        arrays = [getattr(source, {1000514: 'mz', 1000515: 'intensity', 1000516: 'charge'}[d[1]])
                  if d[1] in (1000514, 1000515, 1000516) else source.extra_arrays[d.get(4, f'MS:{d[1]:07d}')] for d in doc[6]]
        roles = ['mz' if d[1] == 1000514 else 'intensity' if d[1] == 1000515 else 'other' for d in doc[6]]
        values = {'dataset': row.dataset.key, 'id': row.spectrum_id, 'points': row.n_peaks,
                  'representation': row.representation, 'ms_level': row.ms_level, 'sizes': {}, 'arrays': []}
        # Keep the same selected transforms to isolate removing the inner compressor.
        for profile, token in [('lossless', row.lossless_token), ('lossy', row.lossy_token)]:
            old_doc, _ = read_token_document(token)
            transformed = []
            for desc in old_doc[6]:
                recovered = decode_pipeline(desc[5], desc[0], row.n_peaks, desc[2], desc[3], desc[7])
                blob, _ = encode_pipeline(recovered, desc[0], desc[2], [0, 1])
                # Decode/re-encode Numpress must preserve the encoded numeric output.
                check = decode_pipeline(blob, desc[0], row.n_peaks, desc[2], [0, 1], desc[7])
                assert check.tobytes() == recovered.tobytes()
                transformed.append({**desc, 3: [0, 1], 5: blob})
            values['sizes'][f'current-{profile}'] = len(token)
            values['sizes'][f'same-{profile}-outer-only'] = assembled(old_doc, transformed)[0]
            values['sizes'][f'same-{profile}-outer-only-minimal'] = assembled(old_doc, transformed, omit_compression=True)[0]
            values['sizes'][f'same-{profile}-inner-zlib'] = assembled(old_doc, transformed, inner=True)[0]
        exact = [{m: exact_choice(a, m) for m in ('raw', 'shuffle', 'delta', 'delta2', 'xor', 'bitshuffle')} for a in arrays]
        policies = {}
        for mz_method in ('raw', 'shuffle', 'delta', 'delta2', 'xor', 'bitshuffle'):
            for int_method in ('raw', 'shuffle', 'bitshuffle'):
                label = f'exact-{mz_method}-{int_method}'
                choices = [opts[mz_method if role == 'mz' else int_method if role == 'intensity' else 'raw'] for role, opts in zip(roles, exact)]
                policies[label] = choices
                values['sizes'][label], raw_size = assembled(doc, choices)
                values['max_cbor_bytes'] = max(values.get('max_cbor_bytes', 0), raw_size)
        lossy = []
        for a, role, exact_opts in zip(arrays, roles, exact):
            error = 1e-5 if role == 'mz' else float(np.max(np.abs(a), initial=0)) * 1e-4
            options = {'exact': exact_opts['delta' if role == 'mz' else 'shuffle']}
            metrics = {}
            if role in ('mz', 'intensity') and error > 0:
                for method in ('shuffle', 'delta', 'delta2', 'bitshuffle', 'varint-delta', 'varint-delta2'):
                    try:
                        options[method], metrics[method] = quantized(a, role, error, method)
                    except ValueError:
                        options[method] = options['exact']
                if a.dtype.kind == 'f':
                    for method in ('shuffle', 'delta'):
                        options['float-' + method], metrics['float-' + method] = rounded_float(a, error, method)
                tuned = tuned_raw(a, role, error)
                if tuned:
                    item, blob = min(tuned, key=lambda x: len(zlib.compress(x[1], 6)))
                    options['numpress'] = {0: item['dtype'], 2: item['encoding'], 3: [0, 1], 5: blob, 7: 1}
                    metrics['numpress'] = item['errors']
                else:
                    options['numpress'] = options['exact']
            values['arrays'].append({'role': role, 'dtype': str(a.dtype), 'error_bound': error,
                                     'payload_zlib': {k: len(zlib.compress(v[5], 6)) for k, v in options.items()}, 'errors': metrics})
            lossy.append(options)
        for mz_method in ('numpress', 'delta', 'delta2', 'varint-delta', 'varint-delta2', 'float-delta'):
            for int_method in ('numpress', 'shuffle', 'bitshuffle', 'float-shuffle'):
                label = f'lossy-{mz_method}-{int_method}'
                choices = [opts.get(mz_method if role == 'mz' else int_method, opts['exact']) if role != 'other' else opts['exact'] for role, opts in zip(roles, lossy)]
                policies[label] = choices
                values['sizes'][label] = assembled(doc, choices)[0]
        for label in ('exact-delta-shuffle', 'exact-delta-raw', 'lossy-numpress-numpress', 'lossy-delta-shuffle'):
            for outer in ('r', 's', 'b'):
                values['sizes'][f'{label}-{outer}'] = assembled(doc, policies[label], outer)[0]
        for key, size in values['sizes'].items():
            totals[key] = totals.get(key, 0) + size
        output['spectra'].append(values)
        output['totals'] = dict(sorted(totals.items(), key=lambda x: x[1]))
        OUTPUT.write_text(json.dumps(output, indent=2) + '\n')
        if index % 20 == 0:
            print(f'{index + 1}/{len(rows)} spectra complete', flush=True)
    output['totals'] = dict(sorted(totals.items(), key=lambda x: x[1]))
    OUTPUT.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output['totals'], indent=2), flush=True)


if __name__ == '__main__':
    main()
