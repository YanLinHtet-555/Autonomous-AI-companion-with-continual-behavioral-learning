import json
import re
from collections import Counter


class BPETokenizer:
    """
    Byte-Pair Encoding tokenizer built from scratch.
    Starts with character-level vocab, learns merges from training text.
    """

    SPECIAL = {
        "<pad>": 0,
        "<unk>": 1,
        "<sos>": 2,
        "<eos>": 3,
        "<user>": 4,
        "<ai>": 5,
        "<obs>": 6,   # observation/activity events
        "<sep>": 7,   # separator between memory chunks
    }

    def __init__(self):
        self.vocab = {}
        self.inverse_vocab = {}
        self.merges = {}       # (a, b) -> merged
        self.merge_order = []  # ordered list for applying merges
        self.vocab_size = 0

    def train(self, texts, target_vocab_size=8000, min_freq=2):
        word_freq = Counter()
        for text in texts:
            for word in re.findall(r"\S+", text.lower()):
                spaced = " ".join(list(word)) + " </w>"
                word_freq[spaced] += 1

        # seed vocab: special tokens + all characters
        vocab = dict(self.SPECIAL)
        idx = len(vocab)
        for word in word_freq:
            for ch in word.split():
                if ch not in vocab:
                    vocab[ch] = idx
                    idx += 1

        bpe_vocab = dict(word_freq)

        while idx < target_vocab_size:
            pairs = self._count_pairs(bpe_vocab)
            if not pairs:
                break
            best_pair, freq = pairs.most_common(1)[0]
            if freq < min_freq:
                break
            merged = "".join(best_pair)
            bpe_vocab = self._merge(best_pair, merged, bpe_vocab)
            self.merges[best_pair] = merged
            self.merge_order.append(best_pair)
            if merged not in vocab:
                vocab[merged] = idx
                idx += 1

        self.vocab = vocab
        self.inverse_vocab = {v: k for k, v in vocab.items()}
        self.vocab_size = len(vocab)
        print(f"Tokenizer trained: {self.vocab_size} tokens")

    def _count_pairs(self, bpe_vocab):
        pairs = Counter()
        for word, freq in bpe_vocab.items():
            symbols = word.split()
            for i in range(len(symbols) - 1):
                pairs[(symbols[i], symbols[i + 1])] += freq
        return pairs

    def _merge(self, pair, merged, bpe_vocab):
        bigram = " ".join(pair)
        new_vocab = {}
        for word, freq in bpe_vocab.items():
            new_vocab[word.replace(bigram, merged)] = freq
        return new_vocab

    def _apply_merges(self, word):
        symbols = list(word) + ["</w>"]
        for pair in self.merge_order:
            i = 0
            new_symbols = []
            while i < len(symbols):
                if i < len(symbols) - 1 and (symbols[i], symbols[i + 1]) == pair:
                    new_symbols.append(self.merges[pair])
                    i += 2
                else:
                    new_symbols.append(symbols[i])
                    i += 1
            symbols = new_symbols
        return symbols

    def encode(self, text, add_special=True):
        tokens = [self.SPECIAL["<sos>"]] if add_special else []
        for word in re.findall(r"\S+", text.lower()):
            for sym in self._apply_merges(word):
                tokens.append(self.vocab.get(sym, self.SPECIAL["<unk>"]))
        if add_special:
            tokens.append(self.SPECIAL["<eos>"])
        return tokens

    def decode(self, token_ids):
        parts = []
        for tid in token_ids:
            sym = self.inverse_vocab.get(tid, "<unk>")
            if sym in self.SPECIAL:
                continue
            parts.append(sym.replace("</w>", " "))
        return "".join(parts).strip()

    def save(self, path):
        data = {
            "vocab": self.vocab,
            "merges": {f"{a}|||{b}": m for (a, b), m in self.merges.items()},
            "merge_order": [f"{a}|||{b}" for a, b in self.merge_order],
            "vocab_size": self.vocab_size,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.vocab = data["vocab"]
        self.merges = {tuple(k.split("|||")): v for k, v in data["merges"].items()}
        self.merge_order = [tuple(k.split("|||")) for k in data["merge_order"]]
        self.vocab_size = data["vocab_size"]
        self.inverse_vocab = {int(v): k for k, v in self.vocab.items()}
        print(f"Tokenizer loaded: {self.vocab_size} tokens")
