"""Download the AI Village transcripts from Hugging Face.

The dataset (https://huggingface.co/datasets/aidigestorg/ai-village) is GATED.
Before this script can work you must, once:

  1. Log in at https://huggingface.co and open the dataset page.
  2. Read and accept the "ai-village-research-terms" (research use only; no
     training on it without permission; do not re-identify people; cite AI
     Digest / AI Village). Access is reviewed manually.
  3. Create a read token at https://huggingface.co/settings/tokens and either
     run `huggingface-cli login` or set the environment variable HF_TOKEN.

Then, from the repo root:

    pip install huggingface_hub
    python scripts/download_ai_village.py                 # swarm-village (small, ~100 MB)
    python scripts/download_ai_village.py --village main-village --tables chat_messages,events

Screenshots (images/*.tar) are skipped by default because they are huge.
Files land in data/ai-village/<village>/ (git-ignored).
"""

import argparse
import os
import sys

REPO = "aidigestorg/ai-village"
SMALL_TABLES = ["chat_messages", "chat_rooms", "agents", "events",
                "computer_use_sessions", "village_goals", "agent_goals", "villages"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--village", default="swarm-village",
                   help="swarm-village | game-jam-village | open-chat-village | main-village")
    p.add_argument("--tables", default=",".join(SMALL_TABLES),
                   help="comma list of tables to fetch (without .jsonl.gz)")
    p.add_argument("--transcript", action="store_true",
                   help="also fetch village-transcript.json (large for main-village)")
    p.add_argument("--out", default="data/ai-village")
    args = p.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("Please `pip install huggingface_hub` first.")

    # Every village (main-village included, as of Nov 2026) is a folder.
    prefix = f"{args.village}/"
    patterns = [f"{prefix}{t}.jsonl.gz" for t in args.tables.split(",") if t]
    patterns += [f"{prefix}README.md", f"{prefix}manifest.json", "SCHEMA.md", "CHANGELOG.md"]
    # Note: if Python cannot reach huggingface.co, download the same files in a
    # signed-in browser and place them in data/ai-village/<village>/.
    if args.transcript:
        patterns.append(f"{prefix}village-transcript.json")

    # Files keep their repo paths under local_dir, so they land in
    # <out>/<village>/.
    local_dir = args.out
    final_dir = os.path.join(args.out, args.village)
    os.makedirs(local_dir, exist_ok=True)
    print(f"Downloading {len(patterns)} patterns from {REPO} into {final_dir} ...")
    try:
        snapshot_download(repo_id=REPO, repo_type="dataset",
                          allow_patterns=patterns, local_dir=local_dir,
                          token=os.environ.get("HF_TOKEN"))
    except Exception as e:  # gated / auth errors are the common case
        msg = str(e)
        if "401" in msg or "403" in msg or "gated" in msg.lower():
            sys.exit("Access denied. Accept the dataset terms on huggingface.co and log in "
                     "(huggingface-cli login, or set HF_TOKEN). Details: " + msg[:300])
        raise
    print("Done:", final_dir)
    print(f"Next:  python -m swarmscope.cli analyze {final_dir} "
          f"--format ai_village --out outputs/ai_village_{args.village}")


if __name__ == "__main__":
    main()
