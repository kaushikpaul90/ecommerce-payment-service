# Payment Service

A microservice for handling payment processing in the e-commerce system. This service is built using FastAPI and provides endpoints for processing payments and managing payment-related operations.

## Features

- Process payments for orders
- Payment status tracking
- Integration with database service
- Configurable synchronous/asynchronous payment processing
- Docker support
- Kubernetes deployment ready with Helm charts

## Tech Stack

- Python 3.11
- FastAPI
- HTTPX for async HTTP requests
- Pydantic for data validation
- Uvicorn ASGI server
- Docker
- Kubernetes/Helm for deployment

## Prerequisites

- Python 3.11 or higher
- Docker (for containerization)
- Kubernetes cluster (for deployment)
- Helm (for Kubernetes package management)

## Installation

### Local Development

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the service:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8005 --reload
   ```

### Docker

1. Build the Docker image:
   ```bash
   docker build -t payment-service .
   ```

2. Run the container:
   ```bash
   docker run -p 8005:8005 payment-service
   ```

## Configuration

The service can be configured using environment variables:

- `DATABASE_SERVICE_URL`: URL of the database service (default: "http://192.168.105.2:30000")
- `PROCESS_PAYMENTS_SYNC`: Control whether to process payments synchronously (default: "true")

## Kubernetes Deployment

The service includes Helm charts for Kubernetes deployment:

1. Navigate to the helm_chart directory:
   ```bash
   cd helm_chart
   ```

2. Install the chart:
   ```bash
   helm install payment-service .
   ```

## API Documentation

Once the service is running, you can access the API documentation at:
- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`

## Project Structure

```
payment_service/
├── app.py              # Main FastAPI application
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker configuration
├── deploy.sh           # Deployment script
└── helm_chart/         # Kubernetes Helm charts
    ├── Chart.yaml
    ├── values.yaml
    ├── values-resolved.yaml
    └── templates/
        ├── deployment.yaml
        ├── service.yaml
        └── hpa.yaml
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/payment_functionality`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/payment_functionality`)
5. Open a Pull Request

## License

This project is proprietary and confidential.
This repository contains the source code of Payment Service of the E-Commerce application
