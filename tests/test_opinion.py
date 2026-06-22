"""Advice/opinion detection — keep these out of a news briefing."""
from briefing.ingest import make_article
from briefing.ingest.opinion import is_opinion


def _a(title, url="https://e.com/x"):
    return make_article(url=url, title=title, source_id="s", source_name="S", topics=["business"])


def test_drops_advice_and_opinion():
    assert is_opinion(_a("I'm 70. A relative offered me a $25,000 home loan secured by a lien"))
    assert is_opinion(_a("My husband wants to hide money from me. What should I do?"))
    assert is_opinion(_a("The Moneyist: I lent my brother $5,000 and he won't pay it back"))
    assert is_opinion(_a("Breaking news", url="https://wsj.com/opinion/a-hot-take"))
    # curly-quoted first-person advice column (MarketWatch style)
    assert is_opinion(_a("‘I’ll probably be working until I die’: I’m 60, wait tables and have $40k saved"))


def test_keeps_real_news():
    assert not is_opinion(_a("Alan Greenspan, who led the Fed for 18 years, dies at 100"))
    assert not is_opinion(_a("Pentagon awards drone autonomy contract worth $1.2 billion"))
    assert not is_opinion(_a("Intel strikes chip-manufacturing deal with Apple"))
