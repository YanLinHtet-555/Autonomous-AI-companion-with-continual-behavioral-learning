"""
First-run setup for the AI Companion.
Run this once before starting main.py:

    python setup.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def check_dependencies():
    print("[Setup] Checking dependencies...")
    required = {
        "torch": "torch",
        "numpy": "numpy",
        "psutil": "psutil",
        "watchdog": "watchdog",
        "cryptography": "cryptography",
        "rich": "rich",
    }
    optional = {
        "faiss": "faiss-cpu",
        "sentence_transformers": "sentence-transformers",
        "win32gui": "pywin32",
        "pynput": "pynput",
        "git": "gitpython",
    }
    missing_required = []
    for module, pkg in required.items():
        try:
            __import__(module)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [MISSING] {pkg}")
            missing_required.append(pkg)

    for module, pkg in optional.items():
        try:
            __import__(module)
            print(f"  [OK] {pkg} (optional)")
        except ImportError:
            print(f"  [SKIP] {pkg} (optional — some features disabled)")

    if missing_required:
        print(f"\n[Setup] Install missing packages:")
        print(f"  pip install {' '.join(missing_required)}")
        print(f"  OR: pip install -r requirements.txt")
        sys.exit(1)
    print("[Setup] All required dependencies present.\n")


def train_tokenizer():
    from config import TRAINING
    from model.tokenizer import BPETokenizer

    tok_path = TRAINING["tokenizer_path"]
    if os.path.exists(tok_path):
        print(f"[Setup] Tokenizer already exists at {tok_path} — skipping")
        return

    print("[Setup] Training BPE tokenizer on seed corpus...")

    # Seed corpus: basic conversational and technical language
    seed_texts = [
        "hello how are you today i am doing well thank you",
        "what is your name my name is companion i am here to help you",
        "can you help me with my code i need to fix a bug in my program",
        "i am working on a python project using pytorch for machine learning",
        "the function returns a list of items sorted by their values",
        "error traceback most recent call last line file exception",
        "please open the file and read the contents into a variable",
        "git commit push pull branch merge conflict resolve",
        "import numpy as np import torch import os import sys",
        "class model init self layers forward backward loss optimizer",
        "def train epoch batch size learning rate gradient descent",
        "user interface button click event handler callback function",
        "database query select insert update delete table column row",
        "today i worked on the authentication module for three hours",
        "i usually start coding at nine in the morning and work until noon",
        "the meeting is scheduled for tuesday at two pm",
        "i prefer working in python over javascript for data tasks",
        "remember that i like concise answers without too much explanation",
        "you observed that i opened visual studio code and worked on main py",
        "the user spent forty five minutes using chrome browser on documentation",
        "continual learning prevents catastrophic forgetting in neural networks",
        "experience replay mixes old and new data during fine tuning",
        "elastic weight consolidation penalizes changing important weights",
        "low rank adaptation lora allows efficient fine tuning of language models",
        "the transformer architecture uses attention mechanisms to process sequences",
        "embeddings represent words as dense vectors in high dimensional space",
        "tokenization splits text into subword units using byte pair encoding",
        "the model generates one token at a time using autoregressive decoding",
        "temperature controls how random the model outputs are during generation",
        "higher temperature more creative lower temperature more deterministic",
    ] * 10  # repeat to increase frequency

    tokenizer = BPETokenizer()
    tokenizer.train(seed_texts, target_vocab_size=8000)
    tokenizer.save(tok_path)
    print(f"[Setup] Tokenizer saved: {tokenizer.vocab_size} tokens\n")


def bootstrap_model():
    import torch
    from config import MODEL, TRAINING, DEVICE
    from model.transformer import CompanionModel
    from model.tokenizer import BPETokenizer
    from model.trainer import Trainer

    ckpt_path = os.path.join(TRAINING["checkpoint_dir"], "checkpoint_latest.pt")
    if os.path.exists(ckpt_path):
        print("[Setup] Model checkpoint already exists — skipping bootstrap")
        return

    print("[Setup] Bootstrapping model with random weights + seed training...")

    tokenizer = BPETokenizer()
    tokenizer.load(TRAINING["tokenizer_path"])

    model = CompanionModel(vocab_size=tokenizer.vocab_size, **MODEL)
    model = model.to(DEVICE)
    print(f"[Setup] Model parameters: {model.parameter_count():,}")

    trainer = Trainer(model, tokenizer, device=DEVICE,
                      lr=TRAINING["lr"],
                      checkpoint_dir=TRAINING["checkpoint_dir"])

    seed_texts = [
        "hello i am your ai companion i am here to learn and help you",
        "i will watch your work and learn your patterns over time",
        "ask me anything and i will do my best to answer",
        "i learn from every conversation we have together",
        "i remember what you tell me and use it to improve",
    ] * 20

    print("[Setup] Running 5 bootstrap epochs...")
    for epoch in range(5):
        loss = trainer.train_epoch(seed_texts, batch_size=4)
        print(f"  Epoch {epoch+1}/5 — loss: {loss:.4f}")

    trainer.save_checkpoint(tag="latest")
    trainer.save_checkpoint(tag="bootstrap")
    print("[Setup] Model bootstrapped and saved.\n")


def setup_privacy():
    from config import PRIVACY
    from privacy.consent_manager import ConsentManager

    consent = ConsentManager(PRIVACY["consent_path"])
    if consent.has_consented():
        print("[Setup] Privacy consent already configured — skipping")
        return

    print("\n" + "="*60)
    print("  PRIVACY SETUP")
    print("="*60)
    print("\nThis AI companion monitors your PC activity to learn")
    print("your habits and workflows. ALL data stays on your machine.")
    print("\nDefault monitoring settings:")
    print("  [ON]  App usage tracking")
    print("  [ON]  Code file activity")
    print("  [ON]  Document activity")
    print("  [ON]  Time and routine patterns")
    print("  [OFF] Keyboard input stats (opt-in only)\n")

    choice = input("Accept default privacy settings? [Y/n]: ").strip().lower()
    if choice in ("", "y", "yes"):
        consent.grant_consent()
    else:
        print("\nCustomizing settings...")
        settings = {}
        for key in ["monitor_apps", "monitor_code", "monitor_tasks", "monitor_time"]:
            ans = input(f"  Enable {key}? [Y/n]: ").strip().lower()
            settings[key] = ans in ("", "y", "yes")
        settings["monitor_input"] = False
        consent.grant_consent(settings)
    print()


def create_data_dirs():
    from config import DATA_DIR, TRAINING
    dirs = [
        DATA_DIR,
        TRAINING["checkpoint_dir"],
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    print(f"[Setup] Data directory: {DATA_DIR}\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  AI COMPANION — FIRST-RUN SETUP")
    print("="*60 + "\n")

    create_data_dirs()
    check_dependencies()
    setup_privacy()
    train_tokenizer()
    bootstrap_model()

    print("="*60)
    print("  Setup complete. Run: python main.py")
    print("="*60 + "\n")
