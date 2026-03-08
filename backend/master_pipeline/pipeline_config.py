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


def _read_env_file(filepath):
    """Parse a .env file directly from disk (no caching via os.environ)."""
    result = {}
    if Path(filepath).exists():
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    result[key.strip()] = value.strip()
    return result


# Identify backend .env path once (but read fresh every time in PipelineConfig)
_BACKEND_ENV_PATH = Path(__file__).parent.parent / '.env'


class PipelineConfig:
    """Central configuration for the master pipeline."""
    
    def __init__(self):
        # Fresh-read backend/.env from disk each time (never stale os.environ)
        _env = _read_env_file(_BACKEND_ENV_PATH)
        if _env:
            print(f"[Config] Fresh-read: {_BACKEND_ENV_PATH}")
        else:
            print(f"[Config] WARNING: No .env file found at {_BACKEND_ENV_PATH}")
            print("[Config] Using environment variables or defaults")

        def _get(key, default=None):
            """Get config value: .env file > os.environ > default."""
            return _env.get(key) or os.getenv(key) or default

        # Backend directory is where this file is located
        self.backend_dir = Path(__file__).parent
        
        # ==================== WORKSPACE PATHS ====================
        workspace = _get('PIPELINE_WORKSPACE', 'pipeline_workspace')
        # Workspace can be absolute or relative to backend directory
        if Path(workspace).is_absolute():
            self.workspace = Path(workspace)
        else:
            self.workspace = self.backend_dir / workspace
        
        # Stage folders
        self.downloaded_dir = self.workspace / _get('DOWNLOADED_IMAGES_DIR', '01_downloaded_from_drive')
        self.unique_dir = self.workspace / _get('UNIQUE_IMAGES_DIR', '02_unique_images')
        self.duplicate_clusters_dir = self.workspace / _get('DUPLICATE_CLUSTERS_DIR', '02_duplicate_clusters')
        self.biometric_processed_dir = self.workspace / _get('BIOMETRIC_PROCESSED_DIR', '03_biometric_processed')
        self.final_output_dir = self.workspace / _get('FINAL_OUTPUT_DIR', '04_final_output')
        
        # ==================== BIOMETRIC PIPELINE PATHS ====================
        biometric_base = _get('BIOMETRIC_PIPELINE_DIR', 'biometric_compliance_pipeline')
        self.biometric_pipeline_dir = self.backend_dir / biometric_base
        
        self.biometric_input_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_INPUT_DIR', 'data/input')
        self.biometric_output_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_OUTPUT_DIR', 'data/obfuscated')
        self.biometric_clean_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_CLEAN_DIR', 'data/clean')
        self.biometric_qa_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_QA_DIR', 'data/qa_review')
        self.biometric_results_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_RESULTS_DIR', 'results')
        self.biometric_logs_dir = self.biometric_pipeline_dir / _get('BIOMETRIC_LOGS_DIR', 'results/logs')
        
        # Biometric pipeline scripts
        self.biometric_scripts_dir = self.biometric_pipeline_dir / 'scripts'
        self.biometric_run_script = self.biometric_scripts_dir / 'stage3_obfuscate_faces_enhanced.py'
        
        # ==================== DEDUPLICATION SETTINGS ====================
        self.dedup_threshold = float(_get('DEDUP_THRESHOLD', '0.32'))
        self.use_llm_validation = (_get('USE_LLM_VALIDATION', 'false')).lower() == 'true'
        self.max_llm_validations = int(_get('MAX_LLM_VALIDATIONS', '100'))
        
        # ==================== FACE DETECTION SETTINGS ====================
        self.face_detection_confidence = float(_get('FACE_DETECTION_CONFIDENCE', '0.5'))
        self.face_verification_threshold = float(_get('FACE_VERIFICATION_THRESHOLD', '0.4'))
        self.obfuscation_method = _get('OBFUSCATION_METHOD', 'egoblur')
        self.filter_animal_faces = (_get('FILTER_ANIMAL_FACES', 'true')).lower() == 'true'
        self.yolo_model = _get('YOLO_MODEL', 'yolov8n.pt')
        
        # ==================== GOOGLE DRIVE CONFIG ====================
        self.google_drive_folder_id = _get('GOOGLE_DRIVE_FOLDER_ID')
        self.google_service_account_file = _get('GOOGLE_SERVICE_ACCOUNT_FILE')
        
        # ==================== OPENAI API ====================
        self.openai_api_key = _get('OPENAI_API_KEY')
        self.openai_model = _get('OPENAI_MODEL', 'gpt-4-vision-preview')
        
        
        # ==================== DATABASE CONFIG ====================
        self.database_url = _get('DATABASE_URL', 'sqlite:///./photo_annotation.db')
        
        # ==================== PIPELINE BEHAVIOR ====================
        self.verbose_logging = (_get('VERBOSE_LOGGING', 'true')).lower() == 'true'
        self.num_workers = int(_get('NUM_WORKERS', '4'))
        self.pipeline_timeout = int(_get('PIPELINE_TIMEOUT', '3600'))
        self.cleanup_temp_files = (_get('CLEANUP_TEMP_FILES', 'true')).lower() == 'true'
        
        # ==================== OUTPUT FORMAT ====================
        self.output_format = _get('OUTPUT_FORMAT', 'jpg')
        self.jpeg_quality = int(_get('JPEG_QUALITY', '95'))
        self.preserve_original_format = (_get('PRESERVE_ORIGINAL_FORMAT', 'true')).lower() == 'true'
        
        # ==================== DEBUG ====================
        self.debug = (_get('DEBUG', 'false')).lower() == 'true'
        self.dry_run = (_get('DRY_RUN', 'false')).lower() == 'true'
        limit_val = _get('LIMIT_IMAGES')
        self.limit_images = int(limit_val) if limit_val and limit_val != '0' else None
        
        # ==================== DEFAULT PIPELINE STEPS ====================
        self.run_download_by_default = (_get('RUN_DOWNLOAD_BY_DEFAULT', 'false')).lower() == 'true'
        self.run_deduplicate_by_default = (_get('RUN_DEDUPLICATE_BY_DEFAULT', 'false')).lower() == 'true'
        self.run_biometric_by_default = (_get('RUN_BIOMETRIC_BY_DEFAULT', 'false')).lower() == 'true'
        self.run_all_by_default = (_get('RUN_ALL_BY_DEFAULT', 'false')).lower() == 'true'
    
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
