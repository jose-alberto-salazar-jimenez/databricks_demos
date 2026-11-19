"""Client for the image classifier serving endpoint (MLflow pyfunc).

Contract: request dataframe_records=[{"image": <base64 image bytes>}]; each prediction is
{"predicted_class": str, "confidence": float, "probabilities": JSON string class -> prob}.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from databricks.sdk import WorkspaceClient


@dataclass(frozen=True)
class Prediction:
    predicted_class: str
    confidence: float
    probabilities: dict[str, float]


def parse_prediction(raw: dict) -> Prediction:
    """Validate and normalise one prediction returned by the endpoint."""
    probabilities = raw.get("probabilities")
    if isinstance(probabilities, str):
        probabilities = json.loads(probabilities)
    if not isinstance(probabilities, dict) or not probabilities:
        raise ValueError(f"Unexpected classifier response: {raw!r}")
    probabilities = {str(k): float(v) for k, v in probabilities.items()}
    predicted_class = str(raw["predicted_class"])
    if predicted_class not in probabilities:
        raise ValueError(f"Predicted class {predicted_class!r} missing from probabilities")
    return Prediction(predicted_class, float(raw["confidence"]), probabilities)


def classify(w: WorkspaceClient, endpoint: str, image_bytes: bytes) -> Prediction:
    """Score one image. Raises on transport or contract errors."""
    record = {"image": base64.b64encode(image_bytes).decode("ascii")}
    response = w.serving_endpoints.query(name=endpoint, dataframe_records=[record])
    predictions = response.predictions or []
    if len(predictions) != 1:
        raise ValueError(f"Expected 1 prediction, got {len(predictions)}")
    return parse_prediction(predictions[0])
