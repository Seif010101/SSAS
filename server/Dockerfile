FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SSAS_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ssas_server ./ssas_server
RUN useradd --system --uid 1000 ssas && mkdir -p /data && chown ssas /data
USER ssas
# 8443: HTTPS with the server's own certificate (local network). 8000: plain HTTP behind Caddy (deploy/vps).
EXPOSE 8443 8000
CMD ["python", "-m", "ssas_server"]
