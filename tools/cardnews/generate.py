import json,sys,zipfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W,H=1080,1350
NAVY='#102B55';BLUE='#2363A0';PALE='#EAF3FB'
def font(size):
 for p in ['/usr/share/fonts/truetype/nanum/NanumSquareB.ttf','/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc']:
  if Path(p).exists():return ImageFont.truetype(p,size)
 raise RuntimeError('Install NanumSquare or Noto CJK font locally')
def wrap(draw,value,x,y,width,size=34,limit=10):
 f=font(size);lines=[]
 for paragraph in str(value).split('\\n'):
  line=''
  for char in paragraph:
   if line and draw.textbbox((0,0),line+char,font=f)[2]>width:
    lines.append(line);line=char
   else:line+=char
  lines.append(line)
 if len(lines)>limit:raise ValueError('Text overflow: split this card into more cards')
 for line in lines:draw.text((x,y),line,font=f,fill='#20242B');y+=size+13
 return y

def render(card,i,n,brand):
 im=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(im)
 d.rectangle((0,0,W,18),fill=NAVY)
 d.text((65,65),brand,font=font(32),fill=NAVY)
 d.text((925,65),f'{i}/{n}',font=font(28),fill=BLUE)
 y=wrap(d,card['title'],65,160,940,60,2)+20
 y=wrap(d,card.get('subtitle',''),65,y,940,28,3)+30
 for section in card['sections']:
  if y>1100:raise ValueError(f'Card {i} overflows')
  d.rounded_rectangle((55,y,1025,y+56),radius=12,fill=PALE)
  d.text((75,y+10),section['heading'],font=font(31),fill=NAVY);y+=77
  for item in section['items']:y=wrap(d,'• '+str(item),82,y,905,31,4)+8
  y+=18
 if y>1220:raise ValueError(f'Card {i} content overlaps footer')
 d.line((65,1240,1015,1240),fill='#CAD7E6',width=2)
 d.text((65,1260),'공식 공고 기준 · 세부사항은 원문 확인',font=font(23),fill=BLUE)
 return im

def main():
 if len(sys.argv)!=3:raise SystemExit('Usage: python generate.py verified.json output_dir')
 from validate import validate
 src=Path(sys.argv[1]);data=json.loads(src.read_text(encoding='utf-8'))
 errors=validate(data)
 if errors:raise ValueError('; '.join(errors))
 out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
 names=[]
 for i,c in enumerate(data['cards'],1):
  name=f'card_{i:02}.png';render(c,i,len(data['cards']),data.get('brand','CAREERPICK | 커리어픽')).save(out/name);names.append(name)
 (out/'source.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'captions.txt').write_text(data.get('instagram_caption','')+'\\n\\n--- Threads ---\\n'+data.get('threads_caption',''),encoding='utf-8')
 with zipfile.ZipFile(out/'cardnews.zip','w',zipfile.ZIP_DEFLATED) as z:
  for name in names+['source.json','captions.txt']:z.write(out/name,name)
 print('Generated',len(names),'cards. Manual visual/factual review required.')
if __name__=='__main__':main()
