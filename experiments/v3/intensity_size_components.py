from pathlib import Path
import sys,copy,json,warnings
sys.path.insert(0, str(Path(__file__).resolve().parent))
import intensity_minimum_study as study
import cbor2
from spectrl.cbor_format import frame_payload,read_token_document
from spectrl.peaks import canonical_sort
from collections import Counter
out={'baseline_chars':0,'metadata_only_chars':0,'full_prototype_chars':0,'baseline_array_bytes':0,'prototype_array_bytes':0,'width_transitions':Counter()}
with warnings.catch_warnings():
 warnings.simplefilter('ignore')
 for row in study.encode_all():
  doc,_=read_token_document(row.lossy_token)
  desc=next(d for d in doc[6] if d[1]==1000515)
  if desc[2][0] !=3: raise ValueError('unexpected exact intensity')
  x=canonical_sort(row.source).intensity.astype('float64')
  blob,params,_=study.prototype(x,'positive_log')
  out['baseline_chars']+=len(row.lossy_token)
  out['baseline_array_bytes']+=len(desc[5])
  out['prototype_array_bytes']+=len(blob)
  out['width_transitions'][str(desc[2][2]['width'])+' to '+str(params['width'])]+=1
  desc[2]=[3,1,params]
  out['metadata_only_chars']+=len(frame_payload(cbor2.dumps(doc,canonical=True)))
  desc[5]=blob
  out['full_prototype_chars']+=len(frame_payload(cbor2.dumps(doc,canonical=True)))
out['additional_chars_metadata']=out['metadata_only_chars']-out['baseline_chars']
out['additional_chars_words_given_metadata']=out['full_prototype_chars']-out['metadata_only_chars']
out['scope']='Counterfactual size accounting only. Metadata-only documents deliberately retain the old words and are not valid numerical encodings.'
p=Path(__file__).with_name('intensity-size-components.json')
p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
