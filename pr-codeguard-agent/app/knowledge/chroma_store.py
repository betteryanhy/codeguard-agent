"""Chroma vector store for code semantics and MR knowledge."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMA = True
except ImportError:
    chromadb = None
    HAS_CHROMA = False
    logger.warning("chromadb not installed, vector store disabled")


class ChromaStore:
    """Vector store for code chunk embeddings and MR semantics."""

    COLLECTION_CODE = "code_chunks"
    COLLECTION_MR = "mr_semantics"

    def __init__(self, persist_dir: str = "./data/chroma"):
        self._persist_dir = persist_dir
        self._client = None
        self._code_collection = None
        self._mr_collection = None

    def init_store(self):
        """Initialize Chroma client and create collections if needed."""
        if not HAS_CHROMA:
            logger.warning("Chroma not available, skipping vector store init")
            return

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Create collections (get_or_create is idempotent)
        self._code_collection = self._client.get_or_create_collection(
            name=self.COLLECTION_CODE,
            metadata={"hnsw:space": "cosine"},
        )
        self._mr_collection = self._client.get_or_create_collection(
            name=self.COLLECTION_MR,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Chroma vector store initialized at %s", self._persist_dir)

    # ------------------------------------------------------------------
    # Code chunks
    # ------------------------------------------------------------------

    def add_code_chunk(self, chunk_id: str, document: str, metadata: dict) -> bool:
        """Add or update a code chunk vector."""
        if not self._code_collection:
            return False
        try:
            self._code_collection.upsert(
                ids=[chunk_id],
                documents=[document],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error("Failed to add code chunk: %s", e)
            return False

    def add_code_chunks(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> bool:
        """Batch add code chunks."""
        if not self._code_collection:
            return False
        try:
            self._code_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            return True
        except Exception as e:
            logger.error("Failed to batch add code chunks: %s", e)
            return False

    def search_code(self, query: str, n_results: int = 5, filter: Optional[dict] = None) -> list[dict]:
        """Search code chunks by semantic similarity."""
        if not self._code_collection:
            return []
        try:
            results = self._code_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter,
            )
            items = []
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
            return items
        except Exception as e:
            logger.error("Code search failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # MR semantics
    # ------------------------------------------------------------------

    def add_mr_semantic(self, mr_id_str: str, document: str, metadata: dict) -> bool:
        """Add MR semantic vector."""
        if not self._mr_collection:
            return False
        try:
            self._mr_collection.upsert(
                ids=[mr_id_str],
                documents=[document],
                metadatas=[metadata],
            )
            return True
        except Exception as e:
            logger.error("Failed to add MR semantic: %s", e)
            return False

    def search_mr(self, query: str, n_results: int = 5, filter: Optional[dict] = None) -> list[dict]:
        """Search MR semantics by semantic similarity."""
        if not self._mr_collection:
            return []
        try:
            results = self._mr_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filter,
            )
            items = []
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
            return items
        except Exception as e:
            logger.error("MR search failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def delete_collection(self, name: str) -> bool:
        """Delete a collection entirely."""
        if not self._client:
            return False
        try:
            self._client.delete_collection(name)
            return True
        except Exception as e:
            logger.warning("Failed to delete collection '%s': %s", name, e)
            return False
