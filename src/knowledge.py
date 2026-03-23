from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config import settings
from src.models import KnowledgeSet, KnowledgeDocument, KnowledgeChunk, Restaurant

logger = logging.getLogger(__name__)


class KnowledgeManager:
    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
        if settings.openai_api_key:
            self.embeddings = OpenAIEmbeddings(
                model=settings.embedding_model,
                api_key=settings.openai_api_key,
            )
        else:
            self.embeddings = OpenAIEmbeddings(
                model=settings.openrouter_embedding_model,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
        self.fallback_embeddings = None
        if settings.openrouter_api_key and settings.openai_api_key:
            self.fallback_embeddings = OpenAIEmbeddings(
                model=settings.openrouter_embedding_model,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )

    def _embed_documents(self, chunks: list[str]) -> list[list[float]]:
        try:
            return self.embeddings.embed_documents(chunks)
        except Exception as primary_error:
            if self.fallback_embeddings:
                logger.debug("Primary embeddings failed, trying OpenRouter fallback: %s", primary_error)
                return self.fallback_embeddings.embed_documents(chunks)
            raise

    def _embed_query(self, query: str) -> list[float]:
        try:
            return self.embeddings.embed_query(query)
        except Exception as primary_error:
            if self.fallback_embeddings:
                logger.debug("Primary query embedding failed, trying OpenRouter fallback: %s", primary_error)
                return self.fallback_embeddings.embed_query(query)
            raise

    def _read_document(self, file_path: Path) -> tuple[str, str]:
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        ext = file_path.suffix.lower()
        if ext in {".md", ".txt"}:
            return ext.lstrip("."), file_path.read_text(encoding="utf-8")

        if ext == ".json":
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            return "json", json.dumps(raw, ensure_ascii=False, indent=2)

        if ext == ".pdf":
            reader = PdfReader(str(file_path))
            parts: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text.strip())
            return "pdf", "\n\n".join(parts)

        raise ValueError("Неподдерживаемый формат. Разрешены: .md, .txt, .json, .pdf")

    def _split_chunks(self, content: str) -> list[str]:
        normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip()).strip()
        if not normalized:
            return []
        if len(normalized) <= 420:
            return [normalized]

        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + 420, len(normalized))
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = end - 80
        return chunks

    def _collection_name(self, set_id: int) -> str:
        return f"{settings.qdrant_collection_prefix}_{set_id}"

    def _ensure_collection(self, set_id: int, dimension: int) -> None:
        name = self._collection_name(set_id)
        if self.client.collection_exists(name):
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )

    def _set_active(self, set_obj: KnowledgeSet):
        (
            KnowledgeSet.update(is_active=False)
            .where(KnowledgeSet.restaurant == set_obj.restaurant)
            .execute()
        )
        set_obj.is_active = True
        set_obj.save()

    def get_active_set(self, restaurant: Restaurant) -> KnowledgeSet | None:
        return (
            KnowledgeSet.select()
            .where((KnowledgeSet.restaurant == restaurant) & (KnowledgeSet.is_active == True))
            .order_by(KnowledgeSet.created_at.desc())
            .first()
        )

    def list_sets(self, restaurant: Restaurant) -> list[KnowledgeSet]:
        return (
            KnowledgeSet.select()
            .where(KnowledgeSet.restaurant == restaurant)
            .order_by(KnowledgeSet.created_at.desc())
        )

    def activate_set(self, restaurant: Restaurant, set_id: int) -> str:
        set_obj = KnowledgeSet.get_or_none(
            (KnowledgeSet.id == set_id) & (KnowledgeSet.restaurant == restaurant)
        )
        if not set_obj:
            return f"Набор знаний с id={set_id} не найден"
        self._set_active(set_obj)
        return f"Активирован набор знаний #{set_obj.id}: {set_obj.name}"

    def create_or_get_set(self, restaurant: Restaurant, set_name: str | None) -> KnowledgeSet:
        if set_name:
            return KnowledgeSet.get_or_create(
                restaurant=restaurant,
                name=set_name,
                defaults={"is_active": False},
            )[0]

        active_set = self.get_active_set(restaurant)
        if active_set:
            return active_set

        default_set = KnowledgeSet.create(
            restaurant=restaurant,
            name="Пользовательский набор",
            description="Создан автоматически при первой загрузке документа.",
            is_active=True,
        )
        return default_set

    def _save_document(
        self, knowledge_set: KnowledgeSet, file_path: Path, source_type: str, content: str
    ) -> KnowledgeDocument:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return KnowledgeDocument.create(
            knowledge_set=knowledge_set,
            title=file_path.stem,
            source_type=source_type,
            source_path=str(file_path.resolve()),
            content_hash=content_hash,
            content=content,
        )

    def _upsert_chunks(self, doc: KnowledgeDocument):
        chunks = self._split_chunks(doc.content)
        if not chunks:
            raise ValueError("Документ пустой после обработки, индексировать нечего")

        vectors = self._embed_documents(chunks)
        dim = len(vectors[0]) if vectors else 0
        if not dim:
            raise ValueError("Не удалось получить векторы для чанков")
        self._ensure_collection(doc.knowledge_set_id, dim)

        points: list[PointStruct] = []
        for idx, chunk in enumerate(chunks):
            chunk_row = KnowledgeChunk.create(
                document=doc,
                chunk_index=idx,
                content=chunk,
                metadata=json.dumps({"title": doc.title, "source_type": doc.source_type}, ensure_ascii=False),
            )
            points.append(
                PointStruct(
                    id=chunk_row.id,
                    vector=vectors[idx],
                    payload={
                        "set_id": doc.knowledge_set_id,
                        "document_id": doc.id,
                        "title": doc.title,
                        "source_path": doc.source_path,
                        "chunk_index": idx,
                        "content": chunk,
                    },
                )
            )

        self.client.upsert(
            collection_name=self._collection_name(doc.knowledge_set_id),
            points=points,
            wait=True,
        )

    def upload_document(self, restaurant: Restaurant, path: str, set_name: str | None = None) -> str:
        file_path = Path(path).expanduser().resolve()
        source_type, content = self._read_document(file_path)
        knowledge_set = self.create_or_get_set(restaurant, set_name)
        document = self._save_document(knowledge_set, file_path, source_type, content)
        self._upsert_chunks(document)

        if not self.get_active_set(restaurant):
            self._set_active(knowledge_set)

        return (
            f"Документ загружен: #{document.id} '{document.title}' ({document.source_type}), "
            f"набор #{knowledge_set.id} '{knowledge_set.name}'"
        )

    def list_documents(self, restaurant: Restaurant) -> list[KnowledgeDocument]:
        return (
            KnowledgeDocument.select()
            .join(KnowledgeSet)
            .where(KnowledgeSet.restaurant == restaurant)
            .order_by(KnowledgeDocument.created_at.desc())
        )

    def reindex_set(self, restaurant: Restaurant, set_id: int | None = None) -> str:
        target_set = None
        if set_id is None:
            target_set = self.get_active_set(restaurant)
        else:
            target_set = KnowledgeSet.get_or_none(
                (KnowledgeSet.id == set_id) & (KnowledgeSet.restaurant == restaurant)
            )
        if not target_set:
            return "Не найден набор знаний для переиндексации"

        collection_name = self._collection_name(target_set.id)
        if self.client.collection_exists(collection_name):
            self.client.delete_collection(collection_name)

        docs = list(
            KnowledgeDocument.select().where(KnowledgeDocument.knowledge_set == target_set)
        )
        if not docs:
            return f"Набор #{target_set.id} пустой, индекс не создан"

        (
            KnowledgeChunk.delete()
            .where(
                KnowledgeChunk.document.in_(
                    KnowledgeDocument.select(KnowledgeDocument.id).where(
                        KnowledgeDocument.knowledge_set == target_set
                    )
                )
            )
            .execute()
        )

        for doc in docs:
            self._upsert_chunks(doc)

        return f"Переиндексация завершена: набор #{target_set.id}, документов {len(docs)}"

    def ensure_seed_set_indexed(self, restaurant: Restaurant):
        active = self.get_active_set(restaurant)
        if not active:
            return
        has_chunks = (
            KnowledgeChunk.select()
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_set == active)
            .count()
        )
        if has_chunks > 0:
            return
        logger.info("Индексируем стартовый набор знаний: %s", active.name)
        self.reindex_set(restaurant, active.id)

    def retrieve_context(
        self,
        restaurant: Restaurant,
        query: str,
        top_k: int | None = None,
        source_title: str | None = None,
    ) -> tuple[list[dict], str]:
        active = self.get_active_set(restaurant)
        if not active:
            return [], "NO_ACTIVE_SET"

        collection_name = self._collection_name(active.id)
        if not self.client.collection_exists(collection_name):
            return [], "NO_INDEX"
        vector = self._embed_query(query)

        response = self.client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=top_k or settings.rag_top_k,
            with_payload=True,
            with_vectors=False,
        )
        results: list[dict] = []
        for point in response.points:
            if point.score < settings.rag_min_score:
                continue
            payload = point.payload or {}
            title = payload.get("title", "unknown")
            if source_title and source_title.lower() not in str(title).lower():
                continue
            results.append(
                {
                    "score": float(point.score),
                    "title": title,
                    "source_path": payload.get("source_path", ""),
                    "content": payload.get("content", ""),
                }
            )
        if not results:
            return [], "NO_RELEVANT_SNIPPETS"
        return results, "OK"
