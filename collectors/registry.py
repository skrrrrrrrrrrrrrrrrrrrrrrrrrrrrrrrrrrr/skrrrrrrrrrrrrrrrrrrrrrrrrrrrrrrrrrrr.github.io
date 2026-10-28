"""분야 -> 수집기 매핑. 새 기관은 여기에 한 줄만 추가하면 된다."""
from .kma import KMACollector

COLLECTORS = {
    "weather": KMACollector,
    # "population": KosisCollector,   # 7단계
    # "health": KdcaCollector,        # 8단계
}


def get_collector(domain: str):
    cls = COLLECTORS.get(domain)
    return cls() if cls else None
