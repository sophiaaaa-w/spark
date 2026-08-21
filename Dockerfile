FROM python:3.11-slim

# ffmpeg 用于抽帧，ffprobe 用于读时长
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway 会注入 PORT
ENV PORT=8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
