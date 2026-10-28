import os
import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google import genai
from plotly.subplots import make_subplots

st.set_page_config(page_title="시간별 날씨 시각화", page_icon="🌦️", layout="wide")


# ---------------------------------------------------------------
# 1. Gemini API 호출
# ---------------------------------------------------------------
def get_api_key() -> str | None:
    """st.secrets > 환경변수 > 사이드바 입력 순으로 API 키를 찾는다."""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY")


def build_prompt(target_date: date, region: str) -> str:
    d = f"{target_date.year}년 {target_date.month}월 {target_date.day}일"
    return f"""{d} {region} 지역의 시간별 기상 데이터(기온, 강수량, 습도)를 시각화하여 알려줘.

반드시 아래 형식을 그대로 지켜서 답변해줘.

1) mermaid xychart-beta 코드 (x축은 0,2,4,...,22 시각 12개, 기온과 습도 두 개의 line):
xychart-beta
title "{target_date.isoformat()} {region} 시간별 기온(℃) 및 습도(%)"
x-axis [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
y-axis "수치" 0 --> 100
line [기온 12개 값]
line [습도 12개 값]

2) 아래 한 줄 (같은 시각 12개의 강수량, 단위 mm):
시간별 강수량(mm): [12개 값]

3) 상세 데이터 요약 (강수량, 기온, 습도 항목)
4) 데이터 출처"""


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_weather_text(api_key: str, model: str, target_date: date, region: str) -> str:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_prompt(target_date, region),
    )
    return response.text or ""


# ---------------------------------------------------------------
# 2. 응답 파싱
# ---------------------------------------------------------------
def _to_floats(raw: str) -> list[float]:
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", raw)]


def parse_response(text: str) -> tuple[pd.DataFrame, str]:
    """
    Gemini 응답(mermaid xychart-beta + 요약 텍스트)에서 시간별 데이터를 추출한다.
    반환: (DataFrame[hour, temp, humidity, rain], 요약 텍스트)
    """
    # 코드펜스 제거
    clean = re.sub(r"```(?:mermaid)?", "", text)

    x_match = re.search(r"x-axis\s*\[([^\]]*)\]", clean)
    line_matches = re.findall(r"^\s*line\s*\[([^\]]*)\]", clean, flags=re.M)
    if not x_match or len(line_matches) < 2:
        raise ValueError("그래프 데이터(x-axis / line)를 찾지 못했습니다.")

    hours = [int(v) for v in _to_floats(x_match.group(1))]
    temp = _to_floats(line_matches[0])
    humidity = _to_floats(line_matches[1])

    n = min(len(hours), len(temp), len(humidity))
    hours, temp, humidity = hours[:n], temp[:n], humidity[:n]

    # 강수량: (1) 시간별 강수량 줄 → (2) 요약 문장에서 추정
    rain = [0.0] * n
    rain_match = re.search(r"강수량\s*\(mm\)\s*[:：]\s*\[([^\]]*)\]", clean)
    if rain_match and len(_to_floats(rain_match.group(1))) >= n:
        rain = _to_floats(rain_match.group(1))[:n]
    else:
        m = re.search(
            r"(\d{1,2})\s*시\s*[~\-–]\s*(\d{1,2})\s*시.*?(\d+(?:\.\d+)?)\s*mm",
            clean,
            flags=re.S,
        )
        if m:
            start, end, total = int(m.group(1)), int(m.group(2)), float(m.group(3))
            idx = [i for i, h in enumerate(hours) if start <= h <= end]
            for i in idx:
                rain[i] = round(total / len(idx), 2)

    df = pd.DataFrame({"hour": hours, "temp": temp, "humidity": humidity, "rain": rain})

    # 요약 텍스트 (상세 데이터 요약 이후)
    summary = ""
    s = re.search(r"상세 데이터 요약.*", clean, flags=re.S)
    if s:
        summary = s.group(0).strip()
    return df, summary


# ---------------------------------------------------------------
# 3. Plotly 시각화
# ---------------------------------------------------------------
def make_figure(df: pd.DataFrame, title: str) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.06,
        specs=[[{"secondary_y": True}], [{}]],
    )

    fig.add_trace(
        go.Scatter(
            x=df["hour"], y=df["temp"], name="기온(℃)",
            mode="lines+markers", line=dict(color="#EF553B", width=3),
            hovertemplate="%{x}시<br>기온 %{y}℃<extra></extra>",
        ),
        row=1, col=1, secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["hour"], y=df["humidity"], name="습도(%)",
            mode="lines+markers", line=dict(color="#636EFA", width=3, dash="dot"),
            hovertemplate="%{x}시<br>습도 %{y}%<extra></extra>",
        ),
        row=1, col=1, secondary_y=True,
    )
    fig.add_trace(
        go.Bar(
            x=df["hour"], y=df["rain"], name="강수량(mm)",
            marker_color="#00CC96",
            hovertemplate="%{x}시<br>강수량 %{y}mm<extra></extra>",
        ),
        row=2, col=1,
    )

    fig.update_yaxes(title_text="기온(℃)", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="습도(%)", range=[0, 100], row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="강수량(mm)", row=2, col=1)
    fig.update_xaxes(
        title_text="시각(시)", tickmode="array", tickvals=df["hour"], row=2, col=1
    )
    fig.update_layout(
        title=title,
        height=620,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
        margin=dict(t=90, l=40, r=40, b=40),
    )
    return fig


# ---------------------------------------------------------------
# 4. Streamlit UI
# ---------------------------------------------------------------
st.title("🌦️ 시간별 날씨 시각화")
st.caption("Gemini API로 수집한 시간별 기온·습도·강수량을 Plotly로 시각화합니다.")

with st.sidebar:
    st.header("설정")
    api_key = get_api_key() or st.text_input("Gemini API Key", type="password")
    model = st.text_input("모델", value="gemini-2.5-flash")
    region = st.text_input("지역", value="서울 강남")
    target_date = st.date_input("날짜", value=date(2022, 8, 20))
    run = st.button("데이터 수집 및 시각화", type="primary", use_container_width=True)

if run:
    if not api_key:
        st.error("Gemini API 키를 입력하거나 secrets/환경변수에 설정해주세요.")
        st.stop()

    try:
        with st.spinner("Gemini에서 데이터를 가져오는 중..."):
            raw_text = fetch_weather_text(api_key, model, target_date, region)
        df, summary = parse_response(raw_text)
    except ValueError as e:
        st.error(f"응답 파싱 실패: {e}")
        with st.expander("원본 응답 보기"):
            st.text(raw_text)
        st.stop()
    except Exception as e:
        st.error(f"API 호출 중 오류가 발생했습니다: {e}")
        st.stop()

    # 요약 지표
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("최고 기온", f"{df['temp'].max():.1f}℃", f"{df.loc[df['temp'].idxmax(), 'hour']}시", delta_color="off")
    c2.metric("최저 기온", f"{df['temp'].min():.1f}℃", f"{df.loc[df['temp'].idxmin(), 'hour']}시", delta_color="off")
    c3.metric("평균 습도", f"{df['humidity'].mean():.0f}%")
    c4.metric("총 강수량", f"{df['rain'].sum():.1f}mm")

    # 그래프
    title = f"{target_date.isoformat()} {region} 시간별 기온·습도·강수량"
    st.plotly_chart(make_figure(df, title), use_container_width=True)

    # 요약 + 데이터 테이블
    tab1, tab2, tab3 = st.tabs(["상세 요약", "데이터 표", "원본 응답"])
    with tab1:
        st.markdown(summary or "요약 텍스트가 응답에 없습니다.")
    with tab2:
        st.dataframe(
            df.rename(columns={"hour": "시각", "temp": "기온(℃)", "humidity": "습도(%)", "rain": "강수량(mm)"}),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "CSV 다운로드",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"weather_{target_date.isoformat()}.csv",
            mime="text/csv",
        )
    with tab3:
        st.text(raw_text)
else:
    st.info("왼쪽 사이드바에서 설정 후 **데이터 수집 및 시각화** 버튼을 눌러주세요.")
