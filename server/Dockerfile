FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SSAS_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ssas_server ./ssas_server
RUN useradd --system --uid 1000 ssas && mkdir -p /data && chown ssas /data
USER ssas
EXPOSE 8443
CMD ["python", "-m", "ssas_server"]
