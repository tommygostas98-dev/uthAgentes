FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Transporte HTTP para hospedaje; la DB en un volumen persistente.
ENV MCP_TRANSPORT=streamable-http \
    HOST=0.0.0.0 \
    PORT=8080 \
    UTHAGENTES_DB=/data/uthagentes.db

EXPOSE 8080

CMD ["python", "server.py"]
