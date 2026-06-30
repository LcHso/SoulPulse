import os
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from core.database import get_db

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    checks = {}
    overall_healthy = True
    
    # Check Database (PostgreSQL or SQLite)
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        overall_healthy = False
    
    # Check ChromaDB
    try:
        import chromadb
        # Try to create/access the client
        chroma_path = os.getenv("CHROMA_PERSIST_DIRECTORY", "./chroma_data")
        client = chromadb.PersistentClient(path=chroma_path)
        client.heartbeat()  # Basic connectivity check
        checks["vector_db"] = "ok"
    except Exception as e:
        checks["vector_db"] = f"error: {str(e)}"
        overall_healthy = False
    
    # Environment info
    env = os.getenv("ENV", "unknown")
    db_url = os.getenv("DATABASE_URL", "sqlite")
    db_type = "postgresql" if "postgresql" in db_url or "postgres" in db_url else "sqlite"
    
    status = "healthy" if overall_healthy else "unhealthy"
    status_code = 200 if overall_healthy else 503
    
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "checks": checks,
            "env": env,
            "db_type": db_type
        }
    )
