import torch
from datetime import datetime


class Chat:
    """
    The conversational interface for the AI companion.
    Injects relevant memory context before generating a response,
    so the AI 'remembers' past interactions and observations.
    """

    def __init__(self, model, tokenizer, experience_buffer,
                 vector_store=None, device="cpu", max_memory_chunks=5):
        self.model = model
        self.tokenizer = tokenizer
        self.buffer = experience_buffer
        self.vector_store = vector_store
        self.device = device
        self.max_memory_chunks = max_memory_chunks
        self._history = []   # [(user_text, ai_response), ...]

    def respond(self, user_input: str, temperature=0.8, max_new_tokens=200):
        # 1. Retrieve relevant memories
        memory_context = self._retrieve_memory(user_input)

        # 2. Build prompt: memory + recent history + current input
        prompt = self._build_prompt(user_input, memory_context)

        # 3. Generate response
        response = self._generate(prompt, temperature, max_new_tokens)

        # 4. Store in experience buffer for future training
        self.buffer.add_conversation(user_input, response)
        self._history.append((user_input, response))

        # 5. Add to vector store for future retrieval
        if self.vector_store:
            self.vector_store.add(
                f"User: {user_input} AI: {response}",
                metadata={"timestamp": datetime.now().isoformat(), "type": "conversation"},
            )

        return response

    def _retrieve_memory(self, query):
        if self.vector_store:
            results = self.vector_store.search(query, top_k=self.max_memory_chunks)
            return [r["text"] for r in results if r["score"] > 0.3]
        return []

    def _build_prompt(self, user_input, memory_context):
        parts = []

        # Inject relevant memories
        if memory_context:
            parts.append("<obs> " + " | ".join(memory_context[:3]))

        # Last 3 conversation turns for short-term context
        for user_turn, ai_turn in self._history[-3:]:
            parts.append(f"<user> {user_turn} <ai> {ai_turn}")

        # Current turn
        parts.append(f"<user> {user_input} <ai>")

        return " ".join(parts)

    def _generate(self, prompt, temperature, max_new_tokens):
        self.model.eval()
        tokens = self.tokenizer.encode(prompt, add_special=False)

        # Truncate to fit model's max sequence length
        max_ctx = self.model.max_seq - max_new_tokens - 10
        if len(tokens) > max_ctx:
            tokens = tokens[-max_ctx:]

        idx = torch.tensor([tokens], dtype=torch.long).to(self.device)

        with torch.no_grad():
            output = self.model.generate(
                idx,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_k=40,
            )

        # Decode only the newly generated tokens
        new_tokens = output[0][len(tokens):].tolist()
        response = self.tokenizer.decode(new_tokens)

        # Clean up any special token artifacts
        for tag in ["<user>", "<ai>", "<obs>", "<sep>", "<eos>", "<sos>"]:
            response = response.replace(tag, "").strip()

        return response if response else "..."

    def clear_history(self):
        self._history.clear()

    def get_history(self):
        return list(self._history)
