"""単価表とコスト算出。

キャッシュ階層を分けて持つ。1つの tokens_in に潰すと、プロンプト
キャッシュを使った瞬間にコストが実態から乖離し、しかも
「キャッシュ最適化が効いたかどうか」が測定できなくなる。

pricing/models.json は出荷時点で placeholder であり、
rates_for() は例外を投げる。これは意図的な fail-closed:
単価が未確定のまま予算ガードを動かすと見積りが 0 になり、
予算超過が永久にブロックされない（fail-open）ため。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from . import ROOT


class PlaceholderPricingError(RuntimeError):
    """単価表が未記入。policy 側はこれを握りつぶさず BLOCK に変換する。"""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def cache_hit_ratio(self) -> float:
        return self.cache_read_input_tokens / self.total_input if self.total_input else 0.0


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads((ROOT / "pricing" / "models.json").read_text(encoding="utf-8"))


def reload() -> None:
    _table.cache_clear()


def version() -> str:
    return _table()["version"]


def is_placeholder() -> bool:
    return bool(_table().get("placeholder", False))


def rates_for(model_id: str) -> dict:
    """1M トークンあたりの USD 単価を返す。未記入なら例外。"""
    table = _table()
    if table.get("placeholder", False):
        raise PlaceholderPricingError(
            "pricing/models.json が placeholder のままです。"
            "公式の料金表から実際の単価を記入し、placeholder を false にしてください。"
            "未記入のまま予算ガードを動かすと見積りが 0 になり、予算超過を検出できません。"
        )
    try:
        return table["models"][model_id]
    except KeyError as e:
        raise PlaceholderPricingError(f"単価表に未登録のモデル: {model_id}") from e


def cost_usd(usage: Usage, model_id: str, rates: dict | None = None) -> float:
    """キャッシュ階層別に課金する。rates を渡せばテストから単価を注入できる。"""
    r = rates if rates is not None else rates_for(model_id)
    per_million = (
        usage.input_tokens * r["input"]
        + usage.cache_creation_input_tokens * r["cache_write"]
        + usage.cache_read_input_tokens * r["cache_read"]
        + usage.output_tokens * r["output"]
    )
    return round(per_million / 1_000_000, 8)
