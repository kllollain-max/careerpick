"""Build a private offline placement mock from the existing six guide bodies.

This never loads an advertising provider or grants content review approval.
The output is outside the public deployment allowlist.
"""
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = [
    'application-checklist.html', 'qualification-preference-guide.html',
    'recruitment-corrections-guide.html', 'self-introduction-star.html',
    'ncs-study-plan.html', 'after-application-checklist.html',
]
MOCK = ('<aside class="cp-ad-mock" data-placement-preview aria-label="광고 자리표시자">'
        '<strong>광고 자리 검토용</strong><br>실제 광고 요청 없음 · 운영자 콘텐츠 검토 대기</aside>')
CHILD_STYLE = '''<style>
.cp-ad-mock{margin:48px 0;padding:20px;min-height:100px;display:block;border:1px dashed #8291ad;
background:#f5f7fb;text-align:center;color:#56657e;font:13px/1.8 system-ui,sans-serif}
.cp-ad-mock strong{font-weight:650}a{cursor:default}body{overflow-wrap:anywhere}
</style>'''
CSP = "default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'"


def guide_data():
    result = []
    for name in GUIDES:
        raw = (ROOT / 'guides' / name).read_text(encoding='utf-8')
        heading = re.search(r'<h1\b[^>]*>(.*?)</h1>', raw, re.S)
        marker = '<h2>공식 자료와 적용 범위</h2>'
        if not heading or raw.count(marker) != 1:
            raise ValueError('Guide structure changed: ' + name)
        if re.search(r'<(?:script|iframe)\b|<[^>]+\bon\w+\s*=', raw, re.I):
            raise ValueError('Executable guide markup is not allowed in this mock')
        # Review frames are read-only copies; actual site links are preserved in source.
        raw = re.sub(r'\s+href=([\"\']).*?\1', '', raw, flags=re.S)
        raw = raw.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="' + html.escape(CSP, quote=True) + '">', 1)
        raw = raw.replace('</head>', CHILD_STYLE + '</head>', 1)
        result.append({
            'path': 'guides/' + name,
            'title': html.unescape(re.sub('<[^>]+>', '', heading[1])),
            'source_sha256': hashlib.sha256((ROOT / 'guides' / name).read_bytes()).hexdigest(),
            'html': raw.replace(marker, MOCK + marker, 1),
        })
    return result


def main():
    data = guide_data()
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    shell = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self' about:; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>커리어픽 · 가이드와 광고 배치 검토</title>
<style>*{box-sizing:border-box}body{margin:0;background:#edf1f7;color:#14213d;font:15px/1.7 system-ui,'Malgun Gothic',sans-serif;overflow-wrap:anywhere}
header,.controls,.summary,.devices{max-width:1120px;margin:auto;padding:20px}header{padding-top:32px}h1{font-size:26px;line-height:1.4;margin:8px 0}h2{font-size:18px}p{margin:8px 0}
.eyebrow{font-weight:750;color:#3757a4}.note{border-left:4px solid #b17a12;background:#fff5de;padding:14px}
.controls{display:grid;grid-template-columns:1fr 1fr;gap:16px}label{display:block;font-weight:650}select{font:inherit;width:100%;padding:10px;border:1px solid #9aaac5;border-radius:8px;background:white;color:#14213d;margin-top:6px}
.summary{padding-top:0}.summary p{font-size:13px;color:#56657e}.device{margin-bottom:24px;background:white;border:1px solid #dae2ee;border-radius:12px;padding:16px;min-width:0}.device h2{margin:0 0 12px}.frame-scroll{overflow:auto;max-width:100%;border:1px solid #d8dfeb}iframe{display:block;height:820px;border:0;background:white}
:focus-visible{outline:3px solid #b77a00;outline-offset:3px}@media(max-width:600px){header,.controls,.summary,.devices{padding:16px}.controls{grid-template-columns:1fr}h1{font-size:22px}.device{padding:10px}}</style></head><body>
<header><div class="eyebrow">커리어픽 · 운영자 검토용</div><h1>가이드 6편과 광고 자리 검토</h1>
<p>기존 본문을 그대로 읽으며 320·390·1440px의 배치 후보를 확인합니다.</p>
<p class="note">공개 운영 화면이 아닙니다. 자리표시자는 가상 배치이며 실제 광고·외부 SDK·개인 기록을 사용하지 않습니다. 모든 글은 운영자의 사람 검토 대기 상태입니다.</p></header>
<section class="controls" aria-label="검토 화면 선택"><div><label for="guide">가이드</label><select id="guide"></select></div>
<div><label for="screen">가상 화면 상태</label><select id="screen"><option value="guide">가이드 본문 · 배치 후보 미리보기</option><option value="list">공고 목록 · 초기 제외</option><option value="job">공고 상세 · 초기 제외</option><option value="saved">저장 0건</option><option value="applications">내 지원 0건</option><option value="settings">설정 · 개인 관리</option><option value="empty">빈 검색 결과</option><option value="loading">로딩</option><option value="error">오류</option><option value="unfinished">미완성 기능</option></select></div></section>
<div class="summary"><output id="status" aria-live="polite"></output><p id="source"></p><p>자리표시자는 가이드 하단의 공식 참고자료 앞에 1개만 둡니다. 지원·원문·저장 등의 조작을 가리지 않으며, 다른 가상 상태에서는 표시하지 않습니다. 실제 활성화에는 콘텐츠 승인·동의·계정 및 화면 상태 제어 구현이 별도로 필요합니다.</p></div>
<main class="devices" id="devices"></main><script id="guide-data" type="application/json">__DATA__</script>
<script>
'use strict';
const guides=JSON.parse(document.getElementById('guide-data').textContent);
const guide=document.getElementById('guide'),screen=document.getElementById('screen');
for(const [index,item] of guides.entries()){const option=document.createElement('option');option.value=index;option.textContent=item.title;guide.append(option);}
const states={list:['공고 목록','목록은 독자적 가치와 정확성 검토 전 초기 광고 대상에서 제외합니다.'],job:['공고 상세','기관·직무·실제 접수기간·공식 원문을 확인하는 영역입니다. 개별 콘텐츠 검토 전에는 광고를 배치하지 않습니다.'],saved:['아직 저장한 공고가 없습니다','전체 공고에서 관심 있는 공고를 찾아 저장하세요. 기존 저장 기능의 자연스러운 빈 상태를 유지합니다.'],applications:['아직 등록한 지원 기록이 없습니다','공고를 확인한 뒤 지원 단계를 기록할 수 있습니다. 개인 기록 관리 화면에는 광고를 배치하지 않습니다.'],settings:['맞춤·개인 설정','관심 조건과 알림 설정을 관리하는 가상 화면입니다. 실제 개인 조건을 읽거나 변경하지 않습니다.'],empty:['검색 결과가 없습니다','검색어를 줄이거나 지역·고용형태 필터를 조정해 보세요.'],loading:['공고를 불러오는 중입니다','확인이 끝나기 전에는 광고를 요청하지 않습니다.'],error:['공고를 불러오지 못했습니다','연결 상태를 확인하고 다시 시도할 수 있도록 안내합니다.'],unfinished:['기능을 준비하고 있습니다','정확한 상태와 공식 채용기관에서 확인하는 대안을 안내합니다.']};
const esc=s=>s.replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
function render(){
 const current=guides[Number(guide.value)],kind=screen.value,isGuide=kind==='guide';
 document.getElementById('status').textContent=isGuide?'가상 배치 1개 · 실제 광고 요청 0 · 사람 검토 대기':'광고 제외 상태 · 자리표시자 0 · 실제 광고 요청 0';
 document.getElementById('source').textContent=isGuide?'본문 출처: '+current.path+' · SHA-256 '+current.source_sha256:'가상 상태 예시입니다. 운영 중인 기록이나 오류 상태를 조회한 결과가 아닙니다.';
 const simple=isGuide?'':'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}body{margin:0;padding:24px;color:#14213d;font:16px/1.8 system-ui,sans-serif;overflow-wrap:anywhere}h1{font-size:23px;line-height:1.4}p{max-width:650px}.notice{padding:14px;background:#eef2ff}</style><h1>'+esc(states[kind][0])+'</h1><p>'+esc(states[kind][1])+'</p><p class="notice">가상 상태 · 실제 광고 요청 없음</p></html>';
 const devices=document.getElementById('devices');devices.replaceChildren();
 for(const width of [320,390,1440]){const box=document.createElement('section');box.className='device';const h=document.createElement('h2');h.textContent=width+'px';const wrap=document.createElement('div');wrap.className='frame-scroll';const frame=document.createElement('iframe');frame.title=width+'px 검토 화면';frame.width=width;frame.setAttribute('sandbox','allow-same-origin');frame.srcdoc=isGuide?current.html:simple;wrap.append(frame);box.append(h,wrap);devices.append(box);}
}
guide.addEventListener('change',render);screen.addEventListener('change',render);render();
</script></body></html>'''
    output = ROOT / 'review-only' / 'ad-layout-preview.html'
    output.write_text(shell.replace('__DATA__', payload), encoding='utf-8')
    print('Built offline guide/placement preview: ' + str(output.relative_to(ROOT)))


if __name__ == '__main__':
    main()
