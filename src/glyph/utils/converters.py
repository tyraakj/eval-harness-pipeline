from enum import Enum

class SourceFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    PYTEST = "pytest"

def detect_format(*args, **kwargs):
    raise NotImplementedError("detect_format is not yet implemented")

def parse_source(*args, **kwargs):
    raise NotImplementedError("parse_source is not yet implemented")

def map_columns(*args, **kwargs):
    raise NotImplementedError("map_columns is not yet implemented")

def generate_id(*args, **kwargs):
    raise NotImplementedError("generate_id is not yet implemented")

def sanitize_case(*args, **kwargs):
    raise NotImplementedError("sanitize_case is not yet implemented")
