"""Explicit live-provider smoke check using synthetic data and an isolated database."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from dealpilot.llm import get_provider
from dealpilot.agents import AgentWorkflow
from dealpilot.database import Database
from dealpilot.models import Customer


def main():
    provider = get_provider(load_local_env=True)
    print({k:v for k,v in provider.status().items() if k != "message"}, flush=True)
    def event(item):
        print({k:item[k] for k in ("node", "outcome", "elapsed_ms", "error")}, flush=True)
    with TemporaryDirectory(prefix="dealpilot-live-") as directory:
        result = AgentWorkflow(Database(Path(directory) / "smoke.sqlite3"), provider, event).start(
            "We need CRM integration for 10 users. Our budget is SAR 100000 including VAT. Delivery is required within 60 calendar days. We request a 15% discount.",
            Customer(id="live-smoke", name="Synthetic Live Demo Services", sector="services"))
        print({"status":result["status"], "errors":result["errors"], "verification":result["verification_findings"]})
        return 0 if result["status"] == "APPROVAL_PENDING" and not result["verification_findings"] else 1


if __name__ == "__main__":
    sys.exit(main())
