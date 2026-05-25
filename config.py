import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# When running in Docker, AI_DATA_DIR env var points to the mounted volume
# (e.g. /app/data). On the host it falls back to BASE_DIR/data.
DATA_DIR = os.environ.get("AI_DATA_DIR", os.path.join(BASE_DIR, "data"))

# Model
MODEL = {
    "vocab_size": 8000,
    "d_model": 256,
    "num_heads": 8,
    "num_layers": 6,
    "d_ff": 1024,
    "max_seq": 512,
    "dropout": 0.1,
}

# Training
TRAINING = {
    "lr": 3e-4,
    "batch_size": 8,
    "nightly_epochs": 3,
    "min_texts_to_train": 10,
    "replay_ratio": 0.3,       # 30% old data mixed in during fine-tuning
    "ewc_lambda": 5000,        # EWC penalty strength
    "checkpoint_dir": os.path.join(DATA_DIR, "checkpoints"),
    "tokenizer_path": os.path.join(DATA_DIR, "tokenizer.json"),
}

# Memory
MEMORY = {
    "db_path": os.path.join(DATA_DIR, "experiences.db"),
    "vector_index_path": os.path.join(DATA_DIR, "faiss.index"),
    "encryption_key_path": os.path.join(DATA_DIR, ".key"),
    "max_replay_buffer": 5000,
    "embed_dim": 384,
}

# Monitoring
MONITORING = {
    "poll_interval": 5,        # seconds between app monitor polls
    "idle_threshold": 120,     # seconds before marking as idle
    "watched_code_extensions": [
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cpp", ".c",
        ".cs", ".go", ".rs", ".php", ".rb", ".html", ".css", ".sql",
    ],
    "watched_dirs": [           # directories to watch for code changes
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\Projects"),
        "D:\\Git_projects",
    ],
    "log_path": os.path.join(DATA_DIR, "activity.log"),
}

# Privacy — what is monitored (user controls these)
PRIVACY = {
    "monitor_apps": True,
    "monitor_code": True,
    "monitor_tasks": True,
    "monitor_time": True,
    "monitor_input": False,    # OFF by default — explicit opt-in required
    "excluded_apps": ["1Password", "KeePass", "banking"],
    "consent_path": os.path.join(DATA_DIR, "consent.json"),
}

# Suggestion engine
SUGGESTIONS = {
    "check_interval": 300,         # check every 5 minutes
    "min_pattern_occurrences": 3,  # need 3+ repeats before suggesting
}

# Security
#
# PRIVACY POLICY (what the AI can and cannot do):
#
#   ALWAYS ALLOWED — AI learns freely from all of these locally:
#     • Daily task monitoring (apps, files, documents)
#     • Code activity (files edited, languages, git commits)
#     • Screen/window activity patterns
#     • How you use the AI and how AI solves your tasks
#     • How AI codes and debugs alongside you
#     • Nightly self-training and model self-upgrade
#     • Storing conversations and observations locally
#
#   ALWAYS BLOCKED — requires your explicit command to proceed:
#     • Any outbound network call (NetworkGuard blocks at socket level)
#     • Exporting data to an external file or service
#     • Sharing data with any person or system
#     • Disabling encryption or the network guard
#
SECURITY = {
    "audit_log_path": os.path.join(DATA_DIR, "audit.log"),
    "audit_key_path": os.path.join(DATA_DIR, ".audit_key"),
    "breach_manifest_path": os.path.join(DATA_DIR, "integrity.json"),
    "network_guard_enabled": True,   # block ALL outbound connections
    "protected_files": [
        os.path.join(DATA_DIR, "experiences.db"),
        os.path.join(DATA_DIR, "faiss.index"),
        os.path.join(DATA_DIR, ".key"),
        os.path.join(DATA_DIR, "consent.json"),
    ],
}

DEVICE = "cuda" if __import__("torch").cuda.is_available() else "cpu"
