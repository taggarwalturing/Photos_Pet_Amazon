# Photo Pets Annotation Tool

An image annotation tool for pet photo categorization. Annotators are assigned categories by an admin and annotate images one category at a time. Features a shared queue (once any annotator completes an image for a category, it's done for everyone), admin review with inline editing and bulk approval, and automatic resume so annotators pick up where they left off.

## Architecture

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **Frontend:** React + Tailwind CSS + Vite
- **Auth:** JWT-based with `admin` and `annotator` roles

## 🚀 Quick Start with Makefile

The easiest way to get started is using the provided Makefile:

```bash
# 1. Copy and configure environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Edit .env files with your credentials

# 2. Run complete setup (installs dependencies + creates database)
make setup

# 3. Start the application
make start
```

That's it! The app will be available at http://localhost:5173

**Common Commands:**
- `make start` - Start both backend and frontend
- `make stop` - Stop all services
- `make status` - Check if services are running
- `make restart` - Restart everything
- `make help` - See all available commands

See [MAKEFILE_GUIDE.md](MAKEFILE_GUIDE.md) for complete documentation or [MAKEFILE_CHEATSHEET.txt](MAKEFILE_CHEATSHEET.txt) for a quick reference.

---

## Manual Setup

If you prefer manual setup without the Makefile:

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally
- Make (optional, for Makefile usage)

### Environment Variables

Copy the example files and update values:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

**Backend (`backend/.env`):**

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://localhost/photo_pets_annotation` |
| `SECRET_KEY` | JWT signing secret (change in production) | — |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry | `480` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:5173,http://localhost:3000` |
| `BACKEND_URL` | Backend URL | `http://localhost:8000` |
| `SEED_ADMINS` | JSON array of admin users to create on first run | See `.env.example` |

**Google Drive Configuration (for image storage):**

| Variable | Description |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_TYPE` | Always `service_account` |
| `GOOGLE_SERVICE_ACCOUNT_PROJECT_ID` | Google Cloud project ID |
| `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID` | Private key ID from service account JSON |
| `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` | Private key (with `\n` for newlines) |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL` | Service account email |
| `GOOGLE_SERVICE_ACCOUNT_CLIENT_ID` | Service account client ID |
| `GOOGLE_DRIVE_FOLDER_ID` | Folder ID from Google Drive URL |

**OpenAI Configuration (for enhanced biometric compliance):**

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o vision (used for re-processing flagged images) |

> **Note:** Share your Google Drive folder with the service account email to grant access.

**Frontend (`frontend/.env`):**

| Variable | Description | Default |
|---|---|---|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000` |

### Backend

```bash
cd backend
python -m venv .venv        # or use the project-level venv
.venv/Scripts/activate       # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend starts on `http://localhost:8000`. On first run it will:
- **Auto-create** the `photo_pets` database if it doesn't exist
- **Auto-create** all tables and run lightweight migrations
- **Seed** admin users (from `SEED_ADMINS` env var), 6 annotation categories with options, and 20 mock images (from picsum.photos)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend starts on `http://localhost:5173` and proxies API requests to the backend.

## Usage

### Admin Flow

1. Log in with admin credentials (configured in `SEED_ADMINS`)
2. **Users & Assignments** tab — create annotator accounts (with auto-generate password), assign one or more categories to each annotator
3. **Progress** tab — monitor annotation progress per annotator and category
4. **Image Status** tab — see per-image completion across all categories (paginated)
5. **Review** tab — review completed annotations:
   - Table view with image thumbnails, category columns, and annotator selections
   - Click an image to open a detail modal with a large image and all category annotations side-by-side
   - Inline edit any annotation's selected options before approving
   - Bulk approve multiple images at once via row checkboxes
   - Keyboard shortcuts: `↑↓` navigate rows, `Enter` open modal, `←→` prev/next in modal, `A` approve all pending, `?` show shortcuts

### Annotator Flow

1. Log in with annotator credentials
2. See assigned categories with progress bars (showing shared completion)
3. Click a category to start annotating — **automatically resumes** from the first unannotated image
4. For each image: select applicable options, optionally mark as duplicate
5. Use **Save & Next**, **Skip**, or **Back** to navigate
6. Keyboard shortcuts: `→`/`Enter` Save & Next, `←` Back, `S` Skip
7. Skip will **not** overwrite already-completed annotations
8. Shared queue: once any annotator completes an image for a category, other annotators skip it automatically

### Annotation Categories

- Lighting Variation
- Angle & Perspective Variation
- Environmental Context Variation
- Occlusion & Partial Visibility
- Activity & Motion
- Multi-Pet Disambiguation

Plus an optional "Is Duplicate?" flag per image.

## API Documentation

Visit `http://localhost:8000/docs` for the interactive Swagger UI.
