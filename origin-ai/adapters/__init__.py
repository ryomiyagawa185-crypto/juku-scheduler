"""adapters — ランタイム固有・移行用の隔離層。

一次ランタイムは Claude Code に決めている。移植性の約束は
「skills/ 配下（SKILL.md + scripts + prompts）を素の Markdown と Python に保つ」
に限定し、ランタイム固有の接着剤は adapters/claude_code/ だけに置く。
そこを差し替えれば他のランタイムに載る、という限定した移植性。
"""
