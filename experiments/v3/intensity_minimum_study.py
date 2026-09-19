"""Prototype positive-intensity grids without changing the released codec."""

from pathlib import Path
import copy
import hashlib
import json
import math
import sys
import warnings

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT.parent / 'spectrl-paper/paper'
sys.path.insert(0, str(PAPER / 'analysis/scripts'))

import cbor2
import numpy as np
from mzmlpy.run import Mzml
from spectrl import from_mzmlpy
from spectrl.cbor_format import frame_payload, read_token_document
from spectrl.codecs.shuffle import shuffle
from spectrl.peaks import canonical_sort
from _datasets import DATASETS, MANIFEST, _ref_groups, encode_all

SCALE = 3600
POLICIES = ('current', 'minimum_bucket', 'positive_log', 'normalized_log1p')


def prototype(x, policy):
    positive = x > 0
    minimum = float(x[positive].min()) if positive.any() else 1.0
    params = {'scale': SCALE, 'log': True}
    if policy == 'positive_log':
        scaled = (np.log(x[positive]) - math.log(minimum)) * SCALE
        q = np.zeros(len(x), dtype=np.uint64)
        q[positive] = 1 + np.floor(scaled + 0.5).astype(np.uint64)
        params = {'scale': SCALE, 'minimum': minimum, 'mapping': 'positive-log'}
    elif policy == 'normalized_log1p':
        # logaddexp avoids overflow in x / minimum.
        scaled = np.logaddexp(0, np.log(x[positive]) - math.log(minimum)) * SCALE
        q = np.zeros(len(x), dtype=np.uint64)
        q[positive] = np.floor(scaled + 0.5).astype(np.uint64)
        params = {'scale': SCALE, 'minimum': minimum, 'mapping': 'normalized-log1p'}
    else:
        q = np.floor(np.log1p(x) * SCALE + 0.5).astype(np.uint64)
        if policy == 'minimum_bucket':
            q[positive] += 1
            params = {'scale': SCALE, 'minimum': minimum, 'mapping': 'minimum-bucket'}
    width = next(w for w in (1, 2, 4, 8) if int(q.max(initial=0)) < 2**(8*w))
    params['width'] = width
    blob = shuffle(q.astype(f'<u{width}').tobytes(), width)
    # Reconstruct from stored words and parameters, without the source mask.
    codes = np.frombuffer(shuffle(blob, width, inverse=True), dtype=f'<u{width}').astype(np.float64)
    recovered = np.zeros(len(codes))
    mask = codes > 0
    if policy == 'positive_log':
        recovered[mask] = np.exp(math.log(minimum) + (codes[mask] - 1) / SCALE)
        recovered[codes == 1] = minimum
    elif policy == 'normalized_log1p':
        t = codes[mask] / SCALE
        recovered[mask] = np.exp(math.log(minimum) + t + np.log1p(-np.exp(-t)))
    elif policy == 'minimum_bucket':
        recovered[mask] = np.expm1((codes[mask] - 1) / SCALE)
        recovered[codes == 1] = minimum
    else:
        recovered = np.expm1(codes / SCALE)
    assert np.isfinite(recovered).all()
    assert np.array_equal(recovered[x == 0], x[x == 0])
    if policy != 'current':
        assert np.all(recovered[positive] > 0)
    return blob, params, recovered


def empty():
    return {'spectra': 0, 'samples': 0, 'positive_samples': 0, 'zero_samples': 0,
            'positive_to_zero': 0, 'max_relative_error_pct': 0.0, 'max_base_peak_error_pct': 0.0}


def measure(x, recovered, result):
    positive = x > 0
    error = np.abs(x - recovered)
    result['spectra'] += 1
    result['samples'] += len(x)
    result['positive_samples'] += int(positive.sum())
    result['zero_samples'] += int((x == 0).sum())
    result['positive_to_zero'] += int(((recovered == 0) & positive).sum())
    result['max_relative_error_pct'] = max(result['max_relative_error_pct'],
        float(np.max(error[positive] / x[positive], initial=0)) * 100)
    result['max_base_peak_error_pct'] = max(result['max_base_peak_error_pct'],
        float(error.max(initial=0) / (x.max(initial=0) or 1)) * 100)


def main():
    report = {'scope': 'Experimental mappings only. Production intensity encoding is unchanged.',
              'size_scope': 'Complete zlib token sizes with proposed core-encoding parameters. These prototype descriptors are not supported production encodings.',
              'full_corpus': {policy: empty() for policy in POLICIES}, 'selected': [], 'source_hashes': {}}
    records = {entry['key']: entry for entry in json.loads(MANIFEST.read_text())['datasets']}
    for dataset in DATASETS:
        digest = hashlib.sha256(dataset.path.read_bytes()).hexdigest()
        assert digest == records[dataset.key]['sha256']
        report['source_hashes'][dataset.key] = digest
        with Mzml(str(dataset.path)) as run:
            refs = _ref_groups(run)
            for spec in run.spectra:
                source = from_mzmlpy(spec, ref_groups=refs, run=run)
                x = np.asarray(source.intensity, dtype=np.float64)
                assert np.isfinite(x).all() and (x >= 0).all()
                for policy in POLICIES:
                    measure(x, prototype(x, policy)[2], report['full_corpus'][policy])
        print(dataset.key, flush=True)
    for row in encode_all():
        doc, _ = read_token_document(row.lossy_token)
        x = canonical_sort(row.source).intensity.astype(np.float64)
        entry = {'dataset': row.dataset.key, 'id': row.spectrum_id, 'chars': {}}
        for policy in POLICIES:
            changed = copy.deepcopy(doc)
            desc = next(d for d in changed[6] if d[1] == 1000515)
            if desc[2][0] == 3:
                blob, params, _ = prototype(x, policy)
                desc[5], desc[2] = blob, [3, 1, params]
            token = frame_payload(cbor2.dumps(changed, canonical=True))
            if policy == 'current':
                assert token == row.lossy_token
            entry['chars'][policy] = len(token)
        report['selected'].append(entry)
    totals = {p: sum(row['chars'][p] for row in report['selected']) for p in POLICIES}
    report['total_chars'] = totals
    report['size_change_pct'] = {p: 100 * (n / totals['current'] - 1) for p,n in totals.items()}
    report['theoretical_positive_log_relative_error_pct'] = 100 * math.expm1(0.5 / SCALE)
    report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (ROOT / 'experiments/v3/intensity-minimum-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'selected','source_hashes'}},indent=2))


if __name__ == '__main__':
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        main()
