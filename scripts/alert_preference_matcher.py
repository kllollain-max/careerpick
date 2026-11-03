"""Safety-first matching of CareerPick ALIO jobs against OneSignal user tags.

No network requests or notification sending. All selected dimensions use AND
across dimensions and OR within each dimension. Unknown fields do not match.
"""
import re
import json

DIMENSIONS = {
    "region": ("region", "cp2_region_"),
    "employment": ("emp", "cp2_employment_"),
    "education": ("edu", "cp2_education_"),
    "category": ("cat", "cp2_category_"),
}

def tokens(value):
    if isinstance(value, list):
        return [str(v).strip().casefold() for v in value if str(v).strip()]
    return [str(value).strip().casefold()] if value is not None and str(value).strip() else []

def region_tokens(value):
    """Split ALIO multi-region strings without substring-based false matches."""
    if isinstance(value, list):
        parts = value
    elif isinstance(value, str):
        parts = [value]
    else:
        return []
    output = []
    for part in parts:
        output.extend(token.strip().casefold() for token in
                      re.split(r"[,，、;/|·\s]+", str(part)) if token.strip())
    return output

def compact_selected(tags, dimension):
    """Schema 3 stores one pipe-separated tag per preference dimension."""
    value = tags.get("cp3_" + dimension, "")
    if not isinstance(value, str):
        return []
    return [item.strip().casefold() for item in value.split("|") if item.strip()][:5]

def selected(tags, prefix):
    return [str(tags.get(prefix + str(i), "")).strip().casefold()
            for i in range(1, 6) if str(tags.get(prefix + str(i), "")).strip()]

def packed_preferences(tags):
    """Read strict two-tag schema 4; never infer opt-in from a profile alone."""
    if str(tags.get("cp_optin", "")).lower() != "yes":
        return None
    try:
        data = json.loads(tags.get("cp_profile", ""))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or type(data.get("v")) is not int or data["v"] != 4:
        return None
    for field in ("region", "employment", "education", "category"):
        values = data.get(field, [])
        if not isinstance(values, list) or len(values) > 5 or any(not isinstance(x, str) for x in values):
            return None
    if not isinstance(data.get("keywords", ""), str) or len(data.get("keywords", "")) > 200:
        return None
    if any(len(value) > 100 for field in ("region", "employment", "education", "category")
           for value in data.get(field, [])):
        return None
    return data

def matches(job, tags):
    profile = packed_preferences(tags)
    if profile is not None:
        choices = {field: [v.strip().casefold() for v in profile.get(field, []) if v.strip()]
                   for field in DIMENSIONS}
        keyword_source = profile.get("keywords", "")
    else:
        if str(tags.get("cp_optin", "")).lower() == "yes":
            return False  # Malformed v4 must not fall back to stale legacy tags.
        if str(tags.get("cp_preferences_set", "")).lower() != "yes":
            return False
        schema = str(tags.get("cp_schema", ""))
        if schema not in ("2", "3"):
            return False
        choices = {field: (compact_selected(tags, field) if schema == "3" else selected(tags, prefix))
                   for field, (_, prefix) in DIMENSIONS.items()}
        keyword_source = str(tags.get("cp_keywords", ""))
    if not any(choices.values()) and not keyword_source.strip():
        return False
    for dimension, (job_key, prefix) in DIMENSIONS.items():
        wants = choices[dimension]
        actual = region_tokens(job.get(job_key)) if job_key == "region" else tokens(job.get(job_key))
        if wants and not set(wants).intersection(actual):
            # Match the site: nationwide ALIO listings are regional candidates,
            # not confirmation of placement in the selected location.
            if dimension != "region" or not set(actual).intersection({"전국", "전지역"}):
                return False
    keywords = [s.strip().casefold() for s in re.split(r"[,，\s]+", keyword_source) if s.strip()]
    if keywords:
        text = " ".join(str(job.get(k) or "") for k in ("title", "org", "cat", "desc", "text")).casefold()
        if not any(word in text for word in keywords):
            return False
    return True
