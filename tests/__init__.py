"""Test package for the Windows 10 Disaster Recovery application.

Why this file exists
--------------------
Making ``tests`` a regular package (rather than relying on pytest's
rootdir heuristics alone) guarantees that, when the documented command

    python -m pytest tests/

is run from the project root, the project root itself is placed on
``sys.path`` and ``import src.models`` resolves unambiguously against the
in-tree ``src`` package (README §4).

Safety posture
--------------
Tests in this package are strictly read-only and pure-memory: they never
touch block devices, mounts, the host filesystem outside ``tmp_path``-style
fixtures, databases, or subprocesses (NFR-10).  The module under test
(:mod:`src.models`) is itself inert; this package adds no I/O capability.
"""
