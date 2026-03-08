#!/usr/bin/env python3
"""
Setup script for Master Image Processing Pipeline
Helps initialize the environment and verify dependencies
"""

import subprocess
import sys
from pathlib import Path
import shutil

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def check_python_version():
    """Verify Python version"""
    print("\n🐍 Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} (need 3.8+)")
        return False

def install_dependencies():
    """Install required packages"""
    print("\n📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("   ✅ Dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("   ❌ Failed to install dependencies")
        return False

def create_folder_structure():
    """Create necessary folder structure"""
    print("\n📁 Creating folder structure...")
    
    folders = [
        "pipeline_workspace/01_downloaded_from_drive",
        "pipeline_workspace/deliverable",
        "biometric_compliance_pipeline/data/clean",
        "biometric_compliance_pipeline/data/obfuscated",
        "biometric_compliance_pipeline/data/qa_review",
        "biometric_compliance_pipeline/results",
    ]
    
    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)
    
    print("   ✅ Folder structure created")
    return True

def check_env_file():
    """Check if .env file exists"""
    print("\n⚙️  Checking environment configuration...")
    if Path(".env").exists():
        print("   ✅ .env file exists")
        return True
    elif Path(".env.example").exists():
        print("   ⚠️  .env file not found")
        print("   📝 Creating .env from .env.example...")
        shutil.copy(".env.example", ".env")
        print("   ✅ .env created - please edit with your credentials")
        return False
    else:
        print("   ❌ .env.example not found")
        return False

def verify_models():
    """Check if required models exist"""
    print("\n🤖 Checking AI models...")
    
    models = [
        ("biometric_compliance_pipeline/models/deploy.prototxt", "Caffe face detection"),
        ("biometric_compliance_pipeline/models/res10_300x300_ssd_iter_140000.caffemodel", "Caffe model weights"),
        ("biometric_compliance_pipeline/yolov8n.pt", "YOLO animal detection"),
    ]
    
    all_present = True
    for model_path, description in models:
        if Path(model_path).exists():
            print(f"   ✅ {description}")
        else:
            print(f"   ❌ {description} - {model_path}")
            all_present = False
    
    if not all_present:
        print("\n   ⚠️  Some models are missing.")
        print("   📥 YOLO model will be downloaded automatically on first run.")
        print("   📥 Caffe models should be in biometric_compliance_pipeline/models/")
    
    return all_present

def main():
    """Main setup routine"""
    print_header("🔄 Master Pipeline Setup")
    
    # Check Python version
    if not check_python_version():
        print("\n❌ Setup failed: Python 3.8+ required")
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Setup failed: Could not install dependencies")
        sys.exit(1)
    
    # Create folder structure
    create_folder_structure()
    
    # Check environment file
    env_ready = check_env_file()
    
    # Verify models
    models_ready = verify_models()
    
    # Final summary
    print_header("📋 Setup Summary")
    
    if env_ready and models_ready:
        print("\n✅ Setup complete! You're ready to run the pipeline.")
        print("\n🚀 Quick start:")
        print("   python master_pipeline.py --all")
    elif env_ready:
        print("\n⚠️  Setup mostly complete!")
        print("   📥 Some models are missing but will download automatically.")
        print("\n🚀 You can run the pipeline:")
        print("   python master_pipeline.py --all")
    else:
        print("\n⚠️  Setup complete with warnings:")
        if not env_ready:
            print("   • Edit .env file with your credentials")
        if not models_ready:
            print("   • Some AI models are missing (will download on first run)")
        print("\n🚀 After configuration, run:")
        print("   python master_pipeline.py --all")

if __name__ == "__main__":
    main()
