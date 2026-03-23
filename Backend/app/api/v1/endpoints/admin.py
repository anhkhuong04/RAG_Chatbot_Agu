import os
import tempfile
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from pydantic import BaseModel
from qdrant_client.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import IngestionService
from app.service.ingestion_service import IngestionService

# Import ChatService getter for cache management
from app.api.v1.endpoints.chat import get_chat_service

# Import Prompt Service and models
from app.service.prompt_service import get_prompt_service
from app.models.prompt import PromptUpdate, PromptResponse, PromptRecord

# Import Security utilities
from app.core.security import (
    verify_admin_credentials,
    create_access_token,
    get_current_admin,
)
from app.core.config import get_settings

# DB singleton
from app.db import (
    get_database,
    get_qdrant_client,
)

router = APIRouter(prefix="/admin", tags=["Admin - Knowledge Base"])
logger = logging.getLogger(__name__)

# ============================================
# PYDANTIC MODELS
# ============================================

class UploadResponse(BaseModel):
    doc_uuid: str
    status: str


class DocumentMetadata(BaseModel):
    year: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None


class DocumentRecord(BaseModel):
    doc_uuid: str
    filename: str
    metadata: DocumentMetadata
    status: str
    created_at: datetime
    chunk_count: Optional[int] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MetadataOptionsResponse(BaseModel):
    years: List[int]
    categories: List[str]


# ============================================
# DEPENDENCIES
# ============================================

def get_mongo_collection():
    return get_database()["documents"]


def get_ingestion_service():
    return IngestionService()


# ============================================
# HELPER FUNCTIONS
# ============================================

def _get_qdrant_client_and_collection() -> tuple[Any, str]:
    qdrant_client = get_qdrant_client()
    collection_name = get_settings().database.qdrant_collection_name
    return qdrant_client, collection_name


def _collect_qdrant_documents() -> Dict[str, Dict[str, Any]]:
    qdrant_client, collection_name = _get_qdrant_client_and_collection()
    documents: Dict[str, Dict[str, Any]] = {}
    next_offset = None

    while True:
        points, next_offset = qdrant_client.scroll(
            collection_name=collection_name,
            limit=256,
            with_payload=["doc_uuid", "filename", "source_doc", "year", "category", "description"],
            with_vectors=False,
            offset=next_offset,
        )

        if not points:
            break

        for point in points:
            payload = point.payload or {}
            doc_uuid = payload.get("doc_uuid")
            if not doc_uuid:
                continue

            record = documents.setdefault(
                doc_uuid,
                {
                    "doc_uuid": doc_uuid,
                    "filename": payload.get("filename") or payload.get("source_doc") or f"Recovered-{doc_uuid[:8]}",
                    "metadata": {
                        "year": payload.get("year"),
                        "category": payload.get("category"),
                        "description": payload.get("description"),
                    },
                    "chunk_count": 0,
                },
            )

            record["chunk_count"] += 1

            # Fill missing values from later points when needed.
            if not record["filename"] and (payload.get("filename") or payload.get("source_doc")):
                record["filename"] = payload.get("filename") or payload.get("source_doc")
            if record["metadata"].get("year") is None and payload.get("year") is not None:
                record["metadata"]["year"] = payload.get("year")
            if not record["metadata"].get("category") and payload.get("category"):
                record["metadata"]["category"] = payload.get("category")
            if not record["metadata"].get("description") and payload.get("description"):
                record["metadata"]["description"] = payload.get("description")

        if next_offset is None:
            break

    return documents


def _reconcile_mongo_documents_from_qdrant(collection) -> int:
    qdrant_docs = _collect_qdrant_documents()
    if not qdrant_docs:
        return 0

    existing_doc_uuids = set(collection.distinct("doc_uuid"))
    recovered_count = 0

    for doc_uuid, qdrant_doc in qdrant_docs.items():
        if doc_uuid in existing_doc_uuids:
            continue

        now = datetime.now()
        collection.insert_one(
            {
                "doc_uuid": doc_uuid,
                "filename": qdrant_doc["filename"],
                "metadata": qdrant_doc["metadata"],
                "status": "INDEXED",
                "storage_type": "qdrant",
                "chunk_count": qdrant_doc["chunk_count"],
                "created_at": now,
                "indexed_at": now,
                "recovered_from_qdrant": True,
            }
        )
        recovered_count += 1

    return recovered_count


def _count_and_delete_qdrant_vectors(doc_uuid: str) -> int:
    qdrant_client, collection_name = _get_qdrant_client_and_collection()
    qdrant_filter = Filter(
        must=[
            FieldCondition(
                key="doc_uuid",
                match=MatchValue(value=doc_uuid),
            )
        ]
    )

    count_result = qdrant_client.count(
        collection_name=collection_name,
        count_filter=qdrant_filter,
        exact=True,
    )
    qdrant_deleted = int(getattr(count_result, "count", 0) or 0)

    qdrant_client.delete(
        collection_name=collection_name,
        points_selector=qdrant_filter,
    )

    return qdrant_deleted


def _get_default_metadata_options() -> MetadataOptionsResponse:
    current_year = datetime.now().year
    return MetadataOptionsResponse(
        years=[current_year + 1, current_year],
        categories=["Tuyển sinh", "Học phí", "Điểm chuẩn", "Khác"],
    )


# ============================================
# AUTH ENDPOINT
# ============================================

@router.post("/login", response_model=TokenResponse)
async def admin_login(body: LoginRequest):
    if not verify_admin_credentials(body.username, body.password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
        )

    token = create_access_token(data={"sub": body.username})
    return TokenResponse(access_token=token)


@router.get("/metadata-options", response_model=MetadataOptionsResponse)
async def get_metadata_options(_admin: str = Depends(get_current_admin)):
    default_options = _get_default_metadata_options()

    try:
        collection = get_mongo_collection()

        # Get distinct years from ingested documents
        raw_years = collection.distinct("metadata.year")
        years: List[int] = []
        for year in raw_years:
            try:
                years.append(int(year))
            except (TypeError, ValueError):
                continue
        years = sorted(set(years), reverse=True)
        if not years:
            years = default_options.years

        # Get distinct categories from ingested documents
        raw_categories = collection.distinct("metadata.category")
        categories = sorted(
            {
                str(cat).strip()
                for cat in raw_categories
                if isinstance(cat, str) and str(cat).strip()
            }
        )

        # Keep default display order first, then append unknown categories
        ordered_categories: List[str] = []
        for default_cat in default_options.categories:
            if default_cat in categories:
                ordered_categories.append(default_cat)

        for cat in categories:
            if cat not in ordered_categories:
                ordered_categories.append(cat)

        if not ordered_categories:
            ordered_categories = default_options.categories

        return MetadataOptionsResponse(years=years, categories=ordered_categories)

    except Exception:
        return default_options


# ============================================
# ENDPOINTS (protected)
# ============================================

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload (PDF, TXT, DOCX, RTF, CSV, JPG, PNG)"),
    year: int = Form(..., description="Document year (e.g., 2026)"),
    category: str = Form(..., description="Document category (e.g., Admissions)"),
    description: Optional[str] = Form(None, description="Optional description"),
    _admin: str = Depends(get_current_admin),
):
    if not IngestionService.is_supported_file(file.filename):
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed: {', '.join(IngestionService.SUPPORTED_EXTENSIONS)}"
        )
    
    # Get file extension for temp file suffix
    file_ext = IngestionService.get_file_extension(file.filename)
    
    # Create temp file
    temp_file = None
    try:
        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name
        
        # Prepare metadata
        metadata = {
            "year": year,
            "category": category,
            "description": description,
            "original_filename": file.filename
        }
        
        # Process file with IngestionService
        ingestion_service = get_ingestion_service()
        doc_uuid = ingestion_service.process_file(temp_path, metadata)
        
        if doc_uuid is None:
            try:
                failed_doc = get_mongo_collection().find_one(
                    {
                        "filename": file.filename,
                        "status": "FAILED",
                    },
                    sort=[("created_at", -1)],
                )
                if failed_doc:
                    logger.error(
                        "Document processing failed for '%s': %s",
                        file.filename,
                        failed_doc.get("error", "unknown error"),
                    )
                else:
                    logger.error(
                        "Document processing failed for '%s' but no FAILED record found in MongoDB",
                        file.filename,
                    )
            except Exception:
                logger.exception("Failed to fetch FAILED document record for '%s'", file.filename)

            raise HTTPException(
                status_code=500,
                detail="Failed to process document. Check server logs."
            )
        
        return UploadResponse(doc_uuid=doc_uuid, status="success")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled exception while uploading '%s'", file.filename)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )
    finally:
        # Clean up temp file
        if temp_file and os.path.exists(temp_path):
            os.unlink(temp_path)


@router.get("/documents", response_model=List[DocumentRecord])
async def list_documents(_admin: str = Depends(get_current_admin)):
    try:
        collection = get_mongo_collection()

        # Self-heal admin listing after Mongo reset by recovering records from Qdrant.
        try:
            recovered = _reconcile_mongo_documents_from_qdrant(collection)
            if recovered:
                logger.info(f"Recovered {recovered} document records from Qdrant into MongoDB")
        except Exception as recover_error:
            logger.warning(f"Failed to reconcile MongoDB from Qdrant: {recover_error}")
        
        # Fetch all documents, sorted by created_at descending
        cursor = collection.find({}).sort("created_at", -1)
        
        documents = []
        for doc in cursor:
            documents.append(DocumentRecord(
                doc_uuid=doc.get("doc_uuid", ""),
                filename=doc.get("filename", ""),
                metadata=DocumentMetadata(
                    year=doc.get("metadata", {}).get("year"),
                    category=doc.get("metadata", {}).get("category"),
                    description=doc.get("metadata", {}).get("description")
                ),
                status=doc.get("status", "UNKNOWN"),
                created_at=doc.get("created_at", datetime.now()),
                chunk_count=doc.get("chunk_count"),
                error=doc.get("error")
            ))
        
        return documents
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching documents: {str(e)}"
        )


@router.delete("/documents/{doc_uuid}")
async def delete_document(doc_uuid: str, _admin: str = Depends(get_current_admin)):
    try:
        collection = get_mongo_collection()
        
        # Step 1: Check if document exists in MongoDB
        doc = collection.find_one({"doc_uuid": doc_uuid})
        if not doc:
            # Mongo may have been reset; still allow deletion directly from Qdrant.
            try:
                qdrant_deleted = _count_and_delete_qdrant_vectors(doc_uuid)
                if qdrant_deleted <= 0:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Document with uuid '{doc_uuid}' not found in MongoDB or Qdrant"
                    )

                return {
                    "status": "deleted",
                    "doc_uuid": doc_uuid,
                    "mongodb_deleted": False,
                    "qdrant_vectors_deleted": qdrant_deleted,
                    "note": "Deleted from Qdrant only (MongoDB metadata was missing)",
                }
            except HTTPException:
                raise
            except Exception as qdrant_only_error:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to delete orphaned Qdrant document: {str(qdrant_only_error)}"
                )
        
        # Step 2: Delete vectors from Qdrant
        qdrant_deleted = 0
        try:
            qdrant_deleted = _count_and_delete_qdrant_vectors(doc_uuid)
            if qdrant_deleted > 0:
                logger.info(f"Deleted ~{qdrant_deleted} vectors from Qdrant for doc: {doc_uuid}")
        except Exception as qdrant_error:
            logger.warning(f"Failed to delete Qdrant vectors: {qdrant_error}")
        
        # Step 3: Delete from MongoDB documents collection
        result = collection.delete_one({"doc_uuid": doc_uuid})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Document with uuid '{doc_uuid}' not found"
            )
        
        # Step 4: Clear ChatService cache to use fresh data
        cache_result = {}
        try:
            chat_service = get_chat_service()
            cache_result = chat_service.clear_cache()
            logger.info("Cache cleared after document deletion")
        except Exception as cache_error:
            logger.warning(f"Failed to clear cache: {cache_error}")
            cache_result = {"status": "error", "error": str(cache_error)}
        
        return {
            "status": "deleted",
            "doc_uuid": doc_uuid,
            "mongodb_deleted": True,
            "qdrant_vectors_deleted": qdrant_deleted,
            "cache_cleared": cache_result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting document: {str(e)}"
        )


@router.post("/clear-cache")
async def clear_cache(_admin: str = Depends(get_current_admin)):
    try:
        chat_service = get_chat_service()
        result = chat_service.clear_cache()
        
        # Also clear prompt cache
        try:
            prompt_service = get_prompt_service()
            prompt_service.invalidate_cache()
            result["prompt_cache_cleared"] = True
        except Exception as prompt_err:
            result["prompt_cache_cleared"] = False
            result["prompt_cache_error"] = str(prompt_err)
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "message": "Cache cleared and reloaded successfully",
                "details": result
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to clear cache: {result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing cache: {str(e)}"
        )


# ============================================
# PROMPT MANAGEMENT ENDPOINTS
# ============================================

@router.get("/prompts", response_model=List[PromptResponse])
async def list_prompts(_admin: str = Depends(get_current_admin)):
    try:
        service = get_prompt_service()
        prompts = service.list_prompts()
        return prompts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch prompts: {str(e)}")


@router.get("/prompts/{intent_name}", response_model=PromptResponse)
async def get_prompt(intent_name: str, _admin: str = Depends(get_current_admin)):
    service = get_prompt_service()
    prompt = service.get_prompt(intent_name)
    if not prompt:
        raise HTTPException(status_code=404, detail=f"Prompt '{intent_name}' not found")
    return prompt


@router.get("/debug-db")
async def debug_db():
    collection = get_mongo_collection()
    docs = list(collection.find({}, {"doc_uuid": 1, "filename": 1, "storage_type": 1, "_id": 0}))

    return {
        "documents": docs,
        "total_count": len(docs),
    }


@router.put("/prompts/{intent_name}", response_model=PromptResponse)
async def update_prompt(intent_name: str, update: PromptUpdate, _admin: str = Depends(get_current_admin)):
    service = get_prompt_service()

    # Verify prompt exists
    existing = service.get_prompt(intent_name)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Prompt '{intent_name}' not found")

    updated = service.update_prompt(intent_name, update)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update prompt")

    return updated


@router.post("/prompts", response_model=PromptResponse, status_code=201)
async def create_prompt(record: PromptRecord, _admin: str = Depends(get_current_admin)):
    service = get_prompt_service()

    # Check for duplicates
    existing = service.get_prompt(record.intent_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Prompt '{record.intent_name}' already exists. Use PUT to update."
        )

    try:
        created = service.create_prompt(record)
        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create prompt: {str(e)}")
