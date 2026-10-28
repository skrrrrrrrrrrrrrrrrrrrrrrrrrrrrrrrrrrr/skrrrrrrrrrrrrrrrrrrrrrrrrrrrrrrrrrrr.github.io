"""API 키 등 민감 정보 조회. 우선순위: Streamlit Secrets -> 환경변수(.env).
수집기가 streamlit에 직접 의존하지 않도록 이 모듈만 secrets를 다룬다."""
import os


def get_secret(name: str, default: str = "") -> str:
    try:
        import streamlit as st
        value = st.secrets.get(name)   # secrets.toml이 없으면 예외가 날 수 있음
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)
