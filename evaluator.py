# evaluator.py
import subprocess
import re
import json
import os
from collections import defaultdict

# --- Configuration ---
NUM_TASKS_PER_DIFFICULTY = {
    "easy": 5,
    "medium": 5,
    "hard": 5
}
AGENT_SCRIPT = "agent.agent" 

class AgentEvaluator:
    def __init__(self, agent_script_module: str):
        self.agent_script_module = agent_script_module
        # Store total score and boolean correctness
        self.results = defaultdict(lambda: {"correct_decisions": 0, "total_tasks": 0, "total_score": 0.0, "details": []})

    def run_evaluation(self):
        print("=========================================")
        print(" Starting Batch Evaluation of Agent ")
        print("=========================================\n")
        
        for difficulty, num_tasks in NUM_TASKS_PER_DIFFICULTY.items():
            print(f"--- Evaluating {num_tasks} '{difficulty}' tasks ---")
            for i in range(num_tasks):
                task_id = f"{difficulty}_{i+1}"
                print(f"  Task {i+1}/{num_tasks} ({task_id}) ... ", end="", flush=True)

                cmd = ["python", "-m", self.agent_script_module, "--task", task_id]
                env_vars = os.environ.copy()
                env_vars["PYTHONIOENCODING"] = "utf-8"
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env_vars)
                
                # Parse the scorecard from stdout
                json_match = re.search(r'SCORECARD_JSON: (\{.*\})', result.stdout)
                
                if json_match:
                    try:
                        reward_data = json.loads(json_match.group(1))
                        score = reward_data.get("score", 0.0)
                        is_correct = reward_data.get("correct_decision_made", False)
                        
                        self.results[difficulty]["total_tasks"] += 1
                        self.results[difficulty]["total_score"] += score
                        if is_correct:
                            self.results[difficulty]["correct_decisions"] += 1
                            
                        mark = "✅" if score == 1.0 else ("⚠️" if score > 0.5 else "❌")
                        print(f"{mark} [ Score: {score:.2f} | DecisionCorrect: {is_correct} ]")
                        
                        self.results[difficulty]["details"].append({
                            "task_id": task_id,
                            "reward_data": reward_data,
                            "score": score
                        })
                    except Exception as e:
                        print(f"❌ [ Parse Error: {e} ]")
                else:
                    print(f"❌ [ Error parsing output: server down? ]")
                    if result.stderr:
                        print(result.stderr)
            print()

        self._print_summary()

    def _print_summary(self):
        print("\n=========================================")
        print("           Evaluation Summary            ")
        print("=========================================")
        
        overall_score = 0.0
        overall_total_tasks = 0

        for difficulty in ["easy", "medium", "hard"]: 
            res = self.results[difficulty]
            if res["total_tasks"] > 0:
                avg_score = res["total_score"] / res["total_tasks"]
                accuracy = (res["correct_decisions"] / res["total_tasks"]) * 100
                print(f"\n--- {difficulty.capitalize()} Tasks ---")
                print(f" Total Tasks       : {res['total_tasks']}")
                print(f" Average Score     : {avg_score:.2f} / 1.0")
                print(f" Decision Accuracy : {accuracy:.2f}%")
                
                overall_score += res["total_score"]
                overall_total_tasks += res["total_tasks"]
            else:
                print(f"\n--- {difficulty.capitalize()} Tasks ---")
                print(" No tasks evaluated.")

        if overall_total_tasks > 0:
            final_weighted_score = overall_score / overall_total_tasks
            print(f"\n=========================================")
            print(f" OVERALL PERFORMANCE : {final_weighted_score:.2%} SUCCESS ")
            print(f"=========================================")
        else:
            print("\nNo tasks evaluated in total.")

if __name__ == "__main__":
    evaluator = AgentEvaluator(AGENT_SCRIPT)
    evaluator.run_evaluation()

if __name__ == "__main__":
    evaluator = AgentEvaluator(AGENT_SCRIPT)
    evaluator.run_evaluation()
