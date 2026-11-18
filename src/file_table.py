"""Fixed-size disk records and a sorted two-column primary-key index.

One active writer/service per directory. This teaching store has no WAL or
multi-file crash recovery; it is not a replacement for a production DBMS.
"""
import json
from pathlib import Path


class FileTable:
    RECORD_SIZE = 501
    PAYLOAD_SIZE = 500

    def __init__(self, root, name, model, key_field):
        self.path = Path(root) / f"{name}.txt"
        self.index_path = Path(root) / f"{name}_index.txt"
        self.model = model
        self.key_field = key_field
        self.path.touch(exist_ok=True)
        self.index_path.touch(exist_ok=True)
        # Only keys and offsets are loaded; data records remain on disk.
        with self.index_path.open(encoding="utf-8") as stream:
            self.index = dict(json.loads(line) for line in stream if line.strip())
        if self.path.stat().st_size % self.RECORD_SIZE:
            raise ValueError(f"Invalid record length: {self.path}")

    def encode(self, obj):
        payload = obj.model_dump_json().encode("utf-8")
        if len(payload) > self.PAYLOAD_SIZE:
            raise ValueError(f"Record exceeds {self.PAYLOAD_SIZE} bytes")
        return payload.ljust(self.PAYLOAD_SIZE, b" ") + b"\n"

    def _save_index(self):
        temporary = self.index_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for key, row in sorted(self.index.items()):
                stream.write(json.dumps([key, row], ensure_ascii=False) + "\n")
        temporary.replace(self.index_path)

    def get(self, key):
        row = self.index.get(key)
        return None if row is None else self.read_row(row)

    def read_row(self, row):
        with self.path.open("rb") as stream:
            stream.seek(row * self.RECORD_SIZE)
            raw = stream.read(self.RECORD_SIZE)
        if len(raw) != self.RECORD_SIZE:
            raise ValueError("Index points outside the data file")
        return self.model.model_validate_json(raw) if raw.strip() else None

    def scan(self):
        with self.path.open("rb") as stream:
            while raw := stream.read(self.RECORD_SIZE):
                if len(raw) != self.RECORD_SIZE:
                    raise ValueError("Truncated data record")
                if raw.strip():
                    yield self.model.model_validate_json(raw)

    def add(self, obj):
        key = getattr(obj, self.key_field)
        if key in self.index:
            raise ValueError(f"Duplicate key: {key}")
        raw = self.encode(obj)
        row = self.path.stat().st_size // self.RECORD_SIZE
        with self.path.open("ab") as stream:
            stream.write(raw)
        self.index[key] = row
        self._save_index()
        return obj

    def replace(self, key, obj):
        if key not in self.index:
            raise ValueError(f"Unknown key: {key}")
        new_key = getattr(obj, self.key_field)
        if new_key != key and new_key in self.index:
            raise ValueError(f"Duplicate key: {new_key}")
        raw = self.encode(obj)
        row = self.index[key]
        with self.path.open("r+b") as stream:
            stream.seek(row * self.RECORD_SIZE)
            stream.write(raw)
        if new_key != key:
            del self.index[key]
            self.index[new_key] = row
            self._save_index()
        return obj

    def delete(self, key):
        if key not in self.index:
            raise ValueError(f"Unknown key: {key}")
        # A blank record is a tombstone: subsequent offsets do not change.
        row = self.index[key]
        with self.path.open("r+b") as stream:
            stream.seek(row * self.RECORD_SIZE)
            stream.write(b" " * self.PAYLOAD_SIZE + b"\n")
        del self.index[key]
        self._save_index()
