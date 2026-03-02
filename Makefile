.PHONY: help install install-backend install-frontend install-pipeline clean-ports start stop dev backend frontend logs status health \
		download-images deduplicate-images process-biometric import-images run-pipeline pipeline-status \
		setup setup-with-images setup-fast first-time-setup run-all run-complete test-complete

# ═══════════════════════════════════════════════════════════════════════════
# Photo Pets Annotation Tool - Makefile
# ═══════════════════════════════════════════════════════════════════════════
#
# 🚀 Quick Start Commands:
#   make run-all            - Start EVERYTHING (Backend + Frontend) in background
#   make run-complete       - Complete workflow: setup + start app
#   make first-time-setup   - Interactive wizard for first-time users
#   make help               - Show all available commands
#
# 📊 Monitor Progress:
#   Frontend: http://localhost:5173
#   Flower:   http://localhost:5555
#
# ═══════════════════════════════════════════════════════════════════════════

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
BOLD := \033[1m
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
	@echo "$(BOLD)$(CYAN)═══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BOLD)$(CYAN)   Photo Pets Annotation Tool - Command Reference$(NC)"
	@echo "$(BOLD)$(CYAN)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(BOLD)$(GREEN)🚀 QUICK START:$(NC)"
	@echo "  $(BOLD)$(CYAN)make run-all$(NC)       - Start EVERYTHING (one command!)"
	@echo "  $(CYAN)make run-complete$(NC)  - Complete setup + start + process"
	@echo ""
	@echo "$(BOLD)$(GREEN)📊 MONITOR:$(NC)"
	@echo "  Frontend: $(YELLOW)http://localhost:5173$(NC)"
	@echo "  Flower:   $(YELLOW)http://localhost:5555$(NC)"
	@echo "  API:      $(YELLOW)http://localhost:8000/docs$(NC)"
	@echo ""
	@echo "$(BOLD)$(GREEN)🛑 STOP:$(NC)"
	@echo "  $(CYAN)make stop-all$(NC)      - Stop everything"
	@echo ""
	@echo "$(BOLD)$(YELLOW)📋 All Available Commands:$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(CYAN)<target>$(NC)\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(CYAN)%-28s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BOLD)$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(BOLD)$(GREEN)💡 Common Workflows:$(NC)"
	@echo ""
	@echo "  $(BOLD)First Time Setup:$(NC)"
	@echo "    1. make first-time-setup"
	@echo "    2. make run-all"
	@echo ""
	@echo "  $(BOLD)Daily Use:$(NC)"
	@echo "    1. make run-all          (starts everything)"
	@echo "    2. Open http://localhost:5173"
	@echo "    3. make stop-all         (when done)"
	@echo ""
	@echo "  $(BOLD)Add More Images:$(NC)"
	@echo "    1. Upload to Google Drive"
	@echo "    2. make run-pipeline"
	@echo ""
	@echo "$(BOLD)$(CYAN)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""

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

##@ Quick Start (One-Command Workflows)

run-all: ## 🚀 START EVERYTHING (Backend + Frontend) - ONE COMMAND!
	@echo "$(CYAN)🚀 Starting complete stack...$(NC)"
	@echo ""
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		echo "$(YELLOW)⚠️  First time setup detected...$(NC)"; \
		echo "$(CYAN)📦 Installing dependencies...$(NC)"; \
		$(MAKE) install; \
	fi
	@echo ""
	@echo "$(CYAN)🚀 Starting application servers...$(NC)"
	@sleep 2
	@$(MAKE) start
	@echo ""
	@echo "$(GREEN)$(BOLD)═══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(GREEN)$(BOLD)   ✅ APPLICATION IS RUNNING!$(NC)"
	@echo "$(GREEN)$(BOLD)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(CYAN)🌐 Access Your Application:$(NC)"
	@echo "  Frontend:  $(YELLOW)http://localhost:5173$(NC)  (Main App)"
	@echo "  API Docs:  $(YELLOW)http://localhost:8000/docs$(NC)"
	@echo ""
	@echo "$(CYAN)📊 Check Status:$(NC)"
	@echo "  Service status:    $(YELLOW)make status$(NC)"
	@echo ""
	@echo "$(CYAN)🛑 Stop Everything:$(NC)"
	@echo "  $(YELLOW)make stop-all$(NC)"
	@echo ""
	@echo "$(GREEN)$(BOLD)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""

run-complete: check-env install db-migrate start ## Complete workflow: setup + start
	@echo ""
	@echo "$(GREEN)$(BOLD)🎉 COMPLETE SETUP FINISHED!$(NC)"
	@echo "$(CYAN)Everything is running!$(NC)"

stop-all: stop ## 🛑 STOP EVERYTHING (Backend + Frontend)
	@echo ""
	@echo "$(GREEN)✅ Everything stopped$(NC)"

status-all: status ## 📊 CHECK STATUS OF EVERYTHING
	@echo ""
	@echo "$(CYAN)Full system status displayed above$(NC)"

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
	@if [ ! -d "$(BACKEND_DIR)/.venv" ]; then \
		echo "$(YELLOW)⚠️  Virtual environment not found, creating...$(NC)"; \
		cd $(BACKEND_DIR) && python3 -m venv .venv; \
		$(PIP) install --upgrade pip; \
		$(PIP) install -r requirements.txt; \
		echo "$(GREEN)✅ Virtual environment created$(NC)"; \
	fi
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

db-migrate-blur: ## Run blur tracking migration (adds blur columns to images table)
	@echo "$(CYAN)🔄 Running blur tracking migration...$(NC)"
	@cd $(BACKEND_DIR) && \
		if [ ! -d ".venv" ]; then \
			echo "$(YELLOW)Creating Python virtual environment...$(NC)"; \
			python3 -m venv .venv; \
		fi && \
		source .venv/bin/activate && \
		$(PYTHON) migrations/add_blur_tracking.py
	@echo "$(GREEN)✅ Blur tracking migration complete$(NC)"

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

download-images: ## Download images from Google Drive only
	@echo "$(CYAN)📥 Downloading images from Google Drive...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../.venv/bin/activate && \
		python master_pipeline.py --download
	@echo "$(GREEN)✅ Images downloaded to pipeline_workspace/01_downloaded_from_drive/$(NC)"

deduplicate-images: ## Remove duplicate images only
	@echo "$(CYAN)🔍 Removing duplicate images...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../.venv/bin/activate && \
		python master_pipeline.py --deduplicate
	@echo "$(GREEN)✅ Unique images saved to pipeline_workspace/02_unique_images/$(NC)"

process-biometric: ## Process images through biometric compliance pipeline only
	@echo "$(CYAN)🔐 Processing images through biometric compliance...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../.venv/bin/activate && \
		python master_pipeline.py --pipeline
	@echo "$(GREEN)✅ Processed images saved to pipeline_workspace/04_final_output/$(NC)"

import-images: ## Import processed images to database
	@echo "$(CYAN)📥 Importing processed images to database...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) import_pipeline_images.py
	@echo "$(GREEN)✅ Images imported to database$(NC)"

import-incremental: ## Import only NEW images (incremental processing)
	@echo "$(CYAN)🔄 Running incremental import (only new images)...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) import_incremental.py --full
	@echo "$(GREEN)✅ Incremental import complete$(NC)"

run-pipeline: ## Run COMPLETE pipeline (download + deduplicate + biometric + import)
	@echo "$(CYAN)🚀 Running COMPLETE master pipeline...$(NC)"
	@echo ""
	@$(MAKE) download-images
	@echo ""
	@$(MAKE) deduplicate-images
	@echo ""
	@$(MAKE) process-biometric
	@echo ""
	@$(MAKE) import-images
	@echo ""
	@echo "$(GREEN)✅ ✅ ✅ Complete pipeline finished!$(NC)"
	@echo "$(CYAN)Images are now ready for annotation in the UI$(NC)"

run-pipeline-fast: ## Run pipeline WITHOUT deduplication (faster)
	@echo "$(CYAN)⚡ Running FAST pipeline (skipping deduplication)...$(NC)"
	@echo ""
	@$(MAKE) download-images
	@echo ""
	@$(MAKE) process-biometric
	@echo ""
	@$(MAKE) import-images
	@echo ""
	@echo "$(GREEN)✅ Fast pipeline complete!$(NC)"

test-pipeline: ## Test pipeline with limited images (10 images max)
	@echo "$(CYAN)🧪 Testing pipeline with 10 images...$(NC)"
	@cd $(BACKEND_DIR)/master_pipeline && \
		source ../.venv/bin/activate && \
		LIMIT_IMAGES=10 python master_pipeline.py --download --pipeline
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) import_pipeline_images.py
	@echo "$(GREEN)✅ Test pipeline complete$(NC)"

check-new-images: ## Check how many new images are ready to process
	@echo "$(CYAN)🔍 Checking for new images...$(NC)"
	@cd $(BACKEND_DIR) && \
		source .venv/bin/activate && \
		$(PYTHON) import_incremental.py --import-only
	@echo ""

pipeline-status: ## Show pipeline workspace status
	@echo "$(CYAN)📊 Pipeline Workspace Status:$(NC)"
	@echo ""
	@if [ -d "$(BACKEND_DIR)/master_pipeline/pipeline_workspace/01_downloaded_from_drive" ]; then \
		count=$$(find $(BACKEND_DIR)/master_pipeline/pipeline_workspace/01_downloaded_from_drive -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) 2>/dev/null | wc -l | tr -d ' '); \
		echo "  📥 Downloaded: $$count images"; \
	else \
		echo "  📥 Downloaded: 0 images (folder doesn't exist)"; \
	fi
	@if [ -d "$(BACKEND_DIR)/master_pipeline/pipeline_workspace/02_unique_images" ]; then \
		count=$$(find $(BACKEND_DIR)/master_pipeline/pipeline_workspace/02_unique_images -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) 2>/dev/null | wc -l | tr -d ' '); \
		echo "  🔍 Unique:     $$count images"; \
	else \
		echo "  🔍 Unique:     0 images (folder doesn't exist)"; \
	fi
	@if [ -d "$(BACKEND_DIR)/master_pipeline/pipeline_workspace/04_final_output" ]; then \
		count=$$(find $(BACKEND_DIR)/master_pipeline/pipeline_workspace/04_final_output -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) 2>/dev/null | wc -l | tr -d ' '); \
		echo "  ✅ Processed:  $$count images"; \
	else \
		echo "  ✅ Processed:  0 images (folder doesn't exist)"; \
	fi
	@cd $(BACKEND_DIR) && \
		if [ -f "photo_annotation.db" ]; then \
			source .venv/bin/activate && \
			count=$$($(PYTHON) -c "from app.database import SessionLocal; from sqlalchemy import text; db = SessionLocal(); result = db.execute(text('SELECT COUNT(*) FROM images')).scalar(); print(result); db.close()" 2>/dev/null || echo "0"); \
			echo "  💾 In Database: $$count images"; \
		else \
			echo "  💾 In Database: 0 images (database doesn't exist)"; \
		fi
	@echo ""

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
	@echo "$(GREEN)🎉 Basic setup complete!$(NC)"
	@echo ""
	@echo "$(CYAN)Next steps:$(NC)"
	@echo "  1. Configure $(BACKEND_DIR)/.env with your credentials"
	@echo "  2. Configure $(FRONTEND_DIR)/.env with backend URL"
	@echo "  3. Run $(YELLOW)make setup-with-images$(NC) to download and process images"
	@echo "  4. Run $(YELLOW)make start$(NC) to launch the application"
	@echo ""

setup-with-images: check-env install db-migrate run-pipeline ## COMPLETE setup with image download and processing
	@echo ""
	@echo "$(GREEN)🎉 🎉 🎉 Complete setup finished!$(NC)"
	@echo ""
	@echo "$(CYAN)✅ All done! Your annotation tool is ready:$(NC)"
	@echo "  • Dependencies installed"
	@echo "  • Database created"
	@echo "  • Images downloaded from Google Drive"
	@echo "  • Images deduplicated"
	@echo "  • Faces blurred (biometric compliance)"
	@echo "  • Images imported to database"
	@echo ""
	@$(MAKE) pipeline-status
	@echo "$(YELLOW)Ready to start:$(NC) Run $(CYAN)make start$(NC)"
	@echo ""

setup-fast: check-env install db-migrate run-pipeline-fast ## Fast setup (skip deduplication)
	@echo ""
	@echo "$(GREEN)🎉 Fast setup complete!$(NC)"
	@echo ""
	@$(MAKE) pipeline-status
	@echo "$(YELLOW)Ready to start:$(NC) Run $(CYAN)make start$(NC)"
	@echo ""

first-time-setup: ## Interactive first-time setup wizard
	@echo "$(CYAN)═══════════════════════════════════════════════════════$(NC)"
	@echo "$(CYAN)   📋 Photo Pets Annotation Tool - First Time Setup$(NC)"
	@echo "$(CYAN)═══════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)This wizard will help you set up the annotation tool.$(NC)"
	@echo ""
	@echo "$(CYAN)Step 1: Environment Configuration$(NC)"
	@if [ ! -f "$(BACKEND_DIR)/.env" ]; then \
		echo "$(YELLOW)Creating backend/.env from example...$(NC)"; \
		cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env; \
		echo "$(RED)⚠️  IMPORTANT: Edit backend/.env and add your credentials!$(NC)"; \
		echo "   Required: GOOGLE_SERVICE_ACCOUNT_* and GOOGLE_DRIVE_FOLDER_ID"; \
		echo ""; \
		read -p "Press Enter after you've configured backend/.env..." dummy; \
	fi
	@if [ ! -f "$(FRONTEND_DIR)/.env" ]; then \
		echo "$(YELLOW)Creating frontend/.env from example...$(NC)"; \
		cp $(FRONTEND_DIR)/.env.example $(FRONTEND_DIR)/.env; \
	fi
	@echo ""
	@echo "$(CYAN)Step 2: Installing Dependencies$(NC)"
	@$(MAKE) install
	@echo ""
	@echo "$(CYAN)Step 3: Database Setup$(NC)"
	@$(MAKE) db-migrate
	@echo ""
	@echo "$(CYAN)Step 4: Image Processing$(NC)"
	@echo "$(YELLOW)Choose how to set up images:$(NC)"
	@echo "  1) Download and process all images (RECOMMENDED)"
	@echo "  2) Skip for now (you can run 'make run-pipeline' later)"
	@read -p "Enter choice (1 or 2): " choice; \
	if [ "$$choice" = "1" ]; then \
		$(MAKE) run-pipeline; \
	else \
		echo "$(YELLOW)Skipping image processing. Run 'make run-pipeline' when ready.$(NC)"; \
	fi
	@echo ""
	@echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"
	@echo "$(GREEN)   🎉 Setup Complete!$(NC)"
	@echo "$(GREEN)═══════════════════════════════════════════════════════$(NC)"
	@echo ""
	@$(MAKE) pipeline-status
	@echo "$(CYAN)To start the application:$(NC)"
	@echo "  $(YELLOW)make start$(NC)"
	@echo ""
	@echo "$(CYAN)Useful commands:$(NC)"
	@echo "  $(YELLOW)make pipeline-status$(NC)  - Check image processing status"
	@echo "  $(YELLOW)make run-pipeline$(NC)     - Process more images"
	@echo "  $(YELLOW)make help$(NC)             - Show all available commands"
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

