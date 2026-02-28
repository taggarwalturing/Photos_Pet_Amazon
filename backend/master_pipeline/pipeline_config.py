#!/usr/bin/env python3
"""
Pipeline Configuration Management
==================================

Loads configuration from environment variables or .env file.
Provides a centralized config object for all pipeline components.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from parent backend directory (single source of truth)
backend_env = Path(__file__).parent.parent / '.env'

if backend_env.exists():
    load_dotenv(backend_env)
    print(f"[Config] Loaded: {backend_env}")
else:
    print(f"[Config] WARNING: No .env file found at {backend_env}")
    print("[Config] Using environment variables or defaults")

class PipelineConfig:
    """Central configuration for the master pipeline."""
    
    def __init__(self):
        # Backend directory is where this file is located
        self.backend_dir = Path(__file__).parent
        
        # ==================== WORKSPACE PATHS ====================
        workspace = os.getenv('PIPELINE_WORKSPACE', 'pipeline_workspace')
        # Workspace can be absolute or relative to backend directory
        if Path(workspace).is_absolute():
            self.workspace = Path(workspace)
        else:
            self.workspace = self.backend_dir / workspace
        
        # Stage folders
        self.downloaded_dir = self.workspace / os.getenv('DOWNLOADED_IMAGES_DIR', '01_downloaded_from_drive')
        self.unique_dir = self.workspace / os.getenv('UNIQUE_IMAGES_DIR', '02_unique_images')
        self.duplicate_clusters_dir = self.workspace / os.getenv('DUPLICATE_CLUSTERS_DIR', '02_duplicate_clusters')
        self.biometric_processed_dir = self.workspace / os.getenv('BIOMETRIC_PROCESSED_DIR', '03_biometric_processed')
        self.final_output_dir = self.workspace / os.getenv('FINAL_OUTPUT_DIR', '04_final_output')
        
        # ==================== BIOMETRIC PIPELINE PATHS ====================
        biometric_base = os.getenv('BIOMETRIC_PIPELINE_DIR', 'biometric_compliance_pipeline')
        self.biometric_pipeline_dir = self.backend_dir / biometric_base
        
        self.biometric_input_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_INPUT_DIR', 'data/input')
        self.biometric_output_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_OUTPUT_DIR', 'data/obfuscated')
        self.biometric_clean_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_CLEAN_DIR', 'data/clean')
        self.biometric_qa_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_QA_DIR', 'data/qa_review')
        self.biometric_results_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_RESULTS_DIR', 'results')
        self.biometric_logs_dir = self.biometric_pipeline_dir / os.getenv('BIOMETRIC_LOGS_DIR', 'results/logs')
        
        # Biometric pipeline scripts
        self.biometric_scripts_dir = self.biometric_pipeline_dir / 'scripts'
        self.biometric_run_script = self.biometric_scripts_dir / 'stage3_obfuscate_faces_enhanced.py'
        
        # ==================== DEDUPLICATION SETTINGS ====================
        self.dedup_threshold = float(os.getenv('DEDUP_THRESHOLD', '0.32'))
        self.use_llm_validation = os.getenv('USE_LLM_VALIDATION', 'false').lower() == 'true'
        self.max_llm_validations = int(os.getenv('MAX_LLM_VALIDATIONS', '100'))
        
        # ==================== FACE DETECTION SETTINGS ====================
        self.face_detection_confidence = float(os.getenv('FACE_DETECTION_CONFIDENCE', '0.5'))
        self.face_verification_threshold = float(os.getenv('FACE_VERIFICATION_THRESHOLD', '0.4'))
        self.obfuscation_method = os.getenv('OBFUSCATION_METHOD', 'egoblur')
        self.filter_animal_faces = os.getenv('FILTER_ANIMAL_FACES', 'true').lower() == 'true'
        self.yolo_model = os.getenv('YOLO_MODEL', 'yolov8n.pt')
        
        # ==================== GOOGLE DRIVE CONFIG ====================
        self.google_drive_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        self.google_service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
        
        # ==================== OPENAI API ====================
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.openai_model = os.getenv('OPENAI_MODEL', 'gpt-4-vision-preview')
        
        # ==================== AWS S3 CONFIG ====================
        self.aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        self.s3_bucket_name = os.getenv('S3_BUCKET_NAME')
        self.s3_upload_prefix = os.getenv('S3_UPLOAD_PREFIX', 'processed-images/')
        
        # ==================== DATABASE CONFIG ====================
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///./photo_annotation.db')
        
        # ==================== PIPELINE BEHAVIOR ====================
        self.verbose_logging = os.getenv('VERBOSE_LOGGING', 'true').lower() == 'true'
        self.num_workers = int(os.getenv('NUM_WORKERS', '4'))
        self.pipeline_timeout = int(os.getenv('PIPELINE_TIMEOUT', '3600'))
        self.cleanup_temp_files = os.getenv('CLEANUP_TEMP_FILES', 'true').lower() == 'true'
        
        # ==================== OUTPUT FORMAT ====================
        self.output_format = os.getenv('OUTPUT_FORMAT', 'jpg')
        self.jpeg_quality = int(os.getenv('JPEG_QUALITY', '95'))
        self.preserve_original_format = os.getenv('PRESERVE_ORIGINAL_FORMAT', 'true').lower() == 'true'
        
        # ==================== DEBUG ====================
        self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
        self.limit_images = int(os.getenv('LIMIT_IMAGES', '0')) if os.getenv('LIMIT_IMAGES') else None
        
        # ==================== DEFAULT PIPELINE STEPS ====================
        self.run_download_by_default = os.getenv('RUN_DOWNLOAD_BY_DEFAULT', 'false').lower() == 'true'
        self.run_deduplicate_by_default = os.getenv('RUN_DEDUPLICATE_BY_DEFAULT', 'false').lower() == 'true'
        self.run_biometric_by_default = os.getenv('RUN_BIOMETRIC_BY_DEFAULT', 'false').lower() == 'true'
        self.run_all_by_default = os.getenv('RUN_ALL_BY_DEFAULT', 'false').lower() == 'true'
    
    def create_directories(self):
        """Create all necessary directories for the pipeline."""
        directories = [
            self.workspace,
            self.downloaded_dir,
            self.unique_dir,
            self.duplicate_clusters_dir,
            self.biometric_processed_dir,
            self.final_output_dir,
            self.biometric_input_dir,
            self.biometric_output_dir,
            self.biometric_clean_dir,
            self.biometric_qa_dir,
            self.biometric_results_dir,
            self.biometric_logs_dir,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration.
        Returns: (is_valid, list_of_errors)
        """
        errors = []
        
        # Check critical paths exist
        if not self.biometric_pipeline_dir.exists():
            errors.append(f"Biometric pipeline directory not found: {self.biometric_pipeline_dir}")
        
        if not self.biometric_run_script.exists():
            errors.append(f"Biometric pipeline run script not found: {self.biometric_run_script}")
        
        # Validate thresholds
        if not 0 <= self.dedup_threshold <= 1:
            errors.append(f"Invalid DEDUP_THRESHOLD: {self.dedup_threshold} (must be 0-1)")
        
        if not 0 <= self.face_detection_confidence <= 1:
            errors.append(f"Invalid FACE_DETECTION_CONFIDENCE: {self.face_detection_confidence} (must be 0-1)")
        
        if not 0 <= self.face_verification_threshold <= 1:
            errors.append(f"Invalid FACE_VERIFICATION_THRESHOLD: {self.face_verification_threshold} (must be 0-1)")
        
        # Validate obfuscation method
        valid_methods = {'egoblur', 'gaussian', 'pixelate', 'solid'}
        if self.obfuscation_method not in valid_methods:
            errors.append(f"Invalid OBFUSCATION_METHOD: {self.obfuscation_method} (must be one of {valid_methods})")
        
        return (len(errors) == 0, errors)
    
    def print_config(self):
        """Print configuration summary."""
        print("=" * 70)
        print("PIPELINE CONFIGURATION")
        print("=" * 70)
        print(f"\n📁 Workspace Paths:")
        print(f"   Workspace:           {self.workspace}")
        print(f"   Downloaded:          {self.downloaded_dir.name}")
        print(f"   Unique:              {self.unique_dir.name}")
        print(f"   Duplicate Clusters:  {self.duplicate_clusters_dir.name}")
        print(f"   Biometric Processed: {self.biometric_processed_dir.name}")
        print(f"   Final Output:        {self.final_output_dir.name}")
        
        print(f"\n🔐 Biometric Pipeline:")
        print(f"   Pipeline Dir:        {self.biometric_pipeline_dir.name}")
        print(f"   Run Script:          {self.biometric_run_script.name}")
        
        print(f"\n⚙️  Settings:")
        print(f"   Dedup Threshold:     {self.dedup_threshold}")
        print(f"   Use LLM Validation:  {self.use_llm_validation}")
        print(f"   Face Detection Conf: {self.face_detection_confidence}")
        print(f"   Obfuscation Method:  {self.obfuscation_method}")
        print(f"   Filter Animals:      {self.filter_animal_faces}")
        print(f"   Output Format:       {self.output_format}")
        print(f"   Verbose Logging:     {self.verbose_logging}")
        print(f"   Debug Mode:          {self.debug}")
        
        if self.dry_run:
            print(f"\n⚠️  DRY RUN MODE ENABLED")
        
        if self.limit_images:
            print(f"\n⚠️  LIMITED TO {self.limit_images} IMAGES (testing mode)")
        
        print("=" * 70)

# Global config instance
config = PipelineConfig()

def get_config() -> PipelineConfig:
    """Get the global pipeline configuration."""
    return config

if __name__ == '__main__':
    # Test configuration
    config = get_config()
    config.print_config()
    
    is_valid, errors = config.validate()
    if is_valid:
        print("\n✅ Configuration is valid!")
    else:
        print("\n❌ Configuration errors:")
        for error in errors:
            print(f"   • {error}")
