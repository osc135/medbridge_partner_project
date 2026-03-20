"""Shared LLM instance and helpers."""

from langchain_openai import ChatOpenAI

_llm = None


def get_llm() -> ChatOpenAI:
    """Return a shared ChatOpenAI instance."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    return _llm
