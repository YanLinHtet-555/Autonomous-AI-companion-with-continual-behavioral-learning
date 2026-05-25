import torch
import torch.nn as nn
import math


class LoRALinear(nn.Module):
    """
    Low-Rank Adaptation layer wrapping a frozen base Linear layer.
    Only the A and B matrices are trained — far fewer parameters,
    much faster fine-tuning, and less risk of destroying previous knowledge.

    delta_W = B @ A * (alpha / rank)
    """

    def __init__(self, base_layer: nn.Linear, rank: int = 8, alpha: float = 16.0):
        super().__init__()
        self.base = base_layer
        self.rank = rank
        self.alpha = alpha
        self.scaling = alpha / rank

        in_features = base_layer.in_features
        out_features = base_layer.out_features

        self.lora_A = nn.Parameter(torch.zeros(rank, in_features))
        self.lora_B = nn.Parameter(torch.zeros(out_features, rank))

        # initialize A with kaiming, B with zeros (so initial delta = 0)
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
        nn.init.zeros_(self.lora_B)

        # freeze base weights
        for p in self.base.parameters():
            p.requires_grad = False

    def forward(self, x):
        base_out = self.base(x)
        lora_out = (x @ self.lora_A.T @ self.lora_B.T) * self.scaling
        return base_out + lora_out

    def merge_weights(self):
        """Merge LoRA delta into base weights permanently."""
        with torch.no_grad():
            delta = (self.lora_B @ self.lora_A) * self.scaling
            self.base.weight.data += delta
        self.lora_A.data.zero_()
        self.lora_B.data.zero_()


def inject_lora(model, rank=8, alpha=16.0, target_modules=("q", "k", "v", "out")):
    """
    Replace Linear layers in target_modules with LoRALinear wrappers.
    Returns the modified model and a list of LoRA parameter groups.
    """
    replaced = 0
    for name, module in model.named_modules():
        for attr_name in target_modules:
            if hasattr(module, attr_name):
                layer = getattr(module, attr_name)
                if isinstance(layer, nn.Linear):
                    setattr(module, attr_name, LoRALinear(layer, rank=rank, alpha=alpha))
                    replaced += 1

    print(f"[LoRA] Injected {replaced} LoRA adapters (rank={rank})")

    lora_params = [p for n, p in model.named_parameters() if "lora_" in n]
    return model, lora_params


def extract_lora_state(model):
    """Save only the LoRA parameters (not full model weights)."""
    return {n: p.data.clone() for n, p in model.named_parameters() if "lora_" in n}


def load_lora_state(model, state_dict):
    """Load LoRA parameters back into model."""
    for name, param in model.named_parameters():
        if name in state_dict:
            param.data.copy_(state_dict[name])
