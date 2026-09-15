"""Recuperação BM25 local, reproduzível e sem dependência externa."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from src.models import ContextChunk

TOKEN_PATTERN = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class RankedChunk:
    """Chunk acompanhado da evidência de ranking."""

    chunk: ContextChunk
    score: float


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def retrieve_chunks(query: str, chunks: list[ContextChunk], top_k: int) -> list[RankedChunk]:
    """Ordena chunks com BM25 e desempate estável pelo ID."""
    if not chunks:
        return []
    tokenized = [_tokens(chunk.text) for chunk in chunks]
    avg_length = sum(map(len, tokenized)) / len(tokenized) or 1
    query_tokens = set(_tokens(query))
    document_frequency = {
        token: sum(token in document for document in tokenized) for token in query_tokens
    }
    ranked: list[RankedChunk] = []
    for chunk, document in zip(chunks, tokenized, strict=True):
        counts = Counter(document)
        score = 0.0
        for token in query_tokens:
            frequency = counts[token]
            if not frequency:
                continue
            idf = math.log(
                1
                + (len(chunks) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(document) / avg_length)
            score += idf * (frequency * 2.5 / denominator)
        ranked.append(RankedChunk(chunk=chunk, score=round(score, 6)))
    return sorted(ranked, key=lambda item: (-item.score, item.chunk.id))[:top_k]
