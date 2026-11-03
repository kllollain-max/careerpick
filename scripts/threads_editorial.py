"""Safe, deterministic editorial copy for CareerPick Threads.

Only supplied verified recruitment fields are repeated as facts.
No external AI calls or invented eligibility requirements.
"""
import re


def _role(job):
    title = str(job.get("title") or "").lower()
    if any(k in title for k in ("전산", "정보보안", "개발", "데이터", "소프트웨어")):
        return "it"
    if any(k in title for k in ("전기", "기계", "시설", "안전", "토목", "건축")):
        return "technical"
    if any(k in title for k in ("연구", "실험", "r&d")):
        return "research"
    return "general"


def insight(job):
    return {
        "it": "💡 커리어픽 직무 관점: 시스템 운영과 보안 역량도 함께 살펴보세요.",
        "technical": "💡 커리어픽 직무 관점: 필요한 자격증과 현장 업무를 확인하세요.",
        "research": "💡 커리어픽 직무 관점: 연구분야와 요구 역량의 일치도를 확인하세요.",
        "general": "💡 지원 전 직무내용·근무지·지원자격을 꼭 확인하세요.",
    }[_role(job)]


def engagement(job):
    questions = {
        "it": ["AI 시대 공공기관 IT 직무, 어떤 역량이 가장 중요할까요?",
               "공공기관 IT 직무에서 개발과 보안 중 어디에 관심이 있나요?"],
        "technical": ["공공기관 기술직에서 가장 중요한 조건은 무엇인가요?",
                      "기술직 취업 준비, 자격증과 경험 중 무엇을 우선하시나요?"],
        "research": ["공공기관 연구직, 연구주제와 근무환경 중 무엇이 더 중요한가요?",
                     "연구직 지원 시 가장 먼저 살펴보는 조건은 무엇인가요?"],
        "general": ["공공기관 지원 시 가장 먼저 확인하는 조건은 무엇인가요?",
                    "공공기관 채용에서 근무지와 직무 중 무엇이 더 중요한가요?"],
    }
    identifier = str(job.get("id") or job.get("org") or "")
    index = sum(map(ord, identifier)) % 2
    return "💬 여러분의 생각은 어떠신가요?\n\n🤔 " + questions[_role(job)][index]


def enrich_main(original, job):
    """Insert optional commentary before the existing reply call-to-action."""
    anchor = "💬 지원자격·접수정보는 답글 확인"
    if anchor not in original:
        return original
    candidate = original.replace(anchor, insight(job) + "\n\n" + anchor, 1)
    return candidate if len(candidate) <= 500 else original


def validated_reply(text):
    return isinstance(text, str) and 0 < len(text) <= 500

def conversation_main(job):
    """Evidence-grounded hook and useful facts in the main post."""
    title = " ".join(str(job.get("title") or "채용공고").split())
    org = " ".join(str(job.get("org") or "공공기관").split())
    emp = str(job.get("employment") or "고용형태 확인")
    location = str(job.get("location") or "공고 확인")
    count = job.get("count")
    due = str(job.get("due") or "공고 확인")
    role = _role(job)
    hooks = {
        "it": ["전산·IT 직무 준비 중이라면 확인할 공고", "공공기관 IT 직무를 찾고 있다면 주목"],
        "technical": ["기술직 채용을 찾는 분께 확인할 공고", "전기·시설·기술 분야 취업 준비 중이라면"],
        "research": ["연구직 채용을 기다렸다면 살펴볼 공고", "연구분야가 맞는지 확인해 볼 채용"],
        "general": ["이번 공공기관 채용, 지원조건을 확인해 보세요", "근무지와 직무를 먼저 살펴볼 채용공고"],
    }
    index = sum(map(ord, str(job.get("id") or org))) % 2
    hook = hooks[role][index]
    if "정규직" in emp and "무기계약" not in emp:
        hook = "정규직 채용! " + hook
    hiring = f"{count}명 모집" if isinstance(count, int) else "모집인원 공고 확인"
    lines = [
        hook, "",
        f"🏢 {org}",
        f"📌 {title[:95]}",
        f"👥 {emp[:45]} · {hiring}",
        f"📍 근무지: {location[:55]}",
        f"📅 마감: {due}",
        "",
        insight(job),
        "",
        "💬 이 직무 준비 중이신가요? 궁금한 점을 댓글로 남겨주세요.",
    ]
    result = "\n".join(lines)
    if len(result) > 500:
        lines[3] = f"📌 {title[:45]}"
        lines[4] = f"👥 {hiring}"
        lines[5] = f"📍 근무지: {location[:25]}"
        result = "\n".join(lines)
    if len(result) > 500:
        raise ValueError("Conversation post exceeds 500 characters")
    return result
