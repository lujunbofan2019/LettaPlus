"""Compute AMSP task complexity for model tier selection.

This tool implements the Adaptive Model Selection Protocol (AMSP) v3.0
complexity scoring system to determine the optimal model tier for a task
based on the required skills' complexity profiles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Environment configuration
MANIFESTS_DIR = os.getenv("DCF_MANIFESTS_DIR", "/app/generated/manifests")
SKILLS_CATALOG = os.getenv("DCF_SKILLS_CATALOG", "/app/generated/catalogs/skills_catalog.json")

# AMSP v3.0 Tier Boundaries (capability-based)
TIER_BOUNDARIES = [
    (0, 12, 0),   # Tier 0: FCS 0-12
    (13, 25, 1),  # Tier 1: FCS 13-25
    (26, 50, 2),  # Tier 2: FCS 26-50
    (51, float('inf'), 3),  # Tier 3: FCS 51+
]

# Tier descriptions for reasoning output
TIER_DESCRIPTIONS = {
    0: "Efficient (single-turn, deterministic, no tools)",
    1: "Balanced (multi-turn, simple tools, moderate context)",
    2: "Strong (complex reasoning, multi-tool, synthesis)",
    3: "Frontier (novel domains, research-grade, maximum capability)",
}

# Default model recommendations per tier (can be overridden by environment)
DEFAULT_MODELS_BY_TIER = {
    0: os.getenv("AMSP_TIER_0_MODEL", "openai/gpt-4o-mini"),
    1: os.getenv("AMSP_TIER_1_MODEL", "anthropic/claude-haiku-4-5"),
    2: os.getenv("AMSP_TIER_2_MODEL", "anthropic/claude-sonnet-4-5"),
    3: os.getenv("AMSP_TIER_3_MODEL", "anthropic/claude-opus-4-5"),
}

# Latency adjustment: critical latency may force lower tier
LATENCY_TIER_CEILING = {
    "critical": 1,   # Max Tier 1 for <2s response
    "standard": 3,   # No ceiling
    "relaxed": 3,    # No ceiling
    "batch": 3,      # No ceiling
}

# AMSP v3.0 Interaction Multipliers (21 pairs analyzed, these are the significant ones)
# Format: ((dim1, dim2), threshold_condition, multiplier, description)
INTERACTION_MULTIPLIERS = [
    # High Horizon combinations
    (("horizon", "context"), lambda h, c: h >= 2 and c >= 2, 1.15, "High Horizon + High Context"),
    (("horizon", "adaptability"), lambda h, a: h >= 2 and a >= 2, 1.10, "High Horizon + High Adaptability"),
    (("horizon", "tooling"), lambda h, t: h >= 2 and t >= 2, 1.08, "High Horizon + High Tooling"),

    # High Context combinations
    (("context", "precision"), lambda c, p: c >= 2 and p >= 2, 1.12, "High Context + High Precision"),
    (("context", "modality"), lambda c, m: c >= 2 and m >= 2, 1.10, "High Context + High Modality"),

    # High Tooling combinations
    (("tooling", "observability"), lambda t, o: t >= 2 and o >= 2, 1.15, "High Tooling + Low Observability"),
    (("tooling", "adaptability"), lambda t, a: t >= 2 and a >= 2, 1.08, "High Tooling + High Adaptability"),

    # High Precision combinations
    (("precision", "observability"), lambda p, o: p >= 2 and o >= 2, 1.12, "High Precision + Low Observability"),
    (("precision", "adaptability"), lambda p, a: p >= 2 and a >= 2, 1.10, "High Precision + High Adaptability"),

    # Triple-high penalty (any 3+ dimensions at max)
    # This is handled separately in _compute_triple_high_penalty
]

# WCM dimension weights (all 1.0 in AMSP v3.0, but configurable)
DIMENSION_WEIGHTS = {
    "horizon": 1.0,
    "context": 1.0,
    "tooling": 1.0,
    "observability": 1.0,
    "modality": 1.0,
    "precision": 1.0,
    "adaptability": 1.0,
}

DIMENSION_ORDER = ["horizon", "context", "tooling", "observability", "modality", "precision", "adaptability"]


def _normalize_skill_id(skill_id: str) -> str:
    """Normalize skill ID to standard format for manifest lookup.

    Handles various input formats:
    - skill://research.web@0.1.0 → skill.research.web@0.1.0
    - research.web@0.1.0 → skill.research.web@0.1.0
    - skill.research.web@0.1.0 → skill.research.web@0.1.0 (unchanged)
    """
    # Strip skill:// prefix
    if skill_id.startswith("skill://"):
        skill_id = skill_id[8:]  # Remove "skill://"

    # Add "skill." prefix if not present
    if not skill_id.startswith("skill."):
        skill_id = f"skill.{skill_id}"

    return skill_id


def _load_skill_manifest(skill_id: str) -> Optional[Dict[str, Any]]:
    """Load a skill manifest by ID from the manifests directory or catalog."""
    # Normalize the skill ID
    original_id = skill_id
    skill_id = _normalize_skill_id(skill_id)

    # Try direct file path first
    if original_id.startswith("file://") or original_id.endswith(".json"):
        path = Path(original_id.replace("file://", ""))
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass

    # Try manifests directory
    manifests_dir = Path(MANIFESTS_DIR)
    if manifests_dir.exists():
        # Generate filename variants (manifests use - instead of @ for version)
        filename_base = skill_id.replace("@", "-")
        patterns = [
            f"{skill_id}",           # skill.research.web@0.1.0
            f"{filename_base}",       # skill.research.web-0.1.0
            f"{skill_id}.json",       # skill.research.web@0.1.0.json
            f"{filename_base}.json",  # skill.research.web-0.1.0.json
        ]

        for pattern in patterns:
            candidate = manifests_dir / pattern
            if candidate.exists():
                try:
                    return json.loads(candidate.read_text(encoding="utf-8"))
                except Exception:
                    pass

        # Search by skillPackageId or manifestId (try both original and normalized)
        search_ids = {skill_id, original_id, _normalize_skill_id(original_id)}
        for manifest_file in manifests_dir.glob("*.json"):
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                manifest_id = manifest.get("manifestId", "")
                pkg_id = manifest.get("skillPackageId", "")
                if manifest_id in search_ids or pkg_id in search_ids:
                    return manifest
            except Exception:
                continue

    # Try catalog lookup
    catalog_path = Path(SKILLS_CATALOG)
    if catalog_path.exists():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            skills = catalog.get("skills", [])
            for skill in skills:
                if skill.get("skillPackageId") == skill_id or skill.get("manifestId") == skill_id:
                    # Catalog entry may have manifest path
                    manifest_path = skill.get("manifestPath")
                    if manifest_path:
                        full_path = Path(manifest_path)
                        if full_path.exists():
                            return json.loads(full_path.read_text(encoding="utf-8"))
                    return skill
        except Exception:
            pass

    return None


def _extract_complexity_profile(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract complexity profile from a skill manifest."""
    return manifest.get("complexityProfile")


def _aggregate_dimension_scores(profiles: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate dimension scores across multiple skills using max strategy."""
    aggregated = {dim: 0 for dim in DIMENSION_ORDER}

    for profile in profiles:
        dim_scores = profile.get("dimensionScores", {})
        for dim in DIMENSION_ORDER:
            score = dim_scores.get(dim, 0)
            if isinstance(score, (int, float)):
                aggregated[dim] = max(aggregated[dim], int(score))

    return aggregated


def _compute_base_wcs(dimension_scores: Dict[str, int]) -> int:
    """Compute base Weighted Complexity Score from dimension scores."""
    total = 0
    for dim in DIMENSION_ORDER:
        score = dimension_scores.get(dim, 0)
        weight = DIMENSION_WEIGHTS.get(dim, 1.0)
        total += score * weight
    return int(round(total))


def _compute_interaction_multipliers(dimension_scores: Dict[str, int]) -> Tuple[List[Dict[str, Any]], float]:
    """Compute applicable interaction multipliers and total multiplier."""
    applicable = []
    total_multiplier = 1.0

    for (dim1, dim2), condition_fn, multiplier, description in INTERACTION_MULTIPLIERS:
        score1 = dimension_scores.get(dim1, 0)
        score2 = dimension_scores.get(dim2, 0)

        if condition_fn(score1, score2):
            applicable.append({
                "pair": f"{dim1}+{dim2}",
                "multiplier": multiplier,
                "condition": description,
                "scores": {dim1: score1, dim2: score2},
            })
            total_multiplier *= multiplier

    # Triple-high penalty: if 3+ dimensions are at maximum (3)
    max_count = sum(1 for dim in DIMENSION_ORDER if dimension_scores.get(dim, 0) >= 3)
    if max_count >= 3:
        triple_penalty = 1.0 + (max_count - 2) * 0.05  # +5% per dimension beyond 2 at max
        applicable.append({
            "pair": "triple_high",
            "multiplier": triple_penalty,
            "condition": f"{max_count} dimensions at maximum (3)",
            "scores": {dim: dimension_scores[dim] for dim in DIMENSION_ORDER if dimension_scores.get(dim, 0) >= 3},
        })
        total_multiplier *= triple_penalty

    return applicable, round(total_multiplier, 3)


def _fcs_to_tier(fcs: float) -> int:
    """Map Final Complexity Score to model tier."""
    for lower, upper, tier in TIER_BOUNDARIES:
        if lower <= fcs <= upper:
            return tier
    return 3  # Default to highest tier for very high FCS


def _compute_confidence_interval(
    base_wcs: int,
    sample_sizes: List[int],
    maturity_levels: List[str],
) -> Dict[str, float]:
    """Compute confidence interval based on sample sizes and maturity."""
    # Base uncertainty from WCS
    base_uncertainty = base_wcs * 0.1  # ±10% baseline

    # Adjust based on maturity (more mature = tighter interval)
    maturity_factors = {
        "provisional": 1.5,
        "emerging": 1.2,
        "validated": 1.0,
        "stable": 0.8,
    }

    avg_factor = 1.0
    if maturity_levels:
        factors = [maturity_factors.get(m, 1.0) for m in maturity_levels]
        avg_factor = sum(factors) / len(factors)

    # Adjust based on sample size (more samples = tighter interval)
    total_samples = sum(sample_sizes) if sample_sizes else 0
    if total_samples >= 100:
        sample_factor = 0.8
    elif total_samples >= 30:
        sample_factor = 1.0
    elif total_samples >= 10:
        sample_factor = 1.2
    else:
        sample_factor = 1.5

    margin = base_uncertainty * avg_factor * sample_factor

    return {
        "lower": round(max(0, base_wcs - margin), 1),
        "upper": round(base_wcs + margin, 1),
    }


def compute_task_complexity(
    skills_json: str,
    context_features: Optional[str] = None,
    latency_requirement: str = "standard",
) -> Dict[str, Any]:
    """Compute AMSP complexity score for a task based on required skills.

    This implements the Adaptive Model Selection Protocol (AMSP) v3.0:
    1. Load complexity profiles from skill manifests
    2. Aggregate dimension scores (max strategy for multiple skills)
    3. Compute base Weighted Complexity Score (WCS)
    4. Apply interaction multipliers for dimension combinations
    5. Calculate Final Complexity Score (FCS = WCS × multipliers)
    6. Map FCS to recommended model tier

    Args:
        skills_json: JSON array of skill IDs (e.g., ["skill.research.web@0.1.0"])
                     or full skill manifest objects with complexityProfile
        context_features: Optional JSON with context overrides:
                         {"horizon": 3, "context": 2}  # Override specific dimensions
        latency_requirement: "critical" | "standard" | "relaxed" | "batch"
                            Critical latency may cap the tier at 1.

    Returns:
        {
            "status": str | None,
            "error": str | None,
            "base_wcs": int,
            "dimension_breakdown": {
                "horizon": int,
                "context": int,
                ...
            },
            "interaction_multipliers": [
                {"pair": str, "multiplier": float, "condition": str}
            ],
            "total_multiplier": float,
            "final_fcs": float,
            "confidence_interval": {"lower": float, "upper": float},
            "recommended_tier": int,
            "tier_description": str,
            "tier_reasoning": str,
            "recommended_model": str,
            "latency_adjusted_tier": int,  # May differ if latency_requirement is "critical"
            "latency_adjusted_model": str,
            "maturity_levels": {skill_id: str},
            "skills_analyzed": int,
            "skills_with_profiles": int,
            "warnings": []
        }
    """
    out: Dict[str, Any] = {
        "status": None,
        "error": None,
        "base_wcs": 0,
        "dimension_breakdown": {},
        "interaction_multipliers": [],
        "total_multiplier": 1.0,
        "final_fcs": 0.0,
        "confidence_interval": {},
        "recommended_tier": 0,
        "tier_description": "",
        "tier_reasoning": "",
        "recommended_model": "",
        "latency_adjusted_tier": 0,
        "latency_adjusted_model": "",
        "maturity_levels": {},
        "skills_analyzed": 0,
        "skills_with_profiles": 0,
        "warnings": [],
    }

    # Parse skills input
    skills: List[Any] = []
    try:
        parsed = json.loads(skills_json)
        if isinstance(parsed, list):
            skills = parsed
        elif isinstance(parsed, dict):
            # Single skill manifest provided
            skills = [parsed]
        else:
            out["error"] = "skills_json must be a JSON array of skill IDs or manifests"
            return out
    except Exception as e:
        out["error"] = f"Failed to parse skills_json: {e}"
        return out

    if not skills:
        out["error"] = "No skills provided"
        return out

    out["skills_analyzed"] = len(skills)

    # Parse context overrides
    context_overrides: Dict[str, int] = {}
    if context_features:
        try:
            parsed_ctx = json.loads(context_features)
            if isinstance(parsed_ctx, dict):
                for dim in DIMENSION_ORDER:
                    if dim in parsed_ctx:
                        val = parsed_ctx[dim]
                        if isinstance(val, (int, float)) and 0 <= val <= 3:
                            context_overrides[dim] = int(val)
        except Exception as e:
            out["warnings"].append(f"Failed to parse context_features: {e}")

    # Validate latency requirement
    if latency_requirement not in LATENCY_TIER_CEILING:
        out["warnings"].append(f"Unknown latency_requirement '{latency_requirement}', defaulting to 'standard'")
        latency_requirement = "standard"

    # Load and extract complexity profiles
    profiles: List[Dict[str, Any]] = []
    sample_sizes: List[int] = []
    maturity_levels_list: List[str] = []

    for skill in skills:
        skill_id = ""
        manifest: Optional[Dict[str, Any]] = None

        if isinstance(skill, str):
            skill_id = skill
            manifest = _load_skill_manifest(skill)
            if not manifest:
                out["warnings"].append(f"Could not load manifest for skill: {skill_id}")
                continue
        elif isinstance(skill, dict):
            skill_id = skill.get("skillPackageId") or skill.get("manifestId") or "inline"
            manifest = skill
        else:
            out["warnings"].append(f"Invalid skill entry type: {type(skill)}")
            continue

        profile = _extract_complexity_profile(manifest)
        if profile:
            profiles.append(profile)
            out["skills_with_profiles"] += 1

            # Track maturity and sample size
            maturity = profile.get("maturityLevel", "provisional")
            out["maturity_levels"][skill_id] = maturity
            maturity_levels_list.append(maturity)

            sample_size = profile.get("sampleSize", 0)
            sample_sizes.append(sample_size)

            # Warn about provisional profiles
            if maturity == "provisional":
                out["warnings"].append(
                    f"Skill '{skill_id}' has provisional complexity profile "
                    f"({sample_size} samples). Results may vary."
                )
        else:
            out["warnings"].append(f"No complexityProfile found in manifest: {skill_id}")

    if not profiles:
        # No profiles found - use default conservative estimate
        out["warnings"].append("No complexity profiles found. Using default Tier 1 estimate.")
        out["dimension_breakdown"] = {dim: 1 for dim in DIMENSION_ORDER}
        out["base_wcs"] = 7
        out["final_fcs"] = 7.0
        out["recommended_tier"] = 1
        out["tier_description"] = TIER_DESCRIPTIONS[1]
        out["tier_reasoning"] = "Default estimate (no profiles available)"
        out["recommended_model"] = DEFAULT_MODELS_BY_TIER[1]
        out["latency_adjusted_tier"] = min(1, LATENCY_TIER_CEILING[latency_requirement])
        out["latency_adjusted_model"] = DEFAULT_MODELS_BY_TIER[out["latency_adjusted_tier"]]
        out["status"] = "Complexity computed with default profile"
        return out

    # Aggregate dimension scores
    dimension_scores = _aggregate_dimension_scores(profiles)

    # Apply context overrides
    for dim, override_val in context_overrides.items():
        original = dimension_scores.get(dim, 0)
        dimension_scores[dim] = override_val
        if override_val != original:
            out["warnings"].append(f"Context override: {dim} changed from {original} to {override_val}")

    out["dimension_breakdown"] = dimension_scores

    # Compute base WCS
    base_wcs = _compute_base_wcs(dimension_scores)
    out["base_wcs"] = base_wcs

    # Compute interaction multipliers
    multipliers, total_multiplier = _compute_interaction_multipliers(dimension_scores)
    out["interaction_multipliers"] = multipliers
    out["total_multiplier"] = total_multiplier

    # Compute Final Complexity Score
    final_fcs = base_wcs * total_multiplier
    out["final_fcs"] = round(final_fcs, 1)

    # Compute confidence interval
    out["confidence_interval"] = _compute_confidence_interval(base_wcs, sample_sizes, maturity_levels_list)

    # Map to tier
    recommended_tier = _fcs_to_tier(final_fcs)
    out["recommended_tier"] = recommended_tier
    out["tier_description"] = TIER_DESCRIPTIONS.get(recommended_tier, "")
    out["tier_reasoning"] = f"FCS {out['final_fcs']} falls in Tier {recommended_tier} range"
    out["recommended_model"] = DEFAULT_MODELS_BY_TIER.get(recommended_tier, DEFAULT_MODELS_BY_TIER[2])

    # Apply latency constraint
    tier_ceiling = LATENCY_TIER_CEILING.get(latency_requirement, 3)
    latency_adjusted_tier = min(recommended_tier, tier_ceiling)
    out["latency_adjusted_tier"] = latency_adjusted_tier
    out["latency_adjusted_model"] = DEFAULT_MODELS_BY_TIER.get(latency_adjusted_tier, DEFAULT_MODELS_BY_TIER[2])

    if latency_adjusted_tier < recommended_tier:
        out["warnings"].append(
            f"Latency requirement '{latency_requirement}' capped tier from {recommended_tier} to {latency_adjusted_tier}"
        )

    out["status"] = f"Complexity computed: FCS={out['final_fcs']}, Tier={recommended_tier}"
    return out
