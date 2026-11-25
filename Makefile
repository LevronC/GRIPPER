# Evaluation targets. They refuse any database whose name does not start with
# gripper_eval or gripper_bench, and they refuse non-local hosts.
# Full benchmarks are not part of CI. See docs/EVALUATION.md.

PY ?= python
BACKEND := backend

.PHONY: eval-retrieval bench-search eval-explanations

eval-retrieval:
	cd $(BACKEND) && $(PY) scripts/eval_retrieval.py --replace

bench-search:
	cd $(BACKEND) && $(PY) scripts/benchmark_search.py --chunks 10000 --queries 200 --seed 42 --replace

eval-explanations:
	cd $(BACKEND) && $(PY) scripts/eval_explanations.py
