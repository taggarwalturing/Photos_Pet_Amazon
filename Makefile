.PHONY: help install install-backend install-frontend install-pipeline clean-ports start stop dev backend frontend logs status health

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Configuration
BACKEND_PORT := 8000
FRONTEND_PORT := 5173
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV_DIR := $(BACKEND_DIR)/.venv
PYTHON := $(VENV_DIR)/bin/python
PIP := $(VENV_DIR)/bin/pip

##@ Help

help: ## Display this help message
	@echo "$(CYAN)Photo Pets Annotation Tool - Makefile Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(CYAN)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Installation

install: install-backend install-frontend install-pipeline ## Install all dependencies (backend + frontend + pipeline)
	@echo "$(GREEN)✅ All dependencies installed successfully!$(NC)"

install-backend: ## Install backend Python dependencies
	@echo "$(CYAN)📦 Installing backend dependencies...$(NC)"
	@cd $(BACKEND_DIR) && \
		if [ ! -d ".venv" ]; then \
			echo "$(YELLOW)Creating Python virtual environment...$(NC)"; \
			python3 -m venv .venv; \
		fi
	@$(PIP) install --upgrade pip
	@$(PIP) install -r $(BACKEND_DIR)/requirements.txt
	@echo "$(GREEN)✅ Backend dependencies installed$(NC)"

install-frontend: ## Install frontend npm dependencies
	@echo "$(CYAN)📦 Installing frontend dependencies...$(NC)"
	@cd $(FRONTEND_DIR) && npm install
	@echo "$(GREEN)✅ Frontend dependencies installed$(NC)"

install-pipeline: ## Install biometric compliance pipeline dependencies
	@echo "$(CYAN)📦 Installing pipeline dependencies...$(NC)"
	@$(PIP) install -r $(BACKEND_DIR)/master_pipeline/requirements.txt
	@echo "$(GREEN)✅ Pipeline dependencies installed$(NC)"

##@ Port Management

clean-ports: ## Kill processes on backend (8000) and frontend (5173) ports
	@echo "$(CYAN)🧹 Cleaning up ports...$(NC)"
	@echo "$(YELLOW)Checking port $(BACKEND_PORT) (backend)...$(NC)"
	@-lsof -ti:$(BACKEND_PORT) | xargs kill -9 2>/dev/null || echo "  Port $(BACKEND_PORT) is already free"
	@echo "$(YELLOW)Checking port $(FRONTEND_PORT) (frontend)...$(NC)"
	@-lsof -ti:$(FRONTEND_PORT) | xargs kill -9 2>/dev/null || echo "  Port $(FRONTEND_PORT) is already free"
	@sleep 2
	@echo "$(GREEN)✅ Ports cleaned$(NC)"

##@ Running

start: clean-ports ## Clean ports, then start both backend and frontend
	@echo "$(CYAN)🚀 Starting Photo Pets Annotation Tool...$(NC)"
	@echo ""
	@$(MAKE) backend &
	@echo "$(YELLOW)⏳ Waiting for backend to be ready...$(NC)"
	@sleep 5
	@until curl -s http://localhost:$(BACKEND_PORT)/docs > /dev/null 2>&1; do \
		echo "$(YELLOW)   Still waiting for backend...$(NC)"; \
		sleep 2; \
	done
	@echo "$(GREEN)✅ Backend is ready!$(NC)"
	@echo ""
	@echo "$(CYAN)🔐 Processing all images before starting frontend...$(NC)"
	@cd $(BACKEND_DIR) && \
		. .venv/bin/activate && \
		PYTHONUNBUFFERED=1 python -u -c "import asyncio; from app.background_tasks import auto_processor; asyncio.run(auto_processor.run_processing_cycle())"
	@echo "$(GREEN)✅ Initial processing complete!$(NC)"
	@echo ""
	@$(MAKE) frontend &
	@sleep 2
	@echo ""
	@echo "$(GREEN)✅ Application started!$(NC)"
	@echo ""
	@echo "$(CYAN)Access the application:$(NC)"
	@echo "  Frontend: $(YELLOW)http://localhost:$(FRONTEND_PORT)$(NC)"
	@echo "  Backend:  $(YELLOW)http://localhost:$(BACKEND_PORT)$(NC)"
	@echo "  API Docs: $(YELLOW)http://localhost:$(BACKEND_PORT)/docs$(NC)"
	@echo ""
	@echo "$(CYAN)Useful commands:$(NC)"
	@echo "  $(YELLOW)make logs$(NC)     - View application logs"
	@echo "  $(YELLOW)make status$(NC)   - Check if services are running"
	@echo "  $(YELLOW)make stop$(NC)     - Stop all services"
	@echo ""

dev: start ## Alias for 'start' - start development servers

backend: ## Start backend server only
	@echo "$(CYAN)🔧 Starting backend server...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		uvicorn app.main:app --reload --host 0.0.0.0 --port $(BACKEND_PORT)

frontend: ## Start frontend server only
	@echo "$(CYAN)🎨 Starting frontend server...$(NC)"
	@cd $(FRONTEND_DIR) && npm run dev

##@ Monitoring

status: ## Check if backend and frontend are running
	@echo "$(CYAN)📊 Service Status:$(NC)"
	@echo ""
	@if lsof -ti:$(BACKEND_PORT) > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Backend  (port $(BACKEND_PORT))$(NC) - Running (PID: $$(lsof -ti:$(BACKEND_PORT)))"; \
	else \
		echo "$(RED)❌ Backend  (port $(BACKEND_PORT))$(NC) - Not running"; \
	fi
	@if lsof -ti:$(FRONTEND_PORT) > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Frontend (port $(FRONTEND_PORT))$(NC) - Running (PID: $$(lsof -ti:$(FRONTEND_PORT)))"; \
	else \
		echo "$(RED)❌ Frontend (port $(FRONTEND_PORT))$(NC) - Not running"; \
	fi
	@echo ""

health: status ## Check service health (alias for status)

logs: ## Show logs from backend and frontend
	@echo "$(CYAN)📋 Application Logs$(NC)"
	@echo "$(YELLOW)Note: This shows process status. For live logs, check terminal output.$(NC)"
	@echo ""
	@$(MAKE) status

##@ Cleanup

stop: clean-ports ## Stop all services
	@echo "$(GREEN)✅ All services stopped$(NC)"

clean: stop ## Stop services and clean build artifacts
	@echo "$(CYAN)🧹 Cleaning build artifacts...$(NC)"
	@find $(BACKEND_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf $(FRONTEND_DIR)/dist 2>/dev/null || true
	@rm -rf $(FRONTEND_DIR)/node_modules/.vite 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

##@ Database

db-migrate: ## Run database migrations (creates tables)
	@echo "$(CYAN)🗄️  Running database migrations...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) -c "from app.database import Base, engine; from app.models import user, category, option, image, annotation, edit_request, notification, system_settings as app_settings; Base.metadata.create_all(bind=engine); print('✅ Database tables created')"
	@echo "$(GREEN)✅ Migrations complete$(NC)"

db-seed: ## Seed database with admin users
	@echo "$(CYAN)🌱 Seeding database...$(NC)"
	@echo "$(YELLOW)Admin users will be created from SEED_ADMINS env var$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		uvicorn app.main:app --host 0.0.0.0 --port $(BACKEND_PORT) &
	@sleep 5
	@$(MAKE) clean-ports
	@echo "$(GREEN)✅ Database seeded$(NC)"

##@ Testing

test-backend: ## Run backend tests
	@echo "$(CYAN)🧪 Running backend tests...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		pytest tests/ -v

test-frontend: ## Run frontend tests
	@echo "$(CYAN)🧪 Running frontend tests...$(NC)"
	@cd $(FRONTEND_DIR) && npm test

test: test-backend test-frontend ## Run all tests

##@ Pipeline

run-pipeline: ## Run standalone master pipeline (download + deduplicate + biometric processing)
	@echo "$(CYAN)🚀 Running master pipeline...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../$(BACKEND_DIR)/.venv/bin/activate && \
		python master_pipeline.py --all
	@echo "$(GREEN)✅ Pipeline complete$(NC)"

test-pipeline: ## Test master pipeline with 10 images
	@echo "$(CYAN)🧪 Testing pipeline with limited images...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../.venv/bin/activate && \
		python master_pipeline.py --pipeline
	@echo "$(GREEN)✅ Test complete$(NC)"

process-images: ## Process Google Drive images through biometric pipeline (legacy - use run-pipeline instead)
	@echo "$(CYAN)🔐 Processing images through compliance pipeline...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) scripts/process_gdrive_only.py
	@echo "$(GREEN)✅ Images processed and uploaded to Google Drive$(NC)"

##@ Utility

check-env: ## Check if required environment files exist
	@echo "$(CYAN)🔍 Checking environment files...$(NC)"
	@if [ -f "$(BACKEND_DIR)/.env" ]; then \
		echo "$(GREEN)✅ Backend .env exists$(NC)"; \
	else \
		echo "$(RED)❌ Backend .env missing$(NC)"; \
		echo "$(YELLOW)   Copy from $(BACKEND_DIR)/.env.example$(NC)"; \
	fi
	@if [ -f "$(FRONTEND_DIR)/.env" ]; then \
		echo "$(GREEN)✅ Frontend .env exists$(NC)"; \
	else \
		echo "$(RED)❌ Frontend .env missing$(NC)"; \
		echo "$(YELLOW)   Copy from $(FRONTEND_DIR)/.env.example$(NC)"; \
	fi

setup: check-env install db-migrate ## Complete first-time setup (env check + install + db setup)
	@echo ""
	@echo "$(GREEN)🎉 Setup complete!$(NC)"
	@echo ""
	@echo "$(CYAN)Next steps:$(NC)"
	@echo "  1. Configure $(BACKEND_DIR)/.env with your credentials"
	@echo "  2. Configure $(FRONTEND_DIR)/.env with backend URL"
	@echo "  3. Run $(YELLOW)make start$(NC) to launch the application"
	@echo ""

##@ Quick Start

quick: ## Quick start (assumes dependencies are installed)
	@$(MAKE) clean-ports
	@$(MAKE) start

restart: stop start ## Restart both services

##@ Information

info: ## Show project information
	@echo "$(CYAN)📋 Photo Pets Annotation Tool$(NC)"
	@echo ""
	@echo "$(YELLOW)Project Structure:$(NC)"
	@echo "  Backend:  FastAPI + SQLAlchemy + PostgreSQL"
	@echo "  Frontend: React + Vite + TailwindCSS"
	@echo "  Pipeline: OpenCV + YOLO + InsightFace"
	@echo ""
	@echo "$(YELLOW)Ports:$(NC)"
	@echo "  Backend:  $(BACKEND_PORT)"
	@echo "  Frontend: $(FRONTEND_PORT)"
	@echo ""
	@echo "$(YELLOW)Key Files:$(NC)"
	@echo "  Backend Config:  $(BACKEND_DIR)/.env"
	@echo "  Frontend Config: $(FRONTEND_DIR)/.env"
	@echo "  Documentation:   README.md"
	@echo ""

version: ## Show version information
	@echo "$(CYAN)Version Information:$(NC)"
	@cd $(BACKEND_DIR) && source .venv/bin/activate && python --version
	@node --version
	@npm --version
