import os, json
from flask import current_app

def get_presets():
    with open(os.path.join(current_app.instance_path, "presets.json"), "r") as f:
        data = json.load(f)

    presets = [
        {"id": preset_id, "name": d.get("name"), "desc": d.get("description")}
        for (preset_id, d) in data.items()
    ]

    return presets
