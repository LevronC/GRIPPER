import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, ForeignKey, DateTime, Float, Integer, Boolean, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from .base import Base

class Institution(Base):
    __tablename__ = "institutions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(50), server_default="free") # free, enterprise
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    users: Mapped[List["User"]] = relationship(back_populates="institution", cascade="all, delete-orphan")
    portfolios: Mapped[List["Portfolio"]] = relationship(back_populates="institution", cascade="all, delete-orphan")
    research_reports: Mapped[List["ResearchReport"]] = relationship(back_populates="institution", cascade="all, delete-orphan")
    meetings: Mapped[List["Meeting"]] = relationship(back_populates="institution", cascade="all, delete-orphan")
    ips_rules: Mapped[List["IPSRule"]] = relationship(back_populates="institution", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # Clerk or Auth0 identifier
    role: Mapped[str] = mapped_column(String(50), nullable=False) # analyst, sector_lead, pm, faculty, trustee, admin
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    permissions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # JSON array of permissions
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship(back_populates="users")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    benchmark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    inception_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(100), nullable=False) # value, fixed_income, growth, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship(back_populates="portfolios")
    holdings: Mapped[List["Holding"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False) # percentage e.g., 0.05 for 5%
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    conviction_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # 1-10 analyst confidence
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"), onupdate=text("TIMEZONE('utc', NOW())"))

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sector: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. Technology, Healthcare
    company: Mapped[str] = mapped_column(String(255), nullable=False) # Company Name / Ticker
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False) # buy, hold, sell
    status: Mapped[str] = mapped_column(String(50), default="draft") # draft, pending_review, approved, rejected
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True) # SHA-256 hash
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship(back_populates="research_reports")
    chunks: Mapped[List["DocumentChunk"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_reports.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    # Using 384 dimensions for HuggingFace all-MiniLM-L6-v2 embeddings
    embedding: Mapped[list] = mapped_column(Vector(384), nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    report: Mapped["ResearchReport"] = relationship(back_populates="chunks")


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. public_trustee, sector_update
    transcript: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decisions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # key decisions/votes
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship(back_populates="meetings")


class IPSRule(Base):
    __tablename__ = "ips_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False) # single_position_cap, sector_exposure_cap, etc.
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), default="warning") # warning, critical
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship(back_populates="ips_rules")


class GovernanceEvent(Base):
    __tablename__ = "governance_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    holding_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("holdings.id", ondelete="SET NULL"), nullable=True)
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ips_rules.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False) # single_position_cap, sector_exposure_cap, liquidity_constraint
    severity: Mapped[str] = mapped_column(String(50), default="warning") # warning, critical
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False) # e.g. {"current_weight": 0.12, "threshold": 0.10, "ticker": "AAPL"}
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("TIMEZONE('utc', NOW())"))

    # Relationships
    institution: Mapped["Institution"] = relationship()

