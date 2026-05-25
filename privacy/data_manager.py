from datetime import datetime


class DataManager:
    """
    Lets the user view, inspect, and delete any data the AI has collected.
    Full transparency — you own your data.
    """

    def __init__(self, experience_buffer, vector_store=None):
        self.buffer = experience_buffer
        self.vector_store = vector_store

    def show_stats(self):
        stats = self.buffer.stats()
        print("\n--- Memory Stats ---")
        print(f"  Total experiences : {stats['total']}")
        print(f"  Trained           : {stats['trained']}")
        print(f"  Untrained         : {stats['untrained']}")
        print(f"  By type:")
        for t, count in stats.get("by_type", {}).items():
            print(f"    {t:<20} {count}")
        if self.vector_store:
            print(f"  Vector index size : {self.vector_store.size()}")
        print("--------------------\n")

    def show_recent(self, n=10, exp_type=None):
        rows = self.buffer.get_for_training(limit=n, types=[exp_type] if exp_type else None)
        print(f"\n--- Recent Experiences (last {n}) ---")
        for i, row in enumerate(rows, 1):
            print(f"  [{i}] [{row['type']}] {row['content'][:120]}...")
        print("-------------------------------------\n")
        return rows

    def delete_experience(self, exp_id: int):
        self.buffer.delete(exp_id)
        print(f"[DataManager] Experience #{exp_id} deleted.")

    def delete_all(self, confirm=False):
        if not confirm:
            print("[DataManager] Pass confirm=True to delete all data.")
            return
        self.buffer.delete_all()
        print("[DataManager] All experiences deleted.")

    def export_summary(self):
        stats = self.buffer.stats()
        return {
            "exported_at": datetime.now().isoformat(),
            "stats": stats,
        }
