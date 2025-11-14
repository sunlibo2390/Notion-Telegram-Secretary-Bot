import json

from data_pipeline.storage import paths
from tqdm import tqdm


def _load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def process_projects():
    projects_path = paths.raw_json_path("projects")
    save_path = paths.processed_json_path("processed_projects")
    projects_data = _load_json(projects_path)

    new_items = {}
    for item in tqdm(projects_data.get("results", []), desc="projects"):
        new_item = {
            "name": item["properties"]["Name"]["title"][0]["plain_text"],
            "status": item["properties"]["Status"]["status"]["name"],
        }
        if new_item["status"] not in ["Done"]:
            new_items[item["id"]] = new_item

    _save_json(save_path, new_items)
    print(f"Processed projects saved to {save_path}")


if __name__ == "__main__":
    process_projects()
