FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Em produção na AWS (RDS), baixa o pacote de certificados da AWS para a conexão
# com o banco usar TLS verificado (DATABASE_SSL_CA=/app/certs/rds-global-bundle.pem).
ARG BAIXAR_CA_RDS=0
RUN mkdir -p /app/certs && if [ "$BAIXAR_CA_RDS" = "1" ]; then \
      python -c "import urllib.request; urllib.request.urlretrieve('https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem', '/app/certs/rds-global-bundle.pem')"; \
    fi

COPY . .

# Não roda como root dentro do contêiner.
RUN useradd --create-home --uid 10001 mediary && chown -R mediary /app
USER mediary

EXPOSE 5000
# Sem --access-logfile de propósito: as URLs têm datas de sintomas (dado de saúde).
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${GUNICORN_WORKERS:-2} --timeout 120 app:app
