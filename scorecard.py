"""
Contrato del scorecard — zona compartida entre el chat (productor) y el backend (consumidor).

Principio: el reclutador nunca ve este JSON crudo. El chat construye un Scorecard,
lo confirma, y lo bloquea en este formato para que el backend determinista lo ejecute.

No hay AI tool-calling aquí: esto es solo estructura y validacion.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal
import json

CriterionType = Literal["eliminatory", "scored"]


@dataclass
class Criterion:
    id: str
    label: str
    type: CriterionType
    points: int
    notes: str = ""  # umbral o senial para el evaluador, ej. "min 4 anios"


@dataclass
class Band:
    status: str       # Ideal / Avanzar / Pendiente / No recomendado
    min_score: int


@dataclass
class Scorecard:
    role: str
    location: str
    criteria: list[Criterion] = field(default_factory=list)
    bands: list[Band] = field(default_factory=list)

    @property
    def total_points(self) -> int:
        return sum(c.points for c in self.criteria)

    def band_for(self, score: int, disqualified: bool = False) -> str:
        # Regla fija: criterio eliminatorio fallado -> No recomendado, sin importar el puntaje.
        if disqualified:
            return "No recomendado"
        for band in sorted(self.bands, key=lambda b: b.min_score, reverse=True):
            if score >= band.min_score:
                return band.status
        return "No recomendado"

    def validate(self) -> list[str]:
        """Devuelve lista de problemas. Vacia = scorecard valido."""
        problems = []
        if not self.role.strip():
            problems.append("Falta el rol.")
        if not self.criteria:
            problems.append("El scorecard no tiene criterios.")
        if not any(c.type == "eliminatory" for c in self.criteria):
            problems.append("No hay ningun criterio eliminatorio definido.")
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)):
            problems.append("Hay IDs de criterio duplicados.")
        return problems

    def to_hidden_json(self) -> str:
        """El artefacto que se bloquea y se entrega al backend."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_hidden_json(cls, raw: str) -> "Scorecard":
        """Reconstruye el Scorecard desde el JSON bloqueado (lo inverso de to_hidden_json)."""
        d = json.loads(raw)
        return cls(
            role=d["role"],
            location=d.get("location", ""),
            criteria=[Criterion(**c) for c in d.get("criteria", [])],
            bands=[Band(**b) for b in d.get("bands", [])],
        )


# Bandas estandar del MVP v2.0
DEFAULT_BANDS = [
    Band("Ideal", 90),
    Band("Avanzar", 80),
    Band("Pendiente", 65),
    Band("No recomendado", 0),
]


def senior_go_developer() -> Scorecard:
    """Caso de oro: el scorecard de referencia fijo. 110 puntos totales."""
    return Scorecard(
        role="Senior Go Developer",
        location="Colombia",
        criteria=[
            Criterion("go", "Go/Golang min. 4 anios", "eliminatory", 30, "min 4 anios"),
            Criterion("exp", "Experiencia total dev min. 6 anios", "scored", 20, "min 6 anios"),
            Criterion("cloud", "Cloud + microservicios (K8s/AWS)", "scored", 20),
            Criterion("db", "Bases de datos (PostgreSQL/ClickHouse)", "scored", 15),
            Criterion("eng", "Ingles avanzado", "scored", 10, "flag informativo en LATAM"),
            Criterion("stab", "Estabilidad laboral (sin roles <1 anio)", "scored", 10),
            Criterion("edu", "Titulo universitario (Sistemas o afin)", "scored", 5),
        ],
        bands=DEFAULT_BANDS.copy(),
    )
