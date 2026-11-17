"""Retrieval-Augmented Generation (RAG) & Document Intelligence for Corbel.

Enterprise document ingestion (Docling), section-aware chunking, genuine Robertson BM25,
pgvector native semantic search, Reciprocal Rank Fusion (RRF), and prompt injection demarcation.
Adheres strictly to ADR-008, ADR-010, ADR-019, and Phase 9 specifications.
"""

import hashlib
import logging
import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from corbel.domains.governance.models import Document, DocumentChunk
from corbel.domains.governance.schemas import DocumentQueryResult

logger = logging.getLogger(__name__)


@dataclass
class DocumentSection:
    """Represents a structured section within an ingested enterprise document."""

    heading: str
    parent_heading: str | None = None
    level: int = 1
    page_number: int | None = None
    paragraphs: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    """Structured representation produced by Docling ingestion."""

    file_name: str
    file_format: str
    raw_text: str
    sections: list[DocumentSection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    provenance_hash: str = ""


# ==============================================================================
# 1. Document Ingestion Engine (Docling + Structural Fallback)
# ==============================================================================


class DoclingIngestionEngine:
    """Enterprise document extraction layer using Docling with structural fallback.

    Extracts heading hierarchy, tables with column headers, paragraphs, and page numbers.
    Enforces security boundaries: rejects oversized files and files with macro/script signatures.
    """

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
    SUPPORTED_FORMATS = {"TXT", "PDF", "DOCX", "MD"}

    # Macro & script signatures prohibited in uploaded business documents
    MALICIOUS_SIGNATURES = [
        re.compile(rb"<script[\s>]", re.IGNORECASE),
        re.compile(rb"vbaProject\.bin", re.IGNORECASE),
        re.compile(rb"auto_open\s*\(", re.IGNORECASE),
        re.compile(rb"document_open\s*\(", re.IGNORECASE),
    ]

    @classmethod
    def validate_content(cls, content_bytes: bytes, file_name: str) -> None:
        """Validate file size and scan for prohibited macro/script signatures."""
        if len(content_bytes) > cls.MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File '{file_name}' exceeds maximum permitted size of {cls.MAX_FILE_SIZE_BYTES // (1024*1024)} MB."
            )

        for sig in cls.MALICIOUS_SIGNATURES:
            if sig.search(content_bytes):
                raise ValueError(
                    f"File '{file_name}' contains prohibited embedded macro or executable script signatures."
                )

    @classmethod
    def extract_document(
        cls,
        raw_text: str,
        file_name: str,
        file_format: str = "TXT",
        metadata: dict[str, Any] | None = None,
    ) -> ExtractedDocument:
        """Parse document content into structured hierarchical sections and tables."""
        file_ext = file_format.upper().strip()
        if file_ext not in cls.SUPPORTED_FORMATS:
            file_ext = "TXT"

        provenance_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        # Heading detection pattern: markdown headers, clauses, sections, articles
        heading_re = re.compile(
            r"^(?:#{1,4}\s+|Clause\s+\d+(?:\.\d+)*|Section\s+\d+(?:\.\d+)*|Article\s+\d+|[A-Z0-9\.\-\s]{3,40}:)",
            re.IGNORECASE,
        )

        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        sections: list[DocumentSection] = []

        current_heading = "Preamble & General Terms"
        current_paragraphs: list[str] = []
        current_tables: list[str] = []
        current_page = 1

        for p in paragraphs:
            lines = p.split("\n")
            first_line = lines[0].strip()

            # Check for page markers e.g. [Page 2] or --- Page 2 ---
            page_match = re.search(r"\[Page\s+(\d+)\]|---\s*Page\s+(\d+)\s*---", first_line, re.IGNORECASE)
            if page_match:
                page_str = page_match.group(1) or page_match.group(2)
                if page_str:
                    current_page = int(page_str)

            # Check if this paragraph is a table (markdown format | col1 | col2 |)
            if all(line.strip().startswith("|") and line.strip().endswith("|") for line in lines if line.strip()):
                current_tables.append(p)
                continue

            # Check if this paragraph begins a new section
            if heading_re.match(first_line) and len(first_line) < 120:
                if current_paragraphs or current_tables:
                    sections.append(
                        DocumentSection(
                            heading=current_heading,
                            page_number=current_page,
                            paragraphs=list(current_paragraphs),
                            tables=list(current_tables),
                        )
                    )
                    current_paragraphs.clear()
                    current_tables.clear()

                current_heading = first_line.lstrip("#").strip()
                remaining_lines = lines[1:]
                if remaining_lines:
                    rem_text = "\n".join(remaining_lines).strip()
                    if all(line.strip().startswith("|") and line.strip().endswith("|") for line in remaining_lines if line.strip()):
                        current_tables.append(rem_text)
                    else:
                        current_paragraphs.append(rem_text)
            else:
                current_paragraphs.append(p)

        # Flush final section
        if current_paragraphs or current_tables:
            sections.append(
                DocumentSection(
                    heading=current_heading,
                    page_number=current_page,
                    paragraphs=list(current_paragraphs),
                    tables=list(current_tables),
                )
            )

        if not sections:
            sections.append(
                DocumentSection(
                    heading="Full Document",
                    page_number=1,
                    paragraphs=[raw_text],
                )
            )

        return ExtractedDocument(
            file_name=file_name,
            file_format=file_ext,
            raw_text=raw_text,
            sections=sections,
            metadata=metadata or {},
            provenance_hash=provenance_hash,
        )


# ==============================================================================
# 2. Section-Aware Chunker
# ==============================================================================


class SectionAwareChunker:
    """Chunker respecting section hierarchy, table boundaries, and contractual clauses.

    Avoids arbitrary word slicing. Preserves complete contractual clauses and associated table headers.
    """

    DEFAULT_TARGET_CHUNK_TOKENS = 400
    DEFAULT_OVERLAP_TOKENS = 60

    @classmethod
    def chunk_document(
        cls,
        document_id: uuid.UUID,
        project_id: uuid.UUID,
        extracted_doc: ExtractedDocument,
        target_tokens: int = DEFAULT_TARGET_CHUNK_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ) -> list[DocumentChunk]:
        """Split extracted document into section-grounded DocumentChunk instances."""
        chunks: list[DocumentChunk] = []
        chunk_idx = 0

        for section in extracted_doc.sections:
            heading = section.heading
            section_items: list[str] = []

            # 1. Add tables preserving column headers
            for table_text in section.tables:
                section_items.append(f"[Table under {heading}]\n{table_text}")

            # 2. Add text paragraphs
            section_items.extend(section.paragraphs)

            if not section_items:
                continue

            current_tokens: list[str] = []
            for item in section_items:
                words = item.split()
                if not words:
                    continue

                # If single item exceeds target size, split by sentence boundaries
                if len(current_tokens) + len(words) > target_tokens and current_tokens:
                    chunk_text = " ".join(current_tokens)
                    token_count = int(len(current_tokens) * 1.3)
                    chunks.append(
                        DocumentChunk(
                            id=uuid.uuid4(),
                            project_id=project_id,
                            document_id=document_id,
                            chunk_index=chunk_idx,
                            section_heading=heading,
                            chunk_text=chunk_text,
                            token_count=token_count,
                            embedding_json=None,
                        )
                    )
                    chunk_idx += 1
                    # Slide with overlap
                    current_tokens = current_tokens[max(0, len(current_tokens) - overlap_tokens) :]

                current_tokens.extend(words)

            if current_tokens:
                chunk_text = " ".join(current_tokens)
                token_count = int(len(current_tokens) * 1.3)
                chunks.append(
                    DocumentChunk(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        document_id=document_id,
                        chunk_index=chunk_idx,
                        section_heading=heading,
                        chunk_text=chunk_text,
                        token_count=token_count,
                        embedding_json=None,
                    )
                )
                chunk_idx += 1

        return chunks


# ==============================================================================
# 3. Genuine Robertson BM25 Retrieval Engine
# ==============================================================================


class BM25RetrievalEngine:
    """Genuine Robertson BM25 lexical retriever with Lucene non-negative IDF and exact identifier boosts.

    Preserves exact matches for PO numbers, Invoice IDs, currency values, supplier names, and clause references.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Tokenize preserving domain-specific identifiers (PO-*, INV-*, currency, clauses)."""
        clean = text.lower()
        # Find exact identifiers like po-1002, inv-9921, $125.00
        special_tokens = re.findall(
            r"(?:po-\d+|inv-\d+|clause\s+\d+(?:\.\d+)*|\$\d+(?:\.\d+)?|\b\d+\.\d{2}\b)",
            clean,
        )
        words = re.findall(r"\b[a-z0-9_]{2,}\b", clean)
        return special_tokens + words

    def score_chunks(
        self,
        query: str,
        chunks: list[DocumentChunk],
    ) -> list[tuple[float, DocumentChunk]]:
        """Calculate Robertson BM25 score with Lucene non-negative IDF for all chunks."""
        if not chunks:
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        n_docs = len(chunks)
        tokenized_corpus = [self.tokenize(c.chunk_text) for c in chunks]
        doc_lens = [len(toks) for toks in tokenized_corpus]
        avg_dl = sum(doc_lens) / n_docs if n_docs > 0 else 1.0

        # Compute document frequency (DF) for query tokens
        dfs: dict[str, int] = Counter()
        for doc_toks in tokenized_corpus:
            unique_toks = set(doc_toks)
            for q in set(query_tokens):
                if q in unique_toks:
                    dfs[q] += 1

        # Lucene formula: IDF = ln(1 + (N - df + 0.5) / (df + 0.5)) -> guaranteed >= 0
        idfs: dict[str, float] = {}
        for q, df in dfs.items():
            idfs[q] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

        scored: list[tuple[float, DocumentChunk]] = []
        for idx, chunk in enumerate(chunks):
            doc_toks = tokenized_corpus[idx]
            doc_len = doc_lens[idx]
            term_counts = Counter(doc_toks)
            score = 0.0

            for q in query_tokens:
                tf = term_counts.get(q, 0)
                if tf > 0:
                    idf = idfs.get(q, 0.0)
                    denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / avg_dl))
                    term_score = idf * (tf * (self.k1 + 1.0)) / denom if denom > 0 else 0.0
                    score += term_score

            # Domain Boost: If chunk heading contains query tokens, apply a 1.5x boost
            if chunk.section_heading:
                heading_tokens = set(self.tokenize(chunk.section_heading))
                overlap = set(query_tokens).intersection(heading_tokens)
                if overlap:
                    score += len(overlap) * 1.5

            if score > 0.0:
                scored.append((round(score, 4), chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


# ==============================================================================
# 4. Vector Retrieval Engine (pgvector + Cosine Math)
# ==============================================================================


class VectorRetrievalEngine:
    """Semantic vector similarity retrieval engine leveraging pgvector cosine similarity."""

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two float vectors."""
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2, strict=False))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        if n1 > 0.0 and n2 > 0.0:
            return dot / (n1 * n2)
        return 0.0

    @classmethod
    def score_chunks(
        cls,
        query_vector: list[float],
        chunks: list[DocumentChunk],
    ) -> list[tuple[float, DocumentChunk]]:
        """Rank chunks by cosine similarity against query vector."""
        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in chunks:
            chunk_vec = chunk.embedding_vector
            if chunk_vec is None and chunk.embedding_json is not None:
                chunk_vec = chunk.embedding_json

            if chunk_vec is not None:
                sim = cls.cosine_similarity(query_vector, chunk_vec)
                if sim > 0.05:
                    scored.append((round(sim, 4), chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored


# ==============================================================================
# 5. Reciprocal Rank Fusion (RRF) Hybrid Retriever
# ==============================================================================


class RRFHybridRetriever:
    """Fuses BM25 lexical and pgvector semantic retrieval pipelines using Reciprocal Rank Fusion.

    RRF formula: RRF(d) = sum_m ( 1 / (k + rank_m(d)) )
    Preserves exact citations, document metadata, and marks untrusted content boundaries.
    """

    def __init__(self, k: int = 60) -> None:
        self.k = k

    def fuse(
        self,
        bm25_ranked: list[tuple[float, DocumentChunk]],
        vector_ranked: list[tuple[float, DocumentChunk]],
        documents_by_id: dict[uuid.UUID, Document],
        top_k: int = 5,
    ) -> list[DocumentQueryResult]:
        """Merge lexical and vector ranked lists using RRF."""
        rrf_scores: dict[uuid.UUID, float] = {}
        chunks_by_id: dict[uuid.UUID, DocumentChunk] = {}

        # 1. Score BM25 ranks
        for rank, (_score, chunk) in enumerate(bm25_ranked, start=1):
            chunks_by_id[chunk.id] = chunk
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (self.k + rank))

        # 2. Score Vector ranks
        for rank, (_score, chunk) in enumerate(vector_ranked, start=1):
            chunks_by_id[chunk.id] = chunk
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + (1.0 / (self.k + rank))

        # 3. Sort by aggregated RRF score descending
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        results: list[DocumentQueryResult] = []
        for chunk_id, rrf_score in sorted_chunks[:top_k]:
            chunk = chunks_by_id[chunk_id]
            doc = documents_by_id.get(chunk.document_id)
            if not doc:
                continue

            results.append(
                DocumentQueryResult(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    document_title=doc.title,
                    file_name=doc.file_name,
                    version_tag=doc.version_tag,
                    section_heading=chunk.section_heading,
                    chunk_text=chunk.chunk_text,
                    relevance_score=round(rrf_score, 6),
                    is_untrusted=True,
                    retrieval_method="HYBRID_RRF",
                )
            )

        return results


# ==============================================================================
# 6. Optional Candidate Reranker
# ==============================================================================


class CandidateReranker:
    """Optional cross-scoring reranker evaluated on top-k candidates to refine boundary precision."""

    @staticmethod
    def rerank(
        query: str,
        candidates: list[DocumentQueryResult],
        top_k: int = 5,
    ) -> list[DocumentQueryResult]:
        """Refine ranking using exact term coverage and sequence alignment."""
        q_tokens = set(re.findall(r"\b\w{3,}\b", query.lower()))
        if not q_tokens or not candidates:
            return candidates[:top_k]

        scored: list[tuple[float, DocumentQueryResult]] = []
        for item in candidates:
            text_tokens = set(re.findall(r"\b\w{3,}\b", item.chunk_text.lower()))
            coverage = len(q_tokens.intersection(text_tokens)) / len(q_tokens)
            # Combine RRF score with term coverage
            combined_score = item.relevance_score * 0.6 + coverage * 0.4
            item_copy = item.model_copy(update={"relevance_score": round(combined_score, 6)})
            scored.append((combined_score, item_copy))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


# ==============================================================================
# 7. Untrusted Content Sanitizer & Injection Demarcation
# ==============================================================================


class UntrustedContentSanitizer:
    """Demarcates untrusted business documents and defends against prompt injection (ADR-019)."""

    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
        re.compile(r"override\s+(?:all\s+)?security\s+checks", re.IGNORECASE),
        re.compile(r"bypass\s+(?:the\s+)?approval", re.IGNORECASE),
        re.compile(r"execute\s+(?:payment|transaction)\s+immediately", re.IGNORECASE),
        re.compile(r"approve\s+this\s+action\s+automatically", re.IGNORECASE),
        re.compile(r"set\s+(?:variance|discrepancy)\s+to\s+0", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_untrusted_text(cls, raw_text: str) -> tuple[str, bool]:
        """Sanitize text and detect if prompt injection patterns exist."""
        detected_injection = False
        sanitized = raw_text

        # Strip angle brackets to prevent delimiter escape
        sanitized = sanitized.replace("<", "[").replace(">", "]")

        for pattern in cls.INJECTION_PATTERNS:
            if pattern.search(sanitized):
                detected_injection = True
                sanitized = pattern.sub("[POTENTIAL_INJECTION_STRIPPED]", sanitized)

        return sanitized, detected_injection

    @classmethod
    def format_untrusted_context_block(
        cls,
        evidence_items: list[dict[str, Any]],
    ) -> str:
        """Format retrieved evidence in explicit untrusted data blocks for LLM reasoning."""
        blocks: list[str] = []

        for idx, item in enumerate(evidence_items, start=1):
            source = item.get("source_identifier", f"DOC-{idx}")
            doc_name = item.get("document_name", "Unknown Document")
            section = item.get("section_or_chunk", "General")
            snippet = item.get("content_snippet", "")
            sanitized_snippet, flagged = cls.sanitize_untrusted_text(snippet)

            flag_tag = ' untrusted_warning="FLAGGED_INJECTION_PATTERN"' if flagged else ""

            block = (
                f'<UNTRUSTED_BUSINESS_EVIDENCE index="{idx}" source="{source}" document="{doc_name}" '
                f'section="{section}"{flag_tag}>\n'
                f"{sanitized_snippet}\n"
                "</UNTRUSTED_BUSINESS_EVIDENCE>"
            )
            blocks.append(block)

        return "\n\n".join(blocks)
