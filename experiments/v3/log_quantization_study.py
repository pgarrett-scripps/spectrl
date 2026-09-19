"""Compare a shared quantized-word encoding at the current default precision."""

import json
import pickle

import numpy as np

from simplification_study import CACHE, ROOT, assembled, exact_choice, packed_integers, read_token_document, words
from spectrl.codecs.numpress import _safe_slof_fp
from spectrl.peaks import canonical_sort


def encode(a, role, packing, intensity_policy):
    x = a.astype('float64')
    fp = 100000 if role == 'mz' else _safe_slof_fp(x, 3600)
    logged = role == 'intensity' and intensity_policy == 'log'
    if logged:
        scaled = np.log1p(x) * fp
    elif role == 'intensity':
        # Hybrid absolute bound near zero, proportional bound for larger values.
        # Here use the same logarithmic grid with finer precision to compare cost.
        fp = 10000
        logged = True
        scaled = np.log1p(x) * fp
    else:
        scaled = x * fp
    if np.any(scaled < 0) or np.any(scaled > 2**53 - 1):
        return exact_choice(a, 'delta' if role == 'mz' else 'shuffle'), None
    q = np.floor(scaled + 0.5).astype('<u8')
    y = np.expm1(q.astype('float64') / fp) if logged else q.astype('float64') / fp
    blob, params = packed_integers(q, packing)
    params.update({'fp': fp, 'log': logged})
    d = {0: 1000523, 2: [7, 1, params], 3: [0, 1], 5: blob, 7: 1}
    return d, {'max_abs': float(np.max(np.abs(x-y),initial=0)), 'max_base_peak_fraction': float(np.max(np.abs(x-y),initial=0)/(np.max(x,initial=0) or 1)),
               'positive_to_zero': int(np.sum((x>0)&(y==0))), 'positives': int(np.sum(x>0))}


def main():
    rows = pickle.loads(CACHE.read_bytes())
    report = {'spectra': [], 'totals': {}}
    for i,row in enumerate(rows):
        source = canonical_sort(row.source)
        doc,_ = read_token_document(row.lossless_token)
        entry = {'dataset':row.dataset.key,'id':row.spectrum_id,'sizes':{},'errors':{}}
        for mzpacking in ('delta','delta2','varint-delta2'):
            for intpacking in ('shuffle','bitshuffle','delta'):
                for policy in ('log','finer-log'):
                    choices=[]
                    for desc in doc[6]:
                        role = {1000514:'mz',1000515:'intensity',1000516:'charge'}.get(desc[1])
                        a=getattr(source,role) if role else source.extra_arrays[desc.get(4,f'MS:{desc[1]:07d}')]
                        if role in ('mz','intensity'):
                            d,errors=encode(a,role,mzpacking if role=='mz' else intpacking,policy)
                            entry['errors'][role+'-'+policy]=errors
                        else:
                            d=exact_choice(a,'raw')
                        choices.append(d)
                    label=f'{mzpacking}-{intpacking}-{policy}'
                    size,raw_bytes=assembled(doc,choices,omit_compression=True)
                    entry['sizes'][label]=size
                    report['totals'][label]=report['totals'].get(label,0)+size
                    if label=='delta-shuffle-log':
                        for outer in ('s','b'):
                            size,_=assembled(doc,choices,outer=outer,omit_compression=True)
                            entry['sizes'][label+'-'+outer]=size
                            report['totals'][label+'-'+outer]=report['totals'].get(label+'-'+outer,0)+size
        report['spectra'].append(entry)
        if i%40==0:
            print(i+1,len(rows),flush=True)
    (ROOT/'experiments/v3/log-quantization-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(sorted(report['totals'].items(),key=lambda x:x[1])),indent=2),flush=True)


if __name__=='__main__':
    main()
