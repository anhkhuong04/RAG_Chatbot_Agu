import logging
import threading
from datetime import datetime
from typing import Dict, Optional, List
from pymongo import ReturnDocument
from dotenv import load_dotenv
from app.service.prompts.intent_prompts import INTENT_PROMPTS as HARDCODED_INTENT_PROMPTS
from app.models.prompt import PromptRecord, PromptUpdate
from app.db import get_database

load_dotenv()
logger = logging.getLogger(__name__)


class PromptService:
    def __init__(self):
        self.db = get_database("university_db")
        self.collection = self.db["prompts"]

        self._cache: Optional[Dict[str, str]] = None
        self._full_cache: Optional[Dict[str, dict]] = None
        self._cache_lock = threading.Lock()

        # Ensure unique index on intent_name
        self.collection.create_index("intent_name", unique=True)

        # Seed defaults if collection is empty
        self._seed_defaults_if_empty()


    def _seed_defaults_if_empty(self):
        if self.collection.count_documents({}) > 0:
            logger.info(
                f"Prompts collection already has {self.collection.count_documents({})} documents — skipping seed."
            )
            return

        logger.info("Seeding prompts collection with hardcoded defaults...")
        now = datetime.utcnow()

        # Description mapping for better admin UX
        descriptions = {
            "general": "Prompt chung cho các câu hỏi tuyển sinh tổng quát",
            "diem_chuan": "Prompt cho câu hỏi về điểm chuẩn các ngành",
            "hoc_phi": "Prompt cho câu hỏi về học phí, chi phí học tập",
            "career_advice": "Prompt cho câu hỏi về tư vấn nghề nghiệp, cơ hội việc làm",
        }

        for intent_name, user_template in HARDCODED_INTENT_PROMPTS.items():
            doc = {
                "intent_name": intent_name,
                "system_prompt": "",
                "user_template": user_template,
                "description": descriptions.get(intent_name, f"Prompt cho intent: {intent_name}"),
                "is_active": True,
                "updated_at": now,
                "created_at": now,
            }
            try:
                self.collection.insert_one(doc)
                logger.info(f"Seeded prompt: {intent_name}")
            except Exception as e:
                logger.warning(f"Failed to seed prompt {intent_name}: {e}")

    # ============================================
    # CACHE MANAGEMENT
    # ============================================

    def _load_cache(self):
        with self._cache_lock:
            if self._cache is not None:
                return  # Already loaded

            try:
                cursor = self.collection.find({"is_active": True})
                self._cache = {}
                self._full_cache = {}

                for doc in cursor:
                    intent = doc["intent_name"]
                    self._cache[intent] = doc.get("user_template", "")
                    # Store full doc for reference (without _id)
                    doc_copy = {k: v for k, v in doc.items() if k != "_id"}
                    self._full_cache[intent] = doc_copy

                logger.info(f"Loaded {len(self._cache)} prompts into cache")

                # If cache is empty (all inactive or DB issue), fallback
                if not self._cache:
                    logger.warning("No active prompts in DB — using hardcoded fallback")
                    self._cache = dict(HARDCODED_INTENT_PROMPTS)

            except Exception as e:
                logger.error(f"Failed to load prompts from MongoDB: {e}")
                self._cache = dict(HARDCODED_INTENT_PROMPTS)
                self._full_cache = {}

    def invalidate_cache(self):
        with self._cache_lock:
            self._cache = None
            self._full_cache = None
            logger.info("Prompt cache invalidated")


    # PROMPT ACCESS (used by ChatService)

    def get_intent_prompt(self, intent: str) -> str:
        self._load_cache()
        return self._cache.get(intent, self._cache.get("general", ""))

    def get_all_prompts(self) -> Dict[str, str]:
        self._load_cache()
        return dict(self._cache)

    # CRUD OPERATIONS (used by Admin API)

    def list_prompts(self) -> List[dict]:
        cursor = self.collection.find({}).sort("intent_name", 1)
        results = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results

    def get_prompt(self, intent_name: str) -> Optional[dict]:
        doc = self.collection.find_one({"intent_name": intent_name})
        if doc:
            doc.pop("_id", None)
        return doc

    def update_prompt(self, intent_name: str, update: PromptUpdate) -> Optional[dict]:
        update_dict = {
            k: v for k, v in update.model_dump().items() if v is not None
        }
        if not update_dict:
            return self.get_prompt(intent_name)

        update_dict["updated_at"] = datetime.utcnow()

        result = self.collection.find_one_and_update(
            {"intent_name": intent_name},
            {"$set": update_dict},
            return_document=ReturnDocument.AFTER,
        )

        if result:
            result.pop("_id", None)
            # Invalidate cache so next chat request picks up changes
            self.invalidate_cache()
            logger.info(f"Updated prompt: {intent_name}")

        return result

    def create_prompt(self, record: PromptRecord) -> dict:
        doc = record.model_dump()
        doc["created_at"] = datetime.utcnow()
        doc["updated_at"] = datetime.utcnow()
        self.collection.insert_one(doc)
        doc.pop("_id", None)
        self.invalidate_cache()
        logger.info(f"Created prompt: {record.intent_name}")
        return doc



_prompt_service_instance: Optional[PromptService] = None
_prompt_service_lock = threading.Lock()


def get_prompt_service() -> PromptService:
    global _prompt_service_instance
    if _prompt_service_instance is None:
        with _prompt_service_lock:
            if _prompt_service_instance is None:
                _prompt_service_instance = PromptService()
    return _prompt_service_instance
