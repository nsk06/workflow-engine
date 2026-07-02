CLUSTER_NAME ?= workflow-demo
ROOT := $(shell pwd)

.PHONY: kind-up build deploy demo loadtest test dev-api dev-worker dev-ui verify-e2e seed-multi-user

kind-up:
	chmod +x scripts/*.sh
	./scripts/kind-up.sh

build:
	docker build -t workflow-engine:latest backend
	docker build -t workflow-ui:latest --build-arg VITE_API_URL=/api frontend

deploy: build
	./scripts/deploy-app.sh

up:
	docker compose --env-file .env.ports up --build -d

verify-e2e:
	chmod +x scripts/verify-e2e.sh scripts/get-token.sh
	./scripts/verify-e2e.sh

seed-multi-user:
	chmod +x scripts/seed-multi-user.sh
	API_URL=http://localhost:18700 ./scripts/seed-multi-user.sh

demo:
	chmod +x scripts/demo.sh scripts/get-token.sh
	API_URL=http://localhost:18700 ./scripts/demo.sh

loadtest:
	k6 run loadtest/k6_workflows.js

test:
	cd backend && pip install -e ".[dev]" -q && PYTHONPATH=. pytest -v

dev-api:
	cd backend && AUTH_DISABLED=false JWT_SECRET=dev DATABASE_URL=sqlite:////tmp/workflow-dev.db OTEL_ENABLED=false \
		DEMO_USERS=demo:demo,alice:alice,bob:bob pip install -e . -q && uvicorn app.main:app --reload --port 8000

dev-worker:
	cd backend && DATABASE_URL=sqlite:////tmp/workflow-dev.db OTEL_ENABLED=false \
		WORKER_ID=dev-worker-1 pip install -e . -q && python -m app.run_worker

dev-ui:
	cd frontend && npm install && VITE_API_URL=http://localhost:8000 npm run dev
