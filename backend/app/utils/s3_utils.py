"""AWS S3 utilities for image storage and retrieval"""
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.config import settings
import io
from typing import Optional, Tuple


def get_s3_client():
    """Create and return S3 client"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
        config=Config(signature_version='s3v4')
    )


def upload_to_s3(file_content: bytes, bucket: str, key: str, content_type: str = 'image/jpeg', prefix: str = '') -> str:
    """
    Upload file to S3
    
    Args:
        file_content: File bytes
        bucket: S3 bucket name
        key: S3 object key (path)
        content_type: MIME type
        prefix: Optional prefix to prepend to key
        
    Returns:
        S3 URL of uploaded file
    """
    s3 = get_s3_client()
    
    # Add prefix if provided
    full_key = f"{prefix}{key}" if prefix else key
    
    try:
        s3.put_object(
            Bucket=bucket,
            Key=full_key,
            Body=file_content,
            ContentType=content_type
        )
        
        # Return S3 URL
        return f"s3://{bucket}/{full_key}"
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        raise


def download_from_s3(bucket: str, key: str) -> bytes:
    """
    Download file from S3
    
    Args:
        bucket: S3 bucket name
        key: S3 object key (path)
        
    Returns:
        File bytes
    """
    s3 = get_s3_client()
    
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except ClientError as e:
        print(f"Error downloading from S3: {e}")
        raise


def generate_presigned_url(bucket: str, key: str, expiration: int = 3600) -> str:
    """
    Generate a presigned URL for temporary access to S3 object
    
    Args:
        bucket: S3 bucket name
        key: S3 object key (path)
        expiration: URL expiration time in seconds (default: 1 hour)
        
    Returns:
        Presigned URL
    """
    s3 = get_s3_client()
    
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        raise


def parse_s3_url(s3_url: str) -> Tuple[str, str]:
    """
    Parse S3 URL into bucket and key
    
    Args:
        s3_url: S3 URL (s3://bucket/key)
        
    Returns:
        Tuple of (bucket, key)
    """
    if not s3_url.startswith('s3://'):
        raise ValueError(f"Invalid S3 URL: {s3_url}")
    
    parts = s3_url.replace('s3://', '').split('/', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URL format: {s3_url}")
    
    return parts[0], parts[1]


def create_bucket_if_not_exists(bucket: str):
    """Create S3 bucket if it doesn't exist"""
    s3 = get_s3_client()
    
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"✅ Bucket '{bucket}' already exists")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            # Bucket doesn't exist, create it
            try:
                if settings.AWS_REGION == 'us-east-1':
                    s3.create_bucket(Bucket=bucket)
                else:
                    s3.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
                    )
                print(f"✅ Created bucket '{bucket}'")
            except ClientError as create_error:
                print(f"❌ Error creating bucket: {create_error}")
                raise
        else:
            print(f"❌ Error checking bucket: {e}")
            raise


def list_s3_objects(bucket: str, prefix: str = '') -> list:
    """
    List all objects in S3 bucket with given prefix
    
    Args:
        bucket: S3 bucket name
        prefix: Key prefix to filter objects
        
    Returns:
        List of object keys
    """
    s3 = get_s3_client()
    
    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        if 'Contents' not in response:
            return []
        
        return [obj['Key'] for obj in response['Contents']]
    except ClientError as e:
        print(f"Error listing S3 objects: {e}")
        raise
