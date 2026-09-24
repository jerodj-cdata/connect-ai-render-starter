# Local development image. Render does not use this file: render.yaml deploys
# with Render's native Python runtime. Keep the Python version in step with
# PYTHON_VERSION in render.yaml.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY jobs jobs

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
