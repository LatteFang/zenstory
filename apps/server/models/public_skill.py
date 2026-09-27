"""
Public skill database model.

Stores skills in the public library that users can discover and add.
Includes both official skills and community-contributed skills.
"""

from datetime import datetime

from sqlmodel import Column, Field, SQLModel, Text

from .utils import generate_uuid


class PublicSkill(SQLModel, table=True):
    """
    Public skill model for the skill discovery system.

    Skills can be official (from the platform) or community-contributed.
    Community skills require admin approval before becoming public.
    """

    __tablename__ = "public_skill"

    id: str = Field(default_factory=generate_uuid, primary_key=True)

    # Skill metadata
    name: str = Field(max_length=100, description="Display name of the skill")
    description: str | None = Field(
        default=None,
        max_length=1024,
        description="Brief description of what the skill does"
    )

    # Instructions to inject into system prompt
    instructions: str = Field(
        sa_column=Column(Text),
        description="Instructions to inject into system prompt"
    )

    # 标准 SKILL.md frontmatter 的其余字段（license / compatibility / allowed_tools / metadata），
    # JSON 对象。allowed_tools 只存储与再导出，没有运行时效果。
    skill_metadata: str = Field(
        default="{}",
        sa_column=Column(Text, nullable=False, server_default="{}"),
        description="JSON object of standard SKILL.md frontmatter extras"
    )

    # Categorization
    category: str = Field(
        default="writing",
        max_length=50,
        description="Category: writing/character/worldbuilding/plot/style"
    )
    tags: str = Field(
        default="[]",
        sa_column=Column(Text),
        description="JSON array of tags for filtering"
    )

    # Source and authorship
    source: str = Field(
        default="official",
        max_length=20,
        description="Source: 'official' or 'community'"
    )
    author_id: str | None = Field(
        default=None,
        foreign_key="user.id",
        description="Author user ID for community skills"
    )

    # Review status for community skills
    status: str = Field(
        default="approved",
        max_length=20,
        description="Status: pending/approved/rejected"
    )
    reviewed_by: str | None = Field(
        default=None,
        foreign_key="user.id",
        description="Admin who reviewed the skill"
    )
    reviewed_at: datetime | None = Field(
        default=None,
        description="When the skill was reviewed"
    )
    rejection_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for rejection if rejected"
    )

    # Statistics
    add_count: int = Field(
        default=0,
        description="Number of times this skill has been added by users"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
