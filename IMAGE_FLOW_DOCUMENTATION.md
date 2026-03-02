# 🖼️ **IMAGE FLOW: From Storage to UI**

## **Complete Journey of Images in Your Application**

---

## **📊 Visual Flow Diagram**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        IMAGE SOURCE (Storage)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │ Google Drive │  │   AWS S3     │  │  Local File  │
            │   (HEIC)     │  │ (s3://...)   │  │ (file://...) │
            └──────────────┘  └──────────────┘  └──────────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DATABASE (photo_annotation.db)                     │
│   ┌────────────────────────────────────────────────────────────┐       │
│   │  images table:                                             │       │
│   │  - id: 123                                                 │       │
│   │  - filename: "dog_photo.heic"                             │       │
│   │  - url: "https://drive.google.com/...?id=abc123"          │       │
│   │       OR "s3://my-bucket/images/dog_photo.jpg"            │       │
│   │       OR "file:///path/to/local/image.jpg"                │       │
│   └────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ (URL stored, NOT the image binary!)
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  FRONTEND (React - ImageAnnotationPage.jsx)             │
│                                                                          │
│   User opens: /annotator/image/123                                      │
│                                                                          │
│   Line 7-11: getImageUrl() function generates proxy URL:                │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │ const getImageUrl = (imageId) => {                               │ │
│   │   return `http://localhost:8000/api/images/proxy/${imageId}`;   │ │
│   │ };                                                               │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│   Line 653: Image displayed with:                                       │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │ <img src={getImageUrl(123)} alt="dog_photo.heic" />             │ │
│   │      ↓                                                           │ │
│   │ <img src="http://localhost:8000/api/images/proxy/123" />        │ │
│   └──────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTP GET Request
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             BACKEND (FastAPI - main.py Line 201-411)                    │
│                      /api/images/proxy/{image_id}                       │
│                                                                          │
│  STEP 1: Check Local Cache (Line 210-219)                              │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  📁 backend/image_cache/{image_id}.jpg                       │     │
│  │  If exists → Return immediately (FAST! ⚡)                    │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                   │                                     │
│                                   │ If NOT cached                       │
│                                   ▼                                     │
│  STEP 2: Query Database (Line 221-227)                                 │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  SELECT * FROM images WHERE id = 123                         │     │
│  │  Get image.url → "https://drive.google.com/...?id=abc123"   │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                   │                                     │
│                                   ▼                                     │
│  STEP 3: Determine Storage Type & Fetch (Line 229-353)                 │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │ IF url.startswith('s3://'):                                 │      │
│  │   → Download from AWS S3 using boto3                        │      │
│  │   → Convert HEIC to JPEG if needed                          │      │
│  │                                                              │      │
│  │ ELIF url.startswith('file://'):                             │      │
│  │   → Read from local filesystem                              │      │
│  │   → Convert HEIC to JPEG if needed                          │      │
│  │                                                              │      │
│  │ ELSE (Google Drive):                                        │      │
│  │   → Extract file_id from URL                                │      │
│  │   → Use Google Drive API (authenticated)                    │      │
│  │   → Download file content                                   │      │
│  │   → Convert HEIC/HEIF to JPEG for browser compatibility     │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                   │                                     │
│                                   ▼                                     │
│  STEP 4: Cache & Return (Line 178-200, 268, 330)                       │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Save to: backend/image_cache/123.jpg                       │      │
│  │  Return Response(content=image_bytes, media_type='image/jpeg')│    │
│  └─────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTP Response (image bytes)
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     BROWSER (User's Screen)                              │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────┐    │
│   │                                                              │    │
│   │                     🖼️ Image Displayed!                      │    │
│   │                                                              │    │
│   │              [Beautiful dog photo appears]                   │    │
│   │                                                              │    │
│   └──────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## **🔍 Detailed Explanation**

### **1. Image Storage (3 Options)**

Your system supports three storage types:

| Storage Type | URL Format | Example |
|-------------|------------|---------|
| **Google Drive** | `https://drive.google.com/...?id=FILE_ID` | `https://drive.google.com/file/d/1abc...xyz/view?id=1abc...xyz` |
| **AWS S3** | `s3://bucket-name/path/to/image.jpg` | `s3://my-photos/pets/dog123.jpg` |
| **Local File** | `file:///absolute/path/to/image.jpg` | `file:///Users/me/photos/cat.jpg` |

**Important**: The database stores ONLY the URL (text), not the actual image bytes!

---

### **2. Database Storage**

The `images` table in `photo_annotation.db` stores metadata:

```sql
CREATE TABLE images (
  id INTEGER PRIMARY KEY,
  filename TEXT,                    -- "dog_photo.heic"
  url TEXT,                         -- URL pointing to actual image
  compliance_status TEXT,
  compliance_processed BOOLEAN,
  -- ... other metadata fields
);
```

**Example row:**
```
id: 123
filename: "golden_retriever.heic"
url: "https://drive.google.com/file/d/.../view?id=1a2b3c4d"
```

---

### **3. Frontend Request Flow**

#### **Code Location**: `frontend/src/pages/ImageAnnotationPage.jsx`

```javascript
// Line 7-11: URL builder function
const getImageUrl = (imageId) => {
  if (!imageId) return '';
  // Generates: http://localhost:8000/api/images/proxy/123?t=1709398765432
  return `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/images/proxy/${imageId}?t=${Date.now()}`;
};

// Line 653: Image element
<img src={getImageUrl(data?.id)} alt={data?.filename} />
```

**Why proxy instead of direct URL?**
- ✅ Bypasses CORS restrictions (browser security)
- ✅ Handles authentication (Google Drive requires credentials)
- ✅ Converts HEIC/HEIF to JPEG (browsers can't display HEIC)
- ✅ Caches locally for fast subsequent loads
- ✅ Works with S3, local files, and Google Drive uniformly

---

### **4. Backend Proxy Endpoint**

#### **Code Location**: `backend/app/main.py` (Lines 201-411)

```python
@app.get("/api/images/proxy/{image_id}")
def proxy_image(image_id: int):
    # STEP 1: Check cache (fast path)
    cached_content, cached_mime = get_cached_image(image_id)
    if cached_content:
        return Response(content=cached_content, media_type=cached_mime)
    
    # STEP 2: Query database for URL
    img = db.query(Image).filter(Image.id == image_id).first()
    url = img.url  # Get the stored URL
    
    # STEP 3: Fetch based on storage type
    if url.startswith('s3://'):
        # Download from AWS S3
        content = download_from_s3(bucket, key)
    elif url.startswith('file://'):
        # Read from local filesystem
        with open(local_path, 'rb') as f:
            content = f.read()
    else:
        # Google Drive (default)
        service = get_drive_service()  # Authenticated
        request = service.files().get_media(fileId=file_id)
        content = request.execute()
    
    # STEP 4: Convert HEIC to JPEG if needed
    if is_heic_file:
        pil_image = PILImage.open(io.BytesIO(content))
        pil_image.save(output_buffer, format='JPEG')
        content = output_buffer.getvalue()
    
    # STEP 5: Cache for future requests
    cache_image(image_id, content, mime_type)
    
    # STEP 6: Return image bytes
    return Response(content=content, media_type='image/jpeg')
```

---

### **5. Local Caching System**

**Cache Location**: `backend/image_cache/`

```
backend/
  image_cache/
    123.jpg  ← Cached version of image ID 123
    124.jpg
    125.jpg
    ...
```

**Benefits:**
- ⚡ First request: ~2-5 seconds (download from Google Drive)
- ⚡ Subsequent requests: ~50-100ms (read from local cache)
- 💾 Reduces Google Drive API calls (quota limits)
- 📦 All images converted to JPEG for consistency

**Cache Headers:**
```http
Cache-Control: public, max-age=604800  (7 days)
X-Cache: HIT  (or MISS for first request)
X-Source: s3 / local-file / google-drive
```

---

## **🎯 Complete Example Flow**

Let's trace an actual image request:

### **User Action:**
User navigates to: `http://localhost:5173/annotator/image/123`

### **Step-by-Step:**

1. **Frontend renders**: 
   ```jsx
   <img src="http://localhost:8000/api/images/proxy/123?t=1709398765432" />
   ```

2. **Browser makes HTTP GET**:
   ```
   GET http://localhost:8000/api/images/proxy/123
   ```

3. **Backend checks cache**:
   ```
   Looking for: backend/image_cache/123.jpg
   Status: NOT FOUND (first time)
   ```

4. **Backend queries database**:
   ```sql
   SELECT * FROM images WHERE id = 123;
   Result: { id: 123, url: "https://drive.google.com/...?id=abc123" }
   ```

5. **Backend extracts file ID**:
   ```python
   file_id = "abc123"  # Extracted from Google Drive URL
   ```

6. **Backend downloads from Google Drive**:
   ```python
   service = get_drive_service()  # Uses credentials from .env
   request = service.files().get_media(fileId="abc123")
   content = request.execute()  # Downloads actual image bytes
   ```

7. **Backend converts HEIC → JPEG**:
   ```python
   # Input: dog_photo.heic (HEIC format, 2.5 MB)
   # Output: JPEG bytes (1.8 MB, browser-compatible)
   ```

8. **Backend caches**:
   ```
   Saving to: backend/image_cache/123.jpg
   ```

9. **Backend responds**:
   ```http
   HTTP/1.1 200 OK
   Content-Type: image/jpeg
   Content-Length: 1835264
   Cache-Control: public, max-age=604800
   X-Cache: MISS
   X-Source: google-drive
   
   <binary image data>
   ```

10. **Browser displays image**:
    User sees the dog photo! 🐕

### **Second Time (Cached)**:

1. **Browser requests**: Same URL
2. **Backend checks cache**: ✅ FOUND at `backend/image_cache/123.jpg`
3. **Backend responds**: Immediately (50ms, vs 3000ms first time)
4. **Headers**: `X-Cache: HIT`

---

## **🚀 Why This Architecture?**

### **Problem Without Proxy:**
```jsx
// ❌ This would NOT work:
<img src="https://drive.google.com/file/d/.../view?id=abc123" />
```

**Issues:**
- 🚫 CORS error (Google Drive blocks cross-origin requests)
- 🚫 No authentication (requires OAuth2 credentials)
- 🚫 HEIC not supported (browsers can't render it)
- 🐌 Slow (download every time)

### **Solution With Proxy:**
```jsx
// ✅ This works perfectly:
<img src="http://localhost:8000/api/images/proxy/123" />
```

**Benefits:**
- ✅ No CORS (same origin)
- ✅ Authenticated (backend handles credentials)
- ✅ JPEG conversion (browser-compatible)
- ✅ Fast (cached after first load)
- ✅ Works with S3, local files, Google Drive

---

## **📝 Configuration**

### **Frontend** (`frontend/.env`):
```env
VITE_API_URL=http://localhost:8000
```

### **Backend** (`backend/.env`):
```env
# Google Drive credentials
GOOGLE_DRIVE_CREDENTIALS_FILE=turing-genai-ws-58339643dd3f.json

# AWS S3 (if using S3)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_S3_BUCKET=your-bucket
```

---

## **🔧 How Images Get Into the Database**

### **Option 1: Google Drive Pipeline** (Most Common)
```bash
make run-pipeline
```

**What happens:**
1. Script connects to Google Drive using credentials
2. Lists all images in specified folder
3. For each image:
   - Downloads to `pipeline_workspace/`
   - Processes (deduplication, compliance checks)
   - Uploads to S3 (or keeps local)
   - Inserts row into database with URL

### **Option 2: Manual Upload via Admin**
1. Admin uploads image through UI
2. Backend saves to S3 or local storage
3. Creates database entry with URL

### **Option 3: Direct Database Insert**
```python
new_image = Image(
    filename="my_dog.jpg",
    url="s3://my-bucket/my_dog.jpg",
    compliance_processed=False
)
db.add(new_image)
db.commit()
```

---

## **📊 Summary Table**

| Component | Purpose | Location |
|-----------|---------|----------|
| **Storage** | Holds actual image files | Google Drive / S3 / Local |
| **Database** | Stores metadata + URL | `photo_annotation.db` |
| **Frontend** | Displays images to users | `ImageAnnotationPage.jsx` |
| **Proxy Endpoint** | Fetches, converts, caches | `main.py /api/images/proxy/{id}` |
| **Cache** | Speeds up repeated access | `backend/image_cache/` |

---

## **🎯 Key Takeaways**

1. **Images are NOT stored in the database** - only URLs are stored
2. **Frontend never accesses storage directly** - always goes through proxy
3. **Backend handles all complexity** - CORS, auth, conversion, caching
4. **First load is slow (~3s)** - downloading from Google Drive
5. **Subsequent loads are fast (~50ms)** - served from local cache
6. **Three storage types supported** - Google Drive, S3, local files
7. **HEIC images auto-convert** - to JPEG for browser compatibility

---

**Need to check where images are coming from?**

```bash
# Check database
sqlite3 backend/photo_annotation.db "SELECT id, filename, url FROM images LIMIT 5;"

# Check cache
ls -lh backend/image_cache/

# Monitor proxy requests
tail -f backend/logs/app.log | grep "proxy"
```

**Image not showing?**
1. Check if URL exists in database
2. Check if Google Drive credentials are valid
3. Check if image is cached: `ls backend/image_cache/{image_id}.jpg`
4. Check backend logs for errors

---

**Last Updated**: March 2, 2026  
**Related Files**:
- `frontend/src/pages/ImageAnnotationPage.jsx` (Lines 7-11, 653)
- `backend/app/main.py` (Lines 201-411)
- `backend/app/models/image.py` (Database schema)
