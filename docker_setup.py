"""
First-run setup for the Docker container.

Run this once after `docker-compose up` to initialise the model:

    docker-compose exec ai-companion python docker_setup.py

It is non-interactive: consent is auto-accepted and the tokenizer +
bootstrap model are trained automatically.  Data lands in /app/data/
(the volume mount defined in docker-compose.yml).
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import DATA_DIR, TRAINING, MODEL, DEVICE
import os


def create_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TRAINING["checkpoint_dir"], exist_ok=True)
    print(f"[DockerSetup] Data dir  : {DATA_DIR}")
    print(f"[DockerSetup] Checkpoint: {TRAINING['checkpoint_dir']}")


def auto_consent():
    from config import PRIVACY
    from privacy.consent_manager import ConsentManager

    consent = ConsentManager(PRIVACY["consent_path"])
    if consent.has_consented():
        print("[DockerSetup] Consent already configured — skipping")
        return

    # Auto-accept defaults: apps/code/tasks/time ON, input OFF
    consent.grant_consent({
        "monitor_apps": True,
        "monitor_code": True,
        "monitor_tasks": True,
        "monitor_time": True,
        "monitor_input": False,
    })
    print("[DockerSetup] Default privacy consent recorded.")


def train_tokenizer():
    from model.tokenizer import BPETokenizer

    tok_path = TRAINING["tokenizer_path"]
    if os.path.exists(tok_path):
        print(f"[DockerSetup] Tokenizer exists — skipping")
        return

    print("[DockerSetup] Training BPE tokenizer...")

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
    ] * 10

    tokenizer = BPETokenizer()
    tokenizer.train(seed_texts, target_vocab_size=8000)
    tokenizer.save(tok_path)
    print(f"[DockerSetup] Tokenizer saved — vocab size: {tokenizer.vocab_size}")


def bootstrap_model():
    import torch
    from model.transformer import CompanionModel
    from model.tokenizer import BPETokenizer
    from model.trainer import Trainer

    ckpt_path = os.path.join(TRAINING["checkpoint_dir"], "checkpoint_latest.pt")
    if os.path.exists(ckpt_path):
        print("[DockerSetup] Checkpoint exists — skipping bootstrap")
        return

    print(f"[DockerSetup] Bootstrapping model on {DEVICE}...")

    tokenizer = BPETokenizer()
    tokenizer.load(TRAINING["tokenizer_path"])

    model = CompanionModel(vocab_size=tokenizer.vocab_size, **MODEL).to(DEVICE)
    print(f"[DockerSetup] Parameters: {model.parameter_count():,}")

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

    print("[DockerSetup] Running 5 bootstrap epochs...")
    for epoch in range(5):
        loss = trainer.train_epoch(seed_texts, batch_size=4)
        print(f"  Epoch {epoch+1}/5 — loss: {loss:.4f}")

    trainer.save_checkpoint(tag="latest")
    trainer.save_checkpoint(tag="bootstrap")
    print("[DockerSetup] Model bootstrapped and saved.")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI COMPANION — DOCKER FIRST-RUN SETUP")
    print("=" * 60 + "\n")

    create_dirs()
    auto_consent()
    train_tokenizer()
    bootstrap_model()

    print("\n" + "=" * 60)
    print("  Setup complete. Restart the container:")
    print("    docker-compose restart ai-companion")
    print("=" * 60 + "\n")
