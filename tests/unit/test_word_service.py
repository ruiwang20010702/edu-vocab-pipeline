"""word_service 单元测试."""

from vocab_qc.core.services import word_service


class TestListWords:
    def test_empty_db(self, db_session):
        result = word_service.list_words(db_session)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1

    def test_with_sample_data(self, db_session, sample_word):
        result = word_service.list_words(db_session)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["word"] == "kind"

    def test_search_filter(self, db_session, sample_word):
        result = word_service.list_words(db_session, q="kind")
        assert result["total"] == 1

        result = word_service.list_words(db_session, q="nonexistent")
        assert result["total"] == 0

    def test_pagination(self, db_session, sample_word):
        result = word_service.list_words(db_session, page=1, limit=1)
        assert result["limit"] == 1
        assert result["page"] == 1

    def test_word_detail_has_phonetics(self, db_session, sample_word):
        result = word_service.list_words(db_session)
        word_data = result["items"][0]
        assert len(word_data["phonetics"]) == 1
        assert word_data["phonetics"][0].ipa == "/kaɪnd/"

    def test_word_detail_has_meanings(self, db_session, sample_word):
        result = word_service.list_words(db_session)
        word_data = result["items"][0]
        assert len(word_data["meanings"]) == 2

    def test_word_detail_has_mnemonic(self, db_session, sample_word):
        result = word_service.list_words(db_session)
        word_data = result["items"][0]
        assert len(word_data["mnemonics"]) > 0


class TestGetWordDetail:
    def test_not_found(self, db_session):
        assert word_service.get_word_detail(db_session, 9999) is None

    def test_found(self, db_session, sample_word):
        word_id = sample_word["word"].id
        result = word_service.get_word_detail(db_session, word_id)
        assert result is not None
        assert result["word"] == "kind"
        assert len(result["meanings"]) == 2
