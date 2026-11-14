FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.lock ./
RUN pip install -r requirements.lock
COPY pyproject.toml README.md LICENSE alembic.ini ./
COPY src ./src
RUN pip install --no-deps .

RUN useradd --create-home tcms
USER tcms
EXPOSE 8000
CMD ["test-junkie-tcms", "serve", "--host", "0.0.0.0", "--port", "8000"]
