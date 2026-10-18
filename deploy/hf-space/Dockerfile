# Hugging Face Docker Space image. Build from the repository root:
#   docker build -f deploy/hf-space/Dockerfile -t bernmatch-hf .
# Spaces run the container as user ID 1000 and expose port 7860 by default.
# The persistent bucket is mounted at /data by the Space settings (volumes).
FROM python:3.12-slim
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    BERNMATCH_DATA_DIR=/data
WORKDIR $HOME/app
COPY --chown=user requirements.lock .
COPY --chown=user app/search/requirements.txt app/search/requirements.txt
COPY --chown=user app/ingest/requirements.txt app/ingest/requirements.txt
RUN pip install --no-cache-dir -r requirements.lock -r app/search/requirements.txt -r app/ingest/requirements.txt
COPY --chown=user app ./app
COPY --chown=user config/suppression.json ./config/suppression.json
COPY --chown=user deploy/hf-space/entrypoint.sh ./entrypoint.sh
EXPOSE 7860
CMD ["sh", "./entrypoint.sh"]
