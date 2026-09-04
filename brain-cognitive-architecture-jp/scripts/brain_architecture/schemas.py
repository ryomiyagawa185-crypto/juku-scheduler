# -*- coding: utf-8 -*-
"""schemas — 認知アーキテクチャ全体で共有する語彙（enum）と JSON Schema（dict）。

標準ライブラリのみで動くため jsonschema には依存しない。validation.py の軽量
バリデータがこの dict（type/required/properties/items/enum/patternProperties の
一部）を解釈する。schemas/*.json は外部ツール向けの正式版で、内容は本モジュールと
一致させている（tests/unit/test_schemas_sync が同期を検証）。

比喩とアルゴリズムの境界: enum 名は神経科学の機能語から借りているが、実体は
決定的な状態機械・スコア関数である。references/ に対応表と限界を明記する。
"""

# --- 入力元の信頼区分（仕様 §10 記憶汚染対策）---
# untrusted_external / model_generated は「事実候補」にはできるが「行動規則」へ
# 昇格できない（learning.py が強制）。
SOURCE_TRUST = [
    "system_policy",          # スキル自身の憲法・安全規則（最上位）
    "user_explicit",          # ユーザーの明示指示
    "user_confirmed",         # ユーザーが確認した内容
    "user_inferred",          # ユーザー意図の推測
    "verified_local",         # ローカル検証（テスト成功等）
    "verified_authoritative", # 権威ある一次情報で検証済み
    "untrusted_external",     # 外部文書・Web・ツール出力（未信頼）
    "model_generated",        # モデル生成（単独証拠にしない）
]
# 行動規則（procedural / constitutional）へ昇格を許す信頼区分。
TRUST_PROMOTABLE_TO_RULE = {"system_policy", "user_explicit", "user_confirmed",
                            "verified_local", "verified_authoritative"}
# 数値化した信頼の重み（証拠の強さの近似・0..1）。
TRUST_WEIGHT = {
    "system_policy": 1.0, "user_explicit": 0.95, "user_confirmed": 0.9,
    "verified_authoritative": 0.85, "verified_local": 0.75,
    "user_inferred": 0.45, "untrusted_external": 0.25, "model_generated": 0.2,
}

# --- スコープ（仕様 §5）。狭いスコープを優先し、恒久昇格は明示承認を要する ---
SCOPES = ["session", "task", "project", "client", "organization",
          "user", "machine", "global"]
# 狭い→広い（数字が小さいほど狭い）。既定解決は「狭いスコープ優先」。
SCOPE_BREADTH = {name: i for i, name in enumerate(SCOPES)}

# --- 記憶種別（仕様 §4）---
MEMORY_TYPES = ["sensory", "working", "episodic", "semantic", "procedural",
                "prospective", "emotional_salience", "inhibitory", "meta_memory"]

# --- 記憶のライフサイクル状態（仕様 §4）---
STATUS = ["observed", "candidate", "verified", "active", "conflicted",
          "deprecated", "archived", "rejected", "purged"]
# 想起・利用の対象になる状態（検索対象）。
RETRIEVABLE_STATUS = {"observed", "candidate", "verified", "active"}
# 変更不可・保持すべき安全記憶（単純な時間減衰で消さない・§7 忘却）。
PROTECTED_STATUS = {"active"}

# --- 昇格レベル（仕様 §8）L0..L5 と、それに対応する粗いライフサイクル状態 ---
LEVELS = ["L0", "L1", "L2", "L3", "L4", "L5"]
LEVEL_TO_STATUS = {
    "L0": "observed",   # 観測
    "L1": "candidate",  # 候補
    "L2": "candidate",  # 複数証拠で裏付け（corroborated）
    "L3": "verified",   # 独立検証済み
    "L4": "active",     # 再利用可能な手続
    "L5": "active",     # 憲法規則（constitutional）
}
LEVEL_ORDER = {lv: i for i, lv in enumerate(LEVELS)}

# --- メタ認知の知識状態（仕様 §L）。「見つからない」と「存在しない」を区別 ---
KNOWLEDGE_STATES = ["known_verified", "known_unverified", "inferred",
                    "conflicted", "unknown", "not_retrieved", "outdated"]

# --- 機密度（§11 プライバシー）---
SENSITIVITY = ["none", "low", "high"]

# --- イベント種別（append-only ログに刻む「事実」と「承認済み変更」）---
# 派生（decay/consolidate/decision の推論過程）はイベントにしない。
EVENT_KINDS = ["observation", "feedback", "promotion", "retraction",
               "inhibition", "note"]

# --- 結果（outcome）区分と品質重み（§H 予測誤差学習）---
OUTCOME_QUALITY = {
    "verified_success": 1.0,
    "retry_recovered": 0.75,
    "unverified_completion": 0.5,
    "unverified": 0.5,
    "partial_failure": 0.25,
    "user_rejected": 0.1,
    "verified_failure": 0.0,
    "aborted": 0.0,
    "unknown": 0.5,
}
OUTCOME_TYPES = sorted(OUTCOME_QUALITY.keys())
# 外部検証を伴う結果（自己申告のみは含めない・§7/§H）。
VERIFIED_OUTCOMES = {"verified_success", "verified_failure", "retry_recovered"}

# --- 型付き有向エッジの関係型（§6）。symmetric/directed と抑制性フラグを持つ ---
RELATION_TYPES = {
    "coactivated_with":  {"direction": "symmetric", "inhibitory": False},
    "precedes":          {"direction": "directed",  "inhibitory": False},
    "follows":           {"direction": "directed",  "inhibitory": False},
    "delegates_to":      {"direction": "directed",  "inhibitory": False},
    "validated_by":      {"direction": "directed",  "inhibitory": False},
    "supports":          {"direction": "directed",  "inhibitory": False},
    "contradicts":       {"direction": "symmetric", "inhibitory": True},
    "complements":       {"direction": "symmetric", "inhibitory": False},
    "substitutes_for":   {"direction": "symmetric", "inhibitory": False},
    "conflicts_with":    {"direction": "symmetric", "inhibitory": True},
    "inhibits":          {"direction": "directed",  "inhibitory": True},
    "depends_on":        {"direction": "directed",  "inhibitory": False},
    "generalizes":       {"direction": "directed",  "inhibitory": False},
    "specializes":       {"direction": "directed",  "inhibitory": False},
    "shares_input_schema":  {"direction": "symmetric", "inhibitory": False},
    "shares_output_schema": {"direction": "symmetric", "inhibitory": False},
    # 汚染対策の抑制関係（§10 例）: 未信頼入力 → 行動規則への昇格を禁止する。
    "must_not_promote":  {"direction": "directed", "inhibitory": True},
}
INHIBITORY_RELATIONS = {r for r, m in RELATION_TYPES.items() if m["inhibitory"]}

# --- 高顕著性（high-salience）操作（§I）。危険度とは別軸で「注意を向ける」対象 ---
# 高顕著性 ⇒ 自動拒否ではなく承認ゲートへ送る。
HIGH_SALIENCE_OPERATIONS = [
    "delete", "overwrite", "external_send", "credential_handling",
    "permission_change", "self_modification", "multi_device_deploy",
    "pii_processing", "legal_decision", "medical_decision",
    "financial_decision", "irreversible_config_change",
]

# --- 注意スコアの次元（§B）。単一値にしない ---
ATTENTION_DIMENSIONS = ["goal_relevance", "novelty", "urgency", "risk",
                        "uncertainty", "emotional_salience",
                        "expected_information_gain"]

# --- 方策評価の軸（§G/§12）。報酬値だけで決めない ---
POLICY_CRITERIA = ["goal_alignment", "expected_utility", "success_probability",
                   "reversibility", "risk", "cost", "latency",
                   "information_gain", "user_preference", "policy_compliance",
                   "evidence_quality", "uncertainty"]

# --- 提案（自己改変候補）の種別（§9）---
PROPOSAL_TYPES = ["semantic", "procedure", "edge", "deprecation", "skill_change"]
PROPOSAL_STATUS = ["open", "approved", "rejected", "applied", "rolled_back"]

# ====================================================================
# JSON Schema（dict 表現・validation.py が解釈）
# ====================================================================

EVENT_SCHEMA = {
    "type": "object",
    "required": ["event_id", "kind", "occurred_at", "scope", "source_trust",
                 "seq"],
    "properties": {
        "event_id": {"type": "string"},
        "kind": {"type": "string", "enum": EVENT_KINDS},
        "occurred_at": {"type": "string"},
        "recorded_at": {"type": "string"},
        "seq": {"type": "integer"},
        "scope": {"type": "string", "enum": SCOPES},
        "partition": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "source_trust": {"type": "string", "enum": SOURCE_TRUST},
        "contains_sensitive_data": {"type": "boolean"},
        "content_hash": {"type": ["string", "null"]},
        "session_id_hash": {"type": ["string", "null"]},
        "payload": {"type": "object"},
        "idempotent": {"type": "boolean"},
    },
}

MEMORY_SCHEMA = {
    "type": "object",
    "required": ["memory_id", "type", "scope", "status", "confidence",
                 "provenance", "created_at"],
    "properties": {
        "memory_id": {"type": "string"},
        "type": {"type": "string", "enum": MEMORY_TYPES},
        "level": {"type": "string", "enum": LEVELS},
        "status": {"type": "string", "enum": STATUS},
        "scope": {"type": "string", "enum": SCOPES},
        "partition": {"type": ["string", "null"]},
        "claim": {"type": ["string", "null"]},
        "content": {"type": ["object", "null"]},
        "confidence": {"type": "number"},
        "sensitivity": {"type": "string", "enum": SENSITIVITY},
        "provenance": {
            "type": "object",
            "required": ["source_trust"],
            "properties": {
                "source": {"type": ["string", "null"]},
                "source_trust": {"type": "string", "enum": SOURCE_TRUST},
            },
        },
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "counterevidence_ids": {"type": "array", "items": {"type": "string"}},
        "success_count": {"type": "integer"},
        "failure_count": {"type": "integer"},
        "created_at": {"type": "string"},
        "last_verified_at": {"type": ["string", "null"]},
        "last_used_at": {"type": ["string", "null"]},
        "valid_from": {"type": ["string", "null"]},
        "review_after": {"type": ["string", "null"]},
        "retention_until": {"type": ["string", "null"]},
        "deletion_policy": {"type": ["string", "null"]},
        "derived": {"type": "object"},
    },
}

EDGE_SCHEMA = {
    "type": "object",
    "required": ["edge_id", "source", "target", "relation", "scope"],
    "properties": {
        "edge_id": {"type": "string"},
        "source": {"type": "string"},
        "target": {"type": "string"},
        "relation": {"type": "string"},
        "direction": {"type": "string", "enum": ["symmetric", "directed"]},
        "scope": {"type": "string", "enum": SCOPES},
        "raw": {"type": "object"},
        "derived": {"type": "object"},
        "status": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
}

GOAL_SCHEMA = {
    "type": "object",
    "required": ["goal_id", "description", "scope"],
    "properties": {
        "goal_id": {"type": "string"},
        "description": {"type": "string"},
        "scope": {"type": "string", "enum": SCOPES},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "priority": {"type": "number"},
        "risk_tolerance": {"type": "number"},
        "created_at": {"type": "string"},
    },
}

POLICY_SCHEMA = {
    "type": "object",
    "required": ["candidate_id", "description"],
    "properties": {
        "candidate_id": {"type": "string"},
        "description": {"type": "string"},
        "operations": {"type": "array", "items": {"type": "string"}},
        "scope": {"type": "string", "enum": SCOPES},
        "criteria": {"type": "object"},
        "reversible": {"type": "boolean"},
        "requires_approval": {"type": "boolean"},
    },
}

PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["proposal_id", "type", "status", "rationale", "created_at"],
    "properties": {
        "proposal_id": {"type": "string"},
        "type": {"type": "string", "enum": PROPOSAL_TYPES},
        "status": {"type": "string", "enum": PROPOSAL_STATUS},
        "target_level": {"type": ["string", "null"], "enum": LEVELS + [None]},
        "rationale": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "diff": {"type": ["object", "null"]},
        "expected_effect": {"type": ["string", "null"]},
        "side_effects": {"type": ["string", "null"]},
        "counterexamples": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
        "approved_by": {"type": ["string", "null"]},
        "scope": {"type": "string", "enum": SCOPES},
    },
}

SNAPSHOT_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "scope", "as_of", "memories", "edges"],
    "properties": {
        "schema_version": {"type": "string"},
        "engine_version": {"type": "string"},
        "scope": {"type": "string"},  # scope 名 or "all"（メタスコープ）
        "generated_at": {"type": ["string", "null"]},
        "as_of": {"type": "string"},
        "event_count": {"type": "integer"},
        "source_event_hash": {"type": ["string", "null"]},
        "memories": {"type": "array", "items": MEMORY_SCHEMA},
        "edges": {"type": "array", "items": EDGE_SCHEMA},
        "working_memory": {"type": "array"},
        "stats": {"type": "object"},
    },
}

SCHEMAS_BY_NAME = {
    "event": EVENT_SCHEMA,
    "memory": MEMORY_SCHEMA,
    "edge": EDGE_SCHEMA,
    "goal": GOAL_SCHEMA,
    "policy": POLICY_SCHEMA,
    "proposal": PROPOSAL_SCHEMA,
    "snapshot": SNAPSHOT_SCHEMA,
}
