"""Guarded retrieval-augmented generation (RAG) over a small knowledge base.

documents.py loads and chunks the pages, embeddings.py turns text into vectors,
store.py finds the nearest chunks, and pipeline.py ties it together: every
retrieved chunk is screened by the guardrail before a model is allowed to read it.
"""
