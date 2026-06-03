from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Type, TypeVar

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from firestore_db import get_firestore_client

try:
    # Newer google-cloud-firestore prefers Query.where(filter=FieldFilter(...))
    # and emits a warning for positional-argument where(field, op, value).
    from google.cloud.firestore_v1.base_query import FieldFilter  # type: ignore
except Exception:  # pragma: no cover
    FieldFilter = None  # type: ignore


T = TypeVar("T", bound="FirestoreModel")


_RUNTIME_CACHE_NOT_SET = object()


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass
class FirestoreModel:
    """Minimal Firestore document helper.

    - Uses a top-level collection per model
    - `id` is the Firestore document id (string)
    """

    collection_name: ClassVar[str]
    id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls: Type[T], doc_id: str, data: Dict[str, Any]) -> T:
        raise NotImplementedError

    @classmethod
    def _col(cls):
        return get_firestore_client().collection(cls.collection_name)

    def save(self) -> "FirestoreModel":
        data = self.to_dict()
        data.setdefault("updated_at", _utcnow())
        if self.id:
            self._col().document(self.id).set(data, merge=True)
        else:
            data.setdefault("created_at", _utcnow())
            ref = self._col().document()
            ref.set(data)
            self.id = ref.id
        return self

    def delete(self) -> None:
        if not self.id:
            return
        self._col().document(self.id).delete()

    @classmethod
    def get(cls: Type[T], doc_id: str) -> Optional[T]:
        if not doc_id:
            return None
        snap = cls._col().document(str(doc_id)).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return cls.from_dict(snap.id, data)

    @classmethod
    def find_all(cls: Type[T]) -> List[T]:
        return [cls.from_dict(s.id, s.to_dict() or {}) for s in cls._col().stream()]

    @classmethod
    def find_by(cls: Type[T], field_name: str, value: Any) -> List[T]:
        # NOTE: Firestore may require composite indexes for more complex queries.
        col = cls._col()
        if FieldFilter is not None:
            q = col.where(filter=FieldFilter(field_name, "==", value))
        else:
            q = col.where(field_name, "==", value)
        return [cls.from_dict(s.id, s.to_dict() or {}) for s in q.stream()]

    @classmethod
    def first_by(cls: Type[T], field_name: str, value: Any) -> Optional[T]:
        rows = cls.find_by(field_name, value)
        return rows[0] if rows else None

    @classmethod
    def find_in(cls: Type[T], field_name: str, values: Iterable[Any], *, chunk_size: int = 10) -> List[T]:
        """Query documents where ``field_name`` is within the provided values.

        Firestore limits ``in`` queries to 10 values per call, so we chunk requests.
        """

        cleaned: List[str] = []
        seen = set()
        for value in values:
            if value is None:
                continue
            string_value = str(value).strip()
            if not string_value or string_value in seen:
                continue
            seen.add(string_value)
            cleaned.append(string_value)

        if not cleaned:
            return []

        results: List[T] = []
        col = cls._col()
        for idx in range(0, len(cleaned), chunk_size):
            chunk = cleaned[idx : idx + chunk_size]
            if FieldFilter is not None:
                query = col.where(filter=FieldFilter(field_name, "in", chunk))
            else:  # pragma: no cover - legacy Firestore API
                query = col.where(field_name, "in", chunk)
            results.extend(cls.from_dict(doc.id, doc.to_dict() or {}) for doc in query.stream())

        return results


@dataclass
class Faculty(FirestoreModel):
    collection_name: ClassVar[str] = "faculties"

    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name}

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Faculty":
        return cls(id=doc_id, name=(data.get("name") or ""))

    @property
    def departments(self) -> List["Department"]:
        if not self.id:
            return []
        return Department.find_by("faculty_id", self.id)


@dataclass
class Department(FirestoreModel):
    """Department/Branch (สาขาวิชา) under a Faculty.

    One department can have many Programs (curriculum revisions/years).
    """

    collection_name: ClassVar[str] = "departments"

    name: str = ""
    faculty_id: Optional[str] = None
    major: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "faculty_id": self.faculty_id, "major": self.major}

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Department":
        return cls(
            id=doc_id,
            name=(data.get("name") or ""),
            faculty_id=data.get("faculty_id"),
            major=data.get("major") or None,
        )

    @property
    def faculty(self) -> Optional[Faculty]:
        return Faculty.get(self.faculty_id) if self.faculty_id else None

    @property
    def programs(self) -> List["Program"]:
        if not self.id:
            return []
        return Program.find_by("department_id", self.id)


@dataclass
class Program(FirestoreModel):
    collection_name: ClassVar[str] = "programs"

    name: str = ""
    department_id: Optional[str] = None
    faculty_id: Optional[str] = None
    year: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "department_id": self.department_id,
            "faculty_id": self.faculty_id,
            "year": self.year,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Program":
        year = data.get("year")
        try:
            year = int(year) if year is not None and year != "" else None
        except Exception:
            year = None
        return cls(
            id=doc_id,
            name=(data.get("name") or ""),
            department_id=data.get("department_id"),
            faculty_id=data.get("faculty_id"),
            year=year,
        )

    @property
    def department(self) -> Optional[Department]:
        return Department.get(self.department_id) if self.department_id else None

    @property
    def faculty(self) -> Optional[Faculty]:
        if self.faculty_id:
            return Faculty.get(self.faculty_id)
        dept = self.department
        return dept.faculty if dept else None

    @property
    def courses(self) -> List["Course"]:
        if not self.id:
            return []
        return Course.find_by("program_id", self.id)


@dataclass
class Course(FirestoreModel):
    collection_name: ClassVar[str] = "courses"

    code: str = ""
    name_th: str = ""
    name_en: str = ""
    credits: Optional[str] = None
    description: Optional[str] = None
    program_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name_th": self.name_th,
            "name_en": self.name_en,
            "credits": self.credits,
            "description": self.description,
            "program_id": self.program_id,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Course":
        return cls(
            id=doc_id,
            code=(data.get("code") or ""),
            name_th=(data.get("name_th") or ""),
            name_en=(data.get("name_en") or ""),
            credits=data.get("credits"),
            description=data.get("description"),
            program_id=data.get("program_id"),
        )

    @property
    def program(self) -> Optional[Program]:
        return Program.get(self.program_id) if self.program_id else None


@dataclass
class Term(FirestoreModel):
    collection_name: ClassVar[str] = "terms"

    year: int = 0
    semester: int = 0
    is_open_tqf3: bool = False
    is_open_tqf5: bool = False
    start_month: Optional[int] = None
    start_year: Optional[int] = None
    end_month: Optional[int] = None
    end_year: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": int(self.year),
            "semester": int(self.semester),
            "is_open_tqf3": bool(self.is_open_tqf3),
            "is_open_tqf5": bool(self.is_open_tqf5),
            "start_month": self.start_month,
            "start_year": self.start_year,
            "end_month": self.end_month,
            "end_year": self.end_year,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Term":
        year = data.get("year") or 0
        semester = data.get("semester") or 0
        is_open_tqf3 = bool(data.get("is_open_tqf3", False))
        is_open_tqf5 = bool(data.get("is_open_tqf5", False))
        try:
            year = int(year)
        except Exception:
            year = 0
        try:
            semester = int(semester)
        except Exception:
            semester = 0

        def _opt_int(v):
            try:
                return int(v) if v is not None and v != "" else None
            except Exception:
                return None

        return cls(
            id=doc_id,
            year=year,
            semester=semester,
            is_open_tqf3=is_open_tqf3,
            is_open_tqf5=is_open_tqf5,
            start_month=_opt_int(data.get("start_month")),
            start_year=_opt_int(data.get("start_year")),
            end_month=_opt_int(data.get("end_month")),
            end_year=_opt_int(data.get("end_year")),
        )


@dataclass
class TermProgram(FirestoreModel):
    collection_name: ClassVar[str] = "term_programs"

    term_id: str = ""
    program_id: str = ""
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term_id": self.term_id,
            "program_id": self.program_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "TermProgram":
        created_at = data.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = _utcnow()
        return cls(
            id=doc_id,
            term_id=(data.get("term_id") or ""),
            program_id=(data.get("program_id") or ""),
            created_at=created_at,
        )


@dataclass
class Section(FirestoreModel):
    collection_name: ClassVar[str] = "sections"

    course_id: str = ""
    term_id: str = ""
    instructor_id: Optional[str] = None
    section_number: Optional[str] = None
    status: str = "active"  # active, locked

    # Optional runtime caches for template/view usage (not persisted)
    _course_cache: Any = field(default=_RUNTIME_CACHE_NOT_SET, init=False, repr=False, compare=False)
    _term_cache: Any = field(default=_RUNTIME_CACHE_NOT_SET, init=False, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_id": self.course_id,
            "term_id": self.term_id,
            "instructor_id": self.instructor_id,
            "section_number": self.section_number,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Section":
        return cls(
            id=doc_id,
            course_id=(data.get("course_id") or ""),
            term_id=(data.get("term_id") or ""),
            instructor_id=data.get("instructor_id"),
            section_number=data.get("section_number"),
            status=(data.get("status") or "active"),
        )

    @property
    def course(self) -> Optional[Course]:
        if self._course_cache is not _RUNTIME_CACHE_NOT_SET:
            return self._course_cache
        return Course.get(self.course_id) if self.course_id else None

    @course.setter
    def course(self, value: Optional[Course]) -> None:
        self._course_cache = value

    @property
    def term(self) -> Optional[Term]:
        if self._term_cache is not _RUNTIME_CACHE_NOT_SET:
            return self._term_cache
        return Term.get(self.term_id) if self.term_id else None

    @term.setter
    def term(self, value: Optional[Term]) -> None:
        self._term_cache = value


@dataclass
class TQF3(FirestoreModel):
    collection_name: ClassVar[str] = "tqf3"

    section_id: str = ""
    status: str = "DRAFT"
    submitted_at: Optional[datetime] = None

    general_info: Dict[str, Any] = field(default_factory=dict)
    clo_plo_mapping: Dict[str, Any] = field(default_factory=dict)
    teaching_plan: Dict[str, Any] = field(default_factory=dict)
    evaluation_plan: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "general_info": self.general_info,
            "clo_plo_mapping": self.clo_plo_mapping,
            "teaching_plan": self.teaching_plan,
            "evaluation_plan": self.evaluation_plan,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "TQF3":
        return cls(
            id=doc_id,
            section_id=(data.get("section_id") or ""),
            status=(data.get("status") or "DRAFT"),
            submitted_at=data.get("submitted_at"),
            general_info=data.get("general_info") or {},
            clo_plo_mapping=data.get("clo_plo_mapping") or {},
            teaching_plan=data.get("teaching_plan") or {},
            evaluation_plan=data.get("evaluation_plan") or {},
        )


@dataclass
class TQF5(FirestoreModel):
    collection_name: ClassVar[str] = "tqf5"

    section_id: str = ""
    tqf3_id: str = ""
    status: str = "DRAFT"
    submitted_at: Optional[datetime] = None

    actual_teaching: Dict[str, Any] = field(default_factory=dict)
    grade_distribution: Dict[str, Any] = field(default_factory=dict)
    improvements: Dict[str, Any] = field(default_factory=dict)
    verification_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_id": self.section_id,
            "tqf3_id": self.tqf3_id,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "actual_teaching": self.actual_teaching,
            "grade_distribution": self.grade_distribution,
            "improvements": self.improvements,
            "verification_result": self.verification_result,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "TQF5":
        return cls(
            id=doc_id,
            section_id=(data.get("section_id") or ""),
            tqf3_id=(data.get("tqf3_id") or ""),
            status=(data.get("status") or "DRAFT"),
            submitted_at=data.get("submitted_at"),
            actual_teaching=data.get("actual_teaching") or {},
            grade_distribution=data.get("grade_distribution") or {},
            improvements=data.get("improvements") or {},
            verification_result=data.get("verification_result") or {},
        )


@dataclass
class HeadTQF5Summary(FirestoreModel):
    collection_name: ClassVar[str] = "head_tqf5_summaries"

    term_id: str = ""
    scope_type: str = ""  # department or program
    scope_id: str = ""
    head_id: str = ""
    status: str = "DRAFT"
    submitted_at: Optional[datetime] = None
    source_tqf5_ids: List[str] = field(default_factory=list)
    summary_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term_id": self.term_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "head_id": self.head_id,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "source_tqf5_ids": list(self.source_tqf5_ids or []),
            "summary_data": self.summary_data,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "HeadTQF5Summary":
        source_tqf5_ids = data.get("source_tqf5_ids")
        if not isinstance(source_tqf5_ids, list):
            source_tqf5_ids = []
        return cls(
            id=doc_id,
            term_id=(data.get("term_id") or ""),
            scope_type=(data.get("scope_type") or ""),
            scope_id=(data.get("scope_id") or ""),
            head_id=(data.get("head_id") or ""),
            status=(data.get("status") or "DRAFT"),
            submitted_at=data.get("submitted_at"),
            source_tqf5_ids=[str(v) for v in source_tqf5_ids if v],
            summary_data=data.get("summary_data") or {},
        )


@dataclass
class Feedback(FirestoreModel):
    collection_name: ClassVar[str] = "feedback"

    tqf_type: str = ""  # TQF3 or TQF5
    tqf_id: str = ""
    reviewer_id: str = ""
    comment: str = ""
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tqf_type": self.tqf_type,
            "tqf_id": self.tqf_id,
            "reviewer_id": self.reviewer_id,
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "Feedback":
        created_at = data.get("created_at")
        if not isinstance(created_at, datetime):
            created_at = _utcnow()
        return cls(
            id=doc_id,
            tqf_type=(data.get("tqf_type") or ""),
            tqf_id=(data.get("tqf_id") or ""),
            reviewer_id=(data.get("reviewer_id") or ""),
            comment=(data.get("comment") or ""),
            created_at=created_at,
        )

    @property
    def reviewer(self) -> Optional["User"]:
        return User.get(self.reviewer_id) if self.reviewer_id else None


@dataclass
class CurriculumUpload(FirestoreModel):
    collection_name: ClassVar[str] = "curriculum_uploads"

    source_filename: Optional[str] = None
    curriculum_name_th: Optional[str] = None
    faculty_name: Optional[str] = None
    revision_year: Optional[int] = None
    program_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_at: datetime = field(default_factory=_utcnow)
    json_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_filename": self.source_filename,
            "curriculum_name_th": self.curriculum_name_th,
            "faculty_name": self.faculty_name,
            "revision_year": self.revision_year,
            "program_id": self.program_id,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at,
            "json_data": self.json_data,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "CurriculumUpload":
        uploaded_at = data.get("uploaded_at")
        if not isinstance(uploaded_at, datetime):
            uploaded_at = _utcnow()
        revision_year = data.get("revision_year")
        try:
            revision_year = int(revision_year) if revision_year is not None and revision_year != "" else None
        except Exception:
            revision_year = None
        return cls(
            id=doc_id,
            source_filename=data.get("source_filename"),
            curriculum_name_th=data.get("curriculum_name_th"),
            faculty_name=data.get("faculty_name"),
            revision_year=revision_year,
            program_id=data.get("program_id"),
            uploaded_by=data.get("uploaded_by"),
            uploaded_at=uploaded_at,
            json_data=data.get("json_data") or {},
        )

    @property
    def program(self) -> Optional[Program]:
        return Program.get(self.program_id) if self.program_id else None

    @property
    def uploader(self) -> Optional["User"]:
        return User.get(self.uploaded_by) if self.uploaded_by else None


@dataclass
class User(UserMixin, FirestoreModel):
    collection_name: ClassVar[str] = "users"

    username: str = ""
    password_hash: str = ""
    full_name: str = ""

    # Roles: store as list, keep legacy single role compatibility
    roles: List[str] = field(default_factory=list)

    faculty_id: Optional[str] = None
    department_id: Optional[str] = None
    program_id: Optional[str] = None

    def get_id(self) -> str:
        # Flask-Login uses this as the session identifier
        return str(self.id or "")

    def to_dict(self) -> Dict[str, Any]:
        roles = [str(r).strip().lower() for r in (self.roles or []) if isinstance(r, str) and r.strip()]
        primary_role = roles[0] if roles else None
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "full_name": self.full_name,
            "roles": roles,
            # Backward compatibility: legacy data stored a single role string.
            "role": primary_role,
            "faculty_id": self.faculty_id,
            "department_id": self.department_id,
            "program_id": self.program_id,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "User":
        roles = data.get("roles")
        if isinstance(roles, str):
            roles = [roles]
        if not isinstance(roles, list):
            roles = []
        roles = [str(r).strip().lower() for r in roles if isinstance(r, str) and str(r).strip()]

        if not roles:
            legacy_role = data.get("role")
            if isinstance(legacy_role, str) and legacy_role.strip():
                roles = [legacy_role.strip().lower()]

        department_id = data.get("department_id")
        if not isinstance(department_id, str) or not department_id:
            department_id = None

        program_id = data.get("program_id")
        if not isinstance(program_id, str) or not program_id:
            program_id = None
        return cls(
            id=doc_id,
            username=(data.get("username") or ""),
            password_hash=(data.get("password_hash") or ""),
            full_name=(data.get("full_name") or ""),
            roles=roles,
            faculty_id=data.get("faculty_id"),
            department_id=department_id,
            program_id=program_id,
        )

    @classmethod
    def get_by_username(cls, username: str) -> Optional["User"]:
        username = (username or "").strip()
        if not username:
            return None
        # Use a query to allow doc_id strategy changes later.
        return cls.first_by("username", username)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password or "")

    def role_names(self) -> List[str]:
        roles = set(r for r in (self.roles or []) if r)
        order = {"admin": 0, "academic": 1, "head": 2, "instructor": 3}
        return sorted(roles, key=lambda x: order.get(x, 99))

    def has_role(self, role_name: str) -> bool:
        return role_name in set(self.role_names())

    def has_any_role(self, role_names: Iterable[str]) -> bool:
        user_roles = set(self.role_names())
        return any(r in user_roles for r in role_names)

    def best_role(self) -> str:
        roles = self.role_names()
        return roles[0] if roles else "instructor"

    @property
    def faculty(self) -> Optional[Faculty]:
        return Faculty.get(self.faculty_id) if self.faculty_id else None

    @property
    def department(self) -> Optional[Department]:
        return Department.get(self.department_id) if self.department_id else None

    @property
    def program(self) -> Optional[Program]:
        return Program.get(self.program_id) if self.program_id else None
