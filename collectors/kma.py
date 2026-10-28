"""기상청 지상(종관, ASOS) 일자료 조회서비스 (공공데이터포털 OpenAPI)
  - 서비스 페이지: https://www.data.go.kr/data/15059093/openapi.do
  - 원본 자료 포털: 기상자료개방포털 https://data.kma.go.kr
"""
import os
from datetime import date, timedelta

import pandas as pd
import requests

from core.errors import DataError
from core.models import ParsedQuery, CollectResult, SourceInfo
from core.parser import REGIONS
from .base import BaseCollector

ENDPOINT = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"
DATASET_PAGE = "https://www.data.go.kr/data/15059093/openapi.do"
PORTAL = "https://data.kma.go.kr"

FIELDS = {
    "avg_temp": ("avgTa", "평균기온", "°C"),
    "max_temp": ("maxTa", "최고기온", "°C"),
    "min_temp": ("minTa", "최저기온", "°C"),
    "rain": ("sumRn", "강수량", "mm"),
    "humidity": ("avgRhm", "평균습도", "%"),
    "wind": ("avgWs", "평균풍속", "m/s"),
}


class KMACollector(BaseCollector):
    domain = "weather"

    def __init__(self, api_key=None, session=None):
        self.api_key = api_key or os.getenv("KMA_API_KEY", "")
        self.session = session or requests.Session()

    def _fetch_page(self, stn, start, end, page):
        params = {
            "serviceKey": self.api_key, "pageNo": page, "numOfRows": 999,
            "dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
            "startDt": start.strftime("%Y%m%d"), "endDt": end.strftime("%Y%m%d"),
            "stnIds": stn,
        }
        try:
            r = self.session.get(ENDPOINT, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            raise DataError("인터넷 연결 또는 기상청 데이터 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.")
        except requests.exceptions.Timeout:
            raise DataError("기상청 데이터 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.")
        except (requests.exceptions.RequestException, ValueError):
            raise DataError("기상청 서버에서 올바른 응답을 받지 못했습니다. 인증키와 요청 내용을 확인해주세요.")

    def collect(self, query: ParsedQuery) -> CollectResult:
        if not self.api_key:
            raise DataError("기상청 API 키가 없습니다. .env 파일에 KMA_API_KEY를 설정해주세요.")
        stn = REGIONS.get(query.region or "")
        if not stn:
            raise DataError("지원하는 지역을 찾지 못했습니다. 예: 서울, 부산, 대전, 제주 등")
        if not query.metrics:
            raise DataError("조회할 날씨 항목(기온, 강수량, 습도, 풍속 등)을 찾지 못했습니다.")

        end = min(query.end, date.today() - timedelta(days=1))  # 일자료는 전일까지 제공
        if query.start > end:
            raise DataError("아직 관측되지 않은 기간입니다. 날짜를 확인해주세요.")

        rows, page = [], 1
        while True:
            data = self._fetch_page(stn, query.start, end, page)
            try:
                header = data["response"]["header"]
                body = data["response"].get("body", {})
            except (KeyError, TypeError, AttributeError):
                raise DataError("기상청 응답 형식이 예상과 다릅니다. 인증키가 올바른지 확인해주세요.")
            if header.get("resultCode") == "03":
                break  # NODATA_ERROR
            if header.get("resultCode") != "00":
                raise DataError(f"기상청 API 오류: {header.get('resultMsg', '알 수 없는 오류')}")
            items = (body.get("items") or {}).get("item", [])
            rows.extend(items)
            if page * 999 >= int(body.get("totalCount", 0)):
                break
            page += 1

        if not rows:
            raise DataError("요청한 기간의 데이터를 찾을 수 없습니다. 날짜 또는 지역을 확인해주세요.")

        raw = pd.DataFrame(rows)
        out = pd.DataFrame({"date": pd.to_datetime(raw["tm"]), "region": raw["stnNm"]})
        units = {}
        for key in query.metrics:
            col, label, unit = FIELDS[key]
            out[key] = pd.to_numeric(raw.get(col), errors="coerce")  # 빈 값은 NaN 유지(원본 보존)
            units[key] = (label, unit)
        out = out.sort_values("date").reset_index(drop=True)

        notes = []
        if "rain" in query.metrics and out["rain"].isna().any():
            notes.append("강수량이 빈 칸인 날은 원본에 값이 없는 날입니다(기상청 일자료에서는 강수 없음인 경우가 많음). 임의로 0으로 바꾸지 않았습니다.")
        if end < query.end:
            notes.append(f"일자료는 전일까지 제공되어 조회 기간을 {end}까지로 조정했습니다.")

        source = SourceInfo(
            agency="기상청",
            dataset="지상(종관, ASOS) 일자료 (기상자료개방포털 제공)",
            url=DATASET_PAGE,
            api=f"{ENDPOINT}  (원본 포털: {PORTAL})",
        )
        return CollectResult(df=out, units=units, source=source, notes=notes)
