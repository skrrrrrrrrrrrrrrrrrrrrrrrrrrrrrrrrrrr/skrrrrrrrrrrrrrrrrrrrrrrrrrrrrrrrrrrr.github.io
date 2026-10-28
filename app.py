import streamlit as st

from collectors.registry import get_collector
from core.charts import build_chart
from core.errors import DataError
from core.parser import parse_query
from core.table import to_display_table

DOMAIN_NAMES = {"weather": "날씨", "population": "인구·사회통계", "health": "질병·보건"}

st.set_page_config(page_title="공공데이터 통합 검색", layout="wide")
st.title("🔎 공공데이터 통합 검색")
st.caption("원하는 데이터를 문장으로 입력하세요. 예) 2026년 4월 서울의 평균기온과 강수량")

text = st.text_input("검색어", placeholder="2026년 4월 서울의 평균기온과 강수량을 알려줘")

if st.button("검색", type="primary") and text.strip():
    q = parse_query(text)

    st.subheader("검색 결과")
    st.markdown(f"**검색어**\n\n> {q.raw}")
    st.markdown("**분석 결과**")
    st.write(
        f"- 분야: {DOMAIN_NAMES.get(q.domain, '판단 불가')}\n"
        f"- 지역: {q.region or '-'}\n"
        f"- 기간: {q.period_label or '-'}\n"
        f"- 데이터: {', '.join(q.metrics) if q.metrics else '-'}"
    )
    for w in q.warnings:
        st.warning(w)

    try:
        if q.domain is None:
            raise DataError("어떤 분야의 데이터인지 알 수 없습니다. 예: 날씨, 인구, 감염병")
        if q.start is None:
            raise DataError("기간을 찾지 못했습니다. 예: '2026년 4월', '2020년부터 2025년까지', '최근 3년'")
        collector = get_collector(q.domain)
        if collector is None:
            raise DataError(f"'{DOMAIN_NAMES[q.domain]}' 분야는 아직 구현 중입니다.")

        with st.spinner("공공데이터를 가져오는 중..."):
            result = collector.collect(q)

        st.markdown("### 데이터 표")
        st.dataframe(to_display_table(result), use_container_width=True, hide_index=True)
        st.markdown("### 시각화")
        st.plotly_chart(build_chart(q, result), use_container_width=True)
        for n in result.notes:
            st.info(n)

        s = result.source
        st.markdown("### 출처")
        st.markdown(
            f"- 기관명: {s.agency}\n- 자료명: {s.dataset}\n- 원본 URL: {s.url}\n"
            f"- API: `{s.api}`\n- 데이터 수집 시점: {s.fetched_at:%Y-%m-%d %H:%M:%S}"
        )
    except DataError as e:
        st.error(str(e))
    except Exception:
        st.error("예상하지 못한 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
