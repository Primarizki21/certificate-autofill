import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from dataclasses import dataclass
from transformers import pipeline
import torch


@dataclass
class NEREntity:
    entity_type: str
    text: str
    start: int
    end: int
    score: float


_ner_pipe = None


def load_ner_model():
    global _ner_pipe
    if _ner_pipe is not None:
        return _ner_pipe
    device = 0 if torch.cuda.is_available() else -1
    print(f"[NER] Loading model on {'GPU' if device == 0 else 'CPU'}...")
    _ner_pipe = pipeline(
        "ner",
        model="treamyracle/indobert-ner-gold",
        device=device,
        aggregation_strategy="max",
    )
    print(f"[NER] Model loaded ({torch.cuda.get_device_name(0) if device == 0 else 'CPU'})")
    return _ner_pipe


def extract_entities(text: str, ner_pipe=None) -> list[NEREntity]:
    if not text or not text.strip():
        return []
    if ner_pipe is None:
        ner_pipe = load_ner_model()
    max_length = 512
    chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    entities = []
    for chunk in chunks:
        results = ner_pipe(chunk)
        for r in results:
            entity_type = r.get("entity_group") or r.get("entity", "O")
            if entity_type == "O":
                continue
            entities.append(NEREntity(
                entity_type=entity_type,
                text=r["word"],
                start=r["start"],
                end=r["end"],
                score=r["score"],
            ))
    return entities


if __name__ == "__main__":
    pipe = load_ner_model()
    sample = (
        "SERTIFIKAT diberikan kepada Primarizki sebagai peserta "
        "dalam kegiatan Dataquest 4.0 yang diselenggarakan oleh "
        "Badan Eksekutif Mahasiswa Fakultas Teknologi Maju dan Multidisiplin "
        "Universitas Airlangga"
    )
    entities = extract_entities(sample, pipe)
    for e in entities:
        print(f"  {e.entity_type:5s}  {e.score:.3f}  '{e.text}'")
