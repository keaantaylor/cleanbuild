# Build context is the REPO ROOT (see docker-compose.yml's `context: ..`),
# not this directory -- the backend depends on the sibling bordereaux/
# package (requirements.txt's -e ../../bordereaux), which Docker can only
# reach if the build context is wide enough to include it.
FROM python:3.11-slim

WORKDIR /app

COPY bordereaux /bordereaux
RUN pip install --no-cache-dir -e /bordereaux

COPY truebind-web/backend/requirements.txt ./
# The last line (-e ../../bordereaux) is a local-dev-only relative path
# that doesn't resolve inside the image; bordereaux is already installed
# above from its own copied context instead.
RUN grep -v '^-e ' requirements.txt > requirements.docker.txt \
    && pip install --no-cache-dir -r requirements.docker.txt

COPY truebind-web/backend/ .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
