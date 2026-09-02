from __future__ import annotations

from retrieval.hybrid_search import SearchResult


def render_context(results: list[SearchResult], max_characters: int = 8_000) -> str:
    sections: list[str] = []
    size = 0
    for result in results:
        section = (
            f"[{result.document.id}] {result.document.title}\n"
            f"source={result.document.source_uri}\n{result.document.body}"
        )
        if size + len(section) > max_characters:
            break
        sections.append(section)
        size += len(section)
    return "\n\n".join(sections)
