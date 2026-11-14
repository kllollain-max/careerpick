import json,sys,re
from pathlib import Path

def validate(d):
 errors=[]
 if d.get('verified') is not True: errors.append('verified must be true after manual official-source review')
 if not isinstance(d.get('source'),str) or not d['source'].strip(): errors.append('official source required')
 cards=d.get('cards',[])
 if not isinstance(cards,list) or not 3<=len(cards)<=8: errors.append('3-8 cards required')
 else:
  for i,c in enumerate(cards,1):
   if not c.get('title') or not c.get('sections'): errors.append(f'card {i}: title and sections required')
   for s in c.get('sections',[]):
    if not s.get('heading') or not s.get('items'): errors.append(f'card {i}: section heading/items required')
 caption=d.get('threads_caption','')
 if caption:
  if re.search(r'https?://|www\\.|[a-zA-Z0-9-]+\\.(?:com|kr|net|org|io)(?:/|\\b)',caption): errors.append('Threads caption URL forbidden')
  if caption.strip().splitlines()[-1]!='자세한 사항은 프로필링크 확인': errors.append('Threads CTA must be exact last line')
 return errors

if __name__=='__main__':
 d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
 errors=validate(d)
 if errors:
  print('\n'.join(errors));sys.exit(1)
 print('Structure and caption checks passed; factual and visual review still required')
