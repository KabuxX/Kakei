"""Search contracts; internal processing authority never enters model context."""
from typing import TypedDict, NotRequired

class TurnContext(TypedDict):
    thread_id: str
    client_message_id: str
    run_token: str

class Evidence(TypedDict):
    field: str
    source: str
    source_id: str
    value: str

class SearchInput(TypedDict):
    query: str
    place_id: str
    brand: NotRequired[str | None]
    branch: NotRequired[str | None]
    locality: NotRequired[str | None]
    landmark: NotRequired[str | None]
    country_code: NotRequired[str | None]
    evidence: NotRequired[list[Evidence]]
    reuse_search_id: NotRequired[str | None]
    refresh: NotRequired[bool]
    address_format: NotRequired[str]

class Candidate(TypedDict, total=False):
    id: str
    providerId: str
    name: str
    address: str
    coordinates: list[float]
    sourceUrl: str
    attribution: str
    savedPlaceId: str
    searchId: str
    matchReasons: list[str]

class ProviderPlace(Candidate, total=False):
    city: str
    district: str
    country_code: str
    categories: list[str]
    result_type: str
    boundary_id: str
    confidence: float
    validationErrors: list[str]

class Region(TypedDict, total=False):
    kind: str
    coordinates: list[float]
    provider_id: str
    country_code: str
    city: str
    district: str
    source_id: str

class Attempt(TypedDict, total=False):
    id: str
    stage: str
    params: dict
    startedAt: float
    finishedAt: float
    status: str
    candidates: list[dict]
    excluded: list[dict]
    errorCode: str
    truncated: bool

class SearchResult(TypedDict, total=False):
    searchId: str
    placeId: str
    query: str
    candidates: list[Candidate]
    status: str
    error: str | None
    unresolved: list[str]
    truncated: bool
    reusedFrom: dict
    grounding: Region | None
    pipelineVersion: str
    sources: list[dict]
    unlocatedCandidates: list[dict]

class HistoryRecord(TypedDict, total=False):
    searchId: str | None
    createdAt: float
    finishedAt: float | None
    input: SearchInput
    attempts: list[Attempt]
    result: SearchResult | None
    status: str
    source: str
    proposalId: str
    legacyCursor: str

class HistoryPage(TypedDict):
    records: list[HistoryRecord]
    nextBeforeId: str | None
    hasMore: bool
    truncated: bool

END_STATES = frozenset(('found','empty','needs_region','needs_clarification','partial','error','cancelled'))

class Source(TypedDict):
    id: str
    title: str
    url: str
    kind: str
    retrievedAt: float

class WebPlace(TypedDict):
    id: str
    name: str
    branch: str
    address: str
    country_code: str
    locality: str
    sources: list[Source]
    evidenceText: str
    unresolved: list[str]

class ResearchReport(TypedDict):
    text: str
    sources: list[Source]
    actions: list[dict]
    usage: dict
    retrievedAt: float

class GeocodeResult(TypedDict):
    candidates: list[dict]
    unresolved: list[str]
