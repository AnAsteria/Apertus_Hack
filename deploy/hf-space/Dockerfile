# Hugging Face Docker Space image. Build from the repository root:
#   docker build -f deploy/hf-space/Dockerfile -t bernmatch-hf .
# Spaces run the container as user ID 1000 and expose port 7860 by default.
FROM python:3.12-slim
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    BERNMATCH_DATA_DIR=/home/user/data
WORKDIR $HOME/app
COPY --chown=user requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY --chown=user app ./app
COPY --chown=user config/suppression.json ./config/suppression.json
RUN mkdir -p $BERNMATCH_DATA_DIR
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
