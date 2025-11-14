import json

from block2md import notion_blocks_to_markdown
from block_children_query import block_children_query
from data_pipeline.storage import paths
from tqdm import tqdm


def _load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def process_logs():
    logs_path = paths.raw_json_path("logs")
    save_path = paths.processed_json_path("processed_logs")
    tasks_path = paths.processed_json_path("processed_tasks")
    logs_data = _load_json(logs_path)
    tasks_data = _load_json(tasks_path) if tasks_path.exists() else {}

    new_items = {}
    for item in tqdm(logs_data.get("results", []), desc="logs"):
        page_info = block_children_query(item["id"])
        md_text = notion_blocks_to_markdown(page_info.get("results", []))
        relation = item["properties"]["Task"]["relation"]
        task_id = relation[0]["id"] if relation else None
        new_item = {
            "name": item["properties"]["Name"]["title"][0]["plain_text"],
            "status": item["properties"]["Status"]["status"]["name"],
            "content": md_text,
            "task_id": task_id,
        }
        new_item["task_name"] = tasks_data.get(task_id, {}).get("name", "Unknown Task")
        if new_item["status"] not in ["Done", "Dormant"]:
            new_items[item["id"]] = new_item

    _save_json(save_path, new_items)
    print(f"Processed logs saved to {save_path}")


if __name__ == "__main__":
    process_logs()
