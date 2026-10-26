ARG PYTHON_BASE=python:3.12-slim
FROM ${PYTHON_BASE}
WORKDIR /app
COPY pyproject.toml README.md LICENSE_STATUS.md ./
COPY easyaiot_face_agent ./easyaiot_face_agent
RUN pip install --no-cache-dir ".[persistence]" gunicorn \
    && useradd --create-home agent \
    && mkdir /state && chown agent:agent /state
USER agent
ENV AGENT_CHECKPOINT_DB=/state/checkpoints.sqlite3
EXPOSE 8765
CMD ["gunicorn", "--workers", "1", "--timeout", "600", "--bind", "0.0.0.0:8765", "easyaiot_face_agent.api.flask_app:create_app()"]
