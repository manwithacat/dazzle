"""Triple-verification helper for file-field writes (#1551 Task 4).

``verify_file_triple`` raises ``ValueError`` when a file reference's
stored metadata triple (entity_name / entity_id / field_name) does not
match the owning (entity, record_id, field) the caller is writing to.

The pending-file case (all three metadata fields empty) is ALLOWED —
that is the normal first-attach path.
"""

import pytest

from dazzle.http.runtime.document_routes import verify_file_triple

# A valid-looking file path with a real UUID so _extract_file_id picks it up.
_FILE_PATH = "/files/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/f.pdf"


def test_forged_triple_rejected() -> None:
    class _Meta:
        entity_name = "OtherEntity"
        entity_id = "x"
        field_name = "file"

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return _Meta()

    with pytest.raises(ValueError):
        verify_file_triple(_FS(), "Attachment", "r1", "file", _FILE_PATH)


def test_matching_triple_ok() -> None:
    class _Meta:
        entity_name = "Attachment"
        entity_id = "r1"
        field_name = "file"

    class _FS:
        def get_metadata(self, fid):  # type: ignore[no-untyped-def]
            return _Meta()

    verify_file_triple(_FS(), "Attachment", "r1", "file", _FILE_PATH)  # no raise
