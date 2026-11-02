"""Mock document MCP server. Read-only."""

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from servers.state import dumps, read_base

server = MCPServer("docs", log_level="ERROR")


def _docs() -> list[dict[str, Any]]:
    return read_base("docs.json")


def _doc(doc_id: str) -> dict[str, Any]:
    for doc in _docs():
        if doc["id"] == doc_id:
            return doc
    raise ToolError(f"Unknown doc_id '{doc_id}'")


def _summary(doc: dict[str, Any]) -> dict[str, Any]:
    return {"doc_id": doc["id"], "title": doc["title"], "folder": doc["folder"], "updated": doc["updated"]}


def _text(doc: dict[str, Any]) -> str:
    parts = [f"# {doc['title']}"]
    for section in doc["sections"]:
        parts.append(f"## {section['heading']}\n{section['body']}")
    return "\n\n".join(parts)


@server.tool(structured_output=False)
def list_folders() -> str:
    """List document folders with the number of documents in each."""
    counts: dict[str, int] = {}
    for doc in _docs():
        counts[doc["folder"]] = counts.get(doc["folder"], 0) + 1
    return dumps({"folders": [{"folder": name, "doc_count": counts[name]} for name in sorted(counts)]})


@server.tool(structured_output=False)
def list_docs(folder: str | None = None) -> str:
    """List documents with title, folder and last updated date, optionally for one folder only."""
    docs = _docs()
    if folder is not None and folder not in {doc["folder"] for doc in docs}:
        raise ToolError(f"Unknown folder '{folder}'")
    return dumps({"docs": [_summary(doc) for doc in docs if folder is None or doc["folder"] == folder]})


@server.tool(structured_output=False)
def search_docs(
    query: Annotated[str, Field(description="Words to look for. A document matches when its title or text contains at least one of them, ignoring case.")],
    folder: Annotated[str | None, Field(description="Restrict the search to this folder, as returned by list_folders. Searches all folders when omitted.")] = None,
    limit: Annotated[int, Field(description="Maximum number of documents to return, from 1 to 50.")] = 10,
) -> str:
    """Search documents by keyword and return the best matches with a short snippet of matching text.

    Documents are ranked by how many times the query words occur, with occurrences in the title
    counted more heavily, and ties are broken by document ID. Each result contains the document ID,
    title, folder, last updated date, match score, and a snippet around the first match. The full
    text is not included; use get_doc or get_doc_section to read a result.
    """
    if not query.strip():
        raise ToolError("query must not be empty")
    if not 1 <= limit <= 50:
        raise ToolError("limit must be between 1 and 50")
    terms = query.lower().split()
    scored = []
    for doc in _docs():
        if folder is not None and doc["folder"] != folder:
            continue
        title, text = doc["title"].lower(), _text(doc).lower()
        score = sum(text.count(term) + 5 * title.count(term) for term in terms)
        if score:
            first = min(position for position in (text.find(term) for term in terms) if position >= 0)
            scored.append((-score, doc["id"], first, doc))
    scored.sort(key=lambda item: item[:2])
    results = [{**_summary(doc), "score": -score, "snippet": _text(doc)[max(first - 60, 0) : first + 140]} for score, _, first, doc in scored[:limit]]
    return dumps({"total_matches": len(scored), "results": results})


@server.tool(structured_output=False)
def get_doc(doc_id: str) -> str:
    """Get the full text of a document, including every section."""
    doc = _doc(doc_id)
    return dumps({**_summary(doc), "author": doc["author"], "text": _text(doc)})


@server.tool(structured_output=False)
def get_doc_metadata(doc_id: str) -> str:
    """Get a document's title, folder, author, last updated date and length in characters."""
    doc = _doc(doc_id)
    return dumps({**_summary(doc), "author": doc["author"], "length_chars": len(_text(doc))})


@server.tool(structured_output=False)
def list_doc_sections(doc_id: str) -> str:
    """List a document's section headings in order, with each section's length in characters."""
    return dumps({"doc_id": doc_id, "sections": [{"heading": s["heading"], "length_chars": len(s["body"])} for s in _doc(doc_id)["sections"]]})


@server.tool(structured_output=False)
def get_doc_section(doc_id: str, heading: str) -> str:
    """Get one section of a document by its exact heading, ignoring case."""
    doc = _doc(doc_id)
    for section in doc["sections"]:
        if section["heading"].lower() == heading.lower():
            return dumps({"doc_id": doc_id, "heading": section["heading"], "body": section["body"]})
    raise ToolError(f"No section '{heading}' in {doc_id}")


@server.tool(structured_output=False)
def get_doc_comments(doc_id: str) -> str:
    """Get the review comments left on a document."""
    return dumps({"doc_id": doc_id, "comments": _doc(doc_id)["comments"]})


if __name__ == "__main__":
    server.run()
