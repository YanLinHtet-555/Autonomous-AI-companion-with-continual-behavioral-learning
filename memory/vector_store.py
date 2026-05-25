import os
import json
import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False


class VectorStore:
    """
    FAISS-based semantic memory search.
    Embeds experience texts and allows similarity search —
    the AI can retrieve the most relevant past experiences
    when responding or generating suggestions.
    """

    def __init__(self, index_path, embed_dim=384):
        self.index_path = index_path
        self.meta_path = index_path + ".meta.json"
        self.embed_dim = embed_dim
        self._index = None
        self._metadata = []  # parallel list to index vectors
        self._encoder = None
        self._ready = False
        self._init()

    def _init(self):
        if not FAISS_AVAILABLE:
            print("[VectorStore] faiss not available — semantic search disabled")
            return
        if not ST_AVAILABLE:
            print("[VectorStore] sentence-transformers not available — semantic search disabled")
            return

        self._encoder = SentenceTransformer("all-MiniLM-L6-v2")

        if os.path.exists(self.index_path):
            self._index = faiss.read_index(self.index_path)
            with open(self.meta_path) as f:
                self._metadata = json.load(f)
        else:
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
            self._index = faiss.IndexFlatL2(self.embed_dim)

        self._ready = True

    def add(self, text: str, metadata: dict = None):
        if not self._ready:
            return
        vec = self._encoder.encode([text], normalize_embeddings=True)
        self._index.add(np.array(vec, dtype=np.float32))
        self._metadata.append({"text": text[:200], **(metadata or {})})
        self._save()

    def search(self, query: str, top_k: int = 5):
        if not self._ready or self._index.ntotal == 0:
            return []
        vec = self._encoder.encode([query], normalize_embeddings=True)
        distances, indices = self._index.search(
            np.array(vec, dtype=np.float32), min(top_k, self._index.ntotal)
        )
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self._metadata):
                results.append({
                    "text": self._metadata[idx].get("text", ""),
                    "score": float(1 / (1 + dist)),
                    "meta": self._metadata[idx],
                })
        return results

    def _save(self):
        if not self._ready:
            return
        faiss.write_index(self._index, self.index_path)
        with open(self.meta_path, "w") as f:
            json.dump(self._metadata, f)

    def size(self):
        return self._index.ntotal if self._ready else 0
