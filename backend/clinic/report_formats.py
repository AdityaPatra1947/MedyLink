"""Current report branding plus compatibility for already-issued monthly PDFs."""

MONTHLY_FORMAT = "medylink-monthly-v1"
MONTHLY_START = "MEDYLINK_MONTHLY_V1"
MONTHLY_END = "END_MEDYLINK_MONTHLY_V1"

# Issued PDFs and extracted clinical provenance are immutable. Keep accepting
# their original format without replacing patient records or report bytes.
MONTHLY_BLOCKS = (
    (MONTHLY_START, MONTHLY_END, MONTHLY_FORMAT),
    ("AROGYATRACK_MONTHLY_V1", "END_AROGYATRACK_MONTHLY_V1", "arogyatrack-monthly-v1"),
)
MONTHLY_FORMATS = tuple(block[2] for block in MONTHLY_BLOCKS)
