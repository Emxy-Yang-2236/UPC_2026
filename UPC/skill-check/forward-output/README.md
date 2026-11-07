# Cooling practice reproduction package

Start with the complete editable English paper at **`paper/manuscript.md`** and the scope/readiness decision at **`readiness.md`**. This is a synthetic practice result, not a real contest entry or an experimental study.

- `problem.md`: original supplied synthetic statement, copied unchanged.
- `model.md`: analytic derivation, assumptions, dimensions, limits and acceptance criteria.
- `data/inputs.json`: explicit inputs and numerical-check settings.
- `src/solve.py`: standard-library calculation and one RK4 implementation check.
- `data/derived/results.csv` and `results.md`: full-precision and display results.
- `data/derived/numerical_check.csv` and `summary.json`: actual numerical check outputs.
- `requirements.csv`, `sources.csv`, `parameters.csv`, `claims.csv`, `validation.csv`, `runs.csv`: skill-format evidence links.
- `review.md`: author self-check and its limits.
- `ai-records/coverage.md`: actual AI activity and incomplete transcript coverage.
- `contest-rules.md`: why no actual-contest compliance claim is made.

From this project directory, run:

```text
python src/solve.py
```

Python 3.9+ and its standard library suffice. This run used the available bundled Python 3.12.14. No third-party dependency, absolute-machine-path dependency, random seed, external dataset or network access is needed to reproduce the physics results. The script replaces only its own derived calculation outputs. `data/derived/reproduction-check.json` records the actual same-environment second-run comparison. The skill's separate structural audit is saved as `audit.json`; that audit does not validate physical realism, contest readiness or complete AI disclosure.
