from __future__ import annotations

ACTIVE_KEYWORD = "\uc561\ud2f0\ube0c"

NON_EQUITY_KEYWORDS = [
    "\ucc44\uad8c",
    "\uad6d\ucc44",
    "\ud68c\uc0ac\ucc44",
    "\ud1b5\uc548\ucc44",
    "\ub2e8\uae30\ucc44",
    "\uc911\uae30\ucc44",
    "\uc7a5\uae30\ucc44",
    "\uc885\ud569\ucc44\uad8c",
    "\uae08\ub9ac",
    "CD",
    "KOFR",
    "MMF",
    "\uba38\ub2c8\ub9c8\ucf13",
    "\ub2ec\ub7ec",
    "\uc5d4\ud654",
    "\ud658\uc728",
    "\uc6d0\uc790\uc7ac",
    "\uae08\uc120\ubb3c",
    "\uae08\ud604\ubb3c",
    "\uace8\ub4dc",
    "\uc740\uc120\ubb3c",
    "\uad6c\ub9ac",
    "\uc6d0\uc720",
    "\ub18d\uc0b0\ubb3c",
    "\ub9ac\uce20",
    "REIT",
    "\ubd80\ub3d9\uc0b0",
]


def is_active_etf_name(name: str) -> bool:
    return ACTIVE_KEYWORD in str(name)


def is_equity_active_etf_name(name: str) -> bool:
    text = str(name).strip()
    upper = text.upper()
    if not is_active_etf_name(text):
        return False
    return not any(keyword.upper() in upper for keyword in NON_EQUITY_KEYWORDS)
