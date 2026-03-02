# 🎯 **Adding Pipeline Progress & Statistics to UI**

## **Issue:**
1. ❌ No progress bar for deduplication
2. ❌ No progress bar for biometric processing  
3. ❌ Pipeline stats missing: dedup count, failed, pending
4. ❌ No real-time updates during pipeline execution

## **Solution Overview:**

We need to add:
1. ✅ Real-time progress tracking for master pipeline
2. ✅ WebSocket or polling for live updates
3. ✅ Detailed statistics dashboard
4. ✅ Progress bars for each pipeline stage

---

## **📋 Implementation Plan:**

### **Backend Changes:**

#### **1. Create Pipeline Status Tracking**
```python
# backend/app/models/pipeline_status.py (NEW FILE)

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean
from app.database import Base
from datetime import datetime

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="pending")  # pending, running, completed, failed
    stage = Column(String, default="idle")  # download, deduplicate, biometric, consolidate
    
    # Overall progress
    total_images = Column(Integer, default=0)
    processed_images = Column(Integer, default=0)
    failed_images = Column(Integer, default=0)
    pending_images = Column(Integer, default=0)
    
    # Deduplication stats
    unique_images = Column(Integer, default=0)
    duplicate_images = Column(Integer, default=0)
    duplicate_clusters = Column(Integer, default=0)
    
    # Biometric stats
    images_with_faces = Column(Integer, default=0)
    images_without_faces = Column(Integer, default=0)
    screenshots_skipped = Column(Integer, default=0)
    
    # Progress tracking
    current_stage_progress = Column(Float, default=0.0)  # 0.0 to 100.0
    overall_progress = Column(Float, default=0.0)
    
    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)
    
    # Errors
    error_message = Column(String, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Metadata
    config = Column(JSON, nullable=True)  # Pipeline configuration used
    logs = Column(JSON, nullable=True)  # Stage-by-stage logs
```

#### **2. Add Pipeline API Endpoints**
```python
# backend/app/routers/pipeline.py (ENHANCE EXISTING)

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.pipeline_status import PipelineRun
from datetime import datetime
import subprocess
import sys

router = APIRouter()

@router.post("/api/admin/pipeline/run")
async def start_pipeline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start the master pipeline in background"""
    
    # Create pipeline run record
    pipeline_run = PipelineRun(
        status="pending",
        stage="initializing",
        started_at=datetime.now()
    )
    db.add(pipeline_run)
    db.commit()
    db.refresh(pipeline_run)
    
    # Start pipeline in background
    background_tasks.add_task(
        run_master_pipeline,
        pipeline_run.id,
        db
    )
    
    return {
        "success": True,
        "pipeline_run_id": pipeline_run.id,
        "message": "Pipeline started in background"
    }

@router.get("/api/admin/pipeline/status/{run_id}")
async def get_pipeline_status(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Get current pipeline status"""
    
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    
    if not pipeline_run:
        return {"error": "Pipeline run not found"}
    
    return {
        "status": pipeline_run.status,
        "stage": pipeline_run.stage,
        "total_images": pipeline_run.total_images,
        "processed_images": pipeline_run.processed_images,
        "failed_images": pipeline_run.failed_images,
        "pending_images": pipeline_run.pending_images,
        "unique_images": pipeline_run.unique_images,
        "duplicate_images": pipeline_run.duplicate_images,
        "duplicate_clusters": pipeline_run.duplicate_clusters,
        "images_with_faces": pipeline_run.images_with_faces,
        "images_without_faces": pipeline_run.images_without_faces,
        "screenshots_skipped": pipeline_run.screenshots_skipped,
        "current_stage_progress": pipeline_run.current_stage_progress,
        "overall_progress": pipeline_run.overall_progress,
        "started_at": pipeline_run.started_at,
        "estimated_completion": pipeline_run.estimated_completion,
        "error_message": pipeline_run.error_message
    }

@router.get("/api/admin/pipeline/stats")
async def get_pipeline_stats(db: Session = Depends(get_db)):
    """Get latest pipeline statistics"""
    
    # Get most recent completed pipeline run
    latest_run = db.query(PipelineRun).order_by(
        PipelineRun.id.desc()
    ).first()
    
    if not latest_run:
        return {
            "total_images": 0,
            "processed": 0,
            "pending": 0,
            "failed": 0,
            "unique_images": 0,
            "duplicates_found": 0
        }
    
    return {
        "total_images": latest_run.total_images,
        "processed": latest_run.processed_images,
        "pending": latest_run.pending_images,
        "failed": latest_run.failed_images,
        "unique_images": latest_run.unique_images,
        "duplicates_found": latest_run.duplicate_images,
        "duplicate_clusters": latest_run.duplicate_clusters,
        "images_with_faces": latest_run.images_with_faces,
        "images_without_faces": latest_run.images_without_faces,
        "screenshots_skipped": latest_run.screenshots_skipped,
        "status": latest_run.status,
        "last_run": latest_run.started_at
    }

async def run_master_pipeline(run_id: int, db: Session):
    """Run the master pipeline and update status"""
    
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    
    try:
        pipeline_run.status = "running"
        pipeline_run.stage = "download"
        db.commit()
        
        # Run pipeline (simplified - needs actual implementation)
        # This should call master_pipeline.py with progress callbacks
        
        # For now, simulate:
        result = subprocess.run([
            sys.executable,
            "backend/master_pipeline/master_pipeline.py",
            "--all"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            pipeline_run.status = "completed"
            pipeline_run.completed_at = datetime.now()
        else:
            pipeline_run.status = "failed"
            pipeline_run.error_message = result.stderr
        
        db.commit()
        
    except Exception as e:
        pipeline_run.status = "failed"
        pipeline_run.error_message = str(e)
        db.commit()
```

#### **3. Modify Master Pipeline to Report Progress**
```python
# backend/master_pipeline/master_pipeline.py (MODIFY EXISTING)

class MasterPipeline:
    def __init__(self, pipeline_run_id=None):
        self.pipeline_run_id = pipeline_run_id
        # ... existing init code
    
    def update_progress(self, stage, progress, **kwargs):
        """Update progress in database for real-time UI updates"""
        if not self.pipeline_run_id:
            return
        
        from app.database import SessionLocal
        from app.models.pipeline_status import PipelineRun
        
        db = SessionLocal()
        try:
            run = db.query(PipelineRun).filter(
                PipelineRun.id == self.pipeline_run_id
            ).first()
            
            if run:
                run.stage = stage
                run.current_stage_progress = progress
                
                # Update specific fields
                for key, value in kwargs.items():
                    if hasattr(run, key):
                        setattr(run, key, value)
                
                db.commit()
        finally:
            db.close()
    
    def step1_download_from_drive(self):
        """Download with progress reporting"""
        self.update_progress("download", 0)
        
        # ... existing download code with progress updates
        for i, file in enumerate(files):
            # Download logic
            progress = (i + 1) / len(files) * 100
            self.update_progress("download", progress, total_images=len(files))
        
        self.update_progress("download", 100, total_images=len(files))
    
    def step2_deduplicate(self):
        """Deduplicate with progress reporting"""
        self.update_progress("deduplicate", 0)
        
        # ... deduplication logic
        
        self.update_progress(
            "deduplicate",
            100,
            unique_images=len(unique),
            duplicate_images=len(duplicates),
            duplicate_clusters=len(clusters)
        )
    
    def step3_biometric_compliance(self):
        """Biometric processing with progress reporting"""
        self.update_progress("biometric", 0)
        
        # ... biometric processing
        for i, img in enumerate(images):
            # Process logic
            progress = (i + 1) / len(images) * 100
            self.update_progress("biometric", progress)
        
        self.update_progress(
            "biometric",
            100,
            images_with_faces=blurred_count,
            images_without_faces=clean_count,
            screenshots_skipped=skipped_count
        )
```

---

### **Frontend Changes:**

#### **1. Create Pipeline Statistics Component**
```jsx
// frontend/src/components/PipelineStatistics.jsx (NEW FILE)

import { useState, useEffect } from 'react';
import api from '../api/client';

function PipelineStatistics() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);
  
  const loadStats = async () => {
    try {
      const response = await api.get('/admin/pipeline/stats');
      setStats(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load pipeline stats:', error);
      setLoading(false);
    }
  };
  
  if (loading) return <div>Loading statistics...</div>;
  if (!stats) return null;
  
  return (
    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-4">Pipeline Statistics</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Total Images */}
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-sm text-blue-600 font-medium">Total Images</div>
          <div className="text-3xl font-bold text-blue-900 mt-1">{stats.total_images}</div>
        </div>
        
        {/* Processed */}
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-sm text-green-600 font-medium">Processed</div>
          <div className="text-3xl font-bold text-green-900 mt-1">{stats.processed}</div>
        </div>
        
        {/* Pending */}
        <div className="bg-yellow-50 rounded-lg p-4">
          <div className="text-sm text-yellow-600 font-medium">Pending</div>
          <div className="text-3xl font-bold text-yellow-900 mt-1">{stats.pending}</div>
        </div>
        
        {/* Failed */}
        <div className="bg-red-50 rounded-lg p-4">
          <div className="text-sm text-red-600 font-medium">Failed</div>
          <div className="text-3xl font-bold text-red-900 mt-1">{stats.failed}</div>
        </div>
      </div>
      
      {/* Deduplication Stats */}
      {stats.duplicates_found > 0 && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-purple-50 rounded-lg p-4">
            <div className="text-sm text-purple-600 font-medium">Unique Images</div>
            <div className="text-2xl font-bold text-purple-900 mt-1">{stats.unique_images}</div>
          </div>
          
          <div className="bg-orange-50 rounded-lg p-4">
            <div className="text-sm text-orange-600 font-medium">Duplicates Found</div>
            <div className="text-2xl font-bold text-orange-900 mt-1">{stats.duplicates_found}</div>
          </div>
          
          <div className="bg-indigo-50 rounded-lg p-4">
            <div className="text-sm text-indigo-600 font-medium">Duplicate Clusters</div>
            <div className="text-2xl font-bold text-indigo-900 mt-1">{stats.duplicate_clusters}</div>
          </div>
        </div>
      )}
      
      {/* Biometric Stats */}
      {stats.images_with_faces > 0 && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-red-50 rounded-lg p-4">
            <div className="text-sm text-red-600 font-medium">Images with Faces (Blurred)</div>
            <div className="text-2xl font-bold text-red-900 mt-1">{stats.images_with_faces}</div>
          </div>
          
          <div className="bg-green-50 rounded-lg p-4">
            <div className="text-sm text-green-600 font-medium">Images without Faces</div>
            <div className="text-2xl font-bold text-green-900 mt-1">{stats.images_without_faces}</div>
          </div>
          
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="text-sm text-gray-600 font-medium">Screenshots Skipped</div>
            <div className="text-2xl font-bold text-gray-900 mt-1">{stats.screenshots_skipped}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PipelineStatistics;
```

#### **2. Create Pipeline Progress Component**
```jsx
// frontend/src/components/PipelineProgress.jsx (NEW FILE)

import { useState, useEffect } from 'react';
import api from '../api/client';

function PipelineProgress({ runId }) {
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    if (!runId) {
      setLoading(false);
      return;
    }
    
    loadProgress();
    const interval = setInterval(loadProgress, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, [runId]);
  
  const loadProgress = async () => {
    try {
      const response = await api.get(`/admin/pipeline/status/${runId}`);
      setProgress(response.data);
      setLoading(false);
      
      // Stop polling if completed or failed
      if (response.data.status === 'completed' || response.data.status === 'failed') {
        clearInterval(interval);
      }
    } catch (error) {
      console.error('Failed to load progress:', error);
      setLoading(false);
    }
  };
  
  if (loading) return <div>Loading progress...</div>;
  if (!progress) return null;
  
  const stages = [
    { key: 'download', label: 'Download', icon: '📥' },
    { key: 'deduplicate', label: 'Deduplication', icon: '🔄' },
    { key: 'biometric', label: 'Face Detection & Blurring', icon: '🔐' },
    { key: 'consolidate', label: 'Consolidate', icon: '📦' }
  ];
  
  const currentStageIndex = stages.findIndex(s => s.key === progress.stage);
  
  return (
    <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-900">Pipeline Progress</h2>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          progress.status === 'running' ? 'bg-blue-100 text-blue-700' :
          progress.status === 'completed' ? 'bg-green-100 text-green-700' :
          progress.status === 'failed' ? 'bg-red-100 text-red-700' :
          'bg-gray-100 text-gray-700'
        }`}>
          {progress.status.charAt(0).toUpperCase() + progress.status.slice(1)}
        </span>
      </div>
      
      {/* Overall Progress Bar */}
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Overall Progress</span>
          <span>{progress.overall_progress.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-gradient-to-r from-blue-500 to-purple-500 h-3 rounded-full transition-all duration-500"
            style={{ width: `${progress.overall_progress}%` }}
          />
        </div>
      </div>
      
      {/* Stage Progress */}
      <div className="space-y-4">
        {stages.map((stage, index) => {
          const isActive = stage.key === progress.stage;
          const isCompleted = index < currentStageIndex;
          const isCurrent = index === currentStageIndex;
          
          return (
            <div key={stage.key} className={`flex items-center gap-4 ${
              isActive ? 'opacity-100' : isCompleted ? 'opacity-75' : 'opacity-40'
            }`}>
              <div className={`flex items-center justify-center w-10 h-10 rounded-full ${
                isCompleted ? 'bg-green-100 text-green-600' :
                isCurrent ? 'bg-blue-100 text-blue-600' :
                'bg-gray-100 text-gray-400'
              }`}>
                {isCompleted ? '✓' : stage.icon}
              </div>
              
              <div className="flex-1">
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium text-gray-900">{stage.label}</span>
                  {isCurrent && (
                    <span className="text-gray-600">
                      {progress.current_stage_progress.toFixed(1)}%
                    </span>
                  )}
                </div>
                
                {isCurrent && (
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${progress.current_stage_progress}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Image Stats */}
      {progress.total_images > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-200">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-gray-900">{progress.processed_images}</div>
              <div className="text-xs text-gray-500">Processed</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-900">{progress.pending_images}</div>
              <div className="text-xs text-gray-500">Pending</div>
            </div>
            {progress.unique_images > 0 && (
              <div>
                <div className="text-2xl font-bold text-purple-600">{progress.unique_images}</div>
                <div className="text-xs text-gray-500">Unique</div>
              </div>
            )}
            {progress.duplicate_images > 0 && (
              <div>
                <div className="text-2xl font-bold text-orange-600">{progress.duplicate_images}</div>
                <div className="text-xs text-gray-500">Duplicates</div>
              </div>
            )}
          </div>
        </div>
      )}
      
      {/* Error Message */}
      {progress.error_message && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="text-sm font-medium text-red-800">Error:</div>
          <div className="text-sm text-red-600 mt-1">{progress.error_message}</div>
        </div>
      )}
    </div>
  );
}

export default PipelineProgress;
```

#### **3. Add to Admin Dashboard**
```jsx
// frontend/src/pages/AdminDashboard.jsx (ADD TO EXISTING)

import PipelineStatistics from '../components/PipelineStatistics';
import PipelineProgress from '../components/PipelineProgress';

function AdminDashboard() {
  const [pipelineRunId, setPipelineRunId] = useState(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  
  const startPipeline = async () => {
    try {
      const response = await api.post('/admin/pipeline/run');
      setPipelineRunId(response.data.pipeline_run_id);
      setPipelineRunning(true);
    } catch (error) {
      console.error('Failed to start pipeline:', error);
    }
  };
  
  return (
    <div>
      {/* Existing dashboard content */}
      
      {/* Add Pipeline Statistics */}
      <PipelineStatistics />
      
      {/* Add Pipeline Progress (if running) */}
      {pipelineRunning && pipelineRunId && (
        <PipelineProgress runId={pipelineRunId} />
      )}
      
      {/* Button to start pipeline */}
      <button
        onClick={startPipeline}
        disabled={pipelineRunning}
        className="btn btn-primary"
      >
        {pipelineRunning ? 'Pipeline Running...' : 'Run Master Pipeline'}
      </button>
    </div>
  );
}
```

---

## **📋 Summary of Changes:**

### **Backend:**
1. ✅ Create `PipelineRun` model for tracking
2. ✅ Add API endpoints for status and progress
3. ✅ Modify master pipeline to report progress
4. ✅ Add database migration for new tables

### **Frontend:**
1. ✅ Create `PipelineStatistics` component
2. ✅ Create `PipelineProgress` component with progress bars
3. ✅ Add polling for real-time updates
4. ✅ Integrate into Admin Dashboard

### **Features Added:**
- ✅ Real-time progress bars for each stage
- ✅ Deduplication count in statistics
- ✅ Total, processed, pending, failed counts
- ✅ Biometric processing stats
- ✅ Live progress updates every 2 seconds
- ✅ Visual stage indicators
- ✅ Error messages display

---

## **🚀 Implementation Priority:**

**Phase 1** (Quick Fix):
- Add pipeline stats endpoint
- Create simple statistics component
- Show cached stats from last run

**Phase 2** (Real-time Progress):
- Add PipelineRun model
- Modify master pipeline for progress reporting
- Add progress component with polling

**Phase 3** (Advanced):
- Add WebSocket for instant updates
- Add estimated completion time
- Add pipeline history view

---

This comprehensive solution will give you:
- Real-time progress bars ✅
- Detailed statistics including dedup counts ✅
- Failed/pending/processed counts ✅
- Beautiful UI matching your screenshot ✅

Would you like me to implement any of these phases first?
