import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    CORS_ORIGINS: str = ""  # comma-separated origins
    SEED_ADMINS: str = "[]"  # JSON array of {username, password, full_name}
    BACKEND_URL: str = "http://localhost:8000"
    
    # AWS S3 Configuration (pulls from system env if not in .env)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET_ORIGINALS: str = "agi-ds-turing"
    AWS_S3_BUCKET_PROCESSED: str = "agi-ds-turing"
    AWS_S3_PREFIX_ORIGINALS: str = "pet-annotation/originals/"
    AWS_S3_PREFIX_PROCESSED: str = "pet-annotation/processed/"
    AWS_ROLE_ARN: str = ""
    
    class Config:
        env_file = ".env"
        extra = "allow"
        # Allow reading from system environment variables
        case_sensitive = False
        env_prefix = ""
    
    # Google Drive Service Account credentials (for migration only)
    GOOGLE_SERVICE_ACCOUNT_TYPE: str = "service_account"
    GOOGLE_SERVICE_ACCOUNT_PROJECT_ID: str = ""
    GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID: str = ""
    GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY: str = ""
    GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL: str = ""
    GOOGLE_SERVICE_ACCOUNT_CLIENT_ID: str = ""
    GOOGLE_DRIVE_FOLDER_ID: str = ""
    
    # OpenAI API Key
    OPENAI_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return []
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def seed_admins_list(self) -> list[dict]:
        try:
            return json.loads(self.SEED_ADMINS)
        except json.JSONDecodeError:
            return []
    
    @property
    def google_service_account_credentials(self) -> dict:
        """Build Google service account credentials dict from env vars"""
        return {
            "type": self.GOOGLE_SERVICE_ACCOUNT_TYPE,
            "project_id": self.GOOGLE_SERVICE_ACCOUNT_PROJECT_ID,
            "private_key_id": self.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY_ID,
            "private_key": self.GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY.replace("\\n", "\n"),
            "client_email": self.GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL,
            "client_id": self.GOOGLE_SERVICE_ACCOUNT_CLIENT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{self.GOOGLE_SERVICE_ACCOUNT_CLIENT_EMAIL}"
        }

    class Config:
        env_file = ".env"
        extra = "allow"
        # Allow reading from system environment variables
        case_sensitive = False


settings = Settings()
