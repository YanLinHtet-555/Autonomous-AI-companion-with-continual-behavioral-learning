import torch
import torch.nn as nn
import copy
from datetime import datetime


class ContinualLearner:
    """
    Wraps the Trainer with continual learning strategies:
    1. Experience Replay  — mixes old data with new to prevent forgetting
    2. EWC               — penalizes changing weights important to prior knowledge
    3. LoRA fine-tuning  — efficient updates via low-rank adapters

    This is the core engine that makes the AI improve every day
    without forgetting what it already learned.
    """

    def __init__(self, model, trainer, experience_buffer,
                 ewc_lambda=5000, replay_ratio=0.3, device="cpu",
                 ai_logger=None, level_system=None, get_study_minutes=None):
        self.model = model
        self.trainer = trainer
        self.buffer = experience_buffer
        self.ewc_lambda = ewc_lambda
        self.replay_ratio = replay_ratio
        self.device = device
        self.ai_logger = ai_logger
        self.level_system = level_system
        # Callable that returns total co-learning study minutes (injected to avoid
        # a circular import between ContinualLearner and CoLearner)
        self._get_study_minutes = get_study_minutes or (lambda: 0.0)

        # EWC state
        self._fisher = {}       # param name -> importance (Fisher diagonal)
        self._optimal_params = {}   # param name -> values after last consolidation
        self._ewc_ready = False

        self.train_history = []  # [{timestamp, loss, n_samples, strategy}]

    # ------------------------------------------------------------------ #
    # Main entry point — called nightly by the scheduler                  #
    # ------------------------------------------------------------------ #

    def learn(self, new_texts, epochs=3, batch_size=8, verbose=True):
        if not new_texts:
            print("[ContinualLearner] No new data — skipping")
            return None

        import time
        t_start = time.time()

        # Notify user training is starting
        if self.ai_logger:
            self.ai_logger.training_start(len(new_texts))

        # Mix new texts with replay sample
        replay = self.buffer.get_replay_sample(
            n=max(1, int(len(new_texts) * self.replay_ratio / (1 - self.replay_ratio)))
        )
        combined = new_texts + replay
        if verbose:
            print(f"[ContinualLearner] Training on {len(new_texts)} new + "
                  f"{len(replay)} replay = {len(combined)} total samples")

        # Backup model before training (for rollback)
        prev_step = self.trainer.step
        backup = copy.deepcopy(self.model.state_dict())

        # Fine-tune with EWC penalty
        total_loss = 0.0
        for epoch in range(epochs):
            loss = self.trainer.train_epoch(combined, batch_size)
            if self._ewc_ready:
                ewc_loss = self._ewc_penalty()
                self._apply_ewc_correction(ewc_loss)
            total_loss += loss
            if verbose:
                print(f"  Epoch {epoch+1}/{epochs} — loss: {loss:.4f}")

        avg_loss = total_loss / epochs

        # Safety check: if loss exploded, roll back
        if avg_loss > 10.0:
            if self.ai_logger:
                self.ai_logger.training_fail(
                    f"Loss exploded ({avg_loss:.4f}) — rolled back to previous checkpoint"
                )
                self.ai_logger.suspicious(
                    "Training loss exploded — unexpected model behaviour",
                    details={"avg_loss": avg_loss, "threshold": 10.0},
                )
            print("[ContinualLearner] Loss too high — rolling back to backup")
            self.model.load_state_dict(backup)
            return None

        # Consolidate new knowledge into EWC state
        self._consolidate(combined)

        # Save checkpoint with date tag
        date_tag = datetime.now().strftime("%Y%m%d")
        self.trainer.save_checkpoint(tag=date_tag)
        self.trainer.save_checkpoint(tag="latest")

        duration = time.time() - t_start
        record = {
            "timestamp": datetime.now().isoformat(),
            "new_samples": len(new_texts),
            "replay_samples": len(replay),
            "epochs": epochs,
            "avg_loss": round(avg_loss, 4),
            "duration_sec": round(duration),
        }
        self.train_history.append(record)

        # Notify user training ended and model upgraded
        if self.ai_logger:
            self.ai_logger.training_end(avg_loss, duration)
            self.ai_logger.self_upgrade(prev_step, self.trainer.step)
            self.ai_logger.checkpoint_saved(date_tag)

        if verbose:
            print(f"[ContinualLearner] Done. Avg loss: {avg_loss:.4f}")

        # Check whether training pushed the AI to the next level
        if self.level_system:
            self.level_system.update(
                experiences=self.buffer.stats().get("total", 0),
                training_sessions=len(self.train_history),
                study_minutes=self._get_study_minutes(),
            )

        return record

    # ------------------------------------------------------------------ #
    # EWC implementation                                                  #
    # ------------------------------------------------------------------ #

    def _consolidate(self, texts):
        """Compute Fisher information and save current weights as optimal."""
        self.model.eval()
        self._optimal_params = {
            n: p.data.clone()
            for n, p in self.model.named_parameters()
            if p.requires_grad
        }
        fisher = {n: torch.zeros_like(p) for n, p in self.model.named_parameters()
                  if p.requires_grad}

        sample = texts[:min(50, len(texts))]
        for text in sample:
            tokens = self.trainer.tokenizer.encode(text)
            if len(tokens) < 2:
                continue
            x = torch.tensor([tokens[:-1]], dtype=torch.long).to(self.device)
            y = torch.tensor([tokens[1:]], dtype=torch.long).to(self.device)
            y[y == 0] = -1

            self.model.zero_grad()
            _, loss = self.model(x, y)
            if loss is not None:
                loss.backward()
                for n, p in self.model.named_parameters():
                    if p.requires_grad and p.grad is not None:
                        fisher[n] += p.grad.data.pow(2)

        n = max(len(sample), 1)
        self._fisher = {n: f / n for n, f in fisher.items()}
        self._ewc_ready = True
        self.model.train()

    def _ewc_penalty(self):
        loss = torch.tensor(0.0, device=self.device)
        for n, p in self.model.named_parameters():
            if n in self._fisher and n in self._optimal_params:
                loss += (self._fisher[n] * (p - self._optimal_params[n]).pow(2)).sum()
        return (self.ewc_lambda / 2) * loss

    def _apply_ewc_correction(self, ewc_loss):
        """Nudge weights back toward optimal using EWC gradient."""
        if not ewc_loss.requires_grad:
            return
        try:
            ewc_loss.backward(retain_graph=True)
            with torch.no_grad():
                for p in self.model.parameters():
                    if p.requires_grad and p.grad is not None:
                        p.data -= self.trainer.optimizer.param_groups[0]["lr"] * p.grad
            self.model.zero_grad()
        except Exception:
            pass

    @property
    def training_sessions(self) -> int:
        return len(self.train_history)

    def get_learning_summary(self):
        if not self.train_history:
            return "No training sessions yet."
        last = self.train_history[-1]
        total_sessions = len(self.train_history)
        total_samples = sum(r["new_samples"] for r in self.train_history)
        return (
            f"{total_sessions} training sessions completed. "
            f"{total_samples} total samples learned. "
            f"Last session: {last['timestamp'][:10]}, "
            f"loss {last['avg_loss']}."
        )
