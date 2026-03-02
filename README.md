# Photos Pet Amazon - Image Annotation Tool

A comprehensive image annotation platform for pet photos with biometric compliance (automatic face blurring), duplicate detection, and multi-user annotation workflow.

## 🎯 Features

- **Biometric Compliance Pipeline**: Automatically detect and blur human faces while preserving pet details
- **Advanced Deduplication**: Remove duplicate images using perceptual hashing and feature matching
- **Multi-User Annotation**: Role-based system with admin and annotator roles
- **Review Workflow**: Admin approval system with feedback and rework tracking
- **Time Tracking**: Automatic tracking of annotation time per image
- **Multiple Storage Options**: Support for Google Drive, AWS S3, and local files
- **Image Format Conversion**: Auto-convert HEIC/HEIF to JPEG for browser compatibility
- **Performance Optimization**: Local caching and browser cache headers

## 🏗️ Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL/SQLite
- **Frontend**: React 19 + Vite + TailwindCSS + React Router
- **Image Processing**: OpenCV + YOLOv8 + InsightFace
- **Storage**: Google Drive API + AWS S3 + Local filesystem

## 📋 Prerequisites

- Python 3.12+
- Node.js 18+
- Google Drive Service Account (for image import)
- AWS S3 credentials (optional)
- PostgreSQL (optional, defaults to SQLite)

## 🚀 Quick Start

### Method 1: Interactive Setup Wizard (RECOMMENDED)

The easiest way to get started:

```bash
make first-time-setup
```

This interactive wizard will:
1. ✅ Check and create `.env` files
2. ✅ Install all dependencies (backend, frontend, pipeline)
3. ✅ Create database tables
4. ✅ Ask if you want to download and process images
5. ✅ Guide you through the entire setup process

After setup completes:
```bash
make start
```

### Method 2: Automated Complete Setup

For automated setup without prompts:

```bash
# Configure environment (IMPORTANT!)
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Edit backend/.env with your Google Drive credentials

# Run complete setup (installs + downloads + processes images)
make setup-with-images

# Start the application
make start
```

**What `setup-with-images` does:**
- Installs all dependencies
- Creates database
- Downloads images from Google Drive
- Removes duplicates
- Detects and blurs faces
- Imports images to database

### Method 3: Manual Step-by-Step

If you prefer manual control:

#### 1. Install Dependencies

```bash
make install
```

#### 2. Configure Environment

**Backend Configuration:**

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and configure:

```bash
# Database (defaults to SQLite if not set)
DATABASE_URL=sqlite:///./photo_annotation.db
# Or use PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost/photo_annotation

# Google Drive Configuration
GOOGLE_SERVICE_ACCOUNT_TYPE=service_account
GOOGLE_SERVICE_ACCOUNT_PROJECT_ID=your-project-id
GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID=your-key-id
GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n..."
GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL=your-account@project.iam.gserviceaccount.com
GOOGLE_SERVICE_ACCOUNT_CLIENT_ID=your-client-id
GOOGLE_DRIVE_FOLDER_ID=your-gdrive-folder-id

# AWS S3 (Optional)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
AWS_BUCKET_NAME=your-bucket-name

# OpenAI (Optional - for LLM-enhanced duplicate detection)
OPENAI_API_KEY=your-openai-api-key

# Security
SECRET_KEY=your-random-secret-key-here

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Admin Users (username:password,username2:password2)
SEED_ADMINS=admin:admin123,superadmin:super123
```

**Frontend Configuration:**

```bash
cp frontend/.env.example frontend/.env
```

Edit `frontend/.env`:

```bash
VITE_API_URL=http://localhost:8000
```

#### 3. Initialize Database

```bash
make db-migrate
```

#### 4. Import Images

**Run Complete Pipeline:**

```bash
# Complete pipeline (download + deduplicate + blur + import)
make run-pipeline
```

**Check Status:**

```bash
make pipeline-status
```

#### 5. Start Application

```bash
make start
```

This starts both backend and frontend servers:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 6. Login

Use the admin credentials from `SEED_ADMINS` in your `.env` file.

Default: `admin` / `admin123`

## 📖 Usage

### Admin Workflow

1. **Create Categories**: Define annotation categories (e.g., "Pet Type", "Photo Quality")
2. **Add Options**: Add choices for each category (e.g., "Dog", "Cat", "Other")
3. **Create Annotators**: Add annotator users
4. **Assign Categories**: Assign annotators to specific categories
5. **Review Annotations**: Approve or reject submitted annotations with feedback

### Annotator Workflow

1. **Select Category**: Choose assigned category to annotate
2. **Annotate Images**: Select options for each image
3. **Mark Duplicates**: Flag duplicate images
4. **Submit**: Submit annotations for review
5. **Rework**: Fix rejected annotations based on admin feedback

## 🔧 Development Commands

### Setup Commands

```bash
make first-time-setup      # Interactive setup wizard (RECOMMENDED)
make setup-with-images     # Automated complete setup with image processing
make setup-fast            # Fast setup (skip deduplication)
make setup                 # Basic setup (no images)
make check-env             # Check if .env files exist
```

### Pipeline Commands

```bash
# Complete workflows
make run-pipeline          # Full pipeline: download + dedupe + blur + import
make run-pipeline-fast     # Fast pipeline: download + blur + import (skip dedupe)
make test-pipeline         # Test with 10 images only

# Individual steps
make download-images       # Download from Google Drive only
make deduplicate-images    # Remove duplicates only
make process-biometric     # Blur faces only
make import-images         # Import to database only

# Incremental processing
make import-incremental    # Process only NEW images (smart/fast)
make check-new-images      # Check how many new images are ready

# Status
make pipeline-status       # Show image counts at each stage
```

### Running

```bash
make start                 # Start both backend and frontend
make backend               # Start backend only (port 8000)
make frontend              # Start frontend only (port 5173)
make stop                  # Stop all services
make restart               # Restart both services
make clean-ports           # Kill processes on ports 8000 and 5173
```

### Installation

```bash
make install               # Install all dependencies
make install-backend       # Install backend only
make install-frontend      # Install frontend only
make install-pipeline      # Install pipeline dependencies only
```

### Database

```bash
make db-migrate            # Create database tables
make db-seed               # Seed admin users
```

### Monitoring

```bash
make status                # Check if services are running
make health                # Health check (alias for status)
make logs                  # Show application logs
```

### Cleanup

```bash
make clean                 # Clean build artifacts
make stop                  # Stop all services
```

### Information

```bash
make help                  # Show all commands with descriptions
make info                  # Show project information
make version               # Show version information
```

## 📁 Project Structure

```
Photos_Pet_Amazon/
├── backend/
│   ├── app/                          # Main FastAPI application
│   │   ├── main.py                   # App entry point, image proxy
│   │   ├── config.py                 # Configuration management
│   │   ├── database.py               # Database connection
│   │   ├── models/                   # SQLAlchemy models
│   │   ├── routers/                  # API endpoints
│   │   ├── schemas/                  # Pydantic schemas
│   │   ├── services/                 # Business logic
│   │   └── utils/                    # Utilities (S3, Drive)
│   ├── master_pipeline/              # Image processing pipeline
│   │   ├── master_pipeline.py        # Pipeline orchestrator
│   │   ├── pipeline_config.py        # Pipeline configuration
│   │   ├── biometric_compliance_pipeline/  # Face detection & blurring
│   │   └── FaceDetectionBlur/        # Deduplication
│   ├── image_cache/                  # Cached images (not in git)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                   # Main app with routing
│   │   ├── context/                  # React context (auth)
│   │   ├── pages/                    # Page components
│   │   └── components/               # Reusable components
│   └── package.json
├── Makefile                          # Development commands
└── README.md
```

## 🗄️ Database Schema

### Users
- Admin and annotator accounts
- Role-based access control
- Password hashing with bcrypt

### Images
- File metadata and URLs
- Biometric compliance tracking
- Version control (original + processed URLs)
- AI-generated detection
- Improper image flagging

### Categories & Options
- Annotation categories (e.g., "Pet Type")
- Multiple-choice options (e.g., "Dog", "Cat")
- Display ordering

### Annotations
- Links image + annotator + category
- Selected options
- Review status (pending/approved/rejected)
- Time tracking (annotation + rework time)
- Duplicate marking

## 🔐 Security

- **Password Hashing**: bcrypt for secure password storage
- **JWT Authentication**: Token-based authentication
- **Role-Based Access Control**: Admin and annotator roles
- **Input Validation**: Pydantic schemas validate all inputs
- **SQL Injection Protection**: SQLAlchemy ORM
- **CORS Configuration**: Controlled cross-origin requests
- **Service Account Authentication**: Secure Google Drive/S3 access

## 🚀 Pipeline Details

### Master Pipeline Workflow

1. **Download**: Fetch images from Google Drive folder
2. **Deduplicate**: Find and remove duplicate images
   - Perceptual hashing
   - Feature matching (SIFT/ORB)
   - Optional LLM validation for edge cases
3. **Biometric Processing**: Detect and blur human faces
   - Face detection: InsightFace
   - Pet detection: YOLOv8
   - Blur methods: EgoBlur, Gaussian, Pixelate, Solid
   - Verification: Ensure faces are properly obscured
4. **Consolidate**: Organize processed images for annotation

### Pipeline Configuration

Edit `backend/master_pipeline/.env` or use command-line flags:

```bash
# Workspace
WORKSPACE_DIR=pipeline_workspace

# Google Drive
GOOGLE_DRIVE_FOLDER_ID=your-folder-id

# Deduplication
USE_LLM_VALIDATION=false
DEDUP_THRESHOLD=0.85
MAX_LLM_VALIDATIONS=100

# Testing
LIMIT_IMAGES=10  # Process only first N images
DRY_RUN=false

# Biometric
BLUR_METHOD=egoblur  # egoblur, gaussian, pixelate, solid
```

## 🐛 Troubleshooting

### No images showing in UI

1. Check if images are imported: `sqlite3 backend/photo_annotation.db "SELECT COUNT(*) FROM images;"`
2. Run import script: `cd backend && python import_pipeline_images.py`
3. Check if image files exist: `ls -lh backend/master_pipeline/pipeline_workspace/04_final_output/`

### Images won't load

1. Check browser console for errors
2. Verify `backend/image_cache/` is writable
3. Test image proxy: `curl http://localhost:8000/api/images/proxy/1`
4. Check file permissions on `pipeline_workspace/`

### Pipeline fails

1. Verify Google Drive credentials in `.env`
2. Check service account has access to folder
3. Ensure `pipeline_workspace/` is writable
4. Run with `--config` flag: `cd backend/master_pipeline && python master_pipeline.py --config`

### Database errors

1. Delete and recreate: `rm backend/photo_annotation.db && make db-migrate`
2. Check PostgreSQL connection (if using)
3. Run migrations manually: `cd backend && python -c "from app.database import Base, engine; Base.metadata.create_all(bind=engine)"`

### Port already in use

```bash
make clean-ports  # Kill processes on ports 8000 and 5173
```

## 📊 Performance Tips

1. **Use PostgreSQL for production**: SQLite is fine for development, but PostgreSQL performs better with multiple users
2. **Run pipeline with GPU**: Face detection is faster with GPU support (install `onnxruntime-gpu`)
3. **Adjust cache size**: Increase `image_cache/` if you have disk space
4. **Use S3 for images**: Better performance than Google Drive for large datasets
5. **Enable LLM validation sparingly**: OpenAI API calls add cost and latency

## 📝 Important Notes

### What's in Git

- ✅ Application code
- ✅ Database schema definitions
- ✅ .env.example templates
- ✅ Documentation

### What's NOT in Git (intentionally excluded)

- ❌ `photo_annotation.db` - Your local database with images
- ❌ `pipeline_workspace/*` - Processed images (549+ MB)
- ❌ `image_cache/*` - Cached images
- ❌ `.env` files - Your credentials
- ❌ `.venv/` - Python virtual environment
- ❌ `node_modules/` - npm packages
- ❌ `*.pt` - Machine learning model files

**This is correct!** Each user should:
1. Clone the repository (gets empty application)
2. Configure their own credentials
3. Run the pipeline to process their own images
4. Import images into their own database

This ensures:
- Clean repository (no large files)
- Data privacy (your images ≠ their images)
- Fast clone times
- No merge conflicts on binary data

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

[Add your license here]

## 📧 Contact

[Add contact information]

## 🙏 Acknowledgments

- FastAPI for the excellent Python web framework
- React team for the frontend library
- YOLOv8 for object detection
- InsightFace for face recognition
- Pillow for image processing
