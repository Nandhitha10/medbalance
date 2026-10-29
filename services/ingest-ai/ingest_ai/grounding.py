"""Drug entity grounding engine using RapidFuzz over codes, names, and multilingual aliases."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set
import yaml
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingest_ai.db_models import DrugAliasModel, DrugModel


@dataclass(frozen=True)
class CandidateMatch:
    drug_code: str
    name: str
    score: float
    matched_term: str
    language: str


class GroundingEngine:
    """Grounds free-text drug mentions to canonical drug codes using RapidFuzz."""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None) -> None:
        self.entries: List[Dict[str, Any]] = []
        self.drug_meta: Dict[str, Dict[str, Any]] = {}
        if items:
            self._load_from_dict_list(items)
        else:
            self._load_fallback_from_yaml()

    @classmethod
    def from_db(cls, session: Session) -> "GroundingEngine":
        """Build grounding engine by querying drug and drug_alias tables."""
        try:
            drugs = session.scalars(select(DrugModel)).all()
            if not drugs:
                return cls()  # fallback to YAML

            items: List[Dict[str, Any]] = []
            for d in drugs:
                # Add code and name
                items.append({
                    "drug_code": d.code,
                    "name": d.name,
                    "term": d.code,
                    "language": "en",
                    "pack_size": d.pack_size,
                    "unit": d.unit,
                })
                items.append({
                    "drug_code": d.code,
                    "name": d.name,
                    "term": d.name,
                    "language": "en",
                    "pack_size": d.pack_size,
                    "unit": d.unit,
                })

            aliases = session.scalars(select(DrugAliasModel)).all()
            drug_lookup = {d.code: d for d in drugs}
            for a in aliases:
                d = drug_lookup.get(a.drug_code)
                items.append({
                    "drug_code": a.drug_code,
                    "name": d.name if d else a.drug_code,
                    "term": a.alias,
                    "language": a.language or "en",
                    "pack_size": d.pack_size if d else 1,
                    "unit": d.unit if d else "unit",
                })

            return cls(items)
        except Exception:
            return cls()

    def _load_fallback_from_yaml(self) -> None:
        """Load drugs and aliases from data/seed/drugs.yaml."""
        seed_path = Path("data/seed/drugs.yaml")
        if not seed_path.exists():
            # Try walking up
            seed_path = Path(__file__).resolve().parents[3] / "data" / "seed" / "drugs.yaml"

        if not seed_path.exists():
            return

        with open(seed_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        items: List[Dict[str, Any]] = []
        for d in data.get("drugs", []):
            code = d["code"]
            name = d["name"]
            pack_size = d.get("pack_size", 1)
            unit = d.get("unit", "unit")

            items.append({
                "drug_code": code,
                "name": name,
                "term": code,
                "language": "en",
                "pack_size": pack_size,
                "unit": unit,
            })
            items.append({
                "drug_code": code,
                "name": name,
                "term": name,
                "language": "en",
                "pack_size": pack_size,
                "unit": unit,
            })

            for alias_entry in d.get("aliases", []):
                items.append({
                    "drug_code": code,
                    "name": name,
                    "term": alias_entry["alias"],
                    "language": alias_entry.get("language", "en"),
                    "pack_size": pack_size,
                    "unit": unit,
                })

        self._load_from_dict_list(items)

    def _load_from_dict_list(self, items: List[Dict[str, Any]]) -> None:
        self.entries = []
        self.drug_meta = {}
        for it in items:
            code = it["drug_code"]
            self.entries.append({
                "drug_code": code,
                "name": it["name"],
                "term": it["term"].strip(),
                "language": it.get("language", "en"),
            })

            # Also add clean base molecule name without dosage specs
            clean_name = re.sub(
                r"\b(\d+(\.\d+)?\s*(mg|g|ml|iu|nos|tabs?|caps?|iu/ml|tablets?))\b",
                "",
                it["name"],
                flags=re.IGNORECASE,
            ).strip()
            if clean_name and clean_name.lower() != it["name"].lower():
                self.entries.append({
                    "drug_code": code,
                    "name": it["name"],
                    "term": clean_name,
                    "language": "en",
                })

            if code not in self.drug_meta:
                self.drug_meta[code] = {
                    "name": it["name"],
                    "pack_size": it.get("pack_size", 1),
                    "unit": it.get("unit", "unit"),
                }

    def match_mention(self, mention: str, top_k: int = 5, min_score: float = 0.40) -> List[CandidateMatch]:
        """Match a single mention string against all known terms, returning top-k drug candidates."""
        mention_str = mention.strip()
        if not mention_str:
            return []

        mention_lower = mention_str.lower()
        best_per_code: Dict[str, Dict[str, Any]] = {}

        for entry in self.entries:
            term = entry["term"]
            term_lower = term.lower()

            # Exact match boost
            if mention_lower == term_lower:
                score = 100.0
            else:
                w_score = fuzz.WRatio(mention_lower, term_lower)
                t_score = fuzz.token_sort_ratio(mention_lower, term_lower)
                p_score = fuzz.partial_ratio(mention_lower, term_lower)
                score = max(w_score, t_score, p_score if len(mention_lower) >= len(term_lower) else p_score * 0.85)

            norm_score = score / 100.0
            if norm_score < min_score:
                continue

            code = entry["drug_code"]
            if code not in best_per_code or norm_score > best_per_code[code]["score"]:
                best_per_code[code] = {
                    "drug_code": code,
                    "name": entry["name"],
                    "score": round(norm_score, 3),
                    "matched_term": term,
                    "language": entry["language"],
                }

        sorted_matches = sorted(
            best_per_code.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        return [
            CandidateMatch(
                drug_code=m["drug_code"],
                name=m["name"],
                score=m["score"],
                matched_term=m["matched_term"],
                language=m["language"],
            )
            for m in sorted_matches[:top_k]
        ]

    def extract_candidates_for_text(self, text: str, top_k: int = 5) -> List[str]:
        """Scan free-form text and return relevant candidate drug codes."""
        if not text:
            return list(self.drug_meta.keys())[:top_k]

        text_lower = text.lower()
        matched_scores: Dict[str, float] = {}

        for entry in self.entries:
            term = entry["term"].strip()
            term_lower = term.lower()
            if not term_lower:
                continue

            code = entry["drug_code"]

            # Substring check for Kannada or exact words
            if term_lower in text_lower:
                matched_scores[code] = max(matched_scores.get(code, 0.0), 1.0)
                continue

            # Partial ratio for multi-word or fuzzy tokens
            pr = fuzz.partial_ratio(term_lower, text_lower)
            if pr >= 80:
                matched_scores[code] = max(matched_scores.get(code, 0.0), pr / 100.0)

        # Also test individual words and tokens in text against terms
        tokens = re.findall(r"[\w\u0C80-\u0CFF]+", text)
        for token in tokens:
            if len(token) < 3:
                continue
            matches = self.match_mention(token, top_k=2, min_score=0.75)
            for m in matches:
                matched_scores[m.drug_code] = max(matched_scores.get(m.drug_code, 0.0), m.score)

        if not matched_scores:
            # Fallback to general formulary drugs
            return list(self.drug_meta.keys())[:top_k]

        sorted_codes = sorted(matched_scores.keys(), key=lambda c: matched_scores[c], reverse=True)
        return sorted_codes[:top_k]

    def get_pack_size(self, drug_code: str) -> int:
        """Get standard packaging size for base unit conversion."""
        return self.drug_meta.get(drug_code, {}).get("pack_size", 1)

    def get_base_unit(self, drug_code: str) -> str:
        """Get standard unit for drug."""
        return self.drug_meta.get(drug_code, {}).get("unit", "unit")
