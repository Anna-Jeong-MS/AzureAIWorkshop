FROM python:3.11-slim

WORKDIR /app

# 에러가 나던 7~12번 라인(apt-get)을 통째로 삭제하거나 주석 처리합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY finassist_chatbot_with_cosmos_ltm.py .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "finassist_chatbot_with_cosmos_ltm.py", "--server.port=8501", "--server.address=0.0.0.0"]