"""测试基础设施：使用 SQLite 内存数据库进行测试."""

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vocab_qc.core.db import Base

# 使用 SQLite 内存数据库进行单元测试，无需 PostgreSQL
TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_word(db_session: Session):
    """创建一个示例单词."""
    from vocab_qc.core.models import ContentItem, Meaning, Phonetic, Source, Word

    word = Word(word="kind")
    db_session.add(word)
    db_session.flush()

    phonetic = Phonetic(word_id=word.id, ipa="/kaɪnd/", syllables="kind")
    db_session.add(phonetic)

    meaning1 = Meaning(word_id=word.id, pos="adj.", definition="友好的")
    meaning2 = Meaning(word_id=word.id, pos="n.", definition="种类")
    db_session.add_all([meaning1, meaning2])
    db_session.flush()

    source1 = Source(meaning_id=meaning1.id, source_name="人教版七年级英语上册（衔接小学）")
    source2 = Source(meaning_id=meaning2.id, source_name="人教版八年级英语下册")
    db_session.add_all([source1, source2])

    # 创建内容项
    chunk1 = ContentItem(word_id=word.id, meaning_id=meaning1.id, dimension="chunk", content="be kind to sb.")
    chunk2 = ContentItem(word_id=word.id, meaning_id=meaning2.id, dimension="chunk", content="a kind of")
    sentence1 = ContentItem(
        word_id=word.id,
        meaning_id=meaning1.id,
        dimension="sentence",
        content="The teacher is always kind to every student.",
        content_cn="老师对每位同学总是很友好。",
    )
    sentence2 = ContentItem(
        word_id=word.id,
        meaning_id=meaning2.id,
        dimension="sentence",
        content="There are many kinds of animals in the zoo.",
        content_cn="动物园里有很多种动物。",
    )
    # 助记按义项创建
    mnemonic_wiw = ContentItem(
        word_id=word.id,
        meaning_id=meaning1.id,
        dimension="mnemonic_word_in_word",
        content='{"formula": "kind = k + ind", "chant": "kind里藏着king", "script": "kind 和 king 只差一个字母，国王(king)对人友好(kind)"}',
    )
    mnemonic_ra = ContentItem(
        word_id=word.id,
        meaning_id=meaning1.id,
        dimension="mnemonic_root_affix",
        content='',
        qc_status="rejected",
    )
    db_session.add_all([chunk1, chunk2, sentence1, sentence2, mnemonic_wiw, mnemonic_ra])
    db_session.flush()

    return {
        "word": word,
        "phonetic": phonetic,
        "meanings": [meaning1, meaning2],
        "sources": [source1, source2],
        "chunks": [chunk1, chunk2],
        "sentences": [sentence1, sentence2],
        "mnemonics": [mnemonic_wiw, mnemonic_ra],
    }
