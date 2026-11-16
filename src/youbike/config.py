"""Project-wide settings shared by every analysis file."""

# Study period: March-June 2026.
# The e-bike share of rides rose from 4.2% (2025-08) to 8.5% (2026-07) as more
# e-bikes were deployed, so months are not directly comparable. Keeping the study
# to four consecutive months with a stable fleet avoids that confound.
STUDY_MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06"]

SEED = 42
