# -*- coding: utf-8 -*-
"""jobspec — ジョブ定義の読込とタスク分割（仕様 §10）。Job と Task を分離。

split 戦略:
  - per-file: input_glob を1ファイル1タスクへ分割（データ並列・§2 で優先）。
  - per-item: params.items を1要素1タスクへ。
  - none/whole: 単一タスク（input を全件）。
aggregation は control ノードで実行する集約タスク（merge 等）。
"""

import glob
import json
import os


def load_job(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return normalize(data)


def normalize(data):
    """§10 の `job:` サブキー形（name/policy を job 配下）を上位へ平坦化する。"""
    if not isinstance(data, dict):
        return data
    if isinstance(data.get("job"), dict):
        meta = data.pop("job")
        for k in ("name", "policy", "priority"):
            if k in meta and k not in data:
                data[k] = meta[k]
    return data


def _expand_inputs(task, base_dir):
    ig = task.get("input_glob")
    if ig:
        pattern = ig if os.path.isabs(ig) else os.path.join(base_dir, ig)
        return sorted(glob.glob(pattern))
    inp = task.get("input")
    if inp is None:
        return []
    files = inp if isinstance(inp, list) else [inp]
    return [f if os.path.isabs(f) else os.path.join(base_dir, f) for f in files]


def _concrete(task, inputs):
    return {
        "type": task.get("type", "task"),
        "executor": task["executor"],
        "input": inputs,
        "argv": task.get("argv"),
        "params": task.get("params") or {},
        "requirements": task.get("requirements") or {},
        "timeout_s": task.get("timeout_s"),
        "max_output_bytes": task.get("max_output_bytes"),
    }


def split_tasks(job_spec, base_dir="."):
    """ジョブを具体的なタスク列へ分割する。戻り値: (tasks, aggregation)。"""
    tasks = []
    for task in job_spec.get("tasks", []):
        split = task.get("split", "none")
        inputs = _expand_inputs(task, base_dir)
        if split == "per-file":
            if not inputs:
                tasks.append(_concrete(task, []))  # 入力0でも1タスク（結果に invalid_input）
            for f in inputs:
                tasks.append(_concrete(task, [f]))
        elif split == "per-item":
            items = (task.get("params") or {}).get("items", [])
            for it in items:
                t = _concrete(task, inputs)
                t["params"] = dict(t["params"], item=it)
                tasks.append(t)
        else:
            tasks.append(_concrete(task, inputs))
    return tasks, job_spec.get("aggregation")


def task_key(task, seq):
    """タスクの内容キー（冪等 task_id 生成用）。"""
    return "%s|%s|%s|%d" % (task.get("type"), task.get("executor"),
                            "|".join(task.get("input") or []), seq)
