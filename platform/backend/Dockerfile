# Use an official lightweight Python image
FROM python:3.12-slim

# Set build and runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MSS_ENVIRONMENT=production \
    MSS_STORAGE_DIR=/app/platform/backend/storage \
    MSS_DATA_ROOT=/app/data \
    MSS_METRO_DEMAND_MODELS_ROOT=/app/ml_pipeline \
    PORT=8000

WORKDIR /app

# Copy the backend code
COPY platform/backend /app/platform/backend

# Copy the ml_pipeline files (models, config, data catalogs)
COPY ml_pipeline /app/ml_pipeline

# Install the local ML package first so pickled models and shared helpers can
# resolve metro_demand_models imports inside the container.
WORKDIR /app/ml_pipeline
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Install the backend dependencies and package
WORKDIR /app/platform/backend
RUN pip install --no-cache-dir -e .

# Expose backend port
EXPOSE 8000

# Run the FastAPI server using Uvicorn
CMD ["uvicorn", "metro_scenario_studio.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
