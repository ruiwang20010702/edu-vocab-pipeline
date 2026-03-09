"""测试 ORM 模型基本功能."""

from vocab_qc.core.models import (
    ContentItem,
    Meaning,
    Phonetic,
    QcStatus,
    Source,
    Word,
)


def test_word_creation(db_session):
    word = Word(word="hello")
    db_session.add(word)
    db_session.flush()
    assert word.id is not None
    assert word.word == "hello"


def test_sample_word_fixture(sample_word):
    word = sample_word["word"]
    assert word.word == "kind"
    assert len(sample_word["meanings"]) == 2
    assert len(sample_word["chunks"]) == 2
    assert len(sample_word["sentences"]) == 2
    assert len(sample_word["mnemonics"]) > 0


def test_content_item_default_qc_status(db_session):
    word = Word(word="test")
    db_session.add(word)
    db_session.flush()

    item = ContentItem(word_id=word.id, dimension="chunk", content="test chunk")
    db_session.add(item)
    db_session.flush()

    assert item.qc_status == QcStatus.PENDING.value
    assert item.retry_count == 0
    assert item.last_qc_run_id is None


def test_meaning_with_sources(db_session):
    word = Word(word="run")
    db_session.add(word)
    db_session.flush()

    meaning = Meaning(word_id=word.id, pos="v.", definition="跑")
    db_session.add(meaning)
    db_session.flush()

    s1 = Source(meaning_id=meaning.id, source_name="人教版三年级上册")
    s2 = Source(meaning_id=meaning.id, source_name="人教版五年级上册")
    db_session.add_all([s1, s2])
    db_session.flush()

    assert len(meaning.sources) == 2


def test_phonetic_creation(db_session):
    word = Word(word="paper")
    db_session.add(word)
    db_session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/ˈpeɪ·pər/", syllables="pa·per")
    db_session.add(phonetic)
    db_session.flush()

    assert phonetic.ipa == "/ˈpeɪ·pər/"
    assert phonetic.syllables == "pa·per"
