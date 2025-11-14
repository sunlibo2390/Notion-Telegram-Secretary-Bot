import json
from typing import List

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


def process_tasks():
    tasks_path = paths.raw_json_path("tasks")
    save_path = paths.processed_json_path("processed_tasks")
    projects_path = paths.processed_json_path("processed_projects")
    tasks_data = _load_json(tasks_path)
    projects_data = _load_json(projects_path) if projects_path.exists() else {}

    new_items = {}
    for item in tqdm(tasks_data.get("results", []), desc="tasks"):
        page_info = block_children_query(item["id"])
        md_text = notion_blocks_to_markdown(page_info.get("results", []))
        relations = item["properties"]["Projects"]["relation"]
        project_id = relations[0]["id"] if relations else None
        due = item["properties"]["Due Date"]["date"]
        page_url = item.get("url") or f"https://www.notion.so/{item['id'].replace('-', '')}"
        # print(item["properties"])
        new_item = {
            "name": item["properties"]["Name"]["title"][0]["plain_text"],
            "priority": item["properties"]["Priority"]["select"]["name"] if item["properties"]["Priority"]["select"] else "No Priority",
            "status": item["properties"]["Status"]["status"]["name"],
            "content": md_text,
            "project_id": project_id,
            "due_date": due["start"] if due else None,
            "page_url": page_url,
            "subtasks_id": [
                rel["id"] for rel in item["properties"]["Subtasks"]["relation"]
            ],
        }
        project_info = projects_data.get(project_id, {})
        new_item["project_name"] = project_info.get("name", "Unknown Project")
        if new_item["status"] not in ["Done", "Dormant"]:
            new_items[item["id"]] = new_item

    for task_id, task_info in new_items.items():
        subtask_names: List[str] = []
        for subtask_id in task_info["subtasks_id"]:
            subtask_info = new_items.get(subtask_id)
            if subtask_info:
                subtask_names.append(subtask_info["name"])
        task_info["subtask_names"] = subtask_names
        task_info.pop("subtasks_id", None)

    _save_json(save_path, new_items)
    print(f"Processed tasks saved to {save_path}")


if __name__ == "__main__":
    process_tasks()
