#!/bin/bash
set -e

echo "🚀 Starting deployment of Payment microservice to Minikube..."

# Start Minikube if not running
if ! minikube status >/dev/null 2>&1; then
  echo "🔧 Starting Minikube..."
  minikube start
else
  echo "✅ Minikube already running."
fi

echo "📦 Applying Kubernetes manifests..."

# Apply all manifests
kubectl apply -f k8s/payment-deployment.yaml
kubectl apply -f k8s/payment-service.yaml

echo "⏳ Waiting for all pods to become ready..."
kubectl wait --for=condition=available --timeout=120s deployment/payment-service

echo "✅ Payment service deployed successfully!"

echo ""
echo "🌐 Access Payment service via the following URL:"

# Retrieve and print service URL
echo "Payment service: $(minikube service payment-service --url)"

echo ""
echo "🎉 Deployment complete!"
