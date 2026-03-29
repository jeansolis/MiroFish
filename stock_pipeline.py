#!/usr/bin/env python3
"""
MiroFish Stock Analysis Pipeline
Automatically researches a stock, generates documents, uploads to MiroFish,
and runs a full simulation to evaluate investment potential.

Usage:
    python stock_pipeline.py DVLT
    python stock_pipeline.py DVLT --rounds 20
    python stock_pipeline.py DVLT --mirofish-url https://your-app.easypanel.host
"""

import argparse
import json
import os
import sys
import time
import tempfile
import requests
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_MIROFISH_URL = os.environ.get("MIROFISH_URL", "http://localhost:3000")
DEFAULT_ROUNDS = 20
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
APP_PASSWORD = os.environ.get("MIROFISH_PASSWORD", "")

# ─── LLM Research ────────────────────────────────────────────────────────────

def research_stock(ticker: str) -> dict:
    """Use LLM to research a stock and generate structured analysis documents."""
    if not OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY environment variable is required.")
        print("Set it with: export OPENROUTER_API_KEY=your_key_here")
        sys.exit(1)

    print(f"\n📡 Researching {ticker} via LLM...")

    prompt = f"""Research the stock ticker "{ticker}" thoroughly and return a JSON object with exactly these 5 keys, each containing a detailed markdown document (at least 500 words each):

1. "company_overview": Company name, what they do, products/services, technology stack, leadership team, industries served. Include the full company name and ticker.

2. "financials": Latest quarterly and annual results, revenue, profit/loss, margins, EPS, market cap, stock price, 52-week range, any guidance. Include specific numbers.

3. "partnerships_and_deals": Major partnerships, clients, acquisitions, strategic deals, investor base, institutional ownership.

4. "risks_and_controversies": All known risks - financial risks, regulatory risks, lawsuits, short seller reports, insider selling, dilution, debt issues, going concern warnings, any controversies.

5. "market_and_competitors": Market opportunity/TAM, direct and indirect competitors with brief descriptions, company's competitive advantages and disadvantages, bull case summary, bear case summary.

IMPORTANT: Return ONLY valid JSON. No markdown code fences. Each value should be a string containing markdown-formatted text. Use real, factual, up-to-date information. If you don't have recent data, use the most recent information available and note the date."""

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 8000,
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    # Clean up potential markdown fences
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        docs = json.loads(content)
    except json.JSONDecodeError:
        print("ERROR: LLM returned invalid JSON. Raw response saved to _debug_response.txt")
        Path("_debug_response.txt").write_text(content)
        sys.exit(1)

    print(f"   ✓ Research complete — generated {len(docs)} documents")
    return docs


def save_documents(ticker: str, docs: dict, output_dir: str) -> list:
    """Save research documents as markdown files."""
    os.makedirs(output_dir, exist_ok=True)

    file_map = {
        "company_overview": f"01-{ticker}-company-overview.md",
        "financials": f"02-{ticker}-financials.md",
        "partnerships_and_deals": f"03-{ticker}-partnerships-and-deals.md",
        "risks_and_controversies": f"04-{ticker}-risks-and-controversies.md",
        "market_and_competitors": f"05-{ticker}-market-and-competitors.md",
    }

    saved_files = []
    for key, filename in file_map.items():
        if key in docs:
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w") as f:
                f.write(docs[key])
            saved_files.append(filepath)
            print(f"   ✓ Saved {filename}")

    return saved_files


# ─── MiroFish API ─────────────────────────────────────────────────────────────

class MiroFishClient:
    def __init__(self, base_url: str, password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 300

        # Authenticate if password is set
        if password:
            resp = self.session.post(
                f"{self.base_url}/api/auth/verify",
                json={"password": password},
            )
            if resp.status_code != 200 or not resp.json().get("authenticated"):
                print("ERROR: MiroFish authentication failed. Check MIROFISH_PASSWORD.")
                sys.exit(1)
            print("   ✓ Authenticated with MiroFish")

    def upload_and_generate_ontology(self, files: list, ticker: str, requirement: str) -> dict:
        """Step 1: Upload files and generate ontology."""
        print("\n🧬 Step 1/6: Uploading files and generating ontology...")

        file_handles = []
        try:
            for f in files:
                file_handles.append(("files", (os.path.basename(f), open(f, "rb"), "text/markdown")))

            resp = self.session.post(
                f"{self.base_url}/api/graph/ontology/generate",
                files=file_handles,
                data={
                    "simulation_requirement": requirement,
                    "project_name": f"{ticker} Investment Analysis",
                },
            )
        finally:
            for _, (_, fh, _) in file_handles:
                fh.close()

        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        project_id = data["data"]["project_id"]
        entity_count = len(data["data"]["ontology"].get("entity_types", []))
        edge_count = len(data["data"]["ontology"].get("edge_types", []))
        print(f"   ✓ Ontology generated: {entity_count} entity types, {edge_count} edge types")
        print(f"   ✓ Project ID: {project_id}")
        return data["data"]

    def build_graph(self, project_id: str) -> str:
        """Step 2: Build knowledge graph and poll until complete."""
        print("\n🕸️  Step 2/6: Building knowledge graph...")

        resp = self.session.post(
            f"{self.base_url}/api/graph/build",
            json={"project_id": project_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        task_id = data["data"]["task_id"]
        return self._poll_task(task_id)

    def _poll_task(self, task_id: str) -> str:
        """Poll a graph build task until completion."""
        while True:
            resp = self.session.get(f"{self.base_url}/api/graph/task/{task_id}")
            resp.raise_for_status()
            data = resp.json()["data"]

            status = data["status"]
            progress = data.get("progress", 0)
            message = data.get("message", "")

            print(f"   [{progress}%] {message}", end="\r")

            if status == "completed":
                graph_id = data["result"]["graph_id"]
                node_count = data["result"].get("node_count", "?")
                edge_count = data["result"].get("edge_count", "?")
                print(f"\n   ✓ Graph built: {node_count} nodes, {edge_count} edges")
                print(f"   ✓ Graph ID: {graph_id}")
                return graph_id
            elif status == "failed":
                print(f"\n   ERROR: Graph build failed — {message}")
                sys.exit(1)

            time.sleep(5)

    def create_simulation(self, project_id: str, graph_id: str) -> str:
        """Step 3: Create simulation."""
        print("\n🧪 Step 3/6: Creating simulation...")

        resp = self.session.post(
            f"{self.base_url}/api/simulation/create",
            json={"project_id": project_id, "graph_id": graph_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        sim_id = data["data"]["simulation_id"]
        print(f"   ✓ Simulation created: {sim_id}")
        return sim_id

    def prepare_simulation(self, simulation_id: str) -> None:
        """Step 4: Prepare simulation environment."""
        print("\n🧬 Step 4/6: Preparing simulation (generating agent profiles)...")

        resp = self.session.post(
            f"{self.base_url}/api/simulation/prepare",
            json={"simulation_id": simulation_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        if data["data"].get("status") == "preparing":
            task_id = data["data"].get("task_id")
            self._poll_prepare(task_id, simulation_id)
        else:
            print(f"   ✓ Simulation already prepared")

    def _poll_prepare(self, task_id: str, simulation_id: str) -> None:
        """Poll preparation status."""
        while True:
            resp = self.session.post(
                f"{self.base_url}/api/simulation/prepare/status",
                json={"task_id": task_id, "simulation_id": simulation_id},
            )
            resp.raise_for_status()
            data = resp.json()["data"]

            status = data["status"]
            progress = data.get("progress", 0)
            message = data.get("message", "")

            print(f"   [{progress}%] {message}", end="\r")

            if status == "completed":
                print(f"\n   ✓ Simulation prepared — agents and config ready")
                return
            elif status == "failed":
                print(f"\n   ERROR: Preparation failed — {message}")
                sys.exit(1)

            time.sleep(5)

    def start_simulation(self, simulation_id: str, max_rounds: int) -> None:
        """Step 5: Run simulation."""
        print(f"\n🌍 Step 5/6: Running simulation ({max_rounds} rounds)...")

        resp = self.session.post(
            f"{self.base_url}/api/simulation/start",
            json={
                "simulation_id": simulation_id,
                "max_rounds": max_rounds,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        self._poll_simulation(simulation_id, max_rounds)

    def _poll_simulation(self, simulation_id: str, max_rounds: int) -> None:
        """Poll simulation progress."""
        while True:
            resp = self.session.get(
                f"{self.base_url}/api/simulation/{simulation_id}/run-status"
            )
            resp.raise_for_status()
            data = resp.json()["data"]

            status = data.get("status", "unknown")
            current_round = data.get("current_round", 0)
            total_actions = data.get("total_actions", 0)

            print(f"   Round {current_round}/{max_rounds} | Actions: {total_actions}", end="\r")

            if status in ("completed", "stopped"):
                print(f"\n   ✓ Simulation complete — {total_actions} total actions")
                return
            elif status == "error":
                print(f"\n   ERROR: Simulation failed")
                sys.exit(1)

            time.sleep(10)

    def generate_report(self, simulation_id: str) -> str:
        """Step 6: Generate analysis report."""
        print("\n📊 Step 6/6: Generating analysis report...")

        resp = self.session.post(
            f"{self.base_url}/api/report/generate",
            json={"simulation_id": simulation_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            print(f"   ERROR: {data.get('error', 'Unknown error')}")
            sys.exit(1)

        report_id = data["data"]["report_id"]
        task_id = data["data"].get("task_id")

        if data["data"].get("status") == "generating" and task_id:
            self._poll_report(task_id, simulation_id)

        # Fetch final report
        resp = self.session.get(f"{self.base_url}/api/report/{report_id}")
        resp.raise_for_status()
        report_data = resp.json()["data"]
        print(f"   ✓ Report generated: {report_id}")
        return report_data

    def _poll_report(self, task_id: str, simulation_id: str) -> None:
        """Poll report generation status."""
        while True:
            resp = self.session.post(
                f"{self.base_url}/api/report/generate/status",
                json={"task_id": task_id, "simulation_id": simulation_id},
            )
            resp.raise_for_status()
            data = resp.json()["data"]

            status = data["status"]
            progress = data.get("progress", 0)
            message = data.get("message", "")

            print(f"   [{progress}%] {message}", end="\r")

            if status == "completed":
                print(f"\n   ✓ Report generation complete")
                return
            elif status == "failed":
                print(f"\n   ERROR: Report generation failed — {message}")
                sys.exit(1)

            time.sleep(10)


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="MiroFish Stock Analysis Pipeline — Research, simulate, and report on any stock.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  OPENROUTER_API_KEY    Your OpenRouter API key (required)
  OPENROUTER_MODEL      LLM model to use (default: anthropic/claude-sonnet-4)
  MIROFISH_URL          MiroFish instance URL (default: http://localhost:3000)
  MIROFISH_PASSWORD     MiroFish app password (if set)

Examples:
  python stock_pipeline.py NVDA
  python stock_pipeline.py TSLA --rounds 10
  python stock_pipeline.py AAPL --mirofish-url https://my-app.easypanel.host --rounds 30
  python stock_pipeline.py DVLT --research-only
        """,
    )
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., NVDA, TSLA, AAPL)")
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS, help=f"Simulation rounds (default: {DEFAULT_ROUNDS})")
    parser.add_argument("--mirofish-url", default=DEFAULT_MIROFISH_URL, help="MiroFish instance URL")
    parser.add_argument("--research-only", action="store_true", help="Only research and save docs, skip simulation")
    parser.add_argument("--docs-dir", default=None, help="Directory to save research documents")
    parser.add_argument("--requirement", default=None, help="Custom simulation requirement text")

    args = parser.parse_args()
    ticker = args.ticker.upper()
    docs_dir = args.docs_dir or os.path.join(tempfile.gettempdir(), f"mirofish-{ticker}")

    print(f"{'='*60}")
    print(f"  MiroFish Stock Analysis Pipeline")
    print(f"  Ticker: {ticker}")
    print(f"  Rounds: {args.rounds}")
    print(f"  MiroFish: {args.mirofish_url}")
    print(f"{'='*60}")

    # Step 0: Research the stock
    docs = research_stock(ticker)
    saved_files = save_documents(ticker, docs, docs_dir)
    print(f"   Documents saved to: {docs_dir}")

    if args.research_only:
        print(f"\n✅ Research complete. Documents saved to {docs_dir}")
        return

    # Default simulation requirement
    requirement = args.requirement or (
        f"Simulate how retail investors, institutional analysts, short sellers, "
        f"company executives, competitors, and financial journalists would debate "
        f"the investment case for {ticker} over the next 6 months. "
        f"Focus on growth potential, risks, competitive position, and whether "
        f"the stock represents a good investment opportunity at current prices."
    )

    # Connect to MiroFish
    client = MiroFishClient(args.mirofish_url, APP_PASSWORD)

    # Run the full pipeline
    ontology_data = client.upload_and_generate_ontology(saved_files, ticker, requirement)
    project_id = ontology_data["project_id"]

    graph_id = client.build_graph(project_id)

    sim_id = client.create_simulation(project_id, graph_id)

    client.prepare_simulation(sim_id)

    client.start_simulation(sim_id, args.rounds)

    report = client.generate_report(sim_id)

    # Save report
    report_file = os.path.join(docs_dir, f"{ticker}-report.md")
    with open(report_file, "w") as f:
        f.write(report.get("markdown_content", "No report content"))
    print(f"\n   Report saved to: {report_file}")

    print(f"\n{'='*60}")
    print(f"  ✅ Analysis complete for {ticker}!")
    print(f"  📄 Report: {report_file}")
    print(f"  🌐 View in MiroFish: {args.mirofish_url}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
