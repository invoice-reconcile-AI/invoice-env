# evaluator.py
"""Batch evaluator — runs the agent against all three benchmark tasks
and prints a scorecard summary.

Usage:
    python evaluator.py
"""

import subprocess
import re
import json
import os
from collections import defaultdict

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# The three actual task IDs defined in server/env.py
ALL_TASKS = [
    "easy-exact-match",
    "medium-fuzzy-match",
    "hard-discrepancy-detection",
]

AGENT_MODULE = "agent.agent"   # run as: python -m agent.agent --task <id>
SUCCESS_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class AgentEvaluator:
    def __init__(self, agent_module: str = AGENT_MODULE) -> None:
        self.agent_module = agent_module
        self.results: list[dict] = []

    def run_evaluation(self) -> None:
        print("=========================================")
        print("  Starting Evaluation of Agent")
        print("=========================================\n")

        for task_id in ALL_TASKS:
            print(f"  Running task: {task_id} ... ", end="", flush=True)

            env_vars = os.environ.copy()
            env_vars["PYTHONIOENCODING"] = "utf-8"

            cmd = ["python", "-m", self.agent_module, "--task", task_id]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env_vars,
            )

            # Parse SCORECARD_JSON line from stdout
            json_match = re.search(r"SCORECARD_JSON: (\{.*\})", proc.stdout)

            if json_match:
                try:
                    scorecard = json.loads(json_match.group(1))
                    score      = float(scorecard.get("score", 0.0))
                    is_correct = bool(scorecard.get("correct_decision_made", False))
                    result_str = scorecard.get("result", "?")

                    if score >= 1.0:
                        mark = "[PASS]"
                    elif score >= SUCCESS_THRESHOLD:
                        mark = "[PASS]"
                    elif score >= 0.5:
                        mark = "[WARN]"
                    else:
                        mark = "[FAIL]"

                    print(f"{mark} Score={score:.2f} | result={result_str} | DecisionCorrect={is_correct}")

                    self.results.append({
                        "task_id":          task_id,
                        "score":            score,
                        "result":           result_str,
                        "correct_decision": is_correct,
                        "scorecard":        scorecard,
                    })

                except Exception as exc:
                    print(f"[FAIL] Parse error: {exc}")
                    self.results.append({"task_id": task_id, "score": 0.0, "result": "error"})
            else:
                print("[FAIL] No SCORECARD_JSON found — is the server running?")
                if proc.stderr:
                    print(f"  stderr: {proc.stderr[:300]}")
                self.results.append({"task_id": task_id, "score": 0.0, "result": "no_output"})

        self._print_summary()

    def _print_summary(self) -> None:
        print("\n=========================================")
        print("          Evaluation Summary")
        print("=========================================")

        total_score = 0.0
        passed      = 0

        for r in self.results:
            score   = r.get("score", 0.0)
            correct = r.get("correct_decision", False)
            result  = r.get("result", "?")
            if score >= SUCCESS_THRESHOLD:
                mark  = "[PASS]"
                passed += 1
            elif score >= 0.5:
                mark = "[WARN]"
            else:
                mark = "[FAIL]"
            print(f"  {mark}  {r['task_id']:35s}  score={score:.2f}  result={result}  correct={correct}")
            total_score += score

        n = len(self.results)
        avg = total_score / n if n else 0.0
        print(f"\n  Total  : {total_score:.2f} / {float(n):.1f}")
        print(f"  Avg    : {avg:.2f}")
        print(f"  Passed : {passed}/{n}  (threshold >= {SUCCESS_THRESHOLD})")
        print("=========================================")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    evaluator = AgentEvaluator()
    evaluator.run_evaluation()
