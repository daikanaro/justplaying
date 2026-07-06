"""Data layer (slice 4.1): download, roll, stitch, QC, and auxiliary loaders.

Raw per-contract data lands in ``data/raw/`` and is promoted to
``data/curated/`` only through :mod:`qt.data.qc` (criticals block promotion).
All timestamps are UTC; exchange time appears only in :mod:`qt.data.sessions`.
"""
