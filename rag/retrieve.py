"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json

import numpy as np
from pythainlp.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs

METHODS = ("tfidf", "hybrid")
BM25_WEIGHT = 0.3  # เลือกจากชุด dev: 0.2–0.4 ได้ hit@1 = 1.0 ส่วน 0.5 ทำให้ Q01 พลาด

# คำพ้องสำหรับขยายคำค้น สร้างจากคำถามชุด dev ที่ค้นพลาดเท่านั้น
# คีย์คือคำที่ผู้ใช้พิมพ์ ค่าคือคำทางการที่เอกสารใช้
SYNONYMS: dict[str, list[str]] = {
    # Q35 "เสียบชาร์จรถอีวีที่ออฟฟิศได้นานแค่ไหน" เอกสาร FA-01 ใช้ "รถยนต์ไฟฟ้า" และ "จุดชาร์จ"
    "อีวี": ["รถยนต์ไฟฟ้า"],
    "เสียบชาร์จ": ["จุดชาร์จ"],
    "นานแค่ไหน": ["ครั้งละไม่เกิน", "ชั่วโมง"],
}


def index_text(c: dict) -> str:
    return f"{c['title']}\n{c['section']}\n{c['text']}"


def tokenize(text: str) -> list[str]:
    return [t for t in word_tokenize(text.lower(), engine="newmm") if t.strip()]


def expand_query(query: str) -> str:
    extra = [w for key, words in SYNONYMS.items() if key in query for w in words]
    return " ".join([query, *extra])


def rescale(scores: np.ndarray) -> np.ndarray:
    top = scores.max()
    return scores / top if top > 0 else scores


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method not in METHODS:
            raise ValueError(f"method ต้องเป็นหนึ่งใน {METHODS}")
        self.chunks = chunk_docs() if chunks is None else chunks
        self.method = method
        texts = [index_text(c) for c in self.chunks]
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform(texts)
        if method == "hybrid":
            self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def scores(self, query: str) -> np.ndarray:
        if self.method == "tfidf":
            return cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        # hybrid: ปรับคะแนนแต่ละแบบให้สูงสุดเป็น 1 ก่อนรวม เพราะสเกลของ BM25 ไม่ตายตัว
        query = expand_query(query)
        tfidf = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        bm25 = np.asarray(self.bm25.get_scores(tokenize(query)))
        return (1 - BM25_WEIGHT) * rescale(tfidf) + BM25_WEIGHT * rescale(bm25)

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        scores = self.scores(query)
        order = scores.argsort()[::-1]
        results = []
        for i in order:
            c = self.chunks[i]
            if not include_superseded and c["status"] != "active":
                continue
            results.append({**c, "score": float(scores[i])})
            if len(results) == k:
                break
        return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--method", default="tfidf")
    ap.add_argument("--include-superseded", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = Retriever(method=a.method).search(a.query, k=a.k, include_superseded=a.include_superseded)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for r in res:
        print(f"[{r['score']:.3f}] {r['chunk_id']} · {r['title']} · {r['section']} ({r['status']}, {r['effective_date']})")
        print("   " + r["text"].replace("\n", " ")[:160])


if __name__ == "__main__":
    main()
