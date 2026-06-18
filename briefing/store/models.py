"""Pydantic models for the briefing pipeline (see docs/IMPLEMENTATION_PLAN.md)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class RawArticle(BaseModel):
    id: str                          # stable hash of canonical_url
    url: str
    canonical_url: str | None = None
    title: str
    summary: str | None = None
    content: str | None = None       # full text when fetched
    author: str | None = None
    source_id: str
    source_name: str
    topics: list[str] = Field(default_factory=list)
    published_at: datetime
    fetched_at: datetime
    content_hash: str
    language: str | None = None
    raw: dict = Field(default_factory=dict)   # original feed entry


class StoryCluster(BaseModel):
    id: str
    title: str
    summary: str | None = None
    article_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_updated: datetime
    score: float | None = None
    score_components: dict = Field(default_factory=dict)


class PlannedSegment(BaseModel):
    kind: str                        # intro | weather | headline | deep_dive | day_ahead | outro
    story_cluster_id: str | None = None
    allotted_sec: int


class EpisodePlan(BaseModel):
    id: str
    date: date
    target_duration_sec: int
    segments: list[PlannedSegment] = Field(default_factory=list)
    status: str = "planned"          # planned | scripted | rendered | published
    show_id: str | None = None
    created_at: datetime


class SourceAttribution(BaseModel):
    article_id: str
    url: str
    title: str


class EpisodeSegment(BaseModel):
    id: str
    episode_id: str
    order_index: int
    kind: str
    story_cluster_id: str | None = None
    script: str = ""                 # ARIA:/ANDREW: tagged dialogue for this segment
    source_attributions: list[SourceAttribution] = Field(default_factory=list)
    audio_offset_sec: float | None = None
    start_time: float | None = None
    end_time: float | None = None


class InteractionContext(BaseModel):
    id: str
    episode_id: str
    segment_id: str | None = None
    timestamp_sec: float
    question: str
    intent: str | None = None
    answer: str | None = None
    answer_sources: list[SourceAttribution] = Field(default_factory=list)
    created_at: datetime
