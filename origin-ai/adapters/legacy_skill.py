"""既存スキルの互換シム。

既存のスキル群はフロントマターに id/version しか持たないものが多い。
全部を一斉に書き換えてから移植するのは現実的でないので、
欠損フィールドを **保守的な既定値** で埋めて無改変のまま動かす。

保守的とは「安全側」の意味:
  risk=high / data_class=pii / gates=外部作用は承認 / stage=experimental /
  予算は小さく。つまり「不明なら厳しく」。
これで既存スキルは新基盤に載り、価値の高いものから順に
契約を書き足していける。ビッグバン移植を避けることが完走の条件。

legacy_shim: true が付いている間は stage を昇格させないこと
（build_registry.py が検査する）。
"""

from __future__ import annotations

# 契約に関わるフィールド。1つでも補ったら legacy_shim を立てる
CONTRACT_DEFAULTS = {
    "tier": "reasoning+execution",
    "risk": "high",
    "stage": "experimental",
    "data_class": "pii",
    "secrets": [],
    "gates": ["external-send", "destructive-ops"],
    "depends_on": [],
    "retry_policy": "none",
    "budget": {"per_call_usd": 0.05, "daily_usd": 0.50},
}

# 契約ではない付随情報。補っても legacy_shim にはしない
METADATA_DEFAULTS = {
    "triggers": [],
    "owner": "user",
    "eval_pass_rate": None,
    "last_evaluated": None,
}

CONSERVATIVE_DEFAULTS = {**CONTRACT_DEFAULTS, **METADATA_DEFAULTS}

REQUIRED_FROM_AUTHOR = ("id", "version")


class LegacySkillError(ValueError):
    pass


def adapt(frontmatter: dict) -> dict:
    """欠損フィールドを既定値で補い、legacy_shim を立てて返す。"""
    for key in REQUIRED_FROM_AUTHOR:
        if key not in frontmatter:
            raise LegacySkillError(f"{key} だけは既定値で補えません（スキル側に書いてください）")

    adapted = dict(frontmatter)
    filled_contract: list[str] = []
    for key, default in CONSERVATIVE_DEFAULTS.items():
        if key not in adapted:
            adapted[key] = default() if callable(default) else default
            if key in CONTRACT_DEFAULTS:
                filled_contract.append(key)

    # 契約フィールドを補った場合だけシム扱い。付随情報の欠落で昇格を止めない
    adapted["legacy_shim"] = bool(filled_contract)
    return adapted


def missing_fields(frontmatter: dict) -> list[str]:
    """まだ著者が書いていない契約フィールド。移行の進捗表示に使う。"""
    return [k for k in CONTRACT_DEFAULTS if k not in frontmatter]
