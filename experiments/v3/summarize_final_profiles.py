from pathlib import Path
import json,hashlib
r=Path(__file__).resolve().parents[2]
p=Path('/home/ty/Repos/spectrl-paper/paper')
v=json.loads((p/'analysis/reports/payload-v3.json').read_text())
old=json.loads((r/'experiments/v3/simplification-results.json').read_text())
summary={}
for lossless in (False,True):
    name='lossless' if lossless else 'lossy'
    totals={c:sum(next(t['chars'] for t in row['tokens'] if t['lossless']==lossless and t['compression']==c) for row in v['profiles']) for c in ('raw','zlib','brotli','auto')}
    prior=old['totals']['current-'+name]
    summary[name]={'totals':totals,'previous_default_chars':prior,'zlib_change_pct':100*(totals['zlib']/prior-1),'brotli_saving_vs_zlib_pct':100*(1-totals['brotli']/totals['zlib'])}
summary['exchanges_per_direction']=v['exchanges_per_direction']
summary['n_selected']=len(v['profiles'])
summary['source_report_sha256']=hashlib.sha256((p/'analysis/reports/payload-v3.json').read_bytes()).hexdigest()
(r/'experiments/v3/final-profile-results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
