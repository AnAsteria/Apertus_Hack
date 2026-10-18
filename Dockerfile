FROM python:3.12-slim
WORKDIR /srv
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
ENV BERNMATCH_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
