"""测试 IPA 导入功能."""

from vocab_qc.core.models import Word, Phonetic
from vocab_qc.core.services import import_service


class TestImportWithIPA:
    def test_import_with_ipa(self, db_session):
        """验证 IPA 字段在导入时正确保存到 Phonetic 表。"""
        data = [
            {
                "word": "apple",
                "ipa": "/ˈæp.əl/",
                "meanings": [
                    {"pos": "n.", "definition": "苹果", "sources": ["人教七上U1"]}
                ]
            },
            {
                "word": "beautiful",
                "ipa": "/ˈbjuː.tə.fəl/",
                "meanings": [
                    {"pos": "adj.", "definition": "美丽的", "sources": ["人教七上U2"]}
                ]
            }
        ]
        
        result = import_service.import_from_json(db_session, data, "ipa_test")
        assert result["word_count"] == 2
        
        # 验证 apple 的 IPA
        apple = db_session.query(Word).filter_by(word="apple").first()
        assert apple is not None
        apple_phonetic = db_session.query(Phonetic).filter_by(word_id=apple.id).first()
        assert apple_phonetic is not None
        assert apple_phonetic.ipa == "/ˈæp.əl/"
        
        # 验证 beautiful 的 IPA
        beautiful = db_session.query(Word).filter_by(word="beautiful").first()
        assert beautiful is not None
        beautiful_phonetic = db_session.query(Phonetic).filter_by(word_id=beautiful.id).first()
        assert beautiful_phonetic is not None
        assert beautiful_phonetic.ipa == "/ˈbjuː.tə.fəl/"

    def test_import_without_ipa(self, db_session):
        """验证不提供 IPA 时也能正常导入（Phonetic 不被创建）。"""
        data = [
            {
                "word": "cat",
                "meanings": [
                    {"pos": "n.", "definition": "猫", "sources": []}
                ]
            }
        ]
        
        result = import_service.import_from_json(db_session, data, "no_ipa_test")
        assert result["word_count"] == 1
        
        cat = db_session.query(Word).filter_by(word="cat").first()
        phonetic = db_session.query(Phonetic).filter_by(word_id=cat.id).first()
        # 如果没有 IPA，Phonetic 不会被创建
        assert phonetic is None

    def test_csv_import_with_ipa(self, db_session):
        """验证 CSV 导入支持 ipa 列。"""
        csv_content = "word,pos,definition,source,ipa\napple,n.,苹果,教材1,/ˈæp.əl/\norange,n.,橙子,教材2,/ˈɔr.ɪndʒ/"
        result = import_service.import_from_csv(db_session, csv_content, "csv_ipa_test")
        assert result["word_count"] == 2
        
        apple = db_session.query(Word).filter_by(word="apple").first()
        apple_phonetic = db_session.query(Phonetic).filter_by(word_id=apple.id).first()
        assert apple_phonetic is not None
        assert apple_phonetic.ipa == "/ˈæp.əl/"
        
        orange = db_session.query(Word).filter_by(word="orange").first()
        orange_phonetic = db_session.query(Phonetic).filter_by(word_id=orange.id).first()
        assert orange_phonetic is not None
        assert orange_phonetic.ipa == "/ˈɔr.ɪndʒ/"

    def test_excel_import_with_ipa(self, db_session):
        """验证 Excel 导入支持 ipa 列。"""
        from openpyxl import Workbook
        import io
        
        # 创建测试 Excel
        wb = Workbook()
        ws = wb.active
        ws.append(["word", "pos", "definition", "source", "ipa"])
        ws.append(["apple", "n.", "苹果", "人教七上U1", "/ˈæp.əl/"])
        ws.append(["book", "n.", "书", "人教七上U2", "/bʊk/"])
        
        # 转为字节
        buffer = io.BytesIO()
        wb.save(buffer)
        excel_bytes = buffer.getvalue()
        
        # 导入
        result = import_service.import_from_json(
            db_session,
            import_service.parse_upload(excel_bytes, "test.xlsx"),
            "excel_ipa_test"
        )
        assert result["word_count"] == 2
        
        # 验证
        apple = db_session.query(Word).filter_by(word="apple").first()
        apple_phonetic = db_session.query(Phonetic).filter_by(word_id=apple.id).first()
        assert apple_phonetic is not None
        assert apple_phonetic.ipa == "/ˈæp.əl/"
        
        book = db_session.query(Word).filter_by(word="book").first()
        book_phonetic = db_session.query(Phonetic).filter_by(word_id=book.id).first()
        assert book_phonetic is not None
        assert book_phonetic.ipa == "/bʊk/"
