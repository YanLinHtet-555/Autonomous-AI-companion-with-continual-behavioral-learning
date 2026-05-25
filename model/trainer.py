import os
import json
import torch
import torch.optim as optim
from datetime import datetime


class Trainer:
    """
    Handles model training, checkpoint saving/loading, and loss tracking.
    Used by both initial bootstrap training and continual learning fine-tuning.
    """

    def __init__(self, model, tokenizer, device="cpu", lr=3e-4,
                 checkpoint_dir="model/checkpoints"):
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.checkpoint_dir = checkpoint_dir
        self.optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=1000)
        self.step = 0
        self.loss_history = []
        os.makedirs(checkpoint_dir, exist_ok=True)

    def prepare_batch(self, texts, max_len=512):
        all_tokens = []
        for text in texts:
            tokens = self.tokenizer.encode(text)
            if len(tokens) > max_len:
                tokens = tokens[:max_len]
            all_tokens.append(tokens)

        max_t = max(len(t) for t in all_tokens)
        padded = [t + [0] * (max_t - len(t)) for t in all_tokens]

        x = torch.tensor([t[:-1] for t in padded], dtype=torch.long).to(self.device)
        y = torch.tensor([t[1:] for t in padded], dtype=torch.long).to(self.device)
        y[y == 0] = -1  # mask padding from loss
        return x, y

    def train_step(self, texts):
        self.model.train()
        x, y = self.prepare_batch(texts)
        _, loss = self.model(x, y)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()
        self.scheduler.step()
        self.step += 1
        return loss.item()

    def train_epoch(self, texts, batch_size=8):
        total_loss = 0.0
        num_batches = 0
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            if not batch:
                continue
            loss = self.train_step(batch)
            total_loss += loss
            num_batches += 1
        avg = total_loss / max(num_batches, 1)
        self.loss_history.append({"step": self.step, "loss": avg,
                                   "time": datetime.now().isoformat()})
        return avg

    def train(self, texts, epochs=1, batch_size=8, verbose=True):
        for epoch in range(epochs):
            avg_loss = self.train_epoch(texts, batch_size)
            if verbose:
                print(f"  Epoch {epoch+1}/{epochs} — loss: {avg_loss:.4f}")
        return avg_loss

    def save_checkpoint(self, tag="latest"):
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{tag}.pt")
        torch.save({
            "model_state": self.model.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "step": self.step,
            "loss_history": self.loss_history[-100:],  # keep last 100
            "timestamp": datetime.now().isoformat(),
        }, path)
        # also write metadata
        meta_path = os.path.join(self.checkpoint_dir, "meta.json")
        meta = self._load_meta()
        meta[tag] = {"step": self.step, "timestamp": datetime.now().isoformat()}
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        return path

    def load_checkpoint(self, tag="latest"):
        path = os.path.join(self.checkpoint_dir, f"checkpoint_{tag}.pt")
        if not os.path.exists(path):
            return False
        ckpt = torch.load(path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state"])
        self.optimizer.load_state_dict(ckpt["optimizer_state"])
        self.step = ckpt.get("step", 0)
        self.loss_history = ckpt.get("loss_history", [])
        print(f"Loaded checkpoint '{tag}' (step {self.step})")
        return True

    def _load_meta(self):
        path = os.path.join(self.checkpoint_dir, "meta.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    def get_loss_trend(self):
        if len(self.loss_history) < 2:
            return "not enough data"
        recent = [e["loss"] for e in self.loss_history[-10:]]
        trend = recent[-1] - recent[0]
        return f"{'improving' if trend < 0 else 'worsening'} ({trend:+.4f} over last {len(recent)} evals)"
