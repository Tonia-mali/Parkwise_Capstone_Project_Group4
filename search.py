# search.py — ParkWise Nairobi
# FacilitySearch: builds sentence embeddings for all facilities at startup,
# then finds semantically similar facilities for any natural language query.
# Uses fastembed (Python 3.14 compatible, no C extension issues on Render).

import numpy as np


class FacilitySearch:
    """
    Semantic facility search using fastembed.

    Responsibilities:
      build(facilities)    — embed all facilities once at startup
      search(query, top_n) — find top N semantically similar facilities
    """

    MODEL_NAME = "BAAI/bge-small-en-v1.5"  # ~130MB, fast on CPU, fastembed default

    def __init__(self):
        self._model = None
        self._embeddings = None   # np.ndarray shape (N, 384)
        self._facility_ids = []   # osm_id in same order as embeddings
        self._ready = False

    # ── Build ─────────────────────────────────────────────────────────────────

    def build(self, facilities: dict) -> None:
        """
        Embed all facilities. Called once in the FastAPI lifespan after
        load_data() has populated the facilities dict.

        Args:
            facilities: {osm_id: facility_dict} from main.py
        """
        try:
            from fastembed import TextEmbedding
            print("[search] Loading fastembed model…")
            self._model = TextEmbedding(model_name=self.MODEL_NAME)

            texts = []
            ids   = []
            for osm_id, f in facilities.items():
                text = self._facility_text(f)
                texts.append(text)
                ids.append(osm_id)

            print(f"[search] Embedding {len(texts)} facilities…")
            embeddings_gen = self._model.embed(texts)
            self._embeddings   = np.array(list(embeddings_gen), dtype=np.float32)
            self._facility_ids = ids
            self._ready = True
            print("[search] Embeddings ready ✓")

        except Exception as e:
            print(f"[search] Build failed ({e}) — semantic search will be unavailable")
            self._ready = False

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_n: int = 10) -> list:
        """
        Return a list of osm_ids ranked by semantic similarity to the query.

        Args:
            query:  Natural language search string
            top_n:  Number of results to return

        Returns:
            List of osm_ids (ints), most similar first.
            Returns [] if embeddings are not ready.
        """
        if not self._ready or self._model is None:
            return []

        try:
            q_vec = np.array(list(self._model.embed([query]))[0], dtype=np.float32)

            # Cosine similarity
            norms  = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
            normed = self._embeddings / np.clip(norms, 1e-10, None)
            q_norm = q_vec / max(float(np.linalg.norm(q_vec)), 1e-10)
            scores = normed @ q_norm

            top_indices = np.argsort(scores)[::-1][:top_n]
            return [self._facility_ids[i] for i in top_indices]

        except Exception as e:
            print(f"[search] Query failed ({e})")
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _facility_text(f: dict) -> str:
        """Build a rich text description for each facility for better matching."""
        parts = []

        name = f.get("facility_name_clean") or f.get("display_name") or ""
        if name:
            parts.append(name)

        category = f.get("category") or ""
        if category:
            parts.append(category)

        zone = f.get("zone") or ""
        if zone:
            parts.append(f"Zone {zone}")

        tier = f.get("tier") or ""
        if "cbd" in tier.lower():
            parts.append("CBD central business district")

        rate = f.get("base_rate_kes")
        if rate is not None:
            if rate <= 100:
                parts.append("cheap budget affordable parking")
            elif rate <= 200:
                parts.append("moderate price parking")
            else:
                parts.append("premium expensive parking")

        hours = f.get("operating_hours") or ""
        if "24" in hours:
            parts.append("open 24 hours overnight all day")

        tariff = f.get("tariff_model") or ""
        if tariff:
            parts.append(tariff)

        payment = f.get("payment_channels") or ""
        if payment:
            parts.append(payment)

        security = f.get("security_score")
        if security is not None:
            if security >= 4.0:
                parts.append("safe secure attended security guard")
            elif security >= 3.0:
                parts.append("moderate security")

        capacity = f.get("estimated_capacity")
        if capacity and capacity > 100:
            parts.append("large capacity many spaces")
        elif capacity and capacity < 20:
            parts.append("small limited spaces")

        return " | ".join(parts)


# ── Shared singleton ──────────────────────────────────────────────────────────
facility_search = FacilitySearch()
