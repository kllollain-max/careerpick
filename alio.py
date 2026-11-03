"""잡알리오(공공기관 채용정보) 공식 공고를 가져와 alio.json에 저장하는 스크립트

- 공공데이터포털 '기획재정부_공공기관 채용정보 조회서비스' (data.go.kr 15125273)
- GitHub Secrets 의 ALIO_KEY (일반 인증키, Decoding) 가 있을 때만 실행
- 실패해도 기존 alio.json 을 그대로 두므로 사이트에는 영향이 없음
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent / "alio.json"
DETAIL = Path(__file__).parent / "alio-detail.json"   # 카드를 눌렀을 때만 불러오는 상세 내용
KST = timezone(timedelta(hours=9))
ENDPOINTS = ["https://apis.data.go.kr/1051000/recruitment/list"]
PER_PAGE = 100
MAX_PAGES = 10


def pick(item, *keys):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", []):
            return v
    return ""


def as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [s.strip() for s in str(v or "").replace("|", ",").split(",") if s.strip()]


def ymd(v):
    s = "".join(ch for ch in str(v or "") if ch.isdigit())[:8]
    if len(s) != 8:
        return None
    try:
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=KST)
    except ValueError:
        return None


def unwrap(data):
    """{result:[...]} 형식과 data.go.kr 표준 {response:{header,body:{items:{item:[...]}}}} 형식 모두 지원"""
    if isinstance(data, dict) and "response" in data:
        resp = data.get("response") or {}
        head, body = resp.get("header") or {}, resp.get("body") or {}
        items = body.get("items")
        if isinstance(items, dict):
            items = items.get("item")
        return {"resultCode": head.get("resultCode", "200"), "resultMsg": head.get("resultMsg"),
                "totalCount": body.get("totalCount"), "result": items or []}
    return data if isinstance(data, dict) else {"result": data}


def call(key, page, ongoing="Y"):
    q = urllib.parse.urlencode({"serviceKey": key, "resultType": "json", "pageNo": page,
                                "numOfRows": PER_PAGE, "ongoingYn": ongoing})
    last = None
    for base in ENDPOINTS:
        try:
            req = urllib.request.Request(f"{base}?{q}", headers={"User-Agent": "jobinfo-hub"})
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode("utf-8", "replace")
            try:
                data = json.loads(text)
            except ValueError:
                raise RuntimeError("JSON 이 아닌 응답: " + text[:300].replace("\n", " "))
            data = unwrap(data)
            code = str(data.get("resultCode", "200"))
            if code not in ("200", "00", "0", "INFO-000", "NORMAL_SERVICE"):
                raise RuntimeError(f"API 오류 {code}: {data.get('resultMsg')}")
            return data
        except Exception as e:
            # HTTP errors can embed serviceKey in the request URL; never log it.
            last = str(e).replace(key, "***").replace(urllib.parse.quote_plus(key), "***")
    raise RuntimeError(last or "ALIO API request failed")


EMP_MAP = [("무기", "무기계약직"), ("정규", "정규직"), ("인턴", "인턴"), ("비정규", "계약직"), ("기간제", "계약직"), ("계약", "계약직")]
EDU_MAP = [("무관", "학력무관"), ("고졸", "고졸 가능"), ("고등", "고졸 가능")]


def convert(it, now):
    sn = str(pick(it, "recrutPblntSn", "recrutPblntSN", "sn"))
    title = str(pick(it, "recrutPbancTtl", "title")).strip()
    org = str(pick(it, "instNm")).strip()
    end = ymd(pick(it, "pbancEndYmd", "pbancEndDt"))
    start = ymd(pick(it, "pbancBgngYmd", "pbancBgngDt"))
    if not (sn and title and end):
        return None
    due = end.replace(hour=23, minute=59)
    if due < now:
        return None
    always = due > now + timedelta(days=365)   # 2050-12-31 같은 상시모집
    hire = " ".join(as_list(pick(it, "hireTypeNmLst", "hireTypeNm")))
    emp = []
    for k, label in EMP_MAP:
        if k == "정규":
            hit = re.search(r"(?<!비)정규", hire)
        elif k == "계약":
            hit = re.search(r"(?<!무기)계약", hire)
        else:
            hit = k in hire
        if hit and label not in emp:
            emp.append(label)
    acbg = " ".join(as_list(pick(it, "acbgCondNmLst", "acbgCondNm")))
    edu = []
    for k, label in EDU_MAP:
        if k in acbg and label not in edu:
            edu.append(label)
    regions = as_list(pick(it, "workRgnNmLst", "workRgnNm"))
    nope = "".join(ch for ch in str(pick(it, "recrutNope")) if ch.isdigit())
    ncs = as_list(pick(it, "ncsCdNmLst", "ncsCdNm"))
    src = str(pick(it, "srcUrl")).strip()
    post = {
        "id": "a" + sn,
        "type": "j",
        "alio": True,
        "cat": "공공기관 공식 공고",
        "title": title,
        "org": org,
        "desc": " · ".join(ncs[:3]),
        "url": f"https://job.alio.go.kr/mobile2021/recruit/recruitView.do?idx={urllib.parse.quote(sn)}",
        "pub": (start or now).isoformat(),
        "due": None if always else due.isoformat(),
        "dueHasTime": False,
        "emp": emp[:3],
        "edu": edu,
        "region": regions[0] if len(regions) == 1 else ("전국" if len(regions) > 3 else (regions[0] if regions else "")),
        "text": " ".join([hire, acbg, " ".join(regions), " ".join(ncs)]),
    }
    if nope and nope != "0":
        post["n"] = nope
    if src.startswith("http"):
        post["src"] = src
    if always:
        post["always"] = True
    return post


def detail_of(it):
    """사이트 상세 화면용: 코드값을 뺀 글자 정보만 보관 (항목 이름은 API 그대로)"""
    out = {}
    for k, v in it.items():
        if isinstance(v, dict) or (isinstance(v, list) and any(isinstance(x, (dict, list)) for x in v)):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if str(x).strip())
        v = str(v).strip() if v is not None else ""
        if not v or v.lower() in ("null", "none"):
            continue
        if k.endswith("Cd") or k.endswith("CdLst") or (k.endswith("Lst") and not k.endswith("NmLst")):
            continue
        out[k] = v  # 원문은 보존하고, 화면 표시 길이는 페이지 생성기에서 관리
    return out


def main():
    key = os.environ.get("ALIO_KEY", "").strip()
    if not key:
        print("ALIO_KEY 가 없어 잡알리오 연동을 건너뜁니다.")
        return None
    now = datetime.now(KST)
    items, total = [], None
    for page in range(1, MAX_PAGES + 1):
        try:
            data = call(key, page)
        except Exception as e:
            print("잡알리오 요청 실패:", type(e).__name__)
            print("잡알리오 수집 중단: 일부 페이지만 수집되어 기존 데이터를 유지합니다.")
            return None
        rows = data.get("result") or []
        if isinstance(rows, dict):
            rows = [rows]
        if page == 1:
            total = data.get("totalCount")
            print(f"총 {total}건 응답")
            if rows:
                print("응답 필드:", ", ".join(sorted(rows[0].keys())))
        items += rows
        try:
            done = bool(total) and len(items) >= int(total)
        except (TypeError, ValueError):
            done = False
        if len(rows) < PER_PAGE or done:
            break
    # Never publish a truncated snapshot if the API reports more than our page cap.
    try:
        expected = int(total) if total is not None else None
    except (TypeError, ValueError):
        expected = None
    if expected is not None and expected > len(items):
        print(f"잡알리오 수집 불완전: 응답 {len(items)}건 / 전체 {expected}건. 기존 데이터를 유지합니다.")
        return None
    posts, seen = [], set()
    bad = 0
    details = {}
    for it in items:
        try:
            p = convert(it, now) if isinstance(it, dict) else None
        except Exception as e:
            bad += 1
            if bad <= 3:
                print("공고 변환 실패:", e, str(it)[:200])
            continue
        if p and p["id"] not in seen:
            seen.add(p["id"])
            posts.append(p)
            try:
                details[p["id"]] = detail_of(it)
            except Exception:
                pass
    if not posts:
        print("가져온 공고가 없어 기존 alio.json 을 유지합니다.")
        return items
    posts.sort(key=lambda p: p["due"] or "9999")
    det_text = json.dumps(details, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not DETAIL.exists() or DETAIL.read_text("utf-8") != det_text:
        DETAIL.write_text(det_text, "utf-8")
        print(f"alio-detail.json 갱신: {len(details)}건")
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    if old.get("posts") == posts:
        print("잡알리오 변경 없음")
        return items
    OUT.write_text(json.dumps({"updated": now.isoformat(timespec="seconds"), "posts": posts},
                              ensure_ascii=False, indent=1), "utf-8")
    print(f"alio.json 갱신: 모집 중 공식 공고 {len(posts)}건 (API 전체 {total})")
    return items


if __name__ == "__main__":
    main()
