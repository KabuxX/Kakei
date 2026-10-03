"""Internal search types; coordinate authority remains server-side."""
from typing import TypedDict, NotRequired
from agent.place_contracts import Source, WebPlace

class PublicPage(TypedDict):
    url: str
    final_url: str
    redirects: list[str]
    content_type: str
    body: bytes
    retrieved_at: float

class EstimationHint(TypedDict):
    method: str
    anchorName: str
    anchorAddress: str
    relationSourceIds: list[str]
    relationExcerpt: str
    distanceMeters: int | None
    bearingDegrees: int | None
    areaScope: str | None

class DiscoveryRow(WebPlace):
    role: str
    urls: list[str]
    hints: list[EstimationHint]

class CoordinateCandidate(TypedDict):
    id: str
    name: str
    address: str
    coordinates: list[float]
    sourceUrl: str
    attribution: str
    sources: list[Source]
    coordinateEvidence: dict
    matchReasons: list[str]

class VerifiedAnchor(TypedDict):
    name: str
    address: str
    coordinates: list[float]
    sources: list[Source]
    observations: list[dict]

class VerificationResult(TypedDict):
    candidates: list[CoordinateCandidate]
    anchors: list[VerifiedAnchor]
    unresolved: list[str]
