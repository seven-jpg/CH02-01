SYNTHETIC CONTRACT TEST ONLY

Every question, answer, search hit, prediction, score and run ID in this directory
is fabricated for deterministic validator tests. No model, data download or search
index was used. These are not real CRAG-MM samples or measured experiment results.
Do not copy them to data/processed/m3 or results/m3 or include them in a report.

The manifest deliberately uses data_origin="official" because m3.v1 requires that
literal. Its dataset_id and fixture_notice explicitly identify synthetic data.
A schema match cannot establish provenance. Passing these files proves format
handling only and cannot replace the group's real smoke test.

Rebuild the files with:
  python fixtures/synthetic/integration/build_fixture.py

The builder writes deterministic UTF-8/LF bytes and then hashes the manifest.
Regenerate after any checkout that changes file line endings. Behavior tests
rebuild the fixture in a temporary directory so they never change these files.

The fixture has three smoke IDs, empty dev/eval sets, full B0/B1 artifacts, and a
two-ID batch list. Null usage/latency means measurements were not taken.
