from pydantic import BaseModel


class ScenarioExtract(BaseModel):
    id: str
    title: str
    crisis_type: str
    severity: str
    phase: str
    context: str
    stakeholders: list[str]
    time_pressure: str
    initial_statement_required: bool
    decision_nodes: list[str]
    relevant_tactics: list[str]
    source: str
    difficulty_for_rookie: str


class QAPairExtract(BaseModel):
    id: str
    question: str
    answer: str
    scenario_tags: list[str]
    difficulty: str
    common_mistake: str
    source_scenario_id: str


class RagChunkExtract(BaseModel):
    chunk_id: str
    text: str
    source_title: str
    source_chapter: str
    topics: list[str]
    scenario_relevance: list[str]
    embedding: list[float] | None = None