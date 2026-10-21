"""AI 요약 버튼 준비 상태 판단 (Streamlit 없이도 단위 검증 가능)."""


def ai_summary_blockers(paper, confirmed, evidence: str, user_ai_key: str) -> list[str]:
    """차단 원인을 사용자 해결 순서로 반환. 키 값은 기록하거나 출력하지 않음."""
    blockers = []
    if not str(user_ai_key or "").strip():
        blockers.append("API_KEY")
    if not paper:
        blockers.append("PAPER")
    if len(str(evidence or "").strip()) < 40:
        blockers.append("EVIDENCE")
    if not confirmed:
        blockers.append("CONFIRM")
    return blockers
